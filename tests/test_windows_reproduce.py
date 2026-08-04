from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

import pytest

pytestmark = pytest.mark.win32



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


def test_orchestrator_is_fail_closed_and_keeps_smoke_artifact_bindings():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '[Alias("Profile")]' in text
    assert '$RunProfile' in text
    assert "--max-pages" in text
    assert '"-limit", "$($profile.expected_pages)"' in text or "--limit" in text
    assert '"-Variant", $profile.variant' in text
    assert "-RequireCdm" in text
    assert '"-PredictionManifest", $manifestRel' in text
    assert "Existing $RunProfile artifacts found" in text
    assert "Move-Item -LiteralPath $temp -Destination $stateFile -Force" in text
    assert '$env:UV_LINK_MODE = "copy"' in text
    assert "$env:UV_LINK_MODE = $previousLinkMode" in text
    assert "trap {" in text
    assert '$state.status = "interrupted"' in text
    assert "$state.resume_command" in text
    assert "Assert-LastExit" in text
    assert "RESUME SKIP: stage already passed" in text
    assert "DRY RUN OK" in text
    assert "outputs\\checkouts\\PaddleOCR-VL-ROCm" in text
    assert '"-CloneDir", $pipelineCheckout' in text
    assert 'Invoke-Stage -Id "inference.input_locks"' in text
    assert "Smoke inference requires exactly" in text
    assert "Manifest generation requires exactly" in text
    assert '[string] $SeedFrom = ""' in text
    assert 'Invoke-Stage -Id "inputs.seed"' in text
    assert "seed-locked-inputs.ps1" in text
    assert 'Invoke-Stage -Id "verification.final"' in text


def test_orchestrator_native_launch_keeps_live_output_without_redirected_pipes():
    text = SCRIPT.read_text(encoding="utf-8")
    block = text.split("function Invoke-ReproNative {", 1)[1].split(
        "function Invoke-ReproExternal {", 1
    )[0]
    assert "-NoNewWindow" in block
    assert "-RedirectStandardOutput" not in block
    assert "-RedirectStandardError" not in block


def test_orchestrator_uses_stable_stage_ids_for_resume():
    text = SCRIPT.read_text(encoding="utf-8")
    for stage_id in (
        "environment.python",
        "environment.mirrors",
        "environment.wsl",
        "profile.preflight",
        "inputs.seed",
        "dataset.setup",
        "dataset.upstream_locks",
        "cdm.wsl_environment",
        "inference.server",
        "inference.layout",
        "inference.pipeline_deps",
        "inference.input_locks",
        "inference.run",
        "inference.prediction_check",
        "scoring.windows",
        "scoring.wsl_cdm",
        "verification.final",
    ):
        assert f'Invoke-Stage -Id "{stage_id}"' in text, f"stage {stage_id} missing"
    assert "$completedStageIds" in text and "$alwaysRunStageIds" in text
    assert "schema_version = 2" in text
    assert "state.json schema v" in text


def test_resume_keys_off_stage_ids_not_display_names():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "stages = @()" in text
    assert "ForEach-Object { $_.id })" in text
    assert "Set-StageRecord" in text
    assert "-not $AlwaysRun.IsPresent" in text


def test_seed_script_copies_only_locked_inputs_and_reverifies_destination():
    text = SEED_SCRIPT.read_text(encoding="utf-8")
    assert "DatasetManifest" in text and "Vlm" in text and "Layout" in text
    assert "verify_dataset_tree.py" in text
    assert "ConvertTo-ExtendedPath" in text
    assert "Initialize-ShortRepoRoot" in text
    assert "[System.IO.File]::Exists($extendedSource)" in text
    assert "$sourceShortRoot" in text and "$destinationShortRoot" in text
    assert 'if ($full.StartsWith("\\\\?\\"))' in text
    assert "Join-LiteralPath" in text
    assert "[System.IO.Path]::GetDirectoryName" in text
    assert '$parsedPages | ForEach-Object { $_ }' in text
    assert "Seed manifest expected 1651 image paths" in text
    assert "predictions" not in text
    assert "metric_result" not in text
    assert 'Join-Path $SourceRoot ".env.local"' not in text
    assert 'Join-Path $DestinationRoot ".env.local"' not in text


def test_orchestrator_dry_run_parses_and_records_ordered_stages(tmp_path: Path):
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
    stage_ids = [
        "environment.python",
        "environment.mirrors",
        "environment.wsl",
        "profile.preflight",
        "inputs.seed",
        "dataset.setup",
        "dataset.upstream_locks",
        "cdm.wsl_environment",
        "inference.server",
        "inference.layout",
        "inference.pipeline_deps",
        "inference.input_locks",
        "inference.run",
        "inference.prediction_check",
        "scoring.windows",
        "scoring.wsl_cdm",
        "verification.final",
    ]
    positions = [text.index(f'Invoke-Stage -Id "{stage_id}"') for stage_id in stage_ids]
    assert positions == sorted(positions)


def test_always_run_stages_are_the_cheap_safety_gates():
    text = SCRIPT.read_text(encoding="utf-8")
    always_run = text.split("$alwaysRunStageIds = @(", 1)[1].split(")", 1)[0]
    for stage_id in (
        "environment.wsl",
        "profile.preflight",
        "inputs.fingerprint",
        "cdm.wsl_environment",
        "inference.server",
        "inference.backend_proof",
        "inference.input_locks",
        "inference.run",
        "verification.final",
        "evidence.pack",
    ):
        assert f'"{stage_id}"' in always_run


def test_resume_uses_skip_existing_and_fingerprint_gate():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--skip-existing" in text
    assert '$skipExistingArg = @("--skip-existing")' in text
    assert "compute_fingerprint.py" in text
    assert 'Invoke-Stage -Id "inputs.fingerprint"' in text
    assert "--check" in text  # resume re-checks the stored fingerprint


def test_full_profile_strict_gates_are_wired():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "verify_prediction_set.py" in text
    assert "--require-selected" in text
    assert "--expected-pages" in text
    assert "--max-failed-pages" in text
    assert "RequireRunStatsSelected" in text
    assert "assert-metrics.ps1" in text
    assert "-NotOlderThan" in text


def test_force_inference_purge_is_scoped():
    text = SCRIPT.read_text(encoding="utf-8")
    block = text.split("if ($ForceInference -and -not $DryRun) {", 1)[1].split("if (-not $Resume -and -not $DryRun) {", 1)[0]
    assert "$profile.owned_manifest -and (Test-Path -LiteralPath $manifest)" in block
    assert 'Filter "$($saveName)_*"' in block
    assert "$predictionDir" in block
    assert "purgeIds" in block


def test_evidence_pack_stage_writes_all_files():
    text = SCRIPT.read_text(encoding="utf-8")
    block = text.split('Invoke-Stage -Id "evidence.pack"', 1)[1].split("-Command", 1)[0]
    # Write-ProfileResolved / Write-HardwareJson / Write-MetricsSummary /
    # Write-Report run inside the stage action.
    for name in ("Write-ProfileResolved", "Write-HardwareJson", "Write-MetricsSummary", "Write-Report"):
        assert name in block, f"{name} missing from evidence.pack"
    # The final artifact hashing runs in the -AfterSave hook, AFTER state.json
    # holds the evidence.pack record (hashing earlier bound a stale state).
    after_save = text.split("-AfterSave {", 1)[1].split("if (-not $DryRun) {", 1)[1].split("-Command", 1)[0]
    for name in ("Write-ArtifactHashes", "compute_fingerprint.py", "fingerprint.evidence.spec.json"):
        assert name in after_save, f"{name} missing from evidence.pack -AfterSave"


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
    assert "-SeedFrom" in readme and "-SeedFrom" in readme_zh and "-SeedFrom" in agents
    assert "predictions" in readme and "never copied" in readme
