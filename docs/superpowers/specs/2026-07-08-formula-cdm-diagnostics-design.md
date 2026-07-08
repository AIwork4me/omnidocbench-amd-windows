# Formula CDM Evidence-Driven Diagnosis Design

Date: 2026-07-08
Status: Ready for implementation planning

## Goal

Turn the remaining PaddleOCR-VL-1.6 Formula CDM gap from a score-chasing problem into a reproducible root-cause investigation.

The next implementation must produce durable evidence for low Formula CDM cases on OmniDocBench v1.6 by:

- preserving the current CDM normalization fixes as a tracked, reproducible patch;
- generating a fixed Formula CDM hard-case subset;
- probing every selected case with GT-to-GT, Pred-to-Pred, and GT-to-Pred CDM;
- comparing the current lightweight adapter against the official PaddleOCR `PaddleOCRVL` doc_parser path on the same subset;
- writing a root-cause report that says what should be fixed next.

The success gate for this project slice is attribution closure. A Formula CDM score increase is welcome but not required.

## Current Evidence

The current latest complete CDM result is:

- Run summary: `\\wsl$\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_run_summary.json`
- Metric result: `\\wsl$\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_metric_result.json`
- Formula samples: `\\wsl$\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_display_formula_result.json`

Latest notebook-style values:

| Metric | Current | Official PaddleOCR-VL-1.6 | Gap |
|---|---:|---:|---:|
| Overall | 95.2326 | 96.33 | -1.0974 |
| Text Edit-distance | 0.033970 | 0.033 | +0.000970 |
| Formula CDM | 94.7731 | 97.49 | -2.7169 |
| Table TEDS | 94.3216 | 94.76 | -0.4384 |
| Reading-order Edit-distance | 0.128325 | 0.127 | +0.001325 |

The current prediction directory contains 1651 Markdown files. `_run_stats.json` reports 1649 successful pages and two VLM 500 failures:

- `book_zh_GB12082006_extracted_page_8.png`
- `newspaper_The Times UK_0801@magazinesclubnew_page_031.png`

The VLM server was not running during planning, so any official/lightweight subset inference must start the server and pause at the existing human GPU confirmation point.

## Existing Fixes To Preserve

The following CDM compatibility fixes already exist inside the ignored OmniDocBench checkout and the WSL mirror. They must become reproducible from tracked repo files:

- Prediction-side alternate CDM candidate generation removes unmatched leading `\left|` while preserving valid paired `\left|...\right|`.
- `\overrightarrow` is normalized to `\vec` for both GT and prediction CDM compatibility.
- Empty array column specs such as `\begin{array}{}` are sanitized to a renderable single-column spec when the formula is already identified as a CDM compatibility case.
- The broad GT matrix rewrite experiment must not be restored; it reduced Formula CDM and is explicitly out of scope.

The tracked source of truth should be a patch file under `eval-infra/01-omnidocbench/patches/`, not direct committed contents under the ignored generated checkout.

## User-Approved Direction

The next mainline is `CDM evidence diagnosis`, not immediate parameter tuning or full official adapter defaulting.

The deliverable level is `tools + report`: the repo should gain reusable diagnostics and a written root-cause report, not just a one-off notebook or temporary script.

The acceptance criterion is `attribution closure`: if the evidence shows the remaining gap comes from the adapter/model path rather than the scorer, this project slice can still be complete.

## Architecture

### Patch Installation

Add a tracked patch:

```text
eval-infra/01-omnidocbench/patches/0001-formula-cdm-normalization.patch
```

Both setup paths must apply it idempotently:

- Windows checkout: `eval-infra/01-omnidocbench/setup.ps1`
- WSL native checkout: `eval-infra/02-cdm-environment/setup.sh`

The patch application must be safe to re-run. A setup script should skip it when the target already contains the expected patched behavior and fail clearly if the target source has drifted so much that the patch cannot apply.

### Diagnostics CLI

Add one repository-owned CLI:

```text
eval-infra/03-scoring/formula_cdm_diagnostics.py
```

It exposes three subcommands:

```powershell
python eval-infra\03-scoring\formula_cdm_diagnostics.py make-hard-cases
python eval-infra\03-scoring\formula_cdm_diagnostics.py pair-probe
python eval-infra\03-scoring\formula_cdm_diagnostics.py report
```

`make-hard-cases` reads the latest or specified `*_display_formula_result.json`, selects at most 50 formula cases, writes the hard-case JSON, writes a page-level OmniDocBench manifest, and copies existing prediction Markdown into a hard-subset prediction directory.

`pair-probe` runs CDM on each selected formula in three directions:

- GT to GT
- Pred to Pred
- GT to Pred

It writes probe metrics, token counts, and an initial failure classification.

`report` combines hard cases, pair probes, run summary values, prediction stats, and optional official/lightweight subset stats into a Markdown report.

### Output Files

The implementation writes these fixed outputs:

```text
docs/formula-cdm-hard-cases-2026-07-08.json
docs/formula-cdm-hard-cases-2026-07-08-probe.json
docs/formula-cdm-root-cause-report-2026-07-08.md
eval-infra/01-omnidocbench/data/OmniDocBench_formula_cdm_hard.json
predictions/paddleocrvl_rocm_formula_cdm_hard/
```

The data and predictions directories are generated and remain gitignored. The docs outputs are tracked diagnostic artifacts.

### CDM Hard Config

Add:

```text
eval-infra/01-omnidocbench/configs/v16-cdm-formula-hard.yaml
```

It must use:

- GT manifest: `<REPO_ROOT>/eval-infra/01-omnidocbench/data/OmniDocBench_formula_cdm_hard.json`
- Prediction directory: `<REPO_ROOT>/predictions/paddleocrvl_rocm_formula_cdm_hard`
- Match method: `quick_match`
- CDM enabled for `display_formula`

The save name must be distinct from the full run, so hard-subset scoring never overwrites `paddleocrvl_rocm_cdm_quick_match_*`.

### Adapter Engines For Subset Comparison

`adapters/paddleocr-vl-1.6/run_adapter.py` must support:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py --engine lightweight ...
python adapters\paddleocr-vl-1.6\run_adapter.py --engine official ...
```

For this project slice:

- `lightweight` preserves current ONNX layout plus llama.cpp behavior.
- `official` uses `from paddleocr import PaddleOCRVL`, `pipeline_version="v1.6"`, `vl_rec_backend="llama-cpp-server"`, and the configured server URL/model name.
- The official path is used only for subset diagnosis in this slice. README reference scores are not updated until a full-set official run exists.

## Hard-Case Selection

The hard-case set is capped at 50 formula samples.

Selection priority:

1. `CDM == 0`
2. `CDM < 0.5` and `Edit_dist <= 0.15`
3. Empty or missing prediction formula
4. Cases suspected to have GT self-CDM or tokenization failure
5. A small number of high-CDM control samples

Every case must include:

```json
{
  "case_id": "cdm-0001",
  "idx": 189,
  "img_id": "page.png",
  "image_name": "page.png",
  "gt_idx": [0],
  "pred_idx": [0],
  "gt": "...",
  "pred": "...",
  "edit": 0.0303,
  "cdm": 0.0,
  "gt_cdm": "...",
  "pred_cdm": "...",
  "pred_cdm_alt": "...",
  "selection_reason": "cdm_zero",
  "failure_class": "pending"
}
```

If the source result file lacks a value, use `null` in JSON rather than inventing data.

## Failure Classes

The final report must use these exact class names:

- `evaluator_gt_compat`: GT-to-GT is zero or `gt_tokens == 0`.
- `pred_latex_unrenderable`: GT-to-GT is healthy, but Pred-to-Pred is zero or `pred_tokens == 0`.
- `normalization_or_matching`: GT and Pred self-probes are healthy, but GT-to-Pred remains low while Edit-distance is low.
- `extraction_or_matching`: prediction is empty, missing, or clearly a wrong formula match.
- `lightweight_adapter_or_llama`: official subset output is materially better than lightweight output on the same cases.
- `model_or_dataset_gap`: official and lightweight are both low while scorer self-probes are healthy.
- `pending`: classification cannot be proven from available artifacts yet.

The implementation may add an internal helper class or enum, but report output must preserve these exact strings.

## Validation

Required validation commands:

```powershell
git diff --check
$env:PYTHONPATH='.'
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' tests\test_formula_cdm_normalization.py
wsl -d Ubuntu2204 bash -lc "cd /root/OmniDocBench && PYTHONPATH=. /root/odb-venv/bin/python tests/test_formula_cdm_normalization.py"
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_formula_cdm_diagnostics.py -q
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 -SaveName paddleocrvl_rocm_cdm_quick_match
```

Full CDM rerun command:

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh
```

Hard subset CDM command:

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh v16-cdm-formula-hard.yaml
```

The VLM server setup remains a human-intervention point. If setup starts the server, pause and show exactly:

```text
⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.
```

## Out Of Scope

- Updating README public reference scores from subset-only evidence.
- Declaring official `doc_parser` the default full reference path before full-set scoring evidence exists.
- Large-scale GT rewrites to chase score.
- Changing final metric values directly.
- Running CDM Windows-native.
- Deleting generated prediction or dataset directories.

## Open Risks

- `eval-infra/01-omnidocbench/OmniDocBench/` is ignored; current CDM fixes may be lost unless the patch is correctly applied during setup.
- Official PaddleOCR subset inference requires the VLM server and may be slow or blocked by server startup.
- Pair-probe CDM is WSL-oriented because CDM requires POSIX tooling; Windows tests should cover selection/report logic without executing CDM rendering.
- Existing untracked debug files and downloaded llama archives should not be modified or removed during implementation.
