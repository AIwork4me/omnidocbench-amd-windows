# Non-CDM Official Regression Root Cause - 2026-07-09

## Metric Comparison

| Run | Text Edit-distance (lower better) | Reading-order Edit-distance (lower better) | Table TEDS (higher better) | Table Edit-distance (lower better) | Formula CDM (higher better) |
|---|---:|---:|---:|---:|---:|
| Lightweight full-set | 0.0339697 | 0.1283252 | 0.9432165 | 0.0553582 | 0.9483259 |
| Official full-set, before fix | 0.0412925 | 0.1296430 | 0.9407939 | 0.0570109 | 0.9668288 |
| Official full-set, after matcher fix | 0.0406371 | 0.1288581 | 0.9407990 | 0.0570109 | not rerun |

## Confirmed Root Causes

1. Scorer timeout fallback was under-merging long text spans.
   - Bad page: `docstructbench_enbook-zlib-o.O-17208435.pdf_57.jpg`.
   - Lightweight and official Markdown are nearly identical, but official scoring hit `quick-match-timeout`.
   - Before fix, the three GT text blocks matched empty predictions: all `edit=1.0`, reading-order `pred=[]`.
   - After fix, full-set scoring recovered them via local span fallback:
     - `gt_idx=[4]`: `1.0000 -> 0.0288`
     - `gt_idx=[5]`: `1.0000 -> 0.0037`
     - `gt_idx=[6]`: `1.0000 -> 0.0130`
   - Full-set impact: Text improved by `0.0006554`, Reading-order improved by `0.0007849`.

2. Official adapter had one VLM/parser failure that became an empty page.
   - Failed page: `newspaper_The Times UK_0801@magazinesclubnew_page_031.png`.
   - Existing official stats: `1650/1651` ok, one VLM 500: `peg-native format`.
   - The scorer still warns: `No prediction ... evaluate as empty page`.
   - Fix added: official engine now retries per page and supports explicit `--fallback-pred-dir`, recording fallback pages in `_run_stats.json`.
   - The already-generated prediction directory was not silently modified; rerun official adapter or use the explicit fallback option to repair this page.

3. Remaining non-CDM gap is mostly output/model-engine behavior, not evaluator compatibility.
   - After the matcher fix, Text is still `+0.0066674` worse than lightweight.
   - Table TEDS is still `-0.0024175`; the largest remaining table drops are the missing page and true official table-output differences such as `page-112859dc-07d9-473a-a027-94904db8fd84.png`.
   - Formula CDM remains higher on official output than lightweight in the last CDM full run (`0.9668288` vs `0.9483259`).

## Fixes Landed

- Added tracked OmniDocBench patch:
  `eval-infra/01-omnidocbench/patches/0002-timeout-fallback-long-text-span.patch`
- Made Windows and WSL setup apply the new patch idempotently.
- Added `v16-official.yaml` for Windows-native official non-CDM scoring.
- Added official adapter per-page retry and explicit fallback prediction support.

## Verification

- RED/GREEN synthetic regression test for long text split across many predictions.
- Real-page probe for `docstructbench_enbook-zlib-o.O-17208435.pdf_57.jpg`.
- Full-set official non-CDM scoring after matcher fix:
  `logs/official-fullset/score_official_nocdm_after_fix_stdout.log`
  and
  `logs/official-fullset/score_official_nocdm_after_fix_stderr.log`.
