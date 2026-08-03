from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_predictions.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_predictions", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_validator(image_dir: Path, prediction_dir: Path, coverage: str = "1.0"):
    return subprocess.run(
        [
            # The interpreter running the tests (works on Windows and Linux CI).
            sys.executable,
            str(VALIDATOR),
            "--img-dir",
            str(image_dir),
            "--pred-dir",
            str(prediction_dir),
            "--min-coverage",
            coverage,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_fixture(tmp_path: Path, count: int = 2) -> tuple[Path, Path]:
    image_dir = tmp_path / "images"
    prediction_dir = tmp_path / "predictions"
    image_dir.mkdir()
    prediction_dir.mkdir()
    for index in range(count):
        (image_dir / f"page-{index}.png").write_bytes(b"image")
        (prediction_dir / f"page-{index}.md").write_text(
            f"# Page {index}\n中文\n", encoding="utf-8"
        )
    return image_dir, prediction_dir


def test_complete_utf8_predictions_pass(tmp_path: Path):
    image_dir, prediction_dir = make_fixture(tmp_path)

    result = run_validator(image_dir, prediction_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Usable coverage: 2/2 (100.00%)" in result.stdout
    assert "PREDICTION VERIFY OK" in result.stdout


def test_tiny_single_page_fixture_passes(tmp_path: Path):
    image_dir, prediction_dir = make_fixture(tmp_path, count=1)

    result = run_validator(image_dir, prediction_dir)

    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_prediction_fails_coverage(tmp_path: Path):
    image_dir, prediction_dir = make_fixture(tmp_path)
    (prediction_dir / "page-1.md").unlink()

    result = run_validator(image_dir, prediction_dir)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "missing predictions (1): page-1" in output
    assert "below required 100.00%" in output


def test_non_utf8_and_empty_predictions_fail(tmp_path: Path):
    image_dir, prediction_dir = make_fixture(tmp_path)
    (prediction_dir / "page-0.md").write_bytes(b"\xff\xfe")
    (prediction_dir / "page-1.md").write_text("   \n", encoding="utf-8")

    result = run_validator(image_dir, prediction_dir)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "prediction is not UTF-8: page-0.md" in output
    assert "prediction is empty: page-1.md" in output


def test_case_collision_helper_reports_all_names():
    validator = load_validator()

    collisions = validator.case_collisions(["Page.md", "page.md", "other.md"])

    assert collisions == [["Page.md", "page.md"]]


def test_manifest_can_define_expected_prediction_set(tmp_path: Path):
    validator = load_validator()
    prediction_dir = tmp_path / "predictions"
    prediction_dir.mkdir()
    (prediction_dir / "page.md").write_text("content", encoding="utf-8")
    manifest = tmp_path / "subset.json"
    manifest.write_text(
        '[{"page_info": {"image_path": "page.png"}}]', encoding="utf-8"
    )

    failures = validator.validate_predictions(
        None, prediction_dir, minimum_coverage=1.0, manifest_path=manifest
    )

    assert failures == []


def test_empty_prediction_is_valid_when_gt_is_empty(tmp_path: Path):
    validator = load_validator()
    prediction_dir = tmp_path / "predictions"
    prediction_dir.mkdir()
    (prediction_dir / "page.md").write_text("", encoding="utf-8")
    manifest = tmp_path / "subset.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "page_info": {"image_path": "page.png"},
                    "layout_dets": [
                        {"category_type": "figure"},
                        {"category_type": "text_mask", "text": ""},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    failures = validator.validate_predictions(
        None, prediction_dir, minimum_coverage=1.0, manifest_path=manifest
    )

    assert failures == []


def test_empty_prediction_still_fails_when_gt_is_not_empty(tmp_path: Path):
    validator = load_validator()
    prediction_dir = tmp_path / "predictions"
    prediction_dir.mkdir()
    (prediction_dir / "page.md").write_text("", encoding="utf-8")
    manifest = tmp_path / "subset.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "page_info": {"image_path": "page.png"},
                    "layout_dets": [
                        {"category_type": "text_block", "text": "real gt"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    failures = validator.validate_predictions(
        None, prediction_dir, minimum_coverage=1.0, manifest_path=manifest
    )

    assert any("empty" in failure for failure in failures)