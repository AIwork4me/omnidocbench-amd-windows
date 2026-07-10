# AMD Windows Release Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the final evidence-backed AMD Windows PaddleOCR-VL-1.6 results and root-cause narrative across the project documentation.

**Architecture:** Keep generated prediction/result files out of git. Update the public entry points first, then release evidence and adapter docs, then run targeted text checks and repository verification.

**Tech Stack:** Markdown documentation, PowerShell verification commands, pytest for existing tests, OmniDocBench result evidence already generated locally.

## Global Constraints

- Use the accepted final PaddleOCR official-engine scores: Overall `95.8600`, Text Edit-distance `0.03446`, Reading-order Edit-distance `0.12929`, Table TEDS `94.2187`, Formula CDM `96.8074`.
- Keep PaddleOCR-VL-ROCm engine scores unchanged: Overall `95.2524`, Text Edit-distance `0.03397`, Reading-order Edit-distance `0.12833`, Table TEDS `94.3216`, Formula CDM `94.8326`.
- Keep official baseline values as already used in the public README: Overall `96.33`, Text Edit-distance `0.033`, Reading-order Edit-distance `0.127`, Table TEDS `94.76`, Formula CDM `97.49`.
- Explain the remaining Formula CDM difference as inference backend/model-output difference: official Linux vLLM-style path vs Windows AMD llama.cpp/GGUF path.
- Mention the one deterministic VLM 500 page and link PaddleOCR issue `https://github.com/PaddlePaddle/PaddleOCR/issues/18248`.
- Do not edit generated predictions, ground truth, or score JSON files.
- Do not update README public reference scores from a partial or fallback-mixed run.

---

### Task 1: Update Public README Files

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Consumes: final scores and root-cause wording from `docs/formula-cdm-official-gap-investigation-2026-07-10.md`.
- Produces: first-viewport public documentation for GitHub readers.

- [ ] **Step 1: Update top score tables**

Replace official-engine values in both README score tables:

```text
Overall: 95.8600
Text Edit-distance: 0.03446
Reading-order Edit-distance: 0.12929
Table TEDS: 94.2187
Formula CDM: 96.8074
```

Expected: both README files have two identical public comparison tables with the final values.

- [ ] **Step 2: Add known-differences note**

Add a short note near the PaddleOCR-VL reference scores explaining:

```text
Formula CDM now reaches 96.8074 after the determinant-array CDM normalization fix.
The remaining gap to 97.49 is attributed to inference backend/model-output differences
between the public Linux vLLM-style path and the Windows AMD llama.cpp/GGUF path.
The official-engine run still has one deterministic VLM 500 page, tracked upstream in
PaddleOCR issue #18248.
```

Use equivalent Chinese wording in `README.zh-CN.md`.

- [ ] **Step 3: Keep quick start stable**

Do not change the default quick-start path (`predictions\paddleocrvl_rocm`) except to clarify that `--engine official` is the score-comparison path and uses `_to_markdown(pretty=False)`.

- [ ] **Step 4: Verify README text**

Run:

```powershell
Select-String -Path README.md,README.zh-CN.md -Pattern "95.8600","96.8074","18248","pretty=False"
```

Expected: each pattern appears in the README set.

### Task 2: Update Release Evidence And Supersession Notes

**Files:**
- Modify: `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`
- Modify: `docs/formula-cdm-vllm-gap-investigation-2026-07-09.md`

**Interfaces:**
- Consumes: final Formula CDM investigation from `docs/formula-cdm-official-gap-investigation-2026-07-10.md`.
- Produces: release evidence that does not conflict with the final README numbers.

- [ ] **Step 1: Update release score table**

Change the official-engine release table to:

```text
Overall: 95.8600
Text Edit-distance: 0.03446
Reading-order Edit-distance: 0.12929
Table TEDS: 94.2187
Formula CDM: 96.8074
```

- [ ] **Step 2: Update Formula CDM root-cause section**

State that the determinant-array evaluator compatibility issue was fixed and raised Formula CDM from `96.6629` to `96.8074`, leaving a `0.6826` point gap to `97.49` primarily explained by inference backend/model-output differences.

- [ ] **Step 3: Link the upstream issue**

Add the failed page and upstream issue URL:

```text
newspaper_The Times UK_0801@magazinesclubnew_page_031.png
https://github.com/PaddlePaddle/PaddleOCR/issues/18248
```

- [ ] **Step 4: Mark the 2026-07-09 vLLM-gap report as superseded**

Add a short note at the top of `docs/formula-cdm-vllm-gap-investigation-2026-07-09.md`:

```text
Superseded note: this was an intermediate investigation. The accepted final
post-fix Formula CDM result is 96.8074; see
docs/formula-cdm-official-gap-investigation-2026-07-10.md.
```

- [ ] **Step 5: Verify release evidence text**

Run:

```powershell
Select-String -Path docs\release-paddleocr-vl-1.6-amd-windows-2026-07-09.md,docs\formula-cdm-vllm-gap-investigation-2026-07-09.md -Pattern "96.8074","0.6826","18248","Superseded"
```

Expected: all final markers are present.

### Task 3: Update Adapter And Agent Documentation

**Files:**
- Modify: `adapters/paddleocr-vl-1.6/README.md`
- Modify: `adapters/README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: public README terminology for `official` and `lightweight` engines.
- Produces: consistent operational docs for agents and adapter authors.

- [ ] **Step 1: Clarify adapter engine roles**

In `adapters/paddleocr-vl-1.6/README.md`, add a score summary and clarify:

```text
--engine official is the PaddleOCR doc_parser score-comparison path.
The default/lightweight path is PaddleOCR-VL-ROCm for easy AMD Windows setup.
```

- [ ] **Step 2: Update adapter index**

In `adapters/README.md`, mention that the reference adapter exposes both `official` and `lightweight` engines.

- [ ] **Step 3: Update CLAUDE success criteria**

Update the reference target table in `CLAUDE.md` to show:

```text
Text Edit-distance: 0.03446 official / 0.03397 ROCm
Reading-order Edit-distance: 0.12929 official / 0.12833 ROCm
Table TEDS: 94.2187 official / 94.3216 ROCm
Formula CDM: 96.8074 official / 94.8326 ROCm
```

Keep the operational steps and human-intervention messages unchanged.

- [ ] **Step 4: Verify adapter and agent text**

Run:

```powershell
Select-String -Path adapters\README.md,adapters\paddleocr-vl-1.6\README.md,CLAUDE.md -Pattern "official","lightweight","96.8074","pretty=False"
```

Expected: the engine terms and final score appear in the relevant docs.

### Task 4: Update Core Eval Documentation

**Files:**
- Modify: `eval-infra/03-scoring/README.md`
- Modify: `eval-infra/01-omnidocbench/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/pitfalls.md`

**Interfaces:**
- Consumes: release evidence and existing setup flow.
- Produces: coherent infrastructure docs for new users and agents.

- [ ] **Step 1: Add official configs to scoring README**

Document the existing official configs:

```text
v16-official-prettyfalse-full-2026-07-09.yaml
v16-cdm-official-prettyfalse-full-2026-07-09.yaml
```

Explain that these consume `predictions/paddleocr_official_prettyfalse_full_2026-07-09`.

- [ ] **Step 2: Clarify OmniDocBench config inventory**

In `eval-infra/01-omnidocbench/README.md`, list the default ROCm configs and the official prettyfalse configs separately.

- [ ] **Step 3: Add architecture note**

In `docs/architecture.md`, add a concise note that the PaddleOCR official engine and PaddleOCR-VL-ROCm engine share the same scoring layer and differ only in prediction generation.

- [ ] **Step 4: Add pitfalls note**

In `docs/pitfalls.md`, update `#official-pretty-markdown` if needed so users know `pretty=False` is mandatory for benchmark scoring.

- [ ] **Step 5: Verify eval docs**

Run:

```powershell
Select-String -Path eval-infra\03-scoring\README.md,eval-infra\01-omnidocbench\README.md,docs\architecture.md,docs\pitfalls.md -Pattern "official-prettyfalse","pretty=False","PaddleOCR official"
```

Expected: scoring configs and Markdown-mode warning are discoverable.

### Task 5: Repository Verification And Commit

**Files:**
- All modified docs from Tasks 1-4.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: a clean documentation release commit.

- [ ] **Step 1: Check stale public values**

Run:

```powershell
rg -n "95\.8116|96\.6629|96\.6829|0\.8271|0\.8071" README.md README.zh-CN.md CLAUDE.md docs\release-paddleocr-vl-1.6-amd-windows-2026-07-09.md adapters\README.md adapters\paddleocr-vl-1.6\README.md eval-infra\01-omnidocbench\README.md eval-infra\03-scoring\README.md docs\architecture.md docs\pitfalls.md
```

Expected: no hits in public docs, except `96.6629` if explicitly labeled as pre determinant fix in the release evidence.

- [ ] **Step 2: Markdown whitespace check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Run existing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Expected: tests pass. If the local environment cannot run the suite, capture the exact failure and report it.

- [ ] **Step 4: Verify final score artifact**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match
```

Expected: all four metrics are non-zero and verification exits 0.

- [ ] **Step 5: Stage and commit intentional files only**

Run:

```powershell
git status --short
git add README.md README.zh-CN.md CLAUDE.md adapters\README.md adapters\paddleocr-vl-1.6\README.md docs\architecture.md docs\pitfalls.md docs\release-paddleocr-vl-1.6-amd-windows-2026-07-09.md docs\formula-cdm-vllm-gap-investigation-2026-07-09.md docs\formula-cdm-official-vllm-gap-cases-2026-07-09.json docs\formula-cdm-official-vllm-gap-probe-2026-07-09.json docs\non-cdm-text-regression-official-vs-lightweight-probe-2026-07-09.md docs\non-cdm-text-regression-full-vs-probe-2026-07-09.json docs\non-cdm-text-regression-htmlnorm-comparison-2026-07-09.json docs\non-cdm-text-regression-prettyfalse-comparison-2026-07-09.json docs\non-cdm-text-regression-probe-summary-2026-07-09.json docs\superpowers\specs\2026-07-10-amd-windows-release-polish-design.md docs\superpowers\plans\2026-07-10-amd-windows-release-polish.md eval-infra\01-omnidocbench\README.md eval-infra\03-scoring\README.md eval-infra\01-omnidocbench\configs\v16-text-regression-probe-lightweight.yaml eval-infra\01-omnidocbench\configs\v16-text-regression-probe-official-htmlnorm.yaml eval-infra\01-omnidocbench\configs\v16-text-regression-probe-official-prettyfalse.yaml eval-infra\01-omnidocbench\configs\v16-text-regression-probe-official.yaml
git commit -m "docs: publish final amd windows benchmark results"
```

Expected: commit succeeds without staging generated predictions, local logs, or old untracked debug files.
