<#
.SYNOPSIS
Copy previously downloaded locked dataset/model inputs into another checkout.

.DESCRIPTION
This is an explicit bandwidth-saving mode, not a clean download. The source is
verified against upstream-lock.json before copying and the destination is
verified afterward. Predictions, score results, environments, generated code
checkouts, and .env.local are never copied.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $SourceRoot,
    [string] $DestinationRoot = ""
)
$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($DestinationRoot)) { $DestinationRoot = $scriptRoot }
$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)
$DestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)
$lockVerify = Join-Path $DestinationRoot "scripts\verify-upstream-lock.ps1"
$treeVerify = Join-Path $DestinationRoot "scripts\verify_dataset_tree.py"
$python = Join-Path $DestinationRoot ".venv\Scripts\python.exe"
$lockFile = Join-Path $DestinationRoot "upstream-lock.json"

function ConvertTo-ExtendedPath([string] $Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full.StartsWith("\\")) { return "\\?\UNC\" + $full.Substring(2) }
    return "\\?\" + $full
}

function Ensure-ShortRepoRoot([string] $RepoRoot) {
    $normalized = [System.IO.Path]::GetFullPath($RepoRoot)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalized.ToLowerInvariant()))
    } finally {
        $sha.Dispose()
    }
    $digest = ([System.BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant().Substring(0, 12)
    $alias = Join-Path (Join-Path (Join-Path $env:LOCALAPPDATA "OmniDocBenchAMD") $digest) "repo"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $alias) | Out-Null
    if (-not (Test-Path -LiteralPath $alias)) {
        New-Item -ItemType Junction -Path $alias -Target $normalized | Out-Null
    }
    return $alias
}

$null = Ensure-ShortRepoRoot $SourceRoot
$null = Ensure-ShortRepoRoot $DestinationRoot

function Copy-LockedFile([string] $Source, [string] $Destination) {
    $extendedSource = ConvertTo-ExtendedPath $Source
    if (-not [System.IO.File]::Exists($extendedSource)) { throw "Seed source missing: $Source" }
    $parent = Split-Path -Parent $Destination
    [System.IO.Directory]::CreateDirectory((ConvertTo-ExtendedPath $parent)) | Out-Null
    [System.IO.File]::Copy($extendedSource, (ConvertTo-ExtendedPath $Destination), $true)
}

if (-not (Test-Path -LiteralPath $python)) { throw "Destination locked Python missing: $python" }
foreach ($component in @("DatasetManifest", "Vlm", "Layout")) {
    $sourcePath = switch ($component) {
        "DatasetManifest" { Join-Path $SourceRoot "eval-infra\01-omnidocbench\data\OmniDocBench.json" }
        "Vlm" { Join-Path $SourceRoot "adapters\paddleocr-vl-1.6\models\PaddleOCR-VL-1.6-GGUF" }
        "Layout" { Join-Path $SourceRoot "adapters\paddleocr-vl-1.6\models\PP-DocLayoutV3-onnx" }
    }
    & powershell -ExecutionPolicy Bypass -File $lockVerify -Component $component -Path $sourcePath -LockFile $lockFile
    if ($LASTEXITCODE -ne 0) { throw "Seed source failed $component lock verification" }
}
& $python $treeVerify `
    --manifest (Join-Path $SourceRoot "eval-infra\01-omnidocbench\data\OmniDocBench.json") `
    --image-dir (Join-Path $SourceRoot "eval-infra\01-omnidocbench\data\images") `
    --lock $lockFile `
    --repo-root $SourceRoot
if ($LASTEXITCODE -ne 0) { throw "Seed source dataset tree lock verification failed" }

$sourceManifest = Join-Path $SourceRoot "eval-infra\01-omnidocbench\data\OmniDocBench.json"
$destinationManifest = Join-Path $DestinationRoot "eval-infra\01-omnidocbench\data\OmniDocBench.json"
Copy-LockedFile $sourceManifest $destinationManifest
$pages = @(Get-Content -Raw -Encoding UTF8 -LiteralPath $sourceManifest | ConvertFrom-Json)
foreach ($page in $pages) {
    $relative = [string]$page.page_info.image_path
    Copy-LockedFile `
        (Join-Path (Join-Path $SourceRoot "eval-infra\01-omnidocbench\data\images") $relative) `
        (Join-Path (Join-Path $DestinationRoot "eval-infra\01-omnidocbench\data\images") $relative)
}

foreach ($relative in @(
    "adapters\paddleocr-vl-1.6\models\PaddleOCR-VL-1.6-GGUF\PaddleOCR-VL-1.6-GGUF.gguf",
    "adapters\paddleocr-vl-1.6\models\PaddleOCR-VL-1.6-GGUF\PaddleOCR-VL-1.6-GGUF-mmproj.gguf",
    "adapters\paddleocr-vl-1.6\models\PP-DocLayoutV3-onnx\inference.onnx",
    "adapters\paddleocr-vl-1.6\models\PP-DocLayoutV3-onnx\inference.yml"
)) {
    Copy-LockedFile (Join-Path $SourceRoot $relative) (Join-Path $DestinationRoot $relative)
}

& powershell -ExecutionPolicy Bypass -File $lockVerify -Component DatasetManifest -Path $destinationManifest -LockFile $lockFile
if ($LASTEXITCODE -ne 0) { throw "Seeded manifest lock verification failed" }
& $python $treeVerify --manifest $destinationManifest --image-dir (Join-Path $DestinationRoot "eval-infra\01-omnidocbench\data\images") --lock $lockFile --repo-root $DestinationRoot
if ($LASTEXITCODE -ne 0) { throw "Seeded dataset tree lock verification failed" }
& powershell -ExecutionPolicy Bypass -File $lockVerify -Component Vlm -Path (Join-Path $DestinationRoot "adapters\paddleocr-vl-1.6\models\PaddleOCR-VL-1.6-GGUF") -LockFile $lockFile
if ($LASTEXITCODE -ne 0) { throw "Seeded VLM lock verification failed" }
& powershell -ExecutionPolicy Bypass -File $lockVerify -Component Layout -Path (Join-Path $DestinationRoot "adapters\paddleocr-vl-1.6\models\PP-DocLayoutV3-onnx") -LockFile $lockFile
if ($LASTEXITCODE -ne 0) { throw "Seeded layout lock verification failed" }

Write-Host "LOCKED INPUT SEED OK: $SourceRoot -> $DestinationRoot" -ForegroundColor Green
exit 0