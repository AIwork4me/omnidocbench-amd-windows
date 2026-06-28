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
"python" on PATH; override with the venv's python.exe if needed.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File score.ps1
  powershell -ExecutionPolicy Bypass -File score.ps1 -Config v16-hard.yaml
  powershell -ExecutionPolicy Bypass -File score.ps1 -Python C:\path\to\.venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [string] $Config = "v16.yaml",
    [string] $Python = "python"
)
$ErrorActionPreference = "Stop"

# Resolve repo root (this script is at <root>/eval-infra/03-scoring/score.ps1).
# Nested Join-Path so this works on Windows PowerShell 5.1 as well as PS 7+.
$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

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

# --- 2. Materialize a run config from the template --------------------------
# Replace the literal placeholder <REPO_ROOT> with the absolute Windows path so
# the GT manifest, predictions dir, and image paths all resolve. We write the
# rendered config into the OmniDocBench checkout (next to pdf_validation.py) so
# relative ./result/ outputs land there too. Gitignored.
#
# NB: -replace's REPLACEMENT string is .NET-regex semantics, where backslash is
# literal (no escaping needed) and '$' is special. So we must NOT double the
# backslashes in $rootDir -- doing so writes C:\\Users\\... into the YAML. We
# pass the path through as-is. (If $rootDir ever contained a '$', we would need
# to escape it as $$, but Windows paths do not.)
$template = Get-Content -Raw -LiteralPath $cfgTemplate
$rendered = $template -replace [regex]::Escape("<REPO_ROOT>"), $rootDir
$runCfg = Join-Path $odbDir "run_$([System.IO.Path]::GetFileNameWithoutExtension($Config)).yaml"
Set-Content -LiteralPath $runCfg -Value $rendered -Encoding UTF8
Write-Host "Rendered run config: $runCfg" -ForegroundColor DarkGray

# --- 3. Run pdf_validation.py (Windows-native, UTF-8 mode) ------------------
# PYTHONUTF8=1 is mandatory on Windows: OmniDocBench opens/c writes UTF-8 JSON
# and reads CJK LaTeX; without it, the default cp1252/cp936 codepage corrupts
# both. Forward slashes in the path are safe on Windows and avoid PS quoting
# headaches.
$env:PYTHONUTF8 = "1"
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
