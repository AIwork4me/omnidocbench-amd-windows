"""Adapter conformance: manifests, paths, contracts and runtime surfaces.

Every adapter under adapters/ must declare an adapter.json manifest that
passes scripts/validate_adapter_manifest.py (schema + path safety + script
existence), and its inference entrypoint must at minimum answer --help.
Prediction naming, UTF-8, resume and stats-schema behavior are covered by the
per-adapter tests (test_paddleocr_vl_adapter.py, test_adapter_resume.py).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_adapter_manifest.py"
ADAPTERS = REPO_ROOT / "adapters"


def adapter_names() -> list[str]:
    return sorted(
        p.name
        for p in ADAPTERS.iterdir()
        if p.is_dir() and (p / "adapter.json").is_file()
    )


@pytest.mark.parametrize("adapter", adapter_names())
def test_manifest_passes_schema_and_path_safety(adapter):
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--adapter", adapter, "--strict"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ADAPTER MANIFEST OK" in result.stdout


def test_every_adapter_dir_declares_a_manifest():
    for p in ADAPTERS.iterdir():
        if p.is_dir() and p.name != "_template" and not p.name.startswith("."):
            assert (p / "adapter.json").is_file(), f"{p.name} lacks adapter.json"


def test_manifest_paths_are_repo_relative_and_inside_adapter(tmp_path):
    bad = tmp_path / "adapters" / "evil"
    (bad / "adapters" / "evil").mkdir(parents=True)
    manifest = {
        "contract_version": 1,
        "name": "evil",
        "maturity": "experimental",
        "supported_platforms": ["windows"],
        "python_runtime_policy": "3.11",
        "lifecycle": {
            "inference_entrypoint": "../../outside.py",
            "backend_proof_capable": False,
            "resume_support": True,
        },
        "output_contract": {"markdown_per_page": True, "utf8": True, "stats_file": "_run_stats.json"},
        "required_env_vars": [],
    }
    (bad / "adapter.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--adapter", "evil", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert ".." in result.stderr


def test_absolute_manifest_paths_rejected(tmp_path):
    bad = tmp_path / "adapters" / "evil2"
    bad.mkdir(parents=True)
    manifest = {
        "contract_version": 1,
        "name": "evil2",
        "maturity": "experimental",
        "supported_platforms": ["windows"],
        "python_runtime_policy": "3.11",
        "lifecycle": {
            "inference_entrypoint": "C:/Windows/System32/cmd.exe",
            "backend_proof_capable": False,
            "resume_support": True,
        },
        "output_contract": {"markdown_per_page": True, "utf8": True, "stats_file": "_run_stats.json"},
        "required_env_vars": [],
    }
    (bad / "adapter.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--adapter", "evil2", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_missing_declared_script_fails_strict(tmp_path):
    bad = tmp_path / "adapters" / "evil3"
    bad.mkdir(parents=True)
    manifest = {
        "contract_version": 1,
        "name": "evil3",
        "maturity": "experimental",
        "supported_platforms": ["windows"],
        "python_runtime_policy": "3.11",
        "lifecycle": {
            "inference_entrypoint": "adapters/evil3/nope.py",
            "backend_proof_capable": False,
            "resume_support": True,
        },
        "output_contract": {"markdown_per_page": True, "utf8": True, "stats_file": "_run_stats.json"},
        "required_env_vars": [],
    }
    (bad / "adapter.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--adapter", "evil3", "--root", str(tmp_path), "--strict"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "does not exist" in result.stderr


@pytest.mark.parametrize("adapter", adapter_names())
def test_inference_entrypoint_answers_help(adapter):
    manifest = json.loads(
        (ADAPTERS / adapter / "adapter.json").read_text(encoding="utf-8")
    )
    entry = REPO_ROOT / manifest["lifecycle"]["inference_entrypoint"]
    assert entry.is_file()
    if entry.suffix == ".py":
        # Entrypoints with mandatory external environments (e.g. mineru_rocm)
        # cannot import in the test env; they must at least be valid Python.
        compile(entry.read_text(encoding="utf-8"), str(entry), "exec")
        try:
            result = subprocess.run(
                [sys.executable, str(entry), "--help"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(f"{entry} --help hung")
        if result.returncode != 0:
            assert "ModuleNotFoundError" in result.stderr, result.stdout + result.stderr


def test_no_committed_local_environment_files():
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = result.stdout.splitlines()
    for name in tracked:
        parts = Path(name).parts
        assert ".env.local" not in parts, f"machine-local env file tracked: {name}"
        assert not (name.startswith(("C:", "D:")) or name.startswith("/") or name.startswith("\\\\")), f"absolute path tracked: {name}"


def test_manifests_declare_output_and_stats_contract():
    for adapter in adapter_names():
        manifest = json.loads((ADAPTERS / adapter / "adapter.json").read_text(encoding="utf-8"))
        output = manifest["output_contract"]
        assert output["markdown_per_page"] is True
        assert output["utf8"] is True
        assert output["stats_file"] == "_run_stats.json"
        assert "resume_support" in manifest["lifecycle"]
