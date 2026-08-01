"""Tests for report.py benchmark report generator."""
import json
import math
from pathlib import Path

import pytest

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
        assert scores["formula_edit_dist"] == 0.034
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

    @pytest.mark.parametrize("invalid_value", ["NaN", math.nan, math.inf])
    def test_rejects_non_numeric_or_nonfinite_metric(self, invalid_value):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        metric["text_block"]["all"]["Edit_dist"]["ALL_page_avg"] = invalid_value

        with pytest.raises(ValueError, match="text_edit_dist"):
            report.extract_scores(metric)


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
        assert "# OmniDocBench v1.6 -- Test Platform Capability Report" in result
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

    def test_empty_platform_is_rejected(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")

        with pytest.raises(ValueError, match="platform"):
            report.generate_report(scores=metric, stats=stats, platform="   ")


class TestResourceRendering:
    """Resource chapter: GPU memory, RAM rendering."""

    def test_gpu_peak_in_report(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        resource = FIXTURE_DIR / "mock_resource_log.jsonl"

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path=str(resource),
            phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "8.4" in result or "8600" in result  # peak GPU
        assert "GPU VRAM" in result

    def test_gpu_unavailable_renders_warning(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path="",  # no resource log
            phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "Resource log unavailable" in result

    def test_gpu_degraded_renders_partial(self, tmp_path):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        degraded_log = tmp_path / "degraded.jsonl"
        lines = [
            '{"ts": 1.0, "gpu_mem_mib": 1000, "gpu_util_pct": 50, "ram_gib": 4.0, "gpu_level": "gpu-full"}',
            '{"ts": 2.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 4.0, "gpu_level": "gpu-degraded"}',
            '{"ts": 3.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 4.0, "gpu_level": "gpu-degraded"}',
        ]
        degraded_log.write_text("\n".join(lines) + "\n")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path=str(degraded_log),
            phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "partial" in result.lower()

    def test_gpu_unavailable_level_renders_warning(self, tmp_path):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        unavailable_log = tmp_path / "unavailable.jsonl"
        lines = [
            '{"ts": 1.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 4.0, "gpu_level": "gpu-unavailable"}',
        ]
        unavailable_log.write_text("\n".join(lines) + "\n")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path=str(unavailable_log),
            phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "unavailable" in result.lower()

    def test_resource_note_is_rendered(self, tmp_path):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        resource = tmp_path / "resource.jsonl"
        resource.write_text(
            '{"ts":1,"gpu_mem_mib":null,"gpu_util_pct":null,"ram_gib":4,'
            '"gpu_level":"gpu-unavailable","note":"CPU fallback: gfx test failed"}\n',
            encoding="utf-8",
        )

        result = report.generate_report(
            scores=metric,
            stats=stats,
            resource_log_path=str(resource),
            platform="Test",
        )

        assert "Resource note: CPU fallback: gfx test failed" in result

    def test_resource_log_accepts_utf8_bom(self, tmp_path):
        resource = tmp_path / "resource.jsonl"
        resource.write_text(
            '{"ts":1,"gpu_mem_mib":null,"gpu_util_pct":null,"ram_gib":4,"gpu_level":"gpu-unavailable"}\n',
            encoding="utf-8-sig",
        )

        rows = report._read_resource_log(str(resource))

        assert rows[0]["gpu_level"] == "gpu-unavailable"


class TestTimingRendering:
    """Timing chapter: P50/P95/P99, throughput, decomposition."""

    def test_percentiles_in_report(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path="", phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "P50" in result
        assert "P95" in result
        assert "P99" in result
        assert "pages/min" in result

    def test_reconstructed_timing_uses_completion_intervals(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = {
            "count": 3,
            "ok": 3,
            "fail": 0,
            "timing_source": "file_mtime_reconstruction",
            "duration_sec": 60.0,
            "stats": [
                {"status": "ok", "seconds": 0.0, "completed_at_epoch": 100.0},
                {"status": "ok", "seconds": 0.0, "completed_at_epoch": 120.0},
                {"status": "ok", "seconds": 0.0, "completed_at_epoch": 160.0},
            ],
        }

        result = report.generate_report(
            scores=metric,
            stats=stats,
            platform="Test",
            qualifier="cpu-reconstructed",
            run_id="r1",
        )

        assert "reconstructed from prediction file completion timestamps" in result
        assert "Median (P50) | 40.0s / page" in result
        assert "Throughput | 3.0 pages/min" in result
        assert "Timing provenance | File mtime reconstruction" in result


class TestAsciiChart:
    """ASCII chart rendering from resource data."""

    def test_chart_contains_block_char_when_data_present(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        resource = FIXTURE_DIR / "mock_resource_log.jsonl"

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path=str(resource),
            phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "GPU memory (GiB)" in result or "GPU" in result

    def test_chart_skipped_when_no_resource_log(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path="", phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        assert "Resource log unavailable" in result


class TestReferenceMode:
    """Reference mode: stability chapter with mean/std."""

    def test_reference_has_stability_section(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        manifest = _load_json(FIXTURE_DIR / "mock_runs_manifest.json")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path="", phase_log=None, mode="reference",
            platform="Test", qualifier="test", run_id="r1",
            runs_manifest=manifest,
        )

        assert "Stability" in result or "stability" in result.lower()

    def test_reference_computes_mean_std(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")
        manifest = _load_json(FIXTURE_DIR / "mock_runs_manifest.json")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path="", phase_log=None, mode="reference",
            platform="Test", qualifier="test", run_id="r1",
            runs_manifest=manifest,
        )

        assert "Mean" in result or "mean" in result.lower() or "avg" in result.lower()
        assert "Std" in result or "std" in result.lower() or "σ" in result.lower()
        assert "0.035" in result


class TestTraceabilityLinks:
    """Report contains traceability links to source JSON."""

    def test_report_contains_trace_comments(self):
        metric = _load_json(FIXTURE_DIR / "mock_metric_result.json")
        stats = _load_json(FIXTURE_DIR / "mock_run_stats.json")

        result = report.generate_report(
            scores=metric, stats=stats,
            resource_log_path="", phase_log=None, mode="single",
            platform="Test", qualifier="test", run_id="r1",
        )

        traces = [line for line in result.splitlines() if "<!-- trace:" in line]
        assert len(traces) >= 4, f"expected >= 4 trace links, got {len(traces)}"
