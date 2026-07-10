# Formula CDM vLLM Gap Investigation

> Superseded note: this was an intermediate investigation. The accepted final
> post-fix Formula CDM result is `96.8074`; see
> [`docs/formula-cdm-official-gap-investigation-2026-07-10.md`](formula-cdm-official-gap-investigation-2026-07-10.md).

## Scope

This note investigates the remaining Formula CDM gap between the current
official `PaddleOCRVL` full-set run on this AMD Windows + llama.cpp/GGUF path
and the public PaddleOCR-VL-1.6 OmniDocBench v1.6 target.

The current question is not whether the earlier lightweight adapter was worse:
that is already proven. The question here is whether the residual gap from
`96.6829` to `97.49` is still an evaluator compatibility issue, or primarily a
VLM serving/model-output-path issue.

## Result

High-confidence conclusion: the remaining Formula CDM gap is primarily a
VLM server / model-output-path difference in the Windows AMD llama.cpp GGUF
setup, not a CDM evaluator GT-compatibility problem.

More precise wording: the evidence currently isolates the issue to the
inference/output boundary. It does not yet split that boundary into a single
cause such as "vLLM only" versus "GGUF conversion", "llama.cpp decoding",
"image pixel preprocessing support", or "server-side output parser behavior".
The definitive next experiment is to run the same official adapter and same
scorer against a Linux vLLM endpoint on the same 50 hard cases and then the
full set.

## Score Evidence

| Run | Formula CDM | Overall | Notes |
|---|---:|---:|---|
| Official public PaddleOCR-VL-1.6 target | 97.49 | 96.33 | Reported in the PaddleOCR-VL-1.6 paper / leaderboard table. |
| Previous lightweight full-run | 94.8326 | 95.2524 | `predictions/paddleocrvl_rocm_cdm_quick_match`. |
| Current official `PaddleOCRVL` full-run | 96.6829 | 95.5443 | `predictions/paddleocrvl_rocm_official_cdm`. |

The official `PaddleOCRVL` doc_parser path recovers `+1.8503` Formula CDM over
the lightweight path. The remaining notebook-level gap to `97.49` is `0.8071`
points.

The current official full-set CDM stage processed `2352` formula samples with:

- `timeout_case_count = 0`
- `error_case_count = 0`
- `exception_case_count = 0`

The one adapter failed page was:

- `newspaper_The Times UK_0801@magazinesclubnew_page_031.png`
- VLM 500: `The model produced output that does not match the expected peg-native format`
- This failed page contributes `0` display-formula samples in the current CDM result, so it does not explain the Formula CDM gap.

## Low-Case Distribution

From `paddleocrvl_rocm_official_cdm_quick_match_display_formula_result.json`:

- Formula samples: `2352`
- Raw sample-average CDM: `0.9657342687`
- `CDM == 0`: `14` samples
- `CDM < 0.5`: `54` samples
- `CDM < 0.8`: `102` samples
- Empty prediction: `4` samples
- Full sample deficit to perfect score: `80.593` sample-points

The residual public-target gap is much smaller than the total remaining model
error: at notebook-level it is `0.8071` points; at raw sample-average scale it
corresponds to about `21.56` sample-points versus the `97.49` target.

## Pair-Probe Evidence

Artifacts:

- `docs/formula-cdm-official-vllm-gap-cases-2026-07-09.json`
- `docs/formula-cdm-official-vllm-gap-probe-2026-07-09.json`

Probe set:

- `50` selected cases
- Includes `5` high-CDM controls, `14` zero/empty-prediction cases, and low-CDM cases by severity
- Selected-case CDM deficit upper bound: `37.641` sample-points

Three-way CDM probe results:

| Check | Result |
|---|---:|
| GT self-CDM F1 min | 1.0 |
| GT self-CDM failures / token-zero cases | 0 / 50 |
| Pred self-CDM F1 min | 0.0 |
| Pred self-CDM zero/token-zero cases | 9 / 50 |
| GT-vs-Pred CDM `< 0.5` | 45 / 50 |

Failure-class attribution over the 50 selected cases:

| Failure class | Count | Selected deficit |
|---|---:|---:|
| `model_or_dataset_gap` | 30 | 22.931 |
| `normalization_or_matching` | 6 | 5.710 |
| `pred_latex_unrenderable` | 5 | 5.000 |
| `extraction_or_matching` | 4 | 4.000 |
| `pending` / high-CDM controls | 5 | 0.000 |

Interpretation:

- GT self-CDM is clean: no evidence remains for a broad GT/evaluator compatibility bug.
- Pred self-CDM failures are real output problems: malformed/unrenderable prediction LaTeX or empty predictions.
- Most selected deficit is still from formulas that render on both sides but are semantically different, missed, or mismatched.
- The `normalization_or_matching` bucket exists, but it is a minority in this probe and is not the dominant explanation for the remaining public-target gap.

## Backend Difference Evidence

The local current "official" adapter does use PaddleOCR's official
`PaddleOCRVL` doc_parser, but it is connected to the AMD Windows VLM service as:

```python
PaddleOCRVL(
    pipeline_version="v1.6",
    vl_rec_backend="llama-cpp-server",
    vl_rec_server_url=server_url,
    vl_rec_api_model_name=api_model_name,
)
```

The local server path is llama.cpp over GGUF weights:

- `PaddleOCR-VL-1.6-GGUF.gguf`: `935,769,056` bytes
- `PaddleOCR-VL-1.6-GGUF-mmproj.gguf`: `881,770,560` bytes

PaddleOCR's documentation distinguishes the complete PaddleOCR-VL pipeline from
the VLM component and documents VLM service backends separately. It also states
that `PaddlePaddle + vLLM` means local layout analysis with a VLM served by
vLLM, and that vLLM/SGLang/FastDeploy cannot run natively on Windows. The
production Docker deployment defaults `VLM_BACKEND` to `vllm`.

Local PaddleX code also exposes a concrete backend behavior difference:

- The pipeline passes `min_pixels` / `max_pixels` per block type, including formulas.
- `paddlex.inference.models.doc_vlm.predictor` forwards those values as
  `mm_processor_kwargs` only for `client.backend == "vllm-server"`.
- With `llama-cpp-server`, the local run repeatedly warns:
  - `'llama-cpp-server' does not support min_pixels`
  - `'llama-cpp-server' does not support max_pixels`

This is direct evidence that the local llama.cpp path is not parameter-identical
to the vLLM path, especially for formula crop resolution handling.

## Root Cause

Primary root cause for the remaining Formula CDM deficit:

VLM output differences from the Windows AMD llama.cpp/GGUF serving path relative
to the official Linux vLLM-style serving path. The observable symptoms are
malformed prediction LaTeX, empty/missed formulas, and formula content/ordering
differences in hard pages.

Rejected as primary cause:

- CDM evaluator environment failure: full-set CDM had no formula metric errors,
  exceptions, or timeouts.
- GT self-CDM compatibility: 50/50 selected cases self-rendered with F1 `1.0`.
- The single VLM 500 page: it had no display-formula samples in the current CDM result.

Secondary issues worth tracking:

- A small number of close-Edit / low-CDM cases remain in
  `normalization_or_matching`; these may justify narrow scorer normalization
  tests, but they do not explain the dominant residual gap.
- Prediction-side render failures should be treated as adapter/server output
  validity issues, not evaluator bugs, unless a specific valid LaTeX construct
  is proven unsupported by CDM.

## Next Definitive Experiment

Run a paired A/B with the same official `PaddleOCRVL` client and same
OmniDocBench scorer:

1. Serve PaddleOCR-VL-1.6 with Linux vLLM / official Docker or equivalent.
2. Re-run the 50-case hard subset into a new prediction directory.
3. Score the subset and run the same pair-probe.
4. If the subset closes most of the gap, run full-set.

Expected decision rule:

- If vLLM subset materially improves over llama.cpp and pred self-CDM failures
  disappear or shrink, promote vLLM/BF16 as the reference-quality path.
- If vLLM produces the same low cases, classify the remainder as model/dataset
  gap or scorer normalization only where pair-probe proves it.

## External References

- PaddleOCR-VL-1.6 paper reports OmniDocBench v1.6 Formula CDM `97.49` and Overall `96.33`: https://arxiv.org/html/2606.03264v1
- PaddleOCR-VL usage docs describe complete pipeline vs VLM component, backend matrix, Windows limitation for vLLM/SGLang/FastDeploy, and vLLM default in Docker deployment: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html
- PaddleOCR-VL-1.6-GGUF model card documents the llama.cpp/GGUF usage path: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF
