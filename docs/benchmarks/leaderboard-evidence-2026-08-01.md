# Multi-model leaderboard — per-cell evidence (2026-08-01)

Date: 2026-08-02. Branch: main. Every number published in the README
"Multi-model leaderboard" section (EN + ZH) is traced below to a scorer
artifact and re-verified by `scripts/verify_leaderboard_numbers.py` (数字铁律:
script assertions against the real JSON/md sources, output pasted verbatim at
the bottom).

2026-08-02 redesign (user directive: README tables are local-evidence-only —
every number must come from tests run on this machine): the paper row and the
official-local row were removed from the README tables and retired to the
"Retired rows" section below (evidence retained); the MinerU2.5-Pro llama.cpp
row was added after the acceptance cross-check recorded in "Row 2".

Aggregation convention: OmniDocBench official leaderboard/notebook page-level
aggregation (`tools/generate_result_tables.ipynb` overall cell), the repo
convention per `AGENTS.md` — text/reading-order use
`all.Edit_dist.ALL_page_avg`, TEDS/CDM use `page.*.ALL × 100`; Overall =
((1 − text Edit-dist) × 100 + TEDS + CDM) / 3. The MinerU rows use
quick-match CDM. Where a JSON's pooled `all.*.all` readout differs from the
published page-level value, the pooled figure is recorded in the row's
transparency note.

## Published table

| Model | Backend (this machine) | Overall | Text Edit-dist ↓ | Reading-order Edit-dist ↓ | Table TEDS ↑ | Formula CDM ↑ |
|---|---|---:|---:|---:|---:|---:|
| PaddleOCR-VL-1.6 | llama.cpp GGUF (ROCm/HIP) | **95.99** | 0.03488 | 0.12882 | **94.09** | **97.36** |
| MinerU2.5-Pro-2605-1.2B | llama.cpp GGUF (HIP) | 95.46 | 0.03734 | **0.12250** | 93.11 | 97.01 |
| MinerU 3.4.4 pipeline | ROCm PyTorch + ONNX DirectML | 86.59 | 0.05655 | 0.15314 | 82.04 | 83.39 |

## Row 1 — PaddleOCR-VL-1.6 (llama.cpp GGUF, ROCm/HIP)

Source: [`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md`](../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md)
("Lightweight (user-facing API path)" table; 1,650 scored pages, symmetric
exclusion of 1 PEG-native page). This is the PaddleOCR-VL-ROCm engine run
measured on this machine (AI MAX+ 395 / Radeon 8060S).

| cell | published | source value | source key |
|---|---:|---:|---|
| Overall | 95.99 | 95.99 | release doc table |
| Text Edit-dist | 0.03488 | 0.03488 | release doc table |
| RO Edit-dist | 0.12882 | 0.12882 | release doc table |
| Table TEDS | 94.09 | 94.0865 | release doc table (rounded to 2 dp) |
| Formula CDM | 97.36 | 97.36 | release doc table |

## Row 2 — MinerU2.5-Pro-2605-1.2B (llama.cpp GGUF, HIP)

Sources:

- Local scorer artifact (this repo, full 1651-page run, quick-match CDM):
  `eval-infra/01-omnidocbench/OmniDocBench/result/mineru2_5_llamacpp_windows_full1651_score_quick_match_metric_result.json`
  (SHA-256 `38507426b6e594ab7a2250c13bacf51301a59eb8f9872cd4c42713a8259b2996`;
  CDM 2,352 samples / 0 timeout / 0 exception; TEDS 665 samples / 0 timeout /
  0 error).
- External cross-check card: `C:\Users\rocm\Desktop\MinerU-ROCm\results\omnidocbench\v16\windows-hip\mineru2.5_v16_quick_match_cdm_metric_result.json`
  — byte-identical to the local artifact (same SHA-256), so the 1e-6
  cross-check in `scripts/verify_leaderboard_numbers.py` section 7 passes with
  diff 0.0 on all four metrics.
- Predictions: `predictions/mineru2_5_llamacpp_windows_full1651_score/` —
  1,651 `.md` files; `scripts/validate_predictions.py` output pasted below.
- Backend per the card bundle README: llama.cpp HIP Q8_0 (build `b9892`),
  context 8192, greedy sampling, flash attention; 1,651 pages attempted,
  1,649 ok, 2 cover/decoration pages with no GT text (empty prediction is
  correct).

| cell | published | raw value | JSON key |
|---|---:|---:|---|
| Overall | 95.46 | 95.45962930130925 | computed: ((1 − text) × 100 + TEDS + CDM) / 3 |
| Text Edit-dist | 0.03734 | 0.037344865867471884 | `text_block.all.Edit_dist.ALL_page_avg` |
| RO Edit-dist | 0.12250 | 0.12250478392812687 | `reading_order.all.Edit_dist.ALL_page_avg` |
| Table TEDS | 93.11 | 93.1054371724098 | `table.page.TEDS.ALL × 100` |
| Formula CDM | 97.01 | 97.00793731826515 | `display_formula.page.CDM.ALL × 100` |

Transparency note: the pooled readout of the same JSON (`table.all.TEDS.all
× 100` = 89.4631, `display_formula.all.CDM.all × 100` = 97.0290) recomputes to
Overall 94.25; the published series above is the repo's page-level convention
per `AGENTS.md` and matches the MinerU-ROCm windows-hip bundle's own headline
(Overall 95.46, identical to the Linux vLLM baseline 95.46). An earlier
revision of this doc published the pooled series; corrected 2026-08-02.

## Row 3 — MinerU 3.4.4 pipeline (ROCm PyTorch + ONNX DirectML)

Sources:

- Model card: `C:\Users\rocm\Desktop\MinerU-ROCm\model_card.pipeline.windows-hip.json`
  (schema_version 1, model_version 3.4.4, backend pipeline, eval_date 2026-07-23).
- Local scorer artifact (this repo):
  `eval-infra/01-omnidocbench/OmniDocBench/result/mineru_pipeline_quick_match_metric_result.json`
  (full 1651-page run, quick-match CDM).
- B2 gate: [`mineru-sample81-gate-2026-08-01.md`](mineru-sample81-gate-2026-08-01.md)
  — verdict **ACCEPT**; 130-page stratified sample (15 strata, seed 42) validated
  the existing 1651-page results: re-inference mean similarity ratio 0.999471
  (≥ 0.98), sample-set scoring diff text 0.000110 (≤ 0.01), TEDS 0.014566 pp
  (≤ 2 pp), and model-card vs metric_result cross-check PASS at 1e-6.

| cell | published | raw value | JSON key |
|---|---:|---:|---|
| Overall | 86.59 | 86.59149200412931 | computed; card `overall` = 86.59 |
| Text Edit-dist | 0.05655 | 0.05654667503567776 | `text_block.all.Edit_dist.ALL_page_avg` |
| RO Edit-dist | 0.15314 | 0.15313839053961972 | `reading_order.all.Edit_dist.ALL_page_avg` |
| Table TEDS | 82.04 | 82.03833096420277 | `table.page.TEDS.ALL × 100` |
| Formula CDM | 83.39 | 83.39081255175297 | `display_formula.page.CDM.ALL × 100` |

Card submetrics equal the local metric_result values bit-for-bit (diff 0.0 at
1e-9); card `overall` is the 2 dp rounding of the computed value.

Transparency note: the pooled readout `table.all.TEDS.all × 100` = 79.6381
(→ 79.64); the published 82.04 above is the repo's page-level convention
(`table.page.TEDS.ALL × 100`) per `AGENTS.md`.

## Retired rows

The paper row and the official-local row were removed from the README tables
per user directive 2026-08-02 (README tables are local-evidence-only; the
paper baseline comparison now lives only in the release doc). Their evidence
is retained here.

### Retired row — PaddleOCR-VL (paper, Linux vLLM)

Source: [`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md`](../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md),
"Public official baseline (OmniDocBench v1.6 leaderboard)" table — the
upstream public baseline.

| cell | published | source value |
|---|---:|---:|
| Overall | 96.33 | 96.33 |
| Text Edit-dist | 0.033 | 0.033 |
| RO Edit-dist | 0.127 | 0.127 |
| Table TEDS | 94.76 | 94.76 |
| Formula CDM | 97.49 | 97.49 |

Note: the published Overall 96.33 is cited verbatim from the upstream baseline
table and does not exactly recompute from the rounded printed cells
((96.7 + 94.76 + 97.49) / 3 = 96.32) because the underlying unrounded inputs
differ.

### Retired row — PaddleOCR-VL official (local run)

Source: Windows-native CDM rerun of the official engine, 2026-07-11 —
metric_result JSON
`C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm\results\omnidocbench\v16\paddleocr_official_local_llamacpp_gguf_quick_match_metric_result_cdm.json`
(run log: `C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm\logs\official_cdm_rerun_20260711_092548.log`,
CDM samples 2352, `timeout_case_count` 0, exception 0). This is the run whose
Formula CDM `96.5022` the READMEs and `AGENTS.md` already cite.

| cell | published | raw value | JSON key |
|---|---:|---:|---|
| Overall | 95.77 | 95.76567875041586 | computed: ((1 − text) × 100 + TEDS + CDM) / 3 |
| Text Edit-dist | 0.03444 | 0.034444814497297645 | `text_block.page.Edit_dist.ALL` |
| RO Edit-dist | 0.12949 | 0.129487416584772 | `reading_order.all.Edit_dist.ALL_page_avg` |
| Table TEDS | 94.24 | 94.23931666667129 | `table.page.TEDS.ALL × 100` |
| Formula CDM | 96.50 | 96.50220103430605 | `display_formula.page.CDM.ALL × 100` |

Note: [`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`](../release-paddleocr-vl-1.6-amd-windows-2026-07-09.md)
records the *earlier* official-engine run scored through the WSL CDM path
(Overall 95.8600 / text 0.03446 / RO 0.12929 / TEDS 94.2187 / CDM 96.8074).
The leaderboard cites the later Windows-native CDM rerun instead, because that
is the run the repo's canonical references (`AGENTS.md` reference table, both
READMEs' `96.5022` citation) point to. The two runs differ only in the CDM
scoring toolchain path (WSL vs Windows-native) and its sibling-metric readout;
the 2026-07-11 set is internally consistent — every cell above comes from one
JSON.

## Verification script output

`./.venv/Scripts/python.exe scripts/verify_leaderboard_numbers.py` (exit 0),
run on this machine 2026-08-02 with the default artifact paths
(`--mineru-rocm-repo` / `--paddleocr-rocm-repo` or the matching
`MINERU_ROCM_REPO` / `PADDLEOCR_ROCM_REPO` env vars override them; missing
artifacts SKIP their section instead of failing):

```
== 1. PaddleOCR-VL-ROCm (reference) <- docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md ==
PASS  release-0716 doc contains 95.99
PASS  release-0716 doc contains 0.03488
PASS  release-0716 doc contains 0.12882
PASS  release-0716 doc contains 94.0865
PASS  release-0716 doc contains 97.36
PASS  ROCm TEDS 94.09 rounds from 94.0865  (published=94.09 actual=94.0865 tol=0.005)
== 2. PaddleOCR-VL (paper, Linux vLLM) <- release-0716 public baseline table ==
PASS  baseline table contains 96.33
PASS  baseline table contains 0.033
PASS  baseline table contains 0.127
PASS  baseline table contains 94.76
PASS  baseline table contains 97.49
== 3. PaddleOCR-VL official (local) <- Windows-native CDM rerun metric_result (2026-07-11) ==
  raw: text=0.034444814497297645 ro=0.129487416584772 teds=94.23931666667129 cdm=96.50220103430605 overall=95.76567875041586
PASS  official text Edit-dist 0.03444  (published=0.03444 actual=0.034444814497297645 tol=5e-06)
PASS  official RO Edit-dist 0.12949  (published=0.12949 actual=0.129487416584772 tol=5e-06)
PASS  official TEDS 94.24  (published=94.24 actual=94.23931666667129 tol=0.005)
PASS  official CDM 96.50  (published=96.5 actual=96.50220103430605 tol=0.005)
PASS  official CDM 96.5022 (4dp, as cited in README/AGENTS.md)  (published=96.5022 actual=96.50220103430605 tol=5e-05)
PASS  official Overall 95.77  (published=95.77 actual=95.76567875041586 tol=0.005)
== 4. MinerU 3.4.4 pipeline (Windows HIP) <- model card + in-repo metric_result ==
  metric_result raw: text=0.05654667503567776 ro=0.15313839053961972 teds=82.03833096420277 cdm=83.39081255175297 overall=86.59149200412931
PASS  card model_version == 3.4.4
PASS  card text == metric_result
PASS  card RO == metric_result
PASS  card TEDS == metric_result
PASS  card CDM == metric_result
PASS  card overall == computed overall (rounded to 2dp)  (card=86.59 computed=86.59149200412931)
PASS  MinerU text Edit-dist 0.05655  (published=0.05655 actual=0.05654667503567776 tol=5e-06)
PASS  MinerU RO Edit-dist 0.15314  (published=0.15314 actual=0.15313839053961972 tol=5e-06)
PASS  MinerU TEDS 82.04  (published=82.04 actual=82.03833096420277 tol=0.005)
PASS  MinerU CDM 83.39  (published=83.39 actual=83.39081255175297 tol=0.005)
PASS  MinerU Overall 86.59  (published=86.59 actual=86.59149200412931 tol=0.005)
== 5. B2 gate doc verdict (docs/benchmarks/mineru-sample81-gate-2026-08-01.md) ==
PASS  gate verdict is ACCEPT
PASS  gate sample was 130 pages
PASS  gate cites the 86.59 series
== 6. README leaderboard rows are numerically identical EN vs ZH ==
  README.md leaderboard rows: [['1.6', '95.99', '0.03488', '0.12882', '94.09', '97.36'], ['2.5', '1.2', '95.46', '0.03734', '0.12250', '93.11', '97.01'], ['3.4', '86.59', '0.05655', '0.15314', '82.04', '83.39']]
  README.zh-CN.md leaderboard rows: [['1.6', '95.99', '0.03488', '0.12882', '94.09', '97.36'], ['2.5', '1.2', '95.46', '0.03734', '0.12250', '93.11', '97.01'], ['3.4', '86.59', '0.05655', '0.15314', '82.04', '83.39']]
PASS  both READMEs have 3 leaderboard data rows
PASS  EN/ZH leaderboard numbers identical
== 7. MinerU2.5-Pro llama.cpp (Windows full-set) <- in-repo metric_result vs MinerU-ROCm windows-hip card + 1651 predictions ==
  in-repo raw (page-level): text=0.037344865867471884 ro=0.12250478392812687 teds=93.1054371724098 cdm=97.00793731826515 overall=95.45962930130925
  in-repo raw (pooled, transparency only): teds=89.4631426986761 cdm=97.02908163265313
PASS  MinerU2.5 text Edit-dist: in-repo == card  (published=0.037344865867471884 actual=0.037344865867471884 tol=1e-06)
PASS  MinerU2.5 RO Edit-dist: in-repo == card  (published=0.12250478392812687 actual=0.12250478392812687 tol=1e-06)
PASS  MinerU2.5 TEDS page-level: in-repo == card  (published=93.1054371724098 actual=93.1054371724098 tol=1e-06)
PASS  MinerU2.5 CDM page-level: in-repo == card  (published=97.00793731826515 actual=97.00793731826515 tol=1e-06)
PASS  MinerU2.5 TEDS pooled: in-repo == card  (published=89.4631426986761 actual=89.4631426986761 tol=1e-06)
PASS  MinerU2.5 CDM pooled: in-repo == card  (published=97.02908163265313 actual=97.02908163265313 tol=1e-06)
PASS  MinerU2.5 text Edit-dist 0.03734  (published=0.03734 actual=0.037344865867471884 tol=5e-06)
PASS  MinerU2.5 RO Edit-dist 0.12250  (published=0.1225 actual=0.12250478392812687 tol=5e-06)
PASS  MinerU2.5 TEDS 93.11 (page-level)  (published=93.11 actual=93.1054371724098 tol=0.005)
PASS  MinerU2.5 CDM 97.01 (page-level)  (published=97.01 actual=97.00793731826515 tol=0.005)
PASS  MinerU2.5 Overall 95.46  (published=95.46 actual=95.45962930130925 tol=0.005)
PASS  bundle README contains the 95.46 headline
PASS  MinerU2.5 predictions dir contains 1651 .md files  (count=1651)

VERIFY OK: all leaderboard numbers match their sources
```

## MinerU2.5 predictions validation output

`./.venv/Scripts/python.exe scripts/validate_predictions.py --img-dir eval-infra/01-omnidocbench/data/images --pred-dir predictions/mineru2_5_llamacpp_windows_full1651_score --min-coverage 0.95`
(exit 0), run on this machine 2026-08-02:

```
Expected pages: 1651
Markdown files: 1651
Usable coverage: 1651/1651 (100.00%)
Error-log entries: 0
PREDICTION VERIFY OK
```
