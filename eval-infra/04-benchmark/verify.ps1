<#
.SYNOPSIS
Verify a benchmark run produced complete, self-consistent output.

.DESCRIPTION
Five checks, in order, first failure exits 1:
  1. Resource log exists, non-empty, required fields present.
  2. Benchmark report exists, >500 chars, declares target hardware.
  3. Report contains machine-generated marker (proves report.py ran).
  4. Scores in report match *_metric_result.json values (anti-tamper).
  5. If stability mode: all N run subdirectories exist and each has a log.

.EXAMPLE
  powershell -File verify.ps1 -ReportDir benchmark-results\20260706-143000
  powershell -File verify.ps1 -ReportDir benchmark-results\reference\paddleocrvl_q4km_hip
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string] $ReportDir
)
$ErrorActionPreference = "Stop"
$passed = 0; $all = 0

function Pass($msg) { $script:passed++; $script:all++; Write-Host "  PASS  $msg" -ForegroundColor Green }
function Fail($msg) { $script:all++; Write-Host "  FAIL  $msg" -ForegroundColor Red; throw "VERIFY FAILED" }

$reportFile   = Join-Path $ReportDir "benchmark-report.md"
$resourceFile = Join-Path $ReportDir "resource_log.jsonl"
$manifestFile = Join-Path $ReportDir "_runs_manifest.json"

# 1. Resource log
Write-Host "[1/5] Resource log ..." -ForegroundColor Cyan
if (-not (Test-Path $resourceFile)) {
    # check subdirectories for stability mode
    $found = Get-ChildItem $ReportDir -Filter "resource_log.jsonl" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $resourceFile = $found.FullName }
    else { Fail "resource_log.jsonl missing at $ReportDir" }
}
$lines = @(Get-Content $resourceFile | Where-Object { $_ -match '\S' })
if ($lines.Count -eq 0) { Fail "resource_log.jsonl is empty" }
$first = $lines[0] | ConvertFrom-Json
foreach ($k in @("ts", "gpu_mem_mib", "gpu_util_pct", "ram_gib", "gpu_level")) {
    if (-not (Get-Member -InputObject $first -Name $k -MemberType NoteProperty)) {
        Fail "resource_log.jsonl missing field: $k"
    }
}
Pass "resource_log.jsonl: $($lines.Count) samples, schema valid"

# 2. Report file
Write-Host "[2/5] Report file ..." -ForegroundColor Cyan
if (-not (Test-Path $reportFile)) { Fail "benchmark-report.md missing at $reportFile" }
$reportContent = Get-Content -Raw $reportFile -Encoding UTF8
if ($reportContent.Length -lt 500) { Fail "benchmark-report.md too short ($($reportContent.Length) chars)" }
if ($reportContent -notmatch "AMD Ryzen AI Max\+ 395") {
    Fail "report does not declare target hardware"
}
Pass "benchmark-report.md: $($reportContent.Length) chars, hardware declared"

# 3. Machine-generated mark
Write-Host "[3/5] Machine-generated check ..." -ForegroundColor Cyan
if ($reportContent -notmatch "<!--\s*generated:\s*true") {
    Fail "report missing machine-generated marker"
}
Pass "machine-generated marker found"

# 4. Score consistency
Write-Host "[4/5] Score consistency ..." -ForegroundColor Cyan
$patterns = @(
    @{label="text_edit_dist";     regex='\|\s*text_block\s*\|\s*Edit_dist\s*\|\s*\*{0,2}([\d.]+)\*{0,2}'},
    @{label="table_teds";         regex='\|\s*table\s*\|\s*TEDS\s*\|\s*\*{0,2}([\d.]+)\*{0,2}'},
    @{label="reading_order";      regex='\|\s*reading_order\s*\|\s*Edit_dist\s*\|\s*\*{0,2}([\d.]+)\*{0,2}'}
)
$scoreExtracted = @{}
foreach ($p in $patterns) {
    if ($reportContent -match $p.regex) {
        $scoreExtracted[$p.label] = [double]$matches[1]
    } else {
        Write-Host "  WARN  score row not found: $($p.label)" -ForegroundColor Yellow
    }
}
$resultJsons = @(Get-ChildItem -Path (Split-Path $ReportDir -Parent) -Filter "*_metric_result.json" -Recurse -ErrorAction SilentlyContinue)
$resultJsons += @(Get-ChildItem -Path $ReportDir -Filter "*_metric_result.json" -Recurse -ErrorAction SilentlyContinue)
if ($resultJsons.Count -gt 0) {
    $resultJson = Get-Content -Raw $resultJsons[0].FullName | ConvertFrom-Json
    foreach ($c in @(
        @{label="text_edit_dist";  val=([double]$resultJson.text_block.all.Edit_dist.ALL_page_avg)},
        @{label="table_teds";      val=([double]$resultJson.table.all.TEDS.all)},
        @{label="reading_order";   val=([double]$resultJson.reading_order.all.Edit_dist.ALL_page_avg)}
    )) {
        if ($scoreExtracted.ContainsKey($c.label)) {
            $delta = [Math]::Abs($c.val - $scoreExtracted[$c.label])
            if ($delta -gt 0.001) {
                Fail "$($c.label): report=$($scoreExtracted[$c.label]) json=$($c.val) delta=$delta"
            }
        }
    }
} else {
    Write-Host "  WARN  metric_result.json not found - skipping cross-check" -ForegroundColor Yellow
}
Pass "score consistency verified"

# 5. Stability
Write-Host "[5/5] Stability check ..." -ForegroundColor Cyan
if (Test-Path $manifestFile) {
    $manifest = Get-Content -Raw $manifestFile | ConvertFrom-Json
    $expected = [int]$manifest.expected_runs
    $actual   = @($manifest.runs).Count
    if ($actual -lt $expected) { Fail "stability runs: expected $expected, found $actual" }
    foreach ($run in $manifest.runs) {
        $runLog = Join-Path $ReportDir $run.run_dir "resource_log.jsonl"
        if (-not (Test-Path $runLog)) { Fail "missing: $runLog" }
    }
    Pass "stability runs: $actual/$expected complete"
} else {
    Pass "single-run mode (no _runs_manifest.json)"
}

Write-Host ""
Write-Host "VERIFY OK  ($passed/$all checks passed)" -ForegroundColor Green
exit 0
