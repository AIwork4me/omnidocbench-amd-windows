<#
.SYNOPSIS
Verify the native Windows OmniDocBench CDM toolchain.

.DESCRIPTION
Checks the generated OmniDocBench checkout contains the tracked Windows CDM
patch, verifies TeX Live/ImageMagick/Ghostscript discovery, then runs a real
CDM identical-formula smoke test. Exit 0 means native Windows CDM is functional.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$odbDir = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench"
$venvPython = Join-Path $rootDir ".venv\Scripts\python.exe"
$windowsCdmPatch = Join-Path $rootDir "patches\omnidocbench\windows-cdm.patch"
$latexColorFile = Join-Path $odbDir "src\metrics\cdm\modules\latex2bbox_color.py"
$texliveEnvFile = Join-Path $odbDir "src\metrics\cdm\modules\texlive_env.py"

$ok = $true
function Fail($message) {
    Write-Host "FAIL: $message" -ForegroundColor Red
    $script:ok = $false
}
function Pass($message) {
    Write-Host "OK: $message" -ForegroundColor Green
}

Write-Host "=== Windows native CDM verify ===" -ForegroundColor Cyan

if (-not (Test-Path $windowsCdmPatch)) { Fail "tracked Windows CDM patch missing at $windowsCdmPatch" }
else { Pass "tracked Windows CDM patch present" }

if (-not (Test-Path $latexColorFile)) { Fail "latex2bbox_color.py missing at $latexColorFile" }
elseif (
    (Select-String -LiteralPath $latexColorFile -Pattern "_safe_temp_prefix" -SimpleMatch -Quiet) -and
    (Select-String -LiteralPath $latexColorFile -Pattern "stdout=subprocess.DEVNULL" -SimpleMatch -Quiet)
) { Pass "Windows CDM latex2bbox_color.py patch sentinels present" }
else { Fail "Windows CDM latex2bbox_color.py patch sentinels missing; re-run eval-infra\01-omnidocbench\setup.ps1" }

if (-not (Test-Path $texliveEnvFile)) { Fail "texlive_env.py missing at $texliveEnvFile" }
elseif (
    (Select-String -LiteralPath $texliveEnvFile -Pattern 'tlpkg", "tlgs", "bin"' -SimpleMatch -Quiet) -and
    (Select-String -LiteralPath $texliveEnvFile -Pattern "GS_LIB" -SimpleMatch -Quiet)
) { Pass "Windows CDM texlive_env.py patch sentinels present" }
else { Fail "Windows CDM texlive_env.py patch sentinels missing; re-run eval-infra\01-omnidocbench\setup.ps1" }

if (-not (Test-Path $venvPython)) { Fail ".venv Python missing at $venvPython" }
else { Pass ".venv Python present" }

$kpse = Get-Command kpsewhich -ErrorAction SilentlyContinue
if ($null -eq $kpse) { Fail "kpsewhich not found on PATH; add TeX Live bin directory to PATH" }
else {
    & $kpse.Source upgreek.sty *> $null
    if ($LASTEXITCODE -eq 0) { Pass "kpsewhich found upgreek.sty" }
    else { Fail "kpsewhich cannot find upgreek.sty; install the TeX Live package that provides it" }
}

$magick = Get-Command magick -ErrorAction SilentlyContinue
if ($null -eq $magick) { Fail "magick not found on PATH" }
else {
    $magickVersion = & $magick.Source -version 2>$null
    if ($LASTEXITCODE -eq 0) { Pass "magick is runnable: $($magickVersion[0])" }
    else { Fail "magick -version failed" }
}

$texRoot = ""
if ($kpse) {
    $pdflatexPath = & $kpse.Source -var-value=SELFAUTOPARENT 2>$null
    if ($LASTEXITCODE -eq 0) { $texRoot = (($pdflatexPath | Select-Object -First 1) -as [string]).Trim() }
}
if ($texRoot) {
    $tlgsBin = Join-Path $texRoot "tlpkg\tlgs\bin"
    $tlgsResource = Join-Path $texRoot "tlpkg\tlgs\Resource"
    if (Test-Path $tlgsBin) { Pass "TeX Live bundled Ghostscript bin present: $tlgsBin" }
    else { Write-Host "WARN: TeX Live bundled Ghostscript bin not found at $tlgsBin" -ForegroundColor Yellow }
    if (Test-Path $tlgsResource) { Pass "TeX Live bundled Ghostscript Resource present: $tlgsResource" }
    else { Write-Host "WARN: TeX Live bundled Ghostscript Resource not found at $tlgsResource" -ForegroundColor Yellow }
} else {
    Write-Host "WARN: could not resolve TeX Live root via kpsewhich SELFAUTOPARENT" -ForegroundColor Yellow
}

if ($ok -and (Test-Path $venvPython)) {
    $smoke = @"
import sys
from pathlib import Path

repo = Path(r"$rootDir")
odb = repo / "eval-infra" / "01-omnidocbench" / "OmniDocBench"
sys.path.insert(0, str(odb))
from src.metrics.cdm_metric import CDM

c = CDM(output_root=str(repo / "tmp" / "windows_cdm_verify"))
r = c.evaluate(
    r"a^2+b^2=c^2",
    r"a^2+b^2=c^2",
    "windows_native_smoke",
    sample_context={"img_id": "windows_native_smoke", "gt_idx": [0], "pred_idx": [0]},
)
f1 = float(r.get("F1_score", 0.0))
print(f"CDM F1_score for identical formulas: {f1}")
raise SystemExit(0 if f1 > 0.5 else 1)
"@
    $env:PYTHONUTF8 = "1"
    $smoke | & $venvPython -
    if ($LASTEXITCODE -eq 0) { Pass "CDM identical-formula smoke produced positive F1_score" }
    else { Fail "CDM identical-formula smoke failed or produced F1_score <= 0.5" }
}

if ($ok) {
    Write-Host ""
    Write-Host "VERIFY OK: Windows native CDM environment functional." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "VERIFY FAILED: Windows native CDM environment is not ready." -ForegroundColor Red
exit 1
