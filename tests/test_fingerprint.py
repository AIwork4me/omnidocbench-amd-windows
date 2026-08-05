"""Phase-scoped fingerprint gating for reproduce.ps1 -Resume.

The fingerprint CLI is phase-aware: --phase provisioning|inference|scoring|
evidence with an input-spec JSON. Each phase binds the artifacts it gates to
the inputs that produced them; on resume the phase fingerprint is recomputed
and compared before its stages may be reused.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "compute_fingerprint.py"
PROFILE = REPO_ROOT / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
CONFIG = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "configs" / "v16-cpu-smoke-10.yaml"


def provisioning_spec(root: Path) -> dict:
    lock_manifest = json.loads((root / "locks" / "manifest.json").read_text(encoding="utf-8"))
    return {
        "profile_sha256": {"file": "scripts/profiles/cpu-smoke-10.profile.json"},
        "upstream_lock_sha256": {"file": "upstream-lock.json"},
        "dataset_manifest_sha256": {"file": "eval-infra/01-omnidocbench/data/OmniDocBench_cpu_smoke_10.json"},
        "windows_scoring_config_sha256": {"file": "eval-infra/01-omnidocbench/configs/v16-cpu-smoke-10.yaml"},
        "wsl_cdm_config_sha256": {"file": "eval-infra/01-omnidocbench/configs/v16-cdm-cpu-smoke-10.yaml"},
        "uv_lock_sha256": {"file": "uv.lock"},
        "uv_normalized_graph_sha256": {"string": lock_manifest["normalized_graph_sha256"]},
        "repo_commit": {"git": "."},
        "repo_tree_sha256": {"repo_tree": "."},
    }


def inference_spec(root: Path) -> dict:
    return {
        "provisioning_fingerprint_sha256": {"file": str(root / "fp.json")},
        "adapter_tree_sha256": {"tree": "adapters/paddleocr-vl-1.6"},
        "pipeline_checkout_commit": {"git": "outputs/checkouts/PaddleOCR-VL-ROCm"},
        "backend_variant": {"string": "cpu"},
        "resolved_server_port": {"string": "8121"},
        "manifest_sha256": {"file": "eval-infra/01-omnidocbench/data/OmniDocBench_cpu_smoke_10.json"},
    }


@pytest.fixture()
def fingerprint_env(tmp_path):
    """A self-contained fingerprint root with all referenced files."""
    root = tmp_path / "repo"
    (root / "scripts" / "profiles").mkdir(parents=True)
    (root / "eval-infra" / "01-omnidocbench" / "data").mkdir(parents=True)
    (root / "eval-infra" / "01-omnidocbench" / "configs").mkdir(parents=True)
    (root / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm" / ".git").mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(root / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"), "init", "-q"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git", "-C", str(root / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"),
            "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-q", "-m", "seed",
        ],
        check=True,
        capture_output=True,
    )
    profile = root / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    profile.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = root / "eval-infra" / "01-omnidocbench" / "data" / "OmniDocBench_cpu_smoke_10.json"
    manifest.write_text(json.dumps([{"page_info": {"image_path": "a.png"}}]), encoding="utf-8")
    (root / "eval-infra" / "01-omnidocbench" / "configs" / "v16-cpu-smoke-10.yaml").write_text(
        CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "eval-infra" / "01-omnidocbench" / "configs" / "v16-cdm-cpu-smoke-10.yaml").write_text(
        "wsl cdm config\n", encoding="utf-8"
    )
    (root / "adapters" / "paddleocr-vl-1.6").mkdir(parents=True)
    (root / "adapters" / "paddleocr-vl-1.6" / "run_adapter.py").write_text(
        "print('fake adapter')\n", encoding="utf-8"
    )
    lock = root / "upstream-lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "verified_at": "x"}), encoding="utf-8")
    (root / "uv.lock").write_text("uv lock bytes\n", encoding="utf-8")
    (root / "locks").mkdir()
    (root / "locks" / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "normalized_graph_sha256": "1" * 64,
        "locks": {},
    }), encoding="utf-8")
    # The pipeline checkout must never be tracked by the root repo (nested
    # .git internals would otherwise appear in `git diff --binary HEAD`).
    (root / ".gitignore").write_text("fp.json\noutputs/\nmirrors.json\n", encoding="utf-8")
    spec = root / "provisioning.spec.json"
    spec.write_text(json.dumps(provisioning_spec(root)), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.com",
            "add", "-A",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-q", "-m", "seed",
        ],
        check=True,
        capture_output=True,
    )
    return root


def _run(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_provisioning(root, out: Path):
    spec = root / "provisioning.spec.json"
    spec.write_text(json.dumps(provisioning_spec(root)), encoding="utf-8")
    return _run(
        root, "--phase", "provisioning", "--inputs", str(spec), "--out", str(out)
    )


def _check_provisioning(root, out: Path):
    spec = root / "provisioning.spec.json"
    spec.write_text(json.dumps(provisioning_spec(root)), encoding="utf-8")
    return _run(
        root, "--phase", "provisioning", "--inputs", str(spec), "--check", str(out)
    )


def test_fingerprint_contains_phase_and_sha(fingerprint_env):
    result = _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode == 0, result.stderr
    fp = json.loads((fingerprint_env / "fp.json").read_text(encoding="utf-8"))
    assert fp["phase"] == "provisioning"
    assert len(fp["sha256"]) == 64
    for key in (
        "profile_sha256",
        "upstream_lock_sha256",
        "dataset_manifest_sha256",
        "windows_scoring_config_sha256",
        "wsl_cdm_config_sha256",
        "uv_lock_sha256",
        "uv_normalized_graph_sha256",
        "repo_commit",
        "repo_tree_sha256",
    ):
        assert key in fp["inputs"], f"missing input key {key}"


def test_check_passes_when_unchanged(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode == 0, result.stderr


def test_check_fails_when_profile_changes(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    profile = fingerprint_env / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    data = json.loads(profile.read_text(encoding="utf-8"))
    data["description"] = "changed"
    profile.write_text(json.dumps(data), encoding="utf-8")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode != 0
    assert "profile_sha256" in result.stdout + result.stderr


def test_check_fails_when_manifest_changes(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    manifest = fingerprint_env / "eval-infra" / "01-omnidocbench" / "data" / "OmniDocBench_cpu_smoke_10.json"
    manifest.write_text(json.dumps([{"page_info": {"image_path": "b.png"}}]), encoding="utf-8")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode != 0
    assert "dataset_manifest_sha256" in result.stdout + result.stderr


def test_check_fails_when_lock_changes(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    lock = fingerprint_env / "upstream-lock.json"
    lock.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode != 0
    assert "upstream_lock_sha256" in result.stdout + result.stderr


def test_check_fails_when_uv_lock_changes(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    (fingerprint_env / "uv.lock").write_text("different\n", encoding="utf-8")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode != 0
    assert "uv_lock_sha256" in result.stdout + result.stderr


def test_provisioning_is_stable_when_only_mirror_selection_changes(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    (fingerprint_env / "mirrors.json").write_text(json.dumps({
        "schema_version": 1,
        "network_status": "degraded",
        "uv_indexes": [{"id": "aliyun", "reachable": True}],
    }), encoding="utf-8")
    environment_lock = fingerprint_env / "outputs" / "reproduction" / "smoke" / "environment-lock.json"
    environment_lock.parent.mkdir(parents=True)
    environment_lock.write_text(json.dumps({"selected_source_id": "aliyun"}), encoding="utf-8")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_fails_when_normalized_graph_digest_changes(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    manifest = fingerprint_env / "locks" / "manifest.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["normalized_graph_sha256"] = "2" * 64
    manifest.write_text(json.dumps(document), encoding="utf-8")
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode != 0
    assert "uv_normalized_graph_sha256" in result.stdout + result.stderr


def test_provisioning_is_insensitive_to_pipeline_checkout(fingerprint_env):
    """The clean-checkout resume regression: provisioning must NOT bind the
    pipeline checkout (it is created later), so a fresh provisioning fingerprint
    with checkout absent must still --check cleanly once the checkout exists."""
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    subprocess.run(
        [
            "git", "-C", str(fingerprint_env / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"),
            "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-q", "-m", "checkout created later",
        ],
        check=True,
        capture_output=True,
    )
    result = _check_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    assert result.returncode == 0, result.stdout + result.stderr


def test_inference_phase_binds_pipeline_checkout_commit(fingerprint_env):
    spec = fingerprint_env / "inference.spec.json"
    spec.write_text(json.dumps(inference_spec(fingerprint_env)), encoding="utf-8")
    result = _run(
        fingerprint_env, "--phase", "inference", "--inputs", str(spec),
        "--out", str(fingerprint_env / "fp-inference.json"),
    )
    assert result.returncode == 0, result.stderr
    subprocess.run(
        [
            "git", "-C", str(fingerprint_env / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"),
            "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-q", "-m", "pipeline updated",
        ],
        check=True,
        capture_output=True,
    )
    result = _run(
        fingerprint_env, "--phase", "inference", "--inputs", str(spec),
        "--check", str(fingerprint_env / "fp-inference.json"),
    )
    assert result.returncode != 0
    assert "pipeline_checkout_commit" in result.stdout + result.stderr


def test_phase_mismatch_fails(fingerprint_env):
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    spec = fingerprint_env / "inference.spec.json"
    spec.write_text(json.dumps(inference_spec(fingerprint_env)), encoding="utf-8")
    result = _run(
        fingerprint_env, "--phase", "inference", "--inputs", str(spec),
        "--check", str(fingerprint_env / "fp.json"),
    )
    assert result.returncode != 0
    assert "phase" in result.stdout + result.stderr


def test_check_without_previous_file_fails(fingerprint_env):
    result = _check_provisioning(fingerprint_env, fingerprint_env / "nope.json")
    assert result.returncode != 0


def test_same_path_out_and_check_detects_mismatch(fingerprint_env):
    """Regression: --out and --check with the SAME path must compare against
    the previous file, not the just-written one."""
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    profile = fingerprint_env / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    data = json.loads(profile.read_text(encoding="utf-8"))
    data["description"] = "changed before resume"
    profile.write_text(json.dumps(data), encoding="utf-8")
    spec = fingerprint_env / "provisioning.spec.json"
    result = _run(
        fingerprint_env, "--phase", "provisioning", "--inputs", str(spec),
        "--out", str(fingerprint_env / "fp.json"),
        "--check", str(fingerprint_env / "fp.json"),
    )
    assert result.returncode != 0
    assert "profile_sha256" in result.stdout + result.stderr


def test_check_clean_fails_when_tree_is_dirty(fingerprint_env):
    spec = fingerprint_env / "provisioning.spec.json"
    (fingerprint_env / "scratch-uncommitted.txt").write_text("edit\n", encoding="utf-8")
    result = _run(
        fingerprint_env, "--phase", "provisioning", "--inputs", str(spec), "--check-clean"
    )
    assert result.returncode != 0
    assert "dirty" in (result.stdout + result.stderr).lower()


def test_check_clean_passes_when_tree_is_clean(fingerprint_env):
    spec = fingerprint_env / "provisioning.spec.json"
    result = _run(
        fingerprint_env, "--phase", "provisioning", "--inputs", str(spec), "--check-clean"
    )
    assert result.returncode == 0, result.stderr


def test_worktree_content_hash_detects_further_edits(fingerprint_env):
    """The porcelain-hash regression: a second edit to an ALREADY-modified
    tracked file must change the repo_tree hash (porcelain output would not)."""
    _write_provisioning(fingerprint_env, fingerprint_env / "fp.json")
    profile = fingerprint_env / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    data = json.loads(profile.read_text(encoding="utf-8"))
    data["description"] = "first edit"
    profile.write_text(json.dumps(data), encoding="utf-8")
    first = json.loads((fingerprint_env / "fp.json").read_text(encoding="utf-8"))
    data["description"] = "second, deeper edit"
    profile.write_text(json.dumps(data), encoding="utf-8")
    spec = fingerprint_env / "provisioning.spec.json"
    result = _run(
        fingerprint_env, "--phase", "provisioning", "--inputs", str(spec),
        "--out", str(fingerprint_env / "fp2.json"),
    )
    assert result.returncode == 0, result.stderr
    second = json.loads((fingerprint_env / "fp2.json").read_text(encoding="utf-8"))
    assert (
        first["inputs"]["repo_tree_sha256"] != second["inputs"]["repo_tree_sha256"]
    ), "further edits to an already-modified file must change the tree hash"
