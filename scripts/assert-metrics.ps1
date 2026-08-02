<#
.SYNOPSIS
Metric sanity gates for a reproduction run: presence, finiteness, scale, and
profile thresholds (raw 0-1 scale).

.DESCRIPTION
Checks a metric_result.json produced by score.ps1 / score-cdm.sh against the
metric_thresholds of a reproduction profile. Enforces:

  - all four metrics present, numeric, finite, non-negative
  - TEDS and CDM in raw 0-1 scale (a >1 value means percentage-scale confusion)
  - CDM present, finite and > 0 when the profile requires it (require_wsl_cdm
    or cdm_min > 0)
  - thresholds from the profile (raw scale, never percentage)
  - with -NotOlderThan <ISO-8601>: the result file must be newer than the
    timestamp (freshness gate -- stale results from a previous run never pass)

The thresholds are a wiring sanity gate for the reference profile, not a
general model-quality bar.

.PARAMETER MetricResult
Path to the *_metric_result.json to check.
.PARAMETER Profile
Path to the profile JSON whose metric_thresholds apply.
.PARAMETER NotOlderThan
ISO-8601 timestamp; the result file must be modified after it.
#>
[CmdletBinding()]
param(
    [string] $MetricResult,
    [string] $Profile,
    [string] $NotOlderThan = ""
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
$rows = @(
    @{ Label = "text_block.Edit_dist";   Value = $json.text_block.all.Edit_dist.ALL_page_avg;       Max = [double]$thresholds.text_edit_dist_max;        Direction = "max" },
    @{ Label = "reading_order.Edit_dist"; Value = $json.reading_order.all.Edit_dist.ALL_page_avg;  Max = [double]$thresholds.reading_order_edit_dist_max; Direction = "max" },
    @{ Label = "table.TEDS";             Value = $json.table.all.TEDS.all;                          Min = [double]$thresholds.teds_min;                    Direction = "min" }
)
$displayAll = $json.display_formula.all
$cdmProperty = $null
if ($null -ne $displayAll) { $cdmProperty = $displayAll.PSObject.Properties["CDM"] }

foreach ($row in $rows) {
    $value = $row.Value
    if ($null -eq $value) {
        Write-Check $row.Label $false "missing"
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
        Write-Check $row.Label $false "not numeric"
        continue
    }
    $num = [double]$value
    if ([double]::IsNaN($num) -or [double]::IsInfinity($num)) {
        Write-Check $row.Label $false "not finite"
        continue
    }
    if ($num -lt 0.0) {
        Write-Check $row.Label $false "negative ($num)"
        continue
    }
    if ($row.Direction -eq "min" -and $num -gt 1.0) {
        Write-Check $row.Label $false "$num > 1 - percentage scale detected; raw 0-1 required"
        continue
    }
    if ($row.Direction -eq "max" -and $num -gt $row.Max) {
        Write-Check $row.Label $false "$num exceeds threshold $($row.Max)"
        continue
    }
    if ($row.Direction -eq "min" -and $num -lt $row.Min) {
        Write-Check $row.Label $false "$num below threshold $($row.Min)"
        continue
    }
    Write-Check $row.Label $true "$num"
}

$requireCdm = ([bool]$profile.require_wsl_cdm) -or ([double]$thresholds.cdm_min -gt 0.0)
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
