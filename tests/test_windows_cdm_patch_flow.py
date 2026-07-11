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
    assert 'preexec_fn = os.setsid if hasattr(os, "setsid") else None' in text
    assert "shutil.which(\"magick\")" in text
    assert "\"-output-directory={output_dir_arg}\"" in text
    assert "\"tlpkg\", \"tlgs\", \"bin\"" in text
    assert "GS_LIB" in text


def test_setup_applies_windows_cdm_patch_idempotently():
    text = read(SETUP)

    assert "windows-cdm.patch" in text
    assert "git -C $odbDir apply --reverse --check $windowsCdmPatch" in text
    assert "Windows native CDM patch already present" in text
    assert "git -C $odbDir apply --check $windowsCdmPatch" in text
    assert "Windows native CDM patch applied" in text


def test_verify_windows_checks_native_cdm_toolchain_and_smoke():
    assert VERIFY_WINDOWS.exists()
    text = read(VERIFY_WINDOWS)

    assert "patches\\omnidocbench\\windows-cdm.patch" in text
    assert "Test-Path $windowsCdmPatch" in text
    assert 'Fail "tracked Windows CDM patch missing' in text
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
    assert "[switch] $WindowsCdm" in text
    assert "SkipWindowsCdm" in text
    assert "-WindowsCdm" in text
    assert "if ($WindowsCdm -and -not $SkipWindowsCdm)" in text
    assert '"SKIP" "native Windows CDM requires -WindowsCdm"' in text
    assert "$previousErrorActionPreference = $ErrorActionPreference" in text
    assert '$ErrorActionPreference = "Continue"' in text
    assert "$ErrorActionPreference = $previousErrorActionPreference" in text
