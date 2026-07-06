# AI MAX+ 395 Benchmark Module — Design Spec

> **Status:** Approved (pending user review)
> **Date:** 2026-07-06
> **Scope:** `eval-infra/04-benchmark/` — new module, zero changes to existing adapter/scoring code

## 1. Objective

Transform `omnidocbench-amd-windows` into a **data-backed, platform-optimized**
open source project. The first deliverable is an end-to-end capability report
that proves, with machine-generated data, that AMD Ryzen AI Max+ 395 (128GB
unified memory) can run the full OmniDocBench v1.6 pipeline — inference +
scoring + CDM — entirely locally, with quantified quality, speed, and resource
utilization.

The benchmark module produces this report automatically after any adapter run,
without requiring adapter code changes.

### 1.1 Target audience

- **Primary:** AMD Ryzen AI Max+ 395 owners who want to evaluate document
  parsing models. They need to know: "Can my machine do this? How long? What
  quality? Can I trust the data?"
- **Secondary:** Model developers who want a reproducible performance baseline
  on this specific hardware.
- **Tertiary:** AI coding agents that read the report to verify setup
  correctness.

### 1.2 Success criteria (what "done" means)

1. `eval-infra/04-benchmark/run.ps1` executes a complete benchmark pipeline and
   produces a valid `benchmark-report.md`.
2. `eval-infra/04-benchmark/verify.ps1` exits 0 after a successful run.
3. The report contains:
   - Four quality metrics with traceability to `*_metric_result.json`
   - GPU memory utilization data with ASCII chart (machine-generated)
   - Per-page timing distribution (P50/P95/P99)
   - End-to-end wall-clock decomposition
   - Environment snapshot
4. `benchmark-results/reference/` contains a stability report (≥3 runs, score
   std < 0.002) committed to git.
5. `scripts/full-verify.ps1` chains the benchmark verify step.
6. Zero changes to the adapter interface contract (`run_adapter` signature) or
   existing scoring pipeline.

## 2. Architecture Decision

### 2.1 Chosen approach: Independent benchmark module

The benchmark infrastructure lives in its own module (`eval-infra/04-benchmark/`)
and observes the adapter + scoring pipeline as external subprocesses. It never
imports adapter code and never requires adapter changes.

### 2.2 Rationale

This follows MLPerf's architecture principle: **measurement infrastructure is
separate from the workload being measured.** The adapter IS the workload.
Profiling observes it, does not live inside it.

Key benefits vs. adding profiling to the adapter contract:

| Dimension | Independent module | Profiling in adapter contract |
|---|---|---|
| Adapter changes required | 0 | Template + ref adapter + contract docs |
| New adapters auto-benefit | Yes (via `_run_stats.json` already produced) | Yes (via new mandatory interface) |
| Per-phase timing (layout vs VLM) | No (external observation only) | Yes (adapter can instrument internally) |
| Platform-specific GPU monitoring | Isolated in monitor.py | Leaks into adapter concerns |
| Industry pattern alignment | MLPerf-style | Custom |

The one loss (per-phase timing) is recoverable later via an optional `--profile`
flag if needed; not required for the first capability report.

## 3. Module Structure

### 3.1 File tree

```
eval-infra/04-benchmark/
├── README.md                   # English usage guide + report interpretation
├── README.zh-CN.md             # Chinese usage guide + report interpretation
├── run.ps1                     # Orchestrator: monitor → adapter → scoring → report
├── verify.ps1                  # Verifier: checks report validity and self-consistency
├── monitor.py                  # Resource sampler: background process, 1 Hz
├── report.py                   # Report generator: consumes 3 JSON inputs → Markdown
├── config/
│   └── default.yaml            # Default parameters (quant, interval, output paths)
└── tests/
    ├── test_monitor.py
    ├── test_report.py
    └── fixtures/
        ├── mock_resource_log.jsonl
        ├── mock_run_stats.json
        └── mock_metric_result.json
```

### 3.2 Output artifacts (gitignored except reference/)

```
benchmark-results/
├── reference/                              ← Git committed, immutable baseline
│   └── paddleocrvl_q4km_hip/
│       ├── benchmark-report.md             ← Includes stability section
│       ├── run-01/
│       │   ├── resource_log.jsonl
│       │   ├── phase_log.json
│       │   └── benchmark-report.md
│       ├── run-02/ ...
│       └── _runs_manifest.json             ← Index + aggregate stats (schema §3.4)
└── <run_id>/                               ← User per-run output, gitignored
    ├── benchmark-report.md
    ├── resource_log.jsonl
    └── phase_log.json
```

`.gitignore` rules (repo root, see §10):
```
benchmark-results/*
!benchmark-results/reference/
**/monitor_stop.txt
```

### 3.3 Responsibility matrix

```
                    monitor.py  run_adapter.py  score.ps1    report.py
                    ──────────  ──────────────  ─────────    ─────────
Produces:
  resource_log.jsonl    ●
  _run_stats.json                        ●
  *metric_result.json                                    ●
  phase_log.json                 (run.ps1 writes)
  benchmark-report.md                                                ●

Consumes:
  resource_log.jsonl                                                  ●
  _run_stats.json                                                     ●
  *metric_result.json                                                 ●
  phase_log.json                                                      ●

                    verify.ps1
                    ──────────
Validates:
  resource_log non-empty + schema   ●
  report exists + non-empty         ●
  machine-generated marker          ●
  score self-consistency            ●
  multi-run stability               ●
```

## 4. Process Lifecycle (the critical path)

The most fragile part of the module is the cross-process coordination between
`run.ps1` (orchestrator) and `monitor.py` (background sampler). The design uses
**file-system handshake** rather than timing assumptions.

### 4.1 Execution sequence

`run.ps1` launches `monitor.py` with its working directory set to the run output
directory. All file paths below are relative to `benchmark-results/<run_id>/`.

```
run.ps1:
  0. read config/default.yaml, override with CLI args
  1. mkdir benchmark-results/<run_id>/
  2. Start-Process python -WorkingDirectory benchmark-results/<run_id>/
       -ArgumentList "monitor.py --output resource_log.jsonl" -PassThru
  3. wait until resource_log.jsonl exists → monitor ready signal
  4. write phase_log.json: {monitor_warmup_end, adapter_start}
       (using ConvertTo-Json, see section 6 for schema)
  5. python adapters/<name>/run_adapter.py --img-dir ... --out-dir ...
       → blocking, minutes to hours
  6. append to phase_log.json: {adapter_end}
  7. New-Item monitor_stop.txt → sentinel file, monitor reads and exits
  8. $proc.WaitForExit(5000) || $proc.Kill()
  9. append to phase_log.json: {scoring_start}
 10. powershell -File eval-infra/03-scoring/score.ps1 -Config v16-cdm.yaml
 11. wsl bash .../score-cdm.sh v16-cdm.yaml
 12. append to phase_log.json: {scoring_end}
 13. python report.py
        --resource resource_log.jsonl
        --stats predictions/<name>/_run_stats.json
        --scores result/*_metric_result.json
        --phase-log phase_log.json
        --output benchmark-report.md
        --mode single
 14. if --stability > 1:
        a. accumulate current run metrics + resource_log into _runs_manifest.json
        b. repeat steps 1-13 for N-1 more runs (each in sub-dir run-NN/)
        c. after all N runs complete, run report.py once with --mode reference
           (reads _runs_manifest.json to aggregate all N runs into stability chapter)
 15. powershell -File verify.ps1 -ReportDir benchmark-results/<run_id>/
```

### 4.2 Monitor loop (monitor.py)

```python
def sample(interval: float, output_path: str):
    """Sample until sentinel file appears. Degrade gracefully on GPU query failure."""
    consecutive_failures = 0
    gpu_backend_level = "gpu-full"   # → gpu-degraded → gpu-unavailable

    with open(output_path, "a") as f:
        while not Path("monitor_stop.txt").exists():
            ts = time.time()
            gpu_mem, gpu_util = None, None

            try:
                gpu_mem, gpu_util = _query_gpu()  # rocm-smi or fallback chain
                consecutive_failures = 0
            except GPUQueryError:
                consecutive_failures += 1
                threshold = config.get("gpu_sample_fail_threshold", 3)
                if consecutive_failures >= threshold:
                    gpu_backend_level = "gpu-degraded"
                if consecutive_failures >= 10 * threshold:   # ~30s at 1 Hz
                    gpu_backend_level = "gpu-unavailable"

            ram = psutil.virtual_memory().used / (1024**3)

            f.write(json.dumps({
                "ts": ts,
                "gpu_mem_mib": gpu_mem,
                "gpu_util_pct": gpu_util,
                "ram_gib": round(ram, 2),
                "gpu_level": gpu_backend_level,
            }) + "\n")
            f.flush()   # survive crash
            time.sleep(interval)
```

### 4.3 GPU query degradation chain

| Order | Backend | Command | Fallback if |
|---|---|---|---|
| 1 | rocm-smi | `rocm-smi --showmeminfo vram --json` | not installed |
| 2 | typeperf | `typeperf "\GPU Adapter Memory(*)\*"` | rocm-smi failed |
| 3 | none | — | all GPU backends failed |

### 4.4 Error severity levels in report

| Level | Condition | Report rendition |
|---|---|---|
| `gpu-full` | rocm-smi available throughout | Full GPU curve + peak + avg utilization |
| `gpu-degraded` | Partial samples missing | "GPU data partial (N of M samples)" + gap markers |
| `gpu-unavailable` | rocm-smi not installed / total failure | "GPU data unavailable — install ROCm HIP SDK" + RAM-only |

### 4.5 Orchestrator robustness guarantees

- **monitor crash:** Does NOT halt the pipeline. Adapter and scoring complete normally.
  Report will show degraded/null GPU data but all quality metrics present.
- **Ctrl+C during adapter:** `finally` block in `run.ps1` writes `monitor_stop.txt` and
  calls `Stop-Process` on the monitor handle.
- **Idempotency:** Re-running with the same `run_id` appends to existing files (monitor
  log continues, phase_log appends). The `run_id` is timestamp-based by default so
  normal runs are always fresh.

## 5. Report Format

### 5.1 Template

The full report template is specified in the design discussion. Key structural
requirements:

1. **Machine-generated marker:** `<!-- generated: true 2026-07-06T14:30:00+08:00 -->`
   at line 1. `verify.ps1` checks for this; absence = FAIL.
2. **Metadata header:** Hardware platform, quantization level, backend, run ID.
3. **Chapter 1 — Overview:** One-screen summary table (4 metrics + time + GPU + success rate).
4. **Chapter 2 — Quality scores:** Detailed table with `[trace]` links to JSON paths.
5. **Chapter 2.3 — Stability** (reference mode only): N-run score statistics (mean, std, range).
6. **Chapter 3 — Compute resources:** GPU memory (peak/avg/curve), GPU utilization, system RAM.
7. **Chapter 4 — Inference performance:** Time decomposition, per-page distribution (P50/P95/P99), failures.
8. **Chapter 5 — Environment snapshot:** OS, ROCm, llama.cpp commit, Python, config name.
9. **Appendix — Traceability index:** Each score → JSON path → file → original command.

### 5.2 ASCII chart generation

`report.py` renders GPU memory and GPU utilization curves using 8-level Unicode
block characters (`█▇▆▅▄▃▂▁`). Data comes from `resource_log.jsonl`.

**Algorithm:**
1. Read all `(ts, gpu_mem)` pairs from JSONL.
2. Align to minute-bucket X-axis, GiB Y-axis.
3. Downsample to fit terminal-width output columns.
4. Use max-value-in-bucket for fill height (never underestimate peaks).
5. Overlay phase boundaries from `phase_log.json` (warmup / inference / scoring).

**Key constraint:** Every character in the chart is data-driven. No hand-drawn
ASCII art. `verify.ps1` does not validate chart fidelity (visual), but the
reproducibility of the underlying data is enforced by the score consistency
check.

### 5.3 Traceability chain

Every numeric claim in the report is backed by a machine-parseable trace:

```markdown
| Formula CDM | **0.944** | <!-- trace: result/paddleocrvl_rocm_cdm_quick_match_metric_result.json#/display_formula/all/CDM/all --> |
```

The appendix auto-indexes all `<!-- trace: ... -->` comments into a table.

### 3.4 `_runs_manifest.json` schema (stability mode only)

Generated by `run.ps1` after all N stability runs complete. Consumed by
`report.py --mode reference` to render the stability chapter.

```json
{
  "expected_runs": 5,
  "runs": [
    {
      "run_dir": "run-01",
      "scores": { "text_edit_dist": 0.0350, "reading_order": 0.1290, "table_teds": 0.9400, "formula_cdm": 0.9440 },
      "duration_sec": 4680,
      "gpu_peak_mib": 8601,
      "pages_ok": 1648,
      "pages_total": 1651
    }
    // ... run-02 through run-05
  ]
}
```

### 3.5 `phase_log.json` schema

## 6. Scoring Metadata (`phase_log.json`)

The orchestrator (`run.ps1`) writes this file to capture phase transition
timestamps so `report.py` can label charts and compute per-phase durations.

```json
{
  "run_id": "20260706-143000",
  "platform": "AMD Ryzen AI Max+ 395 · Radeon 8060S · 128GB",
  "qualifier": "paddleocrvl_q4km_hip",
  "phases": [
    {"name": "monitor_warmup",     "ts": 1750259400.123},
    {"name": "adapter_start",      "ts": 1750259405.456},
    {"name": "adapter_end",        "ts": 1750263120.789},
    {"name": "scoring_start",      "ts": 1750263125.012},
    {"name": "scoring_end",        "ts": 1750264080.345}
  ]
}
```

## 7. Configuration (`config/default.yaml`)

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

## 8. Verify Script (`verify.ps1`)

Five checks, ordered, first failure exits 1:

| Check | What | Fail if |
|---|---|---|
| 1. Resource log | `resource_log.jsonl` exists, non-empty, required fields present | Missing file, empty, missing `ts`/`gpu_mem_mib`/`gpu_util_pct`/`ram_gib` |
| 2. Report file | `benchmark-report.md` exists, >500 chars, declares target hardware | Missing, too short, no "AMD Ryzen AI Max+" string |
| 3. Machine-generated | Contains `<!-- generated: true ... -->` marker | Absent (implies hand-edited, not trustworthy) |
| 4. Score consistency | Extracted scores match `*_metric_result.json` values | Any metric delta > 0.001 |
| 5. Stability (optional) | If `_runs_manifest.json` present, all N run logs exist | Missing sub-directories |

Stability check is a PASS (not skipped) when no manifest exists (single-run mode).

## 9. Test Strategy

### 9.1 `test_monitor.py`

| Test | What it verifies | Assertion |
|---|---|---|
| Output format | Each line is valid JSON | `json.loads(line)` succeeds for all lines |
| Required fields | Every line has `ts`, `gpu_mem_mib`, `gpu_util_pct`, `ram_gib`, `gpu_level` | `KeyError` raised on first missing field |
| Degradation trigger | After N consecutive failures (N=threshold), `gpu_level` degrades | `gpu_level` transitions: full → degraded → unavailable |
| Sentinel exit | Monitor exits within 1s of sentinel file appearing | Loop exits, output file is closed cleanly |
| Idempotent append | Re-running appends to existing log, no corruption | First run lines + second run lines = total lines |

### 9.2 `test_report.py`

| Test | What it verifies | Assertion |
|---|---|---|
| Score extraction | Four metrics parsed correctly from `mock_metric_result.json` | CDM value matches fixture |
| Single-run mode | Report contains no stability chapter | "稳定性" not in output |
| Reference mode | Report contains stability chapter | "标准差" present; mean/std computed correctly from N fixtures |
| GPU degraded rendering | Report shows "GPU data partial" when fixture has mixed levels | Substring match |
| GPU unavailable rendering | Report shows "GPU data unavailable" when fixture has `gpu_level: none` | Substring match |
| Generated marker | First line contains machine-generated comment | `<!-- generated: true` in output |
| ASCII chart | Output contains block characters when data present | At least one `█` in output when GPU data > 0 |
| Traceability link | Report contains `<!-- trace: ... -->` comments | Regex match for at least 4 trace links |

### 9.3 Fixtures

All fixtures are minimal valid examples (10-20 data points each):

- `mock_resource_log.jsonl` — 20 samples: 10 full, 5 degraded (no `gpu_mem`), 5 unavailable
- `mock_run_stats.json` — 10 pages, 8 OK + 2 failed, realistic timing spread
- `mock_metric_result.json` — valid OmniDocBench result schema with known values

### 9.4 Running tests

```powershell
python -m pytest eval-infra\04-benchmark\tests\ -v
```

No new test dependencies beyond Python stdlib + `pytest`.

## 10. Existing Files to Modify

| File | Change |
|---|---|
| `docs/architecture.md` | Add `04-benchmark` to data-flow diagram; update 3-layer to 4-layer listing |
| `eval-infra/README.md` | Module table: add row 5 (04-benchmark) |
| `scripts/full-verify.ps1` | `$modules` array: add `"04-benchmark"`; `Invoke-ModuleVerify` step for benchmark |
| `.gitignore` | Add: `benchmark-results/*` + `!benchmark-results/reference/` + `**/monitor_stop.txt` |
| `CLAUDE.md` | Execution flow: add Step 5 after Step 4; exception lookup: add 2 rows (benchmark-specific failures) |

## 11. Non-Goals (explicitly out of scope)

- **Docker-based runs:** The benchmark module assumes the native Windows+WSL setup.
- **NVIDIA GPU support:** The first implementation targets AMD ROCm/HIP. The GPU
  monitor degradation chain and the config `gpu_backends` list are designed for
  extension (future: `nvidia-smi` backend), but not implemented now.
- **Interactive dashboard / HTML report:** The report is Markdown. ASCII charts
  render in any monospace terminal or GitHub Markdown preview. An HTML export
  could be added as a report template variant later.
- **Continuous benchmarking (CI/CD):** The module runs on-demand (`run.ps1`).
  No GitHub Actions integration in this scope.
- **Adapter per-phase instrumentation:** Layout vs VLM timing breakdown requires
  changes to `paddleocr_vl_rocm` (external package). Deferred until user demand
  justifies it.

## 12. Conventions Followed

All design decisions reference the repo's established conventions from
`CONTRIBUTING.md`, `CLAUDE.md`, and the existing `eval-infra/` modules:

- PowerShell 5.1 compatible (no `??`, no ternary, no `Join-Path` 3-arg)
- `$ErrorActionPreference = "Stop"` in all `.ps1` scripts
- Bash scripts use `set -euo pipefail`
- Idempotency: re-running is safe (append mode for logs, timestamp-based run IDs)
- `mirrors.env`-aware for downloads (benchmark module downloads nothing, but
  subprocess adapter/setup scripts do)
- `PYTHONUTF8=1` set for all Python subprocess calls
- Bilingual README (EN + zh-CN) for the module directory
- `verify.ps1` exits 0/1 per module
- Numbered sub-directory (`04-`) matching `eval-infra/` convention

## 13. Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| `rocm-smi` unavailable on target machine | Medium | Degradation chain → RAM-only fallback. Report clearly labels which GPU data was unavailable. |
| Monitor process orphaned on crash | Low | `finally` block in `run.ps1` kills by process handle. Sentinel file is a backup: monitor exits on its own when `monitor_stop.txt` appears, even if parent crashed. |
| Resource log grows too large (1651 × 3600s = 6M lines) | Low | 1 Hz × 1h = 3600 lines. JSONL ~200 bytes/line = ~0.7 MB. Trivial. |
| Report generation fails due to partial data | Medium | `report.py` treats every input as optional except `_run_stats.json` and `*_metric_result.json`. Missing resource data = degraded chapter, not crash. |
| Stability mode OOM/timeout | Medium | Each stability run is a full 1651-page pipeline. 5 runs × 1.3h = 6.5h. `run.ps1` prints ETA after first run. Configurable via `--stability N`. |
