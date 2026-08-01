# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- CI: pytest (3.10/3.11 matrix) + PSScriptAnalyzer on windows-latest.
- CI: unified workflow on main (uv pytest matrix) + PSScriptAnalyzer job (this branch).
- Guard tests: README EN/ZH metric consistency, markdown relative links,
  scoring-config existence, full-verify.ps1 parameter surface.
- `CHANGELOG.md`.

### Fixed
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
