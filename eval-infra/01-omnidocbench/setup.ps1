<#
.SYNOPSIS
Download OmniDocBench eval code (GitHub) + v1.6 dataset (1651 pages).

Model-agnostic: this infrastructure is required for ANY model's evaluation.
The eval code lives in OmniDocBench/ (git checkout); the dataset (ground-truth
manifest + 1651 page images) lives in data/.

.DESCRIPTION
Steps:
  1. Read mirrors.env (written by scripts/detect-mirrors.ps1) for GITHUB_BASE
     and the dataset source (HF_OR_MS / DATASET_URL).
  2. Clone OmniDocBench from $GITHUB_BASE/opendatalab/OmniDocBench.git (depth 1)
     into OmniDocBench/  -- skipped if pdf_validation.py already present.
  3. Download the v1.6 dataset into data/ -- skipped if OmniDocBench.json present.
     - modelscope: `modelscope download --dataset OpenDataLab/OmniDocBench --local_dir data`
     - huggingface: `huggingface-cli download opendatalab/OmniDocBench --repo-type dataset --local-dir data`

The dataset download (~1651 PNGs, ~18 min on a slow link) is idempotent: re-running
setup.ps1 after a partial/interrupted download resumes via the HF/MS CLI's own cache.

.PARAMETER SkipDataset
Skip the dataset download (use when you only need the eval code). Code clone is
always attempted if missing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1
  powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipDataset
#>
[CmdletBinding()]
param(
    [switch] $SkipDataset
)
$ErrorActionPreference = "Stop"

# NOTE: Join-Path is nested (rather than the PS 7+ 3-arg form) so this runs on
# Windows PowerShell 5.1 as well as PowerShell 7+.
$rootDir  = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)  # repo root
$envFile  = Join-Path $rootDir "mirrors.env"

# --- Parse mirrors.env (KEY=VALUE lines; ignore comments / blanks) ---
$cfg = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.*)$") { $cfg[$matches[1]] = $matches[2] }
    }
} else {
    Write-Host "WARN: mirrors.env not found at $envFile; using defaults." -ForegroundColor Yellow
    Write-Host "      Run scripts/detect-mirrors.ps1 first for a China-firewall-aware setup." -ForegroundColor Yellow
}
$githubBase = if ($cfg["GITHUB_BASE"]) { $cfg["GITHUB_BASE"] } else { "https://github.com" }
$hfOrMs    = if ($cfg["HF_OR_MS"])    { $cfg["HF_OR_MS"] }    else { "modelscope" }

# --- 1. Clone OmniDocBench eval code ---
$odbDir = Join-Path $PSScriptRoot "OmniDocBench"
$probe  = Join-Path $odbDir "pdf_validation.py"
if (-not (Test-Path $probe)) {
    $repoUrl = "$githubBase/opendatalab/OmniDocBench.git"
    Write-Host "Cloning OmniDocBench from $repoUrl ..." -ForegroundColor Cyan
    # --depth 1 keeps it small (no full history needed for eval).
    # If a stale/partial clone exists, remove it first so the clone is clean.
    if (Test-Path $odbDir) { Remove-Item -Recurse -Force $odbDir }
    git clone --depth 1 $repoUrl $odbDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed for OmniDocBench (URL: $repoUrl)" }
    if (-not (Test-Path $probe)) { throw "Clone succeeded but pdf_validation.py missing in $odbDir" }
    Write-Host "OmniDocBench code cloned to $odbDir" -ForegroundColor Green
} else {
    Write-Host "OmniDocBench code already present: $probe" -ForegroundColor Green
}

if ($SkipDataset) {
    Write-Host "Skipping dataset download (-SkipDataset)." -ForegroundColor Yellow
    Write-Host "OmniDocBench code setup complete." -ForegroundColor Green
    exit 0
}

# --- 2. Download v1.6 dataset (1651 pages + GT manifest) ---
$dataDir  = Join-Path $PSScriptRoot "data"
$manifest = Join-Path $dataDir "OmniDocBench.json"
if (Test-Path $manifest) {
    $imgCount = 0
    $imgDir = Join-Path $dataDir "images"
    if (Test-Path $imgDir) {
        $imgCount = (Get-ChildItem $imgDir -File -ErrorAction SilentlyContinue).Count
    }
    Write-Host "Dataset already present: $manifest ($imgCount images in images/)." -ForegroundColor Green
    Write-Host "OmniDocBench setup complete." -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if ($hfOrMs -eq "huggingface") {
    Write-Host "Downloading OmniDocBench v1.6 dataset from HuggingFace ..." -ForegroundColor Cyan
    huggingface-cli download opendatalab/OmniDocBench `
        --repo-type dataset --local-dir $dataDir
    if ($LASTEXITCODE -ne 0) { throw "huggingface-cli download failed" }
} else {
    Write-Host "Downloading OmniDocBench v1.6 dataset from ModelScope ..." -ForegroundColor Cyan
    Write-Host "(~1651 images; this can take ~18 minutes on a slow link.)" -ForegroundColor DarkGray
    modelscope download --dataset OpenDataLab/OmniDocBench --local_dir $dataDir
    if ($LASTEXITCODE -ne 0) { throw "modelscope download failed" }
}

if (-not (Test-Path $manifest)) {
    throw "Download reported success but $manifest is missing. Inspect $dataDir."
}

Write-Host "Dataset downloaded to $dataDir" -ForegroundColor Green
Write-Host "OmniDocBench setup complete." -ForegroundColor Green
exit 0
