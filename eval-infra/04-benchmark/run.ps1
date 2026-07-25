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

.PARAMETER Platform
Hardware identifier written to the capability report. When omitted, the script
builds one from the local CPU, GPU, and installed memory.

.EXAMPLE
  powershell -File run.ps1
  powershell -File run.ps1 -Adapter paddleocr-vl-1.6 -Variant hip -Stability 5
#>
[CmdletBinding()]
param(
    [string] $Adapter = "",
    [string] $Variant = "",
    [int]    $Stability = 0,
    [string] $Config = "",
    [string] $Platform = ""
)
$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$moduleDir = Join-Path $rootDir "eval-infra\04-benchmark"
$python = Join-Path $rootDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "FAIL: locked Python environment not found: $python" -ForegroundColor Red
    Write-Host "      Run 'uv sync --locked --all-groups' first." -ForegroundColor Yellow
    exit 1
}

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

if ([string]::IsNullOrWhiteSpace($Platform)) {
    $cpuName = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name).Trim()
    $gpuNames = @(
        Get-CimInstance Win32_VideoController |
            ForEach-Object { $_.Name.Trim() } |
            Where-Object { $_ } |
            Select-Object -Unique
    )
    $memoryBytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    $memoryGiB = [math]::Round($memoryBytes / 1GB, 1)
    $Platform = "$cpuName - $($gpuNames -join ' + ') - ${memoryGiB} GiB RAM"
}
$platformLabel = $Platform.Trim()
if ([string]::IsNullOrWhiteSpace($platformLabel)) {
    Write-Host "FAIL: -Platform must not be empty." -ForegroundColor Red
    exit 1
}

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$resultsDir = Join-Path $rootDir "benchmark-results\$runId"
$referenceDir = Join-Path $rootDir "benchmark-results\reference\$($adapterName)_q4km_$adapterVariant"

function Write-PhaseLog($path, $phaseName, $ts) {
    if (-not (Test-Path $path)) {
        $initial = [PSCustomObject]@{
            run_id    = $runId
            platform  = $platformLabel
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
    $runLabel  = if ([string]::IsNullOrWhiteSpace($runSubDir)) { "single" } else { $runSubDir }
    $runDir    = if ([string]::IsNullOrWhiteSpace($runSubDir)) { $resultsDir } else { Join-Path $resultsDir $runSubDir }
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    $resLog    = Join-Path $runDir "resource_log.jsonl"
    $phaseLog  = Join-Path $runDir "phase_log.json"
    $stopFile  = Join-Path $runDir "monitor_stop.txt"
    $monitorPy = Join-Path $moduleDir "monitor.py"

    Write-Host "--- Run $($runIndex.Value+1): $runLabel ---" -ForegroundColor Cyan

    Write-Host "Starting monitor ..." -ForegroundColor DarkGray
    $proc = Start-Process $python `
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

        $now = [int64](([DateTimeOffset]::UtcNow) - ([DateTimeOffset](Get-Date "1970-01-01Z").ToUniversalTime())).TotalSeconds
        Write-PhaseLog $phaseLog "monitor_warmup_end" $now
        Write-PhaseLog $phaseLog "adapter_start" $now

        $adapterPy  = Join-Path $rootDir "adapters\$adapterName\run_adapter.py"
        $imgDir     = Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"
        $predictionName = (("{0}_{1}_{2}" -f $adapterName, $runId, $runLabel) -replace '[^A-Za-z0-9_-]', '_')
        $predictionRelative = "predictions/benchmark/$predictionName"
        $outDir     = Join-Path $rootDir ($predictionRelative -replace '/', '\')
        $env:PYTHONUTF8 = "1"
        $adapterLog = Join-Path $runDir "adapter_stdout.log"

        Write-Host "Running adapter: $adapterName ..." -ForegroundColor Cyan
        $adapterStart = Get-Date
        & $python "$adapterPy" --img-dir "$imgDir" --out-dir "$outDir" *> "$adapterLog"
        $adapterExit = $LASTEXITCODE
        $adapterEnd  = Get-Date
        $elapsed = [math]::Round(($adapterEnd - $adapterStart).TotalSeconds, 0)
        $color = if ($adapterExit -eq 0) { "Green" } else { "Red" }
        Write-Host "Adapter finished in ${elapsed}s (exit $adapterExit)" -ForegroundColor $color
        if ($adapterExit -ne 0) {
            throw "Adapter failed with exit $adapterExit. See $adapterLog"
        }

        $statsJson = Join-Path $outDir "_run_stats.json"
        if (-not (Test-Path -LiteralPath $statsJson)) {
            throw "Adapter completed without _run_stats.json: $statsJson"
        }
        $predictionValidator = Join-Path $rootDir "scripts\validate_predictions.py"
        & $python "$predictionValidator" --img-dir "$imgDir" --pred-dir "$outDir" --min-coverage 0.95
        if ($LASTEXITCODE -ne 0) {
            throw "Prediction output validation failed: $outDir"
        }

        $now = [int64](([DateTimeOffset]::UtcNow) - ([DateTimeOffset](Get-Date "1970-01-01Z").ToUniversalTime())).TotalSeconds
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
    $scoreVerify = Join-Path $rootDir "eval-infra\03-scoring\verify.ps1"
    $saveName = "${predictionName}_quick_match"
    Write-Host "Scoring (Edit_dist + TEDS) ..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File "$scorePs1" -Config "v16.yaml" -PredictionDir "$outDir"
    if ($LASTEXITCODE -ne 0) {
        throw "Windows non-CDM scoring exited $LASTEXITCODE"
    }
    $windowsMetric = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench\result\${saveName}_metric_result.json"
    & powershell -ExecutionPolicy Bypass -File "$scoreVerify" -MetricResult "$windowsMetric"
    if ($LASTEXITCODE -ne 0) { throw "Windows non-CDM scoring verification failed" }

    $driveLetter = $rootDir.Substring(0, 1).ToLower()
    $restPath    = ($rootDir.Substring(2) -replace '\\', '/')
    $scoreCdm    = "/mnt/${driveLetter}${restPath}/eval-infra/03-scoring/score-cdm.sh"
    Write-Host "Scoring CDM (WSL) ..." -ForegroundColor Cyan
    wsl -d Ubuntu2204 bash "$scoreCdm" "v16-cdm.yaml" "$predictionRelative"
    if ($LASTEXITCODE -ne 0) {
        throw "WSL CDM scoring exited $LASTEXITCODE"
    }

    $wslHomeOutput = wsl -d Ubuntu2204 -- sh -lc 'printf %s "$HOME"' 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Could not resolve the Ubuntu2204 user home after CDM scoring" }
    $wslHome = ((@($wslHomeOutput) -join "") -replace "`0", "").Trim()
    if ($wslHome -notmatch '^/') { throw "Unexpected Ubuntu2204 HOME: '$wslHome'" }
    $wslHomeUnc = "\\wsl$\Ubuntu2204" + ($wslHome -replace '/', '\')
    $metricJson = Join-Path $wslHomeUnc "OmniDocBench\result\${saveName}_metric_result.json"
    & powershell -ExecutionPolicy Bypass -File "$scoreVerify" -MetricResult "$metricJson" -RequireCdm
    if ($LASTEXITCODE -ne 0) { throw "WSL CDM scoring verification failed" }

    $now = [int64](([DateTimeOffset]::UtcNow) - ([DateTimeOffset](Get-Date "1970-01-01Z").ToUniversalTime())).TotalSeconds
    Write-PhaseLog $phaseLog "scoring_end" $now

    $runMetricJson = Join-Path $runDir "${saveName}_metric_result.json"
    Copy-Item -LiteralPath $metricJson -Destination $runMetricJson -Force
    $metricJson = $runMetricJson
    Write-Host "Scores: $metricJson" -ForegroundColor DarkGray

    $reportPy  = Join-Path $moduleDir "report.py"
    $reportOut = Join-Path $runDir "benchmark-report.md"
    $reportArgs = @(
        "--stats", $statsJson,
        "--scores", $metricJson,
        "--resource", $resLog,
        "--phase-log", $phaseLog,
        "--output", $reportOut,
        "--mode", "single",
        "--platform", $platformLabel,
        "--qualifier", "$($adapterName)_q4km_$adapterVariant",
        "--run-id", $runId
    )
    & $python "$reportPy" $reportArgs
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
        Invoke-BenchmarkRun "" ([ref]$ri)
    } else {
        Write-Host "Stability mode: $stabilityRuns runs" -ForegroundColor Magenta
        $manifest = @{ expected_runs = $stabilityRuns; runs = @() }
        $runIdx = 0
        for ($i = 1; $i -le $stabilityRuns; $i++) {
            $subDir = "run-{0:D2}" -f $i
            Invoke-BenchmarkRun $subDir ([ref]$runIdx)

            $subResLog = Join-Path $resultsDir $subDir "resource_log.jsonl"
            $predictionName = (("{0}_{1}_{2}" -f $adapterName, $runId, $subDir) -replace '[^A-Za-z0-9_-]', '_')
            $metricPath = Join-Path $resultsDir "$subDir\${predictionName}_quick_match_metric_result.json"
            if (-not (Test-Path -LiteralPath $metricPath)) { throw "Stability metric missing: $metricPath" }
            $metricData = Get-Content -Raw -LiteralPath $metricPath | ConvertFrom-Json
            $scores = @{
                text_edit_dist = [double]$metricData.text_block.all.Edit_dist.ALL_page_avg
                reading_order  = [double]$metricData.reading_order.all.Edit_dist.ALL_page_avg
                table_teds     = [double]$metricData.table.all.TEDS.all
                formula_cdm    = [double]$metricData.display_formula.all.CDM.all
            }
            $gpuPeak   = 0
            if ($subResLog -and (Test-Path $subResLog)) {
                Get-Content $subResLog | ForEach-Object {
                    if ($_ -match '"gpu_mem_mib":\s*(\d+\.?\d*)') {
                        $v = [double]$matches[1]; if ($v -gt $gpuPeak) { $gpuPeak = $v }
                    }
                }
            }
            # Count prediction files for this run
            $predDir   = Join-Path $rootDir "predictions\benchmark\$predictionName"
            $pagesOk   = if (Test-Path $predDir) { (Get-ChildItem $predDir -Filter "*.md" -File).Count } else { 0 }
            $statsData = Get-Content -Raw -LiteralPath (Join-Path $predDir "_run_stats.json") | ConvertFrom-Json
            $durationSec = [math]::Round((@($statsData.stats | ForEach-Object { [double]$_.seconds }) | Measure-Object -Sum).Sum, 2)
            $manifest.runs += @{
                run_dir      = $subDir
                scores       = $scores
                duration_sec = $durationSec
                gpu_peak_mib = $gpuPeak
                pages_ok     = $pagesOk
                pages_total  = [int]$statsData.count
            }
        }

        $manifestPath = Join-Path $referenceDir "_runs_manifest.json"
        New-Item -ItemType Directory -Force -Path $referenceDir | Out-Null
        foreach ($run in $manifest.runs) {
            $sourceRun = Join-Path $resultsDir $run.run_dir
            $referenceRun = Join-Path $referenceDir $run.run_dir
            New-Item -ItemType Directory -Force -Path $referenceRun | Out-Null
            Copy-Item -LiteralPath (Join-Path $sourceRun "resource_log.jsonl") -Destination $referenceRun -Force
        }
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

        Write-Host "Generating reference report ..." -ForegroundColor Cyan
        $lastSubDir = "run-{0:D2}" -f $stabilityRuns
        $lastPredictionName = (("{0}_{1}_{2}" -f $adapterName, $runId, $lastSubDir) -replace '[^A-Za-z0-9_-]', '_')
        $lastPredDir = Join-Path $rootDir "predictions\benchmark\$lastPredictionName"
        $lastScores = Join-Path $resultsDir "$lastSubDir\${lastPredictionName}_quick_match_metric_result.json"
        $referenceScores = Join-Path $referenceDir "${lastPredictionName}_quick_match_metric_result.json"
        $referenceStats = Join-Path $referenceDir "_run_stats.json"
        $referenceResource = Join-Path $referenceDir "resource_log.jsonl"
        Copy-Item -LiteralPath $lastScores -Destination $referenceScores -Force
        Copy-Item -LiteralPath (Join-Path $lastPredDir "_run_stats.json") -Destination $referenceStats -Force
        Copy-Item -LiteralPath (Join-Path $resultsDir "$lastSubDir\resource_log.jsonl") -Destination $referenceResource -Force
        $reportArgs = @(
            "--stats", $referenceStats,
            "--scores", $referenceScores,
            "--resource", $referenceResource,
            "--output", (Join-Path $referenceDir "benchmark-report.md"),
            "--mode", "reference",
            "--platform", $platformLabel,
            "--qualifier", "$($adapterName)_q4km_$adapterVariant",
            "--run-id", $runId,
            "--runs-manifest", $manifestPath
        )
        & $python (Join-Path $moduleDir "report.py") $reportArgs
    }

    Write-Host ""
    Write-Host "=== Benchmark complete ===" -ForegroundColor Green
    Write-Host "Results: $resultsDir" -ForegroundColor Cyan
    if ($stabilityRuns -gt 1) {
        Write-Host "Reference: $referenceDir" -ForegroundColor Cyan
    }
    $verifyDir = if ($stabilityRuns -gt 1) { $referenceDir } else { $resultsDir }
    Write-Host "Next: powershell -File eval-infra\04-benchmark\verify.ps1 -ReportDir $verifyDir" -ForegroundColor DarkGray
    exit 0
} finally {
    Write-Host "Cleanup done." -ForegroundColor DarkGray
}
