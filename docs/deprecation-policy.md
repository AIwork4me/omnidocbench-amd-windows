# Deprecation Policy

This repository supports three stable profile contracts plus the adapter
manifest contract. Removing or changing them follows the rules below so that
published evidence stays reproducible.

## Policy

1. **Deprecation announcement.** A feature/flag/profile/CLI surface marked for
   removal is announced in `CHANGELOG.md` under `[Unreleased]` → `Deprecated`
   and stays functional for at least **one minor release**.

2. **Removal.** The actual removal happens in a minor or major release and is
   recorded in the changelog's `Removed` section.

3. **Formal profiles are never silently changed.** The three formal profiles
   (`cpu-smoke-10`, `hip-smoke-10`, `paddleocr-vl-hip-full-1651`) and their CLI
   surface (`-Profile`, `-ListProfiles`, `-Resume`, `-ForceInference`,
   `-DryRun`, `-SeedFrom`, `-ServerPort`, `-SkipCdmSetup`) may only change with
   a changelog entry explaining the compatibility impact.

4. **Adapter manifests.** Adapter manifest `contract_version` bumps are
   additive: new optional keys are allowed within a version; removing or
   reinterpreting a key requires a contract_version bump and a conformance
   test update.

5. **Evidence.** Benchmark rows are never deleted; superseded rows are
   annotated with their date and evidence level (see
   `docs/benchmark-evidence-policy.md`).

6. **Behavioral changes are test-first.** Any change to the state machine
   (resume, fingerprints, invalidation) must ship with the executable
   integration tests that exercise it.
