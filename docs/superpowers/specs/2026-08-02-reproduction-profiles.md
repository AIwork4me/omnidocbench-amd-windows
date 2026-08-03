# Reproduction Profiles — Design (2026-08-02)

Upgrade `scripts/reproduce.ps1` from a single `cpu-smoke-10` entry point into a
declarative, resumable, verifiable multi-profile reproduction system with three
supported profiles: `cpu-smoke-10`, `hip-smoke-10`,
`paddleocr-vl-hip-full-1651`.

## 1. Audit of the current system

### 1.1 What in `reproduce.ps1` is hard-coded to `cpu-smoke-10`?

- `[ValidateSet("cpu-smoke-10")]` on `$RunProfile` (scripts/reproduce.ps1:35).
- Artifact names: `predictions\paddleocrvl_cpu_smoke_10`,
  `OmniDocBench_cpu_smoke_10.json`, the Windows result path, and
  `$saveName = "paddleocrvl_cpu_smoke_10_quick_match"` (lines 48-57).
- Backend: `-Variant cpu` in the Preflight and VLM-server phases; phase display
  name "CPU VLM server" (lines 188, 225-230).
- Page count: `--max-pages 10`, `--limit 10`, and two exact-10 assertions
  (lines 253-269).
- Scoring configs `v16-cpu-smoke-10.yaml` / `v16-cdm-cpu-smoke-10.yaml`
  (lines 272, 279).
- Resume bookkeeping keys on **display names** via `$alwaysRunPhases`
  (lines 69-76) — renaming a phase silently changes resume behavior.
- Default `-ServerPort 8121` (line 43).

### 1.2 Which stages are shareable between profiles?

All provisioning stages: Python env, mirror detection, WSL availability,
preflight, dataset setup/verify, upstream locks, WSL CDM environment, layout
model, pipeline dependency, inference input locks. Only **parameters** differ
(variant, port, pages, prediction dir, manifest, configs, save_name,
thresholds). The inference/manifest/scoring/verification stages are identical
in shape and differ only in those parameters.

### 1.3 Which fields must a profile define?

`schema_version`, `name`, `description`, `kind` (smoke|subset|full), `model`,
`adapter`, `engine`, `variant`, `expected_pages`, `max_pages` (nullable),
`prediction_dir`, `prediction_manifest`, `manifest_is_full_dataset`,
`windows_scoring_config`, `wsl_cdm_config`, `score_save_name`, `server_port`,
`minimum_prediction_coverage`, `maximum_failed_pages`,
`require_gpu_backend_proof`, `require_wsl_cdm`, `metric_sanity` (nullable
threshold block), `estimated_duration_class`.

### 1.4 Why is today's `-Resume` not per-page resume for full inference?

Resume operates at **phase granularity keyed by display name**. Inside the
inference phase the only "resume" is a file-count check
(`...Count -lt 10` → rerun the whole adapter). There is no manifest-aware,
per-page validity model, and a full-set rerun would reprocess every page.

### 1.5 How does the adapter treat existing Markdown after an interruption?

It doesn't. `run_lightweight_folder` rewrites every `<stem>.md`
unconditionally (run_adapter.py:155-176). `run_official_folder` **deletes**
`_run_stats.json` and `_errors.log` at start (lines 342-343). A rerun always
reprocesses everything.

### 1.6 Does `_run_stats.json` survive a killed process?

No. It is written once, after the page loop completes (lines 189-200, 435).
A `Stop-Process` mid-run leaves zero stats.

### 1.7 Does VLM `verify.ps1` prove a HIP build is loaded?

No. It proves: `.env.local` keys exist, files exist, `/v1/models` answers, the
model id is listed. It never checks `.variant`, `LLAMA_VARIANT`, the server
exe's SHA-256, the llama.cpp tag, or the server log for ROCm/HIP device
init + GPU offload. A CPU llama-server on the same port passes.

### 1.8 Is the 95% coverage threshold in `full-verify.ps1` enough for a public "full 1651" claim?

No. 95% of 1651 = 1568: a run missing 83 pages passes. There is no
max-failed-pages bound, no `_run_stats.json` cross-check, no per-page failure
listing, and nothing distinguishes a 10-page subset from a full run.

### 1.9 How do we stop stale state reuse after profile/code/lock/dataset changes?

Compute a **run fingerprint** (profile hash, repo commit + worktree hash,
upstream-lock.json hash, dataset manifest hash, pipeline commit, GGUF/mmproj/
layout hashes, llama-server exe hash + tag, scoring config hashes) and store
it in `state.json` + `fingerprint.json`. `-Resume` recomputes and compares;
any critical-field change fails closed with explicit remediation.

### 1.10 How do we bind config ↔ prediction dir ↔ save_name ↔ result file?

Each profile owns a unique prediction dir and save_name. The profile loader
parses the declared scoring configs and asserts their `data_path` values equal
the profile's `prediction_manifest` / `prediction_dir`, and that
`save_name == basename(prediction_dir) + "_" + match_method`. At verification
time the result files must (a) exist under the expected save_name, (b) have
mtime ≥ run start, (c) hash-match the values recorded in
`artifact-hashes.json`.

## 2. Design

### 2.1 Approach selection

Considered:

1. **Copy the orchestrator per profile** — rejected: triplicated logic,
   guaranteed drift, exactly the anti-pattern the task forbids.
2. **PSD1 profiles + pure-PowerShell orchestrator** — PSD1 is PowerShell-only,
   hard to unit-test from pytest, and `Import-PowerShellDataFile` semantics are
   awkward for schema validation.
3. **JSON profiles + Python resolver/validator + thin PowerShell orchestrator**
   — chosen. JSON is reviewable and PS 5.1-readable (`ConvertFrom-Json`);
   validation, fingerprinting, resume-stats parsing, backend-proof evaluation,
   acceptance checks, and evidence assembly live in small, pytest-covered
   Python modules under `scripts/`; `reproduce.ps1` keeps process
   orchestration, state, traps, and WSL interop.

### 2.2 Components

| File | Role |
|---|---|
| `scripts/profiles/<name>.json` | Declarative profile (schema_version 1) |
| `scripts/reproduction_profiles.py` | Load/validate/resolve/list/dry-run; fail-closed CLI |
| `scripts/run_fingerprint.py` | Compute + compare run fingerprints |
| `scripts/backend_proof.py` | HIP/CPU backend proof evaluator (log predicates, fixture-tested) |
| `scripts/verify_run_acceptance.py` | Strict full-run acceptance (pages, stats, coverage, failures, metrics, freshness, binding) |
| `scripts/evidence_pack.py` | Assemble `outputs/reproduction/<profile>/` evidence + report.md |
| `scripts/reproduce.ps1` | Profile-driven orchestrator; stable phase IDs; atomic state |
| `adapters/paddleocr-vl-1.6/run_adapter.py` | `--skip-existing`, incremental atomic `_run_stats.json` v2 |
| `adapters/.../01-vlm-server/verify.ps1` | `-ExpectedVariant`, `-Port` params |
| `scripts/full-verify.ps1` | `-MinCoverage`, `-MaxFailedPages`, `-ExpectedPages` strict knobs |
| `eval-infra/01-omnidocbench/configs/v16[-cdm]-hip-{smoke-10,full-1651}.yaml` | New scoring configs |
| `scripts/validate_predictions.py` | Read stats schema v2 (keep v1 compat) |

### 2.3 Profiles

| | cpu-smoke-10 | hip-smoke-10 | paddleocr-vl-hip-full-1651 |
|---|---|---|---|
| variant | cpu | hip | hip |
| pages | 10 (`max_pages=10`) | 10 (`max_pages=10`) | 1651 (`max_pages=null`) |
| prediction_dir | predictions/paddleocrvl_cpu_smoke_10 | predictions/paddleocrvl_hip_smoke_10 | predictions/paddleocrvl_hip_full_1651 |
| manifest | OmniDocBench_cpu_smoke_10.json (subset) | OmniDocBench_hip_smoke_10.json (subset) | OmniDocBench.json (full dataset) |
| configs | v16-cpu-smoke-10 / v16-cdm-cpu-smoke-10 | v16-hip-smoke-10 / v16-cdm-hip-smoke-10 | v16-hip-full-1651 / v16-cdm-hip-full-1651 |
| save_name | paddleocrvl_cpu_smoke_10_quick_match | paddleocrvl_hip_smoke_10_quick_match | paddleocrvl_hip_full_1651_quick_match |
| port | 8121 | 8122 | 8122 (shared with hip-smoke; same model+settings, idempotent server) |
| coverage / max failed | 1.0 / 0 | 1.0 / 0 | 0.998 / 2 |
| backend proof | cpu record | hip required | hip required |
| metric sanity | validity only | validity only | validity + wiring gates (Edit<0.10, RO<0.20, TEDS>0.85, CDM>0.85, raw scale) |
| kind | smoke | smoke | full |

Validation rules (fail-closed at load): unique name/prediction_dir/save_name;
`full` ⇒ expected_pages=1651 ∧ max_pages=null ∧ manifest_is_full_dataset ∧
require_wsl_cdm; `hip` ⇒ variant literally `hip` ∧ require_gpu_backend_proof;
`smoke` ⇒ max_pages == expected_pages ∧ coverage == 1.0 ∧ max_failed == 0;
no absolute/UNC paths; configs exist and their data_paths match the profile;
save_name matches `basename(prediction_dir)_quick_match`.

### 2.4 Orchestrator phases (stable IDs)

`environment.python` → `environment.mirrors` → `environment.wsl` →
`environment.preflight` → (`inputs.seed` if `-SeedFrom`) → `dataset.setup` →
`dataset.locks` → `cdm.wsl_environment` → `inference.server` →
`inference.backend_proof` → `inference.layout` → `inference.pipeline` →
`inference.input_locks` → `inference.run` → `predictions.manifest` →
`scoring.windows` → `scoring.wsl_cdm` → `verification.final` →
`evidence.pack`.

Resume skips phases whose **ID** previously passed, except the always-run set:
`environment.wsl`, `environment.preflight`, `dataset.locks`,
`cdm.wsl_environment`, `inference.server`, `inference.backend_proof`,
`inference.input_locks`, `inference.run`, `verification.final`,
`evidence.pack`. (`inference.run` is cheap to re-enter: with
`--skip-existing` it only validates + fills gaps.) Before honoring any skip,
`-Resume` validates the stored fingerprint; mismatch → fail closed.

`-DryRun` prints the resolved profile (all paths/configs/save_name/backend)
plus the ordered phase list with IDs and commands; performs no downloads,
starts no services, touches no predictions/scores. `-ListProfiles` prints a
table (name, backend, pages, kind, duration class, description). An unknown
`-Profile` exits non-zero listing the valid names. `-ServerPort` remains as an
override; default comes from the profile.

### 2.5 Per-page resume in the adapter

`run_adapter.py` gains `--skip-existing` (also exposed on `run_adapter()`).
Per selected page, before inference:

1. Expected file = `<stem>.md` in the profile's own prediction dir.
2. Reuse only if: regular file (not dir/symlink-junction anomaly), UTF-8
   decodable, non-empty after strip, and recorded (or re-validated) against
   the current selection.
3. Anything else (missing, empty, bad encoding, directory) → reprocess.

`_run_stats.json` becomes schema v2, rewritten **atomically** (temp +
`os.replace`) after every page:

```json
{
  "schema_version": 2, "engine": "lightweight",
  "count": 1651, "selected": 1651, "requested_max_pages": null,
  "ok": 1649, "newly_processed": 120, "skipped_existing": 1529, "fail": 2,
  "completed": false, "started_at": "...", "updated_at": "...",
  "img_dir": "...", "out_dir": "...",
  "invocations": [{"started_at": "...", "ended_at": "...", "newly_processed": 120,
                   "skipped_existing": 1529, "failed": 2, "elapsed_seconds": 900.0}],
  "stats": [{"image": "x.png", "status": "ok|skipped_existing|failed: ...",
             "seconds": 4.2}]
}
```

`count` is kept (= selected) so `validate_predictions.py` and existing
consumers keep working; the validator learns v2 fields. Resumed runs load the
prior stats (v1 or v2), retry prior failures, and append a new `invocations`
entry — accumulated evidence survives process kills. `skipped_existing` is
never counted as newly processed; acceptance treats `ok = newly ok + skipped
valid`.

The orchestrator always passes `--skip-existing`; first runs have nothing to
skip, `-Resume` fills gaps, and `-ForceInference` deletes only this profile's
prediction dir, owned subset manifest (never the shared full manifest),
save_name-keyed result files on both Windows and WSL result dirs, and this
profile's `state.json`. Deletion asserts the resolved dir stays under
`<root>\predictions`.

### 2.6 Fingerprints

`scripts/run_fingerprint.py` writes `fingerprint.json`:

- `profile_sha256` (canonical profile JSON)
- `repo_commit`, `worktree_hash` (hash of `git status --porcelain`)
- `upstream_lock_sha256`
- `dataset_manifest_sha256`
- `scoring_config_sha256` (both configs)
- `pipeline_commit` (outputs/checkouts/PaddleOCR-VL-ROCm HEAD)
- `gguf_sha256`, `mmproj_sha256`, `layout_sha256` (values already in
  upstream-lock.json — the lock entry *is* the expected hash; we record the
  locked value + verify the on-disk file matches via verify-upstream-lock)
- `llama_server_exe_sha256`, `llama_tag`, `llama_variant`

Resume comparison: all fields hard-fail on change, with a message naming the
changed field and the remediation (`-ForceInference` or delete
`outputs/reproduction/<profile>/state.json` for a clean start).

### 2.7 HIP backend proof

`scripts/backend_proof.py --expected-variant hip --out backend-proof.json`
evaluates independent conditions (each logged, any failure exits 1):

1. profile variant == hip; `.variant` file == hip; `.env.local` LLAMA_VARIANT == hip.
2. `LLAMA_SERVER_EXE` exists under `adapters/paddleocr-vl-1.6/models/llama.cpp`;
   SHA-256 recorded; `LLAMA_TAG` == locked tag from upstream-lock.json.
3. A live `llama-server.exe` process whose image path == `LLAMA_SERVER_EXE`;
   PID recorded (the pid file holds the wrapper PID, so resolve the real one
   via CIM).
4. `/v1/models` on the profile port returns the expected model id.
5. Server log contains ROCm/HIP device-init evidence AND GPU-offload evidence
   (regex sets, fixture-tested — e.g. `ggml_cuda_init: found N ROCm devices`,
   `AMD Radeon`, `gfx11`, `offloaded n/n layers to GPU`).
6. No CPU-fallback markers (e.g. `falling back to CPU`, `n_gpu_layers = 0`).

`01-vlm-server/verify.ps1` gains `-ExpectedVariant {any,cpu,hip}` (default
`any` = today's behavior) and `-Port`; with `hip` it requires `.variant` and
`LLAMA_VARIANT` to match. HIP profiles also fail at preflight on Radeon
860M/gfx1152 (locked binaries omit it) instead of falling back to CPU —
`preflight.ps1` already gates AMD presence; the orchestrator adds the 860M
refusal for hip profiles pointing at
`docs/llama-cpp-radeon-860m-gfx1152-issue-draft-2026-07-26.md`.

### 2.8 Strict acceptance (`verify_run_acceptance.py`)

Inputs: resolved profile, prediction dir, manifest, `_run_stats.json`, Windows
+ WSL result JSONs, run-start timestamp, evidence dir. Hard gates:

- manifest pages == expected_pages (1651 for full).
- stats.selected == expected_pages; attempted (newly + skipped + failed)
  == expected_pages; full profile ⇒ `requested_max_pages` is null
  (subset can never masquerade as full).
- valid predictions / expected ≥ `minimum_prediction_coverage`
  (1649/1651 = 0.99879 ≥ 0.998 passes; 1648/1651 = 0.99818 ≥ 0.998 passes —
  wait: 1648/1651 = 0.998183 → passes the 0.998 bar; failed=3 > max 2 →
  **fails** the failed-pages gate. 1600 and 1001 fail both).
- failed pages ≤ `maximum_failed_pages`; every missing/failed page is listed
  by name in `prediction-summary.json`.
- metric validity: text/reading-order Edit_dist finite ≥ 0; TEDS finite in
  [0,1] raw or [0,100] % (scale auto-normalized to raw 0..1 for comparison);
  CDM present, finite, > 0 (both Windows where config provides it and WSL).
- full profile ⇒ metric sanity gates (Edit < 0.10, RO < 0.20, TEDS > 0.85,
  CDM > 0.85, raw scale) — wiring sanity, not a model-quality claim.
- result freshness: mtime ≥ run start; sha256 recorded into
  `artifact-hashes.json`; save_name matches the profile.
- denominators (page/sample counts present in the result JSON) recorded;
  timeout/error/exception counters recorded when present.

`full-verify.ps1` gains `-MinCoverage` (default 0.95 = today),
`-MaxFailedPages` (default -1 = unbounded = today), `-ExpectedPages`
(default 0 = infer = today). reproduce.ps1 passes the profile's strict values.

### 2.9 Evidence pack (`outputs/reproduction/<profile>/`)

`state.json` (v2: phase IDs, fingerprint, resume command), 
`profile.resolved.json`, `fingerprint.json`, `hardware.json` (CPU/GPU/driver/
OS/RAM/WSL via CIM + `wsl -l -v`), `backend-proof.json`,
`artifact-hashes.json`, `prediction-summary.json`, `metrics-summary.json`,
`report.md` (verdict, commands, per-phase timings, pages, metrics, hashes).
All JSON writes are temp-file + atomic replace. `outputs/` is gitignored.

### 2.10 Testing

New: `test_reproduction_profiles.py` (load/validate/unique/1651/hip/full
invariants/ListProfiles/DryRun/invalid fail-closed/config↔profile binding),
`test_adapter_resume.py` (fake pipeline: partial→interrupt→resume, no
rewrites of valid pages, invalid/empty/non-UTF8 regenerated, stats v2 fields,
invocation accumulation), `test_backend_proof.py` (HIP/CPU/broken/incomplete
log fixtures; variant mismatch; models-OK-but-wrong-backend),
`test_verify_run_acceptance.py` (1651, 1649, 1648, 1600, 1001, subset-as-full,
NaN/Inf/missing CDM, wrong scale, stale/wrong save_name).
Updated: `test_windows_reproduce.py` (new orchestrator surface),
`test_full_verify_params.py` (new knobs), `test_prediction_validator.py`
(stats v2).

### 2.11 Compatibility

`cpu-smoke-10` keeps identical prediction dir, manifest name, configs,
save_name, port, and phase display names. `-Profile`/`-Resume`/
`-ForceInference`/`-SkipCdmSetup`/`-DryRun`/`-SeedFrom`/`-ServerPort` keep
their meaning. No GPU/model/CDM/1651-page work enters GitHub CI.
