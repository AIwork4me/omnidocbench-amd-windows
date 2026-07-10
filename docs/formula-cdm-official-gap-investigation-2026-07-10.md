# Formula CDM Official Gap Investigation

Date: 2026-07-10

## Scope

Text Edit-distance, Reading-order Edit-distance, and Table TEDS from the
PaddleOCR official engine are treated as accepted. This note focuses on the
remaining Formula CDM gap versus the public PaddleOCR-VL-1.6 OmniDocBench v1.6
target.

The run under investigation is the official PaddleOCRVL doc_parser path with
evaluation-oriented Markdown (`pretty=False`) on the AMD Windows + llama.cpp
GGUF serving path:

- Predictions: `predictions/paddleocr_official_prettyfalse_full_2026-07-09`
- Scoring config: `eval-infra/01-omnidocbench/configs/v16-cdm-official-prettyfalse-full-2026-07-09.yaml`
- Result save name: `paddleocr_official_prettyfalse_full_2026-07-09_quick_match`

## Score Evidence

| Run | Overall | Text Edit-distance | Reading-order Edit-distance | Table TEDS | Formula CDM |
|---|---:|---:|---:|---:|---:|
| Public PaddleOCR-VL-1.6 target | 96.33 | 0.035 | 0.129 | 94.64 | 97.49 |
| Official engine, pre determinant fix | 95.8116 | 0.03447 | 0.12929 | 94.2187 | 96.6629 |
| Official engine, post determinant fix | 95.8600 | 0.03446 | 0.12929 | 94.2187 | 96.8074 |

Notes:

- Formula CDM in the table uses the notebook/page reporting convention from
  `*_run_summary.json`, matching the public target table.
- The post-fix `metric_result.json` sample/all Formula CDM is
  `0.9666857993197283`; the notebook/page Formula CDM is
  `96.80744451700869`.
- Remaining gap to public Formula CDM target: `97.49 - 96.8074 = 0.6826`
  notebook points.

Verification:

- `eval-infra/03-scoring/verify.ps1 -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match` passed.
- CDM stage processed `2352` formula samples with `0` CDM errors,
  `0` exceptions, and `0` timeouts.
- The adapter run still has `1651` pages total, `1650` ok, `1` VLM 500 failure.
  The failed page is not a major Formula CDM contributor in this result.

## Fixed Issue

Root-cause probe found a real evaluator-normalization issue for determinant
formulas where GT uses a vertical-bar wrapped array and prediction uses
`vmatrix`.

Example forms:

- GT: `\left|\begin{array}{...}...\end{array}\right|`
- Prediction: `\begin{vmatrix}...\end{vmatrix}`

Fix:

- Normalize determinant-style `| \begin{array} ... \end{array} |` to
  `\begin{vmatrix} ... \end{vmatrix}` before CDM rendering.
- Added regression coverage in the tracked OmniDocBench normalization patch.

Targeted probe improvement after the fix:

| Case | Before GT-vs-Pred CDM | After GT-vs-Pred CDM |
|---|---:|---:|
| `official-cdm-gap-0007` | 0.730 | 1.000 |
| `official-cdm-gap-0008` | 0.238 | 0.993 |
| `official-cdm-gap-0009` | 0.519 | 1.000 |
| `official-cdm-gap-0010` | 0.752 | 1.000 |

Full-set effect:

- Formula CDM improved from `96.6629` to `96.8074` in notebook/page reporting.
- This is a valid fix, but it explains only a minority of the remaining
  `0.6826` point gap to the public target.

## Post-Fix Low-Case Distribution

From the post-fix full-set `display_formula_result.json`:

- Formula samples: `2352`
- Sample/all Formula CDM: `96.6686%`
- `CDM == 0`: `14` samples
- `CDM < 0.5`: `54` samples
- `CDM < 0.8`: `95` samples
- `CDM < 0.95`: `241` samples
- Empty prediction formulas: `4` samples
- Low Edit but low CDM (`CDM < 0.8` and `Edit <= 0.15`): `7` samples
- Upper bound if all low-Edit/low-CDM samples were made perfect:
  `0.2614` sample-percentage points

## Post-Fix Probe Attribution

Artifacts:

- `docs/formula-cdm-official-gap-cases-2026-07-10.json`
- `docs/formula-cdm-official-gap-probe-2026-07-10.json`
- `docs/formula-cdm-official-gap-probe-2026-07-10-postfix.json`

Selected-case attribution after the determinant fix:

| Failure class | Count | Selected-case deficit |
|---|---:|---:|
| `model_or_dataset_gap` | 15 | 13.019 |
| `normalization_or_matching` | 5 | 4.948 |
| `pred_latex_unrenderable` | 5 | 5.000 |
| `extraction_or_matching` | 4 | 4.000 |
| `pending` / controls / fixed determinant cases | 10 | 1.919 |
| `evaluator_gt_compat` | 0 | 0.000 |

Interpretation:

- GT self-CDM is clean on the selected hard cases; there is no evidence for a
  broad GT/evaluator compatibility failure.
- The determinant issue was real and is fixed.
- Remaining zero/low cases are dominated by prediction-side issues:
  malformed LaTeX, empty/missed formulas, wrong formula matched, or content that
  is visibly different from GT.
- Additional probes for `\lefteqn` and `\overbrace` did not recover
  pred self-CDM or GT-vs-Pred CDM, so these are not yet clean evaluator fixes.

## Main Root Cause

The remaining Formula CDM gap is primarily caused by VLM/model-output and
formula extraction/matching differences on the AMD Windows llama.cpp/GGUF path,
not by a broad CDM evaluator failure.

Evidence:

- Full CDM run has no CDM errors, exceptions, or timeouts.
- GT self-CDM is `1.0` on the targeted hard cases.
- Prediction self-CDM failures are concentrated in malformed or structurally
  damaged prediction LaTeX.
- Empty formulas and wrong/mismatched formulas remain.
- The local serving path is llama.cpp/GGUF, while the public reference path is
  Linux vLLM-style serving; these paths are not parameter-identical, especially
  around VLM image/crop handling.

## Next Action

Do not rewrite GT and do not tune scores.

Recommended next experiment:

1. Run the same official PaddleOCRVL adapter against a Linux vLLM endpoint on
   the post-fix hard subset.
2. Compare hard-subset Formula CDM and pred self-CDM against the local
   llama.cpp/GGUF path.
3. If vLLM closes most of the remaining gap, document vLLM/BF16 as the
   reference-quality path and keep AMD Windows llama.cpp/GGUF as the validated
   local path.
4. Only add more scorer fixes when pair-probe proves a valid LaTeX construct
   fails self-CDM and a minimal normalization restores it without changing
   formula meaning.
