# MinerU sample81 gate — validating the existing 1651-page GPU results

Date: 2026-08-02. Branch: phase-b/mineru-adapter. Machine: AMD Ryzen AI MAX+ 395 (Radeon 8060S), Windows, ROCm 7.2.1 / HIP 7.2.53211.

**Gate verdict: ACCEPT.** The existing full-run predictions (`predictions/mineru_pipeline`, 1651 pages, ok=1651 fail=0) are adopted; no full re-run is triggered. The 86.59-series numbers (model card `model_card.pipeline.windows-hip.json`, eval_date 2026-07-23) are validated for B3 consumption.

## Gate rules (from task B2 brief)

- **Metric A**: fresh re-inference of the sample vs the existing predictions — exact-match ≥ 90% **OR** mean `difflib.SequenceMatcher` ratio ≥ 0.98.
- **Metric B**: sample-set scoring both ways — text Edit-distance diff ≤ 0.01, TEDS diff ≤ 2 pp.
- ACCEPT = both pass. REJECT = either fails → escalate to full re-run (user decision).

## Sample (Step 1–2)

Deterministic stratified sample, `scripts/sample_stratified.py --img-dir eval-infra/01-omnidocbench/data/images --per-category 9 --seed 42`:

- `tmp_sample81.txt` — 130 stems, sha256 `01186a281cb045339761b892435a3098046fe5443600c49942a1edf1595cf780`
- `tmp_sample81_gt.json` — 130-page GT subset of `data/OmniDocBench.json`, sha256 `05dea39c34b4424aecc503c357e45a3525a7e802216f1ec2794f813ba1d5e3ce`

Real category counts (recorded as required; the brief's "~81 pages" assumed ~9 categories, the dataset actually has 15 strata — 14 filename prefixes plus the 296 `page-<uuid>` hard-subset images, which the script groups into one `page` stratum via the documented `-` fallback; 15 × 9 with two strata rounding to 8/6 → **130 pages**):

```
images: 1651  categories: 15  per_category: 9  seed: 42
category           total stride picked
PPT                  108     12      9
book                  72      8      9
color                 42      5      9
docstructbench       170     19      9
eastmoney             53      6      9
exam                  70      8      9
jiaocai               12      2      6
jiaocaineedrop       214     24      8
magazine              42      5      9
newspaper            151     17      9
notes                116     13      9
page                 296     33      9
scihub                39      5      8
yanbaopptmerge       159     18      9
yanbaor2             107     12      9
sample pages: 130
```

CJK/bracket spot-check (per B1 concern): the sample includes **16 CJK-named pages and 1 bracket-named page**, including B1's exact smoke troublemaker `book_en_[陈剑炀#20][HTML5 Canvas].2011.英文版_page_208`. All sorted/copied with ordinal (codepoint) ordering in Python — no PowerShell culture-aware sort involved.

## Incident during Step 3 (honest record)

The first inference attempt (started 08:06) ran 200–450 s/page instead of the expected 9–29 s/page, and a direct torch probe **crashed inside MIOpen** with:

```
MIOpen(HIP): Warning [TryLockOperation] File <"C:\Users\rocm\.miopen\db\miopen-lockfiles\gfx1151_20.HIP.3_5_1_98f923c854.ufdb.txt.lock"> timed lock timed out.
... MIOpen.dll!miopen::RamDb::StoreRecord ... miopenFindConvolutionForwardAlgorithm (abort)
```

Root cause: the machine suffered an **unclean shutdown on 2026-08-01 20:35** (System log Event 41, Kernel-Power; LastBoot 20:35:05), leaving MIOpen's 35 MB user find-db (`~/.miopen/db/gfx1151_20.HIP.3_5_1_98f923c854.ufdb.txt`) corrupted — every convolution algorithm lookup paid a lock timeout and `StoreRecord` aborted on write. Recovery: killed the degraded run, deleted the user find-db + stale lock files (a pure cache; MIOpen rebuilds it), and re-probed:

```
first conv (full MIOpen find): 14.2s   steady conv: 15.88 ms/iter
matmul 4096^3: 59.8 ms/iter  2.30 TFLOPS
PROBE OK
```

The 4 pages produced by the degraded attempt were **discarded**; all 130 repro pages below come from the post-recovery run (started 08:36:05). Adapter source was verified byte-identical to the original full run (`git diff 3298b98f..HEAD -- src/mineru_rocm/` in MinerU-ROCm is empty), so the incident did not affect which code produced the numbers.

## Step 3 — sample re-inference (GPU, py3.12 env)

`mineru-win-rocm/python.exe adapters/mineru/run_adapter.py --backend pipeline --platform windows-hip --img-dir tmp_sample81_images --out-dir predictions/mineru_sample81_repro --skip-existing`

- `_run_stats.json`: **ok=130, fail=0, fallback=0** (count=130)
- Wall clock: 08:36:05 → 09:43:51 = **67.8 min**; per-page mean 31.3 s, max 190.0 s, min 0.87 s (includes the one-time MIOpen find-db rebuild across new shapes; the original full run processed the same 130 pages in 41.0 min, mean 18.9 s)

## Step 4 — Metric A: page-by-page comparison

`scripts/compare_prediction_sets.py --a predictions/mineru_pipeline --b predictions/mineru_sample81_repro --stems tmp_sample81.txt` (machine-readable: `tmp_sample81_compare.json`, gitignored):

```
pages compared : 130   missing: 0/0
EXACT_MATCH    : 103/130 = 0.7923
MEAN_RATIO     : 0.999471
MIN_RATIO      : 0.984348
```

| worst divergences (top 5 of 27 non-exact) | ratio |
|---|---:|
| color_textbook_zhonggaokao_小学_13.人教新起点英语…page_011 | 0.9843 |
| exam_paper_2004-2019上海高考英语听力原文和答案_page_050 | 0.9850 |
| PPT_EnglishtoAmericanTransition_page_003 | 0.9894 |
| jiaocaineedrop_jiaocai_needrop_en_383 | 0.9938 |
| notes_f7f010b78016aeebd76e56d9283eb67f_24 | 0.9952 |

Divergences are token-level OCR nondeterminism (formula spacing, punctuation, single-token flips) — expected under GPU algorithm-choice variation.

**Metric A: PASS** — exact-match 79.23% < 90%, but mean ratio **0.999471 ≥ 0.98** (the gate's OR condition).

## Step 5 — Metric B: sample-set scoring both ways (non-CDM)

Scorer note: `end2end_dataset` iterates the GT manifest and scores a missing prediction as an *empty page* (its `filter` option only matches `page_attribute` equality), so both legs score against the 130-page `tmp_sample81_gt.json` with 130-file prediction dirs — `predictions/mineru_sample81_existing` (copied from `predictions/mineru_pipeline`) and `predictions/mineru_sample81_repro` (fresh). Configs: `eval-infra/01-omnidocbench/configs/v16-sample81.yaml` and `v16-sample81-mineru-repro.yaml`. Both runs matched 130/130 pages, 56 TEDS table samples each.

| metric (page-level aggregation) | existing | repro | abs diff | threshold | verdict |
|---|---:|---:|---:|---:|---|
| text Edit-distance ↓ | 0.074207 | 0.074097 | **0.000110** | ≤ 0.01 | PASS |
| reading-order Edit-distance ↓ | 0.163103 | 0.163103 | 0.000000 | — | — |
| table TEDS (0-100) ↑ | 87.569325 | 87.554759 | **0.014566 pp** | ≤ 2 pp | PASS |
| display-formula Edit-distance ↓ | 0.273740 | 0.273740 | 0.000000 | — | — |

**Metric B: PASS.**

## Step 7 — cross-check: local metric_result vs model card (tolerance 1e-6)

`eval-infra/01-omnidocbench/OmniDocBench/result/mineru_pipeline_quick_match_metric_result.json` vs `MinerU-ROCm/model_card.pipeline.windows-hip.json` submetrics:

| submetric | model_card | metric_result | abs_diff | verdict |
|---|---:|---:|---:|---|
| text_edit_dist | 0.056546675035678 | 0.056546675035678 | 0.000e+00 | PASS |
| reading_order_edit_dist | 0.153138390539620 | 0.153138390539620 | 0.000e+00 | PASS |
| table_teds_percent | 82.038330964202771 | 82.038330964202771 | 0.000e+00 | PASS |
| formula_cdm_percent | 83.390812551752973 | 83.390812551752973 | 0.000e+00 | PASS |

CROSS-CHECK PASS (tolerance 1e-06). Model card: overall 86.59, backend pipeline, eval_date 2026-07-23. Mapping: text/RO use `all.Edit_dist.ALL_page_avg`; TEDS/CDM use `page.*.ALL × 100` (OmniDocBench official page-level aggregation convention).

## Verdict

**ACCEPT** — Metric A PASS (mean ratio 0.999471 ≥ 0.98), Metric B PASS (text diff 0.000110 ≤ 0.01; TEDS diff 0.014566 pp ≤ 2 pp), cross-check PASS. The existing 1651-page MinerU pipeline GPU results (Overall 86.59 / text 0.05655 / RO 0.15314 / TEDS 82.04 / CDM 83.39) stand; B3 may cite them.

## Reproduce

```powershell
# sample + GT subset + image copies (deterministic; regenerates all tmp_sample81* artifacts)
python scripts/sample_stratified.py --img-dir eval-infra/01-omnidocbench/data/images `
  --per-category 9 --seed 42 --out tmp_sample81.txt --copy-to tmp_sample81_images `
  --gt-manifest eval-infra/01-omnidocbench/data/OmniDocBench.json --gt-out tmp_sample81_gt.json
# fresh inference (GPU env), then comparison
C:\Users\rocm\miniconda3\envs\mineru-win-rocm\python.exe adapters\mineru\run_adapter.py `
  --backend pipeline --platform windows-hip `
  --img-dir tmp_sample81_images --out-dir predictions\mineru_sample81_repro --skip-existing
python scripts/compare_prediction_sets.py --a predictions/mineru_pipeline `
  --b predictions/mineru_sample81_repro --stems tmp_sample81.txt
# copy sample stems from predictions/mineru_pipeline into predictions/mineru_sample81_existing, then:
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-sample81-mineru-repro.yaml
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-sample81.yaml
```

`tmp_sample81*` artifacts are gitignored scratch (`.gitignore: tmp_*`); the two configs reference `tmp_sample81_gt.json` at repo root, regenerated by the first command.
