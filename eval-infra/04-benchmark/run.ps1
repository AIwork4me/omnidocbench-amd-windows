<#
.SYNOPSIS
Run a complete benchmark pipeline: monitor -> adapter -> scoring -> report.

.DESCRIPTION
Orchestrates a full OmniDocBench benchmark run on AMD hardware:
  1. Launches monitor.py as background process to sample GPU/RAM at 1 Hz.
  2. Runs the configured adapter over the dataset images.
  3. Stops the monitor and runs Edit_dist+TEDS+CDM scoring.
  4. Generates a Markdown capability report via report.py.
  5. Optionally repeats for N stability runs.

.PARAMETER Adapter
Adapter name (directory under adapters/). Default from config.

.PARAMETER Variant
hip or cpu. Default from config.

.PARAMETER Stability
Number of full runs for stability stats. Default 1 (single run).

.PARAMETER Config
Path to config YAML. Default: eval-infra/04-benchmark/config/default.yaml.

.EXAMPLE
  powershell -File run.ps1
  powershell -File run.ps1 -Adapter paddleocr-vl-1.6 -Variant hip -Stability 5
#>
[CmdletBinding()]
param(
    [string] $Adapter = "",
    [string] $Variant = "",
    [int]    $Stability = 0,
    [string] $Config = ""
)
$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$moduleDir = Join-Path $rootDir "eval-infra\04-benchmark"

$cfgPath = if ($Config) { $Config } else { Join-Path $moduleDir "config\default.yaml" }
if (-not (Test-Path $cfgPath)) {
    Write-Host "Config not found: $cfgPath" -ForegroundColor Red; exit 1
}
$cfg = @{}
Get-Content $cfgPath | ForEach-Object {
    if ($_ -match "^\s*(\w+):\s*(.*)") {
        $key = $matches[1]
        $val = $matches[2].Trim()
        if ($val -match "^['`"](.*)['`"]$") { $val = $matches[1] }
        $cfg[$key] = $val
    }
}

$adapterName    = if ($Adapter)  { $Adapter }  else { "paddleocr-vl-1.6" }
$adapterVariant = if ($Variant) { $Variant } else { "hip" }
$stabilityRuns  = if ($Stability -gt 0) { $Stability } else { 1 }

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$resultsDir = Join-Path $rootDir "benchmark-results\$runId"
$referenceDir = Join-Path $rootDir "benchmark-results\reference\$($adapterName)_q4km_$adapterVariant"

function Write-PhaseLog($path, $phaseName, $ts) {
    if (-not (Test-Path $path)) {
        $initial = [PSCustomObject]@{
            run_id    = $runId
            platform  = "AMD Ryzen AI Max+ 395 - Radeon 8060S - 128GB"
            qualifier = "$($adapterName)_q4km_$adapterVariant"
            phases    = @()
        }
    } else {
        $initial = Get-Content -Raw $path | ConvertFrom-Json
    }
    $entry = [PSCustomObject]@{ name = $phaseName; ts = $ts }
    $initial.phases += $entry
    $initial | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $path -Encoding UTF8
}

function Invoke-BenchmarkRun($runSubDir, [ref]$runIndex) {
    $runDir    = Join-Path $resultsDir $runSubDir
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    $resLog    = Join-Path $runDir "resource_log.jsonl"
    $phaseLog  = Join-Path $runDir "phase_log.json"
    $stopFile  = Join-Path $runDir "monitor_stop.txt"
    $monitorPy = Join-Path $moduleDir "monitor.py"

    Write-Host "--- Run $($runIndex.Value+1): $runSubDir ---" -ForegroundColor Cyan

    Write-Host "Starting monitor ..." -ForegroundColor DarkGray
    $proc = Start-Process python `
        -ArgumentList "`"$monitorPy`" --output `"$resLog`" --interval 1 --stop-file `"$stopFile`"" `
        -WorkingDirectory $runDir -PassThru -NoNewWindow

    try {
        $timeout = 10
        while (-not (Test-Path $resLog) -and $timeout -gt 0) {
            Start-Sleep -Milliseconds 500; $timeout--
        }
        if (-not (Test-Path $resLog)) {
            Write-Host "WARN: monitor did not start within 5s, continuing without it" -ForegroundColor Yellow
        } else {
            Write-Host "Monitor active." -ForegroundColor DarkGray
        }

        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        Write-PhaseLog $phaseLog "monitor_warmup_end" $now
        Write-PhaseLog $phaseLog "adapter_start" $now

        $adapterPy  = Join-Path $rootDir "adapters\$adapterName\run_adapter.py"
        $imgDir     = Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"
        $outDir     = Join-Path $rootDir "predictions\${adapterName}_bench"
        $env:PYTHONUTF8 = "1"
        $adapterLog = Join-Path $runDir "adapter_stdout.log"

        Write-Host "Running adapter: $adapterName ..." -ForegroundColor Cyan
        $adapterStart = Get-Date
        python "$adapterPy" --img-dir "$imgDir" --out-dir "$outDir" *> "$adapterLog"
        $adapterExit = $LASTEXITCODE
        $adapterEnd  = Get-Date
        $elapsed = [math]::Round(($adapterEnd - $adapterStart).TotalSeconds, 0)
        $color = if ($adapterExit -eq 0) { "Green" } else { "Yellow" }
        Write-Host "Adapter finished in ${elapsed}s (exit $adapterExit)" -ForegroundColor $color

        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        Write-PhaseLog $phaseLog "adapter_end" $now

    } finally {
        New-Item -ItemType File -Path $stopFile -Force -ErrorAction SilentlyContinue | Out-Null
        if ($proc -and -not $proc.HasExited) {
            $proc.WaitForExit(5000) | Out-Null
            if (-not $proc.HasExited) { $proc.Kill() }
        }
        Write-Host "Monitor stopped." -ForegroundColor DarkGray
    }

    Write-PhaseLog $phaseLog "scoring_start" $now

    $scorePs1 = Join-Path $rootDir "eval-infra\03-scoring\score.ps1"
    Write-Host "Scoring (Edit_dist + TEDS) ..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File "$scorePs1" -Config "v16-cdm.yaml"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: scoring exited $LASTEXITCODE" -ForegroundColor Yellow
    }

    $driveLetter = $rootDir.Substring(0, 1).ToLower()
    $restPath    = ($rootDir.Substring(2) -replace '\\', '/')
    $scoreCdm    = "/mnt/${driveLetter}${restPath}/eval-infra/03-scoring/score-cdm.sh"
    Write-Host "Scoring CDM (WSL) ..." -ForegroundColor Cyan
    wsl -d Ubuntu2204 bash "$scoreCdm" "v16-cdm.yaml" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: CDM scoring exited $LASTEXITCODE" -ForegroundColor Yellow
    }

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    Write-PhaseLog $phaseLog "scoring_end" $now

    $resultDir    = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench\result"
    $wslResultDir = "\\wsl$\Ubuntu2204\root\OmniDocBench\result"
    $metricJson   = ""
    foreach ($d in @($resultDir, $wslResultDir)) {
        if (Test-Path $d) {
            $found = Get-ChildItem $d -Filter "*_metric_result.json" -File -ErrorAction SilentlyContinue `
                | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($found) { $metricJson = $found.FullName; break }
        }
    }
    if (-not $metricJson) {
        Write-Host "FAIL: metric_result.json not found after scoring" -ForegroundColor Red; exit 1
    }
    Write-Host "Scores: $metricJson" -ForegroundColor DarkGray

    $statsJson = Join-Path $outDir "_run_stats.json"
    if (-not (Test-Path $statsJson)) {
        Write-Host "WARN: _run_stats.json not found at $statsJson" -ForegroundColor Yellow
        $statsJson = ""
    }

    $reportPy  = Join-Path $moduleDir "report.py"
    $reportOut = Join-Path $runDir "benchmark-report.md"
    $reportArgs = @(
        "--stats", $statsJson,
        "--scores", $metricJson,
        "--resource", $resLog,
        "--phase-log", $phaseLog,
        "--output", $reportOut,
        "--mode", "single",
        "--platform", "AMD Ryzen AI Max+ 395 - Radeon 8060S - 128GB",
        "--qualifier", "$($adapterName)_q4km_$adapterVariant",
        "--run-id", $runId
    )
    python "$reportPy" $reportArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: report.py exited $LASTEXITCODE" -ForegroundColor Red; exit 1
    }
    Write-Host "Report: $reportOut" -ForegroundColor Green
    $runIndex.Value++
}

# --- Main ---
try {
    Write-Host "=== Benchmark: $adapterName ($adapterVariant) ===" -ForegroundColor Cyan

    if ($stabilityRuns -le 1) {
        $ri = 0
        Invoke-BenchmarkRun $runId ([ref]$ri)
    } else {
        Write-Host "Stability mode: $stabilityRuns runs" -ForegroundColor Magenta
        $manifest = @{ expected_runs = $stabilityRuns; runs = @() }
        $runIdx = 0
        for ($i = 1; $i -le $stabilityRuns; $i++) {
            $subDir = "run-{0:D2}" -f $i
            Invoke-BenchmarkRun $subDir ([ref]$runIdx)

            $subResLog = Join-Path $resultsDir $subDir "resource_log.jsonl"
            $scores    = @{}
            $gpuPeak   = 0
            if ($subResLog -and (Test-Path $subResLog)) {
                Get-Content $subResLog | ForEach-Object {
                    if ($_ -match '"gpu_mem_mib":\s*(\d+\.?\d*)') {
                        $v = [double]$matches[1]; if ($v -gt $gpuPeak) { $gpuPeak = $v }
                    }
                }
            }
            # Count prediction files for this run
            $predDir   = Join-Path $rootDir "predictions\${adapterName}_bench"
            $pagesOk   = if (Test-Path $predDir) { (Get-ChildItem $predDir -Filter "*.md" -File).Count } else { 0 }
            $manifest.runs += @{
                run_dir      = $subDir
                scores       = $scores
                duration_sec = 0
                gpu_peak_mib = $gpuPeak
                pages_ok     = $pagesOk
                pages_total  = $pagesOk
            }
        }

        $manifestPath = Join-Path $referenceDir "_runs_manifest.json"
        New-Item -ItemType Directory -Force -Path $referenceDir | Out-Null
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

        Write-Host "Generating reference report ..." -ForegroundColor Cyan
        $lastSubDir = "run-{0:D2}" -f $stabilityRuns
        $lastScores = Get-ChildItem (Join-Path $resultsDir $lastSubDir) -Filter "*metric*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        $reportArgs = @(
            "--stats", (Join-Path $rootDir "predictions\${adapterName}_bench\_run_stats.json"),
            "--scores", $(if ($lastScores) { $lastScores.FullName } else { "" }),
            "--resource", (Join-Path $resultsDir $lastSubDir "resource_log.jsonl"),
            "--output", (Join-Path $referenceDir "benchmark-report.md"),
            "--mode", "reference",
            "--platform", "AMD Ryzen AI Max+ 395 - Radeon 8060S - 128GB",
            "--qualifier", "$($adapterName)_q4km_$adapterVariant",
            "--run-id", $runId
        )
        python (Join-Path $moduleDir "report.py") $reportArgs
    }

    Write-Host ""
    Write-Host "=== Benchmark complete ===" -ForegroundColor Green
    Write-Host "Results: $resultsDir" -ForegroundColor Cyan
    if ($stabilityRuns -gt 1) {
        Write-Host "Reference: $referenceDir" -ForegroundColor Cyan
    }
    Write-Host "Next: powershell -File eval-infra\04-benchmark\verify.ps1 -ReportDir $resultsDir" -ForegroundColor DarkGray
    exit 0
} finally {
    Write-Host "Cleanup done." -ForegroundColor DarkGray
}
