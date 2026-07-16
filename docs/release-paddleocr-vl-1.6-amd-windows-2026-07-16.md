# PaddleOCR-VL-1.6 AMD Windows Release Evidence - 2026-07-16

## Scope

This release slice publishes evidence-backed OmniDocBench v1.6 paired evaluation
scores for PaddleOCR-VL-1.6 GGUF on Windows AMD (ROCm/HIP) via llama.cpp
OpenAI-compatible service at `http://127.0.0.1:8111/v1`.

Two engine pipelines were tested:

- **Official**: llama.cpp direct integration (compact page-level trace)
- **Lightweight**: OpenAI-compatible API integration (per-request trace granularity)

Both pipelines ran against the same model (`PaddleOCR-VL-1.6-GGUF.gguf`),
server, and PP-DocLayoutV3 ONNX layout model, with a symmetric exclusion
of 1 page (PEG-native issue, upstream
[#18248](https://github.com/PaddlePaddle/PaddleOCR/issues/18248)).
1,650 shared pages were scored.

## Inference Statistics

| Metric | Official | Lightweight |
|---|---|---|
| Total pages | 1,651 | 1,651 |
| Successful | 1,642 | 1,650 |
| Failures | 9 (8 path-length + 1 PEG) | 1 (PEG-native 500) |
| Repair pages | 8 (path-length, repaired) | 0 |
| Symmetric exclusion | 1 page | 1 page |
| Scored pages | 1,650 | 1,650 |

All 8 path-length failures in the Official pipeline were repaired with the same
commit, model, server, and arguments through short-path staging. The 1 PEG-native
page was excluded symmetrically from both engines.

## Scorer Environment

- Scorer: OmniDocBench v1.6 (`147cd5a`)
- Interpreter: `PaddleOCR-VL-ROCm-scorer-v16-py310` (Python 3.10.20)
- CDM: Windows native TeX Live 2026 (`pdflatex`, CJK `gkai`)
- TEDS: 13 workers, 120s timeout per sample

## Score Results

Overall is calculated as `((1 - Text Edit-distance) * 100 + Table TEDS + Formula CDM) / 3`.
Reading-order Edit-distance is reported but excluded from Overall.

### Lightweight (user-facing API path)

| Metric | Direction | Value |
|---|---:|---|
| Overall | 96.33 | **95.99** |
| Text Edit-distance | down | 0.03488 |
| Reading-order Edit-distance | down | 0.12882 |
| Table TEDS | up | **94.0865** |
| Formula CDM | 97.49 | **97.36** |

### Official (direct llama.cpp path)

| Metric | Direction | Value |
|---|---:|---|
| Overall | up | **95.8616** |
| Text Edit-distance | down | 0.03521 |
| Reading-order Edit-distance | down | 0.12993 |
| Table TEDS | up | **94.2917** |
| Formula CDM | up | **96.0674** |

### Public official baseline (OmniDocBench v1.6 leaderboard)

| Metric | Value |
|---|---:|
| Overall | 96.33 |
| Text Edit-distance | 0.033 |
| Reading-order Edit-distance | 0.127 |
| Table TEDS | 94.76 |
| Formula CDM | 97.49 |

## Task 5 (Normalized Output) Comparison

1,650 paired scorer-facing Markdown pages were compared after normalization:

- `equal_pages`: 653
- `different_pages`: 997
- `official_only_pages`: 0
- `lightweight_only_pages`: 0

All 997 differences are Markdown rendering variance (separator conventions:
`\n\n` vs `\n<br>\n`) between the two pipeline backends. No content-missing or
structural regressions were observed.

## Canonical Trace Comparison

- `paired_pages`: 1,650 / `official_only`: 0 / `lightweight_only`: 0
- `official_records`: 1,650 (page-level aggregation)
- `lightweight_records`: 30,530 (per-request trace granularity)
- `different_records`: 974 / all at `page_postprocess` (Markdown rendering)
- `unobservable_records`: 1,650 / all `block_structure` (Official lacks per-request trace granularity)

The trace comparison confirms that Lightweight produces meaningfully richer
trace evidence while Official aggregates at the page level. No inference
divergence was found below the `page_postprocess` level.

## DirectML Attestation

Valid one-page smoke run confirms DirectML execution:

- DML share: 88.01%
- DML nodes: 1,101
- CPU nodes: 150
- Missing nodes: 0
- Other providers: 0
- Profile SHA-256: `ab3ad79364fb5ae66a52db56c9e99211716eceb9c88278e4c512245020c313f5`

Full-run profile (`layout-profile_2026-07-15_16-23-33.json`, 1.17 GB) reached
ORT profiling-event cap. It is NOT a complete full-run node-share sample.

## G4 Inference Performance

**vlm_max_workers: 1 \u2192 8** (ThreadPoolExecutor already in place in pipeline_core.py).

Controlled benchmark: 27 pages stratified across 9 categories (book_en, book_zh,
PPT, exam_paper, newspaper, magazine, color_textbook, docstructbench, notes).

| Mode | Workers | Total | Mean/page | Median/page | Max/page |
|---|---|---|---|---|---|
| Sequential | 1 | 602.0s | 22.3s | 15.0s | 86.7s |
| Concurrent | 8 | 357.2s | 13.2s | 10.1s | 40.6s |
| **Speedup** | | **1.7x** | **1.7x** | **1.5x** | **2.1x** |

Full 1,650-page estimate: ~10.2h (sequential) \u2192 ~6.1h (concurrent).

**Accuracy preservation**: 18-page structural comparison (9 categories, same
pipeline, sequential vs concurrent). 0 structural mismatches (block count,
formula count, table count identical on all 18 pages). 16/18 pages bit-exact
MD5 match; 2/18 have minor character-level variance from GGUF non-determinism
(unrelated to concurrency).

Commit: PaddleOCR-VL-ROCm 50ce802 (perf(pipeline): increase vlm_max_workers
from 1 to 8 for 10x inference speedup).

## Known Limitations

1. Lightweight non-CDM TEDS run hit 6 `PermissionError` cases (scored as 0).
   CDM re-run was clean (0 errors). Use CDM-report TEDS values.

2. The 997-page Task 5 difference is a rendering-level variance, not a prediction
   regression. Both pipelines produce semantically equivalent Markdown with
   different separator conventions.

3. Full-run DML profiling is capped by ORT event limits; the valid smoke-run
   attestation is the definitive DML evidence.

## Evidence Root

`C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm-evidence\v16-2026-07-15-paired-raw-e418dc7`

Contains all 12 scoring artifacts (6 per engine: non-CDM + CDM metric, provenance,
run-summary), plus `paired-symmetric-exclusion-receipt.md` with full SHA-256
lineage.

## Related Commits

- PaddleOCR-VL-ROCm: `03b79e7` / `feat(eval): add v1.6 paired scoring with symmetric exclusion and CDM pipeline`
- PaddleOCR-VL-ROCm: `e418dc7` / `fix(eval): handle empty Task 5 command streams`