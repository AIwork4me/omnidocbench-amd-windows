# Releasing

This repository follows a tag-driven release process. A release is only
publishable when the **release gate** passes; the gate exists so benchmark
claims, versions, manifests and evidence stay auditable.

## Versioning

The single version source is `pyproject.toml` (`version = "1.0.0"`); the same
version is mirrored in `uv.lock` and `CITATION.cff`. The changelog follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with `## [x.y.z] -
<date>` sections.

## How to release

1. Update `CHANGELOG.md` with the unreleased changes under the new version.
2. Bump `version` in `pyproject.toml` (and mirror it in `uv.lock` +
   `CITATION.cff`).
3. Write release notes: `docs/release-vX.Y.Z.md` — they MUST state:
   - **Verified devices** (exact GPU/CPU, driver, ROCm version)
   - **Unverified devices** (documented but not measured on this release)
   - **Known limitations** (e.g. Radeon 860M/gfx1152 has no official Windows
     HIP build; upstream peg-native failures tracked in PaddlePaddle/PaddleOCR#18248)
   - **Evidence levels** for every benchmark row (clean-room / validated
     resumed / smoke / independent)
4. Tag and run the gate:
   ```powershell
   git tag vX.Y.Z
   powershell -ExecutionPolicy Bypass -File scripts\release-gate.ps1 -Tag vX.Y.Z -WriteArtifacts
   ```
   The gate verifies: tag == version, CHANGELOG updated, tests green, README
   benchmark tables generated from `benchmarks/index.json`, benchmark evidence
   schema valid, adapter manifests valid, clean git tree, release notes
   complete. `-WriteArtifacts` additionally produces `outputs/release/<tag>/`
   with an SBOM, `SHA256SUMS` and an evidence manifest.
5. Publish the release with the SBOM + SHA256SUMS attached.

## Evidence-level rules (binding)

| Label | Required to claim |
|---|---|
| `smoke` | 10-page profile run with backend proof (HIP) |
| `validated resumed` | Full 1651-page run resumed from repo artifacts with provenance-verified inputs, fingerprints and strict prediction acceptance |
| `clean-room` | Full 1651-page run executed from a **fresh checkout** of the release commit (Release Gate run) |
| `independent` | A clean-room run executed by a **second machine** |

Claiming a level without the evidence is a release-blocking defect. No
"officially reproduced" / "independently reproduced" wording may appear
without the corresponding independent reproduction record.

## Benchmark evidence policy

See [`docs/benchmark-evidence-policy.md`](docs/benchmark-evidence-policy.md):
every number in `benchmarks/index.json` must reference an evidence document,
and display values must equal raw values × 100 under the same aggregation
convention (enforced by `scripts/validate_benchmark_index.py`).

## Deprecation policy

See [`docs/deprecation-policy.md`](docs/deprecation-policy.md) for how
profiles, adapters and CLI flags are removed.

## Support

See [`SUPPORT.md`](SUPPORT.md) for where to ask questions and report issues.
