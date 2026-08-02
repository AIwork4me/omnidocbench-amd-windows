<#
.SYNOPSIS
Reproduction profile catalog library (dot-sourceable, Windows PowerShell 5.1 compatible).

.DESCRIPTION
Loads, validates, and resolves the declarative reproduction profiles under
scripts/profiles/*.profile.json. Every loader function fails closed: any
invalid profile raises with ALL problems listed, and callers are expected to
print the valid profile names before exiting non-zero.

Resolved profiles are PSCustomObjects with the raw JSON fields plus these
machine-resolved members:
  PredictionDirAbs, ManifestAbs, ConfigWindowsAbs, ConfigWslAbs,
  EvidenceDir, StateFile, WindowsResultPath, SaveName, Port

This file defines functions only; it performs no work at dot-source time.
#>

$script:ReproRoot = Split-Path -Parent $PSScriptRoot
$script:ReproProfileDir = Join-Path $script:ReproRoot "scripts\profiles"
$script:ReproConfigDir = Join-Path $script:ReproRoot "eval-infra\01-omnidocbench\configs"

function Get-ReproProfileFiles {
    @(Get-ChildItem -LiteralPath $script:ReproProfileDir -Filter "*.profile.json" -File -ErrorAction SilentlyContinue | Sort-Object Name)
}

function Test-ReproIsAbsolutePath {
    param([string] $Value)
    return ($Value -match "^[A-Za-z]:[\\/]") -or $Value.StartsWith("/") -or $Value.StartsWith("\\")
}

function Test-ReproIsWholeNumber {
    param($Value)
    if ($null -eq $Value) { return $false }
    return ($Value -is [int]) -or ($Value -is [int16]) -or ($Value -is [int32]) -or
        ($Value -is [int64]) -or ($Value -is [long]) -or
        ($Value -is [double] -and [math]::Floor([double]$Value) -eq [double]$Value)
}

function Test-ReproIsNumber {
    param($Value)
    if ($null -eq $Value) { return $false }
    return ($Value -is [int]) -or ($Value -is [int16]) -or ($Value -is [int32]) -or
        ($Value -is [int64]) -or ($Value -is [long]) -or ($Value -is [double]) -or
        ($Value -is [single]) -or ($Value -is [decimal])
}

function Get-ReproScoringConfigBinding {
    param([string] $ConfigFile)
    if (-not (Test-Path -LiteralPath $ConfigFile -PathType Leaf)) { return $null }
    $lines = Get-Content -LiteralPath $ConfigFile
    $prediction = ""
    $groundTruth = ""
    foreach ($line in $lines) {
        if ($line -match "^\s*prediction:\s*\{\s*data_path:\s*([^}]+?)\s*\}\s*$") {
            $prediction = $matches[1].Trim()
        } elseif ($line -match "^\s*ground_truth:\s*\{\s*data_path:\s*([^}]+?)\s*\}\s*$") {
            $groundTruth = $matches[1].Trim()
        }
    }
    return [pscustomobject]@{ prediction = $prediction; ground_truth = $groundTruth }
}

function Assert-ReproProfileShape {
    param($Profile, [System.Collections.Generic.List[string]] $Errors)
    $name = [string]$Profile.name
    if ($name -eq "") { $name = "<unnamed>" }

    $requiredFields = @(
        "schema_version", "name", "description", "run_kind", "model", "adapter",
        "engine", "variant", "expected_pages", "prediction_dir", "prediction_manifest",
        "owned_manifest", "windows_scoring_config", "wsl_cdm_config", "score_save_name",
        "server_port", "minimum_prediction_coverage", "maximum_failed_pages",
        "require_gpu_backend_proof", "require_wsl_cdm", "metric_thresholds",
        "expected_runtime_class"
    )
    foreach ($field in $requiredFields) {
        if ($null -eq $Profile.PSObject.Properties[$field]) {
            $Errors.Add("${name}: missing required field '$field'")
        }
    }
    if ($null -eq $Profile.PSObject.Properties["max_pages"]) {
        $Errors.Add("${name}: missing required field 'max_pages' (use null for full runs)")
    }
    if ($Errors.Count -gt 0 -and $null -eq $Profile.PSObject.Properties["name"]) {
        return
    }
    if ($Profile.schema_version -ne 1) { $Errors.Add("${name}: schema_version must be 1") }
    if ($Profile.run_kind -notin @("smoke", "subset", "full")) { $Errors.Add("${name}: run_kind must be smoke|subset|full") }
    if ($Profile.variant -notin @("cpu", "hip")) { $Errors.Add("${name}: variant must be cpu|hip") }
    if ($Profile.engine -ne "lightweight") { $Errors.Add("${name}: engine must be lightweight") }
    if (-not (Test-ReproIsWholeNumber $Profile.expected_pages) -or $Profile.expected_pages -lt 1) {
        $Errors.Add("${name}: expected_pages must be a positive integer")
    }
    if ($Profile.run_kind -eq "full") {
        if ($Profile.expected_pages -ne 1651) { $Errors.Add("${name}: full profile must declare expected_pages = 1651") }
        if ($null -ne $Profile.max_pages) { $Errors.Add("${name}: full profile must not set max_pages") }
        if ($Profile.minimum_prediction_coverage -lt 0.998) { $Errors.Add("${name}: full profile coverage must be >= 0.998") }
        if ($Profile.maximum_failed_pages -gt 2) { $Errors.Add("${name}: full profile max failed pages must be <= 2") }
        if ($Profile.owned_manifest -ne $false) { $Errors.Add("${name}: full profile manifest is the shared locked dataset; owned_manifest must be false") }
    } elseif ($Profile.run_kind -eq "smoke") {
        if ($Profile.max_pages -ne $Profile.expected_pages) { $Errors.Add("${name}: smoke profile max_pages must equal expected_pages") }
    }
    if ($null -ne $Profile.max_pages -and (-not (Test-ReproIsWholeNumber $Profile.max_pages) -or $Profile.max_pages -lt 1)) {
        $Errors.Add("${name}: max_pages must be a positive integer or null")
    }
    if ($Profile.variant -eq "hip" -and -not $Profile.require_gpu_backend_proof) {
        $Errors.Add("${name}: HIP profile must set require_gpu_backend_proof = true")
    }
    if ($Profile.require_gpu_backend_proof -and $Profile.variant -ne "hip") {
        $Errors.Add("${name}: require_gpu_backend_proof = true requires variant hip (the backend proof only proves HIP)")
    }
    if (-not (Test-ReproIsNumber $Profile.minimum_prediction_coverage) -or
        $Profile.minimum_prediction_coverage -le 0.0 -or $Profile.minimum_prediction_coverage -gt 1.0) {
        $Errors.Add("${name}: minimum_prediction_coverage must be in (0, 1]")
    }
    if (-not (Test-ReproIsWholeNumber $Profile.maximum_failed_pages) -or $Profile.maximum_failed_pages -lt 0) {
        $Errors.Add("${name}: maximum_failed_pages must be a non-negative integer")
    }
    foreach ($field in @("prediction_dir", "prediction_manifest")) {
        $value = [string]$Profile.$field
        if ($value -eq "") { $Errors.Add("${name}: $field must not be empty") }
        elseif (Test-ReproIsAbsolutePath $value) { $Errors.Add("${name}: $field must be repo-relative (no absolute paths in committed profiles): $value") }
        elseif ($value -match "[\\]") { $Errors.Add("${name}: $field must use forward slashes") }
        elseif ($value -match "(^|/)(\.\.)(/|$)") { $Errors.Add("${name}: $field must not contain '..' path components (scoped deletion guarantee): $value") }
    }
    if ($null -ne $Profile.PSObject.Properties["metric_thresholds"] -and $null -ne $Profile.metric_thresholds) {
        foreach ($key in @("text_edit_dist_max", "reading_order_edit_dist_max", "teds_min", "cdm_min")) {
            if ($null -eq $Profile.metric_thresholds.PSObject.Properties[$key]) {
                $Errors.Add("${name}: metric_thresholds missing '$key'")
            } elseif (-not (Test-ReproIsNumber $Profile.metric_thresholds.$key) -or
                [double]$Profile.metric_thresholds.$key -lt 0.0 -or [double]$Profile.metric_thresholds.$key -gt 1.0) {
                $Errors.Add("${name}: metric_thresholds.$key must be a raw 0-1 number")
            }
        }
    } else {
        $Errors.Add("${name}: metric_thresholds must be an object")
    }
    $saveBase = ([string]$Profile.prediction_dir).TrimEnd("/").Split("/")[-1]
    if ($Profile.score_save_name -ne "$($saveBase)_quick_match") {
        $Errors.Add("${name}: score_save_name must equal <prediction-dir-basename>_quick_match")
    }
    if ([string]::IsNullOrWhiteSpace($Profile.server_port) -or $Profile.server_port -notmatch "^\d+$") {
        $Errors.Add("${name}: server_port must be a numeric string")
    }
    foreach ($field in @("windows_scoring_config", "wsl_cdm_config")) {
        $configFile = Join-Path $script:ReproConfigDir $Profile.$field
        if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
            $Errors.Add("${name}: scoring config missing: $($Profile.$field)")
            continue
        }
        $binding = Get-ReproScoringConfigBinding -ConfigFile $configFile
        if ($null -eq $binding) {
            $Errors.Add("${name}: cannot read prediction/ground_truth binding from $($Profile.$field)")
            continue
        }
        $predSuffix = "<REPO_ROOT>/$($Profile.prediction_dir)"
        if (-not $binding.prediction.EndsWith($predSuffix)) {
            $Errors.Add("${name}: $($Profile.$field) prediction.data_path does not bind to profile prediction_dir ($($binding.prediction))")
        }
        $manSuffix = "<REPO_ROOT>/$($Profile.prediction_manifest)"
        if (-not $binding.ground_truth.EndsWith($manSuffix)) {
            $Errors.Add("${name}: $($Profile.$field) ground_truth.data_path does not bind to profile manifest ($($binding.ground_truth))")
        }
    }
}

function Resolve-ReproProfile {
    param([string] $Path)
    $errors = New-Object System.Collections.Generic.List[string]
    $raw = $null
    try {
        $raw = Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
    } catch {
        throw "Profile file is not valid JSON: $Path ($($_.Exception.Message))"
    }
    if ($null -eq $raw.PSObject.Properties["name"]) {
        throw "Profile file missing 'name': $Path"
    }
    Assert-ReproProfileShape -Profile $raw -Errors $errors
    if ($errors.Count -gt 0) {
        throw "Invalid profile '$($raw.name)' ($Path):`n  " + ($errors -join "`n  ")
    }
    $predictionRel = ([string]$raw.prediction_dir) -replace "/", "\"
    $manifestRel = ([string]$raw.prediction_manifest) -replace "/", "\"
    $resolved = $raw | Add-Member -NotePropertyName "ProfilePath" -NotePropertyValue $Path -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "PredictionDirAbs" -NotePropertyValue (Join-Path $script:ReproRoot $predictionRel) -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "ManifestAbs" -NotePropertyValue (Join-Path $script:ReproRoot $manifestRel) -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "ConfigWindowsAbs" -NotePropertyValue (Join-Path $script:ReproConfigDir $raw.windows_scoring_config) -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "ConfigWslAbs" -NotePropertyValue (Join-Path $script:ReproConfigDir $raw.wsl_cdm_config) -PassThru
    $evidenceDir = Join-Path $script:ReproRoot ("outputs\reproduction\" + $raw.name)
    $resolved = $resolved | Add-Member -NotePropertyName "EvidenceDir" -NotePropertyValue $evidenceDir -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "StateFile" -NotePropertyValue (Join-Path $evidenceDir "state.json") -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "SaveName" -NotePropertyValue ([string]$raw.score_save_name) -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "Port" -NotePropertyValue ([string]$raw.server_port) -PassThru
    $resolved = $resolved | Add-Member -NotePropertyName "WindowsResultPath" -NotePropertyValue (Join-Path $script:ReproRoot ("eval-infra\01-omnidocbench\OmniDocBench\result\" + $raw.score_save_name + "_metric_result.json")) -PassThru
    return $resolved
}

function Get-ProfileCatalog {
    $profiles = @()
    $allErrors = New-Object System.Collections.Generic.List[string]
    foreach ($file in Get-ReproProfileFiles) {
        try {
            $profiles += Resolve-ReproProfile -Path $file.FullName
        } catch {
            $allErrors.Add($_.Exception.Message)
        }
    }
    if ($allErrors.Count -gt 0) {
        throw "Profile catalog validation failed:`n  " + ($allErrors -join "`n  ")
    }
    if ($profiles.Count -eq 0) {
        throw "No profiles found under $script:ReproProfileDir"
    }
    $byName = @{}
    $byDir = @{}
    $bySave = @{}
    $byPort = @{}
    foreach ($p in $profiles) {
        $name = [string]$p.name
        $dir = [string]$p.prediction_dir
        $save = [string]$p.score_save_name
        $port = [string]$p.server_port
        if ($byName.ContainsKey($name)) { throw "Duplicate profile name: $name" }
        if ($byDir.ContainsKey($dir)) { throw "Duplicate prediction_dir across profiles: $dir" }
        if ($bySave.ContainsKey($save)) { throw "Duplicate score_save_name across profiles: $save" }
        if ($byPort.ContainsKey($port)) { throw "Duplicate server_port across profiles: $port" }
        $byName[$name] = $true
        $byDir[$dir] = $true
        $bySave[$save] = $true
        $byPort[$port] = $true
    }
    return $profiles
}

function Get-ReproProfile {
    param([string] $Name)
    $profiles = @(Get-ProfileCatalog)
    foreach ($p in $profiles) {
        if ([string]$p.name -eq $Name) { return $p }
    }
    $valid = @($profiles | ForEach-Object { $_.name }) -join ", "
    throw "Unknown profile '$Name'. Valid profiles: $valid"
}

function Format-ProfileList {
    $profiles = @(Get-ProfileCatalog)
    $rows = foreach ($p in $profiles) {
        $pages = if ($null -ne $p.max_pages) { "$($p.max_pages)" } else { "$($p.expected_pages) (all)" }
        $backend = if ($p.variant -eq "hip") { "HIP (GPU)" } else { "CPU" }
        "{0,-28} {1,-9} {2,-16} {3,-9} {4}" -f $p.name, $backend, $pages, $p.run_kind, $p.expected_runtime_class
    }
    return @(
        "Available reproduction profiles (name, backend, pages, kind, expected runtime):"
        "------------------------------------------------------------------------------"
    ) + $rows
}

function Show-ResolvedProfile {
    param($Profile)
    $pages = if ($null -ne $Profile.max_pages) { "$($Profile.max_pages)" } else { "unlimited (full set)" }
    [pscustomobject]@{
        name = $Profile.name
        schema_version = $Profile.schema_version
        run_kind = $Profile.run_kind
        model = $Profile.model
        adapter = $Profile.adapter
        engine = $Profile.engine
        variant = $Profile.variant
        expected_pages = $Profile.expected_pages
        max_pages = $pages
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
    }
}
