# Support

## Where to get help

- **Documentation first**: [`README.md`](README.md),
  [`docs/architecture.md`](docs/architecture.md), and the debugging knowledge
  base [`docs/pitfalls.md`](docs/pitfalls.md) cover the common failure modes
  (WSL, ImageMagick, CDM-zero, network mirrors, …).
- **Issues**: report bugs and ask questions in the GitHub issue tracker
  (https://github.com/AIwork4me/omnidocbench-amd-windows/issues). Include the
  exact profile name, the failing stage id from
  `outputs/reproduction/<profile>/state.json`, and the error text.
- **Security issues**: do NOT open a public issue; follow
  [`SECURITY.md`](SECURITY.md).

## What we support

- Windows 10/11 with PowerShell 5.1+ (the orchestrator is PS 5.1 compatible)
- AMD Radeon GPUs with official Windows HIP builds (see
  [`docs/hardware-support.md`](docs/hardware-support.md))
- The three formal profiles and any profile built on the adapter manifest
  contract

## What we cannot support

- GPU models without official Windows ROCm/HIP builds (e.g. Radeon 860M /
  gfx1152): use the CPU variant.
- Closed networks with no reachable mirror for GitHub/HuggingFace/ModelScope:
  run `scripts/detect-mirrors.ps1` first (see `docs/pitfalls.md#network`).

## Response expectations

This is a best-effort open-source project; maintainers triage issues
periodically. Include reproduction commands from `RELEASE.md` when reporting
benchmark discrepancies.

## Community

See [`GOVERNANCE.md`](GOVERNANCE.md) for how decisions are made and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for how to contribute.
