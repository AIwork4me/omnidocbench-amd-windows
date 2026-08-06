"""Deterministic prediction-tree hashing (scripts/hash_prediction_tree.py).

The tree hash binds scoring to the exact bytes consumed: relative path +
byte length + SHA-256 per manifest-declared file, with missing/unexpected
files and _run_stats.json recorded separately. No mtimes, no timestamps.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "hash_prediction_tree.py"


def _run(*args: str, cwd: Path | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_manifest(path: Path, stems: list[str]) -> Path:
    manifest = path / "manifest.json"
    manifest.write_text(
        json.dumps([{"page_info": {"image_path": f"{s}.png"}} for s in stems]),
        encoding="utf-8",
    )
    return manifest


def tree_hash(out: Path) -> str:
    return json.loads(out.read_text(encoding="utf-8"))["prediction_tree_sha256"]


def _write_long_prediction(pred_dir: Path, stem: str, content: str) -> None:
    """Create <stem>.md even when the absolute path exceeds Windows MAX_PATH."""
    target = pred_dir / f"{stem}.md"
    value = os.fspath(target)
    if os.name == "nt" and not value.startswith("\\\\?\\") and len(value) >= 250:
        value = "\\\\?\\" + os.path.abspath(value)
    with open(value, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def test_long_prediction_paths_are_hashed(tmp_path):
    """Regression: >260-char Windows paths must not make predictions disappear."""
    pred = tmp_path / "p"
    pred.mkdir()
    long_stem = "book_en_" + "x" * 180 + "_page_0001"
    _write_long_prediction(pred, long_stem, "long content\n")
    (pred / "p1.md").write_text("hello", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1", long_stem])
    out = tmp_path / "tree.json"
    result = _run(
        "--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["missing"] == []
    assert len(data["files"]) == 2
    entry = next(e for e in data["files"] if e["path"] == f"{long_stem}.md")
    assert entry["bytes"] == len("long content\n")
    assert entry["sha256"] == hashlib.sha256(b"long content\n").hexdigest()


def test_same_content_same_hash_in_different_dirs(tmp_path):
    pred_a = tmp_path / "a"
    pred_b = tmp_path / "b"
    for pred in (pred_a, pred_b):
        pred.mkdir()
        (pred / "p1.md").write_text("hello", encoding="utf-8")
        (pred / "p2.md").write_text("world\n", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1", "p2"])
    out_a = tmp_path / "tree_a.json"
    out_b = tmp_path / "tree_b.json"
    assert _run("--pred-dir", str(pred_a), "--manifest", str(manifest), "--out", str(out_a)).returncode == 0
    assert _run("--pred-dir", str(pred_b), "--manifest", str(manifest), "--out", str(out_b)).returncode == 0
    assert tree_hash(out_a) == tree_hash(out_b)


def test_content_change_changes_hash(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    (pred / "p1.md").write_text("hello", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1"])
    out = tmp_path / "tree.json"
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    first = tree_hash(out)
    (pred / "p1.md").write_text("hello changed", encoding="utf-8")
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    second = tree_hash(out)
    assert first != second


def test_mtime_and_touch_do_not_change_hash(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    path = pred / "p1.md"
    path.write_text("hello", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1"])
    out = tmp_path / "tree.json"
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    first = tree_hash(out)
    old = path.stat().st_mtime - 60
    os.utime(path, (old, old))
    time.sleep(0.01)
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    second = tree_hash(out)
    assert first == second


def test_files_record_path_bytes_sha256(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    (pred / "p1.md").write_text("abc", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1"])
    out = tmp_path / "tree.json"
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    entry = data["files"][0]
    assert entry["path"] == "p1.md"
    assert entry["bytes"] == 3
    assert entry["sha256"] == hashlib.sha256(b"abc").hexdigest()


def test_missing_and_unexpected_reported_separately(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    (pred / "p1.md").write_text("x", encoding="utf-8")
    (pred / "stray.md").write_text("y", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1", "p2"])
    out = tmp_path / "tree.json"
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["missing"] == ["p2"]
    assert data["unexpected"] == ["stray"]
    assert len(data["files"]) == 1


def test_duplicate_manifest_stems_fail_closed(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    (pred / "p1.md").write_text("x", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([
            {"page_info": {"image_path": "p1.png"}},
            {"page_info": {"image_path": "p1.png"}},
        ]),
        encoding="utf-8",
    )
    out = tmp_path / "tree.json"
    result = _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out))
    assert result.returncode != 0
    assert "duplicate" in result.stderr.lower()


def test_run_stats_hash_recorded(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    (pred / "p1.md").write_text("x", encoding="utf-8")
    stats = pred / "_run_stats.json"
    stats.write_text(json.dumps({"selected_pages": 1}), encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1"])
    out = tmp_path / "tree.json"
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_stats_sha256"] is not None
    assert data["run_stats_sha256"] != data["prediction_tree_sha256"]


def test_output_is_bomless_atomic_json(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    (pred / "p1.md").write_text("x", encoding="utf-8")
    manifest = make_manifest(tmp_path, ["p1"])
    out = tmp_path / "tree.json"
    assert _run("--pred-dir", str(pred), "--manifest", str(manifest), "--out", str(out)).returncode == 0
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert not list(tmp_path.glob("tree.json.tmp"))
    json.loads(raw.decode("utf-8"))


def test_manifest_required(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    result = _run("--pred-dir", str(pred))
    assert result.returncode != 0


def test_invalid_manifest_fails_cleanly(tmp_path):
    pred = tmp_path / "p"
    pred.mkdir()
    manifest = tmp_path / "bad.json"
    manifest.write_text("not json", encoding="utf-8")
    result = _run("--pred-dir", str(pred), "--manifest", str(manifest))
    assert result.returncode != 0


def test_missing_prediction_dir_yields_empty_tree(tmp_path):
    manifest = make_manifest(tmp_path, ["p1"])
    out = tmp_path / "tree.json"
    result = _run("--pred-dir", str(tmp_path / "nope"), "--manifest", str(manifest), "--out", str(out))
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["files"] == []
    assert data["missing"] == ["p1"]
