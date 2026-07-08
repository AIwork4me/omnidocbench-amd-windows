from __future__ import annotations

import importlib.util
import json
import sys
import types
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


def test_run_pair_probe_writes_probe_metrics_at_case_top_level(tmp_path, monkeypatch):
    diag = load_module()

    def fake_cdm_metrics(left, right, save_vis=False, tmp_dir=""):
        return {
            "recall": 1.0,
            "precision": 1.0,
            "F1_score": 1.0 if left == right else 0.25,
            "tp": 1,
            "gt_tokens": 1,
            "pred_tokens": 1,
        }

    cdm_module = types.ModuleType("src.metrics.cdm.cdm")
    cdm_module.cdm_metrics = fake_cdm_metrics
    monkeypatch.setitem(sys.modules, "src", types.ModuleType("src"))
    monkeypatch.setitem(sys.modules, "src.metrics", types.ModuleType("src.metrics"))
    monkeypatch.setitem(sys.modules, "src.metrics.cdm", types.ModuleType("src.metrics.cdm"))
    monkeypatch.setitem(sys.modules, "src.metrics.cdm.cdm", cdm_module)
    case = {
        "case_id": "cdm-0001",
        "gt_cdm": "x",
        "pred_cdm": "y",
        "pred": "y",
        "edit": 0.01,
    }

    result = diag.run_pair_probe([case], tmp_path)[0]

    assert result["gt_self"]["F1_score"] == 1.0
    assert result["pred_self"]["F1_score"] == 1.0
    assert result["gt_pred"]["F1_score"] == 0.25
    assert result["failure_class"] == "normalization_or_matching"


def test_run_pair_probe_rebuilds_cdm_variants_from_raw_case_text(tmp_path, monkeypatch):
    diag = load_module()
    calls = []

    def fake_build_matrix_cdm_variants(gt, pred):
        assert gt == "raw gt"
        assert pred == "raw pred"
        return "fresh gt", "fresh pred alt"

    def fake_cdm_metrics(left, right, save_vis=False, tmp_dir=""):
        calls.append((left, right))
        return {
            "recall": 1.0,
            "precision": 1.0,
            "F1_score": 1.0 if left == right else 0.25,
            "tp": 1,
            "gt_tokens": 1,
            "pred_tokens": 1,
        }

    cdm_module = types.ModuleType("src.metrics.cdm.cdm")
    cdm_module.cdm_metrics = fake_cdm_metrics
    formula_module = types.ModuleType("src.core.preprocess.formula_cdm")
    formula_module.build_matrix_cdm_variants = fake_build_matrix_cdm_variants
    monkeypatch.setitem(sys.modules, "src", types.ModuleType("src"))
    monkeypatch.setitem(sys.modules, "src.metrics", types.ModuleType("src.metrics"))
    monkeypatch.setitem(sys.modules, "src.metrics.cdm", types.ModuleType("src.metrics.cdm"))
    monkeypatch.setitem(sys.modules, "src.metrics.cdm.cdm", cdm_module)
    monkeypatch.setitem(sys.modules, "src.core", types.ModuleType("src.core"))
    monkeypatch.setitem(sys.modules, "src.core.preprocess", types.ModuleType("src.core.preprocess"))
    monkeypatch.setitem(sys.modules, "src.core.preprocess.formula_cdm", formula_module)
    case = {
        "case_id": "cdm-0001",
        "gt": "raw gt",
        "pred": "raw pred",
        "gt_cdm": "stale gt",
        "pred_cdm": "stale pred",
        "pred_cdm_alt": "stale pred alt",
        "edit": 0.01,
    }

    result = diag.run_pair_probe([case], tmp_path)[0]

    assert calls == [
        ("fresh gt", "fresh gt"),
        ("fresh pred alt", "fresh pred alt"),
        ("fresh gt", "fresh pred alt"),
    ]
    assert result["gt_cdm"] == "fresh gt"
    assert result["pred_cdm_alt"] == "fresh pred alt"


def test_build_report_includes_hard_subset_metrics_and_recovery_potential():
    diag = load_module()
    cases = [
        {"case_id": "cdm-0001", "cdm": 0.0, "failure_class": "pending"},
        {"case_id": "cdm-0002", "cdm": 0.25, "failure_class": "pending"},
    ]
    probes = [
        {"case_id": "cdm-0001", "failure_class": "evaluator_gt_compat"},
        {"case_id": "cdm-0002", "failure_class": "pred_latex_unrenderable"},
    ]
    hard_summary = {
        "notebook_metric_summary": {
            "overall_notebook": 88.25,
            "metrics": {"display_formula_CDM": {"notebook_value": 75.91}},
        }
    }

    report = diag.build_report(
        cases,
        probes,
        run_summary={},
        prediction_stats={},
        hard_run_summary=hard_summary,
    )

    assert "## Hard-Subset Metrics" in report
    assert "- Overall notebook: 88.25" in report
    assert "- display_formula_CDM: 75.91" in report
    assert "## Selected-Case Recovery Potential" in report
    assert "- evaluator_gt_compat: count=1 sample_cdm_gap_upper_bound=1.0000" in report
    assert "- pred_latex_unrenderable: count=1 sample_cdm_gap_upper_bound=0.7500" in report


def test_build_report_includes_official_lightweight_subset_comparison():
    diag = load_module()
    lightweight_summary = {
        "notebook_metric_summary": {
            "overall_notebook": 88.25,
            "metrics": {"display_formula_CDM": {"notebook_value": 75.90}},
        }
    }
    official_summary = {
        "notebook_metric_summary": {
            "overall_notebook": 89.88,
            "metrics": {"display_formula_CDM": {"notebook_value": 80.72}},
        }
    }
    lightweight_stats = {"count": 31, "ok": 31, "fail": 0, "engine": "lightweight"}
    official_stats = {"count": 31, "ok": 31, "fail": 0, "engine": "official"}

    report = diag.build_report(
        cases=[],
        probes=[],
        run_summary={},
        prediction_stats={},
        lightweight_run_summary=lightweight_summary,
        official_run_summary=official_summary,
        lightweight_stats=lightweight_stats,
        official_stats=official_stats,
    )

    assert "## Official Vs Lightweight Hard-Subset Comparison" in report
    assert "- lightweight: pages=31 ok=31 fail=0 Formula CDM=75.9 Overall=88.25" in report
    assert "- official: pages=31 ok=31 fail=0 Formula CDM=80.72 Overall=89.88" in report
    assert "- Formula CDM delta official-lightweight: 4.8200" in report
    assert "Official doc_parser is materially higher on this hard subset" in report
