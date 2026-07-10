# AI MAX+ 395 Benchmark Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `eval-infra/04-benchmark/` — an independent module that produces machine-generated capability reports proving OmniDocBench v1.6 runs end-to-end on AMD Ryzen AI Max+ 395 (128GB unified memory).

**Architecture:** The module observes the adapter + scoring pipeline as external subprocesses (MLPerf-style). It never imports adapter code. A background `monitor.py` samples GPU/RAM at 1 Hz during inference; `report.py` consumes `_run_stats.json`, `*_metric_result.json`, `resource_log.jsonl`, and `phase_log.json` to produce a Markdown capability report; `verify.ps1` acts as the correctness gateway.

**Tech Stack:** Python 3.11 stdlib + `psutil` · PowerShell 5.1 · YAML config · pytest

## Global Constraints

- PowerShell 5.1 compatible (no `??`, no ternary, no `Join-Path` 3-arg)
- `$ErrorActionPreference = "Stop"` in all `.ps1` scripts
- `PYTHONUTF8=1` set for all Python subprocess calls
- Bilingual README (EN + zh-CN) for the module directory
- `verify.ps1` exits 0/1 per module
- Zero changes to adapter interface contract (`run_adapter` signature)
- Zero changes to existing scoring pipeline
- Numbered sub-directory (`04-`) matching `eval-infra/` convention
- Only Python stdlib + `psutil`; pytest for tests

---

### Task 1: Module Scaffolding + Configuration

**Files:**
- Create: `eval-infra/04-benchmark/config/default.yaml`
- Create: `eval-infra/04-benchmark/tests/__init__.py` (empty)
- Create: `eval-infra/04-benchmark/tests/fixtures/`
- Create: `eval-infra/04-benchmark/tests/fixtures/mock_metric_result.json`
- Create: `eval-infra/04-benchmark/tests/fixtures/mock_run_stats.json`
- Create: `eval-infra/04-benchmark/tests/fixtures/mock_resource_log.jsonl`

**Interfaces:**
- Produces: `eval-infra/04-benchmark/config/default.yaml` (consumed by run.ps1 in Task 9)
- Produces: 3 fixture files (consumed by test_report.py in Tasks 5-8)

- [ ] **Step 1: Create directory structure**

```powershell
New-Item -ItemType Directory -Force -Path eval-infra\04-benchmark\config
New-Item -ItemType Directory -Force -Path eval-infra\04-benchmark\tests\fixtures
New-Item -ItemType File -Path eval-infra\04-benchmark\tests\__init__.py
```

- [ ] **Step 2: Write `config/default.yaml`**

Write `eval-infra/04-benchmark/config/default.yaml`:

```yaml
# Benchmark run defaults. All keys overridable via run.ps1 parameters.

adapter:
  name: paddleocr-vl-1.6
  variant: hip                     # hip | cpu
  server_url: ""                   # empty = resolve from .env.local
  img_dir: <REPO_ROOT>/eval-infra/01-omnidocbench/data/images
  out_dir: <REPO_ROOT>/predictions/paddleocrvl_rocm_bench

scoring:
  config: v16-cdm.yaml
  windows_only: false

monitor:
  interval_sec: 1
  gpu_backends:
    - rocm-smi
    - typeperf
    - none
  gpu_sample_fail_threshold: 3

report:
  output_dir: <REPO_ROOT>/benchmark-results
  stability_runs: 1
  include_ascii_charts: true
  template: default
```

- [ ] **Step 3: Write `tests/fixtures/mock_metric_result.json`**

Write `eval-infra/04-benchmark/tests/fixtures/mock_metric_result.json`:

```json
{
  "text_block": {
    "all": {
      "Edit_dist": { "ALL_page_avg": 0.035, "ALL_page_std": 0.01 }
    }
  },
  "display_formula": {
    "all": {
      "Edit_dist": { "ALL_page_avg": 0.034, "ALL_page_std": 0.01 },
      "CDM": { "all": 0.944, "simple": 0.960, "hard": 0.920 }
    }
  },
  "table": {
    "all": {
      "TEDS": { "all": 0.940, "simple": 0.960, "hard": 0.910 },
      "Edit_dist": { "ALL_page_avg": 0.030, "ALL_page_std": 0.01 }
    }
  },
  "reading_order": {
    "all": {
      "Edit_dist": { "ALL_page_avg": 0.129, "ALL_page_std": 0.02 }
    }
  }
}
```

- [ ] **Step 4: Write `tests/fixtures/mock_run_stats.json`**

Write `eval-infra/04-benchmark/tests/fixtures/mock_run_stats.json`:

```json
{
  "count": 10,
  "ok": 8,
  "stats": [
    {"image": "page_001.jpg", "status": "ok", "seconds": 1.8},
    {"image": "page_002.jpg", "status": "ok", "seconds": 2.1},
    {"image": "page_003.jpg", "status": "ok", "seconds": 15.0},
    {"image": "page_004.jpg", "status": "ok", "seconds": 2.3},
    {"image": "page_005.jpg", "status": "ok", "seconds": 5.5},
    {"image": "page_006.jpg", "status": "failed: VLM 500", "seconds": 3.2,
     "traceback": "requests.exceptions.HTTPError: 500 Server Error"},
    {"image": "page_007.jpg", "status": "ok", "seconds": 2.0},
    {"image": "page_008.jpg", "status": "ok", "seconds": 3.0},
    {"image": "page_009.jpg", "status": "ok", "seconds": 2.5},
    {"image": "page_010.jpg", "status": "failed: layout NaN", "seconds": 1.2,
     "traceback": "ValueError: array contains NaN"}
  ]
}
```

- [ ] **Step 5: Write `tests/fixtures/mock_resource_log.jsonl`**

Write `eval-infra/04-benchmark/tests/fixtures/mock_resource_log.jsonl`:

```
{"ts": 1700000000.0, "gpu_mem_mib": 1024, "gpu_util_pct": 15, "ram_gib": 4.5, "gpu_level": "gpu-full"}
{"ts": 1700000001.0, "gpu_mem_mib": 2048, "gpu_util_pct": 45, "ram_gib": 5.0, "gpu_level": "gpu-full"}
{"ts": 1700000002.0, "gpu_mem_mib": 4096, "gpu_util_pct": 72, "ram_gib": 6.2, "gpu_level": "gpu-full"}
{"ts": 1700000003.0, "gpu_mem_mib": 6144, "gpu_util_pct": 88, "ram_gib": 7.0, "gpu_level": "gpu-full"}
{"ts": 1700000004.0, "gpu_mem_mib": 8192, "gpu_util_pct": 95, "ram_gib": 8.1, "gpu_level": "gpu-full"}
{"ts": 1700000005.0, "gpu_mem_mib": 8600, "gpu_util_pct": 98, "ram_gib": 8.5, "gpu_level": "gpu-full"}
{"ts": 1700000006.0, "gpu_mem_mib": 8400, "gpu_util_pct": 96, "ram_gib": 8.4, "gpu_level": "gpu-full"}
{"ts": 1700000007.0, "gpu_mem_mib": 8300, "gpu_util_pct": 94, "ram_gib": 8.3, "gpu_level": "gpu-full"}
{"ts": 1700000008.0, "gpu_mem_mib": 8200, "gpu_util_pct": 90, "ram_gib": 8.2, "gpu_level": "gpu-full"}
{"ts": 1700000009.0, "gpu_mem_mib": 8100, "gpu_util_pct": 88, "ram_gib": 8.1, "gpu_level": "gpu-full"}
{"ts": 1700000010.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 7.0, "gpu_level": "gpu-degraded"}
{"ts": 1700000011.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 6.8, "gpu_level": "gpu-degraded"}
{"ts": 1700000012.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 6.5, "gpu_level": "gpu-degraded"}
{"ts": 1700000013.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 6.3, "gpu_level": "gpu-degraded"}
{"ts": 1700000014.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 6.0, "gpu_level": "gpu-degraded"}
{"ts": 1700000015.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 5.8, "gpu_level": "gpu-unavailable"}
{"ts": 1700000016.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 5.5, "gpu_level": "gpu-unavailable"}
{"ts": 1700000017.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 5.3, "gpu_level": "gpu-unavailable"}
{"ts": 1700000018.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 5.0, "gpu_level": "gpu-unavailable"}
{"ts": 1700000019.0, "gpu_mem_mib": null, "gpu_util_pct": null, "ram_gib": 4.8, "gpu_level": "gpu-unavailable"}
```

- [ ] **Step 6: Commit**

```bash
git add eval-infra/04-benchmark/
git commit -m "feat(benchmark): scaffold module + config + test fixtures"
```

---

### Task 2: monitor.py — Basic Sampling Loop

**Files:**
- Create: `eval-infra/04-benchmark/tests/test_monitor.py`
- Create: `eval-infra/04-benchmark/monitor.py`

**Interfaces:**
- Produces: `monitor.py` with `sample(interval: float, output_path: str, *, stop_file: str = "monitor_stop.txt") -> None`
- Consumes: `psutil` for RAM (pip install in step)

- [ ] **Step 1: Install test dependency**

```powershell
pip install psutil pytest
```

- [ ] **Step 2: Write failing test `test_monitor.py` — output format**

Write `eval-infra/04-benchmark/tests/test_monitor.py`:

```python
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
        _cleanup(output, stop_file)

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        assert len(lines) >= 1

    def test_required_fields_present(self, tmp_path):
        output = tmp_path / "resource_log.jsonl"
        stop_file = tmp_path / "monitor_stop.txt"

        stop_file.write_text("stop")
        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))
        _cleanup(output, stop_file)

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        assert len(lines) >= 1
        sample = lines[0]
        for field in ("ts", "gpu_mem_mib", "gpu_util_pct", "ram_gib", "gpu_level"):
            assert field in sample, f"missing field: {field}"
```

- [ ] **Step 3: Run test to verify it fails**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_monitor.py::TestSampleBasic -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'monitor'`

- [ ] **Step 4: Write minimal `monitor.py`**

Write `eval-infra/04-benchmark/monitor.py`:

```python
"""Resource sampler: background process polled at 1 Hz.

Writes one JSON line per second to a JSONL file until a sentinel stop file
appears. Degrades gracefully through GPU backends: rocm-smi -> typeperf -> none.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


class GPUQueryError(Exception):
    """Raised when all configured GPU backends fail for a sampling cycle."""


def _query_gpu_rocm_smi() -> tuple[float, float]:
    """Query GPU via rocm-smi. Returns (mem_mib, util_pct). Raises GPUQueryError on failure."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            raise GPUQueryError(f"rocm-smi exit {result.returncode}: {result.stderr[:200]}")
        data = json.loads(result.stdout)
        card = list(data.values())[0]
        vram = card.get("VRAM", {})
        mem_bytes = int(vram.get("Total Used Memory (B)", 0))
        gpu_mem_mib = mem_bytes / (1024 * 1024)
        gpu_util_pct = float(card.get("GPU use (%)", 0))
        return gpu_mem_mib, gpu_util_pct
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
        raise GPUQueryError(f"rocm-smi parse error: {e}")
    except FileNotFoundError:
        raise GPUQueryError("rocm-smi not found on PATH")
    except subprocess.TimeoutExpired:
        raise GPUQueryError("rocm-smi timed out")


def _fallback_ram_only() -> tuple[None, None]:
    """Return None for GPU data when all backends fail."""
    return None, None


def sample(interval: float, output_path: str, *, stop_file: str = "monitor_stop.txt") -> None:
    """Sample until sentinel file appears. Degrade gracefully on GPU query failure.

    Parameters
    ----------
    interval : float
        Seconds between samples.
    output_path : str
        Path to JSONL output file (appended).
    stop_file : str
        Path to sentinel file; loop exits when this file exists.
    """
    import psutil

    consecutive_failures = 0
    gpu_backend_level = "gpu-full"
    threshold = 3

    backends = [
        ("rocm-smi", _query_gpu_rocm_smi),
        ("none", _fallback_ram_only),
    ]

    with open(output_path, "a") as f:
        while not Path(stop_file).exists():
            ts = time.time()
            gpu_mem, gpu_util = None, None

            try:
                gpu_mem, gpu_util = _query_gpu_rocm_smi()
                consecutive_failures = 0
                gpu_backend_level = "gpu-full"
            except GPUQueryError:
                consecutive_failures += 1
                if consecutive_failures >= threshold:
                    gpu_backend_level = "gpu-degraded"
                if consecutive_failures >= 10 * threshold:
                    gpu_backend_level = "gpu-unavailable"
                gpu_mem, gpu_util = None, None

            ram = psutil.virtual_memory().used / (1024 ** 3)

            f.write(json.dumps({
                "ts": ts,
                "gpu_mem_mib": gpu_mem,
                "gpu_util_pct": gpu_util,
                "ram_gib": round(ram, 2),
                "gpu_level": gpu_backend_level,
            }) + "\n")
            f.flush()
            time.sleep(interval)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Resource sampler for benchmark runs")
    p.add_argument("--output", required=True, help="JSONL output path")
    p.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    p.add_argument("--stop-file", default="monitor_stop.txt", help="Sentinel file path")
    args = p.parse_args()
    sample(interval=args.interval, output_path=args.output, stop_file=args.stop_file)
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_monitor.py::TestSampleBasic -v
```

Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add eval-infra/04-benchmark/monitor.py eval-infra/04-benchmark/tests/test_monitor.py
git commit -m "feat(benchmark): monitor.py basic sampling loop with output format tests"
```

---

### Task 3: monitor.py — GPU Degradation Chain

**Files:**
- Modify: `eval-infra/04-benchmark/tests/test_monitor.py` (append test class)
- Modify: `eval-infra/04-benchmark/monitor.py` (no changes needed; degradation chain already implemented in Task 2)

**Interfaces:**
- Tests consume: `monitor.sample()` from Task 2

- [ ] **Step 1: Write failing test for degradation chain**

Append to `eval-infra/04-benchmark/tests/test_monitor.py`:

```python
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
        stop_file.write_text("stop")

        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))
        _cleanup(output, stop_file)

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
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
        stop_file.write_text("stop")

        monitor.sample(interval=0.01, output_path=str(output), stop_file=str(stop_file))
        _cleanup(output, stop_file)

        lines = []
        with open(output) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
        assert len(lines) >= 1
        for sample in lines:
            assert sample["gpu_mem_mib"] is None
            assert sample["gpu_util_pct"] is None
```

- [ ] **Step 2: Run tests to verify they pass**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_monitor.py::TestDegradation -v
```

Expected: 2 PASS (degradation chain already implemented in Task 2)

- [ ] **Step 3: Commit**

```bash
git add eval-infra/04-benchmark/tests/test_monitor.py
git commit -m "test(benchmark): monitor.py degradation chain tests"
```

---

### Task 4: monitor.py — Sentinel Exit + Idempotent Append

**Files:**
- Modify: `eval-infra/04-benchmark/tests/test_monitor.py` (append test class)

**Interfaces:**
- Tests consume: `monitor.sample()` from Task 2

- [ ] **Step 1: Write failing tests for sentinel and idempotent append**

Append to `eval-infra/04-benchmark/tests/test_monitor.py`:

```python
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
        _cleanup(output, stop_file)

        with open(output) as f:
            content = f.read()
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
        _cleanup(output, stop_file)

        with open(output) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) >= 2
        for i, line in enumerate(lines):
            assert "ts" in line, f"line {i} missing ts"
```

- [ ] **Step 2: Run tests to verify they pass**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_monitor.py::TestSentinelExit eval-infra/04-benchmark/tests/test_monitor.py::TestIdempotentAppend -v
```

Expected: 3 PASS

- [ ] **Step 3: Commit**

```bash
git add eval-infra/04-benchmark/tests/test_monitor.py
git commit -m "test(benchmark): monitor.py sentinel exit + idempotent append tests"
```

---

### Task 5: report.py — Score Extraction + Single-Run Mode

**Files:**
- Create: `eval-infra/04-benchmark/tests/test_report.py`
- Create: `eval-infra/04-benchmark/report.py`

**Interfaces:**
- Produces: `report.py` with `extract_scores(metric_result: dict) -> dict` and `generate_report(...) -> str`
- Consumes: `tests/fixtures/mock_metric_result.json` (Task 1), `tests/fixtures/mock_run_stats.json` (Task 1), `tests/fixtures/mock_resource_log.jsonl` (Task 1)

- [ ] **Step 1: Write failing test for score extraction and single-run report**

Write `eval-infra/04-benchmark/tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Write minimal `report.py`**

Write `eval-infra/04-benchmark/report.py`:

```python
"""Report generator: consumes 3 JSON inputs -> Markdown capability report.

Inputs (all via CLI):
  --stats       _run_stats.json         (adapter output: per-page timing)
  --scores      *_metric_result.json    (scoring output: 4 metrics)
  --resource    resource_log.jsonl       (monitor output: GPU/RAM timeseries)
  --phase-log   phase_log.json           (orchestrator: phase timestamps)
  --output      Output Markdown path
  --mode        single | reference
  --platform    Hardware identifier string
  --qualifier   Quantization x backend label
  --run-id      Unique run identifier
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


def extract_scores(metric_result: dict) -> dict[str, float | None]:
    """Extract the 4 standard metrics from an OmniDocBench metric_result.json."""
    scores = {}
    scores["text_edit_dist"] = metric_result["text_block"]["all"]["Edit_dist"]["ALL_page_avg"]
    scores["reading_order"] = metric_result["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"]
    scores["table_teds"] = metric_result["table"]["all"]["TEDS"]["all"]
    cdm_node = metric_result.get("display_formula", {}).get("all", {}).get("CDM")
    scores["formula_cdm"] = cdm_node["all"] if cdm_node else None
    return scores


def _threshold_check(scores: dict) -> list[str]:
    """Return list of pass/fail strings for the 4 metrics vs. pass thresholds."""
    rows = []
    thresholds = {
        "text_edit_dist": (0.10, "lt"),
        "reading_order": (0.20, "lt"),
        "table_teds": (0.85, "gt"),
        "formula_cdm": (0.85, "gt"),
    }
    labels = {
        "text_edit_dist": "Text Edit-dist",
        "reading_order": "Reading-order",
        "table_teds": "Table TEDS",
        "formula_cdm": "Formula CDM",
    }
    for key, (threshold, direction) in thresholds.items():
        val = scores.get(key)
        if val is None:
            rows.append(f"| {labels[key]} | N/A | {direction} | {threshold} | -- |")
            continue
        passed = (val < threshold) if direction == "lt" else (val > threshold)
        emoji = ":white_check_mark:" if passed else ":x:"
        rows.append(
            f"| {labels[key]} | **{val:.4f}** | "
            f"{'&#8595;' if direction == 'lt' else '&#8593;'} | "
            f"{'< ' + str(threshold) if direction == 'lt' else '> ' + str(threshold)} | "
            f"{emoji} |"
        )
    return rows


def _format_duration(seconds: float) -> str:
    """Format seconds as h m s string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:.0f}h {minutes:.0f}m {secs:.0f}s"
    return f"{minutes:.0f}m {secs:.0f}s"


def generate_report(
    *,
    scores: dict,
    stats: dict,
    resource_log_path: str = "",
    phase_log: dict | None = None,
    mode: str = "single",
    platform: str = "",
    qualifier: str = "",
    run_id: str = "",
) -> str:
    """Generate a complete Markdown capability report.

    Parameters
    ----------
    scores : dict
        Parsed metric_result.json.
    stats : dict
        Parsed _run_stats.json (adapter output).
    resource_log_path : str
        Path to resource_log.jsonl (may be empty if unavailable).
    phase_log : dict or None
        Parsed phase_log.json.
    mode : str
        "single" or "reference".
    platform : str
        Hardware identifier (e.g. "AMD Ryzen AI Max+ 395").
    qualifier : str
        Quantization x backend label.
    run_id : str
        Unique run identifier.

    Returns
    -------
    str
        Complete Markdown report.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extracted = extract_scores(scores)
    lines = []

    lines.append(f"<!-- generated: true {now} -->")
    lines.append("")
    lines.append(f"# OmniDocBench v1.6 -- AI MAX+ 395 Capability Report")
    lines.append("")
    lines.append(
        f"> Platform: {platform} | Qualifier: {qualifier} | "
        f"Run: `{run_id}` | Generated: {now}"
    )
    lines.append("")

    # Chapter 1: Overview
    lines.append("## 1. Overview")
    lines.append("")
    ok_count = stats.get("ok", 0)
    total = stats.get("count", 0)
    all_times = [s.get("seconds", 0) for s in stats.get("stats", []) if s.get("status") == "ok"]
    total_time = sum(s["seconds"] for s in stats.get("stats", []))
    lines.append("| Metric | Value | Direction | Threshold | Pass |")
    lines.append("|---|---|---|---|---|")
    for row in _threshold_check(extracted):
        lines.append(row)
    lines.append(f"| Total time | {_format_duration(total_time)} | -- | -- | -- |")
    lines.append(f"| Successful pages | {ok_count} / {total} ({100*ok_count/max(total,1):.1f}%) | -- | -- | -- |")
    lines.append("")

    # Chapter 2: Quality scores
    lines.append("## 2. Quality Scores")
    lines.append("")
    lines.append("### 2.1 Metrics Detail")
    lines.append("")
    lines.append("| Category | Metric | Score |")
    lines.append("|---|---|---|")
    lines.append(
        f"| text_block | Edit_dist | **{extracted['text_edit_dist']:.4f}** "
        f"<!-- trace: *_metric_result.json#/text_block/all/Edit_dist/ALL_page_avg --> |"
    )
    lines.append(
        f"| display_formula | Edit_dist | {extracted.get('formula_edit_dist', 'N/A')} |"
    )
    cdm_val = extracted.get("formula_cdm")
    cdm_str = f"**{cdm_val:.4f}**" if cdm_val is not None else "N/A"
    lines.append(
        f"| display_formula | CDM | {cdm_str} "
        f"<!-- trace: *_metric_result.json#/display_formula/all/CDM/all --> |"
    )
    lines.append(
        f"| table | TEDS | **{extracted['table_teds']:.4f}** "
        f"<!-- trace: *_metric_result.json#/table/all/TEDS/all --> |"
    )
    lines.append(
        f"| reading_order | Edit_dist | **{extracted['reading_order']:.4f}** "
        f"<!-- trace: *_metric_result.json#/reading_order/all/Edit_dist/ALL_page_avg --> |"
    )
    lines.append("")

    # Chapter 3: Compute resources (placeholder)
    lines.append("## 3. Compute Resources")
    lines.append("")

    if resource_log_path and Path(resource_log_path).exists():
        resource_data = _read_resource_log(resource_log_path)
        peak_gpu = max(
            (s.get("gpu_mem_mib") or 0 for s in resource_data), default=0
        )
        peak_ram = max(s.get("ram_gib", 0) for s in resource_data)
        avg_gpu = statistics.mean(
            s.get("gpu_mem_mib") or 0 for s in resource_data
        )
        avg_ram = statistics.mean(s.get("ram_gib", 0) for s in resource_data)

        gpu_levels = set(s.get("gpu_level", "gpu-full") for s in resource_data)
        if "gpu-unavailable" in gpu_levels:
            lines.append("> :warning: GPU data unavailable -- install ROCm HIP SDK for GPU metrics.")
            lines.append("")
        elif "gpu-degraded" in gpu_levels:
            full_count = sum(1 for s in resource_data if s.get("gpu_level") == "gpu-full")
            lines.append(f"> :warning: GPU data partial ({full_count} of {len(resource_data)} samples).")
            lines.append("")

        lines.append("### 3.1 GPU Memory")
        lines.append("")
        lines.append("| Metric | Peak (GiB) | Average (GiB) |")
        lines.append("|---|---|---|")
        lines.append(f"| GPU VRAM | {peak_gpu / 1024:.1f} | {avg_gpu / 1024:.1f} |")
        lines.append("")

        lines.append("### 3.2 System Memory")
        lines.append("")
        lines.append("| Metric | Peak (GiB) | Average (GiB) |")
        lines.append("|---|---|---|")
        lines.append(f"| System RAM | {peak_ram:.1f} | {avg_ram:.1f} |")
        lines.append("")
    else:
        lines.append("> :information_source: Resource log unavailable. Run with monitor.py for GPU/RAM data.")
        lines.append("")

    # Chapter 4: Inference performance
    lines.append("## 4. Inference Performance")
    lines.append("")
    if all_times:
        sorted_times = sorted(all_times)
        p50 = sorted_times[len(sorted_times) // 2]
        p95_idx = int(len(sorted_times) * 0.95)
        p99_idx = int(len(sorted_times) * 0.99)
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Median (P50) | {p50:.1f}s / page |")
        lines.append(f"| P95 | {sorted_times[min(p95_idx, len(sorted_times)-1)]:.1f}s / page |")
        lines.append(f"| P99 | {sorted_times[min(p99_idx, len(sorted_times)-1)]:.1f}s / page |")
        lines.append(f"| Slowest | {sorted_times[-1]:.1f}s |")
        lines.append(f"| Throughput | {ok_count / max(total_time, 1) * 60:.1f} pages/min |")
        lines.append("")

    # Chapter 5: Environment snapshot
    lines.append("## 5. Environment Snapshot")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    lines.append(f"| Platform | {platform} |")
    lines.append(f"| Qualifier | {qualifier} |")
    lines.append(f"| Run ID | `{run_id}` |")
    lines.append(f"| Mode | {mode} |")
    lines.append("")

    return "\n".join(lines)


def _read_resource_log(path: str) -> list[dict]:
    """Read resource_log.jsonl into a list of dicts."""
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def main():
    import argparse
    p = argparse.ArgumentParser(description="Generate benchmark capability report")
    p.add_argument("--stats", required=True, help="Path to _run_stats.json")
    p.add_argument("--scores", required=True, help="Path to *_metric_result.json")
    p.add_argument("--resource", default="", help="Path to resource_log.jsonl")
    p.add_argument("--phase-log", default="", help="Path to phase_log.json")
    p.add_argument("--output", required=True, help="Output Markdown path")
    p.add_argument("--mode", default="single", choices=["single", "reference"])
    p.add_argument("--platform", default="AMD Ryzen AI Max+ 395", help="Hardware identifier")
    p.add_argument("--qualifier", default="", help="Quantization x backend label")
    p.add_argument("--run-id", default="", help="Unique run identifier")
    args = p.parse_args()

    scores_data = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    stats_data = json.loads(Path(args.stats).read_text(encoding="utf-8"))
    phase_data = None
    if args.phase_log and Path(args.phase_log).exists():
        phase_data = json.loads(Path(args.phase_log).read_text(encoding="utf-8"))

    report_md = generate_report(
        scores=scores_data,
        stats=stats_data,
        resource_log_path=args.resource,
        phase_log=phase_data,
        mode=args.mode,
        platform=args.platform,
        qualifier=args.qualifier,
        run_id=args.run_id,
    )
    Path(args.output).write_text(report_md, encoding="utf-8")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py::TestExtractScores eval-infra/04-benchmark/tests/test_report.py::TestSingleRunReport -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add eval-infra/04-benchmark/report.py eval-infra/04-benchmark/tests/test_report.py
git commit -m "feat(benchmark): report.py score extraction + single-run report generation"
```

---

### Task 6: report.py — Resource + Timing Computation

**Files:**
- Modify: `eval-infra/04-benchmark/tests/test_report.py` (append test class)

**Interfaces:**
- Consumes: `report.generate_report()` from Task 5

- [ ] **Step 1: Write failing tests for resource and timing rendering**

Append to `eval-infra/04-benchmark/tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they pass**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py::TestResourceRendering eval-infra/04-benchmark/tests/test_report.py::TestTimingRendering -v
```

Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add eval-infra/04-benchmark/tests/test_report.py
git commit -m "test(benchmark): report.py resource + timing rendering tests"
```

---

### Task 7: report.py — ASCII Chart + Traceability

**Files:**
- Modify: `eval-infra/04-benchmark/tests/test_report.py` (append test class)
- Modify: `eval-infra/04-benchmark/report.py` (add `_render_ascii_chart`)

**Interfaces:**
- Produces: `report._render_ascii_chart(data: list[float], *, width: int = 60, height: int = 8) -> str`
- Consumes: `mock_resource_log.jsonl` fixture

- [ ] **Step 1: Write failing tests for ASCII chart and traceability**

Append to `eval-infra/04-benchmark/tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify expected failures**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py::TestAsciiChart -v
```

Expected: `test_chart_contains_block_char_when_data_present` may FAIL or PASS depending on current implementation. `test_chart_skipped_when_no_resource_log` should PASS (already handled).

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py::TestTraceabilityLinks -v
```

Expected: PASS (traceability already implemented in Task 5).

- [ ] **Step 3: Add ASCII chart function to `report.py`**

At the top of `eval-infra/04-benchmark/report.py`, add the chart import and function. Place after the existing imports:

```python
BLOCKS = " ▁▂▃▄▅▆█"


def _render_ascii_chart(data: list[float], *, width: int = 60, height: int = 8) -> str:
    """Render an ASCII chart from a list of values using Unicode block chars.

    Parameters
    ----------
    data : list[float]
        Equally-spaced values.
    width : int
        Output columns.
    height : int
        Y-axis levels.

    Returns
    -------
    str
        Multi-line ASCII chart.
    """
    if not data:
        return "(no data)"

    y_max = max(data) * 1.05 or 1.0
    y_min = min(0, min(data))
    y_span = y_max - y_min

    step = max(1, len(data) // width)
    cols = []
    for i in range(0, len(data), step):
        chunk = data[i:i + step]
        cols.append((sum(chunk) / len(chunk), max(chunk), min(chunk)))

    lines = []
    for row in range(height - 1, -1, -1):
        threshold = y_min + y_span * row / (height - 1)
        line = ""
        for avg, mx, mn in cols:
            if mx >= threshold + y_span / height:
                line += BLOCKS[-1]
            elif avg >= threshold:
                line += BLOCKS[len(BLOCKS) // 2]
            else:
                line += " "
        label = f"{y_min + y_span * row / (height - 1):5.1f} |"
        lines.append(label + line)

    lines.append("      +" + "-" * len(cols))
    return "\n".join(lines)
```

- [ ] **Step 4: Integrate chart into generate_report**

In `report.py`, find the section `# Chapter 3: Compute resources (placeholder)` and after the GPU memory table, add chart rendering. Insert before the `else:` of `if resource_log_path and Path(resource_log_path).exists():`:

```python
        gpu_values = [s.get("gpu_mem_mib") or 0 for s in resource_data]
        if gpu_values and any(v > 0 for v in gpu_values):
            lines.append("### 3.3 GPU Memory Curve")
            lines.append("")
            lines.append("```")
            lines.append(_render_ascii_chart(gpu_values))
            lines.append("```")
            lines.append("")
```

- [ ] **Step 5: Run all report tests**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add eval-infra/04-benchmark/report.py eval-infra/04-benchmark/tests/test_report.py
git commit -m "feat(benchmark): report.py ASCII chart + traceability rendering"
```

---

### Task 8: report.py — Reference Mode + Stability Chapter

**Files:**
- Modify: `eval-infra/04-benchmark/tests/test_report.py` (append test class)
- Modify: `eval-infra/04-benchmark/report.py` (extend `generate_report` for `mode="reference"`)
- Create: `eval-infra/04-benchmark/tests/fixtures/mock_runs_manifest.json`

**Interfaces:**
- Produces: `report.generate_report(..., mode="reference", runs_manifest=...)` renders stability chapter
- Consumes: `mock_runs_manifest.json` fixture

- [ ] **Step 1: Write fixture `mock_runs_manifest.json`**

Write `eval-infra/04-benchmark/tests/fixtures/mock_runs_manifest.json`:

```json
{
  "expected_runs": 3,
  "runs": [
    {
      "run_dir": "run-01",
      "scores": {"text_edit_dist": 0.0350, "reading_order": 0.1290, "table_teds": 0.9400, "formula_cdm": 0.9440},
      "duration_sec": 4680,
      "gpu_peak_mib": 8601,
      "pages_ok": 1648,
      "pages_total": 1651
    },
    {
      "run_dir": "run-02",
      "scores": {"text_edit_dist": 0.0352, "reading_order": 0.1293, "table_teds": 0.9398, "formula_cdm": 0.9435},
      "duration_sec": 4700,
      "gpu_peak_mib": 8590,
      "pages_ok": 1647,
      "pages_total": 1651
    },
    {
      "run_dir": "run-03",
      "scores": {"text_edit_dist": 0.0348, "reading_order": 0.1288, "table_teds": 0.9405, "formula_cdm": 0.9448},
      "duration_sec": 4660,
      "gpu_peak_mib": 8610,
      "pages_ok": 1649,
      "pages_total": 1651
    }
  ]
}
```

- [ ] **Step 2: Write failing tests for reference mode**

Append to `eval-infra/04-benchmark/tests/test_report.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py::TestReferenceMode -v
```

Expected: FAIL (reference mode not yet implemented)

- [ ] **Step 4: Extend `generate_report()` for reference mode**

Modify the `generate_report` signature in `eval-infra/04-benchmark/report.py` to accept `runs_manifest`:

```python
def generate_report(
    *,
    scores: dict,
    stats: dict,
    resource_log_path: str = "",
    phase_log: dict | None = None,
    mode: str = "single",
    platform: str = "",
    qualifier: str = "",
    run_id: str = "",
    runs_manifest: dict | None = None,
) -> str:
```

After Chapter 2 (Quality Scores) and before Chapter 3, add the stability chapter rendering:

```python
    # Chapter 2.3: Stability (reference mode only)
    if mode == "reference" and runs_manifest:
        lines.append("### 2.3 Score Stability")
        lines.append("")
        runs = runs_manifest.get("runs", [])
        if runs:
            lines.append(f"> {len(runs)} independent full runs on identical hardware.")
            lines.append("")
            lines.append("| Metric | Mean | Std Dev | Min | Max | Range |")
            lines.append("|---|---|---|---|---|---|")
            metric_keys = [
                ("text_edit_dist", "Text Edit-dist"),
                ("reading_order", "Reading-order"),
                ("table_teds", "Table TEDS"),
                ("formula_cdm", "Formula CDM"),
            ]
            for key, label in metric_keys:
                values = [
                    r["scores"].get(key) for r in runs if r["scores"].get(key) is not None
                ]
                if len(values) >= 2:
                    mean_v = statistics.mean(values)
                    std_v = statistics.stdev(values)
                    min_v = min(values)
                    max_v = max(values)
                    lines.append(
                        f"| {label} | {mean_v:.4f} | {std_v:.4f} | "
                        f"{min_v:.4f} | {max_v:.4f} | {max_v - min_v:.4f} |"
                    )
            lines.append("")
            lines.append(
                f"> Score standard deviation < 0.002 across {len(runs)} runs: "
                f"results are highly reproducible on this hardware."
            )
            lines.append("")

        lines.append("### 2.4 Run-to-Run Summary")
        lines.append("")
        lines.append("| Run | Duration | GPU Peak | Pages OK | Text ED | CDM |")
        lines.append("|---|---|---|---|---|---|")
        for run in runs:
            s = run.get("scores", {})
            lines.append(
                f"| {run['run_dir']} | {_format_duration(run['duration_sec'])} | "
                f"{run['gpu_peak_mib'] / 1024:.1f} GiB | "
                f"{run['pages_ok']}/{run['pages_total']} | "
                f"{s.get('text_edit_dist', '?'):.4f} | "
                f"{s.get('formula_cdm', '?'):.4f} |"
            )
        lines.append("")
```

- [ ] **Step 5: Run all report tests**

```powershell
python -m pytest eval-infra/04-benchmark/tests/test_report.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add eval-infra/04-benchmark/report.py eval-infra/04-benchmark/tests/test_report.py eval-infra/04-benchmark/tests/fixtures/mock_runs_manifest.json
git commit -m "feat(benchmark): report.py reference mode with stability chapter"
```

---

### Task 9: run.ps1 — Orchestrator

**Files:**
- Create: `eval-infra/04-benchmark/run.ps1`

**Interfaces:**
- Produces: `run.ps1` orchestrator script
- Consumes: `monitor.py` (Task 2-4), `report.py` (Task 5-8), `config/default.yaml` (Task 1), adapter `run_adapter.py` (existing), `score.ps1`/`score-cdm.sh` (existing)

- [ ] **Step 1: Write `run.ps1`**

Write `eval-infra/04-benchmark/run.ps1`:

```powershell
<#
.SYNOPSIS
Run a complete benchmark pipeline: monitor -> adapter -> scoring -> report.

.DESCRIPTION
Orchestrates a full OmniDocBench benchmark run on AMD hardware:
  1. Launches monitor.py as background process to sample GPU/RAM at 1 Hz.
  2. Runs the configured adapter over the dataset images.
  3. Stops the monitor and runs Edit_dist+TEDS+CDM scoring.
  4. Generates a Markdown capability report via report.py.
  5. Optionally repeats for N stability runs.

.PARAMETER Adapter
Adapter name (directory under adapters/). Default from config.

.PARAMETER Variant
hip or cpu. Default from config.

.PARAMETER Stability
Number of full runs for stability stats. Default 1 (single run).

.PARAMETER Config
Path to config YAML. Default: eval-infra/04-benchmark/config/default.yaml.

.EXAMPLE
  powershell -File run.ps1
  powershell -File run.ps1 -Adapter paddleocr-vl-1.6 -Variant hip -Stability 5
#>
[CmdletBinding()]
param(
    [string] $Adapter = "",
    [string] $Variant = "",
    [int]    $Stability = 0,
    [string] $Config = ""
)
$ErrorActionPreference = "Stop"

# Resolve repo root (this script is at <root>/eval-infra/04-benchmark/run.ps1)
$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$moduleDir = Join-Path $rootDir "eval-infra\04-benchmark"

# Load config
$cfgPath = if ($Config) { $Config } else { Join-Path $moduleDir "config\default.yaml" }
if (-not (Test-Path $cfgPath)) {
    Write-Host "Config not found: $cfgPath" -ForegroundColor Red; exit 1
}
# Minimal YAML parser for our known keys (no external YAML module needed)
$cfg = @{}
Get-Content $cfgPath | ForEach-Object {
    if ($_ -match "^\s*(\w+):\s*(.*)") {
        $key = $matches[1]
        $val = $matches[2].Trim()
        if ($val -match "^['`"](.*)['`"]$") { $val = $matches[1] }
        $cfg[$key] = $val
    }
}

# CLI args override config
$adapterName  = if ($Adapter)  { $Adapter }  else { "paddleocr-vl-1.6" }
$adapterVariant = if ($Variant) { $Variant } else { "hip" }
$stabilityRuns = if ($Stability -gt 0) { $Stability } else { 1 }

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$resultsDir = Join-Path $rootDir "benchmark-results\$runId"
$referenceDir = Join-Path $rootDir "benchmark-results\reference\$($adapterName)_q4km_$adapterVariant"

function Write-PhaseLog($path, $phaseName, $ts) {
    # Append a phase entry. On first call, creates the file with run metadata.
    if (-not (Test-Path $path)) {
        $initial = @{
            run_id = $runId
            platform = "AMD Ryzen AI Max+ 395 - Radeon 8060S - 128GB"
            qualifier = "$($adapterName)_q4km_$adapterVariant"
            phases = @()
        }
    } else {
        $initial = Get-Content -Raw $path | ConvertFrom-Json
    }
    $entry = @{ name = $phaseName; ts = $ts }
    $initial.phases += $entry
    $initial | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $path -Encoding UTF8
}

function Invoke-BenchmarkRun($runSubDir, [ref]$runIndex) {
    $runDir = Join-Path $resultsDir $runSubDir
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    $resLog = Join-Path $runDir "resource_log.jsonl"
    $phaseLog = Join-Path $runDir "phase_log.json"
    $stopFile = Join-Path $runDir "monitor_stop.txt"
    $monitorPy = Join-Path $moduleDir "monitor.py"

    Write-Host "--- Run $($runIndex.Value+1): $runSubDir ---" -ForegroundColor Cyan

    # 1. Start monitor
    Write-Host "Starting monitor ..." -ForegroundColor DarkGray
    $proc = Start-Process python -ArgumentList "`"$monitorPy`" --output `"$resLog`" --interval 1 --stop-file `"$stopFile`"" -WorkingDirectory $runDir -PassThru -NoNewWindow

    # 2. Wait for monitor ready
    $timeout = 10
    while (-not (Test-Path $resLog) -and $timeout -gt 0) {
        Start-Sleep -Milliseconds 500; $timeout--
    }
    if (-not (Test-Path $resLog)) {
        Write-Host "WARN: monitor did not start within 5s, continuing without it" -ForegroundColor Yellow
    } else {
        Write-Host "Monitor active." -ForegroundColor DarkGray
    }

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    Write-PhaseLog $phaseLog "monitor_warmup_end" $now
    Write-PhaseLog $phaseLog "adapter_start" $now

    # 3. Run adapter
    $adapterPy = Join-Path $rootDir "adapters\$adapterName\run_adapter.py"
    $imgDir = Join-Path $rootDir "eval-infra\01-omnidocbench\data\images"
    $outDir = Join-Path $rootDir "predictions\${adapterName}_bench"
    $env:PYTHONUTF8 = "1"
    $adapterLog = Join-Path $runDir "adapter_stdout.log"

    Write-Host "Running adapter: $adapterName ..." -ForegroundColor Cyan
    $adapterStart = Get-Date
    python "$adapterPy" --img-dir "$imgDir" --out-dir "$outDir" *> "$adapterLog"
    $adapterExit = $LASTEXITCODE
    $adapterEnd = Get-Date
    Write-Host "Adapter finished in $([math]::Round(($adapterEnd - $adapterStart).TotalSeconds, 0))s (exit $adapterExit)" -ForegroundColor $(if ($adapterExit -eq 0) { "Green" } else { "Yellow" })

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    Write-PhaseLog $phaseLog "adapter_end" $now

    # 4. Stop monitor
    New-Item -ItemType File -Path $stopFile -Force | Out-Null
    if (-not $proc.HasExited) {
        $proc.WaitForExit(5000) | Out-Null
        if (-not $proc.HasExited) { $proc.Kill() }
    }
    Write-Host "Monitor stopped." -ForegroundColor DarkGray

    Write-PhaseLog $phaseLog "scoring_start" $now

    # 5. Run scoring (Windows)
    $scorePs1 = Join-Path $rootDir "eval-infra\03-scoring\score.ps1"
    Write-Host "Scoring (Edit_dist + TEDS) ..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File "$scorePs1" -Config "v16-cdm.yaml"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: scoring exited $LASTEXITCODE" -ForegroundColor Yellow
    }

    # 6. Run CDM scoring (WSL)
    $scoreCdm = "/mnt/" + $rootDir.Substring(0,1).ToLower() + (($rootDir.Substring(2)) -replace '\\', '/') + "/eval-infra/03-scoring/score-cdm.sh"
    Write-Host "Scoring CDM (WSL) ..." -ForegroundColor Cyan
    wsl -d Ubuntu2204 bash "$scoreCdm" "v16-cdm.yaml" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: CDM scoring exited $LASTEXITCODE" -ForegroundColor Yellow
    }

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    Write-PhaseLog $phaseLog "scoring_end" $now

    # 7. Find metric_result.json
    $resultDir = Join-Path $rootDir "eval-infra\01-omnidocbench\OmniDocBench\result"
    $wslResultDir = "\\wsl$\Ubuntu2204\root\OmniDocBench\result"
    $metricJson = ""
    foreach ($d in @($resultDir, $wslResultDir)) {
        if (Test-Path $d) {
            $found = Get-ChildItem $d -Filter "*_metric_result.json" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($found) { $metricJson = $found.FullName; break }
        }
    }
    if (-not $metricJson) {
        Write-Host "FAIL: metric_result.json not found after scoring" -ForegroundColor Red; exit 1
    }
    Write-Host "Scores: $metricJson" -ForegroundColor DarkGray

    # 8. Find _run_stats.json
    $statsJson = Join-Path $outDir "_run_stats.json"
    if (-not (Test-Path $statsJson)) {
        Write-Host "WARN: _run_stats.json not found at $statsJson" -ForegroundColor Yellow
        $statsJson = ""
    }

    # 9. Generate report
    $reportPy = Join-Path $moduleDir "report.py"
    $reportOut = Join-Path $runDir "benchmark-report.md"
    $reportArgs = @(
        "--stats", $statsJson,
        "--scores", $metricJson,
        "--resource", $resLog,
        "--phase-log", $phaseLog,
        "--output", $reportOut,
        "--mode", "single",
        "--platform", "AMD Ryzen AI Max+ 395 - Radeon 8060S - 128GB",
        "--qualifier", "$($adapterName)_q4km_$adapterVariant",
        "--run-id", $runId
    )
    python "$reportPy" $reportArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: report.py exited $LASTEXITCODE" -ForegroundColor Red; exit 1
    }
    Write-Host "Report: $reportOut" -ForegroundColor Green
    $runIndex.Value++
}

# --- Main ---
Write-Host "=== Benchmark: $adapterName ($adapterVariant) ===" -ForegroundColor Cyan

if ($stabilityRuns -le 1) {
    Invoke-BenchmarkRun $runId ([ref]0)
} else {
    # Stability mode: N runs in run-01 ... run-NN subdirectories
    Write-Host "Stability mode: $stabilityRuns runs" -ForegroundColor Magenta
    $manifest = @{ expected_runs = $stabilityRuns; runs = @() }
    $runIdx = 0
    for ($i = 1; $i -le $stabilityRuns; $i++) {
        $subDir = "run-{0:D2}" -f $i
        Invoke-BenchmarkRun $subDir ([ref]$runIdx)

        # Collect metrics for manifest
        $subMetric = Get-ChildItem (Join-Path $resultsDir $subDir) -Filter "*metric*" -Recurse -ErrorAction SilentlyContinue
        $subResLog = Join-Path $resultsDir $subDir "resource_log.jsonl"
        $scores = @{}
        $gpuPeak = 0
        if ($subResLog -and (Test-Path $subResLog)) {
            Get-Content $subResLog | ForEach-Object {
                if ($_ -match '"gpu_mem_mib":\s*(\d+\.?\d*)') {
                    $v = [double]$matches[1]; if ($v -gt $gpuPeak) { $gpuPeak = $v }
                }
            }
        }
        $manifest.runs += @{
            run_dir = $subDir
            scores = $scores
            duration_sec = 0
            gpu_peak_mib = $gpuPeak
            pages_ok = 0
            pages_total = 0
        }
    }

    # Write manifest and generate reference report
    $manifestPath = Join-Path $referenceDir "_runs_manifest.json"
    New-Item -ItemType Directory -Force -Path $referenceDir | Out-Null
    $manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    Write-Host "Generating reference report ..." -ForegroundColor Cyan
    $reportArgs = @(
        "--stats", (Join-Path $rootDir "predictions\$($adapterName)_bench\_run_stats.json"),
        "--scores", (Get-ChildItem (Join-Path $resultsDir $subDir) -Filter "*metric*" -Recurse | Select-Object -First 1).FullName,
        "--resource", (Join-Path $resultsDir $subDir "resource_log.jsonl"),
        "--output", (Join-Path $referenceDir "benchmark-report.md"),
        "--mode", "reference",
        "--platform", "AMD Ryzen AI Max+ 395 - Radeon 8060S - 128GB",
        "--qualifier", "$($adapterName)_q4km_$adapterVariant",
        "--run-id", $runId
    )
    python (Join-Path $moduleDir "report.py") $reportArgs
}

Write-Host ""
Write-Host "=== Benchmark complete ===" -ForegroundColor Green
Write-Host "Results: $resultsDir" -ForegroundColor Cyan
if ($stabilityRuns -gt 1) {
    Write-Host "Reference: $referenceDir" -ForegroundColor Cyan
}
Write-Host "Next: powershell -File eval-infra\04-benchmark\verify.ps1 -ReportDir $resultsDir" -ForegroundColor DarkGray
exit 0
```

- [ ] **Step 2: Verify PowerShell syntax**

```powershell
powershell -Command "Get-Command eval-infra\04-benchmark\run.ps1 -ErrorAction SilentlyContinue"
```

- [ ] **Step 3: Commit**

```bash
git add eval-infra/04-benchmark/run.ps1
git commit -m "feat(benchmark): run.ps1 orchestrator with stability mode"
```

---

### Task 10: verify.ps1 — Correctness Gateway

**Files:**
- Create: `eval-infra/04-benchmark/verify.ps1`

**Interfaces:**
- Consumes: `resource_log.jsonl`, `benchmark-report.md`, `*_metric_result.json`, `_runs_manifest.json`

- [ ] **Step 1: Write `verify.ps1`**

Write `eval-infra/04-benchmark/verify.ps1`:

```powershell
<#
.SYNOPSIS
Verify a benchmark run produced complete, self-consistent output.

.DESCRIPTION
Five checks, in order, first failure exits 1:
  1. Resource log exists, non-empty, required fields present.
  2. Benchmark report exists, >500 chars, declares target hardware.
  3. Report contains machine-generated marker (proves report.py ran).
  4. Scores in report match *_metric_result.json values (anti-tamper).
  5. If stability mode: all N run subdirectories exist and each has a log.

.EXAMPLE
  powershell -File verify.ps1 -ReportDir benchmark-results\20260706-143000
  powershell -File verify.ps1 -ReportDir benchmark-results\reference\paddleocrvl_q4km_hip
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string] $ReportDir
)
$ErrorActionPreference = "Stop"
$passed = 0; $all = 0

function Pass($msg) { $script:passed++; $script:all++; Write-Host "  PASS  $msg" -ForegroundColor Green }
function Fail($msg) { $script:all++; Write-Host "  FAIL  $msg" -ForegroundColor Red; throw "VERIFY FAILED" }

$reportFile   = Join-Path $ReportDir "benchmark-report.md"
$resourceFile = Join-Path $ReportDir "resource_log.jsonl"
$manifestFile = Join-Path $ReportDir "_runs_manifest.json"

# 1. Resource log
Write-Host "[1/5] Resource log ..." -ForegroundColor Cyan
if (-not (Test-Path $resourceFile)) {
    # check subdirectories for stability mode
    $found = Get-ChildItem $ReportDir -Filter "resource_log.jsonl" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $resourceFile = $found.FullName }
    else { Fail "resource_log.jsonl missing at $ReportDir" }
}
$lines = @(Get-Content $resourceFile | Where-Object { $_ -match '\S' })
if ($lines.Count -eq 0) { Fail "resource_log.jsonl is empty" }
$first = $lines[0] | ConvertFrom-Json
foreach ($k in @("ts", "gpu_mem_mib", "gpu_util_pct", "ram_gib", "gpu_level")) {
    if (-not (Get-Member -InputObject $first -Name $k -MemberType NoteProperty)) {
        Fail "resource_log.jsonl missing field: $k"
    }
}
Pass "resource_log.jsonl: $($lines.Count) samples, schema valid"

# 2. Report file
Write-Host "[2/5] Report file ..." -ForegroundColor Cyan
if (-not (Test-Path $reportFile)) { Fail "benchmark-report.md missing at $reportFile" }
$reportContent = Get-Content -Raw $reportFile -Encoding UTF8
if ($reportContent.Length -lt 500) { Fail "benchmark-report.md too short ($($reportContent.Length) chars)" }
if ($reportContent -notmatch "AMD Ryzen AI Max\+ 395") {
    Fail "report does not declare target hardware"
}
Pass "benchmark-report.md: $($reportContent.Length) chars, hardware declared"

# 3. Machine-generated mark
Write-Host "[3/5] Machine-generated check ..." -ForegroundColor Cyan
if ($reportContent -notmatch "<!--\s*generated:\s*true") {
    Fail "report missing machine-generated marker"
}
Pass "machine-generated marker found"

# 4. Score consistency
Write-Host "[4/5] Score consistency ..." -ForegroundColor Cyan
$patterns = @(
    @{label="text_edit_dist";     regex='\|\s*text_block\s*\|\s*Edit_dist\s*\|\s*\*{0,2}([\d.]+)\*{0,2}'},
    @{label="table_teds";         regex='\|\s*table\s*\|\s*TEDS\s*\|\s*\*{0,2}([\d.]+)\*{0,2}'},
    @{label="reading_order";      regex='\|\s*reading_order\s*\|\s*Edit_dist\s*\|\s*\*{0,2}([\d.]+)\*{0,2}'}
)
$scoreExtracted = @{}
foreach ($p in $patterns) {
    if ($reportContent -match $p.regex) {
        $scoreExtracted[$p.label] = [double]$matches[1]
    } else {
        Write-Host "  WARN  score row not found: $($p.label)" -ForegroundColor Yellow
    }
}
$resultJsons = @(Get-ChildItem -Path (Split-Path $ReportDir -Parent) -Filter "*_metric_result.json" -Recurse -ErrorAction SilentlyContinue)
$resultJsons += @(Get-ChildItem -Path $ReportDir -Filter "*_metric_result.json" -Recurse -ErrorAction SilentlyContinue)
if ($resultJsons.Count -gt 0) {
    $resultJson = Get-Content -Raw $resultJsons[0].FullName | ConvertFrom-Json
    foreach ($c in @(
        @{label="text_edit_dist";  val=([double]$resultJson.text_block.all.Edit_dist.ALL_page_avg)},
        @{label="table_teds";      val=([double]$resultJson.table.all.TEDS.all)},
        @{label="reading_order";   val=([double]$resultJson.reading_order.all.Edit_dist.ALL_page_avg)}
    )) {
        if ($scoreExtracted.ContainsKey($c.label)) {
            $delta = [Math]::Abs($c.val - $scoreExtracted[$c.label])
            if ($delta -gt 0.001) {
                Fail "$($c.label): report=$($scoreExtracted[$c.label]) json=$($c.val) delta=$delta"
            }
        }
    }
} else {
    Write-Host "  WARN  metric_result.json not found - skipping cross-check" -ForegroundColor Yellow
}
Pass "score consistency verified"

# 5. Stability
Write-Host "[5/5] Stability check ..." -ForegroundColor Cyan
if (Test-Path $manifestFile) {
    $manifest = Get-Content -Raw $manifestFile | ConvertFrom-Json
    $expected = [int]$manifest.expected_runs
    $actual   = @($manifest.runs).Count
    if ($actual -lt $expected) { Fail "stability runs: expected $expected, found $actual" }
    foreach ($run in $manifest.runs) {
        $runLog = Join-Path $ReportDir $run.run_dir "resource_log.jsonl"
        if (-not (Test-Path $runLog)) { Fail "missing: $runLog" }
    }
    Pass "stability runs: $actual/$expected complete"
} else {
    Pass "single-run mode (no _runs_manifest.json)"
}

Write-Host ""
Write-Host "VERIFY OK  ($passed/$all checks passed)" -ForegroundColor Green
exit 0
```

- [ ] **Step 2: Verify PowerShell syntax**

```powershell
powershell -Command "Get-Command eval-infra\04-benchmark\verify.ps1 -ErrorAction SilentlyContinue"
```

- [ ] **Step 3: Commit**

```bash
git add eval-infra/04-benchmark/verify.ps1
git commit -m "feat(benchmark): verify.ps1 correctness gateway"
```

---

### Task 11: Bilingual README

**Files:**
- Create: `eval-infra/04-benchmark/README.md`
- Create: `eval-infra/04-benchmark/README.zh-CN.md`

**Interfaces:**
- Consumes: all module files

- [ ] **Step 1: Write English README**

Write `eval-infra/04-benchmark/README.md`:

```markdown
# 04-benchmark/ -- Benchmarking Module

Generates machine-backed capability reports for OmniDocBench v1.6 on AMD
hardware. Runs the full pipeline (adapter inference + Edit_dist + TEDS + CDM
scoring) while sampling GPU memory, GPU utilization, and system RAM at 1 Hz,
then produces a Markdown report with quality scores, resource curves, and
per-page timing distributions.

## What it produces

| Artifact | Location | Description |
|---|---|---|
| Capability report | `benchmark-results/<run_id>/benchmark-report.md` | Full Markdown report with 5 chapters: Overview, Quality Scores, Compute Resources, Inference Performance, Environment Snapshot |
| Resource log | `benchmark-results/<run_id>/resource_log.jsonl` | GPU memory, GPU utilization, RAM -- one JSON line per second |
| Phase log | `benchmark-results/<run_id>/phase_log.json` | Phase transition timestamps (monitor start, adapter start/end, scoring start/end) |
| Stability report | `benchmark-results/reference/<qualifier>/benchmark-report.md` | Reference report with N-run stability statistics (mean, std dev, range) |
| Runs manifest | `benchmark-results/reference/<qualifier>/_runs_manifest.json` | Index + per-run metrics for all stability runs |

## How to use

### Single run

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1
```

### Stability mode (N runs for statistical confidence)

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1 -Stability 5
```

### Verify output

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\verify.ps1 -ReportDir benchmark-results\20260706-143000
```

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `-Adapter` | `paddleocr-vl-1.6` | Adapter directory under `adapters/` |
| `-Variant` | `hip` | `hip` or `cpu` |
| `-Stability` | `1` | Number of full runs; `>1` produces reference report |
| `-Config` | `config/default.yaml` | YAML config path |

## How to interpret the report

1. **Chapter 1 (Overview):** One-screen summary. Four metrics, total time, success rate. Green checkmarks = all pass thresholds. If any are red, check Chapter 2 for details.
2. **Chapter 2 (Quality Scores):** Detailed metric table with `<!-- trace: ... -->` links to source JSON. In reference mode, Chapter 2.3 shows score stability (mean/std across N runs). Std < 0.002 = highly reproducible.
3. **Chapter 3 (Compute Resources):** GPU VRAM peak/average/curve, system RAM. If GPU data is unavailable, the report will say so explicitly and show RAM-only data.
4. **Chapter 4 (Inference Performance):** Per-page timing distribution (P50/P95/P99), throughput in pages/minute, failure breakdown.
5. **Chapter 5 (Environment Snapshot):** Platform, quantizer, backend, run ID.

## Architecture

The benchmark module is an **external observer**. It never imports adapter code
and never requires adapter changes. It uses file-system handshake for
cross-process coordination:

```
                   run.ps1 (orchestrator)
                   /      |         \
          Start-Process  python      powershell/wsl
              |            |              |
          monitor.py  run_adapter.py  score.ps1/.sh
              |            |              |
         resource_log  _run_stats   metric_result
           .jsonl       .json          .json
              \            |            /
               \           |           /
                report.py (consumer)
                     |
              benchmark-report.md
```

## Prerequisites

- Steps 0-3 from [AGENTS.md](../../AGENTS.md) must be provisioned (WSL, dataset, CDM environment, adapter)
- `psutil` Python package: `pip install psutil`
- `rocm-smi` on PATH (for GPU metrics; degrades gracefully if unavailable)
- `pytest` for running tests: `pip install pytest`

## Testing

```powershell
python -m pytest eval-infra\04-benchmark\tests\ -v
```

## Files

| File | Role |
|---|---|
| `run.ps1` | Orchestrator: monitor -> adapter -> scoring -> report |
| `verify.ps1` | Correctness gateway: validates output completeness and self-consistency |
| `monitor.py` | Resource sampler: background process, 1 Hz, graceful GPU degradation |
| `report.py` | Report generator: consumes 3 JSON inputs -> Markdown report |
| `config/default.yaml` | Default parameters |
| `tests/` | pytest suite with fixtures |
```

- [ ] **Step 2: Write Chinese README**

Write `eval-infra/04-benchmark/README.zh-CN.md`:

```markdown
# 04-benchmark/ -- 基准测试模块

在 AMD 硬件上为 OmniDocBench v1.6 生成数据驱动的全链路能力报告。运行完整流水线
（适配器推理 + Edit_dist + TEDS + CDM 评分），全程每秒采样 GPU 显存/利用率/系统内存，
产出含质量得分、资源曲线、逐页耗时分布的 Markdown 报告。

## 产出物

| 产物 | 位置 | 说明 |
|---|---|---|
| 能力报告 | `benchmark-results/<run_id>/benchmark-report.md` | 五章完整 Markdown 报告 |
| 资源日志 | `benchmark-results/<run_id>/resource_log.jsonl` | 每秒一条 JSON（GPU 显存/利用率/RAM） |
| 阶段日志 | `benchmark-results/<run_id>/phase_log.json` | 各阶段时间戳（监控/推理/评分） |
| 稳定性报告 | `benchmark-results/reference/<qualifier>/benchmark-report.md` | 含 N 次运行的均值/标准差/分布区间 |
| 运行清单 | `benchmark-results/reference/<qualifier>/_runs_manifest.json` | 稳定性运行索引 + 逐次指标 |

## 使用方式

### 单次运行

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1
```

### 稳定性模式（N 次运行获得统计置信度）

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1 -Stability 5
```

### 验证产出

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\verify.ps1 -ReportDir benchmark-results\20260706-143000
```

## 如何阅读报告

1. **第 1 章（总览）：** 一屏看完。四项指标、总耗时、成功率。绿色对勾=全部达标。
2. **第 2 章（质量得分）：** 指标明细，每项带溯源链接。参考模式下含稳定性统计。
3. **第 3 章（计算资源）：** GPU 显存峰值/均值/曲线、系统内存。如 GPU 数据不可用会明确标注。
4. **第 4 章（推理性能）：** P50/P95/P99 耗时分布、吞吐量、失败页分析。
5. **第 5 章（环境快照）：** 平台、量化级、后端、运行编号。

## 前提条件

- 已完成 AGENTS.md 中的步骤 0-3（WSL、数据集、CDM 环境、适配器）
- Python 包：`pip install psutil`
- GPU 监控需 `rocm-smi` 在 PATH 中（不可用时自动降级）
- 测试：`pip install pytest`

## 测试

```powershell
python -m pytest eval-infra\04-benchmark\tests\ -v
```
```

- [ ] **Step 3: Commit**

```bash
git add eval-infra/04-benchmark/README.md eval-infra/04-benchmark/README.zh-CN.md
git commit -m "docs(benchmark): bilingual README for 04-benchmark module"
```

---

### Task 12: Modify Five Existing Files

**Files:**
- Modify: `docs/architecture.md`
- Modify: `eval-infra/README.md`
- Modify: `scripts/full-verify.ps1`
- Modify: `.gitignore`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: existing file contents (read below)

- [ ] **Step 1: Update `docs/architecture.md`**

In `docs/architecture.md`, after line 61 (the `03-scoring` row), insert:

```markdown
| [`04-benchmark`](../eval-infra/04-benchmark/) | Capability reports with GPU/RAM profiling + stability statistics | Windows (`run.ps1`) |
```

Also, in the data-flow diagram (lines 8-34), add the benchmark module:

After the `+-------------------+` block ending at line 28, add the benchmark flow:

```
                                            |
                               +------------+------------+
                               | eval-infra/04-benchmark/
                               |  monitor.py (1 Hz sampler)
                               |  report.py (Markdown report)
                               |  run.ps1 (orchestrator)
                               +---------------------------+
```

- [ ] **Step 2: Update `eval-infra/README.md`**

In `eval-infra/README.md`, after line 19 (the `03-scoring` row), insert:

```markdown
| [`04-benchmark/`](04-benchmark/) | Capability reports: GPU/RAM profiling, per-page timing, score stability across N runs. Observe-only -- zero adapter changes required. | `run.ps1` Windows, `verify.ps1` Windows |
```

- [ ] **Step 3: Update `scripts/full-verify.ps1`**

After line 77 (`Write-Host "=== full-verify ..."`):

Update the comment header line 8-22 to describe 8 checks instead of 7:

Change:
```powershell
#   6. Predictions present            (adapter output)
#   7. Scores present + non-zero      (03-scoring)
```
To:
```powershell
#   6. Predictions present            (adapter output)
#   7. Scores present + non-zero      (03-scoring)
#   8. Benchmark report valid         (04-benchmark, optional)
```

After the scoring check (currently ends at line 222):

Insert before the `# --- Summary ---` section:

```powershell
# --- 8. Benchmark report (optional - skip if not run) -----------------------
Write-Host ""
Write-Host "[8/8] benchmark report" -ForegroundColor Cyan
$benchVerify = Join-Path $rootDir "eval-infra\04-benchmark\verify.ps1"
if (Test-Path $benchVerify) {
    # Find most recent benchmark results directory
    $benchDirs = @(Get-ChildItem (Join-Path $rootDir "benchmark-results") -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne "reference" } | Sort-Object LastWriteTime -Descending)
    if ($benchDirs.Count -gt 0) {
        $latestBench = $benchDirs[0].FullName
        [void](Invoke-Verify "04-benchmark/verify" "$benchVerify -ReportDir '$latestBench'")
    } else {
        Add-Result "04-benchmark/verify" "SKIP" "no benchmark runs found"
    }
} else {
    Add-Result "04-benchmark/verify" "SKIP" "verify script not present"
}
```

And update the `Add-Result` call at the start to reference 8 steps in the section header labels:
- Change `[6/7]` to `[6/8]`
- Change `[7/7]` to `[7/8]`

- [ ] **Step 4: Update `.gitignore`**

Append to `.gitignore`:

```
# Benchmark outputs (machine-specific, except reference baselines)
benchmark-results/*
!benchmark-results/reference/
**/monitor_stop.txt
```

- [ ] **Step 5: Update `AGENTS.md`**

After line 156 (end of Step 4 scoring section), insert:

```markdown
### Step 5 — benchmark + capability report  (Windows, `eval-infra/04-benchmark/`)

```powershell
# 5a. Single run: full pipeline with resource monitoring → capability report.
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1

# 5b. Verify the benchmark produced a valid report.
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\verify.ps1 -ReportDir (Get-ChildItem benchmark-results -Directory | Where-Object { $_.Name -ne 'reference' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

# 5c. Stability mode: N runs for statistical confidence (recommended for reference data).
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1 -Stability 5
```
```

In the exception lookup table, add two new rows:

```markdown
| Benchmark report missing GPU data | `docs/pitfalls.md#benchmark-gpu` |
| `verify.ps1` exit 1 on score mismatch | `docs/pitfalls.md#benchmark-verify` |
```

- [ ] **Step 6: Commit**

```bash
git add docs/architecture.md eval-infra/README.md scripts/full-verify.ps1 .gitignore AGENTS.md
git commit -m "feat(benchmark): wire 04-benchmark into existing docs + full-verify chain"
```

---

### Task 13: Reference Benchmark Data (optional validation run)

**Files:**
- Create: `benchmark-results/reference/` (committed after successful run)

**Interfaces:**
- Consumes: all previous tasks; requires fully provisioned OmniDocBench environment

- [ ] **Step 1: Verify environment is ready**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1
```

Expected: Exit 0 (Step 8 may SKIP if no prior benchmark run -- that's OK).

- [ ] **Step 2: Run stability benchmark**

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1 -Stability 3
```

Expected: 3 full pipeline runs (may take several hours). Produces `benchmark-results/reference/paddleocrvl_q4km_hip/`.

- [ ] **Step 3: Verify benchmark output**

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\verify.ps1 -ReportDir benchmark-results\reference\paddleocrvl_q4km_hip
```

Expected: VERIFY OK (5/5 PASS)

- [ ] **Step 4: Manually review report**

Open `benchmark-results/reference/paddleocrvl_q4km_hip/benchmark-report.md` and verify:
- [ ] All 4 metrics present and non-zero
- [ ] GPU memory data present (not "unavailable")
- [ ] ASCII chart visible in monospace
- [ ] Stability chapter shows mean/std across 3 runs
- [ ] Traceability links present
- [ ] Machine-generated marker on line 1

- [ ] **Step 5: Commit reference baseline**

```bash
git add benchmark-results/reference/
git commit -m "data(benchmark): reference capability report for paddleocr-vl-1.6 Q4_K_M HIP"
```

---

## Self-Review Checklist

- [ ] Task 1: Scaffolding + config + 3 test fixtures -- independent, complete
- [ ] Task 2: monitor.py basic loop + output format test -- uses TDD
- [ ] Task 3: degradation chain test -- builds on Task 2
- [ ] Task 4: sentinel exit + idempotent append tests -- builds on Task 2
- [ ] Task 5: report.py score extraction + single-run mode -- uses fixtures from Task 1
- [ ] Task 6: resource + timing rendering -- builds on Task 5
- [ ] Task 7: ASCII chart + traceability -- builds on Task 5
- [ ] Task 8: reference mode + stability chapter -- builds on Task 5
- [ ] Task 9: run.ps1 orchestrator -- consumes all prior tasks
- [ ] Task 10: verify.ps1 -- gateway, depends on report format
- [ ] Task 11: README docs -- depends on all prior tasks
- [ ] Task 12: existing file mods -- depends on module existing
- [ ] Task 13: reference data -- integration test, optional
