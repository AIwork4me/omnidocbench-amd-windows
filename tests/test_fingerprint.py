"""Fingerprint gating for reproduce.ps1 -Resume: refuse stale reuse."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "compute_fingerprint.py"
PROFILE = REPO_ROOT / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
MANIFEST = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "data" / "OmniDocBench_cpu_smoke_10.json"
CONFIG = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "configs" / "v16-cpu-smoke-10.yaml"


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
    lock = root / "upstream-lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "verified_at": "x"}), encoding="utf-8")
    (root / ".gitignore").write_text("fp.json\n", encoding="utf-8")
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


def test_fingerprint_contains_all_critical_keys(fingerprint_env):
    result = _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    assert result.returncode == 0, result.stderr
    fp = json.loads((fingerprint_env / "fp.json").read_text(encoding="utf-8"))
    for key in (
        "profile_sha256",
        "upstream_lock_sha256",
        "dataset_manifest_sha256",
        "windows_scoring_config_sha256",
        "wsl_cdm_config_sha256",
        "pipeline_checkout_commit",
        "repo_commit",
        "repo_dirty",
    ):
        assert key in fp, f"missing key {key}"


def test_check_passes_when_unchanged(fingerprint_env):
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode == 0, result.stderr


def test_check_fails_when_profile_changes(fingerprint_env):
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    profile = fingerprint_env / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    data = json.loads(profile.read_text(encoding="utf-8"))
    data["description"] = "changed"
    profile.write_text(json.dumps(data), encoding="utf-8")
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode != 0
    assert "profile_sha256" in result.stdout + result.stderr


def test_check_fails_when_manifest_changes(fingerprint_env):
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    manifest = fingerprint_env / "eval-infra" / "01-omnidocbench" / "data" / "OmniDocBench_cpu_smoke_10.json"
    manifest.write_text(json.dumps([{"page_info": {"image_path": "b.png"}}]), encoding="utf-8")
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode != 0
    assert "dataset_manifest_sha256" in result.stdout + result.stderr


def test_check_fails_when_lock_changes(fingerprint_env):
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    lock = fingerprint_env / "upstream-lock.json"
    lock.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode != 0
    assert "upstream_lock_sha256" in result.stdout + result.stderr


def test_check_fails_when_pipeline_commit_changes(fingerprint_env):
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    subprocess.run(
        [
            "git", "-C", str(fingerprint_env / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"),
            "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-q", "-m", "change",
        ],
        check=True,
        capture_output=True,
    )
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode != 0
    assert "pipeline_checkout_commit" in result.stdout + result.stderr


def test_dirty_repo_flag_is_recorded(fingerprint_env, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    result = _run(repo, "--out", str(fingerprint_env / "fp.json"))
    assert result.returncode == 0, result.stderr
    fp = json.loads((fingerprint_env / "fp.json").read_text(encoding="utf-8"))
    assert "repo_dirty" in fp
    assert "repo_commit" in fp


def test_missing_pipeline_is_recorded_as_absent(fingerprint_env):
    subprocess.run(
        ["cmd", "/c", "rmdir", "/s", "/q", str(fingerprint_env / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm" / ".git")],
        capture_output=True,
        check=False,
    )
    result = _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    assert result.returncode == 0, result.stderr
    fp = json.loads((fingerprint_env / "fp.json").read_text(encoding="utf-8"))
    assert fp["pipeline_checkout_commit"] is None


def test_check_without_previous_file_fails(fingerprint_env):
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "nope.json"))
    assert result.returncode != 0


def test_same_path_out_and_check_detects_mismatch(fingerprint_env):
    """Regression: --out and --check with the SAME path must compare against
    the previous file, not the just-written one (the gate used to compare the
    fingerprint to itself and always pass)."""
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    profile = fingerprint_env / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    data = json.loads(profile.read_text(encoding="utf-8"))
    data["description"] = "changed before resume"
    profile.write_text(json.dumps(data), encoding="utf-8")
    result = _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"), "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode != 0
    assert "profile_sha256" in result.stdout + result.stderr


def test_porcelain_hash_detects_uncommitted_edits(fingerprint_env):
    _run(fingerprint_env, "--out", str(fingerprint_env / "fp.json"))
    (fingerprint_env / "scratch-uncommitted.txt").write_text("edit\n", encoding="utf-8")
    result = _run(fingerprint_env, "--check", str(fingerprint_env / "fp.json"))
    assert result.returncode != 0
    assert "repo_porcelain_sha256" in result.stdout + result.stderr
