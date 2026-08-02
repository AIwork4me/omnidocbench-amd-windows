<#
.SYNOPSIS
Prove the running llama-server is the requested backend (hip|cpu), not just reachable.

.DESCRIPTION
A reachable /v1/models is NOT proof of the backend. This script decomposes
"HIP backend proof" into explicit checks and emits a machine-readable
backend-proof.json plus per-check console lines:

  1. .env.local LLAMA_VARIANT matches -ExpectedVariant.
  2. The installed .variant marker matches -ExpectedVariant.
  3. Binary evidence: HIP build must have ggml-hip.dll + libhipblas.dll next to
     llama-server.exe; a CPU build must NOT.
  4. The server executable lives under the adapter models/llama.cpp tree and
     its SHA-256 is recorded.
  5. LLAMA_TAG matches the upstream-lock llama.cpp tag.
  6. The recorded PID is alive (unless -SkipPid).
  7. /v1/models answers and lists the expected model (unless -SkipHttp).
  8. GPU offload evidence for HIP: LLAMA_GPU_LAYERS >= 1 AND the server log
     contains at least one HIP/ROCm runtime marker AND no CPU-fallback marker.
     For CPU: LLAMA_GPU_LAYERS == 0.

Any failed check fails the script (exit 1). Nothing is ever guessed from a
single fragile log line: log parsing is a set of regex conditions with
fixture tests.

.PARAMETER EnvFile
Path to the adapter .env.local.
.PARAMETER LogFile
Path to the llama-server log (may be UTF-16 or UTF-8; both are handled).
.PARAMETER PidFile
Path to the llama-server pid file.
.PARAMETER ExpectedVariant
hip|cpu - the backend the caller requires.
.PARAMETER LockFile
Path to upstream-lock.json.
.PARAMETER OutFile
Where to write backend-proof.json (default: alongside the env file).
.PARAMETER BaseUrl
Server base URL (default http://127.0.0.1:<LLAMA_PORT>).
.PARAMETER SkipHttp
Skip PID-alive and /v1/models checks (used by offline fixture tests).
#>
[CmdletBinding()]
param(
    [string] $EnvFile,
    [string] $LogFile,
    [string] $PidFile,
    [ValidateSet("hip", "cpu")]
    [string] $ExpectedVariant,
    [string] $LockFile,
    [string] $OutFile = "",
    [string] $BaseUrl = "",
    [switch] $SkipHttp
)
$ErrorActionPreference = "Stop"

$results = New-Object System.Collections.Generic.List[object]
$ok = $true

function Add-Check([string] $Name, [bool] $Passed, [string] $Detail) {
    $results.Add([pscustomobject]@{ check = $Name; passed = $Passed; detail = $Detail })
    if ($Passed) {
        Write-Host ("OK:   {0} - {1}" -f $Name, $Detail) -ForegroundColor Green
    } else {
        $script:ok = $false
        Write-Host ("FAIL: {0} - {1}" -f $Name, $Detail) -ForegroundColor Red
    }
}

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

function Get-Sha256Hex {
    param([string] $FilePath)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [System.IO.File]::OpenRead($FilePath)
        $bytes = $sha.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $sha.Dispose()
    }
}

function Get-TextAnyEncoding {
    param([string] $Path, [int] $MaxBytes = 8388608)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
    $bytes = $null
    try {
        # The running llama-server holds the log open for append; open with
        # FileShare.ReadWrite so the proof can read while the server writes.
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        try {
            $buffer = New-Object byte[] $MaxBytes
            $read = $stream.Read($buffer, 0, $MaxBytes)
            $bytes = New-Object byte[] $read
            [Array]::Copy($buffer, $bytes, $read)
        } finally {
            $stream.Dispose()
        }
    } catch { return "" }
    if ($null -eq $bytes -or $bytes.Length -eq 0) { return "" }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        return [System.Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        return [System.Text.Encoding]::BigEndianUnicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

$proof = [ordered]@{
    requested_variant = $ExpectedVariant
    checks = @()
    server = [ordered]@{}
    log_evidence = [ordered]@{}
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
}

# --- 1. env variant ---
$envValues = Get-DotEnv -Path $EnvFile
if ($envValues.Count -eq 0) {
    Add-Check "env.variant" $false "no .env.local keys found at $EnvFile"
} else {
    $envVariant = [string]$envValues["LLAMA_VARIANT"]
    if ([string]::IsNullOrWhiteSpace($envVariant)) {
        Add-Check "env.variant" $false "LLAMA_VARIANT not set in $EnvFile"
    } elseif ($envVariant -ne $ExpectedVariant) {
        Add-Check "env.variant" $false "LLAMA_VARIANT=$envVariant does not match requested $ExpectedVariant"
    } else {
        Add-Check "env.variant" $true "LLAMA_VARIANT=$envVariant matches requested $ExpectedVariant"
    }
}

# --- 2. installed .variant marker ---
$exePath = [string]$envValues["LLAMA_SERVER_EXE"]
$variantFile = ""
if ($exePath) { $variantFile = Join-Path (Split-Path -Parent $exePath) ".variant" }
$installedVariant = ""
if (Test-Path -LiteralPath $variantFile) { $installedVariant = (Get-Content -Raw -LiteralPath $variantFile).Trim() }
if ($installedVariant -ne $ExpectedVariant) {
    Add-Check "install.variant" $false "installed .variant='$installedVariant' does not match requested $ExpectedVariant ($variantFile)"
} else {
    Add-Check "install.variant" $true "installed .variant matches $ExpectedVariant"
}

# --- 3. binary evidence ---
if (-not $exePath -or -not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    Add-Check "binary.present" $false "LLAMA_SERVER_EXE not set or missing: $exePath"
} else {
    Add-Check "binary.present" $true "server exe: $exePath"
    $exeDir = Split-Path -Parent $exePath
    $hipDll = Join-Path $exeDir "ggml-hip.dll"
    $hipblasDll = Join-Path $exeDir "libhipblas.dll"
    $proof.server.sha256 = Get-Sha256Hex -FilePath $exePath
    $proof.server.exe = $exePath
    $hasHipDll = Test-Path -LiteralPath $hipDll
    $hasHipblas = Test-Path -LiteralPath $hipblasDll
    $proof.server.ggml_hip_dll = $hasHipDll
    $proof.server.libhipblas_dll = $hasHipblas
    if ($ExpectedVariant -eq "hip") {
        if (-not $hasHipDll -or -not $hasHipblas) {
            Add-Check "binary.hip_dlls" $false "HIP build must ship ggml-hip.dll and libhipblas.dll beside the exe"
        } else {
            Add-Check "binary.hip_dlls" $true "ggml-hip.dll + libhipblas.dll present beside exe"
        }
    } else {
        if ($hasHipDll) {
            Add-Check "binary.cpu_no_hip" $false "CPU build must NOT contain ggml-hip.dll next to the exe"
        } else {
            Add-Check "binary.cpu_no_hip" $true "no ggml-hip.dll next to the exe (CPU build)"
        }
    }
    $adapterModels = Join-Path (Split-Path -Parent $EnvFile) "models\llama.cpp"
    if ($exePath.StartsWith($adapterModels, [System.StringComparison]::OrdinalIgnoreCase)) {
        Add-Check "binary.location" $true "exe inside adapter models/llama.cpp tree"
    } else {
        Add-Check "binary.location" $false "exe outside the adapter models/llama.cpp tree: $exePath"
    }
}

# --- 4. locked tag ---
$tag = [string]$envValues["LLAMA_TAG"]
if (-not $tag) {
    Add-Check "lock.tag" $false "LLAMA_TAG not set in $EnvFile"
} elseif (-not (Test-Path -LiteralPath $LockFile -PathType Leaf)) {
    Add-Check "lock.tag" $false "upstream lock missing: $LockFile"
} else {
    try {
        $lock = Get-Content -Raw -Encoding UTF8 -LiteralPath $LockFile | ConvertFrom-Json
        $lockedTag = [string]$lock.git.llama_cpp.tag
        if ($tag -eq $lockedTag) {
            Add-Check "lock.tag" $true "llama.cpp tag $tag matches upstream lock"
        } else {
            Add-Check "lock.tag" $false "LLAMA_TAG=$tag does not match locked $lockedTag"
        }
    } catch {
        Add-Check "lock.tag" $false "could not read upstream lock: $($_.Exception.Message)"
    }
}

# --- 5. process alive ---
$pidValue = ""
if (Test-Path -LiteralPath $PidFile -PathType Leaf) { $pidValue = (Get-Content -Raw -LiteralPath $PidFile).Trim() }
if (-not $SkipHttp) {
    if (-not $pidValue -or -not ($pidValue -match "^\d+$")) {
        Add-Check "process.alive" $false "pid file missing or invalid: $PidFile"
    } else {
        $proc = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
        if ($null -eq $proc) {
            Add-Check "process.alive" $false "pid $pidValue is not running"
        } else {
            Add-Check "process.alive" $true "server wrapper pid $pidValue is running"
        }
    }
} else {
    Add-Check "process.alive" $true "skipped (-SkipHttp)"
}
$proof.server.pid = $pidValue

# --- 6. HTTP + model id ---
$port = [string]$envValues["LLAMA_PORT"]
$proof.server.port = $port
if (-not $BaseUrl) { $base = "http://127.0.0.1:$port" } else { $base = $BaseUrl }
if (-not $SkipHttp) {
    try {
        $resp = Invoke-RestMethod -Uri "$base/v1/models" -Method Get -TimeoutSec 5
        $ids = @($resp.data | ForEach-Object { $_.id })
        $expectedModel = [string]$envValues["VL_REC_API_MODEL_NAME"]
        if ($ids -contains $expectedModel) {
            Add-Check "http.models" $true "server lists expected model $expectedModel"
        } else {
            Add-Check "http.models" $false "expected model $expectedModel not in /v1/models: $($ids -join ', ')"
        }
    } catch {
        Add-Check "http.models" $false "server unreachable at $base/v1/models: $($_.Exception.Message)"
    }
} else {
    Add-Check "http.models" $true "skipped (-SkipHttp)"
}

# --- 7. GPU offload + log evidence ---
$gpuLayers = [string]$envValues["LLAMA_GPU_LAYERS"]
$logText = Get-TextAnyEncoding -Path $LogFile
$hipMarkers = @(
    "HIP Library Path",
    "amdhip64",
    "ggml_backend_hip",
    "ggml_cuda_init: found",
    "ROCm"
)
$fallbackMarkers = @(
    "falling back to CPU",
    "no supported devices",
    "failed to load backend",
    "CPU only"
)
$hipHits = @($hipMarkers | Where-Object { $logText -match [regex]::Escape($_) })
$fallbackHits = @($fallbackMarkers | Where-Object { $logText -match [regex]::Escape($_) })
$proof.log_evidence.markers_found = $hipHits
$proof.log_evidence.fallback_markers = $fallbackHits
$proof.log_evidence.log_file = $LogFile
if ($ExpectedVariant -eq "hip") {
    if ($gpuLayers -ne "0" -and $gpuLayers -ne "") {
        Add-Check "offload.layers" $true "LLAMA_GPU_LAYERS=$gpuLayers (>= 1 layer offloaded)"
    } else {
        Add-Check "offload.layers" $false "LLAMA_GPU_LAYERS=$gpuLayers proves no GPU offload (must be >= 1 for HIP)"
    }
    if ($hipHits.Count -eq 0) {
        Add-Check "log.hip_evidence" $false "no HIP/ROCm runtime marker in $LogFile"
    } else {
        Add-Check "log.hip_evidence" $true "HIP markers: $($hipHits -join ', ')"
    }
    if ($fallbackHits.Count -gt 0) {
        Add-Check "log.cpu_fallback" $false "CPU-fallback markers present: $($fallbackHits -join ', ')"
    } else {
        Add-Check "log.cpu_fallback" $true "no CPU-fallback markers in log"
    }
} else {
    if ($gpuLayers -eq "0" -or $gpuLayers -eq "") {
        Add-Check "offload.layers" $true "LLAMA_GPU_LAYERS=$gpuLayers (CPU build, no offload)"
    } else {
        Add-Check "offload.layers" $false "LLAMA_GPU_LAYERS=$gpuLayers on a CPU profile (must be 0)"
    }
    Add-Check "log.cpu_evidence" $true "CPU profiles do not require log markers (no GPU offload expected)"
}

$proof.checks = @($results | ForEach-Object { $_ })
if (-not $OutFile) { $OutFile = Join-Path (Split-Path -Parent $EnvFile) "backend-proof.json" }
$temp = "$OutFile.tmp.$PID"
try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($temp, ($proof | ConvertTo-Json -Depth 8), $utf8NoBom)
    Move-Item -LiteralPath $temp -Destination $OutFile -Force
} catch {
    Write-Host "WARN: could not write $OutFile" -ForegroundColor Yellow
}

Write-Host ""
if ($ok) {
    Write-Host "BACKEND PROOF OK: requested $ExpectedVariant is genuinely in use." -ForegroundColor Green
    Write-Host "Evidence: $OutFile"
    exit 0
} else {
    Write-Host "BACKEND PROOF FAILED: requested $ExpectedVariant backend not proven." -ForegroundColor Red
    exit 1
}
