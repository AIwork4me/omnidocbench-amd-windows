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
. (Join-Path $rootDir "scripts\repro-evidence.ps1")

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
    schema_version = 2
    profile = $RunProfile
    repo_commit = (& git -C $rootDir rev-parse HEAD 2>$null)
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    status = "running"
    stages = @()
    seeded_from = $(if ([string]::IsNullOrWhiteSpace($SeedFrom)) { $null } else { [System.IO.Path]::GetFullPath($SeedFrom) })
}
$completedStageIds = @()
$alwaysRunStageIds = @(
    "environment.wsl",
    "profile.preflight",
    "inputs.fingerprint",
    "cdm.wsl_environment",
    "inference.server",
    "inference.backend_proof",
    "inference.input_locks",
    "inference.run",
    "verification.final",
    "evidence.pack"
)
if ($Resume -and (Test-Path -LiteralPath $stateFile)) {
    $previousState = Get-Content -Raw -Encoding UTF8 -LiteralPath $stateFile | ConvertFrom-Json
    if ([int]$previousState.schema_version -ne 2) {
        throw "state.json schema v$($previousState.schema_version) is not compatible with this reproduce.ps1. Start a fresh run (remove or rename $stateFile) -- old phase-name resume keys cannot be mapped safely."
    }
    $completedStageIds = @($previousState.stages | Where-Object { $_.status -eq "passed" } | ForEach-Object { $_.id })
    $state.started_at = $previousState.started_at
    $state.stages = @($previousState.stages)
    $state.resumed_at = (Get-Date).ToUniversalTime().ToString("o")
}

function Save-State {
    New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
    $temp = "$stateFile.tmp"
    $state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temp -Encoding UTF8
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

function Set-StageRecord {
    param([hashtable] $Record)
    $found = $false
    for ($i = 0; $i -lt $state.stages.Count; $i++) {
        if ($state.stages[$i].id -eq $Record.id) { $state.stages[$i] = $Record; $found = $true; break }
    }
    if (-not $found) { $state.stages += $Record }
}

function Invoke-Stage {
    param(
        [string] $Id,
        [string] $Name,
        [switch] $AlwaysRun,
        [scriptblock] $Action,
        [string] $Command
    )
    Write-Host ""; Write-Host "=== $Name [$Id] ===" -ForegroundColor Cyan
    Write-Host $Command -ForegroundColor DarkGray
    if ($Resume -and $completedStageIds -contains $Id -and -not $AlwaysRun.IsPresent) {
        Write-Host "RESUME SKIP: stage already passed" -ForegroundColor Green
        return
    }
    if ($DryRun) {
        Set-StageRecord -Record ([ordered]@{ id = $Id; name = $Name; status = "dry-run"; command = $Command })
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
    Set-StageRecord -Record ([ordered]@{
        id = $Id
        name = $Name
        status = $(if ($exitCode -eq 0) { "passed" } else { "failed" })
        command = $Command
        exit_code = $exitCode
        started_at = $started.ToUniversalTime().ToString("o")
        ended_at = $ended.ToUniversalTime().ToString("o")
        duration_seconds = [math]::Round(($ended - $started).TotalSeconds, 2)
        error = $errorText
    })
    if ($exitCode -ne 0) {
        $state.status = "failed"
        $state.resume_command = "powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $RunProfile -Resume"
        Save-State
        throw "$Name [$Id] failed: $errorText"
    }
    Save-State
}

if ($ForceInference -and -not $DryRun) {
    # Scoped cleanup: ONLY this profile's owned artifacts. The shared locked
    # dataset manifest (full profile) is never touched.
    $targets = @()
    if (Test-Path -LiteralPath $predictionDir) { $targets += $predictionDir }
    if ($profile.owned_manifest -and (Test-Path -LiteralPath $manifest)) { $targets += $manifest }
    $winResultDir = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench\result"
    if (Test-Path -LiteralPath $winResultDir) {
        $targets += @(Get-ChildItem -LiteralPath $winResultDir -File -Filter "$($saveName)_*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    $wslHomeUnc = "\\wsl$\Ubuntu2204\root\OmniDocBench\result"
    if (Test-Path -LiteralPath $wslHomeUnc) {
        $targets += @(Get-ChildItem -LiteralPath $wslHomeUnc -File -Filter "$($saveName)_*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    foreach ($target in $targets) {
        Write-Host "FORCE INFERENCE: removing $target" -ForegroundColor Yellow
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Purge inference/scoring/verification stage records so they re-run.
    $purgeIds = @("inference.run", "inference.prediction_check", "scoring.windows", "scoring.wsl_cdm", "verification.final", "evidence.pack", "inputs.fingerprint")
    $state.stages = @($state.stages | Where-Object { $purgeIds -notcontains $_.id })
    $completedStageIds = @($state.stages | Where-Object { $_.status -eq "passed" } | ForEach-Object { $_.id })
    Save-State
}

if (-not $Resume -and -not $DryRun) {
    $existingPredictions = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    $ownedManifestExists = $profile.owned_manifest -and (Test-Path -LiteralPath $manifest)
    if ($existingPredictions -gt 0 -or $ownedManifestExists -or (Test-Path -LiteralPath $windowsResult)) {
        throw "Existing $RunProfile artifacts found. Use -Resume to reuse them or -ForceInference to replace predictions after removing old score/manifest artifacts."
    }
}
if ($ForceInference -and (Test-Path -LiteralPath $predictionDir)) {
    Remove-Item -LiteralPath $predictionDir -Recurse -Force
}
Save-State

Invoke-Stage -Id "environment.python" -Name "Python environment" {
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
} -Command "uv python install 3.11; uv sync --locked --all-groups"

Invoke-Stage -Id "environment.mirrors" -Name "Network mirrors" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\detect-mirrors.ps1")
    Assert-LastExit "detect-mirrors.ps1"
} -Command "scripts\detect-mirrors.ps1"

Invoke-Stage -Id "environment.wsl" -Name "WSL availability" -AlwaysRun {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\wsl-ensure.ps1")
    Assert-LastExit "wsl-ensure.ps1"
} -Command "scripts\wsl-ensure.ps1"

Invoke-Stage -Id "profile.preflight" -Name "Preflight" -AlwaysRun {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\preflight.ps1") -CdmPath Wsl -Variant $profile.variant
    Assert-LastExit "preflight.ps1"
} -Command "scripts\preflight.ps1 -CdmPath Wsl -Variant $($profile.variant)"

if (-not [string]::IsNullOrWhiteSpace($SeedFrom)) {
    Invoke-Stage -Id "inputs.seed" -Name "Seed locked inputs" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\seed-locked-inputs.ps1") -SourceRoot $SeedFrom -DestinationRoot $rootDir
        Assert-LastExit "seed locked inputs"
    } -Command "seed-locked-inputs.ps1 -SourceRoot $SeedFrom"
}

Invoke-Stage -Id "dataset.setup" -Name "OmniDocBench and dataset" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\01-omnidocbench\setup.ps1")
    Assert-LastExit "01-omnidocbench setup"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\01-omnidocbench\verify.ps1")
    Assert-LastExit "01-omnidocbench verify"
} -Command "eval-infra\01-omnidocbench\setup.ps1; verify.ps1"

Invoke-Stage -Id "dataset.upstream_locks" -Name "Upstream locks" {
    foreach ($component in @("OmniDocBench", "DatasetManifest")) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\verify-upstream-lock.ps1") -Component $component
        if ($LASTEXITCODE -ne 0) { throw "$component lock failed" }
    }
    & $python (Join-Path $rootDir "scripts\verify_dataset_tree.py") --manifest $fullManifest --image-dir (Join-Path $rootDir "eval-infra\01-omnidocbench\data\images") --lock (Join-Path $rootDir "upstream-lock.json")
    Assert-LastExit "dataset tree lock"
} -Command "verify-upstream-lock.ps1; verify_dataset_tree.py"

$fingerprintFile = Join-Path $evidenceDir "fingerprint.json"
Invoke-Stage -Id "inputs.fingerprint" -Name "Input fingerprint" -AlwaysRun {
    $fpArgs = @(
        "--root", $rootDir,
        "--profile", $profile.ProfilePath,
        "--manifest", $fullManifest,
        "--pipeline", $pipelineCheckout,
        "--windows-config", $profile.ConfigWindowsAbs,
        "--wsl-config", $profile.ConfigWslAbs,
        "--out", $fingerprintFile
    )
    if ($Resume -and (Test-Path -LiteralPath $fingerprintFile)) {
        $fpArgs += @("--check", $fingerprintFile)
    }
    & $python (Join-Path $rootDir "scripts\compute_fingerprint.py") @fpArgs
    if ($LASTEXITCODE -ne 0) { throw "Fingerprint check failed - inputs changed since the previous run" }
} -Command "compute_fingerprint.py --out fingerprint.json$(if ($Resume) { ' --check fingerprint.json' })"

Invoke-Stage -Id "cdm.wsl_environment" -Name "WSL CDM environment" -AlwaysRun {
    $script:repoWsl = (wsl -d Ubuntu2204 -- wslpath -a $rootDir).Trim()
    if (-not $SkipCdmSetup) {
        & wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/02-cdm-environment/setup.sh"
        Assert-LastExit "WSL CDM setup"
    }
    & wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/02-cdm-environment/verify.sh"
    Assert-LastExit "WSL CDM verify"
} -Command "WSL setup.sh; verify.sh"

Invoke-Stage -Id "inference.server" -Name "VLM server" -AlwaysRun {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1") -Variant $profile.variant -Port $serverPort
    Assert-LastExit "VLM setup"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1")
    Assert-LastExit "VLM verify"
} -Command "01-vlm-server\setup.ps1 -Variant $($profile.variant) -Port $serverPort; verify.ps1"

Invoke-Stage -Id "inference.backend_proof" -Name "Backend proof" -AlwaysRun {
    if ($profile.require_gpu_backend_proof -and $profile.variant -eq "hip") {
        $adapterRoot = Join-Path $rootDir "adapters\paddleocr-vl-1.6"
        & powershell -ExecutionPolicy Bypass -File (Join-Path $adapterRoot "01-vlm-server\assert-backend-proof.ps1") `
            -EnvFile (Join-Path $adapterRoot ".env.local") `
            -LogFile (Join-Path $adapterRoot "logs\llama-server.log") `
            -PidFile (Join-Path $adapterRoot "logs\llama-server.pid") `
            -ExpectedVariant hip `
            -LockFile (Join-Path $rootDir "upstream-lock.json") `
            -OutFile (Join-Path $evidenceDir "backend-proof.json")
        Assert-LastExit "HIP backend proof"
    } else {
        Write-Host "Backend proof not required for this profile (variant=$($profile.variant))." -ForegroundColor Yellow
    }
} -Command "assert-backend-proof.ps1 -ExpectedVariant $($profile.variant) -> backend-proof.json"

Invoke-Stage -Id "inference.layout" -Name "Layout model" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1")
    Assert-LastExit "layout setup"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\02-layout-model\verify.ps1")
    Assert-LastExit "layout verify"
} -Command "02-layout-model\setup.ps1; verify.ps1"

Invoke-Stage -Id "inference.pipeline_deps" -Name "Pipeline dependency" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1") -CloneDir $pipelineCheckout
    Assert-LastExit "pipeline dependency setup"
} -Command "00-install-deps\setup.ps1 -CloneDir outputs\checkouts\PaddleOCR-VL-ROCm"

Invoke-Stage -Id "inference.input_locks" -Name "Inference input locks" -AlwaysRun {
    foreach ($component in @("Vlm", "Layout")) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\verify-upstream-lock.ps1") -Component $component
        Assert-LastExit "$component lock"
    }
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\verify-upstream-lock.ps1") -Component Pipeline -Path $pipelineCheckout
    Assert-LastExit "Pipeline lock"
} -Command "verify-upstream-lock.ps1 -Component Vlm,Layout,Pipeline"

$maxPagesArgs = if ($null -ne $profile.max_pages) { @("--max-pages", "$($profile.max_pages)") } else { @() }
$skipExistingArg = @()
if ($Resume) { $skipExistingArg = @("--skip-existing") }
Invoke-Stage -Id "inference.run" -Name "Inference" -AlwaysRun {
    $adapterArgs = @(
        "--img-dir", (Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"),
        "--out-dir", $predictionDir,
        "--server-url", "http://127.0.0.1:$serverPort/v1"
    ) + $maxPagesArgs + $skipExistingArg
    & $python (Join-Path $rootDir "adapters\paddleocr-vl-1.6\run_adapter.py") @adapterArgs
    Assert-LastExit "inference"
    $predictionCount = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    if ($profile.run_kind -eq "smoke" -and $predictionCount -ne $profile.expected_pages) {
        throw "Smoke inference requires exactly $($profile.expected_pages) Markdown predictions; found $predictionCount"
    }
} -Command ("run_adapter.py --server-url http://127.0.0.1:$serverPort/v1 " + $(if ($maxPagesArgs.Count -gt 0) { "--max-pages $($profile.max_pages)" } else { "(no page limit)" }) + $(if ($Resume) { " --skip-existing" } else { "" }))

Invoke-Stage -Id "inference.prediction_check" -Name "Prediction manifest and validation" {
    if ($profile.owned_manifest) {
        $predictionCount = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
        if ($predictionCount -ne $profile.expected_pages) { throw "Manifest generation requires exactly $($profile.expected_pages) predictions; found $predictionCount" }
        & $python (Join-Path $rootDir "scripts\build_prediction_subset.py") --full-manifest $fullManifest --pred-dir $predictionDir --output $manifest --limit $($profile.expected_pages)
        Assert-LastExit "manifest build"
    }
    if ($profile.run_kind -eq "full") {
        & $python (Join-Path $rootDir "scripts\verify_prediction_set.py") `
            --manifest $manifest `
            --pred-dir $predictionDir `
            --expected-pages $($profile.expected_pages) `
            --min-coverage $($profile.minimum_prediction_coverage) `
            --max-failed-pages $($profile.maximum_failed_pages) `
            --require-selected `
            --summary-out (Join-Path $evidenceDir "prediction-summary.json")
        Assert-LastExit "strict prediction-set validation"
    } else {
        & $python (Join-Path $rootDir "scripts\validate_predictions.py") --manifest $manifest --pred-dir $predictionDir --min-coverage $($profile.minimum_prediction_coverage)
        Assert-LastExit "prediction validation"
    }
} -Command "build_prediction_subset.py (smoke only); verify_prediction_set.py --expected-pages $($profile.expected_pages) (full); validate_predictions.py (smoke)"

Invoke-Stage -Id "scoring.windows" -Name "Windows scoring" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\03-scoring\score.ps1") -Config $profile.windows_scoring_config
    Assert-LastExit "Windows scoring"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\03-scoring\verify.ps1") -WindowsOnly -SaveName $saveName
    Assert-LastExit "Windows score verify"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\assert-metrics.ps1") `
        -MetricResult $windowsResult `
        -Profile $profile.ProfilePath `
        -NotOlderThan $state.started_at
    Assert-LastExit "Windows metric sanity gates"
} -Command "score.ps1 -Config $($profile.windows_scoring_config); verify.ps1 -WindowsOnly; assert-metrics.ps1"

Invoke-Stage -Id "scoring.wsl_cdm" -Name "WSL CDM scoring" {
    if ([string]::IsNullOrWhiteSpace($repoWsl)) { $script:repoWsl = (wsl -d Ubuntu2204 -- wslpath -a $rootDir).Trim() }
    & wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/03-scoring/score-cdm.sh" $profile.wsl_cdm_config $profile.prediction_dir
    Assert-LastExit "WSL CDM scoring"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "eval-infra\03-scoring\verify.ps1") -WslOnly -RequireCdm -SaveName $saveName
    Assert-LastExit "WSL CDM score verify"
    $wslHome = (wsl -d Ubuntu2204 -- sh -lc 'printf %s "$HOME"').Trim() -replace "`0", ""
    if (-not $wslHome) { $wslHome = "/root" }
    $wslResult = "\\wsl$\Ubuntu2204" + ($wslHome -replace "/", "\") + "\OmniDocBench\result\${saveName}_metric_result.json"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\assert-metrics.ps1") `
        -MetricResult $wslResult `
        -Profile $profile.ProfilePath `
        -NotOlderThan $state.started_at
    Assert-LastExit "WSL CDM metric sanity gates"
} -Command "score-cdm.sh $($profile.wsl_cdm_config) $($profile.prediction_dir); verify -RequireCdm; assert-metrics.ps1"

Invoke-Stage -Id "verification.final" -Name "Exact full verification" -AlwaysRun {
    $verifyArgs = @("-PredictionDir", $predictionRel, "-PredictionManifest", $manifestRel, "-ScoreSaveName", $saveName, "-BenchmarkDir", "__no_benchmark_for_smoke__")
    if ($profile.run_kind -eq "full") {
        $verifyArgs += @(
            "-ExpectedPages", "$($profile.expected_pages)",
            "-MinCoverage", "$($profile.minimum_prediction_coverage)",
            "-MaxFailedPages", "$($profile.maximum_failed_pages)",
            "-RequireRunStatsSelected"
        )
    }
    & powershell -ExecutionPolicy Bypass -File (Join-Path $rootDir "scripts\full-verify.ps1") @verifyArgs
    Assert-LastExit "exact full verification"
} -Command "full-verify.ps1 -PredictionDir $predictionRel -PredictionManifest $manifestRel -ScoreSaveName $saveName $(if ($profile.run_kind -eq 'full') { '(strict profile gates)' } else { '' })"

Invoke-Stage -Id "evidence.pack" -Name "Evidence pack" -AlwaysRun {
    if (-not $DryRun) {
        Write-ProfileResolved -EvidenceDir $evidenceDir -Profile $profile | Out-Null
        Write-HardwareJson -EvidenceDir $evidenceDir
        Write-ArtifactHashes -EvidenceDir $evidenceDir -Profile $profile -PipelineCheckout $pipelineCheckout -EnvFile (Join-Path $rootDir "adapters\paddleocr-vl-1.6\.env.local") | Out-Null
        $wslHome = (wsl -d Ubuntu2204 -- sh -lc 'printf %s "$HOME"').Trim() -replace "`0", ""
        if (-not $wslHome) { $wslHome = "/root" }
        $wslResult = "\\wsl$\Ubuntu2204" + ($wslHome -replace "/", "\") + "\OmniDocBench\result\${saveName}_metric_result.json"
        Write-MetricsSummary -EvidenceDir $evidenceDir -WindowsResult $windowsResult -WslResult $wslResult -SaveName $saveName | Out-Null
        $fingerprint = @{}
        if (Test-Path -LiteralPath $fingerprintFile) {
            $fingerprint = Get-Content -Raw -Encoding UTF8 -LiteralPath $fingerprintFile | ConvertFrom-Json
        }
        Write-Report -EvidenceDir $evidenceDir -State $state -Profile $profile -Fingerprint $fingerprint -ResumeCommand "powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $RunProfile -Resume" | Out-Null
    }
} -Command "evidence pack -> outputs\reproduction\$RunProfile"

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