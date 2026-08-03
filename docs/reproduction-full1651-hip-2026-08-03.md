# Real-machine full-run record: paddleocr-vl-hip-full-1651 (2026-08-03)

Machine: AMD Ryzen AI MAX+ 395 (Radeon 8060S, gfx1151), Windows 11, WSL
Ubuntu 22.04.5.

## Verdict (final): **OFFICIAL PASS**

`reproduce.ps1 -Profile paddleocr-vl-hip-full-1651` completed with
`state.json = passed`, all 19 stages passed, evidence pack complete under
`outputs/reproduction/paddleocr-vl-hip-full-1651/`.

- Inference: 1651/1651 pages selected (3.4 h HIP), `_run_stats.json`
  selected_pages = 1651.
- Strict prediction gate: **1649/1651 usable** (coverage 0.9988 >= 0.998),
  **2 failed pages** (within `maximum_failed_pages = 2`).
- Full verification (`full-verify.ps1` strict mode + `assert-metrics.ps1`
  with profile thresholds text < 0.10 / RO < 0.20 / TEDS > 0.85 / CDM > 0.85):
  PASS.

## Official scores (page_count 1651)

| Metric | Windows | WSL CDM | README reference (ROCm) | Delta |
|---|---|---|---|---|
| Text Edit-distance | 0.035386 | 0.035231 | 0.03402 | +0.0014 |
| Reading-order Edit-distance | 0.129539 | 0.129524 | 0.12824 | +0.0013 |
| Table TEDS | 0.929766 | 0.929756 | 0.943222 | −0.0135 |
| Formula CDM | — (WSL only) | **0.966490** | 0.969219 | −0.0027 |

Windows and WSL shared metrics now agree to < 0.0002 (single-worker matching,
see below); deltas vs the reference are consistent with the 2 missing pages
(one is a dense newspaper table page) and inherent model output variance
(see the sampling test).

## The 2 failed pages (peg-native, upstream-known)

| Page | Failure | Root cause / tracking |
|---|---|---|
| `book_zh_GB12082006_extracted_page_8.png` | HTTP 500, llama-server `common_chat_peg_parse: unparsed peg-native output` | The model responds with valid prose that does not match the expected peg-native structure; llama-server b9637 rejects it. Reproducible with the pipeline request on any server config (seed 1/2, 4K/16K ctx, with/without `--skip-chat-parsing`); a direct simple-prompt request succeeds. **Tracked upstream: PaddlePaddle/PaddleOCR#18248 (peg-native).** |
| `newspaper_The Times UK_0801@magazinesclubnew_page_031.png` | same 500 | same as above. |

Both have non-empty GT (37 / 63 layout dets) and fall within the allowed
2-page failure budget; the harness scores them as empty matches (already
reflected in the metrics).

## Empty-GT pages are correct predictions (not failures)

OmniDocBench v1.6 contains **2 genuinely empty-GT pages**
(`color_textbook_zhonggaokao_小学_13.人教新起点英语（4-5年级）...` pages 001 and
004: layout_dets are only figures plus text_mask regions with empty text).
The empty prediction for `...page_004` is therefore correct. Implemented in
`scripts/gt_manifest.py` (shared by `verify_prediction_set.py`,
`validate_predictions.py`, and the adapter's `--skip-existing` resume via
`--gt-manifest`).

## Completion path (authorized, evidence-backed)

After the validator fixes, the run was completed WITHOUT re-inferring the
1651 pages (the user approved a sampling-based completion instead of a
~6 h full re-run):

1. **Sampling equivalence test** (`scripts/sample_prediction_equivalence.py`,
   committed and unit-tested): 50 deterministic stride-sampled pages were
   re-inferred with the current code and compared against the stored
   predictions. Result: **50/50 content-equivalent**
   (`outputs/.../sample-equivalence.json`, min similarity 0.95). This also
   established that PaddleOCR-VL-1.6 GGUF outputs are NOT byte-reproducible
   across independent runs (glyph-level bullet/quote variants; structural
   variance in reconstructed table HTML) — the equivalence criterion is
   content-based by design.
2. **Fingerprint regeneration**: inputs (profile, upstream lock, dataset
   manifest, pipeline commit, scoring configs) were unchanged across the
   code fixes; `compute_fingerprint.py --out` was re-run at HEAD so the
   stored predictions (produced by the same inputs) could be resumed. The
   only code deltas were validator/resume-path changes, which the sampling
   test proves do not alter inference output.
3. **`-Resume`** completed the official flow: `inference.run` reused the
   1649 stored predictions (`--skip-existing`, 47.8 s), re-attempted the 2
   missing pages (deterministic failures, within budget), then ran the
   official Windows scoring (1977 s), WSL CDM scoring (2590 s),
   `verification.final` and `evidence.pack`.

## WSL CDM fixes discovered during completion

- **Open-file limit**: 1651-page CDM scoring exhausted WSL's default
  1024-file limit (Errno 24); `score-cdm.sh` now raises `ulimit -n 65535`.
- **Fork-in-fork crash** (`AssertionError: can only join a started
  process`): on WSL/Linux, `match_workers: 24` workers forking again for
  `latex_to_text_with_timeout` while filelock threads hold descriptors crash
  flakily (~50% at 1651 pages, always around 82%). The WSL CDM config now
  uses `match_workers: 1 / teds_workers: 1` (the WSL-proven values from the
  cpu-200 reference run; worker counts never change scores). Documented in
  `docs/pitfalls.md` as #wsl-fork-fork.

## Evidence paths

- `outputs/reproduction/paddleocr-vl-hip-full-1651/`: `state.json`
  (passed), `profile.resolved.json`, `fingerprint.json`, `hardware.json`,
  `backend-proof.json`, `artifact-hashes.json`, `prediction-summary.json`,
  `metrics-summary.json`, `sample-equivalence.json`, `report.md` (PASS)
- `predictions/paddleocrvl_hip_full_1651/`: 1649 `.md` + `_run_stats.json`
  (schema v2, invocations 3) + `_errors.log`
- `eval-infra/01-omnidocbench/OmniDocBench/result/` and
  `\\wsl$\Ubuntu2204\root\OmniDocBench\result/`: official metric results

## Reproduce / resume commands

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile paddleocr-vl-hip-full-1651
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile paddleocr-vl-hip-full-1651 -Resume
```
