<#
.SYNOPSIS
Verify locked Git checkouts and downloaded files used by the AMD Windows path.

.DESCRIPTION
Reads upstream-lock.json and fails closed on a missing file, byte-size mismatch,
SHA-256 mismatch, or Git commit mismatch. Callers can verify one component after
download or all currently present components. Optional lock entries whose hash
is null are reported as NOT LOCKED and fail when explicitly requested.
#>
[CmdletBinding()]
param(
    [ValidateSet("AllPresent", "OmniDocBench", "Pipeline", "LlamaCpuZip", "LlamaHipZip", "Vlm", "Layout", "DatasetManifest", "UbuntuRootfs", "ImageMagick")]
    [string] $Component = "AllPresent",
    [string] $Path = "",
    [string] $LockFile = ""
)
$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($LockFile)) { $LockFile = Join-Path $rootDir "upstream-lock.json" }
if (-not (Test-Path -LiteralPath $LockFile -PathType Leaf)) { throw "Upstream lock missing: $LockFile" }
$lock = Get-Content -Raw -Encoding UTF8 -LiteralPath $LockFile | ConvertFrom-Json

function Assert-LockedFile {
    param([string] $Name, [string] $FilePath, $Entry)
    if ([string]::IsNullOrWhiteSpace([string]$Entry.sha256) -or $null -eq $Entry.bytes) {
        throw "$Name is NOT LOCKED in $LockFile; record bytes and SHA-256 before executing it."
    }
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw "$Name missing: $FilePath" }
    $item = Get-Item -LiteralPath $FilePath
    if ([long]$item.Length -ne [long]$Entry.bytes) {
        throw "$Name size mismatch: expected $($Entry.bytes), actual $($item.Length): $FilePath"
    }
    $actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = ([string]$Entry.sha256).ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "$Name SHA-256 mismatch: expected $expected, actual ${actual}: $FilePath"
    }
    Write-Host "LOCK OK: $Name ($actual)" -ForegroundColor Green
}

function Assert-LockedGit {
    param([string] $Name, [string] $RepoPath, $Entry)
    if (-not (Test-Path -LiteralPath (Join-Path $RepoPath ".git"))) { throw "$Name checkout missing: $RepoPath" }
    $actual = (& git -C $RepoPath rev-parse HEAD 2>$null).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { throw "$Name is not a readable Git checkout: $RepoPath" }
    $expected = ([string]$Entry.commit).ToLowerInvariant()
    if ($actual -ne $expected) { throw "$Name commit mismatch: expected $expected, actual ${actual}: $RepoPath" }
    Write-Host "LOCK OK: $Name ($actual)" -ForegroundColor Green
}

function Resolve-RequestedPath([string] $DefaultPath) {
    if (-not [string]::IsNullOrWhiteSpace($Path)) { return $Path }
    if ([System.IO.Path]::IsPathRooted($DefaultPath)) { return $DefaultPath }
    return Join-Path $rootDir $DefaultPath
}

switch ($Component) {
    "OmniDocBench" { Assert-LockedGit "OmniDocBench" (Resolve-RequestedPath "eval-infra\01-omnidocbench\OmniDocBench") $lock.git.omnidocbench }
    "Pipeline" { Assert-LockedGit "PaddleOCR-VL-ROCm" (Resolve-RequestedPath "..\PaddleOCR-VL-ROCm") $lock.git.paddleocr_vl_rocm }
    "LlamaCpuZip" { Assert-LockedFile "llama.cpp CPU ZIP" (Resolve-RequestedPath (Join-Path $env:TEMP $lock.downloads.llama_cpu_zip.file)) $lock.downloads.llama_cpu_zip }
    "LlamaHipZip" { Assert-LockedFile "llama.cpp HIP ZIP" (Resolve-RequestedPath (Join-Path $env:TEMP $lock.downloads.llama_hip_zip.file)) $lock.downloads.llama_hip_zip }
    "Vlm" {
        $base = Resolve-RequestedPath "adapters\paddleocr-vl-1.6\models\PaddleOCR-VL-1.6-GGUF"
        foreach ($property in $lock.huggingface.vlm.files.PSObject.Properties) { Assert-LockedFile "VLM/$($property.Name)" (Join-Path $base $property.Name) $property.Value }
    }
    "Layout" {
        $base = Resolve-RequestedPath "adapters\paddleocr-vl-1.6\models\PP-DocLayoutV3-onnx"
        foreach ($property in $lock.huggingface.layout.files.PSObject.Properties) { Assert-LockedFile "Layout/$($property.Name)" (Join-Path $base $property.Name) $property.Value }
    }
    "DatasetManifest" { Assert-LockedFile "OmniDocBench manifest" (Resolve-RequestedPath "eval-infra\01-omnidocbench\data\OmniDocBench.json") $lock.huggingface.dataset.manifest }
    "UbuntuRootfs" { Assert-LockedFile "Ubuntu rootfs" (Resolve-RequestedPath (Join-Path $env:TEMP $lock.downloads.ubuntu_rootfs.file)) $lock.downloads.ubuntu_rootfs }
    "ImageMagick" { Assert-LockedFile "ImageMagick AppImage" (Resolve-RequestedPath $lock.downloads.imagemagick_appimage.file) $lock.downloads.imagemagick_appimage }
    "AllPresent" {
        $checks = @(
            @("OmniDocBench", "eval-infra\01-omnidocbench\OmniDocBench"),
            @("Vlm", "adapters\paddleocr-vl-1.6\models\PaddleOCR-VL-1.6-GGUF"),
            @("Layout", "adapters\paddleocr-vl-1.6\models\PP-DocLayoutV3-onnx"),
            @("DatasetManifest", "eval-infra\01-omnidocbench\data\OmniDocBench.json")
        )
        foreach ($check in $checks) {
            if (Test-Path -LiteralPath (Join-Path $rootDir $check[1])) {
                & $PSCommandPath -Component $check[0] -LockFile $LockFile
                if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            }
        }
    }
}
Write-Host "UPSTREAM LOCK VERIFY OK: $Component" -ForegroundColor Green
exit 0