# Multi-model leaderboard — per-cell evidence (2026-08-01)

Date: 2026-08-02. Branch: phase-b/mineru-adapter. Every number published in the
README "Multi-model leaderboard" section (EN + ZH) is traced below to a scorer
artifact and re-verified by `scripts/verify_leaderboard_numbers.py` (数字铁律:
script assertions against the real JSON/md sources, output pasted verbatim at
the bottom).

Aggregation convention: OmniDocBench official leaderboard/notebook page-level
aggregation — text/reading-order use `all.Edit_dist.ALL_page_avg`, TEDS/CDM use
`page.*.ALL × 100`; Overall = ((1 − text Edit-dist) × 100 + TEDS + CDM) / 3.
The MinerU row uses quick-match CDM.

## Published table

| Model | Overall | Text Edit-dist ↓ | RO Edit-dist ↓ | Table TEDS ↑ | Formula CDM ↑ |
|---|---:|---:|---:|---:|---:|
| PaddleOCR-VL-ROCm (reference) | 95.99 | 0.03488 | 0.12882 | 94.09 | 97.36 |
| PaddleOCR-VL (paper, Linux vLLM) | 96.33 | 0.033 | 0.127 | 94.76 | 97.49 |
| PaddleOCR-VL official (local run) | 95.77 | 0.03444 | 0.12949 | 94.24 | 96.50 |
| MinerU 3.4.4 pipeline (Windows HIP) | 86.59 | 0.05655 | 0.15314 | 82.04 | 83.39 |

## Row 1 — PaddleOCR-VL-ROCm (reference)

Source: [`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md`](../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md)
("Lightweight (user-facing API path)" table; 1,650 scored pages, symmetric
exclusion of 1 PEG-native page).

| cell | published | source value | source key |
|---|---:|---:|---|
| Overall | 95.99 | 95.99 | release doc table |
| Text Edit-dist | 0.03488 | 0.03488 | release doc table |
| RO Edit-dist | 0.12882 | 0.12882 | release doc table |
| Table TEDS | 94.09 | 94.0865 | release doc table (rounded to 2 dp) |
| Formula CDM | 97.36 | 97.36 | release doc table |

## Row 2 — PaddleOCR-VL (paper, Linux vLLM)

Source: same release doc, "Public official baseline (OmniDocBench v1.6
leaderboard)" table — the upstream public baseline, reproduced in
[`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md`](../release-paddleocr-vl-1.6-amd-windows-2026-07-16.md).

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

## Row 3 — PaddleOCR-VL official (local run)

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

## Row 4 — MinerU 3.4.4 pipeline (Windows HIP)

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
  README.md leaderboard rows: [['95.99', '0.03488', '0.12882', '94.09', '97.36'], ['96.33', '0.033', '0.127', '94.76', '97.49'], ['95.77', '0.03444', '0.12949', '94.24', '96.50'], ['3.4', '86.59', '0.05655', '0.15314', '82.04', '83.39']]
  README.zh-CN.md leaderboard rows: [['95.99', '0.03488', '0.12882', '94.09', '97.36'], ['96.33', '0.033', '0.127', '94.76', '97.49'], ['95.77', '0.03444', '0.12949', '94.24', '96.50'], ['3.4', '86.59', '0.05655', '0.15314', '82.04', '83.39']]
PASS  both READMEs have 4 leaderboard data rows
PASS  EN/ZH leaderboard numbers identical

VERIFY OK: all leaderboard numbers match their sources
```
