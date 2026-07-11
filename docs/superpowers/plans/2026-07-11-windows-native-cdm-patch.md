# Windows Native CDM Patch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track, auto-apply, verify, and document the Windows-native OmniDocBench CDM patch so the repo has a reproducible evaluation-quality loop.

**Architecture:** The root-level `patches/omnidocbench/windows-cdm.patch` is the source of truth for the two upstream OmniDocBench CDM changes. `eval-infra/01-omnidocbench/setup.ps1` applies it idempotently to the generated checkout, `eval-infra/02-cdm-environment/verify-windows.ps1` proves the native CDM toolchain works, and docs/runbooks describe both WSL and Windows-native CDM paths.

**Tech Stack:** PowerShell 5.1-compatible scripts, Git patch application, Python 3.10/3.11 + pytest for static repo tests, local TeX Live/ImageMagick/Ghostscript for operational CDM verification.

## Global Constraints

- Use option A from the approved design: create `patches/omnidocbench/windows-cdm.patch`.
- Do not commit generated OmniDocBench checkouts, datasets, predictions, logs, zip files, or local debug scratch files.
- Preserve existing untracked files in the working tree unless the user explicitly asks to remove them.
- Verification conclusions must cite commands, exit codes, and key evidence output.
- Native Windows CDM is supported only when the tracked patch and TeX Live/ImageMagick/Ghostscript checks pass.
- WSL CDM remains a supported compatibility/reference path.
- CDM F1 `0` is not a success condition.

---

## File Structure

- Create `patches/omnidocbench/windows-cdm.patch`: tracked upstream OmniDocBench diff for `latex2bbox_color.py` and `texlive_env.py`.
- Create `tests/test_windows_cdm_patch_flow.py`: static tests for patch source, setup integration, verifier coverage, and docs wording.
- Modify `eval-infra/01-omnidocbench/setup.ps1`: apply `windows-cdm.patch` after existing OmniDocBench patches.
- Create `eval-infra/02-cdm-environment/verify-windows.ps1`: native Windows CDM toolchain and smoke verifier.
- Modify `scripts/full-verify.ps1`: add optional native CDM verification without forcing WSL.
- Modify `README.md`, `README.zh-CN.md`, `AGENTS.md`, `docs/architecture.md`, `docs/pitfalls.md`, `eval-infra/01-omnidocbench/README.md`, `eval-infra/02-cdm-environment/README.md`, and `eval-infra/03-scoring/README.md`: update runbook and stale "WSL only" claims.

---

### Task 1: Track The Windows CDM Patch

**Files:**
- Create: `tests/test_windows_cdm_patch_flow.py`
- Create: `patches/omnidocbench/windows-cdm.patch`

**Interfaces:**
- Consumes: local patch source at `C:\Users\rocm\Desktop\OmniDocBench`
- Produces: `patches/omnidocbench/windows-cdm.patch`, later consumed by `setup.ps1`

- [ ] **Step 1: Write the failing patch source test**

Create `tests/test_windows_cdm_patch_flow.py` with this content:

```python
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH = REPO_ROOT / "patches" / "omnidocbench" / "windows-cdm.patch"
SETUP = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "setup.ps1"
VERIFY_WINDOWS = REPO_ROOT / "eval-infra" / "02-cdm-environment" / "verify-windows.ps1"
FULL_VERIFY = REPO_ROOT / "scripts" / "full-verify.ps1"
DOC_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.zh-CN.md",
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "pitfalls.md",
    REPO_ROOT / "eval-infra" / "01-omnidocbench" / "README.md",
    REPO_ROOT / "eval-infra" / "02-cdm-environment" / "README.md",
    REPO_ROOT / "eval-infra" / "03-scoring" / "README.md",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_windows_cdm_patch_exists_and_targets_only_cdm_toolchain_files():
    assert PATCH.exists()
    text = read(PATCH)

    assert "src/metrics/cdm/modules/latex2bbox_color.py" in text
    assert "src/metrics/cdm/modules/texlive_env.py" in text
    assert "pdf_validation.py" not in text
    assert "result/" not in text
    assert "predictions/" not in text


def test_windows_cdm_patch_contains_command_and_toolchain_fixes():
    text = read(PATCH)

    assert "_safe_temp_prefix" in text
    assert "stdout=subprocess.DEVNULL" in text
    assert "stderr=subprocess.DEVNULL" in text
    assert "shutil.which(\"magick\")" in text
    assert "\"-output-directory={output_dir_arg}\"" in text
    assert "\"tlpkg\", \"tlgs\", \"bin\"" in text
    assert "GS_LIB" in text
```

- [ ] **Step 2: Run the patch source test and verify it fails**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_windows_cdm_patch_exists_and_targets_only_cdm_toolchain_files -q
```

Expected: fail with `AssertionError` because `patches/omnidocbench/windows-cdm.patch` does not exist.

- [ ] **Step 3: Create the tracked patch directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path patches\omnidocbench | Out-Null
```

Expected: command exits `0`.

- [ ] **Step 4: Generate the patch from the local OmniDocBench checkout**

Run:

```powershell
git -C 'C:\Users\rocm\Desktop\OmniDocBench' diff -- src/metrics/cdm/modules/latex2bbox_color.py src/metrics/cdm/modules/texlive_env.py | Set-Content -LiteralPath patches\omnidocbench\windows-cdm.patch -Encoding UTF8
```

Expected: `patches\omnidocbench\windows-cdm.patch` exists and contains only the two target files.

- [ ] **Step 5: Run the patch source tests and verify they pass**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_windows_cdm_patch_exists_and_targets_only_cdm_toolchain_files tests\test_windows_cdm_patch_flow.py::test_windows_cdm_patch_contains_command_and_toolchain_fixes -q
```

Expected: `2 passed`.

- [ ] **Step 6: Check that the patch applies to the generated checkout or is already present**

Run:

```powershell
$odb = 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\eval-infra\01-omnidocbench\OmniDocBench'
$patch = 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\patches\omnidocbench\windows-cdm.patch'
git -C $odb apply --check $patch
if ($LASTEXITCODE -ne 0) {
    Select-String -LiteralPath "$odb\src\metrics\cdm\modules\latex2bbox_color.py" -Pattern '_safe_temp_prefix','stdout=subprocess.DEVNULL' -SimpleMatch
    Select-String -LiteralPath "$odb\src\metrics\cdm\modules\texlive_env.py" -Pattern 'GS_LIB','tlpkg", "tlgs", "bin"' -SimpleMatch
}
```

Expected: either `git apply --check` exits `0`, or both files already contain the sentinel strings.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add -- tests\test_windows_cdm_patch_flow.py patches\omnidocbench\windows-cdm.patch
git commit -m "test: track windows native cdm patch"
```

Expected: commit succeeds with only these two paths staged.

---

### Task 2: Apply The Patch In setup.ps1

**Files:**
- Modify: `tests/test_windows_cdm_patch_flow.py`
- Modify: `eval-infra/01-omnidocbench/setup.ps1`

**Interfaces:**
- Consumes: `patches/omnidocbench/windows-cdm.patch`
- Produces: an idempotent setup section that applies or detects the Windows CDM patch

- [ ] **Step 1: Add the setup integration test**

Append this test to `tests/test_windows_cdm_patch_flow.py`:

```python
def test_setup_applies_windows_cdm_patch_idempotently():
    text = read(SETUP)

    assert "windows-cdm.patch" in text
    assert "_safe_temp_prefix" in text
    assert "stdout=subprocess.DEVNULL" in text
    assert "tlpkg\", \"tlgs\", \"bin\"" in text
    assert "GS_LIB" in text
    assert "Windows native CDM patch already present" in text
    assert "Windows native CDM patch applied" in text
```

- [ ] **Step 2: Run the setup integration test and verify it fails**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_setup_applies_windows_cdm_patch_idempotently -q
```

Expected: fail because `setup.ps1` does not reference `windows-cdm.patch`.

- [ ] **Step 3: Add root patch path variables to setup.ps1**

In `eval-infra/01-omnidocbench/setup.ps1`, after:

```powershell
$patchDir = Join-Path $PSScriptRoot "patches"
$formulaPatch = Join-Path $patchDir "0001-formula-cdm-normalization.patch"
$timeoutPatch = Join-Path $patchDir "0002-timeout-fallback-long-text-span.patch"
```

insert:

```powershell
$rootPatchDir = Join-Path $rootDir "patches\omnidocbench"
$windowsCdmPatch = Join-Path $rootPatchDir "windows-cdm.patch"
```

- [ ] **Step 4: Add the Windows CDM patch application section**

In `eval-infra/01-omnidocbench/setup.ps1`, after the timeout patch block and before the `.venv` setup section, insert:

```powershell
if (Test-Path $windowsCdmPatch) {
    $latexColorFile = Join-Path $odbDir "src\metrics\cdm\modules\latex2bbox_color.py"
    $texliveEnvFile = Join-Path $odbDir "src\metrics\cdm\modules\texlive_env.py"
    $windowsCdmApplied = (
        (Test-Path $latexColorFile) -and
        (Test-Path $texliveEnvFile) -and
        (Select-String -LiteralPath $latexColorFile -Pattern "_safe_temp_prefix" -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $latexColorFile -Pattern "stdout=subprocess.DEVNULL" -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $texliveEnvFile -Pattern 'tlpkg", "tlgs", "bin"' -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $texliveEnvFile -Pattern "GS_LIB" -SimpleMatch -Quiet)
    )
    if ($windowsCdmApplied) {
        Write-Host "Windows native CDM patch already present." -ForegroundColor Green
    } else {
        Write-Host "Applying Windows native CDM patch ..." -ForegroundColor Cyan
        git -C $odbDir apply --check $windowsCdmPatch
        if ($LASTEXITCODE -ne 0) {
            throw "Windows native CDM patch does not apply cleanly. Inspect $windowsCdmPatch and $odbDir."
        }
        git -C $odbDir apply $windowsCdmPatch
        if ($LASTEXITCODE -ne 0) { throw "Windows native CDM patch failed." }
        Write-Host "Windows native CDM patch applied." -ForegroundColor Green
    }
} else {
    Write-Host "WARN: Windows native CDM patch missing: $windowsCdmPatch" -ForegroundColor Yellow
}
```

- [ ] **Step 5: Run the setup integration test and verify it passes**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_setup_applies_windows_cdm_patch_idempotently -q
```

Expected: `1 passed`.

- [ ] **Step 6: Run setup in code-only mode**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1 -SkipDataset
```

Expected: exit code `0`; output contains either `Windows native CDM patch applied.` or `Windows native CDM patch already present.`

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add -- tests\test_windows_cdm_patch_flow.py eval-infra\01-omnidocbench\setup.ps1
git commit -m "fix: apply windows native cdm patch in setup"
```

Expected: commit succeeds with only these two paths staged.

---

### Task 3: Add Native Windows CDM Verification

**Files:**
- Modify: `tests/test_windows_cdm_patch_flow.py`
- Create: `eval-infra/02-cdm-environment/verify-windows.ps1`
- Modify: `scripts/full-verify.ps1`

**Interfaces:**
- Consumes: patched OmniDocBench checkout and repo `.venv`
- Produces: `verify-windows.ps1`, exit `0` only when native Windows CDM is functional

- [ ] **Step 1: Add static verifier tests**

Append these tests to `tests/test_windows_cdm_patch_flow.py`:

```python
def test_verify_windows_checks_native_cdm_toolchain_and_smoke():
    assert VERIFY_WINDOWS.exists()
    text = read(VERIFY_WINDOWS)

    assert "kpsewhich" in text
    assert "upgreek.sty" in text
    assert "magick" in text
    assert "tlpkg" in text
    assert "tlgs" in text
    assert "GS_LIB" in text
    assert "src.metrics.cdm_metric" in text
    assert "F1_score" in text
    assert "VERIFY OK: Windows native CDM environment functional." in text


def test_full_verify_can_run_windows_native_cdm_without_wsl():
    text = read(FULL_VERIFY)

    assert "Windows native CDM" in text
    assert "verify-windows.ps1" in text
    assert "SkipWindowsCdm" in text
```

- [ ] **Step 2: Run the verifier tests and verify they fail**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_verify_windows_checks_native_cdm_toolchain_and_smoke tests\test_windows_cdm_patch_flow.py::test_full_verify_can_run_windows_native_cdm_without_wsl -q
```

Expected: fail because `verify-windows.ps1` and `SkipWindowsCdm` do not exist.

- [ ] **Step 3: Create verify-windows.ps1**

Create `eval-infra/02-cdm-environment/verify-windows.ps1` with this content:

```powershell
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
```

- [ ] **Step 4: Add full-verify switches and native CDM check**

In `scripts/full-verify.ps1`, update the param block from:

```powershell
param(
    [switch] $SkipWsl,
    [switch] $SkipVlm
)
```

to:

```powershell
param(
    [switch] $SkipWsl,
    [switch] $SkipVlm,
    [switch] $SkipWindowsCdm
)
```

After the WSL CDM environment section, insert:

```powershell
# --- 4b. CDM environment (Windows native) -----------------------------------
Write-Host ""
Write-Host "[4b/8] CDM environment (Windows native)" -ForegroundColor Cyan
if ($SkipWindowsCdm) {
    Add-Result "02-cdm-environment/verify-windows" "SKIP" "-SkipWindowsCdm"
} else {
    $winCdmVerify = Join-Path $rootDir "eval-infra\02-cdm-environment\verify-windows.ps1"
    [void](Invoke-Verify "02-cdm-environment/verify-windows" $winCdmVerify)
}
```

Update the help text to mention:

```powershell
.PARAMETER SkipWindowsCdm
Skip the native Windows CDM toolchain check.
```

- [ ] **Step 5: Run static verifier tests**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_verify_windows_checks_native_cdm_toolchain_and_smoke tests\test_windows_cdm_patch_flow.py::test_full_verify_can_run_windows_native_cdm_without_wsl -q
```

Expected: `2 passed`.

- [ ] **Step 6: Run native Windows CDM verifier**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1
```

Expected: exit code `0`; output contains `VERIFY OK: Windows native CDM environment functional.` and a positive `CDM F1_score for identical formulas`.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add -- tests\test_windows_cdm_patch_flow.py eval-infra\02-cdm-environment\verify-windows.ps1 scripts\full-verify.ps1
git commit -m "test: verify windows native cdm toolchain"
```

Expected: commit succeeds with only these three paths staged.

---

### Task 4: Update Runbooks And Architecture Docs

**Files:**
- Modify: `tests/test_windows_cdm_patch_flow.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/pitfalls.md`
- Modify: `eval-infra/01-omnidocbench/README.md`
- Modify: `eval-infra/02-cdm-environment/README.md`
- Modify: `eval-infra/03-scoring/README.md`

**Interfaces:**
- Consumes: Windows patch and verifier introduced in Tasks 1-3
- Produces: docs that tell users how to reproduce native Windows CDM and when to use WSL

- [ ] **Step 1: Add docs wording tests**

Append these tests to `tests/test_windows_cdm_patch_flow.py`:

```python
def test_docs_describe_windows_native_cdm_and_keep_wsl_reference_path():
    combined = "\n".join(read(path) for path in DOC_FILES)

    assert "windows-cdm.patch" in combined
    assert "verify-windows.ps1" in combined
    assert "Windows-native CDM" in combined or "Windows native CDM" in combined
    assert "WSL CDM remains" in combined or "WSL CDM" in combined
    assert "official_cdm_rerun_20260711_092548.log" in combined
    assert "CDM samples" in combined
```

- [ ] **Step 2: Run docs wording test and verify it fails**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_docs_describe_windows_native_cdm_and_keep_wsl_reference_path -q
```

Expected: fail because docs do not yet mention `windows-cdm.patch` and `verify-windows.ps1`.

- [ ] **Step 3: Update quick-start docs**

Edit `README.md` and `README.zh-CN.md` so the quick start shows:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1
```

Add a short note near the CDM setup section:

```text
Windows-native CDM is supported when `patches/omnidocbench/windows-cdm.patch`
has been applied by `eval-infra/01-omnidocbench/setup.ps1` and
`eval-infra/02-cdm-environment/verify-windows.ps1` passes. WSL CDM remains the
compatibility/reference path for machines where the native TeX Live/ImageMagick
toolchain is not provisioned.
```

In the Chinese README, use:

```text
Windows 原生 CDM 已受支持：`eval-infra/01-omnidocbench/setup.ps1` 会自动应用
`patches/omnidocbench/windows-cdm.patch`，并由
`eval-infra/02-cdm-environment/verify-windows.ps1` 验证。WSL CDM 仍保留为兼容
和 reference 路线。
```

- [ ] **Step 4: Update AGENTS.md**

Replace the stale rule:

```text
- **WSL for CDM**: CDM is POSIX-only. Never attempt CDM on Windows-native.
```

with:

```text
- **CDM paths**: Prefer Windows-native CDM when `verify-windows.ps1` passes after
  `windows-cdm.patch` is applied. Use WSL CDM as the compatibility/reference
  path when the native TeX Live/ImageMagick/Ghostscript toolchain is absent.
```

Add the evidence line:

```text
Latest local Windows-native official-engine CDM evidence:
`C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm\logs\official_cdm_rerun_20260711_092548.log`
reports Text Edit-distance `0.034`, Reading-order Edit-distance `0.129`,
Table TEDS `94.24`, Formula CDM `96.50`, CDM samples `2352`, timeout `0`,
exception `0`.
```

- [ ] **Step 5: Update architecture and pitfall docs**

In `docs/architecture.md`, replace the absolute "CDM runs in WSL, everything else runs Windows-native" statement with:

```text
CDM has two supported toolchain paths. Windows-native CDM is the local fast path
when `windows-cdm.patch` is applied and `verify-windows.ps1` passes. WSL CDM
remains the compatibility/reference path with an isolated Linux TeX Live,
ImageMagick, and Ghostscript stack.
```

In `docs/pitfalls.md`, update the Windows `FileNotFoundError: kpsewhich/magick/gs` entry to mention:

```text
First run `powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1`.
If it fails, follow the reported missing tool or use the WSL CDM path.
```

- [ ] **Step 6: Update module READMEs**

In `eval-infra/01-omnidocbench/README.md`, add a patch row:

```text
| Windows CDM patch | `patches/omnidocbench/windows-cdm.patch` | auto-applied by `setup.ps1`; verified by `verify-windows.ps1` |
```

In `eval-infra/02-cdm-environment/README.md`, add `verify-windows.ps1` to the scripts list:

```text
- **`verify-windows.ps1`** - native Windows CDM verifier. Run from PowerShell
  after `eval-infra/01-omnidocbench/setup.ps1`; it checks patch sentinels,
  TeX Live, ImageMagick, Ghostscript discovery, and a real CDM smoke test.
```

In `eval-infra/03-scoring/README.md`, replace "So CDM must run in WSL" with:

```text
Historically CDM had to run in WSL. This repo now also supports Windows-native
CDM after `windows-cdm.patch` is applied and `verify-windows.ps1` passes. WSL
CDM remains the compatibility/reference path.
```

- [ ] **Step 7: Run docs wording test**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py::test_docs_describe_windows_native_cdm_and_keep_wsl_reference_path -q
```

Expected: `1 passed`.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add -- tests\test_windows_cdm_patch_flow.py README.md README.zh-CN.md AGENTS.md docs\architecture.md docs\pitfalls.md eval-infra\01-omnidocbench\README.md eval-infra\02-cdm-environment\README.md eval-infra\03-scoring\README.md
git commit -m "docs: document windows native cdm path"
```

Expected: commit succeeds with only these paths staged.

---

### Task 5: Final Verification And Evidence Report

**Files:**
- No new source files required.
- The final response must cite verification data.

**Interfaces:**
- Consumes: completed Tasks 1-4
- Produces: verified repo state and evidence-backed final conclusion

- [ ] **Step 1: Run all static tests for the new flow**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_windows_cdm_patch_flow.py -q
```

Expected: all tests in `tests/test_windows_cdm_patch_flow.py` pass.

- [ ] **Step 2: Run existing repo tests**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests -q
```

Expected: all tests pass. If a test fails due to missing optional runtime, record the exact failing test and error.

- [ ] **Step 3: Run whitespace validation**

Run:

```powershell
git diff --check
```

Expected: exit code `0` with no output.

- [ ] **Step 4: Run setup code-only verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1 -SkipDataset
```

Expected: exit code `0`; output contains either `Windows native CDM patch applied.` or `Windows native CDM patch already present.`

- [ ] **Step 5: Run OmniDocBench code/dataset verifier**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1
```

Expected: exit code `0`; output contains `VERIFY OK: OmniDocBench code + dataset ready.`

- [ ] **Step 6: Run native Windows CDM verifier**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1
```

Expected: exit code `0`; output contains:

```text
VERIFY OK: Windows native CDM environment functional.
CDM F1_score for identical formulas: a numeric value greater than 0.5
```

- [ ] **Step 7: Run full verifier in the native CDM mode**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 -SkipWsl
```

Expected: exit code `0` when local VLM/prediction/score artifacts are present. If adapter or benchmark artifacts are absent, rerun with the existing skip switches and record the resulting PASS/SKIP/FAIL summary:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 -SkipWsl -SkipVlm
```

- [ ] **Step 8: Inspect final git status**

Run:

```powershell
git status --short --branch
```

Expected: only known pre-existing untracked files remain, or the working tree is clean except intentionally untracked local artifacts.

- [ ] **Step 9: Push the completed branch**

Run:

```powershell
git push origin main
```

Expected: push succeeds to the configured `omnidocbench-amd-windows` remote. In this workspace, `git remote -v` reports `https://github.com/AIwork4me/omnidocbench-amd-windows.git`.

- [ ] **Step 10: Final response with evidence**

Report:

```text
Changed files:
- patches/omnidocbench/windows-cdm.patch
- tests/test_windows_cdm_patch_flow.py
- eval-infra/01-omnidocbench/setup.ps1
- eval-infra/02-cdm-environment/verify-windows.ps1
- scripts/full-verify.ps1
- README.md
- README.zh-CN.md
- AGENTS.md
- docs/architecture.md
- docs/pitfalls.md
- eval-infra/01-omnidocbench/README.md
- eval-infra/02-cdm-environment/README.md
- eval-infra/03-scoring/README.md

Verification:
- python -m pytest tests/test_windows_cdm_patch_flow.py -q -> exit 0; key output: all tests passed
- python -m pytest tests -q -> exit 0; key output: all tests passed
- git diff --check -> exit 0; key output: no output
- powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1 -SkipDataset -> exit 0; key output: Windows native CDM patch applied or already present
- powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1 -> exit 0; key output: VERIFY OK: OmniDocBench code + dataset ready.
- powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1 -> exit 0; key output: VERIFY OK: Windows native CDM environment functional.

Conclusion:
- Windows-native CDM patch is tracked at patches/omnidocbench/windows-cdm.patch.
- setup.ps1 applies/detects it idempotently.
- verify-windows.ps1 proves or rejects local native CDM readiness.
- Remaining limitations: write "none observed after verification" if every command passed; otherwise list each failed or skipped command with the exact reason.
```

The final response must not claim success for any command that was not run.
