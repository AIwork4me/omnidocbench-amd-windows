<#
.SYNOPSIS
Health check for the PP-DocLayoutV3 ONNX layout model.

.DESCRIPTION
Verifies the layout-detection model provisioned by setup.ps1 is on disk and
referenced correctly. Checks:

  - adapters/paddleocr-vl-1.6/.env.local exists with PP_DOCLAYOUTV3_ONNX_DIR set.
  - The referenced directory exists.
  - inference.onnx (~16 MB weights) and inference.yml (config) are both present
    and non-empty.

This is the verify pitfalls.md#layout points at: "The adapter's verify.ps1
passes." If it fails, re-run setup.ps1 to re-download the model.

Exit 0 = OK, 1 = FAIL. Suitable for chaining in full-verify.ps1 (Task 7) and
for a pre-flight check before running run_adapter.py.
#>
$ErrorActionPreference = "Stop"

$adapterRoot = Split-Path -Parent $PSScriptRoot
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

# --- .env.local present + key set ---
if (-not (Test-Path $envFile)) {
    Write-Host "FAIL: $envFile missing -- run setup.ps1 first." -ForegroundColor Red
    exit 1
}
$env = Get-DotEnv $envFile
$modelDir = $env["PP_DOCLAYOUTV3_ONNX_DIR"]

if ([string]::IsNullOrWhiteSpace($modelDir)) {
    Write-Host "FAIL: PP_DOCLAYOUTV3_ONNX_DIR not set in $envFile." -ForegroundColor Red
    Write-Host "      Run 02-layout-model\setup.ps1 to download the model + write the path." -ForegroundColor DarkGray
    exit 1
}

# --- directory exists ---
if (-not (Test-Path $modelDir)) {
    Write-Host "FAIL: PP_DOCLAYOUTV3_ONNX_DIR path not found: $modelDir" -ForegroundColor Red
    Write-Host "      Re-run 02-layout-model\setup.ps1 (the dir may have been moved/deleted)." -ForegroundColor DarkGray
    exit 1
}

# --- required model files present + non-empty ---
$required = @("inference.onnx", "inference.yml")
foreach ($name in $required) {
    $f = Join-Path $modelDir $name
    if (-not (Test-Path $f)) {
        Write-Host "FAIL: $name missing in $modelDir" -ForegroundColor Red
        $ok = $false
    } else {
        $len = (Get-Item $f).Length
        if ($len -lt 100) {
            Write-Host "FAIL: $name is only $len bytes (truncated/corrupt) in $modelDir" -ForegroundColor Red
            $ok = $false
        } else {
            $sizeStr = if ($name -eq "inference.onnx") {
                "$([math]::Round($len / 1MB, 1)) MB"
            } else {
                "$len B"
            }
            Write-Host "OK: $name present ($sizeStr)" -ForegroundColor Green
        }
    }
}

if ($ok) {
    Write-Host "VERIFY OK: PP-DocLayoutV3 ONNX layout model is present." -ForegroundColor Green
    exit 0
} else {
    Write-Host "VERIFY FAILED: model dir incomplete -- re-run 02-layout-model\setup.ps1." -ForegroundColor Red
    Write-Host "  (see docs/pitfalls.md#layout)" -ForegroundColor DarkGray
    exit 1
}
