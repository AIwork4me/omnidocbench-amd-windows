<#
.SYNOPSIS
Evidence-pack helpers for reproduce.ps1 (dot-sourceable, PowerShell 5.1).

.DESCRIPTION
Atomic JSON writes and machine-hardware/artifact fingerprinting used to build
the per-profile evidence pack under outputs/reproduction/<profile>/.
This file defines functions only; it performs no work at dot-source time.

Single source of truth
----------------------
prediction-summary.json is written ONLY by scripts/verify_prediction_set.py.
The evidence pack verifies and copies it (prediction-summary.strict.json);
it never recomputes the strict summary.
#>
if (-not $script:ReproRoot) { $script:ReproRoot = Split-Path -Parent $PSScriptRoot }

function Save-JsonAtomic {
    param([string] $Path, $Value, [int] $Depth = 12)
    $directory = Split-Path -Parent $Path
    if ($directory) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
    $temp = "$Path.tmp.$PID"
    $lastError = $null
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($temp, ($Value | ConvertTo-Json -Depth $Depth), $utf8NoBom)
        for ($attempt = 0; $attempt -lt 5; $attempt++) {
            try {
                Move-Item -LiteralPath $temp -Destination $Path -Force
                return
            } catch {
                $lastError = $_
                Start-Sleep -Milliseconds 300
            }
        }
        throw "Save-JsonAtomic failed after retries ($Path): $($lastError.Exception.Message)"
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
    }
}

function Get-FileSha256 {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        $bytes = $sha.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $sha.Dispose()
    }
}

function Get-DotEnvValues {
    param([string] $Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $values }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        if ($t -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
            $val = $matches[2].Trim()
            if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and $val[0] -in @("'", '"')) {
                $val = $val.Substring(1, $val.Length - 2)
            }
            $values[$matches[1]] = $val
        }
    }
    return $values
}

function Get-HardwareInfo {
    $info = [ordered]@{}
    $cpu = @()
    try {
        $cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { "$($_.Name) ($($_.NumberOfCores)) cores" } | Where-Object { $_ })
    } catch { }
    $info.cpu = $cpu
    $gpu = @()
    $driver = @()
    try {
        $gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name } | Where-Object { $_ })
        $driver = @(Get-CimInstance Win32_VideoController | ForEach-Object { "$($_.Name) driver $($_.DriverVersion)" } | Where-Object { $_ })
    } catch { }
    $info.gpu = $gpu
    $info.gpu_driver = $driver
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $info.windows = "$($os.Caption) $($os.Version) build $($os.BuildNumber)"
    } catch {
        $info.windows = "unknown"
    }
    $wsl = ""
    if (Get-Command wsl -ErrorAction SilentlyContinue) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $wslVersion = wsl -l -v 2>$null
            if ($LASTEXITCODE -eq 0) { $wsl = ((@($wslVersion) -join "`n") -replace "`0", "").Trim() }
        } catch { }
        finally { $ErrorActionPreference = $previousErrorActionPreference }
    }
    $info.wsl = $wsl
    return $info
}

function Write-ProfileResolved {
    param([string] $EvidenceDir, $Profile, [string] $ServerPort = "")
    $resolved = [ordered]@{
        profile = $Profile.name
        schema_version = $Profile.schema_version
        description = $Profile.description
        run_kind = $Profile.run_kind
        model = $Profile.model
        adapter = $Profile.adapter
        engine = $Profile.engine
        variant = $Profile.variant
        expected_pages = $Profile.expected_pages
        max_pages = $Profile.max_pages
        prediction_dir = $Profile.prediction_dir
        prediction_manifest = $Profile.prediction_manifest
        windows_scoring_config = $Profile.windows_scoring_config
        wsl_cdm_config = $Profile.wsl_cdm_config
        score_save_name = $Profile.score_save_name
        server_port = $Profile.server_port
        resolved_server_port = $(if ($ServerPort) { $ServerPort } else { $Profile.server_port })
        minimum_prediction_coverage = $Profile.minimum_prediction_coverage
        maximum_failed_pages = $Profile.maximum_failed_pages
        require_gpu_backend_proof = $Profile.require_gpu_backend_proof
        require_wsl_cdm = $Profile.require_wsl_cdm
        metric_thresholds = $Profile.metric_thresholds
        evidence_dir = $Profile.EvidenceDir
        prediction_dir_abs = $Profile.PredictionDirAbs
        manifest_abs = $Profile.ManifestAbs
        state_file = $Profile.StateFile
    }
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "profile.resolved.json") -Value $resolved
    return $resolved
}

function Write-HardwareJson {
    param([string] $EvidenceDir)
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "hardware.json") -Value (Get-HardwareInfo)
}

function Get-MetricResultValue {
    param($Json, [string] $Path)
    # Path like "table.all.TEDS.all"; returns $null when any segment is missing.
    $node = $Json
    foreach ($segment in ($Path -split "\.")) {
        if ($null -eq $node) { return $null }
        if ($node -isnot [System.Management.Automation.PSCustomObject]) { return $null }
        $prop = $node.PSObject.Properties[$segment]
        if ($null -eq $prop) { return $null }
        $node = $prop.Value
    }
    return $node
}

function Get-TableTedsPageAvg {
    param([string] $ResultBase)
    # Per-page official aggregation: mean over pages of the mean per-table TEDS
    # on that page. This is the aggregation convention of OmniDocBench's
    # official leaderboard/notebook and differs from the pooled table.all.TEDS.
    $perTable = "$ResultBase" -replace "metric_result\.json$", "table_per_table_TEDS.json"
    if (-not (Test-Path -LiteralPath $perTable -PathType Leaf)) { return $null }
    try {
        $tables = Get-Content -Raw -Encoding UTF8 -LiteralPath $perTable | ConvertFrom-Json
        $byPage = @{}
        foreach ($prop in $tables.PSObject.Properties) {
            $page = $prop.Name.Split("_[")[0]
            $teds = $prop.Value.PSObject.Properties["TEDS"]
            if ($null -eq $teds) { continue }
            $value = $teds.Value
            if (-not $byPage.ContainsKey($page)) { $byPage[$page] = New-Object System.Collections.Generic.List[double] }
            $byPage[$page].Add([double]$value)
        }
        $pageMeans = New-Object System.Collections.Generic.List[double]
        foreach ($key in @($byPage.Keys)) { $pageMeans.Add(($byPage[$key] | Measure-Object -Average).Average) }
        if ($pageMeans.Count -eq 0) { return $null }
        return [math]::Round(($pageMeans | Measure-Object -Average).Average, 10)
    } catch {
        return $null
    }
}

function Write-MetricsSummary {
    param([string] $EvidenceDir, [string] $WindowsResult, [string] $WslResult, [string] $SaveName)
    # Canonical metrics schema (scripts/docs: canonical metrics): every value is
    # raw 0-1 scale and the aggregation path is explicit -- pooled TEDS is never
    # conflated with the official page-level TEDS aggregation.
    $summary = [ordered]@{
        schema_version = 1
        text_edit_distance_page_avg = $null
        reading_order_edit_distance_page_avg = $null
        table_teds_pooled = $null
        table_teds_page_avg = $null
        formula_cdm = $null
        official_overall = $null
        raw_scale = $true
        sources = [ordered]@{ windows = $null; wsl_cdm = $null }
    }
    $winEntry = [ordered]@{ path = $WindowsResult; present = $false }
    if (Test-Path -LiteralPath $WindowsResult -PathType Leaf) {
        try {
            $json = Get-Content -Raw -Encoding UTF8 -LiteralPath $WindowsResult | ConvertFrom-Json
            $winEntry.present = $true
            $winEntry.text_block_edit_dist = Get-MetricResultValue $json "text_block.all.Edit_dist.ALL_page_avg"
            $winEntry.reading_order_edit_dist = Get-MetricResultValue $json "reading_order.all.Edit_dist.ALL_page_avg"
            $winEntry.table_teds_pooled = Get-MetricResultValue $json "table.all.TEDS.all"
            $winEntry.page_count = Get-MetricResultValue $json "match_debug.page_count"
            $summary.text_edit_distance_page_avg = $winEntry.text_block_edit_dist
            $summary.reading_order_edit_distance_page_avg = $winEntry.reading_order_edit_dist
            $summary.table_teds_pooled = $winEntry.table_teds_pooled
            # Prefer the scorer's own page-level node (table.page.TEDS.ALL);
            # fall back to the per-table sidecar aggregation when absent.
            $inPage = Get-MetricResultValue $json "table.page.TEDS.ALL"
            if ($null -ne $inPage) {
                $summary.table_teds_page_avg = $inPage
            } else {
                $summary.table_teds_page_avg = Get-TableTedsPageAvg -ResultBase $WindowsResult
            }
        } catch {
            $winEntry.error = $_.Exception.Message
        }
        $summary.sources.windows = $winEntry
    }
    $wslEntry = [ordered]@{ path = $WslResult; present = $false }
    if (Test-Path -LiteralPath $WslResult -PathType Leaf) {
        try {
            $json = Get-Content -Raw -Encoding UTF8 -LiteralPath $WslResult | ConvertFrom-Json
            $wslEntry.present = $true
            $cdm = Get-MetricResultValue $json "display_formula.all.CDM.all"
            $wslEntry.formula_cdm = $cdm
            $wslEntry.page_count = Get-MetricResultValue $json "match_debug.page_count"
            $wslEntry.table_teds_pooled = Get-MetricResultValue $json "table.all.TEDS.all"
            $wslEntry.table_teds_page_avg = Get-MetricResultValue $json "table.page.TEDS.ALL"
            $summary.formula_cdm = $cdm
        } catch {
            $wslEntry.error = $_.Exception.Message
        }
        $summary.sources.wsl_cdm = $wslEntry
    }
    # official_overall = (text accuracy + CDM + page-level TEDS) / 3, the
    # documented README aggregate; text accuracy = (1 - edit dist).
    if ($null -ne $summary.text_edit_distance_page_avg -and
        $null -ne $summary.formula_cdm -and
        $null -ne $summary.table_teds_page_avg) {
        $summary.official_overall = [math]::Round(
            ((1.0 - [double]$summary.text_edit_distance_page_avg) +
             [double]$summary.formula_cdm +
             [double]$summary.table_teds_page_avg) / 3.0, 10)
    }
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "metrics-summary.json") -Value $summary
    return $summary
}

function Write-Report {
    param(
        [string] $EvidenceDir,
        $State,
        $Profile,
        $Fingerprint,
        [string] $ResumeCommand,
        [string] $ServerPort = "",
        [string] $PredictionTreeHash = ""
    )
    $stages = @($State.stages | Where-Object { $_.status -eq "passed" })
    $failed = @($State.stages | Where-Object { $_.status -eq "failed" })
    $totalSeconds = 0.0
    foreach ($stage in $stages) {
        if ($null -ne $stage.duration_seconds) { $totalSeconds += [double]$stage.duration_seconds }
    }
    $lines = @()
    $lines += "# Reproduction report: $($Profile.name)"
    $lines += ""
    $lines += "- Profile schema: v$($Profile.schema_version) ($($Profile.run_kind), $($Profile.variant) backend)"
    $lines += "- Model: $($Profile.model) ($($Profile.engine) engine)"
    $lines += "- Repo commit: $($State.repo_commit) (dirty: $($Fingerprint.repo_tree_sha256.dirty))"
    $lines += "- Upstream lock sha256: $($Fingerprint.inputs.upstream_lock_sha256)"
    $lines += "- Prediction dir: $($Profile.prediction_dir)"
    $lines += "- Manifest: $($Profile.prediction_manifest)"
    $lines += "- Score save name: $($Profile.score_save_name)"
    $lines += "- Server port (resolved): $(if ($ServerPort) { $ServerPort } else { $Profile.server_port })"
    if ($PredictionTreeHash) { $lines += "- Prediction tree sha256: $PredictionTreeHash" }
    $lines += "- Started: $($State.started_at)"
    if ($State.completed_at) { $lines += "- Completed: $($State.completed_at)" }
    $lines += "- Total stage time: $([math]::Round($totalSeconds, 1))s"
    $lines += "- Status: $($State.status)"
    $lines += ""
    $lines += "## Stages"
    $lines += ""
    foreach ($stage in $State.stages) {
        $lines += "- $($stage.id) [$($stage.status)] $($stage.duration_seconds)s"
        if ($stage.error) { $lines += "    error: $($stage.error)" }
    }
    $lines += ""
    $lines += "## Verdict"
    $lines += ""
    if ($State.status -eq "passed" -and $failed.Count -eq 0) {
        $lines += "PASS: all stages completed; scores within profile thresholds."
    } elseif ($State.status -eq "failed") {
        $lines += "FAIL: see stage errors above."
    } else {
        $lines += "INCOMPLETE: status=$($State.status). Resume with:"
        $lines += ""
        $lines += "    $ResumeCommand"
    }
    $lines += ""
    $lines += "## Reproduce"
    $lines += ""
    $lines += "    powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile $($Profile.name)"
    $lines += ""
    $lines += "## Resume"
    $lines += ""
    $lines += "    $ResumeCommand"
    $reportPath = Join-Path $EvidenceDir "report.md"
    New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($reportPath, $lines, $utf8NoBom)
    return $reportPath
}

function Get-WslResultPath {
    param([string] $SaveName, [string] $RepoRoot, [string] $FileSuffix = "_metric_result.json")
    # Test-only override (fake integration harness): REPRO_WSL_RESULT_DIR points
    # at a local dir standing in for the WSL UNC share; the formal path always
    # resolves the active Ubuntu2204 user's $HOME and builds the UNC path to the
    # WSL-scored metric result (or its provenance sidecar). Used by scoring and
    # evidence stages so the WSL result location is derived in exactly one place.
    $override = $env:REPRO_WSL_RESULT_DIR
    if ($override) { return Join-Path $override "${SaveName}${FileSuffix}" }
    $wslHome = ""
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $wslHome = ((@(wsl -d Ubuntu2204 -- sh -lc 'printf %s "$HOME"' 2>$null) -join "") -replace "`0", "").Trim()
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if (-not $wslHome) { $wslHome = "/root" }
    return "\\wsl$\Ubuntu2204" + ($wslHome -replace "/", "\") + "\OmniDocBench\result\${SaveName}${FileSuffix}"
}

function Get-WslResultDir {
    param([string] $SaveName)
    $resultPath = Get-WslResultPath -SaveName $SaveName
    return Split-Path -Parent $resultPath
}

function Write-ArtifactHashes {
    param(
        [string] $EvidenceDir,
        $Profile,
        [string] $PipelineCheckout,
        [string] $EnvFile,
        [string] $ServerPort = "",
        [string] $PredictionTreeFile = "",
        [string] $PredictionSummaryFile = "",
        [string] $BackendProofFile = "",
        [string] $WindowsResult = "",
        [string] $WindowsProvenanceFile = "",
        [string] $WslResult = "",
        [string] $WslProvenanceFile = "",
        [string] $StateFile = "",
        [string] $ReportFile = "",
        [string] $ProfileResolvedFile = ""
    )
    $hashes = [ordered]@{}
    $hashes.profile_file = Get-FileSha256 $Profile.ProfilePath
    $hashes.profile_resolved = Get-FileSha256 $ProfileResolvedFile
    $hashes.upstream_lock = Get-FileSha256 (Join-Path $script:ReproRoot "upstream-lock.json")
    $hashes.prediction_manifest = Get-FileSha256 $Profile.ManifestAbs
    $hashes.windows_scoring_config = Get-FileSha256 $Profile.ConfigWindowsAbs
    $hashes.wsl_cdm_config = Get-FileSha256 $Profile.ConfigWslAbs
    $hashes.pipeline_checkout_commit = $null
    if (Test-Path -LiteralPath (Join-Path $PipelineCheckout ".git")) {
        $commit = (& git -C $PipelineCheckout rev-parse HEAD 2>$null).Trim()
        if ($LASTEXITCODE -eq 0) { $hashes.pipeline_checkout_commit = $commit }
    }
    $hashes.resolved_server_port = $(if ($ServerPort) { $ServerPort } else { $Profile.server_port })
    $envValues = Get-DotEnvValues -Path $EnvFile
    $hashes.vlm_model = $null
    $hashes.vlm_mmproj = $null
    $hashes.layout_model = $null
    $hashes.server_exe = $null
    if ($envValues["PADDLEOCR_VL_GGUF"]) { $hashes.vlm_model = Get-FileSha256 $envValues["PADDLEOCR_VL_GGUF"] }
    if ($envValues["PADDLEOCR_VL_MMPROJ"]) { $hashes.vlm_mmproj = Get-FileSha256 $envValues["PADDLEOCR_VL_MMPROJ"] }
    if ($envValues["PP_DOCLAYOUTV3_ONNX_DIR"]) { $hashes.layout_model = Get-FileSha256 $envValues["PP_DOCLAYOUTV3_ONNX_DIR"] }
    if ($envValues["LLAMA_SERVER_EXE"]) { $hashes.server_exe = Get-FileSha256 $envValues["LLAMA_SERVER_EXE"] }
    $hashes.prediction_tree = Get-FileSha256 $PredictionTreeFile
    $hashes.run_stats = $null
    if (Test-Path -LiteralPath (Join-Path $Profile.PredictionDirAbs "_run_stats.json") -PathType Leaf) {
        $hashes.run_stats = Get-FileSha256 (Join-Path $Profile.PredictionDirAbs "_run_stats.json")
    }
    $hashes.strict_prediction_summary = Get-FileSha256 $PredictionSummaryFile
    $hashes.backend_proof = Get-FileSha256 $BackendProofFile
    $hashes.windows_metric_result = Get-FileSha256 $WindowsResult
    $hashes.windows_metric_provenance = Get-FileSha256 $WindowsProvenanceFile
    $hashes.wsl_metric_result = Get-FileSha256 $WslResult
    $hashes.wsl_metric_provenance = Get-FileSha256 $WslProvenanceFile
    $hashes.state_json = Get-FileSha256 $StateFile
    $hashes.report_md = Get-FileSha256 $ReportFile
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "artifact-hashes.json") -Value $hashes
    return $hashes
}

<#
.SYNOPSIS
Write the <save>_metric_result.provenance.json sidecar for a scored result.

.DESCRIPTION
scripts/metric_provenance.py is the single implementation of the sidecar
schema; this function only wires the orchestrator inputs. The sidecar binds
the result to the exact prediction tree, manifest, config, scorer checkout and
scoring-code tree it was produced from.
#>
function Write-MetricProvenance {
    param(
        [string] $Python,
        [string] $ScriptRoot,
        $Artifacts,
        [ValidateSet("windows", "wsl")]
        [string] $Platform,
        [string] $ConfigPath,
        [string] $PredictionTreeHash,
        [string] $ScorerCheckout,
        [string] $ScoringCodeDir,
        [int] $ExpectedPages,
        [string] $AggregationMode = "teds_pooled_edit_dist_page_avg"
    )
    $result = if ($Platform -eq "windows") { $Artifacts.WindowsResult } else { $Artifacts.WslResult }
    $out = if ($Platform -eq "windows") { $Artifacts.WindowsProvenance } else { $Artifacts.WslProvenance }
    if (-not (Test-Path -LiteralPath $result -PathType Leaf)) {
        throw "Cannot write provenance for missing $Platform metric result: $result"
    }
    $args = @(
        "write",
        "--result", $result,
        "--out", $out,
        "--prediction-tree", $PredictionTreeHash,
        "--manifest", $Artifacts.Manifest,
        "--config", $ConfigPath,
        "--scorer-checkout", $ScorerCheckout,
        "--scoring-code-dir", $ScoringCodeDir,
        "--expected-pages", "$ExpectedPages",
        "--save-name", $Artifacts.SaveName,
        "--aggregation-mode", $AggregationMode,
        "--platform", $Platform
    )
    & $Python (Join-Path $ScriptRoot "scripts\metric_provenance.py") @args
    if ($LASTEXITCODE -ne 0) { throw "metric provenance write failed for $Platform" }
}

<#
.SYNOPSIS
Resume guard: is a previously scored result still valid for reuse?

.DESCRIPTION
Verifies the stored sidecar against the CURRENT prediction tree hash, manifest
bytes, scoring config bytes and the result file's own bytes. Returns $true only
when every binding still matches; a missing or stale sidecar returns $false so
the caller invalidates the scoring stage and re-runs it.
#>
function Test-MetricProvenanceValid {
    param(
        [string] $Python,
        [string] $ScriptRoot,
        $Artifacts,
        [ValidateSet("windows", "wsl")]
        [string] $Platform,
        [string] $ConfigPath,
        [string] $PredictionTreeHash,
        [string] $ScorerCheckout,
        [string] $ScoringCodeDir,
        [int] $ExpectedPages
    )
    $result = if ($Platform -eq "windows") { $Artifacts.WindowsResult } else { $Artifacts.WslResult }
    $out = if ($Platform -eq "windows") { $Artifacts.WindowsProvenance } else { $Artifacts.WslProvenance }
    $args = @(
        "verify",
        "--result", $result,
        "--out", $out,
        "--prediction-tree", $PredictionTreeHash,
        "--manifest", $Artifacts.Manifest,
        "--config", $ConfigPath,
        "--scorer-checkout", $ScorerCheckout,
        "--scoring-code-dir", $ScoringCodeDir,
        "--expected-pages", "$ExpectedPages",
        "--save-name", $Artifacts.SaveName,
        "--platform", $Platform
    )
    & $Python (Join-Path $ScriptRoot "scripts\metric_provenance.py") @args 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}
