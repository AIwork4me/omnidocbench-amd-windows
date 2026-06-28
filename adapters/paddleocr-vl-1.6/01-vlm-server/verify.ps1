<#
.SYNOPSIS
Health check for the PaddleOCR-VL-1.6 llama-server.

.DESCRIPTION
Verifies the VLM server provisioned by setup.ps1 is reachable and serving the
PaddleOCR-VL-1.6-GGUF model. Checks:

  - .env.local exists with PADDLEOCR_VL_GGUF / LLAMA_SERVER_EXE set.
  - The referenced GGUF and llama-server.exe exist on disk.
  - llama-server answers GET /v1/models at the configured host:port.
  - The expected model id (VL_REC_API_MODEL_NAME) is listed.

Exit 0 = OK, 1 = FAIL. Suitable for chaining in full-verify.ps1 (Task 7).
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
        if ($t -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
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

if (-not (Test-Path $envFile)) {
    Write-Host "FAIL: $envFile missing -- run setup.ps1 first." -ForegroundColor Red
    exit 1
}
$env = Get-DotEnv $envFile

# --- artifacts referenced by .env.local ---
$serverExe = $env["LLAMA_SERVER_EXE"]
$mainGguf  = $env["PADDLEOCR_VL_GGUF"]
$mmproj    = $env["PADDLEOCR_VL_MMPROJ"]
$expectedModel = $env["VL_REC_API_MODEL_NAME"]

foreach ($pair in @(
    @("LLAMA_SERVER_EXE",   $serverExe),
    @("PADDLEOCR_VL_GGUF",  $mainGguf)
)) {
    $key, $val = $pair
    if ([string]::IsNullOrWhiteSpace($val)) {
        Write-Host "FAIL: $key not set in $envFile." -ForegroundColor Red
        $ok = $false
    } elseif (-not (Test-Path $val)) {
        Write-Host "FAIL: $key path not found: $val" -ForegroundColor Red
        $ok = $false
    } else {
        Write-Host "OK: $key present ($val)" -ForegroundColor Green
    }
}
if (-not [string]::IsNullOrWhiteSpace($mmproj) -and -not (Test-Path $mmproj)) {
    Write-Host "WARN: PADDLEOCR_VL_MMPROJ set but missing: $mmproj" -ForegroundColor Yellow
}

# --- reachability ---
$host_  = if ($env["LLAMA_HOST"]) { $env["LLAMA_HOST"] } else { "127.0.0.1" }
$port   = if ($env["LLAMA_PORT"]) { $env["LLAMA_PORT"] } else { "8111" }
$base   = "http://${host_}:$port"

Write-Host "Checking llama-server at $base/v1/models ..." -ForegroundColor Cyan
try {
    $resp = Invoke-RestMethod -Uri "$base/v1/models" -Method Get -TimeoutSec 5
} catch {
    Write-Host "FAIL: llama-server unreachable at $base -- $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "      Run setup.ps1 to start it." -ForegroundColor DarkGray
    exit 1
}

Write-Host "OK: /v1/models reachable." -ForegroundColor Green
$ids = $resp.data | ForEach-Object { $_.id }
Write-Host "Available models:"
$ids | ForEach-Object { Write-Host "  - $_" }

if ($expectedModel) {
    if ($ids -contains $expectedModel) {
        Write-Host "OK: expected model id present ($expectedModel)" -ForegroundColor Green
    } else {
        Write-Host "WARN: VL_REC_API_MODEL_NAME='$expectedModel' not in /v1/models list." -ForegroundColor Yellow
        Write-Host "      run_adapter.py will fail unless --api-model-name matches a served id." -ForegroundColor DarkGray
    }
}

if ($ok) {
    Write-Host "VERIFY OK: PaddleOCR-VL-1.6 VLM server is healthy." -ForegroundColor Green
    exit 0
} else {
    Write-Host "VERIFY FAILED: see messages above." -ForegroundColor Red
    exit 1
}
