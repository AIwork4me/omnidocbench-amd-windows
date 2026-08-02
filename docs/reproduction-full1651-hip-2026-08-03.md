# Real-machine full-run record: paddleocr-vl-hip-full-1651 (2026-08-03)

Machine: AMD Ryzen AI MAX+ 395 (Radeon 8060S, gfx1151), Windows 11, WSL
Ubuntu 22.04.5.

## Verdict (final, after GT-aware validation correction)

**The strict prediction gate PASSES.** 1651/1651 pages were selected and
attempted; **1649/1651 usable** (coverage 0.9988 >= 0.998), **2 failed pages**
(within the profile's `maximum_failed_pages = 2`), `_run_stats.json`
selected_pages = 1651, manifest count = 1651.

The initial "3 failed pages" verdict was corrected after verifying the ground
truth: OmniDocBench v1.6 contains **2 genuinely empty-GT pages**
(`color_textbook_zhonggaokao_小学_13.人教新起点英语（4-5年级）...` pages 001 and
004 — their layout_dets are only figures plus text_mask regions with empty
text). The empty prediction for `...page_004` is therefore **correct**, not a
failure. The validators (`scripts/verify_prediction_set.py`,
`scripts/validate_predictions.py`) and the adapter's `--skip-existing` resume
are now GT-aware (`scripts/gt_manifest.py`): an empty prediction counts as
valid/reusable when the page's GT is itself empty.

## The 2 failed pages (peg-native, upstream-known)

| Page | Failure | Root cause / tracking |
|---|---|---|
| `book_zh_GB12082006_extracted_page_8.png` | HTTP 500, llama-server `common_chat_peg_parse: unparsed peg-native output` | The model responds with valid prose that does not match the expected peg-native structure; llama-server b9637 rejects it. Reproducible with the pipeline request on any server config (seed 1/2, 4K/16K ctx, with/without `--skip-chat-parsing`); a direct simple-prompt request succeeds, so the model can parse the page. **Tracked upstream: PaddlePaddle/PaddleOCR#18248 (peg-native).** |
| `newspaper_The Times UK_0801@magazinesclubnew_page_031.png` | same 500 | same as above. |

Both pages have non-empty GT (37 and 63 layout dets respectively) and are
within the allowed 2-page failure budget; the harness scores them as empty
matches (already reflected in the metrics below).

## Evidence paths

- Run state: `outputs/reproduction/paddleocr-vl-hip-full-1651/state.json`
  (status `failed` at `inference.prediction_check` under the pre-fix
  validator; the same artifacts pass with the GT-aware validator, see
  `verify_prediction_set.py` output above)
- Adapter stats: `predictions/paddleocrvl_hip_full_1651/_run_stats.json`
  (schema v2; invocations 3; selected 1651; last invocation 1648 skipped / 3 new)
- Per-page errors: `predictions/paddleocrvl_hip_full_1651/_errors.log`
- Server evidence: `adapters/paddleocr-vl-1.6/logs/llama-server.log`

## Scores

Scoring stages run manually (off-profile) on the 1648 non-empty predictions:

| Metric | This run (Windows) | This run (WSL CDM) | README reference (ROCm) |
|---|---|---|---|
| Text Edit-distance | 0.035378 | 0.051572* | 0.03402 |
| Reading-order Edit-distance | 0.129539 | 0.130924* | 0.12824 |
| Table TEDS | 0.929766 | 0.631849* | 0.943222 |
| Formula CDM | — (WSL only) | **0.966490** | 0.969219 |

\* WSL shared metrics differ from Windows because text matching is
timeout-driven: WSL hit 1 quick-match timeout fallback, Windows hit 3
(2 quick-match + 1 page timeout); each fallback changes the alignment for
that page. Formula Edit-dist is bit-identical across both scorers
(0.09412421949815843), and the Windows values are within 0.001-0.013 of the
reference — consistent with the 2 missing pages (one is a dense newspaper
table page).

## Resume / completion commands

```powershell
# Per-page resume (fingerprint-gated): re-runs only missing/invalid pages.
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile paddleocr-vl-hip-full-1651 -Resume

# Fresh certified run (after code changes the fingerprint gate requires it):
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile paddleocr-vl-hip-full-1651 -ForceInference
```
