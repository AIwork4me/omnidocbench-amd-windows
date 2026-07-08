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
  4. Create a repo-root .venv (Python 3.10/3.11 -- OmniDocBench is NOT 3.12+
     compatible) and pip install the OmniDocBench runtime deps into it. The
     venv is what eval-infra/03-scoring/score.ps1 runs pdf_validation.py with.
     Skipped if .venv is already importable.

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
# PyPI index (from detect-mirrors.ps1). Fall back to Tsinghua (China-friendly)
# then pypi.org. Used by the venv install in step 4.
$pypiIndex = if ($cfg["PYPI_INDEX"]) { $cfg["PYPI_INDEX"] } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }

# --- 1. Clone OmniDocBench eval code ---
$odbDir = Join-Path $PSScriptRoot "OmniDocBench"
$probe  = Join-Path $odbDir "pdf_validation.py"
$gitHead = Join-Path $odbDir ".git\HEAD"
if (-not (Test-Path $probe)) {
    $repoUrl = "$githubBase/opendatalab/OmniDocBench.git"
    # Resumable clone: if a .git exists (partial/interrupted clone), resume via
    # fetch+reset instead of nuking the dir and re-downloading from scratch. A
    # bare Remove-Item on re-run would discard everything already fetched.
    if (Test-Path $gitHead) {
        Write-Host "Incomplete clone detected (no pdf_validation.py); resuming via git fetch ..." -ForegroundColor Cyan
        git -C $odbDir fetch --depth 1 origin
        if ($LASTEXITCODE -eq 0) {
            git -C $odbDir reset --hard origin/HEAD
        } else {
            Write-Host "git fetch failed; removing partial clone and retrying fresh." -ForegroundColor Yellow
            Remove-Item -Recurse -Force $odbDir
            git clone --depth 1 $repoUrl $odbDir
        }
    } else {
        Write-Host "Cloning OmniDocBench from $repoUrl ..." -ForegroundColor Cyan
        # --depth 1 keeps it small (no full history needed for eval).
        git clone --depth 1 $repoUrl $odbDir
    }
    if ($LASTEXITCODE -ne 0) { throw "git clone failed for OmniDocBench (URL: $repoUrl)" }
    if (-not (Test-Path $probe)) { throw "Clone succeeded but pdf_validation.py missing in $odbDir" }
    Write-Host "OmniDocBench code cloned to $odbDir" -ForegroundColor Green
} else {
    Write-Host "OmniDocBench code already present: $probe" -ForegroundColor Green
}

# --- 1a. Apply repo-maintained OmniDocBench compatibility patches -----------
# The OmniDocBench checkout is a generated dependency and is ignored by this
# repo. Keep local scoring compatibility fixes reproducible by applying tracked
# patch files after clone/resume. Idempotency is handled with a reverse patch
# check: if the patch can be reversed cleanly, it is already applied.
$patchDir = Join-Path $PSScriptRoot "patches"
$formulaPatch = Join-Path $patchDir "0001-formula-cdm-normalization.patch"
if (Test-Path $formulaPatch) {
    Write-Host "Checking Formula CDM normalization patch ..." -ForegroundColor Cyan
    git -C $odbDir apply --reverse --check $formulaPatch *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Formula CDM normalization patch already applied." -ForegroundColor Green
    } else {
        git -C $odbDir apply --check $formulaPatch
        if ($LASTEXITCODE -ne 0) {
            throw "Formula CDM normalization patch does not apply cleanly. Inspect $formulaPatch and $odbDir."
        }
        git -C $odbDir apply $formulaPatch
        if ($LASTEXITCODE -ne 0) { throw "Formula CDM normalization patch failed." }
        Write-Host "Formula CDM normalization patch applied." -ForegroundColor Green
    }
}

# --- 1b. Create repo-root .venv + install OmniDocBench deps ---
# OmniDocBench is NOT Python 3.12+ compatible (uses inspect.getargspec /
# distutils removed in 3.12). Prefer 3.11, then 3.10; fall back to the default
# `python` only if neither launcher exists (and warn).
#
# The venv lives at <repo>/.venv so eval-infra/03-scoring/score.ps1 can target
# .venv\Scripts\python.exe directly instead of relying on a bare `python` that
# may be 3.13. Idempotent: skipped if .venv\Scripts\python.exe already exists
# and the deps are importable there.
$venvDir = Join-Path $rootDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvReady = $false
if (Test-Path $venvPython) {
    # Probe: can the venv import the core OmniDocBench deps?
    $probePy = "import importlib; [importlib.import_module(m) for m in ('pylatexenc','PIL','numpy','pandas','yaml','Levenshtein','apted')]"
    & $venvPython -c $probePy *> $null
    if ($LASTEXITCODE -eq 0) { $venvReady = $true }
}

if ($venvReady) {
    Write-Host ".venv already provisioned with OmniDocBench deps: $venvPython" -ForegroundColor Green
} else {
    # Pick a Python 3.10/3.11 interpreter via the `py` launcher (Windows-only,
    # ships with python.org installers). -p selects the highest installed that
    # matches the version spec.
    $basePy = $null
    foreach ($ver in @("-3.11", "-3.10")) {
        $test = & py $ver --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $test -match "Python 3\.(10|11)\.") {
            $basePy = "py $ver"
            Write-Host "Using Python $ver for venv: $test" -ForegroundColor DarkGray
            break
        }
    }
    if (-not $basePy) {
        $sysVer = & python --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $sysVer -match "Python 3\.(10|11)\.") {
            $basePy = "python"
        } else {
            Write-Host "WARN: no Python 3.10/3.11 found via 'py'/'python' (got: '$sysVer')." -ForegroundColor Yellow
            Write-Host "      OmniDocBench needs Python < 3.12 (see docs/pitfalls.md#python-version)." -ForegroundColor Yellow
            Write-Host "      Creating venv from the default python anyway -- scoring may fail with import errors." -ForegroundColor Yellow
            $basePy = "python"
        }
    }

    Write-Host "Creating .venv at $venvDir ..." -ForegroundColor Cyan
    Invoke-Expression "$basePy -m venv `"$venvDir`""
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed (interpreter: $basePy)" }

    # Upgrade pip first (some old bundled pip chokes on newer wheels).
    & $venvPython -m pip install --upgrade pip -i $pypiIndex *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: pip self-upgrade failed; continuing with the bundled pip." -ForegroundColor Yellow
    }

    # OmniDocBench runtime deps (mirrors the list used by the WSL CDM venv in
    # eval-infra/02-cdm-environment/setup.sh step 9). Unpinned so a fresh
    # install gets currently-working versions.
    $deps = "apted beautifulsoup4 evaluate func-timeout Levenshtein loguru lxml numpy pandas Pillow pylatexenc PyYAML scipy tabulate tqdm nltk matplotlib"
    Write-Host "Installing OmniDocBench deps into .venv (index: $pypiIndex) ..." -ForegroundColor Cyan
    $depsArgs = $deps -split ' '
    & $venvPython -m pip install -i $pypiIndex $depsArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip install of OmniDocBench deps failed (index: $pypiIndex). Re-run setup.ps1; if it persists see docs/pitfalls.md#network."
    }
    Write-Host "OmniDocBench deps installed into .venv" -ForegroundColor Green
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
        # @() for PS 5.1: a single-file dir unwraps to a scalar (empty .Count).
        $imgCount = @(Get-ChildItem $imgDir -File -ErrorAction SilentlyContinue).Count
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
