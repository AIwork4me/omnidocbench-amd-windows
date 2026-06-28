<#
.SYNOPSIS
Install the paddleocr-vl-rocm pipeline package (the adapter's core dependency).

.DESCRIPTION
run_adapter.py imports `paddleocr_vl_rocm` -- the proven inference pipeline
(ONNX layout detection + OpenAI-compatible VLM serving) from the separate
PaddleOCR-VL-ROCm project. This script provisions that package:

  Phase 1 -- Clone PaddleOCR-VL-ROCm
      `git clone` from $GITHUB_BASE/AIwork4me/PaddleOCR-VL-ROCm.git (depth 1)
      into a sibling directory next to this repo's adapter, defaulting to
      ../PaddleOCR-VL-ROCm. Skipped if the checkout already exists.

  Phase 2 -- pip install -e
      Installs the package in editable mode into the target Python
      (prefers the repo-root .venv from eval-infra/01-omnidocbench/setup.ps1;
      falls back to the active `python`). Brings onnxruntime, opencv, pillow,
      requests, ... as dependencies.

Idempotent: a no-op if the package is already importable in the target Python.

.PARAMETER CloneDir
Where to clone PaddleOCR-VL-ROCm. Defaults to ../PaddleOCR-VL-ROCm (a sibling
of this repo's checkout). Pass an absolute path to override.

.PARAMETER Python
Python executable to install into. Defaults to the repo-root .venv
(.venv\Scripts\python.exe) if present, else the `python` on PATH.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Python C:\path\to\.venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [string] $CloneDir,
    [string] $Python
)
$ErrorActionPreference = "Stop"

# adapterRoot = adapters/paddleocr-vl-1.6 ; repoRoot = repo top.
# Nested Split-Path so this runs on Windows PowerShell 5.1 as well as PS 7+.
$adapterRoot = Split-Path -Parent $PSScriptRoot
$repoRoot    = Split-Path -Parent (Split-Path -Parent $adapterRoot)

# --- mirrors.env (GITHUB_BASE; respects China-firewall proxies) ---
$mirrorsFile = Join-Path $repoRoot "mirrors.env"
$mirrors = @{}
if (Test-Path $mirrorsFile) {
    Get-Content $mirrorsFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.*)$") { $mirrors[$matches[1]] = $matches[2] }
    }
}
$githubBase = if ($mirrors["GITHUB_BASE"]) { $mirrors["GITHUB_BASE"] } else { "https://github.com" }
$pypiIndex  = if ($mirrors["PYPI_INDEX"])  { $mirrors["PYPI_INDEX"] }  else { "https://pypi.tuna.tsinghua.edu.cn/simple" }

# --- target Python: prefer the repo-root .venv ---
if ([string]::IsNullOrWhiteSpace($Python)) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $Python = $venvPython
    } else {
        $Python = "python"
        Write-Host "WARN: repo-root .venv not found; installing into the active 'python'." -ForegroundColor Yellow
        Write-Host "      Run eval-infra\01-omnidocbench\setup.ps1 first to create the .venv." -ForegroundColor Yellow
    }
}

# --- clone dir: default to a sibling of this repo ---
if ([string]::IsNullOrWhiteSpace($CloneDir)) {
    # repoRoot's parent holds sibling checkouts; clone there.
    $CloneDir = Join-Path (Split-Path -Parent $repoRoot) "PaddleOCR-VL-ROCm"
}

# --- Phase 0: already installed? (idempotent fast-path) ---
Write-Host "Checking for paddleocr_vl_rocm in $Python ..." -ForegroundColor Cyan
& $Python -c "import paddleocr_vl_rocm" *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "paddleocr_vl_rocm already importable in $Python -- nothing to do." -ForegroundColor Green
    exit 0
}

# --- Phase 1: clone PaddleOCR-VL-ROCm ---
$probe = Join-Path $CloneDir "pyproject.toml"
if (Test-Path $probe) {
    Write-Host "[1/2] PaddleOCR-VL-ROCm already cloned: $CloneDir" -ForegroundColor Green
} else {
    $repoUrl = "$githubBase/AIwork4me/PaddleOCR-VL-ROCm.git"
    Write-Host "[1/2] Cloning PaddleOCR-VL-ROCm from $repoUrl ..." -ForegroundColor Cyan
    Write-Host "      Destination: $CloneDir"
    # --depth 1 keeps it small; the adapter only needs the current source.
    if (Test-Path $CloneDir) { Remove-Item -Recurse -Force $CloneDir }
    git clone --depth 1 $repoUrl $CloneDir
    if ($LASTEXITCODE -ne 0) {
        throw "git clone failed for PaddleOCR-VL-ROCm (URL: $repoUrl). See docs/pitfalls.md#network."
    }
    if (-not (Test-Path $probe)) {
        throw "Clone succeeded but pyproject.toml missing in $CloneDir -- wrong repo?"
    }
    Write-Host "      Cloned to $CloneDir" -ForegroundColor Green
}

# --- Phase 2: pip install -e (editable) ---
Write-Host "[2/2] pip install -e $CloneDir (index: $pypiIndex) ..." -ForegroundColor Cyan
& $Python -m pip install -e $CloneDir -i $pypiIndex
if ($LASTEXITCODE -ne 0) {
    throw "pip install -e failed for PaddleOCR-VL-ROCm (index: $pypiIndex). See docs/pitfalls.md#network."
}

# --- Verify ---
& $Python -c "import paddleocr_vl_rocm; print('paddleocr_vl_rocm', getattr(paddleocr_vl_rocm,'__version__','(no __version__)'))"
if ($LASTEXITCODE -ne 0) {
    throw "Install reported success but 'import paddleocr_vl_rocm' failed in $Python."
}

Write-Host ""
Write-Host "=== paddleocr_vl_rocm installed (editable) ===" -ForegroundColor Green
Write-Host "  Checkout: $CloneDir"
Write-Host "  Python:   $Python"
Write-Host "  run_adapter.py can now import it."
exit 0
