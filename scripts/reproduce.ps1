<#
.SYNOPSIS
Single Windows entry point for AMD Windows OmniDocBench reproduction profiles.

.DESCRIPTION
The cpu-smoke-10 profile provisions the locked Windows/WSL stack, creates ten
fresh CPU predictions, scores Windows metrics and WSL CDM, and verifies the
exact artifacts. Progress is written atomically after every phase to
outputs/reproduction/cpu-smoke-10/state.json.

Resume model
------------
Each phase of a run is bound to its inputs by a phase-scoped fingerprint
(scripts/compute_fingerprint.py --phase provisioning|inference|scoring):

  * provisioning fingerprint: profile, upstream lock, dataset manifest,
    scoring configs, uv.lock, repo commit + working-tree content. Computed
    only after the dataset and upstream locks are provisioned and verified.
    Formal (full) profiles additionally fail closed on a dirty working tree.
  * inference fingerprint: provisioning fingerprint + adapter code tree,
    pipeline checkout commit, GGUF/mmproj/layout/server hashes, backend
    variant, resolved server port, inference-relevant environment.
  * scoring fingerprint: prediction tree hash, manifest, OmniDocBench
    checkout commit, scoring configs, scoring code, save name.

Resume invalidation rules
-------------------------
* Inference inputs changed (inference fingerprint mismatch) -> fail closed;
  use -ForceInference to reset.
* Prediction content changed between the pre-run and post-run tree hashes ->
  inference.prediction_check / scoring.windows / scoring.wsl_cdm /
  verification.final / evidence.pack passed states are cleared and scoring
  re-runs.
* Prediction content unchanged -> scores may be reused, but every scoring
  stage re-validates its metric-result provenance sidecar against the current
  prediction tree / manifest / config / result bytes; a mismatch or missing
  sidecar re-runs scoring.
* Scoring inputs changed (scoring fingerprint mismatch on resume) ->
  downstream score reuse is invalidated and scoring re-runs.

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

.PARAMETER ServerPort
Override the profile's declared server port for this run. The resolved port is
recorded in the evidence pack (profile.resolved.json, artifact-hashes.json,
report.md) so evidence never silently reflects the profile default.
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
# The orchestrator's own library scripts always come from the real checkout;
# REPRO_ROOT only redirects the *machine* (data/predictions/evidence) paths.
$script:RealRepoRoot = Split-Path -Parent $PSScriptRoot
# REPRO_ROOT / REPRO_TEST_PYTHON / REPRO_TEST_HOOKS are test-only injection
# points (fake integration harness, see tests/test_reproduce_harness.py). The
# formal path is unchanged when they are absent.
$rootDir = if ($env:REPRO_ROOT) { $env:REPRO_ROOT } else { $script:RealRepoRoot }
$script:TestHooksDir = $env:REPRO_TEST_HOOKS
. (Join-Path $script:RealRepoRoot "scripts\repro-profiles.ps1")
. (Join-Path $script:RealRepoRoot "scripts\repro-evidence.ps1")

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

# ---------------------------------------------------------------------------
# Unified owned-artifact path block. Every path this profile may read, write,
# or delete is defined HERE, immediately after the profile loads and BEFORE
# any stage or cleanup block runs. -ForceInference and the resume guards
# therefore never reference an uninitialized variable, and scoped deletion is
# limited to exactly these paths.
# ---------------------------------------------------------------------------
$serverPort = if ($PSBoundParameters.ContainsKey("ServerPort")) { $ServerPort } else { $profile.Port }
# REPRO_TEST_PYTHON is a test-only injection point for the fake harness; the
# formal path always uses the locked local venv.
$python = if ($env:REPRO_TEST_PYTHON) { $env:REPRO_TEST_PYTHON } else { Join-Path $rootDir ".venv\Scripts\python.exe" }
$predictionRel = ([string]$profile.prediction_dir) -replace "/", "\"
$predictionDir = $profile.PredictionDirAbs
$manifestRel = ([string]$profile.prediction_manifest) -replace "/", "\"
$manifest = $profile.ManifestAbs
$fullManifest = $profile.FullManifest
$windowsResult = $profile.WindowsResultPath
$evidenceDir = $profile.EvidenceDir
$pipelineCheckout = $profile.PipelineCheckout
$stateFile = $profile.StateFile
if ($DryRun) {
    # Dry-run state must never clobber a real run's evidence: write to a
    # distinct file so CI dry-run tests cannot destroy machine evidence.
    $stateFile = Join-Path $evidenceDir "state.dryrun.json"
}
$saveName = $profile.SaveName
$repoWsl = ""
$adapterDir = Join-Path $rootDir ("adapters\" + $profile.adapter)
$adapterEnvFile = Join-Path $adapterDir ".env.local"
# Adapter lifecycle is driven by the adapter manifest (adapters/<adapter>/adapter.json):
# the orchestrator only runs lifecycle stages the adapter declares. PaddleOCR-VL
# declares the full server/layout/install/inference chain; MinerU declares only
# install + inference and gets no VLM-server or backend-proof stages.
$adapterManifest = Get-AdapterManifest -AdapterName $profile.adapter -RootDir $rootDir
$adapterLifecycle = $adapterManifest.lifecycle
$hasServerLifecycle = -not [string]::IsNullOrWhiteSpace([string]$adapterLifecycle.server_setup)
$hasLayoutLifecycle = -not [string]::IsNullOrWhiteSpace([string]$adapterLifecycle.layout_setup)
$hasInstallLifecycle = -not [string]::IsNullOrWhiteSpace([string]$adapterLifecycle.install_deps)
$backendProofCapable = [bool]$adapterLifecycle.backend_proof_capable
$inferenceEntrypoint = [string]$adapterLifecycle.inference_entrypoint
$humanGates = @($adapterManifest.human_intervention_gates)
foreach ($gate in $humanGates) {
    Write-Host ""
    Write-Host "⚠️  HUMAN INTERVENTION GATE: $gate" -ForegroundColor Yellow
    Write-Host ""
}
$scoringCodeDir = Join-Path $rootDir "eval-infra\03-scoring"
$omnidocbenchCheckout = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench"
$backendProofFile = Join-Path $evidenceDir "backend-proof.json"
$predictionSummaryFile = Join-Path $evidenceDir "prediction-summary.json"
$predictionTreeFile = Join-Path $evidenceDir "prediction-tree.json"
$predictionTreePreFile = Join-Path $evidenceDir "prediction-tree.pre.json"
$windowsProvenanceFile = Join-Path (Split-Path -Parent $windowsResult) "$($saveName)_metric_result.provenance.json"
$wslProvenanceRel = "OmniDocBench\result\${saveName}_metric_result.provenance.json"
$fingerprintProvisioningFile = Join-Path $evidenceDir "fingerprint.provisioning.json"
$fingerprintInferenceFile = Join-Path $evidenceDir "fingerprint.inference.json"
$fingerprintScoringFile = Join-Path $evidenceDir "fingerprint.scoring.json"
$fingerprintEvidenceFile = Join-Path $evidenceDir "fingerprint.evidence.json"
$fingerprintProvisioningSpec = Join-Path $evidenceDir "fingerprint.provisioning.spec.json"
$fingerprintInferenceSpec = Join-Path $evidenceDir "fingerprint.inference.spec.json"
$fingerprintScoringSpec = Join-Path $evidenceDir "fingerprint.scoring.spec.json"
$profileResolvedFile = Join-Path $evidenceDir "profile.resolved.json"
$reportFile = Join-Path $evidenceDir "report.md"
$artifactHashesFile = Join-Path $evidenceDir "artifact-hashes.json"
$metricsSummaryFile = Join-Path $evidenceDir "metrics-summary.json"
$hardwareFile = Join-Path $evidenceDir "hardware.json"
# Purge set: stages whose passed status may be reused only after provenance
# re-validation; prediction/scoring changes clear exactly these.
$downstreamScoringStageIds = @(
    "scoring.windows", "scoring.wsl_cdm", "verification.final", "evidence.pack"
)

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
    "inference.fingerprint",
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
    $temp = "$stateFile.tmp.$PID"
    $lastError = $null
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($temp, ($state | ConvertTo-Json -Depth 10), $utf8NoBom)
        for ($attempt = 0; $attempt -lt 5; $attempt++) {
            try {
                Move-Item -LiteralPath $temp -Destination $stateFile -Force
                return
            } catch {
                $lastError = $_
                # A just-written temp file can be transiently locked by
                # antivirus/search-indexers; retry before giving up.
                Start-Sleep -Milliseconds 300
            }
        }
        throw "Save-State failed after retries: $($lastError.Exception.Message)"
    } finally {
        if (Test-Path -LiteralPath $temp) {
            Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
        }
    }
}

trap {
    if ($state.status -eq "running") {
        $state.status = "interrupted"
        $state.interrupted_at = (Get-Date).ToUniversalTime().ToString("o")
        $state.interruption_reason = $_.Exception.Message
        $state.resume_command = "powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $RunProfile -Resume"
        try { Save-State } catch { }
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

function Remove-StageRecords {
    param([string[]] $Ids)
    $removed = @($state.stages | Where-Object { $Ids -contains $_.id })
    $state.stages = @($state.stages | Where-Object { $Ids -notcontains $_.id })
    $script:completedStageIds = @($state.stages | Where-Object { $_.status -eq "passed" } | ForEach-Object { $_.id })
    if ($removed.Count -gt 0) {
        Write-Host ("INVALIDATED stages: " + (($removed | ForEach-Object { $_.id }) -join ", ")) -ForegroundColor Yellow
        Save-State
    }
}

function Get-JsonField {
    param([string] $Path, [string] $Field)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        $json = Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
        return $json.$Field
    } catch { return $null }
}

function Invoke-Stage {
    param(
        [string] $Id,
        [string] $Name,
        [switch] $AlwaysRun,
        [scriptblock] $Action,
        [string] $Command,
        [scriptblock] $ResumeGuard = $null,
        [string[]] $ResumeGuardPurges = @()
    )
    Write-Host ""; Write-Host "=== $Name [$Id] ===" -ForegroundColor Cyan
    Write-Host $Command -ForegroundColor DarkGray
    $resumeSkip = $Resume -and $completedStageIds -contains $Id -and -not $AlwaysRun.IsPresent
    if ($resumeSkip -and $null -ne $ResumeGuard) {
        Write-Host "RESUME: re-validating $Id provenance before reuse" -ForegroundColor Yellow
        $guardExit = 0
        try {
            & $ResumeGuard
            if ($LASTEXITCODE -ne 0) { $guardExit = $LASTEXITCODE }
        } catch {
            $guardExit = 1
            Write-Host "RESUME GUARD ERROR: $($_.Exception.Message)" -ForegroundColor Red
        }
        if ($guardExit -ne 0) {
            Write-Host "RESUME: provenance mismatch - invalidating $Id and re-running" -ForegroundColor Yellow
            Remove-StageRecords -Ids (@($Id) + @($ResumeGuardPurges) | Where-Object { $_ })
            $resumeSkip = $false
        }
    }
    if ($resumeSkip) {
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

# ---------------------------------------------------------------------------
# Test-only command routing (fake integration harness). When REPRO_TEST_HOOKS
# is set, every external script invocation is re-routed to a fake script with
# the same repo-relative path under the hooks dir; wsl/uv calls are re-routed
# to hooks\wsl.ps1 / hooks\uv.ps1. Scripts without a hook run from the real
# repo (so the real gates like assert-metrics.ps1 still execute), while all
# paths/arguments still point at the fake root. The formal path is
# byte-for-byte unchanged when REPRO_TEST_HOOKS is absent.
# ---------------------------------------------------------------------------
function Resolve-ReproScriptPath {
    param([string] $Relative)
    $rel = $Relative -replace "/", "\"
    if ($script:TestHooksDir) {
        $candidate = Join-Path $script:TestHooksDir $rel
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $candidate = Join-Path $rootDir $rel
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return Join-Path $script:RealRepoRoot $rel
}

function Invoke-ReproExternal {
    param([string] $Relative, [string[]] $Arguments)
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Resolve-ReproScriptPath -Relative $Relative) @Arguments
    return $LASTEXITCODE
}

function Invoke-ReproPython {
    param([string] $Relative, [string[]] $Arguments)
    & $python (Resolve-ReproScriptPath -Relative $Relative) @Arguments
    return $LASTEXITCODE
}

function Invoke-ReproWsl {
    param([string[]] $Arguments)
    if ($script:TestHooksDir) {
        $shim = Join-Path $script:TestHooksDir "wsl.ps1"
        if (Test-Path -LiteralPath $shim -PathType Leaf) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $shim @Arguments
            return $LASTEXITCODE
        }
    }
    & wsl @Arguments
    return $LASTEXITCODE
}

function Invoke-ReproUv {
    param([string[]] $Arguments)
    if ($script:TestHooksDir) {
        $shim = Join-Path $script:TestHooksDir "uv.ps1"
        if (Test-Path -LiteralPath $shim -PathType Leaf) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $shim @Arguments
            return $LASTEXITCODE
        }
    }
    & uv @Arguments
    return $LASTEXITCODE
}

if ($ForceInference -and -not $DryRun) {
    # Scoped cleanup: ONLY this profile's owned artifacts (all paths defined
    # in the artifact-path block above). The shared locked dataset manifest
    # (full profile) is never touched.
    $targets = @()
    if (Test-Path -LiteralPath $predictionDir) { $targets += $predictionDir }
    if ($profile.owned_manifest -and (Test-Path -LiteralPath $manifest)) { $targets += $manifest }
    $winResultDir = Split-Path -Parent $windowsResult
    if (Test-Path -LiteralPath $winResultDir) {
        $targets += @(Get-ChildItem -LiteralPath $winResultDir -File -Filter "$($saveName)_*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    $wslResultDir = Get-WslResultDir -SaveName $saveName
    if (Test-Path -LiteralPath $wslResultDir) {
        $targets += @(Get-ChildItem -LiteralPath $wslResultDir -File -Filter "$($saveName)_*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    foreach ($target in $targets) {
        Write-Host "FORCE INFERENCE: removing $target" -ForegroundColor Yellow
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Purge inference/scoring/verification stage records so they re-run, and
    # clear the phase fingerprints + prediction tree hashes so a later -Resume
    # re-checks against fresh inputs.
    $purgeIds = @(
        "inference.run", "inference.prediction_check", "inference.fingerprint",
        "scoring.fingerprint", "scoring.windows", "scoring.wsl_cdm",
        "verification.final", "evidence.pack", "inputs.fingerprint"
    )
    foreach ($ownedFile in @(
        $fingerprintProvisioningFile, $fingerprintInferenceFile, $fingerprintScoringFile,
        $fingerprintEvidenceFile, $predictionTreeFile, $predictionTreePreFile,
        $predictionSummaryFile, $backendProofFile, $metricsSummaryFile,
        $artifactHashesFile, $profileResolvedFile, $reportFile, $hardwareFile,
        $windowsProvenanceFile
    )) {
        if (Test-Path -LiteralPath $ownedFile) {
            Write-Host "FORCE INFERENCE: removing $ownedFile" -ForegroundColor Yellow
            Remove-Item -LiteralPath $ownedFile -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-StageRecords -Ids $purgeIds
}

if (-not $Resume -and -not $DryRun) {
    $existingPredictions = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    $ownedManifestExists = $profile.owned_manifest -and (Test-Path -LiteralPath $manifest)
    if ($existingPredictions -gt 0 -or $ownedManifestExists -or (Test-Path -LiteralPath $windowsResult)) {
        throw "Existing $RunProfile artifacts found. Use -Resume to reuse them or -ForceInference to replace predictions after removing old score/manifest artifacts."
    }
}
Save-State

Invoke-Stage -Id "environment.python" -Name "Python environment" {
    if (-not $script:TestHooksDir -and -not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv not found; install astral-sh.uv with winget" }
    # mirrors.env (written by detect-mirrors.ps1) is the repo's network
    # contract; its PYPI_INDEX wins over any global UV_INDEX_URL so locked
    # syncs do not silently use a broken or different index.
    $mirrorsFile = Join-Path $rootDir "mirrors.env"
    if (Test-Path -LiteralPath $mirrorsFile -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $mirrorsFile) {
            if ($line -match "^PYPI_INDEX=(.*)$") {
                $env:UV_INDEX_URL = $matches[1].Trim()
                break
            }
        }
    }
    $previousLinkMode = $env:UV_LINK_MODE
    try {
        # OneDrive/Cloud Files rejects hardlinks from uv's local cache with
        # Windows error 396. Copy mode is deterministic and works everywhere.
        $env:UV_LINK_MODE = "copy"
        Invoke-ReproUv python install 3.11
        Assert-LastExit "uv python install"
        Invoke-ReproUv sync --locked --all-groups
        Assert-LastExit "uv sync"
    } finally {
        $env:UV_LINK_MODE = $previousLinkMode
    }
} -Command "uv python install 3.11; uv sync --locked --all-groups (PYPI_INDEX from mirrors.env)"

Invoke-Stage -Id "environment.mirrors" -Name "Network mirrors" {
    Invoke-ReproExternal -Relative "scripts\detect-mirrors.ps1"
    Assert-LastExit "detect-mirrors.ps1"
} -Command "scripts\detect-mirrors.ps1"

Invoke-Stage -Id "environment.wsl" -Name "WSL availability" -AlwaysRun {
    Invoke-ReproExternal -Relative "scripts\wsl-ensure.ps1"
    Assert-LastExit "wsl-ensure.ps1"
} -Command "scripts\wsl-ensure.ps1"

Invoke-Stage -Id "profile.preflight" -Name "Preflight" -AlwaysRun {
    Invoke-ReproExternal -Relative "scripts\preflight.ps1" -Arguments @("-CdmPath", "Wsl", "-Variant", $profile.variant)
    Assert-LastExit "preflight.ps1"
} -Command "scripts\preflight.ps1 -CdmPath Wsl -Variant $($profile.variant)"

if (-not [string]::IsNullOrWhiteSpace($SeedFrom)) {
    Invoke-Stage -Id "inputs.seed" -Name "Seed locked inputs" {
        Invoke-ReproExternal -Relative "scripts\seed-locked-inputs.ps1" -Arguments @("-SourceRoot", $SeedFrom, "-DestinationRoot", $rootDir)
        Assert-LastExit "seed locked inputs"
    } -Command "seed-locked-inputs.ps1 -SourceRoot $SeedFrom"
}

Invoke-Stage -Id "dataset.setup" -Name "OmniDocBench and dataset" {
    Invoke-ReproExternal -Relative "eval-infra\01-omnidocbench\setup.ps1"
    Assert-LastExit "01-omnidocbench setup"
    Invoke-ReproExternal -Relative "eval-infra\01-omnidocbench\verify.ps1"
    Assert-LastExit "01-omnidocbench verify"
} -Command "eval-infra\01-omnidocbench\setup.ps1; verify.ps1"

Invoke-Stage -Id "dataset.upstream_locks" -Name "Upstream locks" {
    foreach ($component in @("OmniDocBench", "DatasetManifest")) {
        Invoke-ReproExternal -Relative "scripts\verify-upstream-lock.ps1" -Arguments @("-Component", $component)
        if ($LASTEXITCODE -ne 0) { throw "$component lock failed" }
    }
    Invoke-ReproPython -Relative "scripts\verify_dataset_tree.py" -Arguments @("--manifest", $fullManifest, "--image-dir", (Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"), "--lock", (Join-Path $rootDir "upstream-lock.json"))
    Assert-LastExit "dataset tree lock"
} -Command "verify-upstream-lock.ps1; verify_dataset_tree.py"

# ---------------------------------------------------------------------------
# Provisioning fingerprint: computed ONLY after the dataset + upstream locks
# are provisioned and verified. Formal (full) profiles fail closed on a dirty
# working tree; non-formal profiles record a content hash of the tree state
# (git diff --binary HEAD + untracked-file contents) so further edits to an
# already-modified file are still detected on resume.
# ---------------------------------------------------------------------------
Invoke-Stage -Id "inputs.fingerprint" -Name "Provisioning fingerprint" -AlwaysRun {
    $spec = [ordered]@{
        profile_sha256 = @{ file = $profile.ProfilePath }
        upstream_lock_sha256 = @{ file = (Join-Path $rootDir "upstream-lock.json") }
        dataset_manifest_sha256 = @{ file = $fullManifest }
        windows_scoring_config_sha256 = @{ file = $profile.ConfigWindowsAbs }
        wsl_cdm_config_sha256 = @{ file = $profile.ConfigWslAbs }
        uv_lock_sha256 = @{ file = (Join-Path $rootDir "uv.lock") }
        repo_commit = @{ git = "." }
        repo_tree_sha256 = @{ repo_tree = "." }
    }
    Save-JsonAtomic -Path $fingerprintProvisioningSpec -Value $spec
    if ($profile.run_kind -eq "full") {
        Invoke-ReproPython -Relative "scripts\compute_fingerprint.py" -Arguments @("--phase", "provisioning", "--root", $rootDir, "--inputs", $fingerprintProvisioningSpec, "--check-clean")
        if ($LASTEXITCODE -ne 0) { throw "Formal profile requires a clean git working tree" }
    }
    $fpArgs = @("--phase", "provisioning", "--root", $rootDir, "--inputs", $fingerprintProvisioningSpec)
    if ($Resume -and -not $ForceInference -and (Test-Path -LiteralPath $fingerprintProvisioningFile -PathType Leaf)) {
        # A previous fingerprint exists: the inputs that produced the stored
        # states must still match. A MISSING fingerprint is fine -- it only
        # means the run was interrupted before this phase completed, so the
        # fingerprint is simply computed fresh (no prior inputs to compare).
        $fpArgs += @("--check", $fingerprintProvisioningFile)
    }
    $fpArgs += @("--out", $fingerprintProvisioningFile)
    Invoke-ReproPython -Relative "scripts\compute_fingerprint.py" -Arguments $fpArgs
    if ($LASTEXITCODE -ne 0) { throw "Provisioning fingerprint check failed - inputs changed since the previous run" }
} -Command "compute_fingerprint.py --phase provisioning$(if ($profile.run_kind -eq 'full') { ' --check-clean' }) $(if ($Resume -and -not $ForceInference) { ' --check fingerprint.provisioning.json' }) --out fingerprint.provisioning.json"

function Get-RepoWslPath {
    # PowerShell -> wsl.exe argument passing eats backslashes, so convert the
    # Windows path to forward slashes first; fall back to a manual /mnt/<drive>
    # translation (the full-verify.ps1 approach) if wslpath still fails.
    $posix = $rootDir -replace "\\", "/"
    $result = ""
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $result = ((@(Invoke-ReproWsl -Arguments @("-d", "Ubuntu2204", "--", "wslpath", "-a", $posix) 2>$null) -join "") -replace "`0", "").Trim()
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (-not $result) {
        $result = "/mnt/" + $posix.Substring(0, 1).ToLowerInvariant() + "/" + $posix.Substring(2)
    }
    return $result
}

Invoke-Stage -Id "cdm.wsl_environment" -Name "WSL CDM environment" -AlwaysRun {
    $script:repoWsl = Get-RepoWslPath
    if (-not $SkipCdmSetup) {
        Invoke-ReproWsl -Arguments @("-d", "Ubuntu2204", "bash", "$repoWsl/eval-infra/02-cdm-environment/setup.sh")
        Assert-LastExit "WSL CDM setup"
    }
    Invoke-ReproWsl -Arguments @("-d", "Ubuntu2204", "bash", "$repoWsl/eval-infra/02-cdm-environment/verify.sh")
    Assert-LastExit "WSL CDM verify"
} -Command "WSL setup.sh; verify.sh"

Invoke-Stage -Id "inference.server" -Name "VLM server" -AlwaysRun {
    if ($hasServerLifecycle) {
        Invoke-ReproExternal -Relative ([string]$adapterLifecycle.server_setup) -Arguments @("-Variant", $profile.variant, "-Port", $serverPort)
        Assert-LastExit "VLM setup"
        Invoke-ReproExternal -Relative ([string]$adapterLifecycle.server_verify)
        Assert-LastExit "VLM verify"
    } else {
        Write-Host "Adapter '$($profile.adapter)' declares no VLM server lifecycle; skipping." -ForegroundColor Yellow
    }
} -Command "01-vlm-server\setup.ps1 -Variant $($profile.variant) -Port $serverPort; verify.ps1"

Invoke-Stage -Id "inference.backend_proof" -Name "Backend proof" -AlwaysRun {
    if ($profile.require_gpu_backend_proof -and $profile.variant -eq "hip" -and $backendProofCapable) {
        Invoke-ReproExternal -Relative "adapters\$($profile.adapter)\01-vlm-server\assert-backend-proof.ps1" -Arguments @(
            "-EnvFile", $adapterEnvFile,
            "-LogFile", (Join-Path $adapterDir "logs\llama-server.log"),
            "-PidFile", (Join-Path $adapterDir "logs\llama-server.pid"),
            "-StartTimeFile", (Join-Path $adapterDir "logs\llama-server.started"),
            "-ExpectedVariant", "hip",
            "-LockFile", (Join-Path $rootDir "upstream-lock.json"),
            "-OutFile", $backendProofFile,
            "-BaseUrl", "http://127.0.0.1:$serverPort"
        )
        Assert-LastExit "HIP backend proof"
    } else {
        Write-Host "Backend proof not required for this profile (variant=$($profile.variant), adapter=$($profile.adapter))." -ForegroundColor Yellow
    }
} -Command "assert-backend-proof.ps1 -ExpectedVariant $($profile.variant) -BaseUrl http://127.0.0.1:$serverPort -> backend-proof.json"

Invoke-Stage -Id "inference.layout" -Name "Layout model" {
    if ($hasLayoutLifecycle) {
        Invoke-ReproExternal -Relative ([string]$adapterLifecycle.layout_setup)
        Assert-LastExit "layout setup"
        Invoke-ReproExternal -Relative ([string]$adapterLifecycle.layout_verify)
        Assert-LastExit "layout verify"
    } else {
        Write-Host "Adapter '$($profile.adapter)' declares no layout-model lifecycle; skipping." -ForegroundColor Yellow
    }
} -Command "02-layout-model\setup.ps1; verify.ps1"

Invoke-Stage -Id "inference.pipeline_deps" -Name "Pipeline dependency" {
    if ($hasInstallLifecycle) {
        Invoke-ReproExternal -Relative ([string]$adapterLifecycle.install_deps) -Arguments @("-CloneDir", $pipelineCheckout)
        Assert-LastExit "pipeline dependency setup"
    } else {
        Write-Host "Adapter '$($profile.adapter)' declares no install lifecycle; skipping." -ForegroundColor Yellow
    }
} -Command "00-install-deps\setup.ps1 -CloneDir outputs\checkouts\PaddleOCR-VL-ROCm"

Invoke-Stage -Id "inference.input_locks" -Name "Inference input locks" -AlwaysRun {
    foreach ($component in @("Vlm", "Layout")) {
        Invoke-ReproExternal -Relative "scripts\verify-upstream-lock.ps1" -Arguments @("-Component", $component)
        Assert-LastExit "$component lock"
    }
    Invoke-ReproExternal -Relative "scripts\verify-upstream-lock.ps1" -Arguments @("-Component", "Pipeline", "-Path", $pipelineCheckout)
    Assert-LastExit "Pipeline lock"
} -Command "verify-upstream-lock.ps1 -Component Vlm,Layout,Pipeline"

# ---------------------------------------------------------------------------
# Inference fingerprint: binds every input that determines prediction content.
# Computed only after the pipeline checkout, model weights and server are
# provisioned and lock-verified. A mismatch on resume fails closed (reusing
# --skip-existing predictions from different model bytes would be wrong).
# ---------------------------------------------------------------------------
Invoke-Stage -Id "inference.fingerprint" -Name "Inference fingerprint" -AlwaysRun {
    $envValues = Get-DotEnvValues -Path $adapterEnvFile
    $spec = [ordered]@{
        provisioning_fingerprint_sha256 = @{ file = $fingerprintProvisioningFile }
        adapter_tree_sha256 = @{ tree = $adapterDir }
        pipeline_checkout_commit = @{ git = $pipelineCheckout }
        vlm_gguf_sha256 = @{ file = ([string]$envValues["PADDLEOCR_VL_GGUF"]) }
        vlm_mmproj_sha256 = @{ file = ([string]$envValues["PADDLEOCR_VL_MMPROJ"]) }
        layout_model_sha256 = @{ file = ([string]$envValues["PP_DOCLAYOUTV3_ONNX_DIR"]) }
        server_exe_sha256 = @{ file = ([string]$envValues["LLAMA_SERVER_EXE"]) }
        backend_variant = @{ string = $profile.variant }
        resolved_server_port = @{ string = $serverPort }
        manifest_sha256 = @{ file = $fullManifest }
        inference_env = @{ env = @("PYTHONUTF8", "ADAPTER_SERVER_URL", "ADAPTER_LAYOUT_MODEL", "ADAPTER_API_MODEL_NAME", "PADDLEOCR_VL_ENGINE", "PADDLEOCR_VL_PAGE_RETRIES", "PADDLEOCR_VL_FALLBACK_PRED_DIR", "LLAMA_HOST", "LLAMA_PORT") }
    }
    Save-JsonAtomic -Path $fingerprintInferenceSpec -Value $spec
    $fpArgs = @("--phase", "inference", "--root", $rootDir, "--inputs", $fingerprintInferenceSpec)
    if ($Resume -and -not $ForceInference -and (Test-Path -LiteralPath $fingerprintInferenceFile -PathType Leaf)) {
        # Same rule as provisioning: a stored fingerprint must still match;
        # a missing one (interrupted run) is simply computed fresh.
        $fpArgs += @("--check", $fingerprintInferenceFile)
    }
    $fpArgs += @("--out", $fingerprintInferenceFile)
    Invoke-ReproPython -Relative "scripts\compute_fingerprint.py" -Arguments $fpArgs
    if ($LASTEXITCODE -ne 0) { throw "Inference fingerprint check failed - inference inputs changed since the previous run" }
} -Command "compute_fingerprint.py --phase inference --out fingerprint.inference.json"

$maxPagesArgs = if ($null -ne $profile.max_pages) { @("--max-pages", "$($profile.max_pages)") } else { @() }
$skipExistingArg = @()
if ($Resume) { $skipExistingArg = @("--skip-existing") }
Invoke-Stage -Id "inference.run" -Name "Inference" -AlwaysRun {
    # Pre-run prediction tree hash: the resume baseline. If the post-run hash
    # differs, the predictions changed and every downstream score reuse is
    # invalidated (never reuse a score computed from different bytes).
    Invoke-ReproPython -Relative "scripts\hash_prediction_tree.py" -Arguments @("--manifest", $fullManifest, "--pred-dir", $predictionDir, "--out", $predictionTreePreFile)
    if ($LASTEXITCODE -ne 0) { throw "pre-run prediction tree hash failed" }
    $preTreeHash = Get-JsonField -Path $predictionTreePreFile -Field "prediction_tree_sha256"
    $adapterArgs = @(
        "--img-dir", (Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"),
        "--out-dir", $predictionDir,
        "--server-url", "http://127.0.0.1:$serverPort/v1",
        "--gt-manifest", $fullManifest
    ) + $maxPagesArgs + $skipExistingArg
    Invoke-ReproPython -Relative $inferenceEntrypoint -Arguments $adapterArgs
    Assert-LastExit "inference"
    $predictionCount = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    if ($profile.run_kind -eq "smoke" -and $predictionCount -ne $profile.expected_pages) {
        throw "Smoke inference requires exactly $($profile.expected_pages) Markdown predictions; found $predictionCount"
    }
    Invoke-ReproPython -Relative "scripts\hash_prediction_tree.py" -Arguments @("--manifest", $fullManifest, "--pred-dir", $predictionDir, "--out", $predictionTreeFile)
    if ($LASTEXITCODE -ne 0) { throw "post-run prediction tree hash failed" }
    $postTreeHash = Get-JsonField -Path $predictionTreeFile -Field "prediction_tree_sha256"
    if ($Resume -and $preTreeHash -and $postTreeHash -and $preTreeHash -ne $postTreeHash) {
        Write-Host "PREDICTION CONTENT CHANGED: invalidating prediction_check, scoring and evidence reuse" -ForegroundColor Yellow
        Remove-StageRecords -Ids (@("inference.prediction_check", "scoring.fingerprint") + $downstreamScoringStageIds)
    }
} -Command ("run_adapter.py --server-url http://127.0.0.1:$serverPort/v1 " + $(if ($maxPagesArgs.Count -gt 0) { "--max-pages $($profile.max_pages)" } else { "(no page limit)" }) + $(if ($Resume) { " --skip-existing" } else { "" }) + "; hash_prediction_tree.py pre/post")

Invoke-Stage -Id "inference.prediction_check" -Name "Prediction manifest and validation" {
    if ($profile.owned_manifest) {
        $predictionCount = @(Get-ChildItem -LiteralPath $predictionDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
        if ($predictionCount -ne $profile.expected_pages) { throw "Manifest generation requires exactly $($profile.expected_pages) predictions; found $predictionCount" }
        Invoke-ReproPython -Relative "scripts\build_prediction_subset.py" -Arguments @("--full-manifest", $fullManifest, "--pred-dir", $predictionDir, "--output", $manifest, "--limit", "$($profile.expected_pages)")
        Assert-LastExit "manifest build"
    }
    $allowedArgs = @()
    if ($null -ne $profile.allowed_failed_page_stems) {
        foreach ($stem in @($profile.allowed_failed_page_stems)) {
            $allowedArgs += @("--allowed-failed-page-stems", $stem)
        }
    }
    # verify_prediction_set.py is the SINGLE source of truth for the strict
    # prediction-summary.json; evidence.pack only reads/copies it.
    $verifyArgs = @(
        "--manifest", $manifest,
        "--pred-dir", $predictionDir,
        "--expected-pages", "$($profile.expected_pages)",
        "--min-coverage", "$($profile.minimum_prediction_coverage)",
        "--max-failed-pages", "$($profile.maximum_failed_pages)",
        "--require-selected",
        "--prediction-tree-json", $predictionTreeFile,
        "--summary-out", $predictionSummaryFile
    ) + $allowedArgs
    Invoke-ReproPython -Relative "scripts\verify_prediction_set.py" -Arguments $verifyArgs
    Assert-LastExit "strict prediction-set validation"
} -Command "build_prediction_subset.py (smoke only); verify_prediction_set.py --expected-pages $($profile.expected_pages) -> prediction-summary.json"

# ---------------------------------------------------------------------------
# Scoring fingerprint: binds the prediction tree hash + scorer inputs. On
# resume, any mismatch invalidates downstream score reuse and re-runs scoring.
# ---------------------------------------------------------------------------
Invoke-Stage -Id "scoring.fingerprint" -Name "Scoring fingerprint" {
    $treeHash = Get-JsonField -Path $predictionTreeFile -Field "prediction_tree_sha256"
    $spec = [ordered]@{
        prediction_tree_sha256 = @{ string = $treeHash }
        prediction_manifest_sha256 = @{ file = $manifest }
        omnidocbench_checkout_commit = @{ git = $omnidocbenchCheckout }
        windows_scoring_config_sha256 = @{ file = $profile.ConfigWindowsAbs }
        wsl_cdm_config_sha256 = @{ file = $profile.ConfigWslAbs }
        scoring_code_sha256 = @{ tree = $scoringCodeDir }
        hash_prediction_tree_py_sha256 = @{ file = (Join-Path $rootDir "scripts\hash_prediction_tree.py") }
        verify_prediction_set_py_sha256 = @{ file = (Join-Path $rootDir "scripts\verify_prediction_set.py") }
        metric_provenance_py_sha256 = @{ file = (Join-Path $rootDir "scripts\metric_provenance.py") }
        compute_fingerprint_py_sha256 = @{ file = (Join-Path $rootDir "scripts\compute_fingerprint.py") }
        save_name = @{ string = $saveName }
    }
    Save-JsonAtomic -Path $fingerprintScoringSpec -Value $spec
    $fpArgs = @("--phase", "scoring", "--root", $rootDir, "--inputs", $fingerprintScoringSpec)
    $fpArgs += @("--out", $fingerprintScoringFile)
    Invoke-ReproPython -Relative "scripts\compute_fingerprint.py" -Arguments $fpArgs
    if ($LASTEXITCODE -ne 0) { throw "scoring fingerprint failed" }
} -Command "compute_fingerprint.py --phase scoring --out fingerprint.scoring.json" -ResumeGuard {
    $treeHash = Get-JsonField -Path $predictionTreeFile -Field "prediction_tree_sha256"
    $spec = [ordered]@{
        prediction_tree_sha256 = @{ string = $treeHash }
        prediction_manifest_sha256 = @{ file = $manifest }
        omnidocbench_checkout_commit = @{ git = $omnidocbenchCheckout }
        windows_scoring_config_sha256 = @{ file = $profile.ConfigWindowsAbs }
        wsl_cdm_config_sha256 = @{ file = $profile.ConfigWslAbs }
        scoring_code_sha256 = @{ tree = $scoringCodeDir }
        hash_prediction_tree_py_sha256 = @{ file = (Join-Path $rootDir "scripts\hash_prediction_tree.py") }
        verify_prediction_set_py_sha256 = @{ file = (Join-Path $rootDir "scripts\verify_prediction_set.py") }
        metric_provenance_py_sha256 = @{ file = (Join-Path $rootDir "scripts\metric_provenance.py") }
        compute_fingerprint_py_sha256 = @{ file = (Join-Path $rootDir "scripts\compute_fingerprint.py") }
        save_name = @{ string = $saveName }
    }
    Save-JsonAtomic -Path $fingerprintScoringSpec -Value $spec
    Invoke-ReproPython -Relative "scripts\compute_fingerprint.py" -Arguments @("--phase", "scoring", "--root", $rootDir, "--inputs", $fingerprintScoringSpec, "--check", $fingerprintScoringFile)
} -ResumeGuardPurges @("scoring.windows", "scoring.wsl_cdm", "verification.final", "evidence.pack", "evidence.fingerprint")

function Assert-ScoringProvenance {
    param([string] $ResultFile, [string] $ProvenanceFile, [string] $ConfigFile, [string] $Platform)
    $treeHash = Get-JsonField -Path $predictionTreeFile -Field "prediction_tree_sha256"
    if ([string]::IsNullOrWhiteSpace($treeHash)) { throw "prediction tree hash missing ($predictionTreeFile)" }
    Invoke-ReproPython -Relative "scripts\metric_provenance.py" -Arguments @(
        "verify",
        "--result", $ResultFile,
        "--out", $ProvenanceFile,
        "--prediction-tree", $treeHash,
        "--manifest", $manifest,
        "--config", $ConfigFile,
        "--scorer-checkout", $omnidocbenchCheckout,
        "--scoring-code-dir", $scoringCodeDir,
        "--expected-pages", "$([int]$profile.expected_pages)",
        "--save-name", $saveName,
        "--platform", $Platform
    )
}

function Write-ScoringProvenance {
    param([string] $ResultFile, [string] $ProvenanceFile, [string] $ConfigFile, [string] $Platform)
    $treeHash = Get-JsonField -Path $predictionTreeFile -Field "prediction_tree_sha256"
    if ([string]::IsNullOrWhiteSpace($treeHash)) { throw "prediction tree hash missing ($predictionTreeFile)" }
    Invoke-ReproPython -Relative "scripts\metric_provenance.py" -Arguments @(
        "write",
        "--result", $ResultFile,
        "--out", $ProvenanceFile,
        "--prediction-tree", $treeHash,
        "--manifest", $manifest,
        "--config", $ConfigFile,
        "--scorer-checkout", $omnidocbenchCheckout,
        "--scoring-code-dir", $scoringCodeDir,
        "--expected-pages", "$([int]$profile.expected_pages)",
        "--save-name", $saveName,
        "--platform", $Platform
    )
    Assert-LastExit "metric provenance write ($Platform)"
}

Invoke-Stage -Id "scoring.windows" -Name "Windows scoring" {
    Invoke-ReproExternal -Relative "eval-infra\03-scoring\score.ps1" -Arguments @("-Config", $profile.windows_scoring_config)
    Assert-LastExit "Windows scoring"
    Invoke-ReproExternal -Relative "eval-infra\03-scoring\verify.ps1" -Arguments @("-WindowsOnly", "-SaveName", $saveName)
    Assert-LastExit "Windows score verify"
    Write-ScoringProvenance -ResultFile $windowsResult -ProvenanceFile $windowsProvenanceFile -ConfigFile $profile.ConfigWindowsAbs -Platform windows
    $metricArgs = @(
        "-MetricResult", $windowsResult,
        "-Profile", $profile.ProfilePath,
        "-ProvenanceFile", $windowsProvenanceFile,
        "-NotOlderThan", $state.started_at,
        "-ExpectedPages", "$([int]$profile.expected_pages)"
    )
    if ($null -ne $profile.PSObject.Properties["max_timeout_cases"] -and $null -ne $profile.max_timeout_cases) { $metricArgs += @("-MaxTimeouts", "$($profile.max_timeout_cases)") }
    if ($null -ne $profile.PSObject.Properties["max_exception_cases"] -and $null -ne $profile.max_exception_cases) { $metricArgs += @("-MaxExceptions", "$($profile.max_exception_cases)") }
    if ($null -ne $profile.PSObject.Properties["max_metric_error_cases"] -and $null -ne $profile.max_metric_error_cases) { $metricArgs += @("-MaxMetricErrors", "$($profile.max_metric_error_cases)") }
    Invoke-ReproExternal -Relative "scripts\assert-metrics.ps1" -Arguments $metricArgs
    Assert-LastExit "Windows metric sanity gates"
} -Command "score.ps1 -Config $($profile.windows_scoring_config); verify.ps1 -WindowsOnly; metric_provenance.py write; assert-metrics.ps1" -ResumeGuard {
    Assert-ScoringProvenance -ResultFile $windowsResult -ProvenanceFile $windowsProvenanceFile -ConfigFile $profile.ConfigWindowsAbs -Platform windows
} -ResumeGuardPurges @("verification.final", "evidence.pack", "evidence.fingerprint")

Invoke-Stage -Id "scoring.wsl_cdm" -Name "WSL CDM scoring" {
    if ([string]::IsNullOrWhiteSpace($repoWsl)) { $script:repoWsl = Get-RepoWslPath }
    Invoke-ReproWsl -Arguments @("-d", "Ubuntu2204", "bash", "$repoWsl/eval-infra/03-scoring/score-cdm.sh", $profile.wsl_cdm_config, $profile.prediction_dir)
    Assert-LastExit "WSL CDM scoring"
    Invoke-ReproExternal -Relative "eval-infra\03-scoring\verify.ps1" -Arguments @("-WslOnly", "-RequireCdm", "-SaveName", $saveName)
    Assert-LastExit "WSL CDM score verify"
    $wslResult = Get-WslResultPath -SaveName $saveName
    $wslProvenance = Get-WslResultPath -SaveName $saveName -FileSuffix "_metric_result.provenance.json"
    Write-ScoringProvenance -ResultFile $wslResult -ProvenanceFile $wslProvenance -ConfigFile $profile.ConfigWslAbs -Platform wsl
    $metricArgs = @(
        "-MetricResult", $wslResult,
        "-Profile", $profile.ProfilePath,
        "-RequireCdm",
        "-ProvenanceFile", $wslProvenance,
        "-NotOlderThan", $state.started_at,
        "-ExpectedPages", "$([int]$profile.expected_pages)",
        "-CompareResult", $windowsResult
    )
    if ($null -ne $profile.PSObject.Properties["max_timeout_cases"] -and $null -ne $profile.max_timeout_cases) { $metricArgs += @("-MaxTimeouts", "$($profile.max_timeout_cases)") }
    if ($null -ne $profile.PSObject.Properties["max_exception_cases"] -and $null -ne $profile.max_exception_cases) { $metricArgs += @("-MaxExceptions", "$($profile.max_exception_cases)") }
    if ($null -ne $profile.PSObject.Properties["max_metric_error_cases"] -and $null -ne $profile.max_metric_error_cases) { $metricArgs += @("-MaxMetricErrors", "$($profile.max_metric_error_cases)") }
    Invoke-ReproExternal -Relative "scripts\assert-metrics.ps1" -Arguments $metricArgs
    Assert-LastExit "WSL CDM metric sanity gates"
} -Command "score-cdm.sh $($profile.wsl_cdm_config) $($profile.prediction_dir); verify -RequireCdm; metric_provenance.py write; assert-metrics.ps1" -ResumeGuard {
    $wslResult = Get-WslResultPath -SaveName $saveName
    $wslProvenance = Get-WslResultPath -SaveName $saveName -FileSuffix "_metric_result.provenance.json"
    Assert-ScoringProvenance -ResultFile $wslResult -ProvenanceFile $wslProvenance -ConfigFile $profile.ConfigWslAbs -Platform wsl
} -ResumeGuardPurges @("verification.final", "evidence.pack", "evidence.fingerprint")

Invoke-Stage -Id "verification.final" -Name "Exact full verification" -AlwaysRun {
    $verifyArgs = @("-PredictionDir", $predictionRel, "-PredictionManifest", $manifestRel, "-ScoreSaveName", $saveName)
    if ($profile.run_kind -eq "full") {
        $verifyArgs += @(
            "-ExpectedPages", "$($profile.expected_pages)",
            "-MinCoverage", "$($profile.minimum_prediction_coverage)",
            "-MaxFailedPages", "$($profile.maximum_failed_pages)",
            "-RequireRunStatsSelected"
        )
        # PowerShell 5.1 -File binding rejects repeated -AllowedFailedPageStem
        # occurrences (ParameterAlreadyBound); bind once with comma-joined stems.
        if (@($profile.allowed_failed_page_stems).Count -gt 0) {
            $verifyArgs += @("-AllowedFailedPageStem", (@($profile.allowed_failed_page_stems) -join ","))
        }
    }
    Invoke-ReproExternal -Relative "scripts\full-verify.ps1" -Arguments $verifyArgs
    Assert-LastExit "exact full verification"
} -Command "full-verify.ps1 -PredictionDir $predictionRel -PredictionManifest $manifestRel -ScoreSaveName $saveName $(if ($profile.run_kind -eq 'full') { '(strict profile gates)' } else { '' })"

Invoke-Stage -Id "evidence.pack" -Name "Evidence pack" -AlwaysRun {
    if (-not $DryRun) {
        Write-ProfileResolved -EvidenceDir $evidenceDir -Profile $profile -ServerPort $serverPort | Out-Null
        Write-HardwareJson -EvidenceDir $evidenceDir
        Write-ArtifactHashes -EvidenceDir $evidenceDir -Profile $profile -PipelineCheckout $pipelineCheckout -EnvFile $adapterEnvFile -ServerPort $serverPort -PredictionTreeFile $predictionTreeFile -PredictionSummaryFile $predictionSummaryFile -BackendProofFile $backendProofFile -WindowsResult $windowsResult -WindowsProvenanceFile $windowsProvenanceFile -WslResult (Get-WslResultPath -SaveName $saveName) -WslProvenanceFile (Get-WslResultPath -SaveName $saveName -FileSuffix "_metric_result.provenance.json") -StateFile $stateFile -ReportFile $reportFile -ProfileResolvedFile $profileResolvedFile | Out-Null
        # prediction-summary.json is written ONLY by verify_prediction_set.py;
        # the evidence pack verifies and copies it, never recomputes it.
        if (-not (Test-Path -LiteralPath $predictionSummaryFile -PathType Leaf)) {
            throw "strict prediction summary missing: $predictionSummaryFile (verify_prediction_set.py must produce it)"
        }
        $strictSummary = Get-Content -Raw -Encoding UTF8 -LiteralPath $predictionSummaryFile | ConvertFrom-Json
        if ([string]$strictSummary.verdict -ne "pass") {
            throw "strict prediction summary verdict is '$($strictSummary.verdict)', not 'pass' - refusing to pack evidence"
        }
        Copy-Item -LiteralPath $predictionSummaryFile -Destination (Join-Path $evidenceDir "prediction-summary.strict.json") -Force
        $wslResult = Get-WslResultPath -SaveName $saveName
        Write-MetricsSummary -EvidenceDir $evidenceDir -WindowsResult $windowsResult -WslResult $wslResult -SaveName $saveName | Out-Null
        $fingerprint = @{}
        if (Test-Path -LiteralPath $fingerprintProvisioningFile) {
            $fingerprint = Get-Content -Raw -Encoding UTF8 -LiteralPath $fingerprintProvisioningFile | ConvertFrom-Json
        }
        # Mark the run passed BEFORE the report is rendered so report.md reflects
        # the final verdict instead of the in-flight "running" status.
        $state.status = "passed"
        $state.completed_at = (Get-Date).ToUniversalTime().ToString("o")
        $state.artifacts = [ordered]@{
            predictions = $predictionRel
            manifest = $manifestRel
            windows_metric = $windowsResult.Substring($rootDir.Length + 1)
            save_name = $saveName
            resolved_server_port = $serverPort
        }
        Write-Report -EvidenceDir $evidenceDir -State $state -Profile $profile -Fingerprint $fingerprint -ResumeCommand "powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $RunProfile -Resume" -ServerPort $serverPort -PredictionTreeHash (Get-JsonField -Path $predictionTreeFile -Field "prediction_tree_sha256") | Out-Null
        Save-State
        # Evidence fingerprint must bind the FINAL state file, so it is
        # computed after the run is marked passed.
        $spec = [ordered]@{
            strict_prediction_summary_sha256 = @{ file = $predictionSummaryFile }
            windows_metric_result_sha256 = @{ file = $windowsResult }
            wsl_metric_result_sha256 = @{ file = $wslResult }
            backend_proof_sha256 = @{ file = $backendProofFile }
            run_state_sha256 = @{ file = $stateFile }
            full_verify_ps1_sha256 = @{ file = (Join-Path $rootDir "scripts\full-verify.ps1") }
            assert_metrics_ps1_sha256 = @{ file = (Join-Path $rootDir "scripts\assert-metrics.ps1") }
            repro_evidence_ps1_sha256 = @{ file = (Join-Path $rootDir "scripts\repro-evidence.ps1") }
        }
        Save-JsonAtomic -Path (Join-Path $evidenceDir "fingerprint.evidence.spec.json") -Value $spec
        Invoke-ReproPython -Relative "scripts\compute_fingerprint.py" -Arguments @("--phase", "evidence", "--root", $rootDir, "--inputs", (Join-Path $evidenceDir "fingerprint.evidence.spec.json"), "--out", $fingerprintEvidenceFile)
        if ($LASTEXITCODE -ne 0) { throw "evidence fingerprint failed" }
    }
} -Command "evidence pack -> outputs\reproduction\$RunProfile"

if (-not $DryRun) {
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
