<#
.SYNOPSIS
Release gate: audit a tag/release before it can be published.

.DESCRIPTION
Fails (exit 1) unless ALL of the following hold:

  1. git tag <Tag> exists and equals the pyproject version
  2. CHANGELOG.md has an entry for the version
  3. the test suite is green (uv run pytest -q)
  4. the README benchmark tables are generated from benchmarks/index.json
     (render is a no-op)
  5. benchmarks/index.json passes scripts/validate_benchmark_index.py
  6. adapter manifests pass scripts/validate_adapter_manifest.py --strict
  7. the git working tree is clean
  8. release notes are written for the tag (docs/release-<tag>.md) and state
     verified devices, unverified devices, known limitations and evidence
     levels (clean-room vs validated-resumed vs smoke)

SBOM + SHA256SUMS + evidence manifest are produced under
outputs/release/<tag>/ by -WriteArtifacts.
#>
[CmdletBinding()]
param(
    [string] $Tag = "",
    [switch] $WriteArtifacts
)
$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $PSScriptRoot
$py = Join-Path $rootDir ".venv\Scripts\python.exe"

function Fail([string] $Message) {
    Write-Host "RELEASE GATE FAIL: $Message" -ForegroundColor Red
    exit 1
}

$requiredReleaseFiles = @(
    ".venv\Scripts\python.exe",
    "scripts\verify_uv_lock_variants.py",
    "uv.lock",
    "locks\uv.tuna.lock",
    "locks\uv.aliyun.lock",
    "locks\manifest.json"
)
foreach ($relativePath in $requiredReleaseFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $rootDir $relativePath) -PathType Leaf)) {
        Fail "required release file is missing: $relativePath"
    }
}

# Validate the tracked three-source lock catalog with the already-locked
# repository interpreter before any release can succeed.
& $py (Join-Path $rootDir "scripts\verify_uv_lock_variants.py") `
    --root $rootDir --manifest "locks\manifest.json"
if ($LASTEXITCODE -ne 0) { Fail "uv lock catalog verification failed" }

$pyproject = (Get-Content -Raw -LiteralPath (Join-Path $rootDir "pyproject.toml")) -replace "`r`n", "`n"
$versionMatch = [regex]::Match($pyproject, '(?m)^version = "([^"]+)"$')
if (-not $versionMatch.Success) { Fail "pyproject.toml has no version declaration" }
$version = $versionMatch.Groups[1].Value
if (-not $Tag) { $Tag = "v$version" }

# 1. tag == pyproject version
$tags = @(& git -C $rootDir tag -l "$Tag")
if ($tags.Count -eq 0) { Fail "tag $Tag does not exist (create it before running the gate)" }
if ($Tag -ne "v$version") { Fail "tag $Tag does not match pyproject version $version" }

# 2. CHANGELOG updated
$changelog = Get-Content -Raw -LiteralPath (Join-Path $rootDir "CHANGELOG.md")
if ($changelog -notmatch "## \[$version\]") { Fail "CHANGELOG.md has no entry for $version" }

# 3. tests green
Write-Host "Running the full test suite..." -ForegroundColor Cyan
# Use the locked interpreter as a module: `uv run pytest` does not put the
# repository root on sys.path on Windows (tests import `scripts.*`) and can
# trigger a network re-sync against a mirror. `python -m pytest` matches how
# every local verification command in this repo runs the suite.
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { Fail "test suite failed" }

# 4. README tables generated (drift check)
& $py (Join-Path $rootDir "scripts\render_benchmark_tables.py")
if ($LASTEXITCODE -ne 0) { Fail "benchmark table renderer failed" }
$drift = & git -C $rootDir diff --stat -- README.md README.zh-CN.md
if ($drift) { Fail "README benchmark tables drifted from benchmarks/index.json: run scripts/render_benchmark_tables.py and commit" }

# 5. benchmark evidence schema
& $py (Join-Path $rootDir "scripts\validate_benchmark_index.py")
if ($LASTEXITCODE -ne 0) { Fail "benchmarks/index.json invalid" }

# 6. adapter manifests
$manifestsOk = $true
foreach ($adapter in @(Get-ChildItem -Directory (Join-Path $rootDir "adapters") | Where-Object { Test-Path (Join-Path $_.FullName "adapter.json") } | ForEach-Object { $_.Name })) {
    & $py (Join-Path $rootDir "scripts\validate_adapter_manifest.py") --adapter $adapter --strict
    if ($LASTEXITCODE -ne 0) { $manifestsOk = $false }
}
if (-not $manifestsOk) { Fail "one or more adapter manifests are invalid" }

# 7. clean tree
$status = & git -C $rootDir status --porcelain
if ($status) { Fail "working tree is dirty:" + ($status -join "; ") }

# 8. release notes
$notes = Join-Path $rootDir "docs\release-$Tag.md"
if (-not (Test-Path -LiteralPath $notes)) { Fail "release notes missing: docs/release-$Tag.md" }
$notesText = Get-Content -Raw -LiteralPath $notes
foreach ($required in @("Verified devices", "Unverified devices", "Known limitations", "Evidence levels")) {
    if ($notesText -notmatch $required) { Fail "release notes must state: $required" }
}

Write-Host ""
Write-Host "RELEASE GATE OK: $Tag (version $version)" -ForegroundColor Green

if ($WriteArtifacts) {
    $outDir = Join-Path $rootDir "outputs\release\$Tag"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    & uv run --directory $rootDir pip install cyclonedx-bom -q
    & uv run --directory $rootDir cyclonedx-py -e -o (Join-Path $outDir "sbom.cdx.json")
    if ($LASTEXITCODE -ne 0) { Fail "SBOM generation failed" }
    # SHA256SUMS over the release-critical artifacts
    $hashLines = @()
    foreach ($rel in @("benchmarks\index.json", "benchmarks\schema.json", "upstream-lock.json", "uv.lock", "locks\uv.tuna.lock", "locks\uv.aliyun.lock", "locks\manifest.json", "pyproject.toml", "CHANGELOG.md")) {
        $path = Join-Path $rootDir $rel
        if (Test-Path -LiteralPath $path) {
            $sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
            $hashLines += "$sha  $rel"
        }
    }
    Set-Content -LiteralPath (Join-Path $outDir "SHA256SUMS") -Value $hashLines -Encoding ASCII
    $manifest = [ordered]@{
        tag = $Tag
        version = $version
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        sha256sums = "outputs/release/$Tag/SHA256SUMS"
        sbom = "outputs/release/$Tag/sbom.cdx.json"
        evidence = "docs/release-$Tag.md"
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $outDir "evidence-manifest.json"), ($manifest | ConvertTo-Json -Depth 6), $utf8NoBom)
    Write-Host "Release artifacts written to $outDir" -ForegroundColor Green
}
exit 0
