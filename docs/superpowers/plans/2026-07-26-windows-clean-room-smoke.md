# AMD Windows Clean-Room Smoke Plan

> Execute in order. Every implementation step is followed immediately by its
> focused test. Do not claim clean-room success until the isolated clone has
> produced and scored ten new predictions with no repo-local generated state
> copied from the development checkout.

## Goal

Prove that a new AMD Windows user can start from a fresh clone and complete a
deterministic ten-page OmniDocBench capability run through one Windows command.
Lock every upstream input consumed by that path and fail closed when a fetched
Git checkout or binary/model artifact differs from the verified lock.

## Scope

- Platform: Windows 11 on AMD hardware.
- Profile: `cpu-smoke-10` only for this clean-room acceptance run.
- Metrics: Windows Edit-distance/TEDS plus WSL Formula CDM.
- Existing machine-global WSL/CDM installation may be reused, but the clone,
  Python environment, OmniDocBench checkout, dataset tree, adapter checkout,
  model files, predictions, subset manifest, and Windows score must be new or
  fetched into the isolated clone.
- This is a capability and provisioning test, not a new accuracy benchmark.

## Phase 1: Executable Upstream Lock

- [ ] Add a tracked machine-readable lock containing canonical source, exact
  Git commit or release tag, expected files, byte sizes, and SHA-256 hashes.
- [ ] Add PowerShell 5.1-compatible helpers to read the lock, verify files, and
  verify detached Git checkouts.
- [ ] Pin OmniDocBench and PaddleOCR-VL-ROCm clones to exact commits.
- [ ] Verify llama.cpp CPU archive/binary, GGUF/mmproj, layout ONNX/YAML, dataset
  manifest, Ubuntu rootfs fallback, and ImageMagick AppImage where applicable.
- [ ] Keep mirrors as transport alternatives only; they may not change locked
  content.

**Gate:** focused tests prove wrong Git commits and one-byte artifact corruption
exit non-zero with the component name, expected hash, and actual hash.

## Phase 2: Ten-Page Profile

- [ ] Add non-CDM and CDM config templates for an exact ten-page manifest and
  isolated prediction directory.
- [ ] Keep deterministic single-worker matching/TEDS settings.
- [ ] Use adapter `--max-pages 10`; build the exact ground truth from the ten
  successful prediction stems; require 100% prediction coverage.

**Gate:** config and adapter tests prove exactly ten sorted images are selected,
the manifest/config paths agree, and no 200-page/full-set artifact is reused.

## Phase 3: Windows Single Entry Point

- [ ] Add `scripts/reproduce.ps1 -Profile cpu-smoke-10` as the canonical human
  entry point.
- [ ] Orchestrate uv sync, mirrors, WSL availability, preflight, dataset setup
  and verify, WSL CDM setup and verify, CPU VLM setup and verify, layout setup
  and verify, dependency setup, ten-page inference, manifest build, prediction
  validation, Windows score and verify, WSL CDM score and verify, and exact
  full-chain verification.
- [ ] Persist an atomic JSON state/evidence file after every phase with command,
  exit code, duration, artifact paths, and resume command.
- [ ] Support `-Resume`, `-ForceInference`, and `-SkipCdmSetup`; never silently
  reuse predictions unless resume is explicitly requested.
- [ ] Preserve the four human-intervention boundaries in `AGENTS.md`.

**Gate:** dry-run/fixture tests verify phase order, failure propagation, resume
semantics, exact artifact binding, and PowerShell 5.1 parsing.

## Phase 4: Development-Checkout Validation

- [ ] Run the full deterministic test suite and syntax/data/doc gates.
- [ ] Run the orchestrator against existing resources in explicit resume mode
  to validate command wiring without claiming clean-room evidence.

**Gate:** all deterministic checks pass and the existing physical evidence
chain remains green.

## Phase 5: Real Isolated Clean Room

- [ ] Commit and push the implementation so the validation clone starts from a
  public immutable commit.
- [ ] Clone that commit into a new path containing spaces outside this checkout.
- [ ] Confirm the isolated clone has no `.venv`, `mirrors.env`, generated
  checkout, data, models, predictions, results, or `.env.local`.
- [ ] Run only the single entry point for `cpu-smoke-10`.
- [ ] Allow machine-global uv downloads, package caches, WSL distro, and WSL CDM
  tools, but do not copy repo-local generated artifacts from this checkout.
- [ ] Verify ten new non-empty UTF-8 predictions, exact ten-page manifest,
  finite Windows metrics, positive WSL CDM, and final chain success.
- [ ] Re-run with `-Resume` to prove idempotent recovery.

**Gate:** dated evidence records the public commit, machine/software versions,
all phase exits, durations, artifact hashes, `10/10` coverage, score sample
counts, and the explicit distinction between shared machine-global caches and
fresh repo-local outputs.

## Phase 6: Documentation And Release

- [ ] Update English/Chinese README and `AGENTS.md` to make the one-command
  profile canonical for AMD Windows smoke validation.
- [ ] Record lock update procedure and clean-room evidence.
- [ ] Re-run CI, review the final diff, commit, push, and confirm warning-free
  GitHub Actions.

## Success Criteria

1. A public commit contains the orchestrator, ten-page configs, executable lock,
   tests, and documentation.
2. The isolated clone completes through one command except for documented
   reboot/UAC/network boundaries.
3. All repo-local generated state in the clean-room run originates in that
   clone; only explicitly documented machine-global caches/toolchains are reused.
4. Every locked input is verified before execution or scoring.
5. Ten predictions and ten ground-truth pages match exactly at 100% coverage.
6. Windows mandatory metrics are finite and non-negative; WSL CDM is finite and
   positive.
7. A second `-Resume` run exits 0 without redoing completed expensive phases.