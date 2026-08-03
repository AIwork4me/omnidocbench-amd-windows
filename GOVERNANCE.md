# Governance

This project is maintained by the contributors listed in
[`MAINTAINERS.md`](MAINTAINERS.md) on a best-effort, open-source basis.

## Decision-making

- **Trivial changes** (docs, typos, test-only fixes): merged by any maintainer
  after CI passes.
- **Behavioral changes** (orchestrator state machine, fingerprints, profile
  contracts, adapter contract): require a changelog entry and the executable
  tests that prove the new behavior (see `docs/deprecation-policy.md`); merged
  after review by at least one maintainer.
- **Benchmark claims**: governed by `docs/benchmark-evidence-policy.md`. No
  maintainer may upgrade an evidence level without the corresponding run
  record.
- **Releases**: tag-driven, gated by `scripts/release-gate.ps1` (see
  `RELEASE.md`).

## Scope

The repository's scope is the Windows + AMD (ROCm/HIP) OmniDocBench v1.6
evaluation infrastructure: dataset provisioning, profile-driven
reproduction, scoring, CDM, evidence and adapters. Upstream bugs belong to
their upstream projects (e.g. PaddlePaddle/PaddleOCR#18248).

## Code of conduct

All interactions are governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Conflict resolution

Disagreements are resolved by discussion in issues/PRs; if no consensus is
reached the maintainers decide, documenting the reasoning in the issue.

## Deprecations

Removals follow [`docs/deprecation-policy.md`](docs/deprecation-policy.md).
