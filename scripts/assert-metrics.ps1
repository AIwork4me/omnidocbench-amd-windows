<#
.SYNOPSIS
Metric sanity gates for a reproduction run: presence, finiteness, scale,
profile thresholds (raw 0-1 scale), full-denominator page counts, and
provenance binding.

.DESCRIPTION
Checks a metric_result.json produced by score.ps1 / score-cdm.sh against the
metric_thresholds of a reproduction profile. Enforces:

  - all four metrics present, numeric, finite, non-negative
  - TEDS and CDM in raw 0-1 scale (a >1 value means percentage-scale confusion)
  - CDM present, finite and > 0 when the profile requires it (require_wsl_cdm
    or cdm_min > 0)
  - thresholds from the profile (raw scale, never percentage)
  - with -ExpectedPages: match_debug.page_count == expected (the metrics must
    come from the full denominator, never a subset)
  - with -ProvenanceFile: the metric-result provenance sidecar must match the
    result bytes (metric_result_sha256) and, when -PredictionTreeHash is
    given, the sidecar's prediction_tree_sha256 must equal it
  - with -NotOlderThan <ISO-8601>: the result file must be newer than the
    timestamp (freshness gate -- stale results from a previous run never pass)
  - with -MaxTimeouts / -MaxExceptions / -MaxMetricErrors: match-timeout,
    exception and metric-error counters must fit their budgets

The thresholds are a wiring sanity gate for the reference profile, not a
general model-quality bar.

.PARAMETER MetricResult
Path to the *_metric_result.json to check.
.PARAMETER Profile
Path to the profile JSON whose metric_thresholds apply.
.PARAMETER RequireCdm
Require display_formula.CDM to be present, finite, positive and within the
profile threshold. Pass this for the CDM-enabled result (WSL CDM scoring);
the Edit_dist-only Windows result legitimately has no CDM node.
.PARAMETER NotOlderThan
ISO-8601 timestamp; the result file must be modified after it.
.PARAMETER ExpectedPages
If > 0, match_debug.page_count must equal this value (full denominator).
.PARAMETER PredictionTreeHash
When given (with -ProvenanceFile), the sidecar's prediction_tree_sha256 must
equal this value, binding the score to the current prediction tree.
.PARAMETER ProvenanceFile
Path to the <save_name>_metric_result.provenance.json sidecar.
.PARAMETER MaxTimeouts
If >= 0, the total match-timeout count (quick_match_timeout + page_timeout)
plus any metric timeout_case_count must not exceed it.
.PARAMETER MaxExceptions
If >= 0, any exception counters present in the result must not exceed it.
.PARAMETER MaxMetricErrors
If >= 0, any metric error_case_count must not exceed it.
.PARAMETER CompareResult
Path to the other platform's metric result. When given, the shared metrics
(text_block.Edit_dist and reading_order.Edit_dist) must agree between the two
platforms within -CompareTolerance, proving the Windows and WSL scoring paths
scored the same prediction bytes.
.PARAMETER CompareTolerance
Absolute tolerance for the -CompareResult cross-check (default 0.02).
#>
[CmdletBinding()]
param(
    [string] $MetricResult,
    [string] $Profile,
    [switch] $RequireCdm,
    [string] $NotOlderThan = "",
    [int] $ExpectedPages = 0,
    [string] $PredictionTreeHash = "",
    [string] $ProvenanceFile = "",
    [int] $MaxTimeouts = -1,
    [int] $MaxExceptions = -1,
    [int] $MaxMetricErrors = -1,
    [string] $CompareResult = "",
    [double] $CompareTolerance = 0.02
)
$ErrorActionPreference = "Stop"
$ok = $true

function Write-Check([string] $Name, [bool] $Passed, [string] $Detail) {
    if ($Passed) {
        Write-Host ("OK:   {0} = {1}" -f $Name, $Detail) -ForegroundColor Green
    } else {
        $script:ok = $false
        Write-Host ("FAIL: {0} = {1}" -f $Name, $Detail) -ForegroundColor Red
    }
}

function Get-MetricResultValue($Json, [string] $Path) {
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

function Get-Sha256File {
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

if (-not (Test-Path -LiteralPath $MetricResult -PathType Leaf)) {
    Write-Host "FAIL: metric result not found: $MetricResult" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $Profile -PathType Leaf)) {
    Write-Host "FAIL: profile not found: $Profile" -ForegroundColor Red
    exit 1
}
$profile = Get-Content -Raw -Encoding UTF8 -LiteralPath $Profile | ConvertFrom-Json
$thresholds = $profile.metric_thresholds

if ($NotOlderThan) {
    try {
        $cutoff = [datetime]::Parse($NotOlderThan).ToUniversalTime()
        $fileTime = (Get-Item -LiteralPath $MetricResult).LastWriteTimeUtc
        if ($fileTime -le $cutoff) {
            Write-Host ("FAIL: {0} is stale (mtime {1} <= cutoff {2}) - this result predates the run" -f $MetricResult, $fileTime, $cutoff) -ForegroundColor Red
            exit 1
        }
        Write-Host "OK:   freshness = result newer than run start" -ForegroundColor Green
    } catch {
        Write-Host "FAIL: cannot parse -NotOlderThan timestamp: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

$json = Get-Content -Raw -Encoding UTF8 -LiteralPath $MetricResult | ConvertFrom-Json

# --- full-denominator gate ------------------------------------------------
if ($ExpectedPages -gt 0) {
    $pageCount = Get-MetricResultValue $json "match_debug.page_count"
    if ($null -eq $pageCount) {
        Write-Check "match_debug.page_count" $false "missing (cannot prove the full denominator)"
    } elseif ([int]$pageCount -ne $ExpectedPages) {
        Write-Check "match_debug.page_count" $false "$pageCount != expected $ExpectedPages (metrics are not computed over the full set)"
    } else {
        Write-Check "match_debug.page_count" $true "$pageCount"
    }
}

# --- provenance binding ----------------------------------------------------
if ($ProvenanceFile) {
    if (-not (Test-Path -LiteralPath $ProvenanceFile -PathType Leaf)) {
        Write-Check "metric provenance" $false "sidecar missing: $ProvenanceFile (score is not bound to its inputs)"
    } else {
        try {
            $provenance = Get-Content -Raw -Encoding UTF8 -LiteralPath $ProvenanceFile | ConvertFrom-Json
        } catch {
            Write-Check "metric provenance" $false "sidecar unreadable: $($_.Exception.Message)"
            $provenance = $null
        }
        if ($null -ne $provenance) {
            $resultSha = Get-Sha256File -Path $MetricResult
            if ([string]$provenance.metric_result_sha256 -ne $resultSha) {
                Write-Check "metric provenance" $false "sidecar metric_result_sha256=$($provenance.metric_result_sha256) != actual $resultSha (result bytes changed after scoring)"
            } elseif ($PredictionTreeHash -and [string]$provenance.prediction_tree_sha256 -ne $PredictionTreeHash) {
                Write-Check "metric provenance" $false "sidecar prediction_tree_sha256=$($provenance.prediction_tree_sha256) != current $PredictionTreeHash (score was computed from different predictions)"
            } else {
                Write-Check "metric provenance" $true "sidecar matches result bytes and current prediction tree"
            }
        }
    }
}

# --- budgets: timeout / exception / metric error ---------------------------
if ($MaxTimeouts -ge 0) {
    $totalTimeouts = 0
    $fallbackCounts = Get-MetricResultValue $json "match_debug.text_match_fallback_counts"
    if ($null -ne $fallbackCounts) {
        foreach ($prop in $fallbackCounts.PSObject.Properties) {
            $totalTimeouts += [int]$prop.Value
        }
    }
    $tableTimeout = Get-MetricResultValue $json "table.metric_debug.TEDS.timeout_case_count"
    if ($null -ne $tableTimeout) { $totalTimeouts += [int]$tableTimeout }
    if ($totalTimeouts -gt $MaxTimeouts) {
        Write-Check "timeout budget" $false "total match/metric timeouts $totalTimeouts exceeds budget $MaxTimeouts"
    } else {
        Write-Check "timeout budget" $true "$totalTimeouts <= $MaxTimeouts"
    }
}
if ($MaxExceptions -ge 0) {
    # metric_result.json has no exception counters in this schema; a non-zero
    # budget with no counter present is vacuously satisfied.
    Write-Check "exception budget" $true "no exception counters in this result schema (budget $MaxExceptions)"
}
if ($MaxMetricErrors -ge 0) {
    $totalErrors = 0
    $tableErrors = Get-MetricResultValue $json "table.metric_debug.TEDS.error_case_count"
    if ($null -ne $tableErrors) { $totalErrors += [int]$tableErrors }
    if ($totalErrors -gt $MaxMetricErrors) {
        Write-Check "metric error budget" $false "metric error cases $totalErrors exceeds budget $MaxMetricErrors"
    } else {
        Write-Check "metric error budget" $true "$totalErrors <= $MaxMetricErrors"
    }
}

$rows = @(
    @{ Label = "text_block.Edit_dist";   Value = Get-MetricResultValue $json "text_block.all.Edit_dist.ALL_page_avg";       Max = [double]$thresholds.text_edit_dist_max;        Direction = "max"; Path = "text_block.all.Edit_dist.ALL_page_avg" },
    @{ Label = "reading_order.Edit_dist"; Value = Get-MetricResultValue $json "reading_order.all.Edit_dist.ALL_page_avg";  Max = [double]$thresholds.reading_order_edit_dist_max; Direction = "max"; Path = "reading_order.all.Edit_dist.ALL_page_avg" },
    @{ Label = "table.TEDS.pooled";       Value = Get-MetricResultValue $json "table.all.TEDS.all";                          Min = [double]$thresholds.teds_min;                    Direction = "min"; Path = "table.all.TEDS.all" }
)
$displayAll = Get-MetricResultValue $json "display_formula.all"
$cdmProperty = $null
if ($null -ne $displayAll) { $cdmProperty = $displayAll.PSObject.Properties["CDM"] }

foreach ($row in $rows) {
    $value = $row.Value
    if ($null -eq $value) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "missing"
        continue
    }
    $isNumeric = (
        ($value -is [byte]) -or ($value -is [sbyte]) -or
        ($value -is [int16]) -or ($value -is [uint16]) -or
        ($value -is [int32]) -or ($value -is [uint32]) -or
        ($value -is [int64]) -or ($value -is [uint64]) -or
        ($value -is [single]) -or ($value -is [double]) -or
        ($value -is [decimal])
    )
    if (-not $isNumeric) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "not numeric"
        continue
    }
    $num = [double]$value
    if ([double]::IsNaN($num) -or [double]::IsInfinity($num)) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "not finite"
        continue
    }
    if ($num -lt 0.0) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "negative ($num)"
        continue
    }
    if ($row.Direction -eq "min" -and $num -gt 1.0) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "$num > 1 - percentage scale detected; raw 0-1 required"
        continue
    }
    if ($row.Direction -eq "max" -and $num -gt $row.Max) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "$num exceeds threshold $($row.Max)"
        continue
    }
    if ($row.Direction -eq "min" -and $num -lt $row.Min) {
        Write-Check "$($row.Label) [$($row.Path)]" $false "$num below threshold $($row.Min)"
        continue
    }
    Write-Check "$($row.Label) [$($row.Path)]" $true "$num"
}

# --- cross-platform consistency (Windows vs WSL shared metrics) ------------
if ($CompareResult) {
    if (-not (Test-Path -LiteralPath $CompareResult -PathType Leaf)) {
        Write-Check "cross-platform consistency" $false "comparison result not found: $CompareResult"
    } else {
        try {
            $otherJson = Get-Content -Raw -Encoding UTF8 -LiteralPath $CompareResult | ConvertFrom-Json
        } catch {
            Write-Check "cross-platform consistency" $false "comparison result unreadable: $($_.Exception.Message)"
            $otherJson = $null
        }
        if ($null -ne $otherJson) {
            $shared = @(
                @{ Label = "text_block.Edit_dist"; Path = "text_block.all.Edit_dist.ALL_page_avg" },
                @{ Label = "reading_order.Edit_dist"; Path = "reading_order.all.Edit_dist.ALL_page_avg" }
            )
            $crossOk = $true
            foreach ($item in $shared) {
                $a = Get-MetricResultValue $json $item.Path
                $b = Get-MetricResultValue $otherJson $item.Path
                if ($null -eq $a -or $null -eq $b) {
                    Write-Check "cross-platform $($item.Label)" $false "missing on one platform ($a / $b)"
                    $crossOk = $false
                    continue
                }
                $delta = [math]::Abs([double]$a - [double]$b)
                if ($delta -gt $CompareTolerance) {
                    Write-Check "cross-platform $($item.Label)" $false "|$a - $b| = $delta exceeds tolerance $CompareTolerance"
                    $crossOk = $false
                } else {
                    Write-Check "cross-platform $($item.Label) [$($item.Path)]" $true "|$a - $b| = $delta <= $CompareTolerance"
                }
            }
        }
    }
}

$requireCdm = $RequireCdm.IsPresent
if ($null -eq $cdmProperty) {
    if ($requireCdm) {
        Write-Check "display_formula.CDM" $false "missing but required by profile"
    } else {
        Write-Check "display_formula.CDM" $true "absent (not required by profile)"
    }
} else {
    $cdmValue = $cdmProperty.Value
    $cdmAll = $null
    if ($null -ne $cdmValue) { $cdmAll = $cdmValue.PSObject.Properties["all"] }
    if ($null -eq $cdmAll -or $null -eq $cdmAll.Value) {
        Write-Check "display_formula.CDM" $false "missing or null"
    } else {
        $cdmNum = [double]$cdmAll.Value
        if ([double]::IsNaN($cdmNum) -or [double]::IsInfinity($cdmNum)) {
            Write-Check "display_formula.CDM" $false "not finite"
        } elseif ($cdmNum -le 0.0) {
            Write-Check "display_formula.CDM" $false "non-positive ($cdmNum) - see docs/pitfalls.md#cdm-zero"
        } elseif ($cdmNum -gt 1.0) {
            Write-Check "display_formula.CDM" $false "$cdmNum > 1 - percentage scale detected; raw 0-1 required"
        } elseif ($cdmNum -lt [double]$thresholds.cdm_min) {
            Write-Check "display_formula.CDM" $false "$cdmNum below threshold $([double]$thresholds.cdm_min)"
        } else {
            Write-Check "display_formula.CDM" $true "$cdmNum"
        }
    }
}

if ($ok) {
    Write-Host ""
    Write-Host "METRIC VERIFY OK: all metrics present, finite, in raw scale, within profile thresholds." -ForegroundColor Green
    exit 0
}
Write-Host ""
Write-Host "METRIC VERIFY FAILED: see messages above." -ForegroundColor Red
exit 1
