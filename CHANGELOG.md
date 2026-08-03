# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Phase-scoped fingerprints for safe resume: provisioning / inference /
  scoring / evidence phases via `scripts/compute_fingerprint.py --phase`;
  formal (full) profiles fail closed on a dirty working tree; non-formal
  profiles bind a content hash of `git diff --binary HEAD` plus untracked
  files (further edits to an already-modified file are detected).
- Deterministic prediction-tree hashing (`scripts/hash_prediction_tree.py`):
  manifest-ordered relative path + byte length + SHA-256, no mtimes;
  missing/unexpected files and `_run_stats.json` recorded separately.
- Metric-result provenance sidecars (`<save>_metric_result.provenance.json`)
  via `scripts/metric_provenance.py`: prediction tree, manifest, config,
  scorer checkout/code, result SHA, expected pages. Resume re-validates the
  sidecar before reusing a score; a mismatch re-runs scoring.
- Prediction-change invalidation: pre/post inference tree hashes clear
  `inference.prediction_check` / `scoring.windows` / `scoring.wsl_cdm` /
  `verification.final` / `evidence.pack` passed states so stale scores are
  never reused.
- Known-failure allowlist (`allowed_failed_page_stems`) for formal profiles:
  `verify_prediction_set.py` reports `known_allowed_failures` /
  `unknown_failures` / `recovered_known_failures`, rejects unknown failed
  pages, checks `_run_stats.json` per-page status against the files and fails
  on duplicate manifest stems.
- `verify_prediction_set.py` is now the single source of truth for
  `prediction-summary.json` (canonical schema incl. `empty_gt_valid`,
  `prediction_tree_sha256`, `verdict`); the evidence pack only verifies and
  copies it (smoke profiles use the same verifier).
- Adapter manifests (`adapters/<adapter>/adapter.json`) with
  `scripts/validate_adapter_manifest.py` (schema + repo-relative path safety);
  the orchestrator runs only the lifecycle stages an adapter declares.
- `mineru-pipeline-hip-smoke` profile with a documented human-intervention
  gate (Python 3.12 + ROCm torch; never pretends to be unattended).
- Benchmark single source of truth: `benchmarks/schema.json`,
  `benchmarks/index.json`, `scripts/validate_benchmark_index.py` and
  `scripts/render_benchmark_tables.py` (README tables generated, CI drift
  check). The 2026-08-03 full-set row is labelled **validated resumed**.
- Release gate `scripts/release-gate.ps1` (version/tag, CHANGELOG, tests,
  table drift, benchmark/adapter schema, clean tree, release notes) with
  optional SBOM/SHA256SUMS/evidence manifest; `CITATION.cff`, `RELEASE.md`,
  `SUPPORT.md`, `GOVERNANCE.md`, `MAINTAINERS.md`,
  `docs/benchmark-evidence-policy.md`, `docs/deprecation-policy.md` and the
  hardware support matrix (`docs/hardware-support.{md,json}`).
- Executable orchestrator integration tests
  (`tests/test_reproduce_harness.py`, `tests/test_repro_artifacts.py`,
  `tests/test_reproduce_harness.py`) via test-only `REPRO_*` injection
  (fake scripts/root; the formal path is unchanged) covering fresh runs,
  interrupt/resume, prediction-change invalidation, stale-provenance
  rejection, scoped ForceInference, dirty-formal rejection, empty-GT and
  allowlist gates; hardened HIP backend proof (strict layer parsing,
  Win32_Process identity, server start-time/log-freshness, one minimal
  inference request, DLL hashes) with fixture tests.
- CI hardening: Ubuntu pure-Python jobs, Ruff/Pyright, ShellCheck,
  actionlint, benchmark drift + adapter/benchmark schema checks, dependency
  review, OpenSSF Scorecard, Dependabot, concurrency/timeouts, and a manual
  self-hosted AMD GPU HIP-smoke workflow with scrubbed evidence upload.

### Changed
- `scripts/reproduce.ps1`: unified owned-artifact path block (Fix
  `-ForceInference` referencing `$fingerprintFile` before definition),
  manifest-driven adapter lifecycle, resolved server port recorded in
  evidence, `-ServerPort` never leaks the profile default, conditional
  budget parameters.
- `scripts/assert-metrics.ps1`: `-ExpectedPages` (full denominator),
  `-ProvenanceFile` (result SHA + prediction-tree binding),
  `-MaxTimeouts/-MaxExceptions/-MaxMetricErrors`, Windows↔WSL cross-platform
  tolerance check, explicit aggregation paths.
- Canonical metrics naming in `metrics-summary.json`: pooled vs page-level
  TEDS are distinct keys (`table_teds_pooled`, `table_teds_page_avg`,
  `official_overall`); `artifact-hashes.json` now covers prediction tree,
  run stats, strict summary, backend proof, both metric results + provenance
  sidecars, state, report, profile.resolved and the resolved port.
- `build_prediction_subset.py` accepts empty predictions for empty-GT pages.
- Version single source: `pyproject.toml` bumped 0.0.0 → 1.0.0 (mirrored in
  `uv.lock`, `CITATION.cff`).

### Fixed
- Clean-checkout resume no longer fails on `pipeline_checkout_commit = null`:
  provisioning no longer binds the pipeline checkout; the inference phase
  binds it after provision.
- Resume after an early interrupt (fingerprint not yet written) computes the
  fingerprint fresh instead of throwing.
- `-AllowedFailedPageStem` passed once with comma-joined stems (PowerShell
  5.1 rejects repeated array-parameter occurrences on `-File`).
- MinerU/other adapters may declare HIP profiles without the
  llama.cpp-specific backend proof when their manifest documents the
  capability gap.

### Deprecated
- `scripts/validate_predictions.py` remains for CLI compatibility; the
  orchestrator uses `verify_prediction_set.py` for every profile.

### Added (reproduction profiles system)
- Profile-driven reproduction system: declarative profiles in
  `scripts/profiles/*.profile.json` (`cpu-smoke-10`, `hip-smoke-10`,
  `paddleocr-vl-hip-full-1651`, `mineru-pipeline-hip-smoke`) with schema
  validation in `scripts/repro-profiles.ps1`, `-ListProfiles`, `-DryRun` and
  stable machine-readable stage IDs in `scripts/reproduce.ps1`.
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
- Sample prediction equivalence check (`scripts/sample_prediction_equivalence.py`):
  deterministic stride sampling, re-infers a sample with the current code and
  compares content-equivalence (difflib similarity, default 0.95) against the
  stored predictions — the evidence basis for completing a run by resume after
  code changes without re-inferring the full set. Also documents that
  PaddleOCR-VL-1.6 GGUF outputs are NOT byte-reproducible across independent
  runs (glyph-level and table-structure variance).

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
- `01-vlm-server/setup.ps1` serves a deterministic model id via `--alias`
  (llama-server b9637 reports the full `-m` path verbatim otherwise).
- The WSL CDM full-set config (`v16-cdm-hip-full-1651.yaml`) uses
  `match_workers: 1 / teds_workers: 1` — WSL/Linux fork-in-fork crashes with
  `match_workers: 24` (see `docs/pitfalls.md` #wsl-fork-fork).
- `evidence.pack` marks the run passed before rendering `report.md` so the
  report shows the final verdict, not the in-flight "running" status.
- README restructured for focus: leaderboard first, single source of metrics
  truth, PaddleOCR operational details moved to the adapter README.

### Fixed
- Empty predictions are now GT-aware: OmniDocBench v1.6 contains genuinely
  empty-GT pages (figures + empty text-masks only), so an empty prediction
  for such a page is valid and reusable
  (`scripts/gt_manifest.py` consumed by `verify_prediction_set.py`,
  `validate_predictions.py`, and the adapter's `--skip-existing` resume via
  `--gt-manifest`). This flips the full 1651 run's strict gate verdict to
  PASS: 1649/1651 usable, 2 failed pages (peg-native, tracked upstream as
  PaddlePaddle/PaddleOCR#18248).
- `_run_stats.json` is now written atomically after every page, so killed
  runs keep full per-page progress and statistics.
- WSL CDM scoring raised the open-file limit (`ulimit -n 65535` in
  `score-cdm.sh`) — the 1651-page run hit WSL's default 1024-file limit
  (Errno 24) mid-match.
- README.zh-CN.md: official-local Formula CDM corrected to 96.5022 (EN parity).

### Verified (2026-08-03, AMD Ryzen AI MAX+ 395 / Radeon 8060S)
- `paddleocr-vl-hip-full-1651` official PASS: 1651 pages selected, 1649/1651
  usable (0.9988), 2 budgeted peg-native failures (upstream #18248). Windows
  text 0.035386 / RO 0.129539 / TEDS 0.929766; WSL CDM 0.966490; shared
  metrics agree Windows-vs-WSL within 0.0002. Evidence:
  `docs/reproduction-full1651-hip-2026-08-03.md`.
- `hip-smoke-10` official PASS (19/19 stages, backend proof complete);
  resume verified (25 s, 0 pages reprocessed).
  Evidence: `docs/reproduction-hip-smoke-2026-08-02.md`.

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
