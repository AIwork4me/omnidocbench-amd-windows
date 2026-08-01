<#
.SYNOPSIS
Health check for the MinerU (pipeline backend) adapter environment.

.DESCRIPTION
Exit 0 = OK, 1 = FAIL. Each check prints PASS/FAIL plus a fix hint on FAIL.

  1. .env.local present; MINERU_ROCM_REPO exists on disk.
  2. Inference Python has HIP torch (prints GPU name; expect AMD Radeon).
  3. onnxruntime with DmlExecutionProvider first.
  4. Weights dir from ~/mineru.json with layout/MFR/OCR model files.
  5. Smoke: one dataset page through the adapter into a temp dir; assert the
     output .md exists and is > 100 bytes. (First run warms up the models on
     GPU -- allow 1-3 minutes.)
#>
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$adapterRoot = $PSScriptRoot
$repoRoot    = Split-Path -Parent (Split-Path -Parent $adapterRoot)
$envFile     = Join-Path $adapterRoot ".env.local"

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

$ok = $true

# --- 1. .env.local + MINERU_ROCM_REPO ----------------------------------------
if (-not (Test-Path $envFile)) {
    Write-Host "FAIL [1/5]: $envFile missing -- copy .env.local.example and run setup.ps1." -ForegroundColor Red
    exit 1
}
$dotenv = Get-DotEnv $envFile
$py         = $dotenv["MINERU_WIN_ROCM_PYTHON"]
$mineruRepo = $dotenv["MINERU_ROCM_REPO"]
if ([string]::IsNullOrWhiteSpace($py) -or -not (Test-Path $py)) {
    Write-Host "FAIL [1/5]: MINERU_WIN_ROCM_PYTHON missing/not found: $py" -ForegroundColor Red
    Write-Host "      Fix .env.local, then re-run setup.ps1." -ForegroundColor DarkGray
    exit 1
}
if ([string]::IsNullOrWhiteSpace($mineruRepo) -or -not (Test-Path $mineruRepo)) {
    Write-Host "FAIL [1/5]: MINERU_ROCM_REPO not found: $mineruRepo" -ForegroundColor Red
    Write-Host "      Fix .env.local to point at the MinerU-ROCm checkout." -ForegroundColor DarkGray
    $ok = $false
} else {
    Write-Host "PASS [1/5]: .env.local OK, MINERU_ROCM_REPO=$mineruRepo" -ForegroundColor Green
}

# --- 2. torch HIP + GPU name ---------------------------------------------------
$gpuLine = & $py -c "import torch; assert torch.version.hip and torch.cuda.is_available(); print(torch.cuda.get_device_name(0))" 2>$null
if ($LASTEXITCODE -eq 0 -and $gpuLine -match "AMD|Radeon") {
    Write-Host "PASS [2/5]: torch HIP GPU: $gpuLine" -ForegroundColor Green
} else {
    Write-Host "FAIL [2/5]: torch HIP check failed (got: $gpuLine)" -ForegroundColor Red
    Write-Host "      Re-run setup.ps1; ROCm wheel install is a human step (HANDOFF-windows-hip.md section 2)." -ForegroundColor DarkGray
    $ok = $false
}

# --- 3. onnxruntime DML provider first ------------------------------------------
& $py -c "import onnxruntime as ort; assert ort.get_available_providers()[0]=='DmlExecutionProvider'" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "PASS [3/5]: DmlExecutionProvider is first" -ForegroundColor Green
} else {
    Write-Host "FAIL [3/5]: DmlExecutionProvider not first" -ForegroundColor Red
    Write-Host "      pip install --force-reinstall --no-deps onnxruntime-directml==1.24.4 (install LAST)." -ForegroundColor DarkGray
    $ok = $false
}

# --- 4. Weights spot-check --------------------------------------------------------
$mineruJson = Join-Path $HOME "mineru.json"
$weightsDir = $null
if (Test-Path $mineruJson) {
    try { $weightsDir = (Get-Content -LiteralPath $mineruJson -Raw | ConvertFrom-Json).'models-dir'.pipeline } catch { }
}
$spot = @(
    "models\Layout\PP-DocLayoutV2",
    "models\MFR\unimernet_hf_small_2503",
    "models\OCR\paddleocr_torch"
)
if (-not $weightsDir -or -not (Test-Path $weightsDir)) {
    Write-Host "FAIL [4/5]: weights dir missing (mineru.json: $weightsDir)" -ForegroundColor Red
    Write-Host "      Run setup.ps1 (downloads via mineru-models-download -s huggingface -m pipeline)." -ForegroundColor DarkGray
    $ok = $false
} else {
    $missing = @($spot | Where-Object { -not (Test-Path (Join-Path $weightsDir $_)) })
    if ($missing.Count -gt 0) {
        Write-Host "FAIL [4/5]: weights incomplete under $weightsDir -- missing: $($missing -join ', ')" -ForegroundColor Red
        Write-Host "      Re-run setup.ps1 to re-download." -ForegroundColor DarkGray
        $ok = $false
    } else {
        Write-Host "PASS [4/5]: weights present at $weightsDir" -ForegroundColor Green
    }
}

# --- 5. Smoke inference -----------------------------------------------------------
$imagesDir = Join-Path $repoRoot "eval-infra\01-omnidocbench\data\images"
# Ordinal (byte-order) sort: matches "alphabetical first" regardless of
# console culture, and avoids culture-sorted CJK/bracket names for the smoke.
$names = @((Get-ChildItem -LiteralPath $imagesDir -Filter *.png).Name)
[Array]::Sort($names, [StringComparer]::Ordinal)
if ($names.Count -eq 0) {
    Write-Host "FAIL [5/5]: no dataset images under $imagesDir -- run eval-infra\01-omnidocbench\setup.ps1." -ForegroundColor Red
    $ok = $false
} else {
    $firstName = $names[0]
    $tmpIn  = Join-Path $env:TEMP "mineru-verify-in"
    $tmpOut = Join-Path $env:TEMP "mineru-verify-out"
    foreach ($d in @($tmpIn, $tmpOut)) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d }
        New-Item -ItemType Directory -Path $d | Out-Null
    }
    Copy-Item -LiteralPath (Join-Path $imagesDir $firstName) $tmpIn
    Write-Host "[5/5] smoke: $firstName through adapter (GPU warmup may take 1-3 min)..." -ForegroundColor Cyan
    $env:PYTHONUTF8 = "1"
    & $py (Join-Path $adapterRoot "run_adapter.py") --backend pipeline --platform windows-hip `
        --img-dir $tmpIn --out-dir $tmpOut
    $md = Join-Path $tmpOut ([IO.Path]::GetFileNameWithoutExtension($firstName) + ".md")
    if ($LASTEXITCODE -eq 0 -and (Test-Path $md) -and (Get-Item $md).Length -gt 100) {
        Write-Host "PASS [5/5]: smoke produced $md ($((Get-Item $md).Length) bytes)" -ForegroundColor Green
    } else {
        Write-Host "FAIL [5/5]: smoke inference failed (exit=$LASTEXITCODE, md exists: $(Test-Path $md))" -ForegroundColor Red
        Write-Host "      Check GPU/server logs; see docs/pitfalls.md." -ForegroundColor DarkGray
        $ok = $false
    }
    Remove-Item -Recurse -Force $tmpIn, $tmpOut -ErrorAction SilentlyContinue
}

if ($ok) {
    Write-Host "VERIFY OK: MinerU adapter environment ready." -ForegroundColor Green
    exit 0
} else {
    Write-Host "VERIFY FAILED -- fix the FAIL items above, then re-run." -ForegroundColor Red
    exit 1
}
