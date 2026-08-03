"""GT-emptiness edge cases shared by validators and the adapter."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "gt_manifest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("gt_manifest", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_layout_dets_key_is_non_empty():
    module = load_module()
    assert module.page_has_empty_gt({"page_info": {}}) is False


def test_ignored_dets_do_not_count():
    module = load_module()
    page = {
        "layout_dets": [
            {"category_type": "text_block", "text": "real content", "ignore": True},
            {"category_type": "figure"},
        ]
    }
    assert module.page_has_empty_gt(page) is True


def test_latex_only_content_counts_as_non_empty():
    module = load_module()
    page = {"layout_dets": [{"category_type": "equation_isolated", "latex": "x^2"}]}
    assert module.page_has_empty_gt(page) is False


def test_html_only_content_counts_as_non_empty():
    module = load_module()
    page = {"layout_dets": [{"category_type": "table", "html": "<table><tr><td>1</td></tr></table>"}]}
    assert module.page_has_empty_gt(page) is False


def test_content_field_counts_as_non_empty():
    module = load_module()
    page = {"layout_dets": [{"category_type": "text_block", "content": "preprocessed"}]}
    assert module.page_has_empty_gt(page) is False


def test_empty_dets_are_empty_gt():
    module = load_module()
    page = {
        "layout_dets": [
            {"category_type": "figure"},
            {"category_type": "text_mask", "text": ""},
        ]
    }
    assert module.page_has_empty_gt(page) is True


def test_empty_gt_stems_skips_pages_without_image_path():
    module = load_module()
    pages = [
        {"page_info": {"image_path": "d/empty.png"}, "layout_dets": [{"category_type": "figure"}]},
        {"page_info": {"image_path": "d/full.png"}, "layout_dets": [{"category_type": "text_block", "text": "x"}]},
        {"page_info": {}},
    ]
    assert module.empty_gt_stems(pages) == {"empty"}
