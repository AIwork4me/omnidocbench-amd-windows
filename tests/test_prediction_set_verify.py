"""Strict full-set prediction acceptance: verify_prediction_set.py boundaries."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_prediction_set.py"


def _make_dataset(tmp_path, total):
    manifest = []
    img = tmp_path / "images"
    pred = tmp_path / "pred"
    pred.mkdir(parents=True)
    img.mkdir(parents=True)
    for i in range(total):
        name = f"page-{i:04d}.png"
        manifest.append({"page_info": {"image_path": f"some/dir/{name}"}})
        (img / name).write_bytes(b"x")
        (pred / f"page-{i:04d}.md").write_text(f"content {i}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, pred


def _run(manifest, pred_dir, *extra):
    return subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--manifest", str(manifest),
            "--pred-dir", str(pred_dir),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_exact_1651_passes(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1651/1651" in result.stdout


def test_1649_of_1651_passes(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    (pred / "page-0000.md").unlink()
    (pred / "page-0001.md").unlink()
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode == 0, result.stdout + result.stderr


def test_1648_of_1651_fails_coverage(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    for i in range(3):
        (pred / f"page-{i:04d}.md").unlink()
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode != 0
    assert "0.998" in result.stdout + result.stderr


def test_1648_of_1651_passes_with_max_failed_three(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    for i in range(3):
        (pred / f"page-{i:04d}.md").unlink()
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "3")
    assert result.returncode == 0, result.stdout + result.stderr


def test_1600_of_1651_fails(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    for i in range(51):
        (pred / f"page-{i:04d}.md").unlink()
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode != 0


def test_1001_of_1651_fails(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    for i in range(650):
        (pred / f"page-{i:04d}.md").unlink()
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode != 0


def test_ten_page_subset_is_not_full_set(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode != 0
    assert "manifest" in (result.stdout + result.stderr).lower()


def test_invalid_predictions_count_as_failed(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 100)
    (pred / "page-0000.md").write_text("", encoding="utf-8")
    (pred / "page-0001.md").write_bytes(b"\xff\xfe")
    result = _run(manifest, pred, "--expected-pages", "100", "--min-coverage", "0.98", "--max-failed-pages", "0")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "page-0000" in output and "page-0001" in output


def test_unexpected_predictions_are_reported(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    (pred / "foreign-page.md").write_text("x\n", encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0")
    assert result.returncode != 0
    assert "unexpected" in (result.stdout + result.stderr).lower()


def test_run_stats_selected_must_match_when_required(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    stats = {
        "schema_version": 2,
        "selected_pages": 7,
        "newly_processed": 7,
        "skipped_existing": 0,
        "count": 7,
        "ok": 7,
        "fail": 0,
        "pages": {},
        "invocations": [],
        "failed_pages": [],
    }
    (pred / "_run_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0", "--require-selected")
    assert result.returncode != 0
    assert "selected_pages" in (result.stdout + result.stderr)


def test_run_stats_missing_fails_when_required(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0", "--require-selected")
    assert result.returncode != 0
    assert "_run_stats.json" in (result.stdout + result.stderr)


def test_summary_json_is_emitted(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    summary = tmp_path / "prediction-summary.json"
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0", "--summary-out", str(summary))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["expected"] == 10
    assert data["valid"] == 10
    assert data["coverage"] == 1.0
    assert data["verdict"] == "pass"
    assert data["failed_pages"] == []


def _make_dataset_with_empty_gt(tmp_path, total, empty_stems):
    manifest = []
    img = tmp_path / "images"
    pred = tmp_path / "pred"
    pred.mkdir(parents=True)
    img.mkdir(parents=True)
    for i in range(total):
        name = f"page-{i:04d}.png"
        dets = [{"category_type": "text_block", "text": f"gt text {i}"}]
        if f"page-{i:04d}" in empty_stems:
            dets = [{"category_type": "figure"}, {"category_type": "text_mask", "text": ""}]
        manifest.append(
            {"page_info": {"image_path": f"some/dir/{name}"}, "layout_dets": dets}
        )
        (img / name).write_bytes(b"x")
        (pred / f"page-{i:04d}.md").write_text(f"content {i}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, pred


def test_empty_prediction_is_valid_when_gt_is_empty(tmp_path):
    manifest, pred = _make_dataset_with_empty_gt(tmp_path, 10, {"page-0003"})
    (pred / "page-0003.md").write_text("", encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "10/10" in result.stdout


def test_empty_prediction_still_fails_when_gt_is_not_empty(tmp_path):
    manifest, pred = _make_dataset_with_empty_gt(tmp_path, 10, set())
    (pred / "page-0003.md").write_text("", encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0")
    assert result.returncode != 0
    assert "page-0003" in result.stdout + result.stderr


def test_full_set_with_one_empty_gt_page_and_two_missing_passes(tmp_path):
    """The real 1651 outcome: 1 empty-GT page predicted empty + 2 missing."""
    manifest, pred = _make_dataset_with_empty_gt(tmp_path, 1651, {"page-1650"})
    (pred / "page-1650.md").write_text("", encoding="utf-8")
    (pred / "page-0000.md").unlink()
    (pred / "page-0001.md").unlink()
    result = _run(manifest, pred, "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1649/1651" in result.stdout
