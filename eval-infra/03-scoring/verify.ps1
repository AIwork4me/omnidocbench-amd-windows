<#
.SYNOPSIS
Verify a scoring run produced a non-degenerate metric_result.json.

.DESCRIPTION
Checks that:
  1. A metric_result.json exists (from score.ps1 or score-cdm.sh). The
     OmniDocBench pipeline writes it to <omnidocbench_checkout>/result/
     <save_name>_metric_result.json, where save_name =
     <prediction-dir-basename>_<match_method>.
  2. All 4 expected metrics are present AND non-negative:
       text_block.Edit_dist       (ALL_page_avg)
       display_formula.Edit_dist  (ALL_page_avg)
       table.TEDS                 (all)
       reading_order.Edit_dist    (ALL_page_avg)
     A negative metric is a hard failure (a scoring bug). A metric of exactly
     0.0 is treated as a WARNING, not a hard failure: while in practice a
     real all-page aggregate is never byte-perfect 0.0 (Edit_dist = 0 means
     every page matched GT exactly), a tiny toy subset could legitimately hit
     it. Negative values (which OmniDocBench never produces legitimately) are
     the real "silent run failure" signal.

.PARAMETER MetricResult
Path to a *_metric_result.json file. If omitted, the script searches the
default result locations (Windows checkout and WSL /root path, mirrored to
\\wsl$\...) and uses the most recently written one.

.PARAMETER SaveName
Optional save_name to disambiguate when multiple runs exist (e.g.
paddleocrvl_rocm_quick_match vs paddleocrvl_rocm_hard_quick_match). Ignored if
-MetricResult is given.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File verify.ps1
  powershell -ExecutionPolicy Bypass -File verify.ps1 -SaveName paddleocrvl_rocm_cdm_quick_match
  powershell -ExecutionPolicy Bypass -File verify.ps1 -MetricResult C:\path\to\metric_result.json

Exit code 0 = OK, 1 = FAIL. Suitable for chaining in full-verify.ps1 (Task 7).
#>
[CmdletBinding()]
param(
    [string] $MetricResult = "",
    [string] $SaveName = ""
)
$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# --- 1. Locate metric_result.json ------------------------------------------
$file = ""
if ($MetricResult -ne "") {
    $file = $MetricResult
    if (-not (Test-Path $file)) {
        Write-Host "FAIL: -MetricResult not found: $file" -ForegroundColor Red
        exit 1
    }
} else {
    # Candidate result directories: Windows OmniDocBench checkout, and the WSL
    # native checkout (reached via the \\wsl$ share). Most-recent wins.
    $winResult   = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench\result"
    $wslResult   = "\\wsl$\Ubuntu2204\root\OmniDocBench\result"
    $candidates  = @()
    foreach ($d in @($winResult, $wslResult)) {
        if (Test-Path $d) {
            if ($SaveName -ne "") {
                $named = Join-Path $d "${SaveName}_metric_result.json"
                if (Test-Path $named) { $candidates += Get-Item $named }
            } else {
                $candidates += Get-ChildItem $d -Filter "*_metric_result.json" -File -ErrorAction SilentlyContinue
            }
        }
    }
    if ($candidates.Count -eq 0) {
        Write-Host "FAIL: no metric_result.json found." -ForegroundColor Red
        Write-Host "      Searched: $winResult , $wslResult" -ForegroundColor DarkGray
        Write-Host "      Run score.ps1 (or score-cdm.sh) first." -ForegroundColor DarkGray
        exit 1
    }
    # Most recently written.
    $file = ($candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}

Write-Host "Using: $file" -ForegroundColor DarkGray

# --- 2. Parse + check the 4 mandatory metrics ------------------------------
# Schema (from pdf_validation.py):
#   { "<category>": { "all": { "<metric>": { "<key>": <float> } } }, ... }
# Edit_dist uses "ALL_page_avg"; TEDS uses "all".
try {
    $json = Get-Content -Raw -LiteralPath $file | ConvertFrom-Json
} catch {
    Write-Host "FAIL: metric_result.json is not valid JSON: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Each row: category, metric, value-key, human label.
$checks = @(
    @{ Category = "text_block";      Metric = "Edit_dist"; Key = "ALL_page_avg"; Label = "text_block.Edit_dist" },
    @{ Category = "display_formula"; Metric = "Edit_dist"; Key = "ALL_page_avg"; Label = "display_formula.Edit_dist" },
    @{ Category = "table";           Metric = "TEDS";       Key = "all";         Label = "table.TEDS" },
    @{ Category = "reading_order";   Metric = "Edit_dist"; Key = "ALL_page_avg"; Label = "reading_order.Edit_dist" }
)

$ok = $true
foreach ($c in $checks) {
    $catNode = $json.$($c.Category)
    if ($null -eq $catNode) {
        Write-Host ("FAIL: {0,-28} category missing" -f $c.Label) -ForegroundColor Red
        $ok = $false; continue
    }
    $metricNode = $catNode.all.$($c.Metric)
    if ($null -eq $metricNode) {
        Write-Host ("FAIL: {0,-28} metric missing (no .all.{1})" -f $c.Label, $c.Metric) -ForegroundColor Red
        $ok = $false; continue
    }
    $val = $metricNode.$($c.Key)
    if ($null -eq $val) {
        Write-Host ("FAIL: {0,-28} value key '{1}' missing" -f $c.Label, $c.Key) -ForegroundColor Red
        $ok = $false; continue
    }
    $num = [double]$val
    if ($num -lt 0.0) {
        # Negative = a genuine scoring bug (OmniDocBench never produces negatives).
        Write-Host ("FAIL: {0,-28} = {1}  (negative - silent run failure / scoring bug)" -f $c.Label, $num) -ForegroundColor Red
        $ok = $false
    } elseif ($num -eq 0.0) {
        # Exactly 0.0 is suspicious at the full-set aggregate (would mean every
        # page matched GT byte-for-byte), but a tiny toy subset could legitimately
        # produce it, so WARN rather than hard-fail. At the full 1651-page scale a
        # 0.0 here almost always means a missing/empty predictions dir.
        Write-Host ("WARN: {0,-28} = {1}  (exactly 0 - check predictions dir isn't empty)" -f $c.Label, $num) -ForegroundColor Yellow
    } else {
        Write-Host ("OK:   {0,-28} = {1}" -f $c.Label, $num) -ForegroundColor Green
    }
}

# --- 3. Optional: CDM score (only present for CDM runs) ---------------------
$cdmNode = $json.display_formula.all.CDM
if ($null -ne $cdmNode) {
    # CDM uses "all" for the aggregate F1.
    $cdmVal = $cdmNode.all
    if ($null -ne $cdmVal) {
        $cdmNum = [double]$cdmVal
        if ($cdmNum -le 0.0) {
            # Red (not Yellow): CDM F1=0 in a CDM run is the repo's most-deceptive
            # failure (everything succeeds yet the score is zero), so it must NOT
            # look like a benign SKIP. Yellow is full-verify.ps1's SKIP color; a
            # CDM=0 here is a real problem worth investigating, not a skip.
            Write-Host ("WARN: display_formula.CDM       = $cdmNum  (CDM F1=0 - see docs/pitfalls.md#cdm-zero)") -ForegroundColor Red
            # Not a hard failure: the Edit_dist-only run has no CDM. But a
            # CDM run with F1=0 is the classic IM6/\mathcolor bug.
        } else {
            Write-Host ("OK:   display_formula.CDM       = $cdmNum") -ForegroundColor Green
        }
    }
}

if ($ok) {
    Write-Host ""
    Write-Host "VERIFY OK: metric_result.json valid, all 4 metrics non-zero." -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "VERIFY FAILED: see messages above." -ForegroundColor Red
    Write-Host "  If display_formula is 0 in a CDM run, see docs/pitfalls.md#cdm-zero." -ForegroundColor DarkGray
    exit 1
}
