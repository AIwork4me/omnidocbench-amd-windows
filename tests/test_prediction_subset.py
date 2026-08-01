from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_prediction_subset.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_prediction_subset", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_manifest(path: Path, names: list[str]) -> None:
    path.write_text(
        json.dumps([{"page_info": {"image_path": name}} for name in names]),
        encoding="utf-8",
    )


def test_builds_sorted_exact_subset_and_preserves_unicode(tmp_path: Path):
    module = load_module()
    manifest = tmp_path / "full.json"
    predictions = tmp_path / "predictions"
    output = tmp_path / "subset.json"
    predictions.mkdir()
    write_manifest(manifest, ["页面-b.png", "page-a.png", "page-c.png"])
    (predictions / "页面-b.md").write_text("内容", encoding="utf-8")
    (predictions / "page-a.md").write_text("text", encoding="utf-8")
    (predictions / "page-c.md").write_text("text", encoding="utf-8")

    subset = module.build_subset(manifest, predictions, output, limit=2)

    assert [page["page_info"]["image_path"] for page in subset] == [
        "page-a.png",
        "page-c.png",
    ]
    assert "页面" not in output.read_text(encoding="utf-8")


def test_rejects_fewer_predictions_than_required(tmp_path: Path):
    module = load_module()
    manifest = tmp_path / "full.json"
    predictions = tmp_path / "predictions"
    output = tmp_path / "subset.json"
    predictions.mkdir()
    write_manifest(manifest, ["page-a.png", "page-b.png"])
    (predictions / "page-a.md").write_text("text", encoding="utf-8")

    with pytest.raises(ValueError, match="only 1 usable predictions"):
        module.build_subset(manifest, predictions, output, limit=2)


def test_rejects_prediction_without_ground_truth(tmp_path: Path):
    module = load_module()
    manifest = tmp_path / "full.json"
    predictions = tmp_path / "predictions"
    output = tmp_path / "subset.json"
    predictions.mkdir()
    write_manifest(manifest, ["page-a.png"])
    (predictions / "unknown.md").write_text("text", encoding="utf-8")

    with pytest.raises(ValueError, match="no ground truth"):
        module.build_subset(manifest, predictions, output)


def test_builder_routes_repo_predictions_through_short_path():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "through_short_repo(prediction_dir, REPO_ROOT)" in text


def test_cpu_200_configs_use_deterministic_single_worker_scoring():
    for name in ("v16-cpu-200.yaml", "v16-cdm-cpu-200.yaml"):
        text = (
            REPO_ROOT
            / "eval-infra"
            / "01-omnidocbench"
            / "configs"
            / name
        ).read_text(encoding="utf-8")
        assert "teds_workers: 1" in text
        assert "match_workers: 1" in text