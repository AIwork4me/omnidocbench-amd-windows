<#
.SYNOPSIS
Evidence-pack helpers for reproduce.ps1 (dot-sourceable, PowerShell 5.1).

.DESCRIPTION
Atomic JSON writes and machine-hardware/artifact fingerprinting used to build
the per-profile evidence pack under outputs/reproduction/<profile>/.
This file defines functions only; it performs no work at dot-source time.
#>
if (-not $script:ReproRoot) { $script:ReproRoot = Split-Path -Parent $PSScriptRoot }

function Save-JsonAtomic {
    param([string] $Path, $Value, [int] $Depth = 12)
    $directory = Split-Path -Parent $Path
    if ($directory) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
    $temp = "$Path.tmp.$PID"
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($temp, ($Value | ConvertTo-Json -Depth $Depth), $utf8NoBom)
        Move-Item -LiteralPath $temp -Destination $Path -Force
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
    param([string] $EvidenceDir, $Profile)
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

function Write-MetricsSummary {
    param([string] $EvidenceDir, [string] $WindowsResult, [string] $WslResult, [string] $SaveName)
    $summary = [ordered]@{}
    foreach ($pair in @(@("windows", $WindowsResult), @("wsl_cdm", $WslResult))) {
        $label = $pair[0]
        $path = $pair[1]
        $entry = [ordered]@{ path = $path; present = $false }
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            try {
                $json = Get-Content -Raw -Encoding UTF8 -LiteralPath $path | ConvertFrom-Json
                $entry.present = $true
                $entry.text_block_edit_dist = $json.text_block.all.Edit_dist.ALL_page_avg
                $entry.reading_order_edit_dist = $json.reading_order.all.Edit_dist.ALL_page_avg
                $entry.table_teds = $json.table.all.TEDS.all
                $entry.formula_cdm = $null
                $cdmProp = $json.display_formula.all.PSObject.Properties["CDM"]
                if ($null -ne $cdmProp) { $entry.formula_cdm = $cdmProp.Value.all }
                $entry.page_count = $json.match_debug.page_count
            } catch {
                $entry.error = $_.Exception.Message
            }
        }
        $summary[$label] = $entry
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
        [string] $ResumeCommand
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
    $lines += "- Repo commit: $($State.repo_commit) (dirty: $($Fingerprint.repo_dirty))"
    $lines += "- Upstream lock sha256: $($Fingerprint.upstream_lock_sha256)"
    $lines += "- Prediction dir: $($Profile.prediction_dir)"
    $lines += "- Manifest: $($Profile.prediction_manifest)"
    $lines += "- Score save name: $($Profile.score_save_name)"
    $lines += "- Server port: $($Profile.server_port)"
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

function Write-PredictionSummary {
    param([string] $EvidenceDir, [string] $PredictionDir, [int] $ExpectedPages)
    $summary = [ordered]@{
        expected = $ExpectedPages
        markdown_files = 0
        valid = 0
        missing = @()
        invalid = @()
        unexpected = @()
        failed_pages = @()
        coverage = 0.0
        stats = $null
    }
    if (Test-Path -LiteralPath $PredictionDir -PathType Container) {
        $markdown = @(Get-ChildItem -LiteralPath $PredictionDir -Filter *.md -File -ErrorAction SilentlyContinue)
        $summary.markdown_files = $markdown.Count
        $valid = 0
        $invalidNames = New-Object System.Collections.Generic.List[string]
        foreach ($md in $markdown) {
            try {
                $content = [System.IO.File]::ReadAllText($md.FullName, [System.Text.Encoding]::UTF8)
                if ([string]::IsNullOrWhiteSpace($content)) { $invalidNames.Add("$($md.Name) (empty)") }
                else { $valid++ }
            } catch {
                $invalidNames.Add("$($md.Name) (not UTF-8)")
            }
        }
        $summary.valid = $valid
        $summary.invalid = @($invalidNames)
        $summary.coverage = if ($ExpectedPages -gt 0) { [math]::Round($valid / $ExpectedPages, 6) } else { 0.0 }
    }
    $statsPath = Join-Path $PredictionDir "_run_stats.json"
    if (Test-Path -LiteralPath $statsPath -PathType Leaf) {
        try {
            $summary.stats = Get-Content -Raw -Encoding UTF8 -LiteralPath $statsPath | ConvertFrom-Json
        } catch { }
    }
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "prediction-summary.json") -Value $summary
    return $summary
}

function Write-ArtifactHashes {
    param([string] $EvidenceDir, $Profile, [string] $PipelineCheckout, [string] $EnvFile)
    $hashes = [ordered]@{}
    $hashes.profile_file = Get-FileSha256 $Profile.ProfilePath
    $hashes.upstream_lock = Get-FileSha256 (Join-Path $script:ReproRoot "upstream-lock.json")
    $hashes.prediction_manifest = Get-FileSha256 $Profile.ManifestAbs
    $hashes.windows_scoring_config = Get-FileSha256 $Profile.ConfigWindowsAbs
    $hashes.wsl_cdm_config = Get-FileSha256 $Profile.ConfigWslAbs
    $hashes.pipeline_checkout_commit = $null
    if (Test-Path -LiteralPath (Join-Path $PipelineCheckout ".git")) {
        $commit = (& git -C $PipelineCheckout rev-parse HEAD 2>$null).Trim()
        if ($LASTEXITCODE -eq 0) { $hashes.pipeline_checkout_commit = $commit }
    }
    $hashes.vlm_model = $null
    $hashes.vlm_mmproj = $null
    $hashes.layout_model = $null
    $hashes.server_exe = $null
    if (Test-Path -LiteralPath $EnvFile -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $EnvFile) {
            $t = $line.Trim()
            if ($t -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
                $val = $matches[2].Trim()
                if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and $val[0] -in @("'", '"')) {
                    $val = $val.Substring(1, $val.Length - 2)
                }
                if ($matches[1] -eq "PADDLEOCR_VL_GGUF") { $hashes.vlm_model = Get-FileSha256 $val }
                elseif ($matches[1] -eq "PADDLEOCR_VL_MMPROJ") { $hashes.vlm_mmproj = Get-FileSha256 $val }
                elseif ($matches[1] -eq "LLAMA_SERVER_EXE") { $hashes.server_exe = Get-FileSha256 $val }
            }
        }
    }
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "artifact-hashes.json") -Value $hashes
    return $hashes
}

