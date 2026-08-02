# Reproduction Profiles Implementation Plan

> **For agentic workers:** Spec: `docs/superpowers/specs/2026-08-02-reproduction-profiles.md`. Executed inline in the main session (decision recorded: the audit context is session-local; subagent handoffs would lose it). TDD per task; commit per task.

**Goal:** Turn `scripts/reproduce.ps1` from a cpu-smoke-10-only script into a profile-driven orchestrator with three profiles (`cpu-smoke-10`, `hip-smoke-10`, `paddleocr-vl-hip-full-1651`), per-page resume, HIP backend proof, strict full-set acceptance, and evidence packs.

**Architecture:** Declarative JSON profiles validated by a PS library + pytest; orchestrator stages keyed by stable IDs; fingerprint-gated resume; adapter `--skip-existing` with stats schema v2; backend-proof and strict-verification as standalone fixture-testable scripts.

**Tech Stack:** PowerShell 5.1-compatible scripts, Python 3.10/3.11 (pytest), JSON profiles, existing uv/pytest/PSScriptAnalyzer CI.

## Global Constraints

- PowerShell 5.1 syntax only (no `??`, no ternary, `?.`).
- No new runtime dependencies; test deps only if locked in `pyproject.toml`/`uv.lock`.
- Existing commands keep working: `reproduce.ps1 -Profile cpu-smoke-10` semantics unchanged.
- Fail-closed everywhere; no silent CPU fallback for HIP profiles; no stale-result passes.
- Raw metric scale (0–1) in profiles and assertions.
- `@()` wrap before `.Count` on pipeline results (PS 5.1).

---

### Task 1: Profile JSON files + scoring configs

**Files:**
- Create: `scripts/profiles/cpu-smoke-10.profile.json`, `scripts/profiles/hip-smoke-10.profile.json`, `scripts/profiles/paddleocr-vl-hip-full-1651.profile.json`
- Create: `eval-infra/01-omnidocbench/configs/v16-hip-smoke-10.yaml`, `v16-cdm-hip-smoke-10.yaml`, `v16-hip-full-1651.yaml`, `v16-cdm-hip-full-1651.yaml`
- Test: `tests/test_reproduction_profiles.py`

**Interfaces (profile schema v1):** keys `schema_version, name, description, run_kind(smoke|subset|full), model, adapter, engine, variant, expected_pages(int), max_pages(int|null), prediction_dir(repo-rel), prediction_manifest(repo-rel), owned_manifest(bool), windows_scoring_config, wsl_cdm_config, score_save_name, server_port(string), minimum_prediction_coverage(float), maximum_failed_pages(int), require_gpu_backend_proof(bool), require_wsl_cdm(bool), metric_thresholds{text_edit_dist_max, reading_order_edit_dist_max, teds_min, cdm_min}, expected_runtime_class`.

- [ ] Step 1: failing pytest validating the 3 profiles exist, schema, uniqueness, full/hip invariants, YAML binding (data_path suffixes, save_name == basename+"_quick_match").
- [ ] Step 2: run `uv run pytest tests/test_reproduction_profiles.py` → FAIL.
- [ ] Step 3: write the 3 JSON profiles + 4 YAML configs (clone smoke/full patterns; full thresholds: text 0.10, RO 0.20, teds 0.85, cdm 0.85; smoke thresholds loose: text 0.60, RO 0.60, teds 0.0, cdm 0.0 — smoke gates validity not accuracy; hip-smoke same shape as cpu-smoke).
- [ ] Step 4: tests PASS.
- [ ] Step 5: commit `feat: add reproduction profile definitions + scoring configs`.

### Task 2: Profile loader library + `-ListProfiles`/`-DryRun`

**Files:**
- Create: `scripts/repro-profiles.ps1` (`Get-ProfileCatalog`, `Get-ReproProfile -Name`, `Format-ProfileList`, `Show-ResolvedProfile`)
- Modify: `scripts/reproduce.ps1` (param block: remove ValidateSet, add `-ListProfiles`; load profile; keep everything else temporarily)
- Test: `tests/test_reproduction_profiles.py` (extend: `-ListProfiles` lists 3, invalid profile exits non-zero listing valid ones, DryRun prints resolved fields)

**Interfaces:** `Get-ReproProfile` returns PSCustomObject with resolved absolute paths added (`PredictionDirAbs`, `ManifestAbs`, `EvidenceDir`, `WindowsResultPath`, `StateFile`, `SaveName`).

- [ ] Steps: failing tests (subprocess powershell, no network) → implement → pass → commit.

### Task 3: Orchestrator refactor to stable stage IDs + evidence skeleton

**Files:**
- Modify: `scripts/reproduce.ps1` (Invoke-Stage -Id/-Name/-AlwaysRun; state schema v2 with stage IDs; reject v1 state on resume; per-stage evidence fields)
- Create: `scripts/repro-evidence.ps1` (`Save-JsonAtomic`, `Write-HardwareInfo`, `Write-ArtifactHashes`, `Write-Report`)
- Test: `tests/test_windows_reproduce.py` (rewrite), `tests/test_reproduction_profiles.py` (dry-run stage IDs ordered)

- [ ] Steps: failing tests → implement → pass → commit. cpu-smoke-10 must still DryRun identically ordered.

### Task 4: Adapter `--skip-existing` + stats schema v2

**Files:**
- Modify: `adapters/paddleocr-vl-1.6/run_adapter.py`
- Test: `tests/test_adapter_resume.py` (new), keep `tests/test_paddleocr_vl_adapter.py` green

**Interfaces:** `run_lightweight_folder(..., skip_existing: bool = False)`; stats v2 as spec'd; `_prediction_is_reusable(path) -> bool`; summary keys `count, ok, fail, engine, stats` preserved + `newly_processed, skipped_existing, failed_pages, schema_version`. Atomic per-page stats write `_write_stats_atomic`. v1 stats upgrade reader `_load_prior_stats`.

- [ ] Steps: failing tests (fake pipeline via sys.modules stub; partial→kill→resume; invalid file regenerated; valid untouched; counters) → implement → pass → commit.

### Task 5: Fingerprint script

**Files:**
- Create: `scripts/compute_fingerprint.py` (`build_fingerprint(root, profile_path, manifest, configs, pipeline_dir) -> dict`; CLI `--out x.json` / `--check prev.json`)
- Test: `tests/test_fingerprint.py`

- [ ] Steps: failing tests (each key mismatch detected; dirty-tree flag; missing pipeline tolerated→"absent") → implement → pass → commit.

### Task 6: HIP backend proof

**Files:**
- Create: `adapters/paddleocr-vl-1.6/01-vlm-server/assert-backend-proof.ps1`
- Modify: `adapters/paddleocr-vl-1.6/01-vlm-server/verify.ps1` (`-ExpectedVariant`, `-Port`, delegate), `setup.ps1` (repair missing `.variant` when exe present; write `.variant` always after Phase 1 skip path)
- Create fixtures: `tests/fixtures/backend-proof/{hip,cpu,truncated}/...`
- Test: `tests/test_backend_proof.py`
- Modify: `scripts/preflight.ps1` (860M/gfx1152 HIP fail-closed)

- [ ] Steps: failing fixture tests → implement → pass → commit.

### Task 7: Strict prediction-set + metric verification

**Files:**
- Create: `scripts/verify_prediction_set.py`
- Modify: `scripts/full-verify.ps1` (`-ExpectedPages`, `-MinCoverage`, `-MaxFailedPages`, `-RequireRunStatsSelected`; defaults preserve current 95% behavior; delegates strict checks to verify_prediction_set.py)
- Create: `scripts/assert-metrics.ps1` (`-MetricResult`, `-Profile` or explicit thresholds; freshness check via `-NotOlderThan`)
- Test: `tests/test_prediction_set_verify.py`, `tests/test_assert_metrics.py`, `tests/test_full_verify_params.py` (extend)

- [ ] Steps: failing boundary tests (1651/1649/1648/1600/1001, subset-not-full, NaN/Inf/missing-CDM/wrong-scale/stale) → implement → pass → commit.

### Task 8: Orchestrator integration (inference/scoring/verification/evidence stages)

**Files:**
- Modify: `scripts/reproduce.ps1` (profile-driven variants everywhere; fingerprint write+check; `--skip-existing` on resume; strict verify params for full; assert-metrics; evidence pack finalization; `-ForceInference` scoped cleanup incl. WSL result root)

- [ ] Steps: extend dry-run/integration tests → implement → `uv run pytest -q` green → commit.

### Task 9: CI/static gates + docs

**Files:**
- Modify: `README.md`, `README.zh-CN.md`, `AGENTS.md`, `docs/architecture.md`, `CHANGELOG.md`, `tests/test_windows_reproduce.py` compat, `tests/test_readme_consistency.py` if needed
- Run: `uv sync --locked --all-groups`, `uv run pytest -q`, PS parse all, PSScriptAnalyzer Error level, `bash -n` all .sh

### Task 10: Real-machine validation

DryRun ×3 → hip-smoke-10 full run + `-Resume` → `paddleocr-vl-hip-full-1651` full run + `-Resume` → compare vs README reference.

### Task 11: Independent code review

Dispatch review subagent against the §15 checklist; fix; re-run gates.

---

## Self-review notes

- Spec coverage: §3 profiles (T1), §4 architecture/ListProfiles/DryRun (T1–T3), §5 stage IDs (T3), §6 resume (T4–T5, T8), §7 HIP proof (T6), §8 strict acceptance (T7), §9 scoring binding (T1, T7, T8), §10 evidence (T3, T8), §11 tests (per-task), §12 CI (T9), §13 real machine (T10), §14 docs (T9), §15 review (T11).
- Type consistency: `Get-ReproProfile` fields consumed in T3/T8; stats v2 keys consumed by verify_prediction_set.py in T7 (`selected_pages`, `pages` map); fingerprint CLI contract consumed in T8.
