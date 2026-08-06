"""Metric-result provenance sidecar helpers (scripts/metric_provenance.py)."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "metric_provenance.py"


def load_module():
    spec = importlib.util.spec_from_file_location("metric_provenance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_long_file(directory: Path, stem: str, content: bytes) -> None:
    """Create a file whose absolute path exceeds Windows MAX_PATH."""
    target = directory / f"{stem}.json"
    value = os.fspath(target)
    if os.name == "nt" and not value.startswith("\\\\?\\") and len(value) >= 250:
        value = "\\\\?\\" + os.path.abspath(value)
    with open(value, "wb") as fh:
        fh.write(content)


def test_sha256_file_short_path(tmp_path: Path):
    module = load_module()
    path = tmp_path / "result.json"
    path.write_bytes(b"abc")

    assert module.sha256_file(path) == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file_long_path(tmp_path: Path):
    """Regression: >260-char Windows paths must still hash, not report missing."""
    module = load_module()
    long_stem = "metric_result_" + "q" * 180
    _write_long_file(tmp_path, long_stem, b"long result\n")

    digest = module.sha256_file(tmp_path / f"{long_stem}.json")

    assert digest == hashlib.sha256(b"long result\n").hexdigest()


def test_sha256_file_missing_returns_none(tmp_path: Path):
    module = load_module()

    assert module.sha256_file(tmp_path / "nope.json") is None
