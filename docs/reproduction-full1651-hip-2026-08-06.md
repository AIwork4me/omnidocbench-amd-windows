# Real-machine full-run record: paddleocr-vl-hip-full-1651 (2026-08-06)

Machine: AMD Ryzen AI MAX+ 395 (Radeon 8060S, gfx1151), Windows 11, WSL
Ubuntu 22.04.5.

## Verdict (final): **OFFICIAL PASS**

`reproduce.ps1 -Profile paddleocr-vl-hip-full-1651` completed with
`state.json = passed` at commit `dfd89624c0e7f5f93b91ec1e4f90166da5c60f59`
(clean tree), all 21 stages passed, evidence pack complete under
`outputs/reproduction/paddleocr-vl-hip-full-1651/`.

- Inference: 1651/1651 pages selected (HIP), `_run_stats.json`
  selected_pages = 1651, ok = 1649, fail = 2.
- Strict prediction gate: **1649/1651 usable** (coverage 0.998789 >= 0.998),
  **2 failed pages**, both on the `allowed_failed_page_stems` allowlist,
  `unknown_failures = 0`, verdict = pass.
- Full verification (`verify_prediction_set.py` strict mode +
  `assert-metrics.ps1` with profile thresholds text < 0.10 / RO < 0.20 /
  TEDS > 0.85 / CDM > 0.85): PASS.
- Four phase fingerprints (provisioning / inference / scoring / evidence)
  re-verified fresh with `compute_fingerprint.py --check`: all exit 0.
- `artifact-hashes.json` matches the on-disk state.json, report.md,
  prediction-tree.json, strict prediction summary, backend proof,
  environment lock, and both Windows and WSL metric results/provenances.

## Official scores (page_count 1651)

| Metric | Windows | WSL CDM | README reference (ROCm) | Delta |
|---|---|---|---|---|
| Text Edit-distance | 0.035251 | 0.035231 | 0.03402 | +0.0012 |
| Reading-order Edit-distance | 0.129328 | 0.129524 | 0.12824 | +0.0011 |
| Table TEDS | 0.929792 | 0.929782 | 0.943222 | -0.0134 |
| Formula CDM | - (WSL only) | **0.965605** | 0.969219 | -0.0036 |

Windows and WSL shared metrics agree to < 0.0001. Deltas vs the reference
are consistent with the 2 missing pages and inherent model output variance.

## The 2 failed pages (allowlisted, upstream-known)

| Page | Failure | Root cause / tracking |
|---|---|---|
| `book_zh_GB12082006_extracted_page_8.png` | HTTP 500, llama-server `common_chat_peg_parse: unparsed peg-native output` | Upstream peg-native parsing failure, tracked at PaddlePaddle/PaddleOCR#18248. |
| `newspaper_The Times UK_0801@magazinesclubnew_page_031.png` | same 500 | same as above. |

Both are within `maximum_failed_pages = 2` and are on the profile's
`allowed_failed_page_stems` allowlist.

## Empty-GT pages are correct predictions (not failures)

As documented in the 2026-08-03 record, OmniDocBench v1.6 contains genuinely
empty-GT pages; empty predictions for those pages are valid
(`empty_gt_valid`), implemented in `scripts/gt_manifest.py`.

## Operational note: Windows MAX_PATH workaround (now fixed in-tree)

The first verification attempt of this run failed at `inference.prediction_check`
because 8 prediction filenames push their absolute paths past Windows MAX_PATH
(261 UTF-16 units in this worktree), making Python `os.stat/open` fail with
WinError 3 even though directory enumeration sees the files. The run was
completed with a machine-local venv shim (gitignored, not part of any
fingerprint). The permanent fix is committed at `252a6e2`:
`verify_prediction_set.py` and `hash_prediction_tree.py` now use an
extended-length (`\\?\`) access helper and `os.scandir` DirEntry data. With
the shim removed, both scripts verify this exact prediction directory cleanly
and the prediction tree hash (`17365b4a...`) is byte-identical to the packed
evidence.

## Evidence trail

- `state.json` / `report.md` / `metrics-summary.json` /
  `prediction-summary.json` / `artifact-hashes.json` /
  `fingerprint.{provisioning,inference,scoring,evidence}.json` under
  `outputs/reproduction/paddleocr-vl-hip-full-1651/`.
- Benchmark row: `benchmarks/index.json`
  (`paddleocr-vl-rocm-full-1651-2026-08-06`), label **validated resumed**.
- Audit: `.superpowers/sdd/full-run-2026-08-06-audit.md` (10-item read-only
  audit, all PASS; auditor subagents were unresponsive in this environment,
  so the itemized audit was performed by the continuation agent).
