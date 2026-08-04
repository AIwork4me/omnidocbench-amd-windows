"""Sample prediction equivalence: deterministic selection + byte comparison."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sample_prediction_equivalence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sample_equiv", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selection_is_deterministic_and_covers_the_set():
    module = load_module()
    stems = [f"p-{i:04d}" for i in range(1000)]
    first = module.select_sample(stems, 50)
    second = module.select_sample(stems, 50)
    assert first == second, "selection must be deterministic"
    assert len(first) == 50
    assert first == sorted(first)
    # stride sampling must cover the whole range (first and last regions)
    assert first[0] == "p-0000" and first[-1] == "p-0980"


def test_selection_returns_all_when_sample_exceeds_total():
    module = load_module()
    stems = [f"p-{i}" for i in range(10)]
    assert module.select_sample(stems, 50) == sorted(stems)


def test_selection_rejects_non_positive_sample():
    module = load_module()
    try:
        module.select_sample(["a"], 0)
    except ValueError:
        pass
    else:
        raise AssertionError("sample_size 0 must fail")


def test_compare_predictions_detects_byte_diffs(tmp_path):
    module = load_module()
    stored = tmp_path / "stored"
    fresh = tmp_path / "fresh"
    stored.mkdir()
    fresh.mkdir()
    (stored / "a.md").write_text("same\n", encoding="utf-8")
    (fresh / "a.md").write_text("same\n", encoding="utf-8")
    (stored / "b.md").write_text("old\n", encoding="utf-8")
    (fresh / "b.md").write_text("new\n", encoding="utf-8")
    (stored / "c.md").write_text("x\n", encoding="utf-8")
    # c.md missing in fresh
    diffs = module.compare_predictions(stored, fresh, ["a", "b", "c"])
    issues = [d["issue"] for d in diffs]
    assert issues == ["content differs", "fresh prediction missing"]


def test_compare_predictions_handles_empty_files(tmp_path):
    module = load_module()
    stored = tmp_path / "stored"
    fresh = tmp_path / "fresh"
    stored.mkdir()
    fresh.mkdir()
    (stored / "empty.md").write_text("", encoding="utf-8")
    (fresh / "empty.md").write_text("", encoding="utf-8")
    assert module.compare_predictions(stored, fresh, ["empty"]) == []


def test_glyph_level_variance_is_equivalent(tmp_path):
    """Model outputs are not byte-reproducible across runs; bullet/quote
    glyph variants are content-equivalent and must pass."""
    module = load_module()
    stored = tmp_path / "stored"
    fresh = tmp_path / "fresh"
    stored.mkdir()
    fresh.mkdir()
    (stored / "p.md").write_text("- Have taught CS courses\n", encoding="utf-8")
    (fresh / "p.md").write_text("– Have taught CS courses\n", encoding="utf-8")
    assert module.compare_predictions(stored, fresh, ["p"]) == []


def test_substantial_content_change_is_not_equivalent(tmp_path):
    module = load_module()
    stored = tmp_path / "stored"
    fresh = tmp_path / "fresh"
    stored.mkdir()
    fresh.mkdir()
    (stored / "p.md").write_text("The quick brown fox jumps over the lazy dog.\n", encoding="utf-8")
    (fresh / "p.md").write_text("Totally different paragraph about something else entirely.\n", encoding="utf-8")
    diffs = module.compare_predictions(stored, fresh, ["p"])
    assert diffs and diffs[0]["issue"] == "content differs"


def test_build_sample_image_dir_copies_expected_images(tmp_path):
    module = load_module()
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "p-00.png").write_bytes(b"a")
    (img_dir / "p-01.jpg").write_bytes(b"b")
    # Lowercase extension: the .png probe is case-sensitive on Linux CI (a
    # p-02.PNG fixture would only resolve on case-insensitive Windows).
    (img_dir / "p-02.png").write_bytes(b"c")
    out = module.build_sample_image_dir(img_dir, ["p-00", "p-01", "p-02"], tmp_path / "work")
    names = sorted(p.name for p in out.iterdir())
    assert len(names) == 3
    assert {name.lower() for name in names} == {"p-00.png", "p-01.jpg", "p-02.png"}
