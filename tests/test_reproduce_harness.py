"""Executable orchestrator state-machine tests via the fake integration harness.

scripts/reproduce.ps1 runs its REAL stage machine end-to-end against a fake
machine root (REPRO_ROOT) with fake external scripts (REPRO_TEST_HOOKS): no
network, models, WSL or GPU involved. These tests exercise execution order,
resume invalidation, provenance binding, scoped cleanup and evidence
authority -- the state-machine behavior string assertions cannot see.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.win32


from harness_fake import build_harness, score_marker_count, set_behavior

REPO_ROOT = Path(__file__).resolve().parents[1]
REPRODUCE = REPO_ROOT / "scripts" / "reproduce.ps1"

SMOKE = "harness-smoke"
FULL = "harness-full"


@pytest.fixture()
def harness(tmp_path, request):
    profile = getattr(request, "param", "smoke")
    return build_harness(tmp_path, profile=profile)


def run_reproduce(env: dict, *args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.pop("REPRO_ROOT", None)
    full_env.pop("REPRO_PROFILE_DIR", None)
    full_env.pop("REPRO_CONFIG_DIR", None)
    full_env.pop("REPRO_TEST_HOOKS", None)
    full_env.pop("REPRO_WSL_RESULT_DIR", None)
    full_env.pop("REPRO_TEST_PYTHON", None)
    full_env.update(env)
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPRODUCE), *args],
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def state_path(harness: dict) -> Path:
    return harness["root"] / "outputs" / "reproduction" / harness["profile"]["name"] / "state.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_dir(harness: dict) -> Path:
    return harness["root"] / "outputs" / "reproduction" / harness["profile"]["name"]


def read_state(harness: dict) -> dict:
    return load_json(state_path(harness))


# --- 1. clean fresh run -----------------------------------------------------
def test_01_clean_fresh_run_passes(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    if result.returncode != 0:
        diag = ""
        state_p = state_path(harness)
        if state_p.is_file():
            try:
                state = load_json(state_p)
                failed = [
                    {k: s.get(k) for k in ("id", "status", "exit_code", "error", "command")}
                    for s in state.get("stages", [])
                    if s.get("status") != "passed"
                ]
                diag = (
                    f"\nSTATUS={state.get('status')} "
                    f"RESUME={state.get('resume_command')} "
                    f"INTERRUPTED={state.get('interruption_reason')} "
                    f"FAILED={json.dumps(failed, ensure_ascii=False)}"
                )
            except Exception as error:  # noqa: BLE001
                diag = f"\nSTATE UNREADABLE: {error}"
        assert False, result.stdout + result.stderr + diag
    assert "REPRODUCTION OK" in result.stdout
    state = read_state(harness)
    assert state["status"] == "passed"
    stage_ids = [s["id"] for s in state["stages"]]
    for expected in (
        "environment.python", "environment.mirrors", "environment.wsl",
        "profile.preflight", "dataset.setup", "dataset.upstream_locks",
        "inputs.fingerprint", "cdm.wsl_environment", "inference.server",
        "inference.layout", "inference.pipeline_deps", "inference.input_locks",
        "inference.fingerprint", "inference.run", "inference.prediction_check",
        "scoring.fingerprint", "scoring.windows", "scoring.wsl_cdm",
        "verification.final", "evidence.pack",
    ):
        assert expected in stage_ids, f"stage {expected} missing from state"
    order = [s["id"] for s in state["stages"]]
    assert order.index("inference.run") < order.index("inference.prediction_check") < order.index("scoring.windows") < order.index("evidence.pack")
    # Both platforms scored exactly once.
    assert score_marker_count(harness["hooks"]) == 2
    summary = load_json(evidence_dir(harness) / "prediction-summary.json")
    assert summary["verdict"] == "pass"
    assert summary["expected"] == 10
    assert summary["selected_pages"] == 10


# --- 2+3. interrupt before checkout, resume after checkout created ---------
def test_02_03_interrupt_before_checkout_then_resume(harness):
    set_behavior(harness["hooks"], {"pipeline_deps_fail": True})
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode != 0
    state = read_state(harness)
    assert state["status"] == "failed"
    assert state["resume_command"], "resume_command must be persisted on failure"
    assert "reproduce.ps1 -Profile harness-smoke -Resume" in state["resume_command"]
    failed_stage = next(s for s in state["stages"] if s["id"] == "inference.pipeline_deps")
    assert failed_stage["status"] == "failed"
    assert failed_stage["exit_code"] == 1
    assert "exited 1" in (failed_stage.get("error") or "")
    # The checkout was NOT created by the failed run.
    checkout = harness["root"] / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"
    assert not (checkout / ".git").exists()

    # Resume now that pipeline deps succeed.
    set_behavior(harness["hooks"], {"pipeline_deps_fail": False})
    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-Resume")
    assert result.returncode == 0, result.stdout + result.stderr
    state = read_state(harness)
    assert state["status"] == "passed"
    assert (checkout / ".git").exists()
    assert score_marker_count(harness["hooks"]) == 2


# --- 4. resume with unchanged predictions reuses scores ---------------------
def test_04_resume_unchanged_predictions_reuses_scores(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert score_marker_count(harness["hooks"]) == 2
    tree_before = load_json(evidence_dir(harness) / "prediction-tree.json")["prediction_tree_sha256"]

    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-Resume")
    assert result.returncode == 0, result.stdout + result.stderr
    # Scoring was skipped on resume: no additional score marker lines.
    assert score_marker_count(harness["hooks"]) == 2
    state = read_state(harness)
    assert state["status"] == "passed"
    assert "resumed_at" in state
    tree_after = load_json(evidence_dir(harness) / "prediction-tree.json")["prediction_tree_sha256"]
    assert tree_before == tree_after


# --- 5. resume completes a missing prediction -------------------------------
def test_05_resume_completes_missing_prediction(harness):
    set_behavior(harness["hooks"], {"adapter": {"fail_stems": ["page-0009"]}})
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode != 0, "missing unknown page must fail prediction_check"
    assert "page-0009" in result.stdout + result.stderr
    assert score_marker_count(harness["hooks"]) == 0

    set_behavior(harness["hooks"], {"adapter": {"fail_stems": []}})
    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-Resume")
    assert result.returncode == 0, result.stdout + result.stderr
    preds = harness["root"] / "outputs" / "harness" / "predictions" / "fake_model"
    assert (preds / "page-0009.md").is_file()
    state = read_state(harness)
    assert state["status"] == "passed"
    assert score_marker_count(harness["hooks"]) == 2


# --- 6. prediction change invalidates scoring -------------------------------
def test_06_prediction_change_invalidates_scoring(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert score_marker_count(harness["hooks"]) == 2
    old_tree = load_json(evidence_dir(harness) / "prediction-tree.json")["prediction_tree_sha256"]

    set_behavior(harness["hooks"], {"adapter": {"content": "v2", "force_rewrite_stems": ["page-0000"]}})
    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-Resume")
    assert result.returncode == 0, result.stdout + result.stderr
    # Scoring re-ran for both platforms after the prediction bytes changed.
    assert score_marker_count(harness["hooks"]) == 4
    new_tree = load_json(evidence_dir(harness) / "prediction-tree.json")["prediction_tree_sha256"]
    assert old_tree != new_tree
    # The stored scores must be bound to the NEW prediction tree.
    prov = load_json(
        harness["root"] / "eval-infra" / "01-omnidocbench" / "OmniDocBench" / "result"
        / "fake_model_quick_match_metric_result.provenance.json"
    )
    assert prov["prediction_tree_sha256"] == new_tree


# --- 7. stale metric provenance is rejected and scoring re-runs -------------
def test_07_stale_provenance_rejected(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert score_marker_count(harness["hooks"]) == 2
    prov_path = (
        harness["root"] / "eval-infra" / "01-omnidocbench" / "OmniDocBench" / "result"
        / "fake_model_quick_match_metric_result.provenance.json"
    )
    prov = load_json(prov_path)
    prov["prediction_tree_sha256"] = "deadbeef" * 8
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-Resume")
    assert result.returncode == 0, result.stdout + result.stderr
    # The stale sidecar was detected: Windows scoring re-ran (WSL sidecar was
    # still valid and was reused).
    assert score_marker_count(harness["hooks"]) == 3
    repaired = load_json(prov_path)
    current_tree = load_json(evidence_dir(harness) / "prediction-tree.json")["prediction_tree_sha256"]
    assert repaired["prediction_tree_sha256"] == current_tree


# --- 8. ForceInference scoped cleanup ---------------------------------------
def test_08_force_inference_scoped_cleanup(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode == 0, result.stdout + result.stderr
    preds = harness["root"] / "outputs" / "harness" / "predictions" / "fake_model"
    assert (preds / "page-0000.md").is_file()

    # Other-profile artifacts must survive the scoped cleanup.
    other_preds = harness["root"] / "predictions" / "other_profile"
    other_preds.mkdir(parents=True)
    (other_preds / "other.md").write_text("other", encoding="utf-8")
    win_dir = harness["root"] / "eval-infra" / "01-omnidocbench" / "OmniDocBench" / "result"
    win_dir.mkdir(parents=True, exist_ok=True)
    (win_dir / "other_profile_quick_match_metric_result.json").write_text("{}", encoding="utf-8")

    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-ForceInference")
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "FORCE INFERENCE: removing" in output, "ForceInference cleanup must log removals"
    assert str(preds) in output, "the owned prediction dir must be in the cleanup list"
    # A fresh full run regenerates the owned artifacts, but never touches
    # artifacts owned by other profiles.
    assert (preds / "page-0000.md").is_file(), "fresh run must regenerate predictions"
    assert (other_preds / "other.md").is_file(), "other profile's predictions must survive"
    assert (win_dir / "other_profile_quick_match_metric_result.json").is_file()
    ev = evidence_dir(harness)
    assert (ev / "fingerprint.provisioning.json").exists(), "fingerprints regenerated by the fresh run"
    assert (ev / "state.json").exists()


# --- 9. dirty formal run is rejected ----------------------------------------
@pytest.mark.parametrize("harness", ["full"], indirect=True)
def test_09_dirty_formal_run_rejected(harness):
    lock = harness["root"] / "upstream-lock.json"
    lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = run_reproduce(harness["env"], "-Profile", FULL)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "dirty" in output.lower() or "clean" in output.lower()
    state = read_state(harness)
    assert state["status"] == "failed"
    # Clean up the tree: the same run now passes.
    subprocess.run(
        ["git", "-C", str(harness["root"]), "checkout", "--", "upstream-lock.json"],
        check=True,
        capture_output=True,
    )
    result = run_reproduce(harness["env"], "-Profile", FULL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_state(harness)["status"] == "passed"


# --- 10. empty-GT summary ----------------------------------------------------
def test_10_empty_gt_summary(harness):
    set_behavior(harness["hooks"], {"empty_gt_stems": ["page-0005"]})
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = load_json(evidence_dir(harness) / "prediction-summary.json")
    assert summary["empty_gt_valid"] == 1
    assert summary["valid"] == 10
    assert summary["verdict"] == "pass"
    assert summary["prediction_tree_sha256"]
    assert len(summary["prediction_tree_sha256"]) == 64


# --- 11. unknown failed page rejected; known failure allowed ----------------
@pytest.mark.parametrize("harness", ["full"], indirect=True)
def test_11_unknown_failed_page_rejected(harness):
    set_behavior(harness["hooks"], {"adapter": {"fail_stems": ["page-0010"]}})
    result = run_reproduce(harness["env"], "-Profile", FULL)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "page-0010" in output
    assert "unknown failed pages" in output
    summary = load_json(evidence_dir(harness) / "prediction-summary.json")
    assert summary["unknown_failures"] == ["page-0010"]
    assert summary["verdict"] == "fail"


@pytest.mark.parametrize("harness", ["full"], indirect=True)
def test_11b_known_failure_on_allowlist_passes(harness):
    set_behavior(harness["hooks"], {"adapter": {"fail_stems": ["page-0000"]}})
    result = run_reproduce(harness["env"], "-Profile", FULL)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = load_json(evidence_dir(harness) / "prediction-summary.json")
    assert summary["known_allowed_failures"] == ["page-0000"]
    assert summary["unknown_failures"] == []
    assert summary["verdict"] == "pass"
    assert summary["recovered_known_failures"] == ["page-0001"]


# --- 12. evidence pack never overwrites the strict summary ------------------
def test_12_evidence_pack_keeps_strict_summary(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode == 0, result.stdout + result.stderr
    ev = evidence_dir(harness)
    original = (ev / "prediction-summary.json").read_bytes()
    strict = (ev / "prediction-summary.strict.json").read_bytes()
    assert original == strict, "evidence pack must copy the strict summary verbatim"
    assert "prediction_tree_sha256" in json.loads(original.decode("utf-8"))


# --- 13. ServerPort override recorded in evidence ---------------------------
def test_13_server_port_override_in_evidence(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-ServerPort", "9999")
    assert result.returncode == 0, result.stdout + result.stderr
    ev = evidence_dir(harness)
    resolved = load_json(ev / "profile.resolved.json")
    assert resolved["resolved_server_port"] == "9999"
    hashes = load_json(ev / "artifact-hashes.json")
    assert hashes["resolved_server_port"] == "9999"
    report = (ev / "report.md").read_text(encoding="utf-8")
    assert "9999" in report
    assert "8765" not in report.split("Resolved server port")[0].split("server port")[0]


# --- 14. dry run never touches the real state -------------------------------
def test_14_dry_run_no_state_pollution(harness):
    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-DryRun")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DRY RUN OK" in result.stdout
    ev = evidence_dir(harness)
    assert not (ev / "state.json").exists(), "dry run must not create the real state"
    assert (ev / "state.dryrun.json").exists(), "dry run must write state.dryrun.json"
    dry = load_json(ev / "state.dryrun.json")
    assert dry["status"] in ("running", "dry-run")
    assert all(s["status"] == "dry-run" for s in dry["stages"])


# --- 15. stage failure persistence (covered in 02/03) + extra fields --------
def test_15_failure_persists_stage_error_and_exit_code(harness):
    set_behavior(harness["hooks"], {"pipeline_deps_fail": True})
    result = run_reproduce(harness["env"], "-Profile", SMOKE)
    assert result.returncode != 0
    state = read_state(harness)
    failed = [s for s in state["stages"] if s["status"] == "failed"]
    assert any(s["id"] == "inference.pipeline_deps" for s in failed)
    stage = next(s for s in failed if s["id"] == "inference.pipeline_deps")
    assert stage["exit_code"] == 1
    assert stage["error"]
    assert "started_at" in stage and "ended_at" in stage
    # The failed stage is not in the resume-able set.
    result = run_reproduce(harness["env"], "-Profile", SMOKE, "-DryRun", "-Resume")
    assert result.returncode == 0
