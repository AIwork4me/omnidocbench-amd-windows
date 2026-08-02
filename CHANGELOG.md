# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Profile-driven reproduction system: declarative profiles in
  `scripts/profiles/*.profile.json` (`cpu-smoke-10`, `hip-smoke-10`,
  `paddleocr-vl-hip-full-1651`), schema validation in
  `scripts/repro-profiles.ps1`, `-ListProfiles`, `-DryRun`, and stable
  machine-readable stage IDs in `scripts/reproduce.ps1`.
- Full 1651-page HIP benchmark as a single command:
  `reproduce.ps1 -Profile paddleocr-vl-hip-full-1651` with strict acceptance
  (exact manifest count, >=99.8% coverage, <=2 failed pages, selected_pages
  binding) via `scripts/verify_prediction_set.py`.
- HIP backend proof: `01-vlm-server/assert-backend-proof.ps1` (variant
  markers, HIP binary evidence, locked tag, GPU offload, log markers,
  CPU-fallback rejection) wired into `verify.ps1 -ExpectedVariant` and the
  `inference.backend_proof` stage.
- Safe per-page inference resume: adapter `--skip-existing` with stats
  schema v2 written atomically after every page; resume reuses only valid
  UTF-8 non-empty predictions and distinguishes newly-processed vs skipped.
- Fingerprint-gated resume: `scripts/compute_fingerprint.py` binds profile,
  upstream lock, dataset manifest, scoring configs, pipeline commit and repo
  state; `-ForceInference` purges only the profile's own artifacts.
- Metric sanity gates: `scripts/assert-metrics.ps1` (presence, finiteness,
  raw 0-1 scale, profile thresholds, freshness).
- Evidence packs under `outputs/reproduction/<profile>/` (state, resolved
  profile, fingerprint, hardware, backend proof, artifact hashes,
  prediction summary, metrics summary, report).
- Guard tests: profile catalog invariants, adapter resume, fingerprint,
  backend proof fixtures, strict prediction-set boundaries, metric gates.

### Changed
- `scripts/reproduce.ps1` resume keys off stable stage IDs; old v1
  state.json files are rejected with a clear "start fresh" message.
- `scripts/full-verify.ps1` gained `-ExpectedPages`, `-MinCoverage`,
  `-MaxFailedPages`, `-RequireRunStatsSelected` (defaults preserve the
  historical 95% heuristic).
- `scripts/preflight.ps1` fails closed on Radeon 860M/gfx1152 for
  `-Variant hip` instead of allowing a silent CPU fallback.
- `01-vlm-server/setup.ps1` repairs a missing `.variant` marker from the
  installed binary instead of re-downloading.
- README restructured for focus: leaderboard first, single source of metrics
  truth, PaddleOCR operational details moved to the adapter README.

### Added
- Profile-driven reproduction system: declarative profiles in
  `scripts/profiles/*.profile.json` (`cpu-smoke-10`, `hip-smoke-10`,
  `paddleocr-vl-hip-full-1651`), schema validation in
  `scripts/repro-profiles.ps1`, `-ListProfiles`, `-DryRun`, and stable
  machine-readable stage IDs in `scripts/reproduce.ps1`.
- Full 1651-page HIP benchmark as a single command:
  `reproduce.ps1 -Profile paddleocr-vl-hip-full-1651` with strict acceptance
  (exact manifest count, >=99.8% coverage, <=2 failed pages, selected_pages
  binding) via `scripts/verify_prediction_set.py`.
- HIP backend proof: `01-vlm-server/assert-backend-proof.ps1` (variant
  markers, HIP binary evidence, locked tag, GPU offload, log markers,
  CPU-fallback rejection) wired into `verify.ps1 -ExpectedVariant` and the
  `inference.backend_proof` stage.
- Safe per-page inference resume: adapter `--skip-existing` with stats
  schema v2 written atomically after every page; resume reuses only valid
  UTF-8 non-empty predictions and distinguishes newly-processed vs skipped.
- Fingerprint-gated resume: `scripts/compute_fingerprint.py` binds profile,
  upstream lock, dataset manifest, scoring configs, pipeline commit and repo
  state; `-ForceInference` purges only the profile's own artifacts.
- Metric sanity gates: `scripts/assert-metrics.ps1` (presence, finiteness,
  raw 0-1 scale, profile thresholds, freshness).
- Evidence packs under `outputs/reproduction/<profile>/` (state, resolved
  profile, fingerprint, hardware, backend proof, artifact hashes,
  prediction summary, metrics summary, report).
- Guard tests: profile catalog invariants, adapter resume, fingerprint,
  backend proof fixtures, strict prediction-set boundaries, metric gates.
- CI: unified workflow on main — uv pytest matrix (3.10/3.11, windows-latest)
  + PSScriptAnalyzer Error-gate.
- Guard tests: README EN/ZH metric consistency, markdown relative links,
  scoring-config existence, full-verify.ps1 parameter surface.
- `CHANGELOG.md`.

### Fixed
- `_run_stats.json` is now written atomically after every page, so killed
  runs keep full per-page progress and statistics.
- README.zh-CN.md: official-local Formula CDM corrected to 96.5022 (EN parity).

## [1.0.0] - 2026-07-16

### Added
- Paired v16 Lightweight/Official published scores (Overall 95.99, Formula CDM 97.36).
- G4 inference speedup evidence: 1.7x (27-page stratified benchmark).
- Windows-native CDM path (`patches/omnidocbench/windows-cdm.patch` +
  `eval-infra/02-cdm-environment/verify-windows.ps1`), verified 2026-07-11.

## [0.9.0] - 2026-07-09

### Added
- First validated full-set release: PaddleOCR-VL-1.6 on OmniDocBench v1.6,
  Windows + AMD Radeon (ROCm/HIP), all four metrics.
- Idempotent setup/verify pipeline (`eval-infra/01..04`), `AGENTS.md`
  orchestration, symptom-indexed `docs/pitfalls.md`.
