<#
.SYNOPSIS
Provision + start the PaddleOCR-VL-1.6 VLM server (llama.cpp / llama-server).

.DESCRIPTION
This is the VLM half of the PaddleOCR-VL-1.6 reference adapter. It performs
three idempotent phases and leaves llama-server running in the background:

  Phase 1 -- Download llama.cpp
      Fetches the prebuilt Windows binary (cpu or hip/Radeon) and extracts it
      under adapters/paddleocr-vl-1.6/models/llama.cpp/. ~17 MB (cpu) or
      ~321 MB (hip).

  Phase 2 -- Download PaddleOCR-VL-1.6-GGUF weights
      Fetches PaddlePaddle/PaddleOCR-VL-1.6-GGUF via modelscope (or
      huggingface, per mirrors.env) into
      adapters/paddleocr-vl-1.6/models/PaddleOCR-VL-1.6-GGUF/. ~1.7 GB.

  Phase 3 -- Start llama-server
      Launches llama-server.exe in the background with OpenAI-compatible API,
      tuned for AMD Radeon (flash-attn on, 8 slots, temp 0 for deterministic
      output). Waits up to 5 min for /v1/models to respond, writes the wrapper
      PID to a pid file.

All machine-local paths are written to adapters/paddleocr-vl-1.6/.env.local
(gitignored). run_adapter.py reads the same file for defaults.

Re-running this script is safe: each phase skips itself if its output already
exists, and Phase 3 exits early if llama-server is already answering.

.PARAMETER Variant
llama.cpp build variant: "cpu" (default) or "hip" (AMD Radeon GPU). Use "hip"
on Radeon hardware for ~10x throughput.

.PARAMETER Tag
llama.cpp release tag. Defaults to b9637 (known-good for PaddleOCR-VL-1.6).

.PARAMETER Port
Port llama-server listens on. Default 8111 (matches run_adapter.py default).

.PARAMETER SkipDownload
Skip Phases 1-2 (use when the binaries/weights are already in place) and go
straight to starting the server.

.PARAMETER Force
Redownload + re-extract even if outputs already exist.

.EXAMPLE
  # CPU build, defaults:
  powershell -ExecutionPolicy Bypass -File setup.ps1
  # AMD Radeon (Ryzen AI / Radeon 8060S):
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Variant hip
#>
[CmdletBinding()]
param(
    [ValidateSet("cpu", "hip")]
    [string] $Variant = "cpu",
    [string] $Tag = "b9637",
    [string] $Port = "8111",
    [switch] $SkipDownload,
    [switch] $Force
)
$ErrorActionPreference = "Stop"

# adapterRoot = adapters/paddleocr-vl-1.6 ; repoRoot = repo top.
$adapterRoot = Split-Path -Parent $PSScriptRoot
$repoRoot    = Split-Path -Parent (Split-Path -Parent $adapterRoot)
$modelsDir   = Join-Path $adapterRoot "models"
$envFile     = Join-Path $adapterRoot ".env.local"
$llamaDir    = Join-Path $modelsDir "llama.cpp"
$variantFile = Join-Path $llamaDir ".variant"
$vlmModelDir = Join-Path $modelsDir "PaddleOCR-VL-1.6-GGUF"
$logDir      = Join-Path $adapterRoot "logs"
$logFile     = Join-Path $logDir "llama-server.log"
$pidFile     = Join-Path $logDir "llama-server.pid"
$host_       = "127.0.0.1"
$baseUrl     = "http://${host_}:$Port"
$lockFile    = Join-Path $repoRoot "upstream-lock.json"
$lockVerify  = Join-Path $repoRoot "scripts\verify-upstream-lock.ps1"
if (-not (Test-Path -LiteralPath $lockFile)) { throw "Upstream lock missing: $lockFile" }
$upstreamLock = Get-Content -Raw -Encoding UTF8 -LiteralPath $lockFile | ConvertFrom-Json
$lockedLlamaTag = [string]$upstreamLock.git.llama_cpp.tag
$vlmRevision = [string]$upstreamLock.huggingface.vlm.revision
if ($Tag -ne $lockedLlamaTag) { throw "llama.cpp tag '$Tag' is not locked; expected '$lockedLlamaTag' from upstream-lock.json" }

New-Item -ItemType Directory -Force -Path $modelsDir, $logDir | Out-Null

# --- helpers: read/write .env.local (KEY='VALUE' lines) ---
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
function Set-DotEnv {
    param([string]$Path, [hashtable]$Values)
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path) }
    foreach ($key in $Values.Keys) {
        $pat = [regex]::Escape($key)
        $quoted = "'" + (([string]$Values[$key]) -replace "'", "\'") + "'"
        $newLine = "$key=$quoted"
        $hit = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^\s*$pat\s*=") { $lines[$i] = $newLine; $hit = $true; break }
        }
        if (-not $hit) { $lines += $newLine }
    }
    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

# --- mirrors.env (GITHUB_BASE / HF_OR_MS) ---
$mirrorsFile = Join-Path $repoRoot "mirrors.env"
$mirrors = @{}
if (Test-Path $mirrorsFile) {
    Get-Content $mirrorsFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.*)$") { $mirrors[$matches[1]] = $matches[2] }
    }
}
$githubBase = if ($mirrors["GITHUB_BASE"]) { $mirrors["GITHUB_BASE"] } else { "https://github.com" }
$hfOrMs     = if ($mirrors["HF_OR_MS"])    { $mirrors["HF_OR_MS"] }    else { "modelscope" }
$repoId     = "PaddlePaddle/PaddleOCR-VL-1.6-GGUF"

# ===========================================================================
# Phase 1 -- download llama.cpp
# ===========================================================================
$serverExe = Get-ChildItem -Path $llamaDir -Filter "llama-server.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
$installedVariant = if (Test-Path -LiteralPath $variantFile) { (Get-Content -Raw -LiteralPath $variantFile).Trim() } else { "" }
# Repair a missing/mismatched .variant marker when the binary tree already
# exists: infer the installed build from its DLL set instead of re-downloading.
if ($serverExe -and $installedVariant -ne $Variant) {
    $inferredVariant = if (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $serverExe.FullName) "ggml-hip.dll")) { "hip" } else { "cpu" }
    if ($inferredVariant -eq $Variant) {
        Set-Content -LiteralPath $variantFile -Value $Variant -Encoding ASCII
        $installedVariant = $Variant
        Write-Host "[1/3] Repaired .variant marker (installed binary is $Variant)." -ForegroundColor Green
    }
}
if ($SkipDownload) {
    Write-Host "[1/3] Skipping llama.cpp download (-SkipDownload)." -ForegroundColor Yellow
} elseif ($serverExe -and $installedVariant -eq $Variant -and -not $Force) {
    Write-Host "[1/3] llama-server.exe already present: $($serverExe.FullName)" -ForegroundColor Green
} else {
    if ($serverExe -and $installedVariant -ne $Variant) {
        Write-Host "[1/3] llama.cpp variant mismatch (installed='$installedVariant', requested='$Variant'); replacing binary." -ForegroundColor Yellow
    }
    $assetName = switch ($Variant) {
        "cpu" { "llama-$Tag-bin-win-cpu-x64.zip" }
        "hip" { "llama-$Tag-bin-win-hip-radeon-x64.zip" }
    }
    $url = "$githubBase/ggml-org/llama.cpp/releases/download/$Tag/$assetName"
    $zip = Join-Path $env:TEMP $assetName
    Write-Host "[1/3] Downloading llama.cpp $Variant ($Tag) from $url" -ForegroundColor Cyan
    if (-not (Test-Path $zip) -or $Force) {
        try {
            Import-Module BitsTransfer -ErrorAction Stop
            Start-BitsTransfer -Source $url -Destination $zip -DisplayName "llama.cpp download"
        } catch {
            Write-Host "BITS unavailable, using Invoke-WebRequest..." -ForegroundColor Yellow
            $ProgressPreference = "SilentlyContinue"
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        }
    }
    if (-not (Test-Path $zip)) { throw "Download failed: $url" }
    $llamaComponent = if ($Variant -eq "hip") { "LlamaHipZip" } else { "LlamaCpuZip" }
    & powershell -ExecutionPolicy Bypass -File $lockVerify -Component $llamaComponent -Path $zip
    if ($LASTEXITCODE -ne 0) { throw "Downloaded llama.cpp archive does not match upstream-lock.json" }
    Write-Host "      Downloaded $([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB" -ForegroundColor Green
    if (Test-Path $llamaDir) { Remove-Item $llamaDir -Recurse -Force }
    New-Item -ItemType Directory -Path $llamaDir -Force | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $llamaDir -Force
    Set-Content -LiteralPath $variantFile -Value $Variant -Encoding ASCII
    Write-Host "      Extracted to $llamaDir" -ForegroundColor Green
    $serverExe = Get-ChildItem -Path $llamaDir -Filter "llama-server.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $serverExe) { throw "llama-server.exe not found after extraction in $llamaDir" }
}

# ===========================================================================
# Phase 2 -- download PaddleOCR-VL-1.6-GGUF weights
# ===========================================================================
$envLocal = Get-DotEnv $envFile
$mainGguf = $envLocal["PADDLEOCR_VL_GGUF"]
$lockedMainGguf = Join-Path $vlmModelDir "PaddleOCR-VL-1.6-GGUF.gguf"
$lockedMmproj = Join-Path $vlmModelDir "PaddleOCR-VL-1.6-GGUF-mmproj.gguf"
if ((-not $mainGguf -or -not (Test-Path -LiteralPath $mainGguf)) -and
    (Test-Path -LiteralPath $lockedMainGguf) -and (Test-Path -LiteralPath $lockedMmproj)) {
    & powershell -ExecutionPolicy Bypass -File $lockVerify -Component Vlm -Path $vlmModelDir
    if ($LASTEXITCODE -ne 0) { throw "Seeded VLM model does not match upstream-lock.json" }
    $mainGguf = $lockedMainGguf
    Set-DotEnv -Path $envFile -Values @{
        PADDLEOCR_VL_GGUF = $lockedMainGguf
        PADDLEOCR_VL_MMPROJ = $lockedMmproj
        VL_REC_API_MODEL_NAME = (Split-Path $lockedMainGguf -Leaf)
    }
    Write-Host "[2/3] Adopted lock-verified seeded GGUF files and rebuilt .env.local." -ForegroundColor Green
}
if ($SkipDownload) {
    Write-Host "[2/3] Skipping weights download (-SkipDownload)." -ForegroundColor Yellow
} elseif ($mainGguf -and (Test-Path $mainGguf) -and -not $Force) {
    & powershell -ExecutionPolicy Bypass -File $lockVerify -Component Vlm -Path $vlmModelDir
    if ($LASTEXITCODE -ne 0) { throw "Existing VLM model does not match upstream-lock.json" }
    Write-Host "[2/3] PaddleOCR-VL-1.6-GGUF already present: $mainGguf" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Force -Path $vlmModelDir | Out-Null
    Write-Host "[2/3] Downloading $repoId via $hfOrMs (~1.7 GB)..." -ForegroundColor Cyan
    Write-Host "      Destination: $vlmModelDir"
    if ($hfOrMs -eq "huggingface") {
        $hfCli = Join-Path $repoRoot ".venv\Scripts\hf.exe"
        if (-not (Test-Path -LiteralPath $hfCli)) {
            $legacyHfCli = Join-Path $repoRoot ".venv\Scripts\huggingface-cli.exe"
            if (Test-Path -LiteralPath $legacyHfCli) { $hfCli = $legacyHfCli }
        }
        if (-not (Test-Path -LiteralPath $hfCli)) {
            throw "Hugging Face CLI missing from the locked environment. Run 'uv sync --locked --all-groups' and retry."
        }
        $previousDisableXet = $env:HF_HUB_DISABLE_XET
        try {
            $env:HF_HUB_DISABLE_XET = "1"
            & $hfCli download $repoId --revision $vlmRevision --local-dir $vlmModelDir --max-workers 4
        } finally {
            $env:HF_HUB_DISABLE_XET = $previousDisableXet
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Hugging Face model download failed for $repoId; re-run setup.ps1 to resume."
        }
    } else {
        $py = @"
import sys
from pathlib import Path
try:
    from modelscope.hub.snapshot_download import snapshot_download
except ImportError:
    from modelscope import snapshot_download
p = snapshot_download(model_id='$repoId', local_dir=str(Path(r'$vlmModelDir')))
print('Downloaded to:', p)
"@
        $venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
        $pythonExe = if (Test-Path $venvPy) { $venvPy } else { "python" }
        $py | & $pythonExe -
        if ($LASTEXITCODE -ne 0) { throw "modelscope download failed for $repoId" }
    }
    & powershell -ExecutionPolicy Bypass -File $lockVerify -Component Vlm -Path $vlmModelDir
    if ($LASTEXITCODE -ne 0) { throw "Downloaded VLM model does not match upstream-lock.json" }
    $ggufs = @(Get-ChildItem -LiteralPath $vlmModelDir -Recurse -File -Filter "*.gguf" -ErrorAction SilentlyContinue)
    if ($ggufs.Count -eq 0) { throw "No .gguf files found under $vlmModelDir" }
    $mainGguf = ($ggufs | Where-Object { $_.Name -notmatch "mmproj" } | Sort-Object Length -Descending | Select-Object -First 1).FullName
    if (-not $mainGguf) { $mainGguf = ($ggufs | Sort-Object Length -Descending | Select-Object -First 1).FullName }
    $mmproj = ($ggufs | Where-Object { $_.Name -match "mmproj" } | Sort-Object Length -Descending | Select-Object -First 1).FullName
    Write-Host "      Main GGUF:   $mainGguf" -ForegroundColor Green
    if ($mmproj) { Write-Host "      mmproj GGUF: $mmproj" -ForegroundColor Green }
    $vals = @{
        PADDLEOCR_VL_GGUF     = $mainGguf
        VL_REC_API_MODEL_NAME = (Split-Path $mainGguf -Leaf)
    }
    if ($mmproj) { $vals["PADDLEOCR_VL_MMPROJ"] = $mmproj }
    Set-DotEnv -Path $envFile -Values $vals
}

# Re-read env in case Phase 2 just populated it.
$envLocal = Get-DotEnv $envFile
$mainGguf = $envLocal["PADDLEOCR_VL_GGUF"]
$mmproj   = $envLocal["PADDLEOCR_VL_MMPROJ"]
if (-not $serverExe) { throw "llama-server.exe path unknown -- Phase 1 did not run?" }
if (-not $mainGguf)  { throw "PADDLEOCR_VL_GGUF not set in $envFile -- Phase 2 did not run?" }
if (-not (Test-Path -LiteralPath $serverExe.FullName)) { throw "llama-server.exe missing: $($serverExe.FullName)" }
if (-not (Test-Path $mainGguf))  { throw "Main GGUF missing: $mainGguf" }

# Persist server metadata so run_adapter.py + verify.ps1 can find it.
Set-DotEnv -Path $envFile -Values @{
    LLAMA_SERVER_EXE = $serverExe.FullName
    LLAMA_VARIANT    = $Variant
    LLAMA_TAG        = $Tag
    LLAMA_HOST       = $host_
    LLAMA_PORT       = $Port
    LLAMA_GPU_LAYERS = $(if ($Variant -eq "hip") { "99" } else { "0" })
    VL_REC_API_MODEL_NAME = (Split-Path $mainGguf -Leaf)
}

# ===========================================================================
# Phase 3 -- start llama-server (idempotent: skip if already answering)
# ===========================================================================
Write-Host "[3/3] Starting llama-server at $baseUrl ..." -ForegroundColor Cyan
$alreadyUp = $false
try {
    $null = Invoke-RestMethod -Uri "$baseUrl/v1/models" -Method Get -TimeoutSec 2
    Write-Host "      llama-server already running at $baseUrl -- nothing to do." -ForegroundColor Yellow
    $alreadyUp = $true
} catch {}

if (-not $alreadyUp) {
    # Parameters tuned + verified byte-identical vs conservative config on
    # AMD Radeon 8060S (Phase 5 parameter sweep in the source project).
    $gpuLayers = if ($Variant -eq "hip") { "99" } else { "0" }
    $modelAlias = Split-Path $mainGguf -Leaf
    $llamaArgs = @(
        "--host", $host_,
        "--port", $Port,
        "-m", $mainGguf,
        # Serve a deterministic model id: llama-server b9637 reports the -m
        # argument verbatim (full path on Windows), but the pipeline and
        # verify.ps1 ask for the basename. --alias pins the served id to the
        # basename so VL_REC_API_MODEL_NAME always matches /v1/models.
        "--alias", $modelAlias,
        "--temp", "0",
        "-c", "32768",
        "-ngl", $gpuLayers,
        "-fa", "on",
        "--seed", "1",
        "--top-k", "1",
        "--top-p", "1.0",
        "--min-p", "0.0",
        "--repeat-penalty", "1.0",
        "--fit", "off",
        "-np", "8",
        "--threads", "8",
        "--no-cache-prompt",
        "--cache-ram", "0",
        "--slot-prompt-similarity", "0.0",
        "--skip-chat-parsing",
        "--reasoning-format", "none",
        "--reasoning", "off"
    )
    if ($mmproj -and (Test-Path $mmproj)) { $llamaArgs = @("--mmproj", $mmproj) + $llamaArgs }

    $literalExe  = "'" + ($serverExe.FullName -replace "'", "''") + "'"
    $literalArgs = ($llamaArgs | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join " "
    $literalLog  = "'" + ($logFile -replace "'", "''") + "'"
    $bgCommand   = "& $literalExe $literalArgs *>> $literalLog"

    # Record the server start time and truncate the log so it contains ONLY
    # output produced by this server instance. assert-backend-proof.ps1 uses
    # both to reject stale logs and markers from earlier sessions.
    # A stale llama-server from an earlier session (same locked exe, different
    # port, or wedged) holds the log open and would make the truncate fail:
    # reclaim it first, but ONLY when the requested port is not answering and
    # ONLY instances of OUR locked executable.
    $staleServers = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -ieq "llama-server.exe" -and
        $_.ExecutablePath -and $_.ExecutablePath -ieq $serverExe.FullName -and
        $_.CommandLine -notmatch "--port\s+$Port"
    })
    foreach ($stale in $staleServers) {
        Write-Host "      Reclaiming stale llama-server pid $($stale.ProcessId) (port $Port not answering, instance serves a different port)..." -ForegroundColor Yellow
        Stop-Process -Id $stale.ProcessId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $startedFile = Join-Path $logDir "llama-server.started"
    [System.IO.File]::WriteAllText($startedFile, (Get-Date).ToUniversalTime().ToString("o"), $utf8NoBom)
    if (Test-Path -LiteralPath $logFile) {
        [System.IO.File]::WriteAllText($logFile, "", $utf8NoBom)
    }

    # Launch the wrapper via WMI Win32_Process.Create so it does NOT inherit
    # this process's handles. The orchestrator (reproduce.ps1 Invoke-ReproNative)
    # runs setup.ps1 through `Start-Process -Wait -RedirectStandardOutput`; a
    # wrapper launched by Start-Process would inherit that redirected stdout
    # pipe, and -Wait would then block until the long-lived server exits (a
    # deadlock that hangs any fresh inference.server stage). WMI-created
    # processes are spawned by the WMI service in a separate context and never
    # inherit caller handles, so the orchestrator's -Wait returns as soon as
    # setup.ps1 itself exits. (-WindowStyle Hidden keeps the wrapper headless.)
    $wrapperCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command " + $bgCommand
    $createRes = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $wrapperCmd }
    if ($createRes.ReturnValue -ne 0) {
        throw "WMI Win32_Process.Create failed (ReturnValue=$($createRes.ReturnValue)) while launching the llama-server wrapper"
    }
    $wrapperId = [int]$createRes.ProcessId
    Set-Content -LiteralPath $pidFile -Value $wrapperId -Encoding ASCII
    Write-Host "      Launched wrapper PID $wrapperId (via WMI); waiting for /v1/models..." -ForegroundColor DarkGray

    $ready = $false
    # Heartbeat: print a dot every ~30s (every 6th iteration of the 5s loop) so
    # an agent/user watching stdout can tell the script is alive and loading the
    # ~1.7 GB GGUF (normal, slow) rather than hung. Without this the loop prints
    # nothing for the first 30s, which is indistinguishable from a hang.
    Write-Host "      Waiting for llama-server (up to 5 min; loading the GGUF can take a while)..." -ForegroundColor DarkGray -NoNewline
    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Seconds 5
        try {
            $null = Invoke-RestMethod -Uri "$baseUrl/v1/models" -Method Get -TimeoutSec 3
            $ready = $true
            Write-Host ""  # finish the dot/heartbeat line
            Write-Host "      Server ready after $($i)x5s" -ForegroundColor Green
            break
        } catch {
            if ($i % 6 -eq 0) {
                Write-Host "." -ForegroundColor DarkGray -NoNewline
            }
        }
    }
    Write-Host ""  # ensure the heartbeat line ends with a newline
    if (-not $ready) {
        Write-Host "FAILED: llama-server not ready after 5 minutes." -ForegroundColor Red
        Write-Host "Last 20 log lines:" -ForegroundColor Yellow
        Get-Content $logFile -Tail 20 -ErrorAction SilentlyContinue
        exit 1
    }
}

Write-Host ""
Write-Host "=== llama-server is running ===" -ForegroundColor Green
Write-Host "  Endpoint: $baseUrl"
Write-Host "  PID file: $pidFile"
Write-Host "  Log:      $logFile"
Write-Host "  Env:      $envFile"
exit 0
