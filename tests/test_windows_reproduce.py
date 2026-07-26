from __future__ import annotations

from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "reproduce.ps1"
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed-locked-inputs.ps1"
CONFIG_DIR = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "configs"


def test_cpu_smoke_configs_bind_exact_ten_page_artifacts():
    for name in ("v16-cpu-smoke-10.yaml", "v16-cdm-cpu-smoke-10.yaml"):
        data = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))
        dataset = data["end2end_eval"]["dataset"]
        assert dataset["ground_truth"]["data_path"].endswith("OmniDocBench_cpu_smoke_10.json")
        assert dataset["prediction"]["data_path"].endswith("predictions/paddleocrvl_cpu_smoke_10")
        assert dataset["match_workers"] == 1
        assert data["end2end_eval"]["metrics"]["table"]["teds_workers"] == 1


def test_orchestrator_is_windows_only_fail_closed_and_exactly_ten_pages():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '[ValidateSet("cpu-smoke-10")]' in text
    assert '[Alias("Profile")]' in text
    assert '$RunProfile' in text
    assert "--max-pages 10" in text
    assert "--limit 10" in text
    assert "-Variant cpu -Port $ServerPort" in text
    assert 'ServerPort = "8121"' in text
    assert "-RequireCdm" in text
    assert "-PredictionManifest $manifestRel" in text
    assert "Existing $RunProfile artifacts found" in text
    assert "Move-Item -LiteralPath $temp -Destination $stateFile -Force" in text
    assert '$env:UV_LINK_MODE = "copy"' in text
    assert "$env:UV_LINK_MODE = $previousLinkMode" in text
    assert "trap {" in text
    assert '$state.status = "interrupted"' in text
    assert "$state.resume_command" in text
    assert "Assert-LastExit" in text
    assert "RESUME SKIP: phase already passed" in text
    always_run = text.split("$alwaysRunPhases", 1)[1].split("$state", 1)[0]
    assert '"CPU VLM server"' in always_run
    assert '"WSL CDM environment"' in always_run
    assert '"Exact full verification"' in always_run
    assert "DRY RUN OK" in text
    assert "outputs\\checkouts\\PaddleOCR-VL-ROCm" in text
    assert "-CloneDir $pipelineCheckout" in text
    assert 'Invoke-Phase "Inference input locks"' in text
    assert "Ten-page inference requires exactly 10 Markdown predictions" in text
    assert "Manifest generation requires exactly 10 predictions" in text
    assert '[string] $SeedFrom = ""' in text
    assert 'Invoke-Phase "Seed locked inputs"' in text
    assert "seed-locked-inputs.ps1" in text


def test_seed_script_copies_only_locked_inputs_and_reverifies_destination():
    text = SEED_SCRIPT.read_text(encoding="utf-8")
    assert "DatasetManifest" in text and "Vlm" in text and "Layout" in text
    assert "verify_dataset_tree.py" in text
    assert "ConvertTo-ExtendedPath" in text
    assert "Ensure-ShortRepoRoot" in text
    assert "[System.IO.File]::Exists($extendedSource)" in text
    assert "$sourceShortRoot" in text and "$destinationShortRoot" in text
    assert 'if ($full.StartsWith("\\\\?\\"))' in text
    assert "predictions" not in text
    assert "metric_result" not in text
    assert 'Join-Path $SourceRoot ".env.local"' not in text
    assert 'Join-Path $DestinationRoot ".env.local"' not in text


def test_orchestrator_dry_run_parses_and_records_ordered_phases(tmp_path: Path):
    parse = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$tokens=$null;$errors=$null;"
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',[ref]$tokens,[ref]$errors);"
            "if($errors.Count){$errors|% Message;exit 1}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert parse.returncode == 0, parse.stdout + parse.stderr
    text = SCRIPT.read_text(encoding="utf-8")
    phases = [
        "Python environment",
        "Network mirrors",
        "WSL availability",
        "Preflight",
        "Seed locked inputs",
        "OmniDocBench and dataset",
        "Upstream locks",
        "WSL CDM environment",
        "CPU VLM server",
        "Layout model",
        "Pipeline dependency",
        "Inference input locks",
        "Ten-page CPU inference",
        "Exact ten-page manifest",
        "Windows scoring",
        "WSL CDM scoring",
        "Exact full verification",
    ]
    positions = [text.index(f'Invoke-Phase "{phase}"') for phase in phases]
    assert positions == sorted(positions)


def test_entrypoint_docs_make_ten_page_profile_canonical():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8-sig")
    readme_zh = (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8-sig")
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8-sig")
    command = "scripts\\reproduce.ps1"
    for text in (readme, readme_zh, agents):
        assert command in text
        assert "cpu-smoke-10" in text
    assert "docs/upstream-lock.md" in readme
    assert "能力 smoke test" in readme_zh