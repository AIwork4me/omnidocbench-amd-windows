from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH = REPO_ROOT / "patches" / "omnidocbench" / "windows-cdm.patch"
SETUP = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "setup.ps1"
VERIFY_WINDOWS = REPO_ROOT / "eval-infra" / "02-cdm-environment" / "verify-windows.ps1"
FULL_VERIFY = REPO_ROOT / "scripts" / "full-verify.ps1"
SCORING_README = REPO_ROOT / "eval-infra" / "03-scoring" / "README.md"
SCORE_PS1 = REPO_ROOT / "eval-infra" / "03-scoring" / "score.ps1"
SCORE_CDM_SH = REPO_ROOT / "eval-infra" / "03-scoring" / "score-cdm.sh"
SCORING_VERIFY = REPO_ROOT / "eval-infra" / "03-scoring" / "verify.ps1"
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


def write_metric_result(path: Path, *, cdm=..., mandatory_value=0.1):
    display_formula = {"Edit_dist": {"ALL_page_avg": mandatory_value}}
    if cdm is not ...:
        display_formula["CDM"] = cdm
    path.write_text(
        json.dumps(
            {
                "text_block": {
                    "all": {"Edit_dist": {"ALL_page_avg": mandatory_value}}
                },
                "display_formula": {"all": display_formula},
                "table": {"all": {"TEDS": {"all": mandatory_value}}},
                "reading_order": {
                    "all": {"Edit_dist": {"ALL_page_avg": mandatory_value}}
                },
            }
        ),
        encoding="utf-8",
    )


def run_scoring_verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCORING_VERIFY),
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_minimal_full_verify_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(FULL_VERIFY, root / "scripts" / "full-verify.ps1")
    (root / "mirrors.env").write_text(
        "\n".join(f"SOURCE_{letter}=ok" for letter in "ABCDE"),
        encoding="utf-8",
    )
    return root


def write_passing_verifier(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("exit 0\n", encoding="utf-8")


def run_full_verify(
    script: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_scoring_verifier_rejects_present_zero_cdm_f1(tmp_path: Path):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result, cdm={"all": 0.0})

    result = run_scoring_verify("-MetricResult", str(metric_result))

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "CDM F1=0" in output or "CDM <= 0" in output


def test_scoring_verifier_rejects_present_cdm_without_all(tmp_path: Path):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result, cdm={})

    result = run_scoring_verify("-MetricResult", str(metric_result))

    assert result.returncode != 0
    assert "display_formula.CDM.all" in result.stdout + result.stderr


def test_scoring_verifier_rejects_present_null_cdm_all(tmp_path: Path):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result, cdm={"all": None})

    result = run_scoring_verify("-MetricResult", str(metric_result))

    assert result.returncode != 0
    assert "display_formula.CDM.all" in result.stdout + result.stderr


def test_scoring_verifier_require_cdm_rejects_edit_dist_only_result(tmp_path: Path):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result)

    result = run_scoring_verify(
        "-MetricResult", str(metric_result), "-RequireCdm"
    )

    assert result.returncode != 0
    assert "CDM metric required" in result.stdout + result.stderr


def test_scoring_verifier_accepts_edit_dist_only_result_without_require_cdm(
    tmp_path: Path,
):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result)

    result = run_scoring_verify("-MetricResult", str(metric_result))

    assert result.returncode == 0, result.stdout + result.stderr


def test_scoring_verifier_success_text_matches_zero_metric_warning_policy(
    tmp_path: Path,
):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result, mandatory_value=0.0)

    result = run_scoring_verify("-MetricResult", str(metric_result))

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "mandatory metrics present and non-negative" in output
    assert "CDM positive when present or required" in output
    assert "all 4 metrics non-zero" not in output


def test_scoring_verifier_rejects_present_non_numeric_cdm_all(tmp_path: Path):
    metric_result = tmp_path / "metric_result.json"
    write_metric_result(metric_result, cdm={"all": "not-a-number"})

    result = run_scoring_verify("-MetricResult", str(metric_result))

    assert result.returncode != 0
    assert "must be numeric" in result.stdout + result.stderr


def test_scoring_verifier_rejects_raw_json_nonfinite_cdm_all(tmp_path: Path):
    metric_result = tmp_path / "metric_result.json"
    metric_result.write_text(
        """
{
  "text_block": {"all": {"Edit_dist": {"ALL_page_avg": 0.1}}},
  "display_formula": {
    "all": {
      "Edit_dist": {"ALL_page_avg": 0.1},
      "CDM": {"all": 1e309}
    }
  },
  "table": {"all": {"TEDS": {"all": 0.1}}},
  "reading_order": {"all": {"Edit_dist": {"ALL_page_avg": 0.1}}}
}
""",
        encoding="utf-8",
    )

    result = run_scoring_verify("-MetricResult", str(metric_result))

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "not valid JSON" in output
    assert "1e309" in output


def test_scoring_verifier_windows_only_excludes_wsl_candidates():
    save_name = f"windows_only_missing_{uuid.uuid4().hex}"

    result = run_scoring_verify("-WindowsOnly", "-SaveName", save_name)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "eval-infra\\01-omnidocbench\\OmniDocBench\\result" in output
    assert "\\\\wsl$" not in output


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
    assert "git -C $odbDir apply --reverse --check $windowsCdmPatch" in text
    assert 'Fail "tracked Windows CDM patch is not applied' in text
    assert "kpsewhich" in text
    assert "upgreek.sty" in text
    assert "magick" in text
    assert "tlpkg" in text
    assert "tlgs" in text
    assert "GS_LIB" in text
    assert 'Fail "TeX Live bundled Ghostscript bin not found at $tlgsBin"' in text
    assert 'Fail "TeX Live bundled Ghostscript Resource not found at $tlgsResource"' in text
    assert 'Fail "could not resolve TeX Live root via kpsewhich SELFAUTOPARENT' in text
    assert "WARN: TeX Live bundled Ghostscript bin not found" not in text
    assert "WARN: TeX Live bundled Ghostscript Resource not found" not in text
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
    assert '"-WindowsOnly", "-RequireCdm"' in text
    assert '"-WslOnly", "-RequireCdm"' in text
    assert '$argumentText = $verifyArguments -join " "' in text


def test_full_verify_default_wsl_scoring_requires_wsl_cdm_result():
    text = read(FULL_VERIFY)

    assert (
        '} else {\n'
        '    [void](Invoke-Verify "03-scoring/verify-wsl" $scoreVerify '
        '@("-WslOnly", "-RequireCdm"))\n'
        '}'
    ) in text


def test_full_verify_wsl_cdm_verifier_temporarily_allows_stderr():
    text = read(FULL_VERIFY)
    wsl_cdm_block = text.split("# --- 4. CDM environment (WSL)", 1)[1].split(
        "# --- 4b. CDM environment (Windows native)", 1
    )[0]

    expected_sequence = [
        "$previousErrorActionPreference = $ErrorActionPreference",
        '$ErrorActionPreference = "Continue"',
        "$output = wsl -d Ubuntu2204 bash $wslPath 2>&1",
        "$wslExit = $LASTEXITCODE",
        "finally {",
        "$ErrorActionPreference = $previousErrorActionPreference",
    ]
    positions = [wsl_cdm_block.index(item) for item in expected_sequence]

    assert positions == sorted(positions)


def test_full_verify_wsl_cdm_stage_accepts_benign_stderr_at_runtime(
    tmp_path: Path,
):
    root = make_minimal_full_verify_tree(tmp_path)
    write_passing_verifier(root / "eval-infra/01-omnidocbench/verify.ps1")
    write_passing_verifier(root / "eval-infra/03-scoring/verify.ps1")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_wsl = fake_bin / "wsl.cmd"
    fake_wsl.write_text(
        "\r\n".join(
            [
                "@echo off",
                "setlocal enabledelayedexpansion",
                'if "%1"=="--list" (',
                "  echo Ubuntu2204",
                "  exit /b 0",
                ")",
                'if "%1"=="-d" if "%2"=="Ubuntu2204" if "%3"=="--" (',
                '  if "%4"=="echo" (',
                "    echo %5",
                "    exit /b 0",
                "  )",
                ")",
                'if "%1"=="-d" if "%2"=="Ubuntu2204" if "%3"=="bash" (',
                "  >&2 echo benign WSL diagnostic",
                "  echo VERIFY OK",
                "  exit /b 0",
                ")",
                "echo unexpected fake wsl args: %*",
                "exit /b 1",
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]

    result = run_full_verify(
        root / "scripts/full-verify.ps1",
        "-SkipVlm",
        "-SkipWindowsCdm",
        env=env,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "02-cdm-environment/verify" in output
    assert "CDM pipeline functional (VERIFY OK)" in output


def test_full_verify_rejects_contradictory_windows_cdm_switches():
    result = run_full_verify(
        FULL_VERIFY,
        "-WindowsCdm",
        "-SkipWindowsCdm",
        "-SkipWsl",
        "-SkipVlm",
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "-WindowsCdm and -SkipWindowsCdm cannot be combined" in output


def test_full_verify_fails_when_requested_windows_cdm_verifier_is_missing(
    tmp_path: Path,
):
    root = make_minimal_full_verify_tree(tmp_path)
    write_passing_verifier(root / "eval-infra/01-omnidocbench/verify.ps1")
    write_passing_verifier(root / "eval-infra/03-scoring/verify.ps1")

    result = run_full_verify(
        root / "scripts/full-verify.ps1",
        "-SkipWsl",
        "-SkipVlm",
        "-WindowsCdm",
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "02-cdm-environment/verify-windows" in output
    assert "verify script missing" in output
    assert "SKIP" not in next(
        line
        for line in output.splitlines()
        if "02-cdm-environment/verify-windows" in line
    )


def test_full_verify_fails_when_scoring_verifier_is_missing(tmp_path: Path):
    root = make_minimal_full_verify_tree(tmp_path)
    write_passing_verifier(root / "eval-infra/01-omnidocbench/verify.ps1")

    result = run_full_verify(
        root / "scripts/full-verify.ps1",
        "-SkipWsl",
        "-SkipVlm",
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "03-scoring/verify-windows" in output
    assert "verify script missing" in output
    assert "SKIP" not in next(
        line for line in output.splitlines() if "03-scoring/verify-windows" in line
    )
    benchmark_line = next(
        line for line in output.splitlines() if "04-benchmark/verify" in line
    )
    assert "SKIP" in benchmark_line
    assert "verify script not present" in benchmark_line


def test_scoring_verifier_resolves_wsl_home_and_keeps_root_fallback():
    text = read(SCORING_VERIFY)

    assert "wsl -d Ubuntu2204 -- sh -lc" in text
    assert 'printf %s "$HOME"' in text
    assert "OmniDocBench\\result" in text
    assert '"\\\\wsl$\\Ubuntu2204\\root\\OmniDocBench\\result"' in text


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


def test_full_verify_help_documents_both_cdm_scoring_paths():
    text = read(FULL_VERIFY)
    normalized = " ".join(text.split())

    assert "WSL via `score-cdm.sh`" in normalized
    assert "native Windows via `verify-windows.ps1` + `score.ps1 -Config v16-cdm.yaml`" in normalized
    assert "Native full verification via `-SkipWsl -WindowsCdm`" in normalized


def test_full_verify_help_distinguishes_mandatory_gates_from_optional_benchmark():
    text = read(FULL_VERIFY)
    normalized = " ".join(text.split())

    assert "module gates are mandatory and fail" in normalized
    assert "benchmark report remains optional" in normalized
    assert "reported as SKIP rather than FAIL when their inputs are absent" not in text


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

    assert "Score adapter predictions with the metrics enabled by a config." in score_ps1
    assert 'Write-Host "Scoring with config $Config ..."' in score_ps1
    assert "mandatory metrics are present and non-negative; CDM must be positive when present or required" in score_ps1
    assert "Scoring (Edit_dist + TEDS) with $Config" not in score_ps1
    assert "all 4 metrics are non-zero" not in score_ps1
    assert "v16-cdm.yaml" in score_ps1
    assert "windows-cdm.patch" in score_ps1
    assert "verify-windows.ps1" in score_ps1
    assert "WSL compatibility/reference CDM path" in score_cdm_sh
    assert "Native Windows CDM is available via score.ps1 with a CDM config" in score_cdm_sh
    assert "verify-windows.ps1" in score_cdm_sh


def test_official_config_describes_native_or_wsl_cdm_path():
    text = read(
        REPO_ROOT / "eval-infra" / "01-omnidocbench" / "configs" / "v16-official.yaml"
    )
    normalized = " ".join(text.split())

    assert "native Windows scorer or WSL scoring path" in normalized
    assert "in WSL when Formula CDM is needed" not in text


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


def test_docs_describe_the_implemented_zero_score_policy():
    for text in (read(REPO_ROOT / "AGENTS.md"), read(SCORING_README)):
        normalized = " ".join(text.split())
        assert "mandatory non-CDM metrics are present and non-negative" in normalized
        assert "zero non-cdm metrics warn but can pass" in normalized.lower()
        assert "CDM must be positive when present or required" in normalized

    architecture = read(REPO_ROOT / "docs" / "architecture.md")
    assert "non-CDM >= 0" in architecture
    assert "CDM > 0 if used" in architecture
    assert "all 4 metrics" not in architecture
    assert "non-zero?" not in architecture

    full_verify = read(FULL_VERIFY)
    assert "Scores valid" in full_verify
    assert "Scores present + non-zero" not in full_verify


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
