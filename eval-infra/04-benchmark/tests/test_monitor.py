"""Tests for monitor.py resource sampler."""
import json
import os
import threading
import time
from pathlib import Path

import pytest

import monitor


def _cleanup(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


class TestSampleBasic:
    """Basic sampling loop: output format, required fields, idempotent append."""

    def test_output_is_valid_jsonl(self, tmp_path):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        stop_file.write_text("stop")
        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        _cleanup(output, stop_file)
        assert len(lines) >= 1

    def test_required_fields_present(self, tmp_path):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        stop_file.write_text("stop")
        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        _cleanup(output, stop_file)
        assert len(lines) >= 1
        sample = lines[0]
        for field in ("ts", "gpu_mem_mib", "gpu_util_pct", "ram_gib", "gpu_level"):
            assert field in sample, f"missing field: {field}"


class TestDegradation:
    """GPU query degradation: gpu-full -> gpu-degraded -> gpu-unavailable."""

    def test_levels_transition_on_consecutive_failures(self, tmp_path, monkeypatch):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"
        call_count = [0]

        def _mock_query():
            call_count[0] += 1
            raise monitor.GPUQueryError("mock failure")

        monkeypatch.setattr(monitor, "_query_gpu_rocm_smi", _mock_query)

        def _delayed_stop():
            time.sleep(0.5)
            stop_file.write_text("stop")

        t = threading.Thread(target=_delayed_stop, daemon=True)
        t.start()

        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        _cleanup(output, stop_file)
        assert len(lines) >= 1

        levels = [s["gpu_level"] for s in lines]
        assert "gpu-degraded" in levels, f"expected degraded, got levels: {levels}"
        if len(lines) >= 31:
            assert "gpu-unavailable" in levels, f"expected unavailable after 30 failures, got: {levels}"

    def test_gpu_mem_null_when_failing(self, tmp_path, monkeypatch):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        def _mock_query():
            raise monitor.GPUQueryError("mock failure")

        monkeypatch.setattr(monitor, "_query_gpu_rocm_smi", _mock_query)

        def _delayed_stop():
            time.sleep(0.05)
            stop_file.write_text("stop")

        t = threading.Thread(target=_delayed_stop, daemon=True)
        t.start()

        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        _cleanup(output, stop_file)
        assert len(lines) >= 1
        for sample in lines:
            assert sample["gpu_mem_mib"] is None
            assert sample["gpu_util_pct"] is None


class TestSentinelExit:
    """Monitor exits cleanly when stop file appears."""

    def test_exits_within_one_second_of_stop_file(self, tmp_path):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        stop_file.write_text("stop")
        start = time.time()
        monitor.sample(interval=0.1, output_path=str(output), stop_file=str(stop_file))
        elapsed = time.time() - start
        _cleanup(output, stop_file)

        assert elapsed < 1.5, f"monitor took {elapsed:.2f}s to exit (expected < 1.5s)"

    def test_output_file_closed_cleanly(self, tmp_path):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        stop_file.write_text("stop")
        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        with open(output) as f:
            content = f.read()
        _cleanup(output, stop_file)
        assert len(content) > 0
        assert content.endswith("\n") or content.endswith("\n}")


class TestIdempotentAppend:
    """Re-running monitor appends, no corruption."""

    def test_second_run_appends_no_corruption(self, tmp_path):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        stop_file.write_text("stop")
        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        os.remove(str(stop_file))
        stop_file.write_text("stop")
        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))

        with open(output) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        _cleanup(output, stop_file)
        assert len(lines) >= 2
        for i, line in enumerate(lines):
            assert "ts" in line, f"line {i} missing ts"
