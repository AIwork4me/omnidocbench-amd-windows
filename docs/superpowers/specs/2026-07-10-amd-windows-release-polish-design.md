# AMD Windows Release Polish Design

Date: 2026-07-10

## Goal

Publish `omnidocbench-amd-windows` as an evidence-backed, easy-to-follow
OmniDocBench v1.6 evaluation project for AMD Ryzen AI MAX+ 395 / Radeon 8060S
Windows laptops, using the final accepted PaddleOCR-VL-1.6 results and root
cause conclusions.

## Final Public Position

The project will present three score columns:

| Metric | Official baseline | PaddleOCR official engine | PaddleOCR-VL-ROCm engine |
|---|---:|---:|---:|
| Overall | 96.33 | 95.8600 | 95.2524 |
| Text Edit-distance | 0.033 | 0.03446 | 0.03397 |
| Reading-order Edit-distance | 0.127 | 0.12929 | 0.12833 |
| Table TEDS | 94.76 | 94.2187 | 94.3216 |
| Formula CDM | 97.49 | 96.8074 | 94.8326 |

The Formula CDM gap from `96.8074` to `97.49` is documented as an inference
backend/model-output difference between the official Linux vLLM-style reference
path and this Windows AMD llama.cpp/GGUF path, after ruling out broad CDM
evaluator failure. The Overall gap also includes one deterministic VLM 500 page
on the llama.cpp/GGUF path, tracked upstream as
<https://github.com/PaddlePaddle/PaddleOCR/issues/18248>.

## Scope

Update public-facing documentation and release evidence only. Do not rerun full
inference, do not rewrite prediction artifacts, and do not edit ground truth or
final score JSON files.

In scope:

- Top-level English and Chinese README files.
- Agent orchestration documentation (`AGENTS.md`) where reference scores and
  success criteria are shown.
- PaddleOCR-VL adapter documentation.
- Core scoring/evaluation READMEs where users need to understand the official
  engine, `_to_markdown(pretty=False)`, and CDM evidence.
- Release evidence documents and supersession notes for intermediate
  investigations.

Out of scope:

- Historical handoff notes and raw experiment logs, except for adding a
  supersession pointer when a document is likely to be mistaken for the latest
  result.
- Generated predictions, generated benchmark outputs, local VLM logs, and WSL
  OmniDocBench result files.
- Any attempt to close the remaining score gap by changing GT or scorer outputs
  without new pair-probe evidence.

## Documentation Architecture

`README.md` and `README.zh-CN.md` are the first-viewport truth. They must show
the final score table, quick start, and a short "known differences vs official"
explanation without requiring users to read the investigation reports first.

`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md` remains the release
evidence document because its run directory and save name use the 2026-07-09
full-set prediction artifact. It will be updated with the post-fix 2026-07-10
Formula CDM score and linked to the final Formula CDM investigation report.

`docs/formula-cdm-official-gap-investigation-2026-07-10.md` is the final root
cause note for Formula CDM. Older 2026-07-09 vLLM-gap notes will be marked as
superseded by it.

`adapters/paddleocr-vl-1.6/README.md` explains the two engines:

- `official`: `paddleocr.PaddleOCRVL` doc_parser, used for closest score
  comparison, with `_to_markdown(pretty=False)` for benchmark Markdown.
- `lightweight`: `PaddleOCR-VL-ROCm`, the easy local AMD Windows path, retained
  for reproducible setup and adapter development.

`AGENTS.md` and core eval-infra README files should keep operational steps
unchanged while updating final reference numbers and known exceptions.

## Error Handling And Honesty Rules

- State that `pretty=True` Markdown is for display, while `pretty=False`
  Markdown is required for OmniDocBench scoring.
- State that the one failed page is a known upstream issue, not hidden by a
  fallback in the published official-engine score.
- Do not claim exact official parity. The project reproduces a strong AMD
  Windows result with a documented backend gap.
- Keep success thresholds pragmatic (`Text Edit-distance < 0.10`, reading-order
  `< 0.20`, `TEDS > 0.85`, `CDM > 0.85`) while publishing the actual measured
  values.

## Verification

The release polish is complete when:

- Stale public numbers `95.8116` and `96.6629` no longer appear in the primary
  public docs except where explicitly labeled as "pre determinant fix".
- Public docs mention Formula CDM `96.8074` and Overall `95.8600`.
- Public docs mention the upstream issue URL for the deterministic VLM 500 page.
- Markdown formatting passes `git diff --check`.
- Existing tests still pass, or any unavailable test environment is reported
  clearly.
