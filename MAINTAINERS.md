# Maintainers

> Placeholder identity note: this file must be filled with the real
> maintainer handles/emails by the project owner before public release.
> Do not invent identities.

| Role | Handle | Contact | Timezone |
|---|---|---|---|
| Project owner / primary maintainer | AIwork4me | (via GitHub) | — |

## Responsibilities

- Triage issues and review PRs against `GOVERNANCE.md` and
  `docs/benchmark-evidence-policy.md`.
- Own the release process (`RELEASE.md`, `scripts/release-gate.ps1`).
- Keep the hardware support matrix (`docs/hardware-support.md`) accurate.
- Enforce the evidence policy: no benchmark row without evidence, no evidence
  level upgrade without the corresponding run.

## Adding a maintainer

Proposed by any maintainer, confirmed by the project owner, recorded in this
file with the contributor's consent.

## Onboarding a new maintainer

1. Read `AGENTS.md`, `docs/architecture.md`, `docs/pitfalls.md`,
   `RELEASE.md`, `GOVERNANCE.md`, `docs/benchmark-evidence-policy.md`.
2. Run `cpu-smoke-10` on the target machine (see README Quick Start).
3. Review the integration harness (`tests/test_reproduce_harness.py`) and the
   evidence-pack layout (`outputs/reproduction/<profile>/`).
