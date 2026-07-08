from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "eval-infra" / "03-scoring" / "formula_cdm_diagnostics.py"


def load_module():
    spec = importlib.util.spec_from_file_location("formula_cdm_diagnostics", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample(idx, cdm, edit, pred="x", gt="x", img="page.png"):
    return {
        "gt_idx": [idx],
        "gt": gt,
        "pred_idx": [idx],
        "pred": pred,
        "edit": edit,
        "metric": {"CDM": cdm, "Edit_dist": edit},
        "img_id": img,
        "image_name": img,
        "gt_cdm": gt,
        "pred_cdm": pred,
        "pred_cdm_alt": "",
    }


def test_select_hard_cases_prioritizes_zero_and_close_low_cases():
    diag = load_module()
    samples = [
        sample(1, 0.99, 0.0),
        sample(2, 0.0, 0.4),
        sample(3, 0.4, 0.1),
        sample(4, 0.8, 0.2),
    ]

    cases = diag.select_hard_cases(samples, limit=3)

    assert [c["idx"] for c in cases] == [1, 2, 3]
    assert cases[0]["selection_reason"] == "control_high_cdm"
    assert cases[1]["selection_reason"] == "cdm_zero"
    assert cases[2]["selection_reason"] == "cdm_low_edit_close"


def test_classify_probe_detects_gt_compat_failure():
    diag = load_module()
    case = {"pred": "x", "edit": 0.02}
    probe = {
        "gt_self": {"F1_score": 0.0, "gt_tokens": 0},
        "pred_self": {"F1_score": 1.0, "pred_tokens": 2},
        "gt_pred": {"F1_score": 0.0},
    }

    assert diag.classify_probe(case, probe) == "evaluator_gt_compat"


def test_classify_probe_detects_prediction_render_failure():
    diag = load_module()
    case = {"pred": r"\bad", "edit": 0.02}
    probe = {
        "gt_self": {"F1_score": 1.0, "gt_tokens": 2},
        "pred_self": {"F1_score": 0.0, "pred_tokens": 0},
        "gt_pred": {"F1_score": 0.0},
    }

    assert diag.classify_probe(case, probe) == "pred_latex_unrenderable"


def test_write_page_manifest_filters_selected_pages(tmp_path):
    diag = load_module()
    full_manifest = [
        {"img_id": "a.png", "page_info": 1},
        {"img_id": "b.png", "page_info": 2},
    ]
    cases = [{"img_id": "b.png"}]
    out = tmp_path / "hard.json"

    count = diag.write_page_manifest(full_manifest, cases, out)

    assert count == 1
    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"img_id": "b.png", "page_info": 2}
    ]
