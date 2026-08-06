"""Strict full-set prediction acceptance: verify_prediction_set.py boundaries."""
from __future__ import annotations

import json
import os
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


def _write_long_prediction(pred_dir: Path, stem: str, content: str) -> None:
    """Create <stem>.md even when the absolute path exceeds Windows MAX_PATH."""
    target = pred_dir / f"{stem}.md"
    value = os.fspath(target)
    if os.name == "nt" and not value.startswith("\\\\?\\") and len(value) >= 250:
        value = "\\\\?\\" + os.path.abspath(value)
    with open(value, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def test_long_prediction_paths_are_valid(tmp_path):
    """Regression: >260-char Windows paths must count as valid predictions."""
    manifest, pred = _make_dataset(tmp_path, 2)
    long_stem = "book_en_" + "y" * 180 + "_page_0001"
    pages = json.loads(manifest.read_text(encoding="utf-8"))
    pages.append({"page_info": {"image_path": f"some/dir/{long_stem}.png"}})
    manifest.write_text(json.dumps(pages), encoding="utf-8")
    _write_long_prediction(pred, long_stem, "long content\n")
    result = _run(
        manifest, pred,
        "--expected-pages", "3", "--min-coverage", "1.0", "--max-failed-pages", "0",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3/3" in result.stdout


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


def test_allowlist_permits_known_failures_and_counts_them(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    (pred / "page-0000.md").unlink()
    (pred / "page-0001.md").unlink()
    summary = tmp_path / "summary.json"
    result = _run(
        manifest, pred,
        "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2",
        "--allowed-failed-page-stems", "page-0000,page-0001",
        "--summary-out", str(summary),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["known_allowed_failures"] == ["page-0000", "page-0001"]
    assert data["unknown_failures"] == []
    assert data["recovered_known_failures"] == []
    assert data["verdict"] == "pass"


def test_unknown_failed_page_outside_allowlist_fails(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    (pred / "page-0000.md").unlink()
    (pred / "page-0001.md").unlink()
    (pred / "page-0002.md").unlink()
    summary = tmp_path / "summary.json"
    result = _run(
        manifest, pred,
        "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2",
        "--allowed-failed-page-stems", "page-0000,page-0001",
        "--summary-out", str(summary),
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "page-0002" in output
    assert "unknown failed pages" in output
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["unknown_failures"] == ["page-0002"]
    assert data["known_allowed_failures"] == ["page-0000", "page-0001"]
    assert data["verdict"] == "fail"


def test_total_failed_budget_still_binds_with_allowlist(tmp_path):
    """Even allowlisted failures cannot exceed maximum_failed_pages."""
    manifest, pred = _make_dataset(tmp_path, 1651)
    for i in range(3):
        (pred / f"page-{i:04d}.md").unlink()
    result = _run(
        manifest, pred,
        "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2",
        "--allowed-failed-page-stems", "page-0000,page-0001,page-0002",
    )
    assert result.returncode != 0
    assert "maximum allowed" in result.stdout + result.stderr


def test_recovered_known_failures_are_reported(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 1651)
    summary = tmp_path / "summary.json"
    result = _run(
        manifest, pred,
        "--expected-pages", "1651", "--min-coverage", "0.998", "--max-failed-pages", "2",
        "--allowed-failed-page-stems", "page-0000,page-0001",
        "--summary-out", str(summary),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["recovered_known_failures"] == ["page-0000", "page-0001"]
    assert data["known_allowed_failures"] == []
    assert data["verdict"] == "pass"


def test_duplicate_manifest_stems_fail(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    pages = json.loads(manifest.read_text(encoding="utf-8"))
    pages.append(dict(pages[0]))
    manifest.write_text(json.dumps(pages), encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "11", "--min-coverage", "1.0", "--max-failed-pages", "0")
    assert result.returncode != 0
    assert "duplicate" in (result.stdout + result.stderr).lower()


def test_run_stats_failed_status_must_match_files(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    (pred / "page-0000.md").unlink()
    stats = {
        "schema_version": 2,
        "selected_pages": 10,
        "count": 10,
        "ok": 9,
        "fail": 1,
        "pages": {"page-0000.png": {"status": "ok"}},
        "invocations": [],
        "failed_pages": [],
    }
    (pred / "_run_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0", "--require-selected")
    assert result.returncode != 0
    assert "page-0000" in result.stdout + result.stderr


def test_run_stats_ok_status_must_not_claim_failure(tmp_path):
    manifest, pred = _make_dataset(tmp_path, 10)
    stats = {
        "schema_version": 2,
        "selected_pages": 10,
        "count": 10,
        "ok": 10,
        "fail": 0,
        "pages": {"page-0000.png": {"status": "failed: boom"}},
        "invocations": [],
        "failed_pages": [],
    }
    (pred / "_run_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    result = _run(manifest, pred, "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0", "--require-selected")
    assert result.returncode != 0
    assert "page-0000" in result.stdout + result.stderr


def test_summary_schema_is_canonical(tmp_path):
    manifest, pred = _make_dataset_with_empty_gt(tmp_path, 10, {"page-0003"})
    (pred / "page-0003.md").write_text("", encoding="utf-8")
    tree = tmp_path / "tree.json"
    tree.write_text(
        json.dumps({"prediction_tree_sha256": "ab" * 32}), encoding="utf-8"
    )
    summary = tmp_path / "prediction-summary.json"
    result = _run(
        manifest, pred,
        "--expected-pages", "10", "--min-coverage", "1.0", "--max-failed-pages", "0",
        "--prediction-tree-json", str(tree), "--summary-out", str(summary),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(summary.read_text(encoding="utf-8"))
    for key in (
        "expected", "manifest_unique_stems", "markdown_files", "valid",
        "empty_gt_valid", "missing", "invalid", "unexpected",
        "known_allowed_failures", "unknown_failures", "recovered_known_failures",
        "coverage", "selected_pages", "prediction_tree_sha256", "verdict",
    ):
        assert key in data, f"summary missing {key}"
    assert data["manifest_unique_stems"] == 10
    assert data["empty_gt_valid"] == 1
    assert data["prediction_tree_sha256"] == "ab" * 32
