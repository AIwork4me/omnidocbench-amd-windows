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

- Steps 0-3 from [CLAUDE.md](../../CLAUDE.md) must be provisioned (WSL, dataset, CDM environment, adapter)
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
