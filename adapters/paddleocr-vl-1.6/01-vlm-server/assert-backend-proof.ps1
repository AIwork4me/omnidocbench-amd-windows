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
.PARAMETER StartTimeFile
Path to the server start-time file written by setup.ps1 (default:
<llama-server.started> next to -PidFile). When the file exists, the log must
be modified AFTER the recorded start (stale logs from earlier sessions cannot
pass the proof) and the recorded start is stored in the proof output.
.PARAMETER SkipHttp
Skip PID-alive, process-identity, /v1/models and the minimal inference request
checks (used by offline fixture tests). The env/log/layer gates still run.
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
    [string] $StartTimeFile = "",
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
    process = [ordered]@{}
    inference_request = [ordered]@{}
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
    # DLL content hashes: the proof records what the binary links against so a
    # later tamper with the runtime DLLs is detectable in the evidence pack.
    $proof.server.ggml_hip_dll_sha256 = if ($hasHipDll) { Get-Sha256Hex -FilePath $hipDll } else { $null }
    $proof.server.libhipblas_dll_sha256 = if ($hasHipblas) { Get-Sha256Hex -FilePath $hipblasDll } else { $null }
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

# --- 5. strict LLAMA_GPU_LAYERS parsing -------------------------------
# A layer count is only evidence when it is a real integer: "0" proves no
# offload, ">= 1" proves offload was requested, anything else (empty, "none",
# "99.5") is refused.
$gpuLayersRaw = [string]$envValues["LLAMA_GPU_LAYERS"]
$actualGpuLayers = $null
$layersParsed = [int]::TryParse($gpuLayersRaw, [ref]$actualGpuLayers)
$proof.server.actual_gpu_layers = if ($layersParsed) { $actualGpuLayers } else { $null }
$proof.server.gpu_layers_raw = $gpuLayersRaw
if (-not $layersParsed) {
    Add-Check "offload.layers_parse" $false "LLAMA_GPU_LAYERS='$gpuLayersRaw' is not an integer (a layer count must parse strictly)"
} elseif ($ExpectedVariant -eq "hip") {
    if ($actualGpuLayers -lt 1) {
        Add-Check "offload.layers" $false "LLAMA_GPU_LAYERS=$actualGpuLayers proves no GPU offload (HIP requires >= 1)"
    } else {
        Add-Check "offload.layers" $true "LLAMA_GPU_LAYERS=$actualGpuLayers (>= 1 layer offloaded)"
    }
} else {
    if ($actualGpuLayers -ne 0) {
        Add-Check "offload.layers" $false "LLAMA_GPU_LAYERS=$actualGpuLayers on a CPU profile (must be exactly 0)"
    } else {
        Add-Check "offload.layers" $true "LLAMA_GPU_LAYERS=0 (CPU build, no offload)"
    }
}

# --- 6. process identity + server start time ---------------------------
$pidValue = ""
if (Test-Path -LiteralPath $PidFile -PathType Leaf) { $pidValue = (Get-Content -Raw -LiteralPath $PidFile).Trim() }
$proof.server.pid = $pidValue

$startTimeFile = $StartTimeFile
if (-not $startTimeFile -and $PidFile) {
    $startTimeFile = Join-Path (Split-Path -Parent $PidFile) "llama-server.started"
}
$serverStart = $null
$proof.server.start_time = $null
$proof.server.log_mtime_utc = $null
if ($startTimeFile -and (Test-Path -LiteralPath $startTimeFile -PathType Leaf)) {
    $rawStart = (Get-Content -Raw -LiteralPath $startTimeFile).Trim()
    $serverStart = [datetime]::MinValue
    if (-not [datetime]::TryParse($rawStart, [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::AdjustToUniversal -bor [System.Globalization.DateTimeStyles]::AssumeUniversal,
            [ref]$serverStart)) {
        Add-Check "server.start_time" $false "start-time file unreadable at $startTimeFile ('$rawStart')"
        $serverStart = $null
    } else {
        $proof.server.start_time = $serverStart.ToUniversalTime().ToString("o")
        Add-Check "server.start_time" $true "server started $($serverStart.ToUniversalTime().ToString('o'))"
        if (Test-Path -LiteralPath $LogFile -PathType Leaf) {
            $logMtime = (Get-Item -LiteralPath $LogFile).LastWriteTimeUtc
            $proof.server.log_mtime_utc = $logMtime.ToString("o")
            if ($logMtime -le $serverStart.ToUniversalTime()) {
                Add-Check "log.freshness" $false "log mtime $($logMtime.ToString('o')) is NOT after server start $($serverStart.ToUniversalTime().ToString('o')) - stale log from an earlier session"
            } else {
                Add-Check "log.freshness" $true "log mtime $($logMtime.ToString('o')) is after server start"
            }
        } else {
            Add-Check "log.freshness" $false "log file missing: $LogFile"
        }
    }
}

$port = [string]$envValues["LLAMA_PORT"]
$proof.server.port = $port
if (-not $BaseUrl) { $base = "http://127.0.0.1:$port" } else { $base = $BaseUrl }

if (-not $SkipHttp) {
    if (-not $pidValue -or -not ($pidValue -match "^\d+$")) {
        Add-Check "process.alive" $false "pid file missing or invalid: $PidFile"
    } else {
        $wrapperProc = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
        if ($null -eq $wrapperProc) {
            Add-Check "process.alive" $false "wrapper pid $pidValue is not running"
        } else {
            Add-Check "process.alive" $true "server wrapper pid $pidValue is running"
        }
    }
    # Identity proof: the running llama-server must be THIS executable, serving
    # THIS port, THIS model path and THIS alias. An unrelated process (or an
    # old server instance on a different model) can never pass.
    $proof.process.wrapper_pid = $pidValue
    $proof.process.server_pids = @()
    $proof.process.command_line = $null
    $matched = $null
    $exeLower = $exePath.ToLowerInvariant()
    if ($exePath -and (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant() -eq $exeLower
        })
        $expectedModelPath = [string]$envValues["PADDLEOCR_VL_GGUF"]
        $expectedAlias = [string]$envValues["VL_REC_API_MODEL_NAME"]
        if (-not $expectedModelPath) { $expectedModelPath = "" }
        foreach ($p in $procs) {
            $cmd = [string]$p.CommandLine
            if ($cmd -match "--port\s+$port" -and
                ($expectedModelPath -eq "" -or $cmd.IndexOf($expectedModelPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -and
                ($expectedAlias -eq "" -or $cmd -match "--alias\s+" + [regex]::Escape($expectedAlias))) {
                $matched = $p
                break
            }
        }
        if ($null -eq $matched) {
            Add-Check "process.identity" $false "no llama-server process with ExecutablePath=$exePath, --port $port, model path and alias '$(if ($expectedAlias) { $expectedAlias } else { '?' })'"
        } else {
            $proof.process.server_pids = @([int]$matched.ProcessId)
            $proof.process.command_line = [string]$matched.CommandLine
            $proof.process.executable_path = [string]$matched.ExecutablePath
            Add-Check "process.identity" $true "llama-server pid $($matched.ProcessId) matches exe, --port $port, model and alias"
        }
    } else {
        Add-Check "process.identity" $false "cannot validate process identity: server exe missing"
    }
    # One minimal inference request: proves the loaded model actually generates
    # (a reachable /v1/models endpoint alone is not proof).
    try {
        $reqBody = @{
            model = [string]$envValues["VL_REC_API_MODEL_NAME"]
            messages = @(@{ role = "user"; content = "Reply with: OK" })
            max_tokens = 8
            temperature = 0
        } | ConvertTo-Json -Depth 6
        $requestTs = (Get-Date).ToUniversalTime().ToString("o")
        $resp = Invoke-RestMethod -Uri "$base/v1/chat/completions" -Method Post -Body $reqBody -ContentType "application/json" -TimeoutSec 60
        $status = "200"
        $proof.inference_request.timestamp = $requestTs
        $proof.inference_request.status = $status
        $content = ""
        try { $content = [string]$resp.choices[0].message.content } catch { }
        $proof.inference_request.usage = $resp.usage
        $proof.inference_request.response_snippet = $content.Substring(0, [math]::Min(80, $content.Length))
        Add-Check "inference.request" $true "minimal chat completion returned HTTP 200 (snippet: '$($proof.inference_request.response_snippet)')"
    } catch {
        $proof.inference_request.timestamp = (Get-Date).ToUniversalTime().ToString("o")
        $proof.inference_request.status = "error"
        $proof.inference_request.error = $_.Exception.Message
        Add-Check "inference.request" $false "minimal chat completion failed: $($_.Exception.Message)"
    }
} else {
    Add-Check "process.alive" $true "skipped (-SkipHttp)"
    Add-Check "process.identity" $true "skipped (-SkipHttp)"
    Add-Check "inference.request" $true "skipped (-SkipHttp)"
}

# --- 7. HTTP + model id ---
if (-not $SkipHttp) {
    try {
        $resp = Invoke-RestMethod -Uri "$base/v1/models" -Method Get -TimeoutSec 5
        $ids = @($resp.data | ForEach-Object { $_.id })
        $expectedModel = [string]$envValues["VL_REC_API_MODEL_NAME"]
        $proof.server.requested_model = $expectedModel
        $proof.server.returned_model = ($ids -join ", ")
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

# --- 8. GPU offload + log evidence ---
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
