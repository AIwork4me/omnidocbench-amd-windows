# Formula CDM Evidence Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` if explicitly authorized for subagents, otherwise use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible Formula CDM hard-case diagnostics pipeline that preserves existing CDM compatibility fixes, generates evidence-backed hard cases, runs GT/Pred CDM probes, and reports root-cause attribution.

**Architecture:** Keep generated OmniDocBench and prediction contents ignored, but make all behavior reproducible through tracked patches, configs, scripts, tests, and diagnostic docs. Add a focused Python CLI under `eval-infra/03-scoring/` for hard-case selection, CDM pair probing, and report generation. Extend the PaddleOCR-VL adapter with explicit `official` and `lightweight` engines only for controlled subset comparison in this project slice.

**Tech Stack:** Windows PowerShell 5.1-compatible scripts, WSL Ubuntu2204 for CDM, Python 3.10/3.11, pytest, OmniDocBench `src.metrics.cdm.cdm.cdm_metrics`, PaddleOCR `3.6.0`, llama.cpp OpenAI-compatible server.

## Global Constraints

- CDM execution remains WSL-only; Windows-native code may select cases and generate reports but must not run formula rendering CDM.
- Do not edit or commit generated OmniDocBench checkout files directly; preserve scorer changes through tracked patches and idempotent setup application.
- Do not update README reference scores from subset-only evidence.
- Do not make broad GT rewrites or mutate final scores to chase points.
- Keep existing untracked files such as `AGENTS.md`, `cdm_debug.py`, `cdm_diag.py`, `docs/handoff-2026-07-08-formula-cdm.md`, and downloaded llama archives untouched unless explicitly requested.
- VLM server startup remains a human intervention point and must show the exact GPU confirmation message before continuing.

---

## File Structure

- `eval-infra/01-omnidocbench/patches/0001-formula-cdm-normalization.patch`: tracked patch containing existing Formula CDM compatibility fixes and the normalization regression test.
- `eval-infra/01-omnidocbench/setup.ps1`: applies the patch idempotently to the Windows OmniDocBench checkout.
- `eval-infra/02-cdm-environment/setup.sh`: applies the same patch idempotently to `/root/OmniDocBench` after the WSL copy exists.
- `eval-infra/01-omnidocbench/configs/v16-cdm-formula-hard.yaml`: CDM-enabled hard-subset scoring config.
- `eval-infra/03-scoring/formula_cdm_diagnostics.py`: hard-case selection, pair-probe, and report CLI.
- `tests/test_formula_cdm_diagnostics.py`: fast unit tests for selection, manifest generation, classification, and report behavior.
- `adapters/paddleocr-vl-1.6/run_adapter.py`: explicit `--engine official|lightweight` dispatcher for subset comparison.
- `tests/test_paddleocr_vl_adapter.py`: focused adapter dispatch/export tests.
- `docs/formula-cdm-hard-cases-2026-07-08.json`: generated diagnostic hard-case artifact.
- `docs/formula-cdm-hard-cases-2026-07-08-probe.json`: generated pair-probe artifact.
- `docs/formula-cdm-root-cause-report-2026-07-08.md`: generated attribution report.

---

## Task 1: Preserve Formula CDM Normalization As A Tracked Patch

**Files:**
- Create: `eval-infra/01-omnidocbench/patches/0001-formula-cdm-normalization.patch`
- Modify: `eval-infra/01-omnidocbench/setup.ps1`
- Modify: `eval-infra/02-cdm-environment/setup.sh`
- Source generated files to diff from:
  - `eval-infra/01-omnidocbench/OmniDocBench/src/core/preprocess/formula_cdm.py`
  - `eval-infra/01-omnidocbench/OmniDocBench/tests/test_formula_cdm_normalization.py`

**Interfaces:**
- Produces tracked patch file applied by both setup scripts.
- Produces setup behavior that leaves `build_matrix_cdm_variants()` and `sanitize_formula_for_cdm()` available in both Windows and WSL checkouts.

- [ ] **Step 1: Generate the patch from current ignored checkout state**

Run:

```powershell
New-Item -ItemType Directory -Force -Path eval-infra\01-omnidocbench\patches | Out-Null
git -C eval-infra\01-omnidocbench\OmniDocBench diff -- `
  src/core/preprocess/formula_cdm.py `
  tests/test_formula_cdm_normalization.py `
  > eval-infra\01-omnidocbench\patches\0001-formula-cdm-normalization.patch
```

If the generated patch is empty, inspect the ignored checkout and WSL mirror before proceeding; the existing fixes may not be present.

- [ ] **Step 2: Add patch-application tests by command-level verification**

Run:

```powershell
Select-String -Path eval-infra\01-omnidocbench\patches\0001-formula-cdm-normalization.patch -Pattern "pred_cdm_alt","overrightarrow","test_sanitize_formula_fixes_empty_array_column_spec"
```

Expected: all three patterns appear.

- [ ] **Step 3: Implement idempotent Windows setup patching**

In `eval-infra/01-omnidocbench/setup.ps1`, after the OmniDocBench clone is present and before venv setup, add logic equivalent to:

```powershell
$patchDir = Join-Path $PSScriptRoot "patches"
$formulaPatch = Join-Path $patchDir "0001-formula-cdm-normalization.patch"
if (Test-Path $formulaPatch) {
    $formulaFile = Join-Path $odbDir "src\core\preprocess\formula_cdm.py"
    $patched = $false
    if (Test-Path $formulaFile) {
        $formulaText = Get-Content -Raw -LiteralPath $formulaFile -Encoding UTF8
        $patched = (
            $formulaText -match "pred_cdm_alt" -and
            $formulaText -match "\\\\overrightarrow" -and
            $formulaText -match "_EMPTY_ARRAY_SPEC_RE"
        )
    }
    if ($patched) {
        Write-Host "Formula CDM normalization patch already applied." -ForegroundColor Green
    } else {
        Write-Host "Applying Formula CDM normalization patch ..." -ForegroundColor Cyan
        git -C $odbDir apply --check $formulaPatch
        if ($LASTEXITCODE -ne 0) { throw "Formula CDM normalization patch does not apply cleanly. Inspect $formulaPatch and $formulaFile." }
        git -C $odbDir apply $formulaPatch
        if ($LASTEXITCODE -ne 0) { throw "Formula CDM normalization patch failed." }
        Write-Host "Formula CDM normalization patch applied." -ForegroundColor Green
    }
}
```

- [ ] **Step 4: Implement idempotent WSL setup patching**

In `eval-infra/02-cdm-environment/setup.sh`, after `$ODB_LOCAL` exists and before Step 9 dependencies, add logic equivalent to:

```bash
FORMULA_PATCH="$REPO_ROOT/eval-infra/01-omnidocbench/patches/0001-formula-cdm-normalization.patch"
FORMULA_FILE="$ODB_LOCAL/src/core/preprocess/formula_cdm.py"
if [ -f "$FORMULA_PATCH" ]; then
    if grep -q "pred_cdm_alt" "$FORMULA_FILE" 2>/dev/null \
       && grep -q "\\\\overrightarrow" "$FORMULA_FILE" 2>/dev/null \
       && grep -q "_EMPTY_ARRAY_SPEC_RE" "$FORMULA_FILE" 2>/dev/null; then
        ok "Formula CDM normalization patch already present"
    else
        (cd "$ODB_LOCAL" && git apply --check "$FORMULA_PATCH") || fail "Formula CDM normalization patch check"
        (cd "$ODB_LOCAL" && git apply "$FORMULA_PATCH") || fail "Formula CDM normalization patch apply"
        ok "Formula CDM normalization patch applied"
    fi
fi
```

- [ ] **Step 5: Verify normalization tests**

Run:

```powershell
$env:PYTHONPATH='.'
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' tests\test_formula_cdm_normalization.py
wsl -d Ubuntu2204 bash -lc "cd /root/OmniDocBench && PYTHONPATH=. /root/odb-venv/bin/python tests/test_formula_cdm_normalization.py"
```

Expected: both commands exit `0`.

---

## Task 2: Add Formula CDM Diagnostics CLI With Tests

**Files:**
- Create: `eval-infra/03-scoring/formula_cdm_diagnostics.py`
- Create: `tests/test_formula_cdm_diagnostics.py`

**Interfaces:**
- Produces `select_hard_cases(samples: list[dict], limit: int = 50) -> list[dict]`.
- Produces `classify_probe(case: dict, probe: dict) -> str`.
- Produces CLI subcommands `make-hard-cases`, `pair-probe`, and `report`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_formula_cdm_diagnostics.py` with tests for:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "eval-infra" / "03-scoring" / "formula_cdm_diagnostics.py"


def load_module():
    spec = importlib.util.spec_from_file_location("formula_cdm_diagnostics", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample(idx, cdm, edit, pred="x", gt="x", img="page.png"):
    return {
        "gt_idx": [idx],
        "gt": gt,
        "pred_idx": [idx],
        "pred": pred,
        "edit": edit,
        "metric": {"CDM": cdm, "Edit_dist": edit},
        "img_id": img,
        "image_name": img,
        "gt_cdm": gt,
        "pred_cdm": pred,
        "pred_cdm_alt": "",
    }


def test_select_hard_cases_prioritizes_zero_and_close_low_cases():
    diag = load_module()
    samples = [
        sample(1, 0.99, 0.0),
        sample(2, 0.0, 0.4),
        sample(3, 0.4, 0.1),
        sample(4, 0.8, 0.2),
    ]

    cases = diag.select_hard_cases(samples, limit=3)

    assert [c["idx"] for c in cases] == [1, 2, 3]
    assert cases[0]["selection_reason"] == "control_high_cdm"
    assert cases[1]["selection_reason"] == "cdm_zero"
    assert cases[2]["selection_reason"] == "cdm_low_edit_close"


def test_classify_probe_detects_gt_compat_failure():
    diag = load_module()
    case = {"pred": "x", "edit": 0.02}
    probe = {"gt_self": {"F1_score": 0.0, "gt_tokens": 0}, "pred_self": {"F1_score": 1.0, "pred_tokens": 2}, "gt_pred": {"F1_score": 0.0}}

    assert diag.classify_probe(case, probe) == "evaluator_gt_compat"


def test_classify_probe_detects_prediction_render_failure():
    diag = load_module()
    case = {"pred": r"\bad", "edit": 0.02}
    probe = {"gt_self": {"F1_score": 1.0, "gt_tokens": 2}, "pred_self": {"F1_score": 0.0, "pred_tokens": 0}, "gt_pred": {"F1_score": 0.0}}

    assert diag.classify_probe(case, probe) == "pred_latex_unrenderable"


def test_write_page_manifest_filters_selected_pages(tmp_path):
    diag = load_module()
    full_manifest = [
        {"img_id": "a.png", "page_info": 1},
        {"img_id": "b.png", "page_info": 2},
    ]
    cases = [{"img_id": "b.png"}]
    out = tmp_path / "hard.json"

    count = diag.write_page_manifest(full_manifest, cases, out)

    assert count == 1
    assert json.loads(out.read_text(encoding="utf-8")) == [{"img_id": "b.png", "page_info": 2}]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_formula_cdm_diagnostics.py -q
```

Expected: fail because `formula_cdm_diagnostics.py` does not exist or functions are missing.

- [ ] **Step 3: Implement minimal diagnostics module**

Implement:

- JSON read/write helpers with UTF-8.
- `metric_value(sample, name)` to read `sample["metric"][name]`.
- `selection_reason(sample)` returning one of `cdm_zero`, `cdm_low_edit_close`, `prediction_empty`, `control_high_cdm`, or `None`.
- `select_hard_cases(samples, limit=50)` that includes up to five high-CDM controls first, then zero and low/edit-close cases in stable source order, with `case_id` assigned as `cdm-0001`.
- `write_page_manifest(full_manifest, cases, out_path)` filtering by `img_id` or `image_name`.
- `classify_probe(case, probe)` using the exact class names from the spec.
- CLI argument parsing for `make-hard-cases`, `pair-probe`, and `report`.

For `pair-probe`, import `cdm_metrics` lazily inside the subcommand so unit tests on Windows do not require CDM execution.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_formula_cdm_diagnostics.py -q
```

Expected: all tests pass.

---

## Task 3: Add Formula CDM Hard-Subset Scoring Config

**Files:**
- Create: `eval-infra/01-omnidocbench/configs/v16-cdm-formula-hard.yaml`

**Interfaces:**
- Consumed by `score-cdm.sh v16-cdm-formula-hard.yaml`.
- Reads generated manifest `OmniDocBench_formula_cdm_hard.json`.
- Reads generated prediction directory `predictions/paddleocrvl_rocm_formula_cdm_hard`.

- [ ] **Step 1: Create the config**

Add:

```yaml
# OmniDocBench v1.6 Formula CDM hard-case subset.
# Generated by eval-infra/03-scoring/formula_cdm_diagnostics.py make-hard-cases.
end2end_eval:
  metrics:
    text_block:      { metric: [Edit_dist] }
    display_formula: { metric: [Edit_dist, CDM], cdm_workers: 8 }
    table:           { metric: [TEDS, Edit_dist], teds_workers: 16 }
    reading_order:   { metric: [Edit_dist] }
  dataset:
    dataset_name: end2end_dataset
    ground_truth: { data_path: <REPO_ROOT>/eval-infra/01-omnidocbench/data/OmniDocBench_formula_cdm_hard.json }
    prediction:   { data_path: <REPO_ROOT>/predictions/paddleocrvl_rocm_formula_cdm_hard }
    match_method: quick_match
    match_workers: 8
```

- [ ] **Step 2: Verify config path rendering**

Run:

```powershell
Select-String -Path eval-infra\01-omnidocbench\configs\v16-cdm-formula-hard.yaml -Pattern "OmniDocBench_formula_cdm_hard","paddleocrvl_rocm_formula_cdm_hard","CDM"
```

Expected: all three patterns appear.

---

## Task 4: Add Explicit PaddleOCR-VL Adapter Engines

**Files:**
- Modify: `adapters/paddleocr-vl-1.6/run_adapter.py`
- Create: `tests/test_paddleocr_vl_adapter.py`

**Interfaces:**
- `run_adapter(img_dir, out_dir, server_url="", *, engine="lightweight", ...) -> dict`
- CLI option `--engine {lightweight,official}`
- `run_lightweight_folder(...)`
- `run_official_folder(...)`

- [ ] **Step 1: Write failing adapter tests**

Create tests that load `run_adapter.py` with `importlib`, monkeypatch `run_lightweight_folder` and `run_official_folder`, and assert:

- default engine is `lightweight` for backward compatibility in this project slice;
- explicit `engine="official"` dispatches to the official runner;
- `expected_md_name("scan.JPG") == "scan.md"`;
- `_official_result_to_markdown()` reads `.markdown` from a fake object.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_paddleocr_vl_adapter.py -q
```

Expected: fail because engine dispatch is not implemented.

- [ ] **Step 3: Implement adapter dispatcher**

Refactor current `process_folder()` into `run_lightweight_folder()` without changing its core behavior.

Add `run_official_folder()`:

- lazy import `from paddleocr import PaddleOCRVL`;
- instantiate `PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="llama-cpp-server", vl_rec_server_url=server_url, vl_rec_api_model_name=api_model_name)`;
- for each image, call `pipeline.predict(str(image_path))`;
- join each result object's `.markdown` value with blank lines;
- write `<stem>.md`;
- write `_run_stats.json` with `engine`, `count`, `ok`, `fail`, and per-page stats;
- append exceptions to `_errors.log`;
- exit code `2` if fewer than 50 percent of pages succeed.

Add CLI:

```powershell
--engine lightweight|official
```

Default remains `lightweight` until a full-set official run proves the README reference baseline.

- [ ] **Step 4: Run adapter tests and help smoke**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_paddleocr_vl_adapter.py -q
python adapters\paddleocr-vl-1.6\run_adapter.py --help
```

Expected: tests pass and help shows `--engine {lightweight,official}`.

---

## Task 5: Generate Hard Cases, Pair Probe, And Report

**Files:**
- Generate: `docs/formula-cdm-hard-cases-2026-07-08.json`
- Generate: `docs/formula-cdm-hard-cases-2026-07-08-probe.json`
- Generate: `docs/formula-cdm-root-cause-report-2026-07-08.md`
- Generate: `eval-infra/01-omnidocbench/data/OmniDocBench_formula_cdm_hard.json`
- Generate: `predictions/paddleocrvl_rocm_formula_cdm_hard/`

**Interfaces:**
- Consumes latest full CDM result JSON under `\\wsl$\Ubuntu2204\root\OmniDocBench\result`.
- Produces tracked diagnostic docs and ignored generated scoring inputs.

- [ ] **Step 1: Confirm no stale CDM process**

Run:

```powershell
wsl -d Ubuntu2204 bash -lc "ps -eo pid,ppid,stat,etime,cmd | grep -E 'pdf_validation|score-cdm|pdflatex|magick' | grep -v grep || true"
```

Expected: no active scoring processes.

- [ ] **Step 2: Re-run full CDM after the array fix**

Run:

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 -SaveName paddleocrvl_rocm_cdm_quick_match
```

Expected: verify exits `0` and all four metrics are present and non-zero.

- [ ] **Step 3: Generate hard cases and subset inputs**

Run:

```powershell
python eval-infra\03-scoring\formula_cdm_diagnostics.py make-hard-cases `
  --display-result "\\wsl$\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_display_formula_result.json" `
  --full-manifest eval-infra\01-omnidocbench\data\OmniDocBench.json `
  --source-predictions predictions\paddleocrvl_rocm_cdm `
  --cases-out docs\formula-cdm-hard-cases-2026-07-08.json `
  --manifest-out eval-infra\01-omnidocbench\data\OmniDocBench_formula_cdm_hard.json `
  --prediction-out predictions\paddleocrvl_rocm_formula_cdm_hard `
  --limit 50
```

Expected: hard-case JSON has at most 50 cases and the generated manifest includes the selected pages.

- [ ] **Step 4: Run pair probe in WSL**

Run:

```powershell
wsl -d Ubuntu2204 bash -lc "cd /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows && PYTHONPATH=/root/OmniDocBench /root/odb-venv/bin/python eval-infra/03-scoring/formula_cdm_diagnostics.py pair-probe --cases docs/formula-cdm-hard-cases-2026-07-08.json --probe-out docs/formula-cdm-hard-cases-2026-07-08-probe.json"
```

Expected: probe JSON contains `gt_self`, `pred_self`, `gt_pred`, and `failure_class` for each case.

- [ ] **Step 5: Score hard subset**

Run:

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh v16-cdm-formula-hard.yaml
```

Expected: result save name is based on `paddleocrvl_rocm_formula_cdm_hard_quick_match`, not the full run.

- [ ] **Step 6: Generate report**

Run:

```powershell
python eval-infra\03-scoring\formula_cdm_diagnostics.py report `
  --cases docs\formula-cdm-hard-cases-2026-07-08.json `
  --probe docs\formula-cdm-hard-cases-2026-07-08-probe.json `
  --run-summary "\\wsl$\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_run_summary.json" `
  --prediction-stats predictions\paddleocrvl_rocm\_run_stats.json `
  --report-out docs\formula-cdm-root-cause-report-2026-07-08.md
```

Expected: report includes current full metrics, hard-case counts by class, top recoverable cases, and a next-action recommendation.

---

## Task 6: Optional Official vs Lightweight Hard-Subset Adapter Comparison

**Files:**
- Generate: `predictions/paddleocrvl_rocm_formula_cdm_hard_lightweight/`
- Generate: `predictions/paddleocrvl_rocm_formula_cdm_hard_official/`
- Update: `docs/formula-cdm-root-cause-report-2026-07-08.md`

**Interfaces:**
- Consumes hard-case page images selected by Task 5.
- Uses `run_adapter.py --engine lightweight|official`.

- [ ] **Step 1: Start or verify VLM server**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
```

If setup starts the server, pause and show:

```text
⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.
```

- [ ] **Step 2: Materialize hard-case images**

The diagnostics CLI may create a temporary image directory from `OmniDocBench_formula_cdm_hard.json`; if not, create it under `%TEMP%\odb_formula_cdm_hard_images` by copying selected `img_id` files from `eval-infra\01-omnidocbench\data\images`.

- [ ] **Step 3: Run lightweight subset**

Run:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine lightweight `
  --img-dir "$env:TEMP\odb_formula_cdm_hard_images" `
  --out-dir predictions\paddleocrvl_rocm_formula_cdm_hard_lightweight
```

- [ ] **Step 4: Run official subset**

Run:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine official `
  --img-dir "$env:TEMP\odb_formula_cdm_hard_images" `
  --out-dir predictions\paddleocrvl_rocm_formula_cdm_hard_official
```

- [ ] **Step 5: Update report with subset comparison**

Run `formula_cdm_diagnostics.py report` again, passing optional stats paths for both subset output directories if implemented.

Expected: report says whether subset evidence points toward `lightweight_adapter_or_llama`, scorer compatibility, extraction/matching, or model/dataset gap.

---

## Task 7: Final Verification

**Files:**
- All files changed above.

**Interfaces:**
- Confirms docs, tests, configs, and generated diagnostics are coherent.

- [ ] **Step 1: Run diff whitespace check**

```powershell
git diff --check
```

Expected: no output, exit `0`.

- [ ] **Step 2: Run unit tests**

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_formula_cdm_diagnostics.py tests\test_paddleocr_vl_adapter.py -q
```

Expected: tests pass.

- [ ] **Step 3: Run formula normalization tests**

```powershell
$env:PYTHONPATH='.'
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' tests\test_formula_cdm_normalization.py
wsl -d Ubuntu2204 bash -lc "cd /root/OmniDocBench && PYTHONPATH=. /root/odb-venv/bin/python tests/test_formula_cdm_normalization.py"
```

Expected: both commands exit `0`.

- [ ] **Step 4: Verify full CDM score artifact**

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 -SaveName paddleocrvl_rocm_cdm_quick_match
```

Expected: `VERIFY OK`.

- [ ] **Step 5: Review produced artifacts**

```powershell
git status --short
Get-Content -TotalCount 80 docs\formula-cdm-root-cause-report-2026-07-08.md
```

Expected: tracked code/docs changes are clear; generated report has metrics, counts, and next-action recommendation.
