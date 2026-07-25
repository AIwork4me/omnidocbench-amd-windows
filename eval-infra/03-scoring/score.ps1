<#
.SYNOPSIS
Score adapter predictions with the metrics enabled by a config.

.DESCRIPTION
Runs OmniDocBench's pdf_validation.py against a config template (from
eval-infra/01-omnidocbench/configs/) with the `<REPO_ROOT>` placeholder resolved
to this repo's absolute root. This Windows-native scorer runs the metrics
enabled by the selected config. CDM configs such as `v16-cdm.yaml` require
`windows-cdm.patch` and a passing `verify-windows.ps1` check first.

The result files land in the OmniDocBench checkout's ./result/ directory:
    <save_name>_metric_result.json   (the scores; consumed by verify.ps1)
    <save_name>_run_summary.json     (environment + runtime report)
where <save_name> = <prediction-dir-basename>_<match_method>, e.g.
paddleocrvl_rocm_quick_match.

.PARAMETER Config
Config template to use (under eval-infra/01-omnidocbench/configs/). Defaults to
"v16.yaml" (full 1651-page set). Use "v16-hard.yaml" for the 296-page hard
subset. Use "v16-cdm.yaml" to include CDM after the native Windows CDM
prerequisites described above pass verification.

.PARAMETER Python
Python executable to run pdf_validation.py with. Must be the OmniDocBench
venv (Python 3.10/3.11 — OmniDocBench is not 3.12-compatible). Defaults to
the repo-root .venv created by eval-infra/01-omnidocbench/setup.ps1; falls
back to "python" on PATH only if that venv is absent.

.PARAMETER PredictionDir
Optional prediction directory override. Relative paths resolve from the repo
root. The directory must exist and contain at least one Markdown file. This is
used by benchmark/custom-adapter runs so inference and scoring consume the
same explicit output directory.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File score.ps1
  powershell -ExecutionPolicy Bypass -File score.ps1 -Config v16-hard.yaml
  powershell -ExecutionPolicy Bypass -File score.ps1 -Config v16-cdm.yaml
  powershell -ExecutionPolicy Bypass -File score.ps1 -Python C:\path\to\.venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [string] $Config = "v16.yaml",
    [string] $Python = "",
    [string] $PredictionDir = ""
)
$ErrorActionPreference = "Stop"

# Resolve repo root (this script is at <root>/eval-infra/03-scoring/score.ps1).
# Nested Join-Path so this works on Windows PowerShell 5.1 as well as PS 7+.
$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Get-ShortRepoRoot {
    param([string]$RepoRoot)
    $normalizedRoot = [System.IO.Path]::GetFullPath($RepoRoot)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedRoot.ToLowerInvariant()))
    } finally {
        $sha.Dispose()
    }
    $hash = ([System.BitConverter]::ToString($hashBytes) -replace "-", "").ToLowerInvariant().Substring(0, 12)
    $alias = Join-Path (Join-Path (Join-Path $env:LOCALAPPDATA "OmniDocBenchAMD") $hash) "repo"
    if (Test-Path -LiteralPath $alias) { return $alias }
    return $normalizedRoot
}

function ConvertTo-ShortRepoPath {
    param([string]$Path, [string]$RepoRoot)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $fullRoot = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
    if ($fullPath.Equals($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return Get-ShortRepoRoot -RepoRoot $RepoRoot
    }
    $rootPrefix = $fullRoot + "\"
    if ($fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relative = $fullPath.Substring($rootPrefix.Length)
        return Join-Path (Get-ShortRepoRoot -RepoRoot $RepoRoot) $relative
    }
    return $fullPath
}

# Default to the repo-root .venv (created by 01-omnidocbench/setup.ps1) so a
# bare `python` that happens to be 3.13 doesn't crash OmniDocBench mid-score.
# Fall back to "python" only if the venv wasn't provisioned.
if ([string]::IsNullOrWhiteSpace($Python)) {
    $venvPython = Join-Path $rootDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $Python = $venvPython
    } else {
        $Python = "python"
        Write-Host "WARN: repo-root .venv not found; using bare 'python'." -ForegroundColor Yellow
        Write-Host "      Run eval-infra\01-omnidocbench\setup.ps1 to create it (OmniDocBench needs Python < 3.12)." -ForegroundColor Yellow
        Write-Host "      See docs/pitfalls.md#python-version." -ForegroundColor Yellow
    }
}

try {
    $pythonVersion = & $Python --version 2>&1
} catch {
    throw "Python executable could not be started: $Python`nRun 'uv sync --locked --all-groups' first."
}
if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch "Python 3\.(10|11)\.") {
    throw "OmniDocBench scoring requires Python 3.10 or 3.11 (found: '$pythonVersion'). Run 'uv sync --locked --all-groups' first."
}

# --- 1. Locate inputs -------------------------------------------------------
$cfgTemplate = Join-Path $rootDir "eval-infra\01-omnidocbench\configs\$Config"
if (-not (Test-Path $cfgTemplate)) {
    throw "Config template not found: $cfgTemplate`nAvailable templates include: v16.yaml, v16-official.yaml, v16-hard.yaml, v16-cdm.yaml, v16-cdm-official.yaml"
}

$configRoot = Get-ShortRepoRoot -RepoRoot $rootDir
$rootPosix = $configRoot -replace '\\', '/'
$template = Get-Content -Raw -LiteralPath $cfgTemplate
$rendered = $template -replace [regex]::Escape("<REPO_ROOT>"), $rootPosix
$predictionPattern = '(?m)^(\s*)prediction:\s*\{\s*data_path:\s*([^}\r\n]+?)\s*\}\s*$'
$predictionMatches = [regex]::Matches($rendered, $predictionPattern)
if ($predictionMatches.Count -ne 1) {
    throw "Config must contain exactly one inline prediction.data_path (found $($predictionMatches.Count)): $cfgTemplate"
}
if (-not [string]::IsNullOrWhiteSpace($PredictionDir)) {
    if (-not [System.IO.Path]::IsPathRooted($PredictionDir)) {
        $PredictionDir = Join-Path $rootDir $PredictionDir
    }
    $PredictionDir = ConvertTo-ShortRepoPath -Path $PredictionDir -RepoRoot $rootDir
    $predictionPosix = $PredictionDir -replace '\\', '/'
    $indent = $predictionMatches[0].Groups[1].Value
    $replacement = "${indent}prediction:   { data_path: $predictionPosix }"
    $rendered = $rendered.Replace($predictionMatches[0].Value, $replacement)
}

$configuredPrediction = [regex]::Match($rendered, $predictionPattern).Groups[2].Value.Trim()
if (-not (Test-Path -LiteralPath $configuredPrediction -PathType Container)) {
    throw "Prediction directory not found: $configuredPrediction`nRun the adapter with --out-dir matching the scoring config, or pass -PredictionDir."
}
$predictionCount = @(Get-ChildItem -LiteralPath $configuredPrediction -Filter "*.md" -File -ErrorAction SilentlyContinue).Count
if ($predictionCount -eq 0) {
    throw "Prediction directory contains no Markdown files: $configuredPrediction`nRun the adapter before scoring."
}
Write-Host "Predictions: $configuredPrediction ($predictionCount Markdown files)" -ForegroundColor DarkGray

$odbDir = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench"
$pdfValidation = Join-Path $odbDir "pdf_validation.py"
if (-not (Test-Path $pdfValidation)) {
    throw "OmniDocBench code missing ($pdfValidation).`nRun eval-infra\01-omnidocbench\setup.ps1 first."
}

# --- 1b. Auto-derive the hard-subset manifest when a hard config is selected --
# OmniDocBench_hard296.json is a derivative of OmniDocBench.json (filter for
# subset in {equation_hard, layout_hard, table_hard}). It is NOT in the dataset
# download. Rather than leave it as a manual TODO, we materialize it here on
# first use so `score.ps1 -Config v16-hard.yaml` is self-contained. Idempotent:
# skipped if the file already exists.
$dataDir   = Join-Path $rootDir "eval-infra\01-omnidocbench\data"
$fullMan   = Join-Path $dataDir "OmniDocBench.json"
$hardMan   = Join-Path $dataDir "OmniDocBench_hard296.json"
if ($Config -match "hard" -and (Test-Path $fullMan) -and -not (Test-Path $hardMan)) {
    Write-Host "Deriving hard-subset manifest from OmniDocBench.json ..." -ForegroundColor DarkGray
    try {
        $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $fullMan | ConvertFrom-Json
        # OmniDocBench.json stores the subset under
        # page_info.page_attribute.subset. Keep only hard-subset pages.
        $hardSets = @("equation_hard", "layout_hard", "table_hard")
        $hardPages = @($manifest | Where-Object { $hardSets -contains $_.page_info.page_attribute.subset })
        if ($hardPages.Count -eq 0) {
            throw "Hard-subset derivation produced 0 pages (expected approximately 296). The upstream manifest schema may have changed; check page_info.page_attribute.subset."
        } else {
            $hardPages | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $hardMan -Encoding UTF8
            Write-Host "Wrote $hardMan ($($hardPages.Count) hard pages)." -ForegroundColor Green
        }
    } catch {
        throw "Could not derive $hardMan from $fullMan. $($_.Exception.Message)"
    }
}

# --- 2. Materialize a run config from the template --------------------------
# Replace the literal placeholder <REPO_ROOT> with the absolute path so the GT
# manifest, predictions dir, and image paths all resolve. We write the rendered
# config into the OmniDocBench checkout (next to pdf_validation.py) so relative
# ./result/ outputs land there too. Gitignored.
#
# We normalize the path to FORWARD SLASHES. Both YAML and Python accept '/' on
# Windows (os.path / pathlib handle it), and this matches the form score-cdm.sh
# already produces (it expands <REPO_ROOT> to a /mnt/c/... path). Keeping the
# two scorers' rendered YAML path-style identical means a future cross-boundary
# config consumer won't break on a backslash/forward-slash mismatch.
#
$runCfg = Join-Path $odbDir "run_$([System.IO.Path]::GetFileNameWithoutExtension($Config)).yaml"
Set-Content -LiteralPath $runCfg -Value $rendered -Encoding UTF8
Write-Host "Rendered run config: $runCfg" -ForegroundColor DarkGray

# --- 3. Run pdf_validation.py (Windows-native, UTF-8 mode) ------------------
# PYTHONUTF8=1 is mandatory on Windows: OmniDocBench opens/c writes UTF-8 JSON
# and reads CJK LaTeX; without it, the default cp1252/cp936 codepage corrupts
# both. Forward slashes in the path are safe on Windows and avoid PS quoting
# headaches.
$env:PYTHONUTF8 = "1"
# Hint for the hand-debugging path: if a user runs pdf_validation.py directly
# (bypassing this script, common during debugging), or from an IDE that doesn't
# inherit this env var, they'll hit UnicodeDecodeError/'gbk' codec errors with
# no mention of PYTHONUTF8. Surface the requirement up front.
Write-Host "PYTHONUTF8=1 set for this run. If you call pdf_validation.py directly," -ForegroundColor DarkGray
Write-Host "set PYTHONUTF8=1 yourself, or see docs/pitfalls.md#pythonutf8." -ForegroundColor DarkGray
Push-Location $odbDir
try {
    Write-Host "Scoring with config $Config ..." -ForegroundColor Cyan
    & $Python $pdfValidation --config $runCfg
    if ($LASTEXITCODE -ne 0) { throw "pdf_validation.py exited $LASTEXITCODE" }
    Write-Host "Scoring complete. Results in: $odbDir\result\" -ForegroundColor Green
}
finally {
    Pop-Location
}

# --- 4. Point the user at the result files ---------------------------------
# save_name = basename(prediction data_path) + "_" + match_method, e.g.
# paddleocrvl_rocm_quick_match. We don't parse it here; verify.ps1 locates the
# most recent *_metric_result.json if a save_name isn't given.
Write-Host ""
Write-Host "Next: run verify.ps1 to confirm metric_result.json exists; mandatory metrics are present and non-negative; CDM must be positive when present or required." -ForegroundColor Cyan
