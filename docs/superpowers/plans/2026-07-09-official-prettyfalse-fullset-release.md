# Official Pretty-False Full-Set Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and publish evidence-backed PaddleOCR-VL-1.6 OmniDocBench v1.6 results for `omnidocbench-amd-windows` using a fresh PaddleOCR official-engine full-set run with evaluation Markdown (`pretty=False`) and the existing validated PaddleOCR-VL-ROCm full-set run.

**Architecture:** Keep generated predictions and OmniDocBench result files isolated by run name, then promote only configs, tests, docs, and release evidence into git. The official engine writes to `predictions/paddleocr_official_prettyfalse_full_2026-07-09`, Windows scores non-CDM metrics, WSL scores Formula CDM, and a release report updates README after verification. The ROCm engine is not rerun in this slice; its existing validated full-set result remains the local AMD reference.

**Tech Stack:** Windows PowerShell 5.1, Python 3.10/3.11 virtualenv at `.venv`, PaddleOCR `PaddleOCRVL`, llama.cpp OpenAI-compatible HIP server, WSL Ubuntu2204, OmniDocBench v1.6, pytest, JSON/YAML scoring configs.

## Global Constraints

- Use option B: fresh-rerun only the PaddleOCR official engine; reuse existing PaddleOCR-VL-ROCm full-set data.
- The final comparison table has exactly these data columns: Official baseline, PaddleOCR official engine, PaddleOCR-VL-ROCm engine.
- Official benchmark Markdown must use `_to_markdown(pretty=False)` when available.
- Do not mix lightweight/ROCm fallback predictions into the official engine headline score.
- Do not update README reference numbers before fresh official full-set scoring and verification pass.
- CDM scoring remains WSL-only.
- Preserve existing untracked debug files, generated predictions, downloaded llama archives, and prior evidence unless a step explicitly names a tracked docs file.
- If VLM server setup starts or restarts the server, pause and show exactly: `⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.`

---

## File Structure

- Create `eval-infra/01-omnidocbench/configs/v16-official-prettyfalse-full-2026-07-09.yaml`: Windows non-CDM full-set scoring config for the new official prediction directory.
- Create `eval-infra/01-omnidocbench/configs/v16-cdm-official-prettyfalse-full-2026-07-09.yaml`: WSL CDM-enabled full-set scoring config for the same official prediction directory.
- Modify `adapters/paddleocr-vl-1.6/run_adapter.py`: keep the official engine export preference for `_to_markdown(pretty=False)` and HTML wrapper normalization.
- Modify `tests/test_paddleocr_vl_adapter.py`: keep tests that prove the official engine prefers `pretty=False`, retries per page, and supports explicit fallback without using fallback in the release run.
- Modify `adapters/paddleocr-vl-1.6/README.md`: document benchmark Markdown mode and the required `pretty=False` call.
- Modify `docs/pitfalls.md`: document the `#official-pretty-markdown` root cause and verification evidence.
- Create `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`: final evidence report generated after scoring.
- Modify `README.md`: update the public comparison table after fresh official metrics exist.
- Modify `README.zh-CN.md` only when `rg` confirms it contains the same stale reference score table as `README.md`; otherwise leave it unchanged and record that it had no matching score table.

---

## Task 1: Freeze The Official Pretty-False Run Identity

**Files:**
- Create: `eval-infra/01-omnidocbench/configs/v16-official-prettyfalse-full-2026-07-09.yaml`
- Create: `eval-infra/01-omnidocbench/configs/v16-cdm-official-prettyfalse-full-2026-07-09.yaml`

**Interfaces:**
- Consumes: `eval-infra/01-omnidocbench/data/OmniDocBench.json`
- Consumes: `predictions/paddleocr_official_prettyfalse_full_2026-07-09`
- Produces save name: `paddleocr_official_prettyfalse_full_2026-07-09_quick_match`

- [ ] **Step 1: Add the Windows non-CDM config**

Create `eval-infra/01-omnidocbench/configs/v16-official-prettyfalse-full-2026-07-09.yaml` with this exact content:

```yaml
# OmniDocBench v1.6 full-set eval config for the PaddleOCR official engine
# after forcing evaluation-oriented Markdown with _to_markdown(pretty=False).
# CDM is disabled here because Formula CDM runs in WSL via the paired config.
end2end_eval:
  metrics:
    text_block:      { metric: [Edit_dist] }
    display_formula: { metric: [Edit_dist] }
    table:           { metric: [TEDS, Edit_dist], teds_workers: 16 }
    reading_order:   { metric: [Edit_dist] }
  dataset:
    dataset_name: end2end_dataset
    ground_truth: { data_path: <REPO_ROOT>/eval-infra/01-omnidocbench/data/OmniDocBench.json }
    prediction:   { data_path: <REPO_ROOT>/predictions/paddleocr_official_prettyfalse_full_2026-07-09 }
    match_method: quick_match
    match_workers: 24
```

- [ ] **Step 2: Add the WSL CDM config**

Create `eval-infra/01-omnidocbench/configs/v16-cdm-official-prettyfalse-full-2026-07-09.yaml` with this exact content:

```yaml
# OmniDocBench v1.6 full-set eval config WITH Formula CDM enabled for the
# PaddleOCR official engine after forcing _to_markdown(pretty=False).
end2end_eval:
  metrics:
    text_block:      { metric: [Edit_dist] }
    display_formula: { metric: [Edit_dist, CDM], cdm_workers: 8 }
    table:           { metric: [TEDS, Edit_dist], teds_workers: 16 }
    reading_order:   { metric: [Edit_dist] }
  dataset:
    dataset_name: end2end_dataset
    ground_truth: { data_path: <REPO_ROOT>/eval-infra/01-omnidocbench/data/OmniDocBench.json }
    prediction:   { data_path: <REPO_ROOT>/predictions/paddleocr_official_prettyfalse_full_2026-07-09 }
    match_method: quick_match
    match_workers: 24
```

- [ ] **Step 3: Verify config paths and save-name inputs**

Run:

```powershell
Select-String -Path eval-infra\01-omnidocbench\configs\v16-official-prettyfalse-full-2026-07-09.yaml -Pattern "paddleocr_official_prettyfalse_full_2026-07-09","OmniDocBench.json","quick_match"
Select-String -Path eval-infra\01-omnidocbench\configs\v16-cdm-official-prettyfalse-full-2026-07-09.yaml -Pattern "paddleocr_official_prettyfalse_full_2026-07-09","display_formula","CDM"
```

Expected: both commands find all listed patterns.

---

## Task 2: Lock In The Pretty-False Adapter Behavior

**Files:**
- Modify: `adapters/paddleocr-vl-1.6/run_adapter.py`
- Modify: `tests/test_paddleocr_vl_adapter.py`
- Modify: `adapters/paddleocr-vl-1.6/README.md`
- Modify: `docs/pitfalls.md`

**Interfaces:**
- Produces: `_official_result_to_markdown(result: object) -> str`
- Produces: `run_adapter(..., engine="official", page_retries=1, fallback_pred_dir=None) -> dict`

- [ ] **Step 1: Confirm the adapter prefers `pretty=False`**

Run:

```powershell
rg -n "_to_markdown\\(pretty=False\\)|official-pretty-markdown|Official engine Markdown mode" adapters\paddleocr-vl-1.6\run_adapter.py adapters\paddleocr-vl-1.6\README.md docs\pitfalls.md
```

Expected: matches appear in all three files.

- [ ] **Step 2: Run the adapter unit tests**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests\test_paddleocr_vl_adapter.py -q
```

Expected: adapter tests pass, including the test that records `_to_markdown(pretty=False)`.

- [ ] **Step 3: Run the full fast test suite**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests -q
```

Expected: all tests pass.

---

## Task 3: Preflight The Long Full-Set Run

**Files:**
- Read: `adapters/paddleocr-vl-1.6/01-vlm-server/verify.ps1`
- Read: `eval-infra/02-cdm-environment/verify.sh`
- Read: `.venv/Scripts/python.exe`

**Interfaces:**
- Produces: confirmed VLM server availability before inference.
- Produces: confirmed CDM environment availability before WSL scoring.

- [ ] **Step 1: Check whitespace and current test baseline**

Run:

```powershell
git diff --check
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests -q
```

Expected: `git diff --check` exits 0 and pytest passes.

- [ ] **Step 2: Verify the VLM server**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
```

Expected: verify exits 0 and `/v1/models` responds. If the server is not running and setup must be started, run:

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip
```

Then pause and show:

```text
⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.
```

- [ ] **Step 3: Verify the CDM environment**

Run:

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/verify.sh
```

Expected: output includes `VERIFY OK` and the command exits 0.

- [ ] **Step 4: Confirm the new prediction directory is isolated**

Run:

```powershell
if (Test-Path predictions\paddleocr_official_prettyfalse_full_2026-07-09) {
  Get-ChildItem predictions\paddleocr_official_prettyfalse_full_2026-07-09 | Select-Object -First 5 Name,Length,LastWriteTime
} else {
  "prediction directory does not exist yet"
}
```

Expected: either the directory does not exist yet, or it contains only a partial run that the user has explicitly allowed to resume or replace.

---

## Task 4: Run PaddleOCR Official Engine Full-Set Inference

**Files:**
- Generate ignored: `predictions/paddleocr_official_prettyfalse_full_2026-07-09/*.md`
- Generate ignored: `predictions/paddleocr_official_prettyfalse_full_2026-07-09/_run_stats.json`
- Generate ignored on failures: `predictions/paddleocr_official_prettyfalse_full_2026-07-09/_errors.log`

**Interfaces:**
- Consumes: `eval-infra/01-omnidocbench/data/images`
- Consumes: VLM server from `adapters/paddleocr-vl-1.6/01-vlm-server`
- Produces: one Markdown file per successfully parsed page.

- [ ] **Step 1: Start the official full-set run**

Run from repo root:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine official `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\paddleocr_official_prettyfalse_full_2026-07-09 `
  --page-retries 1
```

Expected: command exits 0 unless more than half of pages fail. Per-page failures are recorded and do not abort the run.

- [ ] **Step 2: Summarize run stats**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -c "import json, pathlib; p=pathlib.Path('predictions/paddleocr_official_prettyfalse_full_2026-07-09/_run_stats.json'); s=json.loads(p.read_text(encoding='utf-8')); print({'count': s.get('count'), 'ok': s.get('ok'), 'fail': s.get('fail'), 'fallback': s.get('fallback'), 'engine': s.get('engine')}); print([x for x in s.get('stats', []) if x.get('status') != 'ok'][:10])"
```

Expected: `engine` is `official`, `count` is 1651, and any failed pages are listed.

- [ ] **Step 3: Count Markdown predictions**

Run:

```powershell
(Get-ChildItem predictions\paddleocr_official_prettyfalse_full_2026-07-09\*.md).Count
```

Expected: count is close to the `ok` value from `_run_stats.json`.

---

## Task 5: Score Official Non-CDM Metrics On Windows

**Files:**
- Generate ignored: `eval-infra/01-omnidocbench/OmniDocBench/result/paddleocr_official_prettyfalse_full_2026-07-09_quick_match_metric_result.json`
- Generate ignored: `eval-infra/01-omnidocbench/OmniDocBench/result/paddleocr_official_prettyfalse_full_2026-07-09_quick_match_run_summary.json`

**Interfaces:**
- Consumes: `v16-official-prettyfalse-full-2026-07-09.yaml`
- Produces: Windows-side text, formula Edit-distance, table, and reading-order scores without CDM.

- [ ] **Step 1: Run Windows scoring**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-official-prettyfalse-full-2026-07-09.yaml
```

Expected: `pdf_validation.py` exits 0.

- [ ] **Step 2: Inspect the metric result**

Run:

```powershell
Get-Item eval-infra\01-omnidocbench\OmniDocBench\result\paddleocr_official_prettyfalse_full_2026-07-09_quick_match_metric_result.json
```

Expected: file exists and has a new `LastWriteTime`.

---

## Task 6: Score Official Formula CDM In WSL

**Files:**
- Generate ignored in WSL: `/root/OmniDocBench/result/paddleocr_official_prettyfalse_full_2026-07-09_quick_match_metric_result.json`
- Generate ignored in WSL: `/root/OmniDocBench/result/paddleocr_official_prettyfalse_full_2026-07-09_quick_match_run_summary.json`

**Interfaces:**
- Consumes: `v16-cdm-official-prettyfalse-full-2026-07-09.yaml`
- Produces: Formula CDM for the same official pretty-false prediction directory.

- [ ] **Step 1: Run WSL CDM scoring**

Run:

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh v16-cdm-official-prettyfalse-full-2026-07-09.yaml
```

Expected: CDM scoring exits 0 and writes WSL result files.

- [ ] **Step 2: Verify official pretty-false full-set result**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match
```

Expected: `VERIFY OK` and all four metrics are non-zero.

---

## Task 7: Generate The Release Evidence Report

**Files:**
- Create: `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`

**Interfaces:**
- Consumes: official pretty-false Windows and WSL metric results.
- Consumes: existing PaddleOCR-VL-ROCm full-set metric results.
- Consumes: public official baseline values from README and existing investigation docs.
- Produces: the single evidence source for README table changes.

- [ ] **Step 1: Extract official pretty-false metrics**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -c "import json, pathlib; p=pathlib.Path(r'\\wsl.localhost\Ubuntu2204\root\OmniDocBench\result\paddleocr_official_prettyfalse_full_2026-07-09_quick_match_metric_result.json'); print(json.dumps(json.loads(p.read_text(encoding='utf-8')), ensure_ascii=False, indent=2)[:4000])"
```

Expected: JSON preview includes `text_block`, `display_formula`, `table`, and `reading_order`.

- [ ] **Step 2: Extract ROCm reference metrics**

Run:

```powershell
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -c "import json, pathlib; p=pathlib.Path(r'\\wsl.localhost\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_metric_result.json'); print(json.dumps(json.loads(p.read_text(encoding='utf-8')), ensure_ascii=False, indent=2)[:4000])"
```

Expected: JSON preview includes the validated ROCm full-set values.

- [ ] **Step 3: Write the report**

Use these metric extraction rules for both local runs:

```python
text_edit = metric["text_block"]["all"]["Edit_dist"]["ALL_page_avg"]
reading_edit = metric["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"]
table_teds = metric["table"]["page"]["TEDS"]["ALL"] * 100.0
formula_cdm = metric["display_formula"]["page"]["CDM"]["ALL"] * 100.0
overall = ((1.0 - text_edit) * 100.0 + table_teds + formula_cdm) / 3.0
```

Use these public baseline values:

```text
Overall: 96.33
Text Edit-distance: 0.033
Reading-order Edit-distance: 0.127
Table TEDS: 94.76
Formula CDM: 97.49
```

Create `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md` with these sections and a completed score table using the extraction rules above:

```markdown
# PaddleOCR-VL-1.6 AMD Windows Release Evidence - 2026-07-09

## Scope

## Commands

## Run Stats

## Score Comparison

| Metric | Direction | Official baseline | PaddleOCR official engine | PaddleOCR-VL-ROCm engine |
|---|:---:|---:|---:|---:|

## Text Edit-distance Root Cause

## Formula CDM Root Cause

## Publication Decision
```

Round local Overall, Table TEDS, and Formula CDM to 4 decimals. Round local Text Edit-distance and Reading-order Edit-distance to 5 decimals. Include an explicit note when `_run_stats.json` reports failed official pages.

- [ ] **Step 4: Verify report has the approved columns only**

Run:

```powershell
Select-String -Path docs\release-paddleocr-vl-1.6-amd-windows-2026-07-09.md -Pattern "Official baseline","PaddleOCR official engine","PaddleOCR-VL-ROCm engine"
```

Expected: all three approved column labels appear.

---

## Task 8: Update Public README Tables And Guidance

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md` only when its current score table mirrors stale README values.
- Modify: `AGENTS.md` only when its success criteria table mirrors stale README values.

**Interfaces:**
- Consumes: `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`
- Produces: public-facing setup and score guidance aligned with the new evidence.

- [ ] **Step 1: Update README headline table**

Replace the current single local score column with the completed `## Score Comparison` table from `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`. The README table must keep this exact header:

```markdown
| Metric | Direction | Official baseline | PaddleOCR official engine | PaddleOCR-VL-ROCm engine |
|---|:---:|---:|---:|---:|
```

After updating, run `rg -n "PaddleOCR official engine|PaddleOCR-VL-ROCm engine|Official baseline" README.md` and confirm all three column names are present.

- [ ] **Step 2: Update the PaddleOCR-VL reference section**

Add a short note:

```markdown
For benchmark scoring, the official PaddleOCRVL engine must export Markdown with `_to_markdown(pretty=False)`. The default pretty Markdown is intended for display and can inflate Text Edit-distance because OmniDocBench expects evaluation-oriented Markdown.
```

- [ ] **Step 3: Keep the default quick-start stable**

Leave the default quick-start adapter command on the current proven path unless the fresh official full-set result is chosen as the new default after review. Add the official engine command as an explicit benchmark variant:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --engine official `
    --img-dir eval-infra\01-omnidocbench\data\images `
    --out-dir predictions\paddleocr_official_prettyfalse_full_2026-07-09
```

- [ ] **Step 4: Update Chinese README only if it contains the same stale reference table**

Run:

```powershell
rg -n "PaddleOCR|Formula CDM|0\\.944|94\\.63|96\\.33|参考|基线" README.zh-CN.md
```

Expected: if the Chinese README contains the old reference scores, update its table with the same measured values and the same `pretty=False` warning in Chinese.

---

## Task 9: Final Verification And Commit

**Files:**
- All tracked files modified above.

**Interfaces:**
- Produces: one clean commit ready to push or PR.

- [ ] **Step 1: Run final checks**

Run:

```powershell
git diff --check
& 'C:\Users\rocm\Desktop\omnidocbench-amd-windows\.venv\Scripts\python.exe' -m pytest tests -q
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match
```

Expected: all commands exit 0.

- [ ] **Step 2: Review tracked and untracked files**

Run:

```powershell
git status --short
```

Expected tracked changes include only configs, adapter/tests/docs, README updates, and release evidence. Generated prediction directories, `tmp/`, downloaded llama zip files, and one-off debug scripts remain untracked and unstaged.

- [ ] **Step 3: Stage only release files**

Run:

```powershell
git add adapters/paddleocr-vl-1.6/run_adapter.py `
  adapters/paddleocr-vl-1.6/README.md `
  tests/test_paddleocr_vl_adapter.py `
  docs/pitfalls.md `
  docs/superpowers/specs/2026-07-09-official-prettyfalse-fullset-release-design.md `
  docs/superpowers/plans/2026-07-09-official-prettyfalse-fullset-release.md `
  eval-infra/01-omnidocbench/configs/v16-official-prettyfalse-full-2026-07-09.yaml `
  eval-infra/01-omnidocbench/configs/v16-cdm-official-prettyfalse-full-2026-07-09.yaml `
  docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md `
  README.md
```

If `README.zh-CN.md` is updated, include it in the same `git add`.

- [ ] **Step 4: Commit**

Run:

```powershell
git commit -m "docs: publish paddleocr vl amd windows evidence"
```

Expected: commit succeeds.

- [ ] **Step 5: Publish after user confirmation**

Run only after the user confirms pushing:

```powershell
git push origin HEAD
```

Expected: push succeeds to `https://github.com/AIwork4me/omnidocbench-amd-windows.git`.
