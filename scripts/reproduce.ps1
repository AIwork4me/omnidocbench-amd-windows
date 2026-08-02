<#
.SYNOPSIS
Single Windows entry point for AMD Windows OmniDocBench reproduction profiles.

.DESCRIPTION
The cpu-smoke-10 profile provisions the locked Windows/WSL stack, creates ten
fresh CPU predictions, scores Windows metrics and WSL CDM, and verifies the
exact artifacts. Progress is written atomically after every phase to
outputs/reproduction/cpu-smoke-10/state.json.

.PARAMETER Profile
Reproduction profile name (see -ListProfiles). Default: cpu-smoke-10.

.PARAMETER ListProfiles
List the available profiles (name, backend, pages, kind, expected runtime) and
exit without touching anything.

.PARAMETER Resume
Reuse completed stages in this clone. Without -Resume, existing prediction,
subset-manifest, or result artifacts cause a fail-closed error.

.PARAMETER ForceInference
Delete this profile's predictions and rerun inference. Cannot be combined with
a non-empty prediction directory unless explicitly provided.

.PARAMETER SkipCdmSetup
Reuse an already verified machine-global Ubuntu2204 CDM environment. The CDM
verifier still runs and CDM scoring remains mandatory.

.PARAMETER DryRun
Print the resolved profile and the ordered stage commands without executing
them (no downloads, no servers, no prediction/scoring writes).

.PARAMETER SeedFrom
Explicitly reuse lock-verified dataset/GGUF/layout bytes from another checkout.
This skips repeated bulk downloads but remains a fresh inference/scoring run.
#>
[CmdletBinding()]
param(
    [Alias("Profile")]
    [string] $RunProfile = "cpu-smoke-10",
    [switch] $ListProfiles,
    [switch] $Resume,
    [switch] $ForceInference,
    [switch] $SkipCdmSetup,
    [switch] $DryRun,
    [string] $SeedFrom = "",
    [string] $ServerPort = ""
)
$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $rootDir "scripts\repro-profiles.ps1")

if ($ListProfiles) {
    try {
        Format-ProfileList | Write-Host
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
    exit 0
}

$profile = $null
try {
    $profile = Get-ReproProfile -Name $RunProfile
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    try {
        $valid = @(Get-ProfileCatalog | ForEach-Object { $_.name }) -join ", "
        Write-Host "Valid profiles: $valid" -ForegroundColor Yellow
    } catch { }
    exit 1
}
$serverPort = if ($PSBoundParameters.ContainsKey("ServerPort")) { $ServerPort } else { $profile.Port }

$python = Join-Path $rootDir ".venv\Scripts\python.exe"
$predictionRel = ([string]$profile.prediction_dir) -replace "/", "\"
$predictionDir = $profile.PredictionDirAbs
$manifestRel = ([string]$profile.prediction_manifest) -replace "/", "\"
$manifest = $profile.ManifestAbs
$fullManifest = Join-Path $rootDir "eval-infra\01-omnidocbench\data\OmniDocBench.json"
$windowsResult = $profile.WindowsResultPath
$evidenceDir = $profile.EvidenceDir
$pipelineCheckout = Join-Path $rootDir "outputs\checkouts\PaddleOCR-VL-ROCm"
$stateFile = $profile.StateFile
$saveName = $profile.SaveName
$repoWsl = ""

Write-Host ""
Write-Host "=== Reproduction profile: $($profile.name) ($($profile.run_kind), $($profile.variant) backend) ===" -ForegroundColor Cyan
Show-ResolvedProfile -Profile $profile | Format-List | Out-Host
$state = [ordered]@{
    schema_version = 1
    profile = $RunProfile
    repo_commit = (& git -C $rootDir rev-parse HEAD 2>$null)
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    status = "running"
    phases = @()
    seeded_from = $(if ([string]::IsNullOrWhiteSpace($SeedFrom)) { $null } else { [System.IO.Path]::GetFullPath($SeedFrom) })
}
$completedPhases = @()
$alwaysRunPhases = @(
    "WSL availability",
    "Preflight",
    "WSL CDM environment",
    "CPU VLM server",
    "Inference input locks",
    "Exact full verification"
)
if ($Resume -and (Test-Path -LiteralPath $stateFile)) {
    $previousState = Get-Content -Raw -Encoding UTF8 -LiteralPath $stateFile | ConvertFrom-Json
    $completedPhases = @($previousState.phases | Where-Object { $_.status -eq "passed" } | ForEach-Object { $_.name })
    $state.started_at = $previousState.started_at
    $state.phases = @($previousState.phases)
    $state.resumed_at = (Get-Date).ToUniversalTime().ToString("o")
}

function Save-State {
    New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
    $temp = "$stateFile.tmp"
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $stateFile -Force
}

trap {
    if ($state.status -eq "running") {
        $state.status = "interrupted"
        $state.interrupted_at = (Get-Date).ToUniversalTime().ToString("o")
        $state.interruption_reason = $_.Exception.Message
        $state.resume_command = "powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $RunProfile -Resume"
        Save-State
    }
    throw
}

function Assert-LastExit([string] $Label) {
    if ($LASTEXITCODE -ne 0) { throw "$Label exited $LASTEXITCODE" }
}

function Invoke-Phase {
    param([string] $Name, [scriptblock] $Action, [string] $Command)
    Write-Host ""; Write-Host "=== $Name ===" -ForegroundColor Cyan
    Write-Host $Command -ForegroundColor DarkGray
    if ($Resume -and $completedPhases -contains $Name -and $alwaysRunPhases -notcontains $Name) {
        Write-Host "RESUME SKIP: phase already passed" -ForegroundColor Green
        return
    }
    if ($DryRun) {
        $state.phases += [ordered]@{ name = $Name; status = "dry-run"; command = $Command }
        Save-State
        return
    }
    $started = Get-Date
    $exitCode = 0
    $errorText = ""
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE; throw "Command exited $exitCode" }
    } catch {
        if ($exitCode -eq 0) { $exitCode = 1 }
        $errorText = $_.Exception.Message
    }
    $ended = Get-Date
    $state.phases += [ordered]@{
        name = $Name
        status = $(if ($exitCode -eq 0) { "passed" } else { "failed" })
        command = $Command
        exit_code = $exitCode
        started_at = $started.ToUniversalTime().ToString("o")
        ended_at = $ended.ToUniversalTime().ToString("o")
        duration_seconds = [math]::Round(($ended - $started).TotalSeconds, 2)
        error = $errorText
    }
    if ($exitCode -ne 0) {
        $state.status = "failed"
        $state.resume_command = "powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $RunProfile -Resume"
        Save-State
        throw "$Name failed: $errorText"
    }
    Save-State
}

if (-not $Resume -and -not $DryRun) {
    $existingPredictions = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    if ($existingPredictions -gt 0 -or (Test-Path -LiteralPath $manifest) -or (Test-Path -LiteralPath $windowsResult)) {
        throw "Existing $RunProfile artifacts found. Use -Resume to reuse them or -ForceInference to replace predictions after removing old score/manifest artifacts."
    }
}
if ($ForceInference -and (Test-Path -LiteralPath $predictionDir)) {
    Remove-Item -LiteralPath $predictionDir -Recurse -Force
}
Save-State

Invoke-Phase "Python environment" {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv not found; install astral-sh.uv with winget" }
    $previousLinkMode = $env:UV_LINK_MODE
    try {
        # OneDrive/Cloud Files rejects hardlinks from uv's local cache with
        # Windows error 396. Copy mode is deterministic and works everywhere.
        $env:UV_LINK_MODE = "copy"
        & uv python install 3.11
        Assert-LastExit "uv python install"
        & uv sync --locked --all-groups
        Assert-LastExit "uv sync"
    } finally {
        $env:UV_LINK_MODE = $previousLinkMode
    }
} "uv python install 3.11; uv sync --locked --all-groups"

Invoke-Phase "Network mirrors" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\detect-mirrors.ps1")
    Assert-LastExit "detect-mirrors.ps1"
} "scripts\detect-mirrors.ps1"

Invoke-Phase "WSL availability" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\wsl-ensure.ps1")
    Assert-LastExit "wsl-ensure.ps1"
} "scripts\wsl-ensure.ps1"

Invoke-Phase "Preflight" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\preflight.ps1") -CdmPath Wsl -Variant cpu
    Assert-LastExit "preflight.ps1"
} "scripts\preflight.ps1 -CdmPath Wsl -Variant cpu"

if (-not [string]::IsNullOrWhiteSpace($SeedFrom)) {
    Invoke-Phase "Seed locked inputs" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\seed-locked-inputs.ps1") -SourceRoot $SeedFrom -DestinationRoot $rootDir
        Assert-LastExit "seed locked inputs"
    } "seed-locked-inputs.ps1 -SourceRoot $SeedFrom"
}

Invoke-Phase "OmniDocBench and dataset" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\01-omnidocbench\setup.ps1")
    Assert-LastExit "01-omnidocbench setup"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\01-omnidocbench\verify.ps1")
    Assert-LastExit "01-omnidocbench verify"
} "eval-infra\01-omnidocbench\setup.ps1; verify.ps1"

Invoke-Phase "Upstream locks" {
    foreach ($component in @("OmniDocBench", "DatasetManifest")) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\verify-upstream-lock.ps1") -Component $component
        if ($LASTEXITCODE -ne 0) { throw "$component lock failed" }
    }
    & $python (Join-Path $rootDir "scripts\verify_dataset_tree.py") --manifest $fullManifest --image-dir (Join-Path $rootDir "eval-infra\01-omnidocbench\data\images") --lock (Join-Path $rootDir "upstream-lock.json")
    Assert-LastExit "dataset tree lock"
} "verify-upstream-lock.ps1; verify_dataset_tree.py"

Invoke-Phase "WSL CDM environment" {
    $script:repoWsl = (wsl -d Ubuntu2204 -- wslpath -a $rootDir).Trim()
    if (-not $SkipCdmSetup) {
        & wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/02-cdm-environment/setup.sh"
        Assert-LastExit "WSL CDM setup"
    }
    & wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/02-cdm-environment/verify.sh"
    Assert-LastExit "WSL CDM verify"
} "WSL setup.sh; verify.sh"

Invoke-Phase "CPU VLM server" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1") -Variant cpu -Port $serverPort
    Assert-LastExit "CPU VLM setup"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1")
    Assert-LastExit "CPU VLM verify"
} "01-vlm-server\setup.ps1 -Variant cpu -Port $serverPort; verify.ps1"

Invoke-Phase "Layout model" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1")
    Assert-LastExit "layout setup"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\02-layout-model\verify.ps1")
    Assert-LastExit "layout verify"
} "02-layout-model\setup.ps1; verify.ps1"

Invoke-Phase "Pipeline dependency" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1") -CloneDir $pipelineCheckout
    Assert-LastExit "pipeline dependency setup"
} "00-install-deps\setup.ps1 -CloneDir outputs\checkouts\PaddleOCR-VL-ROCm"

Invoke-Phase "Inference input locks" {
    foreach ($component in @("Vlm", "Layout")) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\verify-upstream-lock.ps1") -Component $component
        Assert-LastExit "$component lock"
    }
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\verify-upstream-lock.ps1") -Component Pipeline -Path $pipelineCheckout
    Assert-LastExit "Pipeline lock"
} "verify-upstream-lock.ps1 -Component Vlm,Layout,Pipeline"

Invoke-Phase "Ten-page CPU inference" {
    if (-not $Resume -or @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count -lt 10) {
        & $python (Join-Path $rootDir "adapters\paddleocr-vl-1.6\run_adapter.py") --img-dir (Join-Path $rootDir "eval-infra\01-omnidocbench\data\images") --out-dir $predictionDir --server-url "http://127.0.0.1:$serverPort/v1" --max-pages 10
        Assert-LastExit "ten-page inference"
    }
    $predictionCount = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    if ($predictionCount -ne 10) { throw "Ten-page inference requires exactly 10 Markdown predictions; found $predictionCount" }
} "run_adapter.py --server-url http://127.0.0.1:$serverPort/v1 --max-pages 10"

Invoke-Phase "Exact ten-page manifest" {
    $predictionCount = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    if ($predictionCount -ne 10) { throw "Manifest generation requires exactly 10 predictions; found $predictionCount" }
    & $python (Join-Path $rootDir "scripts\build_prediction_subset.py") --full-manifest $fullManifest --pred-dir $predictionDir --output $manifest --limit 10
    Assert-LastExit "ten-page manifest build"
    & $python (Join-Path $rootDir "scripts\validate_predictions.py") --manifest $manifest --pred-dir $predictionDir --min-coverage 1.0
    Assert-LastExit "ten-page prediction validation"
} "build_prediction_subset.py --limit 10; validate_predictions.py --min-coverage 1.0"

Invoke-Phase "Windows scoring" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\03-scoring\score.ps1") -Config v16-cpu-smoke-10.yaml
    Assert-LastExit "Windows scoring"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\03-scoring\verify.ps1") -WindowsOnly -SaveName $saveName
    Assert-LastExit "Windows score verify"
} "score.ps1 -Config v16-cpu-smoke-10.yaml; verify.ps1 -WindowsOnly -SaveName $saveName"

Invoke-Phase "WSL CDM scoring" {
    if ([string]::IsNullOrWhiteSpace($repoWsl)) { $script:repoWsl = (wsl -d Ubuntu2204 -- wslpath -a $rootDir).Trim() }
    & wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/03-scoring/score-cdm.sh" v16-cdm-cpu-smoke-10.yaml "predictions/paddleocrvl_cpu_smoke_10"
    Assert-LastExit "WSL CDM scoring"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\03-scoring\verify.ps1") -WslOnly -RequireCdm -SaveName $saveName
    Assert-LastExit "WSL CDM score verify"
} "score-cdm.sh v16-cdm-cpu-smoke-10.yaml predictions/paddleocrvl_cpu_smoke_10; verify -RequireCdm"

Invoke-Phase "Exact full verification" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\full-verify.ps1") -PredictionDir $predictionRel -PredictionManifest $manifestRel -ScoreSaveName $saveName -BenchmarkDir "__no_benchmark_for_smoke__"
    Assert-LastExit "exact full verification"
} "full-verify.ps1 -PredictionDir $predictionRel -PredictionManifest $manifestRel -ScoreSaveName $saveName"

if (-not $DryRun) {
    $state.status = "passed"
    $state.completed_at = (Get-Date).ToUniversalTime().ToString("o")
    $state.artifacts = [ordered]@{
        predictions = $predictionRel
        manifest = $manifestRel
        windows_metric = $windowsResult.Substring($rootDir.Length + 1)
        save_name = $saveName
    }
    Save-State
}
Write-Host ""
if ($DryRun) {
    Write-Host "DRY RUN OK: $RunProfile" -ForegroundColor Green
} else {
    Write-Host "REPRODUCTION OK: $RunProfile" -ForegroundColor Green
}
Write-Host "Evidence: $stateFile"
exit 0