<#
.SYNOPSIS
Score adapter predictions with Edit_dist + TEDS (Windows-native; CDM disabled).

.DESCRIPTION
Runs OmniDocBench's pdf_validation.py against a config template (from
eval-infra/01-omnidocbench/configs/) with the `<REPO_ROOT>` placeholder resolved
to this repo's absolute root. CDM is intentionally OFF — it needs the WSL
LaTeX/ImageMagick toolchain (see score-cdm.sh). Use this for the fast, pure-
Python Edit_dist + TEDS pass over text_block / display_formula / table /
reading_order.

The result files land in the OmniDocBench checkout's ./result/ directory:
    <save_name>_metric_result.json   (the scores; consumed by verify.ps1)
    <save_name>_run_summary.json     (environment + runtime report)
where <save_name> = <prediction-dir-basename>_<match_method>, e.g.
paddleocrvl_rocm_quick_match.

.PARAMETER Config
Config template to use (under eval-infra/01-omnidocbench/configs/). Defaults to
"v16.yaml" (full 1651-page set, Edit_dist + TEDS). Use "v16-hard.yaml" for the
296-page hard subset.

.PARAMETER Python
Python executable to run pdf_validation.py with. Must be the OmniDocBench
venv (Python 3.10/3.11 — OmniDocBench is not 3.12-compatible). Defaults to
the repo-root .venv created by eval-infra/01-omnidocbench/setup.ps1; falls
back to "python" on PATH only if that venv is absent.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File score.ps1
  powershell -ExecutionPolicy Bypass -File score.ps1 -Config v16-hard.yaml
  powershell -ExecutionPolicy Bypass -File score.ps1 -Python C:\path\to\.venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [string] $Config = "v16.yaml",
    [string] $Python = ""
)
$ErrorActionPreference = "Stop"

# Resolve repo root (this script is at <root>/eval-infra/03-scoring/score.ps1).
# Nested Join-Path so this works on Windows PowerShell 5.1 as well as PS 7+.
$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

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

# --- 1. Locate inputs -------------------------------------------------------
$cfgTemplate = Join-Path $rootDir "eval-infra\01-omnidocbench\configs\$Config"
if (-not (Test-Path $cfgTemplate)) {
    throw "Config template not found: $cfgTemplate`nAvailable templates: v16.yaml, v16-hard.yaml, v16-cdm.yaml"
}

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
        $manifest = Get-Content -Raw -LiteralPath $fullMan | ConvertFrom-Json
        # OmniDocBench.json is a list of page objects each with a "subset" field.
        # Keep only the hard-subset pages.
        $hardSets = @("equation_hard", "layout_hard", "table_hard")
        $hardPages = @($manifest | Where-Object { $hardSets -contains $_.subset })
        if ($hardPages.Count -eq 0) {
            Write-Host "WARN: 0 hard pages found in manifest (expected ~296)." -ForegroundColor Yellow
            Write-Host "      The upstream manifest schema may have changed; check the 'subset' field." -ForegroundColor Yellow
        } else {
            $hardPages | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $hardMan -Encoding UTF8
            Write-Host "Wrote $hardMan ($($hardPages.Count) hard pages)." -ForegroundColor Green
        }
    } catch {
        Write-Host "WARN: could not auto-derive $hardMan : $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "      Create it manually by filtering OmniDocBench.json for subset in {equation_hard, layout_hard, table_hard}." -ForegroundColor Yellow
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
# NB: -replace's REPLACEMENT string is .NET-regex semantics, where backslash is
# literal (no escaping needed) and '$' is special. We convert $rootDir to
# forward-slash form BEFORE the replace so the YAML contains C:/Users/... .
# (If $rootDir ever contained a '$', we would need to escape it as $$.)
$rootPosix = $rootDir -replace '\\', '/'
$template = Get-Content -Raw -LiteralPath $cfgTemplate
$rendered = $template -replace [regex]::Escape("<REPO_ROOT>"), $rootPosix
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
    Write-Host "Scoring (Edit_dist + TEDS) with $Config ..." -ForegroundColor Cyan
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
Write-Host "Next: run verify.ps1 to confirm metric_result.json exists and all 4 metrics are non-zero." -ForegroundColor Cyan
