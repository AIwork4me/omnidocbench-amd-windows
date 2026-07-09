# PaddleOCR-VL-1.6 AMD Windows Release Evidence - 2026-07-09

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
| Overall | ↑ | 96.33 | 95.8116 | 95.2524 |
| Text Edit-distance | ↓ | 0.033 | 0.03447 | 0.03397 |
| Reading-order Edit-distance | ↓ | 0.127 | 0.12929 | 0.12833 |
| Table TEDS | ↑ | 94.76 | 94.2187 | 94.3216 |
| Formula CDM | ↑ | 97.49 | 96.6629 | 94.8326 |

## Text Edit-distance Root Cause

The earlier PaddleOCR official-engine Text Edit-distance regression was caused
by Markdown shape, not by the underlying text recognizer alone. PaddleOCRVL's
default Markdown export is presentation-oriented: `_to_markdown(pretty=True)`
wraps centered images and captions in HTML, while OmniDocBench expects
evaluation-oriented Markdown that can be filtered and matched cleanly.

The 2026-07-09 probe showed raw official pretty Markdown at `0.430483` Text
Edit-distance on the selected probe pages, while `_to_markdown(pretty=False)`
scored `0.183316`, nearly matching the PaddleOCR-VL-ROCm path at `0.178384`.
On the full set, the official engine now scores `0.03447`, close to both the
PaddleOCR-VL-ROCm engine (`0.03397`) and the public baseline (`0.033`).

Conclusion: benchmark users should export official PaddleOCRVL Markdown with
`_to_markdown(pretty=False)`. The repo's `--engine official` path does this by
default for evaluation runs.

## Formula CDM Root Cause

The fresh official-engine run scores `96.6629` Formula CDM, substantially
higher than the PaddleOCR-VL-ROCm engine's `94.8326`. This confirms that much
of the earlier Formula CDM gap came from adapter/model-output differences in
the lightweight ROCm path rather than from a zero-CDM evaluator failure.

The remaining gap to the public official baseline is about `0.8271` CDM points
(`97.49 - 96.6629`). The public baseline was produced with the official Linux
vLLM inference setup, while this run uses the Windows AMD llama.cpp/OpenAI
server path and had one unrecovered VLM 500 page. Given that the CDM
environment verify passes and the official-engine output is much closer to the
baseline, the remaining Formula CDM gap is best attributed to inference backend
and model-output differences, plus the single failed page, not to a known CDM
scorer compatibility bug.

## Publication Decision

Publish the PaddleOCR-VL-1.6 AMD Windows evidence with both local engine
columns. The PaddleOCR official engine is the best reference for CDM closeness
to the public baseline, while the PaddleOCR-VL-ROCm engine remains the proven
default Windows AMD path for easy local setup. Keep the default quick start on
the stable ROCm engine, and document the official engine as an explicit
benchmark variant.
