<#
.SYNOPSIS
Full-chain verification of the OmniDocBench AMD Windows evaluation system.

.DESCRIPTION
Runs every per-module verify script in dependency order and aggregates the
results into one pass/fail report. It is the single command an agent (or human)
runs after the Step 0-4 provisioning in AGENTS.md to confirm the whole system
is wired up and producing real scores.

This is a VERIFICATION harness, not an installer. It assumes you have already
run the setup steps it checks. Each verify it invokes is itself idempotent and
side-effect-free, so re-running full-verify is always safe.

Order mirrors AGENTS.md's dependency chain:
  1. mirrors.env written            (detect-mirrors)
  2. WSL Ubuntu2204 reachable       (wsl-ensure)
  3. OmniDocBench code + dataset    (01-omnidocbench)
  4. CDM environment functional     (WSL via `score-cdm.sh`, or native Windows via `verify-windows.ps1` + `score.ps1 -Config v16-cdm.yaml`)
  5. VLM server + layout model      (paddleocr-vl-1.6/01-vlm-server + 02-layout-model)
  6. Predictions present            (adapter output)
  7. Scores present + non-zero      (03-scoring)
  8. Benchmark report valid         (04-benchmark, optional)

Steps that depend on optional setup (e.g. predictions exist only after the
adapter ran; CDM scores only after their selected path is run: WSL via
`score-cdm.sh`, or native Windows via `verify-windows.ps1` + `score.ps1 -Config
v16-cdm.yaml`) are reported as SKIP rather than FAIL when their inputs are
absent, so the core infra check still exits 0. Native full verification via
`-SkipWsl -WindowsCdm` runs the Windows CDM gate without WSL checks.

.PARAMETER SkipWsl
Skip the WSL checks, including setup.sh/verify.sh/score-cdm.sh checks; native
CDM can still be requested with `-WindowsCdm`.

.PARAMETER SkipVlm
Skip the VLM-server and prediction checks (use when verifying infra without a
model adapter provisioned yet).

.PARAMETER WindowsCdm
Run the native Windows CDM toolchain check. This is opt-in because it requires
the local TeX Live, ImageMagick, and Ghostscript toolchain.

.PARAMETER SkipWindowsCdm
Skip the native Windows CDM toolchain check, including when -WindowsCdm is set.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1
  powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 -SkipWsl
  powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 -WindowsCdm
  powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 -SkipWsl -WindowsCdm

Exit code 0 = all mandatory checks passed (optional ones either passed or were
legitimately skipped); 1 = at least one mandatory check failed.
#>
[CmdletBinding()]
param(
    [switch] $SkipWsl,
    [switch] $SkipVlm,
    [switch] $WindowsCdm,
    [switch] $SkipWindowsCdm
)
$ErrorActionPreference = "Stop"

# Repo root (this script is at <root>/scripts/full-verify.ps1). Nested Split-Path
# so this runs on Windows PowerShell 5.1 as well as PS 7+.
$rootDir = Split-Path -Parent $PSScriptRoot

# A check is one row of the report. Status: PASS / FAIL / SKIP.
$results = New-Object System.Collections.Generic.List[object]

function Add-Result($name, $status, $detail) {
    $results.Add([pscustomobject]@{ Check = $name; Status = $status; Detail = $detail })
    $color = @{ PASS = "Green"; FAIL = "Red"; SKIP = "Yellow" }[$status]
    Write-Host ("  [{0,-4}] {1,-42} {2}" -f $status, $name, $detail) -ForegroundColor $color
}

function Invoke-Verify($label, $file) {
    if (-not (Test-Path $file)) {
        Add-Result $label "SKIP" "verify script missing: $file"
        return "SKIP"
    }
    # Verifiers may emit non-fatal warnings on stderr. Evaluate their declared
    # process exit code instead of allowing PowerShell's Stop preference to
    # turn those warnings into terminating NativeCommandError records.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & powershell -ExecutionPolicy Bypass -File $file *> $null
        $verifyExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($verifyExit -eq 0) {
        Add-Result $label "PASS" ""
        return "PASS"
    } else {
        Add-Result $label "FAIL" "exit $verifyExit - re-run: powershell -File $file"
        return "FAIL"
    }
}

Write-Host "=== full-verify: OmniDocBench AMD Windows system check ===" -ForegroundColor Cyan
Write-Host ""

# --- 1. mirrors.env ----------------------------------------------------------
Write-Host "[1/8] network/mirrors" -ForegroundColor Cyan
$envFile = Join-Path $rootDir "mirrors.env"
if (Test-Path $envFile) {
    # @() forces array context so .Count is correct on PS 5.1 even when the
    # filter matches exactly one line (PS 5.1 unwraps a single-element pipeline
    # to a scalar, whose .Count is empty -- which would read as "0 sources").
    $keys = @(Get-Content $envFile | Where-Object { $_ -match "^[A-Z_]+=" }).Count
    if ($keys -ge 5) {
        Add-Result "mirrors.env" "PASS" "$keys sources recorded"
    } else {
        Add-Result "mirrors.env" "FAIL" "only $keys sources - re-run scripts/detect-mirrors.ps1"
    }
} else {
    Add-Result "mirrors.env" "FAIL" "missing - run scripts/detect-mirrors.ps1 (pitfalls.md#network)"
}

# --- 2. WSL ------------------------------------------------------------------
Write-Host ""
Write-Host "[2/8] WSL Ubuntu2204" -ForegroundColor Cyan
if ($SkipWsl) {
    Add-Result "WSL Ubuntu2204" "SKIP" "-SkipWsl"
} else {
    # Canonical distro name is Ubuntu2204 (every script here uses it). Be
    # defensive: if only the un-normalized "Ubuntu-22.04" exists (the name
    # `wsl --install` produces), flag it so the user runs wsl-ensure.ps1 to
    # rename it, rather than reporting a bare "not installed".
    $distros = (wsl --list --quiet 2>$null) | ForEach-Object { ($_ -replace "`0","").Trim() } | Where-Object { $_ }
    $distroText = ($distros -join "`n")
    if ($distroText -match "Ubuntu2204") {
        $probe = wsl -d Ubuntu2204 -- echo "WSL_OK" 2>$null
        if ($probe -match "WSL_OK") {
            Add-Result "WSL Ubuntu2204" "PASS" "reachable"
        } else {
            Add-Result "WSL Ubuntu2204" "FAIL" "imported but not startable - reboot Windows? (pitfalls.md#wsl)"
        }
    } elseif ($distroText -match "Ubuntu-22\.04") {
        Add-Result "WSL Ubuntu2204" "FAIL" "only 'Ubuntu-22.04' exists - run scripts/wsl-ensure.ps1 to normalize the name to Ubuntu2204"
    } else {
        Add-Result "WSL Ubuntu2204" "FAIL" "not installed - run scripts/wsl-ensure.ps1"
    }
}

# --- 3. OmniDocBench code + dataset -----------------------------------------
Write-Host ""
Write-Host "[3/8] OmniDocBench code + dataset" -ForegroundColor Cyan
$odbVerify = Join-Path $rootDir "eval-infra\01-omnidocbench\verify.ps1"
[void](Invoke-Verify "01-omnidocbench/verify" $odbVerify)

# --- 4. CDM environment (WSL) ------------------------------------------------
Write-Host ""
Write-Host "[4/8] CDM environment (WSL)" -ForegroundColor Cyan
if ($SkipWsl) {
    Add-Result "02-cdm-environment/verify" "SKIP" "-SkipWsl"
} else {
    $cdmVerify = Join-Path $rootDir "eval-infra\02-cdm-environment\verify.sh"
    # Translate a Windows path C:\...\verify.sh to its WSL form /mnt/c/.../verify.sh.
    $wslPath = "/mnt/" + $cdmVerify.Substring(0,1).ToLower() + (($cdmVerify.Substring(2)) -replace '\\', '/')
    # Capture stdout+stderr together. Relying on $LASTEXITCODE alone is NOT
    # enough: WSL interop can report a 0 exit even when the CDM pipeline is
    # subtly broken (e.g. a stage failed but the script's `set -e` didn't
    # propagate, or stderr noise masked the real status). verify.sh prints the
    # literal sentinel "VERIFY OK" only on genuine success, so we require BOTH
    # a clean exit AND the sentinel in the output.
    $output = wsl -d Ubuntu2204 bash $wslPath 2>&1
    $wslExit = $LASTEXITCODE
    # Normalize the captured stream to a single string for -match. @() + -join
    # keeps PS 5.1 happy when $output is a scalar or an array of lines.
    $outputText = (@($output) -join "`n")
    if ($wslExit -ne 0) {
        Add-Result "02-cdm-environment/verify" "FAIL" "WSL verify exited $wslExit - see pitfalls.md#cdm-zero (decision tree)"
    } elseif ($outputText -notmatch "VERIFY OK") {
        Add-Result "02-cdm-environment/verify" "FAIL" "exited 0 but no 'VERIFY OK' sentinel - CDM not actually functional (pitfalls.md#cdm-zero)"
    } else {
        Add-Result "02-cdm-environment/verify" "PASS" "CDM pipeline functional (VERIFY OK)"
    }
}

# --- 4b. CDM environment (Windows native) -----------------------------------
# Windows native CDM verification is independent of the WSL CDM check above.
Write-Host ""
Write-Host "[4b/8] CDM environment (Windows native)" -ForegroundColor Cyan
if ($WindowsCdm -and -not $SkipWindowsCdm) {
    $winCdmVerify = Join-Path $rootDir "eval-infra\02-cdm-environment\verify-windows.ps1"
    [void](Invoke-Verify "02-cdm-environment/verify-windows" $winCdmVerify)
} elseif ($SkipWindowsCdm) {
    Add-Result "02-cdm-environment/verify-windows" "SKIP" "-SkipWindowsCdm"
} else {
    Add-Result "02-cdm-environment/verify-windows" "SKIP" "native Windows CDM requires -WindowsCdm"
}

# --- 5. VLM server + layout model (reference adapter) ------------------------
Write-Host ""
Write-Host "[5/8] VLM server + layout model (reference adapter)" -ForegroundColor Cyan
if ($SkipVlm) {
    Add-Result "01-vlm-server/verify" "SKIP" "-SkipVlm"
    Add-Result "02-layout-model/verify" "SKIP" "-SkipVlm"
} else {
    $vlmVerify = Join-Path $rootDir "adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1"
    [void](Invoke-Verify "01-vlm-server/verify" $vlmVerify)
    # The reference adapter has a second provisioning half (PP-DocLayoutV3 ONNX);
    # verify it too so a missing layout model is caught here, not mid-run.
    $layoutVerify = Join-Path $rootDir "adapters\paddleocr-vl-1.6\02-layout-model\verify.ps1"
    [void](Invoke-Verify "02-layout-model/verify" $layoutVerify)
}

# --- 6. Predictions present --------------------------------------------------
Write-Host ""
Write-Host "[6/8] adapter predictions" -ForegroundColor Cyan
if ($SkipVlm) {
    Add-Result "predictions/paddleocrvl_rocm" "SKIP" "-SkipVlm"
} else {
    # predictions/paddleocrvl_rocm is the dir the committed configs (v16*.yaml)
    # read from -- keep this in sync with eval-infra/01-omnidocbench/configs/.
    $predDir = Join-Path $rootDir "predictions\paddleocrvl_rocm"
    $count = 0
    if (Test-Path $predDir) {
        # @(): Get-ChildItem returns a scalar (not array) for one match on PS
        # 5.1, and $null for a missing dir; @() normalizes both to an array so
        # .Count is correct.
        $count = @(Get-ChildItem $predDir -Filter *.md -File -ErrorAction SilentlyContinue).Count
    }
    # Derive the expected count from the actual dataset: count page images in
    # eval-infra\01-omnidocbench\data\images\ and require the prediction count
    # to be >= 95% of that (tolerance for a few failed pages). This replaces a
    # hardcoded >= 1000 magic number that gave a false FAIL on the 296-page
    # hard subset and a false PASS on a 1001/1651 partial full-set run.
    $imgDir = Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"
    $expected = 0
    if (Test-Path $imgDir) {
        $expected = @(Get-ChildItem $imgDir -Include *.png,*.jpg,*.jpeg,*.bmp,*.tif,*.tiff -File -Recurse -ErrorAction SilentlyContinue).Count
    }
    if ($expected -eq 0) {
        # Dataset images not present (e.g. running infra-only verification).
        # Fall back to a loose non-zero check so we don't spuriously FAIL when
        # there is simply no dataset to count against.
        $expected = $count
    }
    # Tolerance: require >= 95% of the image count (allows a handful of failed
    # pages without flagging a complete-enough run). At least 1 required.
    $threshold = [int][Math]::Max(1, [Math]::Floor(0.95 * $expected))
    if ($count -ge $threshold) {
        Add-Result "predictions/paddleocrvl_rocm" "PASS" "$count .md files (expected ~$expected)"
    } elseif ($count -gt 0) {
        Add-Result "predictions/paddleocrvl_rocm" "FAIL" "only $count .md (expected ~$expected, threshold $threshold) - re-run run_adapter.py"
    } else {
        Add-Result "predictions/paddleocrvl_rocm" "FAIL" "none - run the adapter (adapters/paddleocr-vl-1.6/run_adapter.py)"
    }
}

# --- 7. Scores present + non-zero -------------------------------------------
Write-Host ""
Write-Host "[7/8] scoring results" -ForegroundColor Cyan
$scoreVerify = Join-Path $rootDir "eval-infra\03-scoring\verify.ps1"
[void](Invoke-Verify "03-scoring/verify" $scoreVerify)

# --- 8. Benchmark report (optional - skip if not run) -----------------------
Write-Host ""
Write-Host "[8/8] benchmark report" -ForegroundColor Cyan
$benchVerify = Join-Path $rootDir "eval-infra\04-benchmark\verify.ps1"
if (Test-Path $benchVerify) {
    # Find most recent benchmark results directory
    $benchDirs = @(Get-ChildItem (Join-Path $rootDir "benchmark-results") -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne "reference" } | Sort-Object LastWriteTime -Descending)
    if ($benchDirs.Count -gt 0) {
        $latestBench = $benchDirs[0].FullName
        [void](Invoke-Verify "04-benchmark/verify" "$benchVerify -ReportDir '$latestBench'")
    } else {
        Add-Result "04-benchmark/verify" "SKIP" "no benchmark runs found"
    }
} else {
    Add-Result "04-benchmark/verify" "SKIP" "verify script not present"
}

# --- Summary -----------------------------------------------------------------
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize | Out-Host

# CRITICAL: wrap in @() so .Count is correct on Windows PowerShell 5.1.
# PS 5.1 unwraps a single-element pipeline result to a scalar object, whose
# .Count is empty (not 1). Without @() the harness reports "0 failed" and
# exits 0 even when exactly one check failed -- the most common case.
$failed  = @($results | Where-Object { $_.Status -eq "FAIL" }).Count
$passed  = @($results | Where-Object { $_.Status -eq "PASS" }).Count
$skipped = @($results | Where-Object { $_.Status -eq "SKIP" }).Count
Write-Host ("{0} passed, {1} failed, {2} skipped" -f $passed, $failed, $skipped)

if ($failed -gt 0) {
    Write-Host ""
    Write-Host "FAILED checks - fix per the Detail column / docs/pitfalls.md, then re-run full-verify.ps1." -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "ALL CHECKS PASSED (skips were optional). The evaluation system is operational." -ForegroundColor Green
exit 0
