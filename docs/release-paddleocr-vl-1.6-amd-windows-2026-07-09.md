# PaddleOCR-VL-1.6 AMD Windows Release Evidence - 2026-07-09

Updated: 2026-07-10 with the post determinant-array CDM normalization score.

## Scope

This release slice publishes evidence-backed OmniDocBench v1.6 full-set scores
for PaddleOCR-VL-1.6 on this Windows AMD setup. It compares exactly three
columns: the public official baseline, the PaddleOCR official engine run from
this repo, and the existing validated PaddleOCR-VL-ROCm engine run.

The fresh run used the official `paddleocr.PaddleOCRVL` engine with
evaluation-oriented Markdown export, `result._to_markdown(pretty=False)`.
No PaddleOCR-VL-ROCm fallback pages were mixed into the official-engine score.

## Commands

```powershell
.\.venv\Scripts\python.exe adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine official `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\paddleocr_official_prettyfalse_full_2026-07-09 `
  --page-retries 1
```

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 `
  -Config v16-official-prettyfalse-full-2026-07-09.yaml
```

```powershell
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh `
  v16-cdm-official-prettyfalse-full-2026-07-09.yaml
```

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 `
  -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match
```

## Run Stats

Official-engine prediction output:

- Directory: `predictions/paddleocr_official_prettyfalse_full_2026-07-09`
- Engine: `official`
- Pages: 1651
- Successful Markdown pages: 1650
- Failed pages: 1
- Fallback pages: 0

Failed official page:

- `newspaper_The Times UK_0801@magazinesclubnew_page_031.png`
- Attempts: 2
- Error: VLM server 500, `The model produced output that does not match the expected peg-native format`
- Upstream tracking: <https://github.com/PaddlePaddle/PaddleOCR/issues/18248>

Scoring verification:

- Windows non-CDM scoring wrote
  `paddleocr_official_prettyfalse_full_2026-07-09_quick_match_metric_result.json`.
- WSL CDM scoring wrote the final CDM-enabled metric result under
  `/root/OmniDocBench/result/`.
- `verify.ps1 -SaveName paddleocr_official_prettyfalse_full_2026-07-09_quick_match`
  passed with all four metrics non-zero.

## Score Comparison

Overall is calculated as `((1 - Text Edit-distance) * 100 + Table TEDS + Formula CDM) / 3`.
Reading-order Edit-distance is reported but excluded from Overall.

| Metric | Direction | Official baseline | PaddleOCR official engine | PaddleOCR-VL-ROCm engine |
|---|:---:|---:|---:|---:|
| Overall | ↑ | 96.33 | 95.8600 | 95.2524 |
| Text Edit-distance | ↓ | 0.033 | 0.03446 | 0.03397 |
| Reading-order Edit-distance | ↓ | 0.127 | 0.12929 | 0.12833 |
| Table TEDS | ↑ | 94.76 | 94.2187 | 94.3216 |
| Formula CDM | ↑ | 97.49 | 96.8074 | 94.8326 |

## Text Edit-distance Root Cause

The earlier PaddleOCR official-engine Text Edit-distance regression was caused
by Markdown shape, not by the underlying text recognizer alone. PaddleOCRVL's
default Markdown export is presentation-oriented: `_to_markdown(pretty=True)`
wraps centered images and captions in HTML, while OmniDocBench expects
evaluation-oriented Markdown that can be filtered and matched cleanly.

The 2026-07-09 probe showed raw official pretty Markdown at `0.430483` Text
Edit-distance on the selected probe pages, while `_to_markdown(pretty=False)`
scored `0.183316`, nearly matching the PaddleOCR-VL-ROCm path at `0.178384`.
On the full set, the official engine now scores `0.03446`, close to both the
PaddleOCR-VL-ROCm engine (`0.03397`) and the public baseline (`0.033`).

Conclusion: benchmark users should export official PaddleOCRVL Markdown with
`_to_markdown(pretty=False)`. The repo's `--engine official` path does this by
default for evaluation runs.

Detailed probe evidence:

- [`docs/non-cdm-text-regression-official-vs-lightweight-probe-2026-07-09.md`](non-cdm-text-regression-official-vs-lightweight-probe-2026-07-09.md)
- [`docs/non-cdm-official-regression-root-cause-2026-07-09.md`](non-cdm-official-regression-root-cause-2026-07-09.md)

## Formula CDM Root Cause

The fresh official-engine run first scored `96.6629` Formula CDM,
substantially higher than the PaddleOCR-VL-ROCm engine's `94.8326`. A targeted
pair-probe then found one real evaluator compatibility issue: determinant
formulas written as vertical-bar wrapped arrays in GT should normalize to the
same CDM rendering form as `vmatrix` predictions. The tracked normalization
patch fixed those cases and raised the full-set official-engine Formula CDM to
`96.8074`.

The remaining gap to the public official baseline is about `0.6826` CDM points
(`97.49 - 96.8074`). The public baseline was produced with the official Linux
vLLM-style inference setup, while this run uses the Windows AMD llama.cpp/GGUF
OpenAI-compatible server path and had one unrecovered VLM 500 page. The CDM
environment verify passes, the full CDM stage processed `2352` formulas with
`0` CDM errors/exceptions/timeouts, and GT self-CDM compatibility failures were
not found in the final hard-case probe. The remaining Formula CDM gap is
therefore best attributed to inference backend and model-output differences,
not to a broad CDM scorer compatibility bug.

Final Formula CDM evidence:

- Root-cause report:
  [`docs/formula-cdm-official-gap-investigation-2026-07-10.md`](formula-cdm-official-gap-investigation-2026-07-10.md)
- Post-fix probe:
  [`docs/formula-cdm-official-gap-probe-2026-07-10-postfix.json`](formula-cdm-official-gap-probe-2026-07-10-postfix.json)

## Publication Decision

Publish the PaddleOCR-VL-1.6 AMD Windows evidence with both local engine
columns. The PaddleOCR official engine is the best reference for CDM closeness
to the public baseline, while the PaddleOCR-VL-ROCm engine remains the proven
default Windows AMD path for easy local setup. Keep the default quick start on
the stable ROCm engine, document the official engine as an explicit benchmark
variant, and tell benchmark users to export official PaddleOCRVL Markdown with
`_to_markdown(pretty=False)`.
