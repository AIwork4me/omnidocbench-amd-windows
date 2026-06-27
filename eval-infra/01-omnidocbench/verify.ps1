<#
.SYNOPSIS
Verify OmniDocBench eval code + v1.6 dataset are present and complete.

Checks:
  - OmniDocBench/pdf_validation.py exists (code cloned).
  - data/OmniDocBench.json exists (GT manifest downloaded).
  - data/images/ contains ~1651 page images.
  - Optional: a hard-subset manifest exists for v16-hard.yaml
    (data/OmniDocBench_hard296.json). This is a derivative file produced by
    filtering the full manifest; its absence is a WARNING, not a failure.

Exit code 0 = OK, 1 = FAIL. Suitable for chaining in full-verify.ps1 (Task 7).
#>
$ErrorActionPreference = "Stop"

$odbDir  = Join-Path $PSScriptRoot "OmniDocBench"
$dataDir = Join-Path $PSScriptRoot "data"

$ok = $true

# --- Code ---
$probe = Join-Path $odbDir "pdf_validation.py"
if (-not (Test-Path $probe)) {
    Write-Host "FAIL: OmniDocBench code missing (pdf_validation.py not found at $probe)." -ForegroundColor Red
    Write-Host "      Run setup.ps1 to clone the repo." -ForegroundColor DarkGray
    $ok = $false
} else {
    Write-Host "OK: OmniDocBench code present ($probe)" -ForegroundColor Green
}

# --- GT manifest ---
$manifest = Join-Path $dataDir "OmniDocBench.json"
if (-not (Test-Path $manifest)) {
    Write-Host "FAIL: GT manifest missing (OmniDocBench.json not found at $manifest)." -ForegroundColor Red
    Write-Host "      Run setup.ps1 to download the dataset." -ForegroundColor DarkGray
    $ok = $false
} else {
    Write-Host "OK: GT manifest present ($manifest)" -ForegroundColor Green
}

# --- Images (~1651 expected) ---
$imgDir   = Join-Path $dataDir "images"
$imgCount = 0
if (Test-Path $imgDir) {
    # Count any image file (dataset is PNG, but accept jpg/jpeg too for robustness).
    $imgCount = (Get-ChildItem $imgDir -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @(".png", ".jpg", ".jpeg")
    }).Count
}

if ($imgCount -lt 1000) {
    Write-Host ("FAIL: only {0} images in {1} (expected ~1651)." -f $imgCount, $imgDir) -ForegroundColor Red
    $ok = $false
} else {
    Write-Host ("OK: {0} page images present (expected ~1651)." -f $imgCount) -ForegroundColor Green
}

# --- Hard subset manifest (optional derivative; WARNING only) ---
$hardManifest = Join-Path $dataDir "OmniDocBench_hard296.json"
if (-not (Test-Path $hardManifest)) {
    Write-Host "WARN: hard-subset manifest missing ($hardManifest)." -ForegroundColor Yellow
    Write-Host "      Not required for the full run; v16-hard.yaml needs it (Task 5 filters it)." -ForegroundColor DarkGray
} else {
    Write-Host "OK: hard-subset manifest present ($hardManifest)" -ForegroundColor Green
}

if ($ok) {
    Write-Host "VERIFY OK: OmniDocBench code + dataset ready." -ForegroundColor Green
    exit 0
} else {
    Write-Host "VERIFY FAILED: see messages above." -ForegroundColor Red
    exit 1
}
