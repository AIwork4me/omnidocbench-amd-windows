from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH = REPO_ROOT / "patches" / "omnidocbench" / "windows-cdm.patch"
SETUP = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "setup.ps1"
VERIFY_WINDOWS = REPO_ROOT / "eval-infra" / "02-cdm-environment" / "verify-windows.ps1"
FULL_VERIFY = REPO_ROOT / "scripts" / "full-verify.ps1"
SCORING_README = REPO_ROOT / "eval-infra" / "03-scoring" / "README.md"
SCORE_PS1 = REPO_ROOT / "eval-infra" / "03-scoring" / "score.ps1"
SCORE_CDM_SH = REPO_ROOT / "eval-infra" / "03-scoring" / "score-cdm.sh"
DOC_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.zh-CN.md",
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "pitfalls.md",
    REPO_ROOT / "eval-infra" / "01-omnidocbench" / "README.md",
    REPO_ROOT / "eval-infra" / "02-cdm-environment" / "README.md",
    REPO_ROOT / "eval-infra" / "03-scoring" / "README.md",
    REPO_ROOT / "eval-infra" / "README.md",
    REPO_ROOT / "docs" / "wechat-article.md",
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


def test_pitfalls_limits_wsl_only_warning_to_shell_scripts_and_names_native_verifier():
    text = read(REPO_ROOT / "docs" / "pitfalls.md")
    normalized = " ".join(text.split())

    assert "Nothing in `eval-infra/02-cdm-environment`" not in text
    assert "`setup.sh`, `verify.sh`, and `score-cdm.sh`" in normalized
    assert "`verify-windows.ps1`" in text
    assert "native verifier" in text


def test_full_verify_help_documents_skip_wsl_native_cdm_semantics_and_command():
    text = read(FULL_VERIFY)
    normalized = " ".join(text.split())

    assert "Skip the WSL checks" in text
    assert "native CDM can still be requested with `-WindowsCdm`" in normalized
    assert (
        "powershell -ExecutionPolicy Bypass -File "
        "scripts\\full-verify.ps1 -SkipWsl -WindowsCdm"
    ) in normalized


def test_scoring_readme_documents_native_and_wsl_cdm_scoring_paths():
    text = read(SCORING_README)

    assert "windows-cdm.patch" in text
    assert "verify-windows.ps1" in text
    assert (
        "powershell -ExecutionPolicy Bypass -File "
        "eval-infra\\03-scoring\\score.ps1 -Config v16-cdm.yaml"
    ) in text
    assert "score-cdm.sh" in text
    assert "wsl -d Ubuntu2204 bash" in text
    assert "Did you run in WSL (not Windows)?" not in text


def test_executable_scoring_guidance_describes_native_and_wsl_cdm_paths():
    score_ps1 = read(SCORE_PS1)
    score_cdm_sh = read(SCORE_CDM_SH)

    assert "Edit_dist + TEDS or CDM (Windows-native)" in score_ps1
    assert "v16-cdm.yaml" in score_ps1
    assert "windows-cdm.patch" in score_ps1
    assert "verify-windows.ps1" in score_ps1
    assert "WSL compatibility/reference CDM path" in score_cdm_sh
    assert "Native Windows CDM is available via score.ps1 with a CDM config" in score_cdm_sh
    assert "verify-windows.ps1" in score_cdm_sh


def test_docs_describe_windows_native_cdm_and_keep_wsl_reference_path():
    combined = "\n".join(read(path) for path in DOC_FILES)
    readme = read(REPO_ROOT / "README.md")
    readme_zh = read(REPO_ROOT / "README.zh-CN.md")

    assert "windows-cdm.patch" in combined
    assert "verify-windows.ps1" in combined
    assert "Windows-native CDM" in combined or "Windows native CDM" in combined
    assert "WSL CDM remains" in combined or "WSL CDM" in combined
    assert "official_cdm_rerun_20260711_092548.log" in combined
    assert "CDM samples" in combined
    assert "Optional native-CDM verification" in readme
    assert "可选的原生 CDM 验证" in readme_zh
    assert "CDM 有两条受支持的工具链路径" in readme_zh
    assert "Windows 原生 CDM 是应用 `windows-cdm.patch` 并通过 `verify-windows.ps1` 后的本地快速路径" in readme_zh
    assert "WSL CDM 仍是兼容性/参考路径，使用隔离的 Linux TeX Live、ImageMagick 和 Ghostscript 工具链" in readme_zh
    assert "CDM（公式渲染指标）必须在 **WSL** 里跑" not in readme_zh
    assert "TeX Live" in readme and "ImageMagick" in readme and "Ghostscript" in readme
    assert "TeX Live" in readme_zh and "ImageMagick" in readme_zh and "Ghostscript" in readme_zh
    assert "timeout_case_count` `0`" in combined
    assert "quick_match_timeout" in combined

    article = read(REPO_ROOT / "docs" / "wechat-article.md")
    assert "历史坑：原版 OmniDocBench CDM shell 命令" in article
    assert "原始命令在 Windows 上会失败" in article
    assert "当前 repo 通过 `windows-cdm.patch` + `verify-windows.ps1` 支持原生 Windows CDM" in article
    assert "本机原生 TeX Live/ImageMagick/Ghostscript 验证通过" in article
    assert "WSL 仍是兼容性/参考路径" in article
    assert "CDM 代码 POSIX-only" not in article
    assert "CDM 在 Windows 上 F1=0" not in article


def test_contributing_and_eval_infra_docs_describe_both_supported_cdm_paths():
    contributing = read(REPO_ROOT / "CONTRIBUTING.md")
    eval_infra_readme = read(REPO_ROOT / "eval-infra" / "README.md")

    for text in (contributing, eval_infra_readme):
        normalized = " ".join(text.split())
        assert "windows-cdm.patch" in text
        assert "verify-windows.ps1" in text
        assert "WSL" in text
        assert "Windows-native CDM is supported" in normalized
        assert "WSL CDM remains the compatibility/reference path" in normalized

    assert "CDM runs in WSL" not in contributing
    assert "inside WSL" not in eval_infra_readme
    assert "-WindowsCdm" in eval_infra_readme


def test_agents_verification_instruction_is_conditional_by_cdm_path():
    text = read(REPO_ROOT / "AGENTS.md")
    normalized = " ".join(text.split())

    assert "Native Windows CDM users run `eval-infra\\02-cdm-environment\\verify-windows.ps1` first" in normalized
    assert "WSL CDM users run `eval-infra/02-cdm-environment/verify.sh` first" in normalized
    assert "Always run `eval-infra/02-cdm-environment/verify.sh` first" not in normalized


def test_full_verify_docs_include_the_native_only_cdm_command():
    command = "scripts\\full-verify.ps1 -SkipWsl -WindowsCdm"

    assert command in read(REPO_ROOT / "AGENTS.md")
    assert command in read(REPO_ROOT / "eval-infra" / "README.md")


def test_agents_success_criteria_accepts_the_applicable_cdm_verifier():
    text = read(REPO_ROOT / "AGENTS.md")
    normalized = " ".join(text.split())

    assert (
        "Windows native path `eval-infra\\02-cdm-environment\\verify-windows.ps1` "
        "prints `VERIFY OK` and positive identical-formula F1"
    ) in normalized
    assert (
        "WSL path `eval-infra/02-cdm-environment/verify.sh` prints `VERIFY OK`"
    ) in normalized


def test_user_facing_docs_do_not_describe_cdm_as_wsl_only():
    stale_claims = {
        "AGENTS.md": (
            "The system is fully operational when **all** hold:\n\n1. "
            "`scripts/wsl-ensure.ps1`",
        ),
        "docs/architecture.md": (
            "CDM needs WSL:",
            "Everything in between (LaTeX compilation, PDF rasterization, CDM matching)\n"
            "stays entirely on the Linux side.",
        ),
        "README.md": ("02-cdm-environment/ CDM toolchain in WSL:",),
        "README.zh-CN.md": ("02-cdm-environment/ WSL 内的 CDM 工具链：",),
        "eval-infra/02-cdm-environment/README.md": (
            "It produces exactly one thing: **a WSL environment",
            "re-run `verify.sh` first",
        ),
        "eval-infra/README.md": (
            "the same WSL/TeX Live 2026/ImageMagick 7 stack",
        ),
    }

    for relative_path, claims in stale_claims.items():
        text = read(REPO_ROOT / relative_path)
        for claim in claims:
            assert claim not in text, f"stale WSL-only CDM claim in {relative_path}: {claim}"
