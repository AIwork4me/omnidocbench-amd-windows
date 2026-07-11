# Windows Native CDM Verification - 2026-07-11

This report records the local Windows-native CDM scoring evidence for the
`codex/windows-native-cdm-patch` branch after `windows-cdm.patch` was made
reproducible through setup and verification.

It is intentionally lightweight: the generated OmniDocBench result JSON files
remain local artifacts and are not committed to git.

## Scope

- Repository: `C:\Users\rocm\Desktop\omnidocbench-amd-windows`
- Branch: `codex/windows-native-cdm-patch`
- Commit: `49a48ab test: cover final CDM verification policy gaps`
- Config: `eval-infra/01-omnidocbench/configs/v16-cdm.yaml`
- Prediction directory: `predictions/paddleocrvl_rocm_cdm`
- Save name: `paddleocrvl_rocm_cdm_quick_match`
- Metric result: `eval-infra/01-omnidocbench/OmniDocBench/result/paddleocrvl_rocm_cdm_quick_match_metric_result.json`
- Run summary: `eval-infra/01-omnidocbench/OmniDocBench/result/paddleocrvl_rocm_cdm_quick_match_run_summary.json`

This evidence is based only on the local Windows hardware/software environment.
It is not a Linux vLLM/BF16 reference-path A/B run.

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1

powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 `
  -Config v16-cdm.yaml

powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 `
  -WindowsOnly `
  -RequireCdm `
  -SaveName paddleocrvl_rocm_cdm_quick_match

powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 `
  -SkipWsl `
  -WindowsCdm `
  -SkipVlm
```

## Environment Evidence

`verify-windows.ps1` passed the native CDM gate:

- Tracked patch exists.
- Tracked patch is applied to the generated OmniDocBench checkout.
- Patch sentinels are present in `latex2bbox_color.py` and `texlive_env.py`.
- `kpsewhich` finds `upgreek.sty`.
- ImageMagick is runnable: `ImageMagick 7.1.2-26 Q16-HDRI`.
- TeX Live bundled Ghostscript paths exist under `C:\texlive\2026\tlpkg\tlgs`.
- Identical-formula CDM smoke produced `F1_score = 1.0`.

The scoring run summary recorded:

| Item | Value |
|---|---:|
| Pages matched | 1651 |
| Match workers | 24 |
| CDM workers | 8 |
| CDM samples | 2352 |
| CDM timeout cases | 0 |
| CDM error cases | 0 |
| CDM exception cases | 0 |
| TEDS samples | 665 |
| TEDS timeout/error/exception cases | 0 |

Page matching used fallback logic for three pages:

| Fallback | Count |
|---|---:|
| `quick_match_timeout` | 2 |
| `page_timeout` | 1 |

These fallbacks completed and did not prevent metric generation.

## Metric Evidence

`verify.ps1 -WindowsOnly -RequireCdm -SaveName paddleocrvl_rocm_cdm_quick_match`
passed with:

| Metric | Raw value | Reported scale |
|---|---:|---:|
| Text Edit-distance | 0.03401597503524673 | 0.03402 |
| Display-formula Edit-distance | 0.09136706177344286 | 0.09137 |
| Table TEDS | 0.9313452461867218 | 93.1345 |
| Reading-order Edit-distance | 0.1282380300787933 | 0.12824 |
| Formula CDM | 0.9671288265306126 | 96.7129 |

The verifier printed:

```text
VERIFY OK: metric_result.json valid; mandatory metrics present and non-negative; CDM positive when present or required.
```

## Full-Verify Evidence

Native-only full verification passed:

```text
4 passed, 0 failed, 6 skipped
ALL CHECKS PASSED (skips were optional). The evaluation system is operational.
```

The passing gates were:

- `mirrors.env`
- `01-omnidocbench/verify`
- `02-cdm-environment/verify-windows`
- `03-scoring/verify-windows`

The skipped gates were intentional for this local native-CDM scoring check:

- WSL checks: `-SkipWsl`
- VLM server/layout/prediction checks: `-SkipVlm`
- Benchmark report: no benchmark run present

## Conclusion

The previous native-only full-verification failure was caused by a missing
Windows CDM scoring artifact, not by the Windows-native CDM patch, TeX Live,
ImageMagick, Ghostscript, or the scoring verifier.

After generating `paddleocrvl_rocm_cdm_quick_match_metric_result.json`, the
Windows-native CDM loop is green:

1. native CDM environment gate passes;
2. Windows scoring artifact contains finite positive CDM;
3. `verify.ps1 -WindowsOnly -RequireCdm` passes;
4. `full-verify.ps1 -SkipWsl -WindowsCdm -SkipVlm` passes.

## Follow-Up

This report records a local Windows-native CDM result for
`predictions/paddleocrvl_rocm_cdm`. It should not automatically replace the
published README benchmark table without reconciling prediction directory,
adapter version, run date, and aggregation convention against the existing
release evidence.

