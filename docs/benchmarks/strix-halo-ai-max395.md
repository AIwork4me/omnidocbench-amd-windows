# Strix Halo (Ryzen AI MAX+ 395) platform evidence

Date: 2026-08-02. Branch: phase-b/mineru-adapter. Scope: measured timings and
resource data for the full OmniDocBench v1.6 pipeline on the reference machine.
Every number cites its source file; nothing is estimated without saying so.

## 1. Platform

| Item | Value | Source |
|---|---|---|
| CPU | AMD Ryzen AI MAX+ 395 (Strix Halo) | `Get-CimInstance Win32_Processor`, re-run 2026-08-02 |
| GPU | AMD Radeon 8060S (`AMD Radeon(TM) 8060S Graphics`, gfx1151) | `torch.cuda.get_device_name(0)`, re-run 2026-08-02 |
| Memory | 128 GB unified; 123.6 GiB OS-visible | `psutil.virtual_memory().total` / CIM, 2026-08-02 |
| GPU-addressable memory | 80,065.5 MiB (~78.2 GiB) reported by ROCm | `torch.cuda.mem_get_info()` in [strix-halo-gpu-probe-2026-08-02.jsonl](strix-halo-gpu-probe-2026-08-02.jsonl) |
| PyTorch / HIP | torch 2.9.1+rocm7.2.1, HIP 7.2.53211-158bd99533 | B1 verify (`.superpowers/sdd/task-B1-report.md`); re-run `python -c "import torch; print(torch.version.hip)"` 2026-08-02 |
| OS | Windows 11 | machine baseline |

Model-card hardware block agrees: `MinerU-ROCm/model_card.pipeline.windows-hip.json`
records `AMD Ryzen AI MAX+ 395 (Radeon 8060S, Strix Halo)`, shared unified
memory, Windows ROCm 7.2.1 / HIP 7.2.53211.

## 2. Per-phase wall-clock (full 1651-page pipeline)

| Phase | Measured wall-clock | Source / method |
|---|---:|---|
| Dataset download | no timing retained on this machine | honest gap — not re-measured |
| CDM environment (TeX Live 2026 + IM7 + Ghostscript) | no timing retained on this machine | honest gap — not re-measured |
| Inference — PaddleOCR-VL-ROCm engine (1651 pages, ok=1649) | per-page seconds sum **21,061.5 s ≈ 5.85 h**; mean 12.76 s/page | `predictions/paddleocrvl_rocm/_run_stats.json` (stats[].seconds sum) |
| Inference — PaddleOCR-VL official engine, run 2026-07-09 (ok=1650, 1 PEG fail) | per-page seconds sum **28,365.9 s ≈ 7.88 h**; mean 17.18 s/page | `predictions/paddleocr_official_prettyfalse_full_2026-07-09/_run_stats.json` |
| Inference — PaddleOCR-VL official engine, run 2026-07-10 (1650/1651 ok) | log span 2026-07-10 18:47:20 → last write 2026-07-11 03:18 ≈ **8.5 h wall** | `PaddleOCR-VL-ROCm/logs/official_full_infer_20260710_184720.out.log` (filename start timestamp + file mtime) |
| Inference — MinerU 3.4.4 pipeline (1651 pages, ok=1651, fail=0) | per-page seconds sum **31,497.3 s ≈ 8.75 h**; mean 19.08 s/page (min 0.68 s, max 2297.8 s) | `predictions/mineru_pipeline/_run_stats.json` (stats[].seconds sum; method note below) |
| Scoring — Windows-native CDM (official rerun, 2352 CDM samples) | log 2026-07-11 09:25:51 → last write 10:21 ≈ **55 min** | `PaddleOCR-VL-ROCm/logs/official_cdm_rerun_20260711_092548.log` |
| Scoring — non-CDM (Edit-dist + TEDS) | no precise timing retained | honest gap — minutes scale |

**MinerU wall-clock method note.** `predictions/mineru_pipeline/_run_stats.json`
stores per-page `seconds` but no start/end timestamps, so the wall-clock is the
sum of per-page seconds; the pipeline engine processes pages sequentially, so
the sum is a wall-clock measure, not a lower bound from concurrent latencies.
Filesystem bounds corroborate: initial stats written 2026-07-22 20:58, retry
stats 22:31, final merged stats 2026-07-23 09:46 (retries/repairs included;
model card `eval_date` 2026-07-23). Independent corroboration: the B2 gate doc
records that the original full run processed the same 130-page stratified
sample in **41.0 min (mean 18.9 s/page)**, matching the full-run mean of
19.08 s/page ([mineru-sample81-gate-2026-08-01.md](mineru-sample81-gate-2026-08-01.md), Step 3).

## 3. Resource usage key points

Fresh minimal collection on 2026-08-02 (no usable monitor archive existed in
this checkout): `eval-infra/04-benchmark/monitor.py` sampled system state at
1 Hz for 89.3 s while a sustained torch matmul load with a ~4.9 GiB persistent
GPU allocation ran on the 8060S. Raw data:
[strix-halo-monitor-2026-08-02.jsonl](strix-halo-monitor-2026-08-02.jsonl) (90 samples),
[strix-halo-gpu-probe-2026-08-02.jsonl](strix-halo-gpu-probe-2026-08-02.jsonl).

- **Unified memory confirmed**: system RAM rose 21.05 → 25.9 GiB (Δ ≈ 4.9 GiB,
  min/max over the window) while torch held 4,896 MiB device-allocated — GPU
  allocations surface directly in system RAM on Strix Halo.
- **GPU counters unavailable on Windows**: `rocm-smi` is not on PATH; the
  monitor degraded `gpu-full → gpu-unavailable` and kept RAM-only samples.
  Consistent with the B2 gate note that Windows GPU performance counters stay
  ~0% during genuinely-GPU ROCm/HIP work. GPU-side memory was therefore
  measured via `torch.cuda.mem_get_info()` / `memory_allocated()` instead.
- **Compute probe**: matmul 4096³ = 65.07 ms/iter ≈ **2.11 TFLOPS** (fresh,
  2026-08-02), vs 59.8 ms/iter ≈ **2.30 TFLOPS** for the same shape in the B2
  gate doc (post-recovery probe) — same ballpark, healthy MIOpen find-db.
- **MIOpen cache sensitivity** (from the B2 gate incident): an unclean shutdown
  corrupted the 35 MB user find-db (`~/.miopen/db/gfx1151_20...ufdb.txt`) and
  made inference 20–100× slower per page; deleting the cache fixed it. Relevant
  to anyone reproducing these timings.

## 4. G4 concurrency speedup (re-citation)

Source: [`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md`](../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md),
"G4 Inference Performance" (commit `PaddleOCR-VL-ROCm 50ce802`,
`vlm_max_workers` 1 → 8). Controlled benchmark on 27 stratified pages (9
categories), same machine:

| Mode | Total | Mean/page | Median/page | Max/page |
|---|---:|---:|---:|---:|
| Sequential (workers=1) | 602.0 s | 22.3 s | 15.0 s | 86.7 s |
| Concurrent (workers=8) | 357.2 s | 13.2 s | 10.1 s | 40.6 s |
| **Speedup** | **1.7x** | **1.7x** | **1.5x** | **2.1x** |

Full 1650-page estimate in that doc: ~10.2 h sequential → ~6.1 h concurrent.
Accuracy preservation: 18-page structural comparison, 0 structural mismatches,
16/18 bit-exact MD5 (2/18 character-level GGUF nondeterminism, unrelated to
concurrency).

Cross-check with the measured full runs above: the ROCm-engine full run's
per-page seconds sum (5.85 h, mean 12.76 s/page) matches the G4 concurrent
estimate (~6.1 h, mean 13.2 s/page), and the official-engine measured wall
(~8.5 h / 7.88 h latency-sum, mean 17.18 s/page) sits between the G4
sequential and concurrent estimates.

## 5. Source inventory

| Number in this page | Source file |
|---|---|
| MinerU 8.75 h / mean 19.08 s / ok=1651 | `predictions/mineru_pipeline/_run_stats.json` (machine-local, gitignored) |
| MinerU 130-page 41.0 min / 18.9 s corroboration, 2.30 TFLOPS, MIOpen incident | [mineru-sample81-gate-2026-08-01.md](mineru-sample81-gate-2026-08-01.md) |
| ROCm-engine 5.85 h / mean 12.76 s / ok=1649 | `predictions/paddleocrvl_rocm/_run_stats.json` (machine-local, gitignored) |
| Official 2026-07-09 run 7.88 h / mean 17.18 s / ok=1650 | `predictions/paddleocr_official_prettyfalse_full_2026-07-09/_run_stats.json` (machine-local, gitignored) |
| Official 2026-07-10 run ~8.5 h wall | `C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm\logs\official_full_infer_20260710_184720.out.log` |
| CDM scoring ~55 min / 2352 samples | `C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm\logs\official_cdm_rerun_20260711_092548.log` |
| G4 1.7x table + full-run estimate + accuracy check | [../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md](../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md) |
| RAM 21.05→25.9 GiB, monitor degradation | [strix-halo-monitor-2026-08-02.jsonl](strix-halo-monitor-2026-08-02.jsonl) |
| 2.11 TFLOPS, torch device total 80,065.5 MiB, 4,896 MiB alloc | [strix-halo-gpu-probe-2026-08-02.jsonl](strix-halo-gpu-probe-2026-08-02.jsonl) |
| torch 2.9.1+rocm7.2.1 / HIP 7.2.53211 / GPU name | fresh re-run 2026-08-02 + `.superpowers/sdd/task-B1-report.md` |
| Hardware block (Strix Halo, unified memory, ROCm 7.2.1) | `C:\Users\rocm\Desktop\MinerU-ROCm\model_card.pipeline.windows-hip.json` |
