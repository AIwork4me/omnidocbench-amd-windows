"""Tests for monitor.py resource sampler."""
import json
import os
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
