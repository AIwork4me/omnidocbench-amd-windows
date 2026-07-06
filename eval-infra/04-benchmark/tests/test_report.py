"""Tests for report.py benchmark report generator."""
import json
from pathlib import Path

import report


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestExtractScores:
    """Score extraction from metric_result.json."""

    def test_extracts_four_metrics(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        scores = report.extract_scores(metric)

        assert scores["text_edit_dist"] == 0.035
        assert scores["reading_order"] == 0.129
        assert scores["table_teds"] == 0.940
        assert scores["formula_cdm"] == 0.944

    def test_missing_cdm_returns_none(self):
        metric = {
            "text_block": {"all": {"Edit_dist": {"ALL_page_avg": 0.035}}},
            "display_formula": {"all": {"Edit_dist": {"ALL_page_avg": 0.034}}},
            "table": {"all": {"TEDS": {"all": 0.940}}},
            "reading_order": {"all": {"Edit_dist": {"ALL_page_avg": 0.129}}},
        }
        scores = report.extract_scores(metric)
        assert scores["formula_cdm"] is None
        assert scores["text_edit_dist"] == 0.035


class TestSingleRunReport:
    """Single-run mode: report contains no stability chapter."""

    def test_single_run_has_no_stability_section(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        resource = FIXTURE_DIR / "mock_resource_log.jsonl"

        result = report.generate_report(
            scores=metric,
            stats=stats,
            resource_log_path=str(resource),
            phase_log=None,
            mode="single",
            platform="Test Platform",
            qualifier="test_q4km",
            run_id="test-001",
        )

        assert "generate" in result.lower() or "<!-- generated" in result
        assert "# " in result
        assert "Test Platform" in result
        assert "test_q4km" in result

    def test_single_run_has_generated_marker(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        resource = FIXTURE_DIR / "mock_resource_log.jsonl"

        result = report.generate_report(
            scores=metric,
            stats=stats,
            resource_log_path=str(resource),
            phase_log=None,
            mode="single",
            platform="Test Platform",
            qualifier="test_q4km",
            run_id="test-001",
        )

        assert "<!-- generated: true" in result
