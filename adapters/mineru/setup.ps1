<#
.SYNOPSIS
Provisioning for the MinerU (pipeline backend) adapter on Windows + AMD HIP.

.DESCRIPTION
Idempotent: every step self-checks and prints SKIP when already satisfied.

  0. Load .env.local (MINERU_ROCM_REPO, MINERU_WIN_ROCM_PYTHON).
  1. Inference Python exists AND torch has HIP (torch.version.hip +
     cuda.is_available()). If missing, prints the exact ROCm wheel install
     block (MinerU-ROCm docs/HANDOFF-windows-hip.md section 2) and exits 1 --
     the ROCm SDK install needs a human/UAC (AGENTS.md warning-3 pattern).
  2. mineru[pipeline]==3.4.4 installed (NEVER mineru[all] -- its VLM extra
     pins public torch 2.8.0 and clobbers the ROCm wheel).
  3. mineru_rocm importable (pip install -e MINERU_ROCM_REPO --no-deps).
  4. onnxruntime-directml==1.24.4 with DmlExecutionProvider FIRST. Installed
     LAST of all packages so the DirectML ORT binary wins over the CPU wheel.
  5. Pipeline weights present (~/mineru.json models-dir non-empty); else
     downloads via mineru-models-download, honouring HF_ENDPOINT from the
     repo-root mirrors.env when set.
  6. Prints SETUP OK + environment facts (torch HIP version, DML providers).
#>
#Requires -Version 5.1
param()
$ErrorActionPreference = 'Stop'

$adapterRoot = $PSScriptRoot
$repoRoot    = Split-Path -Parent (Split-Path -Parent $adapterRoot)

function Get-DotEnv {
    param([string]$Path)
    $v = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $v }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        if ($t -match "^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)\s*$") {
            $val = $matches[2].Trim()
            if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and $val[0] -in @("'", '"')) {
                $val = $val.Substring(1, $val.Length - 2)
            }
            $v[$matches[1]] = $val
        }
    }
    return $v
}

# --- 0. Load .env.local -----------------------------------------------------
$envFile = Join-Path $adapterRoot ".env.local"
if (-not (Test-Path $envFile)) {
    Write-Host "FAIL: $envFile missing." -ForegroundColor Red
    Write-Host "      Copy .env.local.example to .env.local and fill in the two paths." -ForegroundColor DarkGray
    exit 1
}
$dotenv = Get-DotEnv $envFile
$py           = $dotenv["MINERU_WIN_ROCM_PYTHON"]
$mineruRepo   = $dotenv["MINERU_ROCM_REPO"]
if ([string]::IsNullOrWhiteSpace($py) -or [string]::IsNullOrWhiteSpace($mineruRepo)) {
    Write-Host "FAIL: .env.local must set MINERU_ROCM_REPO and MINERU_WIN_ROCM_PYTHON." -ForegroundColor Red
    exit 1
}

# --- 1. Inference Python with HIP torch --------------------------------------
Write-Host "[1/6] torch HIP in inference env" -ForegroundColor Cyan
$torchOk = $false
if (Test-Path $py) {
    & $py -c "import torch; assert torch.version.hip and torch.cuda.is_available()" 2>$null
    $torchOk = ($LASTEXITCODE -eq 0)
}
if ($torchOk) {
    Write-Host "SKIP: torch with HIP already available ($py)" -ForegroundColor Yellow
} else {
    Write-Host "FAIL: inference Python missing or torch lacks HIP: $py" -ForegroundColor Red
    Write-Host @"
      Install the AMD Windows ROCm 7.2.1 SDK + cp312 torch wheels (needs a
      human for any UAC prompt -- AGENTS.md warning-3), then re-run setup:

      conda create -n mineru-win-rocm python=3.12 pip -y
      conda activate mineru-win-rocm
      pip install --no-cache-dir ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm-7.2.1.tar.gz
      pip install --no-cache-dir ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl ``
        https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl

      (MinerU-ROCm docs/HANDOFF-windows-hip.md section 2)
"@ -ForegroundColor DarkGray
    exit 1
}

# --- 2. mineru[pipeline]==3.4.4 ----------------------------------------------
Write-Host "[2/6] mineru[pipeline]==3.4.4" -ForegroundColor Cyan
& $py -c "import importlib.metadata as m; assert m.version('mineru') == '3.4.4'" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "SKIP: mineru 3.4.4 already installed" -ForegroundColor Yellow
} else {
    Write-Host "Installing mineru[pipeline]==3.4.4 (NEVER mineru[all])..." -ForegroundColor Cyan
    & $py -m pip install "mineru[pipeline]==3.4.4"
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: pip install mineru[pipeline]==3.4.4" -ForegroundColor Red; exit 1 }
}

# --- 3. mineru_rocm (editable, --no-deps) ------------------------------------
Write-Host "[3/6] mineru_rocm importable" -ForegroundColor Cyan
& $py -c "import mineru_rocm" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "SKIP: mineru_rocm already importable" -ForegroundColor Yellow
} else {
    if (-not (Test-Path $mineruRepo)) {
        Write-Host "FAIL: MINERU_ROCM_REPO not found: $mineruRepo" -ForegroundColor Red
        Write-Host "      git clone https://github.com/AIwork4me/MinerU-ROCm there, then re-run." -ForegroundColor DarkGray
        exit 1
    }
    Write-Host "Installing mineru_rocm editable from $mineruRepo ..." -ForegroundColor Cyan
    & $py -m pip install -e $mineruRepo --no-deps
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: pip install -e MINERU_ROCM_REPO" -ForegroundColor Red; exit 1 }
}

# --- 4. onnxruntime-directml LAST ---------------------------------------------
Write-Host "[4/6] onnxruntime-directml==1.24.4 (DmlExecutionProvider first)" -ForegroundColor Cyan
& $py -c "import onnxruntime as ort; import importlib.metadata as m; assert m.version('onnxruntime-directml') == '1.24.4'; assert ort.get_available_providers()[0] == 'DmlExecutionProvider'" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "SKIP: onnxruntime-directml 1.24.4 with DmlExecutionProvider first" -ForegroundColor Yellow
} else {
    Write-Host "Installing onnxruntime-directml==1.24.4 (last, so its binary wins)..." -ForegroundColor Cyan
    & $py -m pip install --force-reinstall --no-deps "onnxruntime-directml==1.24.4"
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: pip install onnxruntime-directml" -ForegroundColor Red; exit 1 }
}

# --- 5. Pipeline weights -------------------------------------------------------
Write-Host "[5/6] pipeline weights (~/mineru.json models-dir)" -ForegroundColor Cyan
$mineruJson = Join-Path $HOME "mineru.json"
$weightsDir = $null
if (Test-Path $mineruJson) {
    try {
        $cfg = Get-Content -LiteralPath $mineruJson -Raw | ConvertFrom-Json
        $weightsDir = $cfg.'models-dir'.pipeline
    } catch { }
}
if ($weightsDir -and (Test-Path $weightsDir) -and @(Get-ChildItem -Recurse -File $weightsDir -ErrorAction SilentlyContinue | Select-Object -First 1).Count -gt 0) {
    Write-Host "SKIP: weights present at $weightsDir" -ForegroundColor Yellow
} else {
    $mirrorsFile = Join-Path $repoRoot "mirrors.env"
    $mirrors = Get-DotEnv $mirrorsFile
    if ($mirrors.ContainsKey("HF_ENDPOINT") -and -not [string]::IsNullOrWhiteSpace($mirrors["HF_ENDPOINT"])) {
        $env:HF_ENDPOINT = $mirrors["HF_ENDPOINT"]
        Write-Host "Using HF_ENDPOINT=$env:HF_ENDPOINT from mirrors.env" -ForegroundColor Cyan
    }
    $dl = Join-Path (Split-Path -Parent $py) "Scripts\mineru-models-download.exe"
    if (-not (Test-Path $dl)) { $dl = "mineru-models-download" }
    Write-Host "Downloading pipeline weights: $dl -s huggingface -m pipeline" -ForegroundColor Cyan
    & $dl -s huggingface -m pipeline
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: weights download failed (see docs/pitfalls.md#network)" -ForegroundColor Red
        exit 1
    }
}

# --- 6. Facts ------------------------------------------------------------------
& $py -c "import torch, onnxruntime as ort; print('torch', torch.__version__, 'hip', torch.version.hip); print('providers', ort.get_available_providers())"
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: final environment check" -ForegroundColor Red; exit 1 }
Write-Host "SETUP OK: MinerU adapter environment ready." -ForegroundColor Green
exit 0
