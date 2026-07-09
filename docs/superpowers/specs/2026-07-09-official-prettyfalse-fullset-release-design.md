# Official Pretty-False Full-Set Release Design

Date: 2026-07-09
Status: Ready for implementation approval

## Goal

Use option B for this release slice: make `omnidocbench-amd-windows` easier to publish and trust by producing a fresh, evidence-backed PaddleOCR official-engine full-set run after the `pretty=False` Markdown fix, while reusing the existing validated PaddleOCR-VL-ROCm engine full-set data as the local AMD reference.

This slice is about release quality for the repository, not broad new model tuning. The final public comparison table must contain only:

- Official PaddleOCR-VL-1.6 baseline
- PaddleOCR official engine on this Windows AMD setup
- PaddleOCR-VL-ROCm engine on this Windows AMD setup

The release must also explain why the previous official non-CDM metrics regressed and how benchmark users should avoid that failure mode.

## User-Approved Direction

The selected path is option B:

- Fresh rerun only for the PaddleOCR official engine.
- Do not fresh-rerun the PaddleOCR-VL-ROCm engine in this release slice.
- Keep the comparison table scoped to the official public baseline, PaddleOCR official engine, and PaddleOCR-VL-ROCm engine.
- Focus this round on making and publishing the `omnidocbench-amd-windows` project with clean docs, reproducible commands, and evidence-backed numbers.

## Current Evidence

The current repository already contains strong evidence from the Formula CDM and non-CDM investigations:

- PaddleOCR-VL-ROCm full-set data is validated and should remain the AMD reference for this slice.
- Previous official full-set data showed Formula CDM improvement over lightweight/ROCm output, but non-CDM metrics regressed.
- The major official Text Edit-distance regression was traced to default PaddleOCRVL presentation Markdown.
- The official doc_parser default export is display-oriented: `_to_markdown(pretty=True)` wraps centered images and captions in HTML.
- OmniDocBench scoring expects evaluation-oriented plain Markdown, where image syntax can be filtered cleanly.
- The adapter now prefers `result._to_markdown(pretty=False)` and has a fallback normalizer for centered HTML wrappers.

Validated probe evidence from 2026-07-09:

| Probe | Text Edit-distance | Interpretation |
|---|---:|---|
| Lightweight/ROCm probe | 0.178384 | Compatible reference behavior on the selected probe pages |
| Official default pretty Markdown | 0.430483 | Severe scorer incompatibility from presentation Markdown wrappers |
| Official `pretty=False` Markdown | 0.183316 | Regression largely disappears on the same pages |

Existing full-set comparison before the `pretty=False` full rerun:

| Metric | PaddleOCR-VL-ROCm full-set | Previous official full-set before `pretty=False` rerun | Official public baseline |
|---|---:|---:|---:|
| Overall | 95.2524 | 95.5443 | 96.33 |
| Text Edit-distance | 0.03397 | 0.04129 | 0.033 |
| Formula CDM | 94.8326 | 96.6829 | 97.49 |
| Table TEDS | 94.3216 | 94.0794 | 94.76 |
| Reading-order Edit-distance | 0.12833 | 0.12964 | 0.127 |

These previous official numbers are useful evidence but are not the final release table because they were generated before the full-set `pretty=False` correction.

## Architecture

### Isolated Official Full-Set Run

The fresh official run must write to a new prediction directory:

```text
predictions/paddleocr_official_prettyfalse_full_2026-07-09
```

This keeps the new official evidence separate from:

- `predictions/paddleocrvl_rocm`
- `predictions/paddleocrvl_rocm_cdm`
- `predictions/paddleocrvl_rocm_official_cdm`
- text-regression probe outputs

The matching score save name is expected to be:

```text
paddleocr_official_prettyfalse_full_2026-07-09_quick_match
```

### Scoring Configs

Add two full-set config templates:

```text
eval-infra/01-omnidocbench/configs/v16-official-prettyfalse-full-2026-07-09.yaml
eval-infra/01-omnidocbench/configs/v16-cdm-official-prettyfalse-full-2026-07-09.yaml
```

Both use the full OmniDocBench v1.6 manifest:

```text
eval-infra/01-omnidocbench/data/OmniDocBench.json
```

Both read predictions from:

```text
predictions/paddleocr_official_prettyfalse_full_2026-07-09
```

The Windows config scores Edit-distance and TEDS without CDM. The WSL config scores the same output with Formula CDM enabled.

### Official Engine Markdown Contract

For benchmark scoring, official PaddleOCRVL output must be exported as evaluation-oriented Markdown:

```python
markdown = result._to_markdown(pretty=False)["markdown_texts"]
```

If the installed PaddleOCR/PaddleX version exposes a different result shape, the adapter may fall back to result `.markdown`, dict-like Markdown fields, or the existing HTML-wrapper normalizer. The preferred path remains `_to_markdown(pretty=False)`.

This behavior must be documented in:

- `adapters/paddleocr-vl-1.6/README.md`
- `docs/pitfalls.md#official-pretty-markdown`
- the final release evidence report

### Release Evidence Report

Generate a focused report:

```text
docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md
```

The report must contain:

- exact commands used for inference and scoring;
- official engine `_run_stats.json` totals, including failed pages;
- the final metric comparison table with only the three approved columns;
- the root-cause conclusion for the old Text Edit-distance regression;
- the current Formula CDM conclusion after the official pretty-false full-set run;
- a clear note that fresh official numbers come from this Windows AMD llama.cpp server setup, while the public official baseline used Linux with vLLM.

### README Update

After the fresh official full-set run and verification succeed, update the README reference table so the repository no longer presents only one local number without context. The table should show:

- official public baseline;
- this repo using PaddleOCR official engine;
- this repo using PaddleOCR-VL-ROCm engine.

The README must not claim parity with the public official baseline unless the measured numbers support that claim. If a metric remains lower, the gap should be shown directly.

## Execution Flow

1. Preserve and verify the current `pretty=False` adapter fix and docs.
2. Add isolated official pretty-false config templates.
3. Preflight the VLM server, the adapter tests, and the CDM environment.
4. Run the official engine over the full 1651-page image set into the new prediction directory.
5. Score non-CDM metrics on Windows.
6. Score Formula CDM in WSL.
7. Verify all metrics are present and non-zero.
8. Generate the release evidence report and comparison table.
9. Update README and related docs only after fresh full-set data exists.
10. Run final checks, commit, and publish to `origin` if the user confirms the release push.

If the VLM server setup starts or restarts the server, pause and show exactly:

```text
⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.
```

## Success Criteria

The release slice is complete when all of these are true:

- `git diff --check` exits 0.
- `python -m pytest tests -q` passes.
- The VLM server verify script exits 0 before inference.
- `eval-infra/02-cdm-environment/verify.sh` exits 0 before CDM scoring.
- The new official prediction directory has `_run_stats.json` and close to 1651 page Markdown files.
- Windows scoring writes a metric result for `paddleocr_official_prettyfalse_full_2026-07-09_quick_match`.
- WSL CDM scoring writes a metric result with Formula CDM for the same save name.
- `verify.ps1 -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match` exits 0.
- The final report records official baseline, PaddleOCR official engine, and PaddleOCR-VL-ROCm engine in one comparison table.
- README and troubleshooting docs explain `pretty=False` for benchmark Markdown.
- The commit contains only tracked source/docs/config changes and no generated prediction directories, temporary debug files, or downloaded archives.

## Non-Goals

- Do not fresh-rerun PaddleOCR-VL-ROCm full-set inference in this slice.
- Do not mix lightweight/ROCm fallback pages into the official engine headline score.
- Do not update public reference scores before the fresh official full-set run finishes and verifies.
- Do not chase Formula CDM by editing GT or mutating final score JSON.
- Do not run CDM Windows-native.
- Do not delete existing prediction/result evidence from earlier investigations.

## Risks And Handling

- The official engine may still have VLM 500 failures. Record them in `_run_stats.json` and the report; do not hide them with cross-engine fallback.
- The official engine may remain below the public Linux vLLM baseline. Report the gap directly and attribute only what the evidence proves.
- The full run may take hours. Use isolated output paths so partial results do not corrupt previous evidence.
- Existing untracked experiment files should remain untouched unless a later explicit publication step chooses to track specific evidence docs.
