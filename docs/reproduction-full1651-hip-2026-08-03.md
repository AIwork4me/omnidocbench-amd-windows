# Real-machine full-run record: paddleocr-vl-hip-full-1651 (2026-08-03)

Machine: AMD Ryzen AI MAX+ 395 (Radeon 8060S, gfx1151), Windows 11, WSL
Ubuntu 22.04.5. Repo commit `9311f25` (+ uncommitted follow-ups below).

## Verdict

**The strict prediction gate FAILED by design.** 1651/1651 pages were selected
and attempted; 1648 are usable (0.9982 coverage >= 0.998), but **3 pages fail
deterministically**, which exceeds the profile's `maximum_failed_pages = 2`.
The gate did its job: it refused to certify a run with 3 failed pages.

All other stages passed (env, mirrors, WSL, preflight, dataset, locks,
fingerprint, CDM env, VLM server, backend proof, layout, pipeline deps, input
locks, 3.4 h HIP inference).

## The 3 deterministic failed pages

| Page | Failure | Root cause |
|---|---|---|
| `book_zh_GB12082006_extracted_page_8.png` | HTTP 500, llama-server `common_chat_peg_parse: unparsed peg-native output` | The locked pipeline (PaddleOCR-VL-ROCm `f0cb401`, 07-25) prompts the model such that it responds with valid **prose**; llama-server b9637 rejects non-peg-native output. Reproducible with the pipeline request on any server config (seed 1/2, 4K/16K ctx, with/without `--skip-chat-parsing`); a direct simple-prompt request succeeds, so the model can parse the page. |
| `newspaper_The Times UK_0801@magazinesclubnew_page_031.png` | same 500 | same as above. The reference run (07-08 era, older pipeline) produced a valid table for this page; the newer locked pipeline's prompt changes model behavior. |
| `color_textbook_zhonggaokao_小学_13.人教新起点英语（4-5年级）_人教新起点五年级英语上册_课本_人教新起点英语5A电子课本_page_004` | empty Markdown (0 bytes) | Model-level empty output. **The reference run (`predictions/paddleocrvl_rocm`) has the identical 0-byte prediction for this page** — a known persistent model failure, not a regression. |

## Evidence paths

- Run state: `outputs/reproduction/paddleocr-vl-hip-full-1651/state.json`
  (status `failed`, `inference.run` passed 12098 s, `inference.prediction_check` failed)
- Adapter stats: `predictions/paddleocrvl_hip_full_1651/_run_stats.json`
  (schema v2; invocations 3; selected 1651; last invocation 1648 skipped / 3 new)
- Per-page errors: `predictions/paddleocrvl_hip_full_1651/_errors.log`
- Server evidence: `adapters/paddleocr-vl-1.6/logs/llama-server.log`
  (95 `common_chat_peg_parse` exceptions over all sessions)

## Supplementary scores (off-profile, for comparison only)

Because the gate failed, the profile's scoring stages did not run. They were
run manually on the 1648-valid set (labeled, not a certified profile result):

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
reference — consistent with the 2 missing table/text pages (one is a dense
newspaper table page) and the empty page.

## Resume commands

The gate will fail identically on `-Resume` (the 3 failures are
deterministic). Resume still works correctly per page:

```
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile paddleocr-vl-hip-full-1651 -Resume
```

To rerun inference from scratch:

```
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile paddleocr-vl-hip-full-1651 -ForceInference
```

## What would make this run pass (no gate relaxation)

1. A pipeline revision whose prompt does not trigger peg-native rejection on
   the 2 prose pages (the reference-era pipeline produced valid output), and
2. the model producing non-empty output for the known-empty page (also empty
   in the reference run), or the empty-page failure being accepted as a known
   model-level limitation via an evidence-based budget discussion.
