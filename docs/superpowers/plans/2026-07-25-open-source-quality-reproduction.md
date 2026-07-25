# Open-Source Quality And Reproduction Plan

> Execution rule: complete tasks in order. Run the stated gate immediately
> after each change or setup step. Do not proceed while a mandatory gate is
> failing. Record commands, exit codes, versions, and non-secret evidence in
> `docs/reproduction-2026-07-25.md` as the work proceeds.

**Goal:** Turn this repository into a reviewed, reproducible, community-ready
OmniDocBench v1.6 project whose Windows + AMD reference path has been executed
from a clean clone and proven to produce valid, non-degenerate scores.

**Quality standard:** A new user should receive an actionable prerequisite
failure before any long download, be able to resume every setup stage, run one
documented path without guessing directories or commands, and independently
verify the resulting environment, predictions, metrics, and benchmark report.

**Architecture:** Preserve the existing model-agnostic boundary:
`adapters/` produces Markdown, `eval-infra/` owns evaluation, and `scripts/`
owns orchestration. Improve the gates and user journey around those boundaries
instead of duplicating model or scorer logic.

## Global Constraints

- Preserve PowerShell 5.1 compatibility and setup idempotency.
- Keep `PYTHONUTF8=1` on every Windows scoring path.
- Never commit datasets, models, predictions, virtual environments, generated
  upstream checkouts, credentials, tokens, or machine-specific paths.
- Do not rewrite or discard user changes. Do not commit or push unless the user
  explicitly requests it.
- Use Python 3.10 or 3.11 for OmniDocBench. Unsupported Python must fail before
  virtual-environment creation, dependency installation, or scoring.
- Treat setup and verification as pairs. A setup task is incomplete until its
  corresponding verifier exits 0 and its evidence is recorded.
- Follow the four exact human-intervention messages in `AGENTS.md`. Stop at a
  reboot, UAC, network, or GPU-confirmation boundary instead of bypassing it.
- Use WSL CDM as the compatibility/reference reproduction path. Validate the
  Windows-native CDM path separately when its native prerequisites are present.
- Do not publish or describe a run as reproduced unless it reaches real
  predictions and finite metrics. CDM, when selected, must be present and
  positive.

## Definition Of Done

- The repository's own fast tests pass from a clean clone.
- Public instructions, scripts, configs, and verifiers agree on paths, engine
  names, supported versions, expected artifacts, and success criteria.
- Fresh-machine preflight catches unsupported Python, missing Git, insufficient
  disk, unusable WSL, unwritable/unsafe paths, and unavailable download sources
  before expensive setup.
- Each setup script is safe to re-run after a partial failure.
- The reference adapter produces Markdown for at least 95% of dataset pages,
  reports failures, and passes an explicit output-contract validator.
- Non-CDM scoring produces all mandatory finite, non-negative metrics.
- The selected CDM path produces a finite, positive CDM score.
- A benchmark run produces a report accepted by its verifier.
- A dated reproduction report records machine/software versions, commands,
  exit codes, artifact counts, scores, deviations, and unresolved limitations.
- Community health files and contributor instructions make support,
  vulnerability reporting, testing, and pull-request expectations explicit.

---

## Phase 0: Baseline And Evidence Discipline

### Task 0.1: Establish the immutable baseline

- [x] Record `git status`, current commit/tag, remote URL, Windows version,
  PowerShell version, CPU/RAM/disk, GPU/driver, Python installations, Git,
  GitHub CLI, and WSL state without exposing tokens.
- [x] Create `docs/reproduction-2026-07-25.md` with an evidence table whose
  initial status is `NOT RUN`, not assumed success.
- [x] Confirm generated artifacts are ignored before any setup runs.

**Gate:** Worktree starts clean except for this plan/evidence work; remote is
`AIwork4me/omnidocbench-amd-windows`; no secret appears in captured output.

### Task 0.2: Run the fast repository baseline

- [ ] Compile all tracked Python files that do not require generated upstream
  dependencies.
- [ ] Run the complete configured pytest collection.
- [ ] Parse every tracked YAML and JSON file.
- [ ] Parse PowerShell scripts without executing installers.
- [ ] Check Markdown links and referenced local paths with a deterministic
  repository test rather than an ad hoc manual list.

**Gate:** Every fast check passes, or each pre-existing failure is recorded as
a finding before it is changed.

---

## Phase 1: Whole-Repository Review

### Task 1.1: Review behavior and ownership boundaries

- [x] Review every setup/verify pair for idempotency, partial-failure recovery,
  deterministic exit codes, actionable errors, and path quoting.
- [x] Review adapters for output-contract enforcement, UTF-8 handling,
  per-page failure behavior, retry behavior, and prediction completeness.
- [x] Review scoring configs and scripts for placeholder resolution, required
  input validation, result disambiguation, finite metric checks, and hard/full
  subset semantics.
- [x] Review benchmark monitoring/reporting for GPU-data availability,
  interrupted runs, stability statistics, and verifier coverage.
- [x] Review documentation for contradictions, stale scores, dead links,
  unsupported claims, hidden prerequisites, and English/Chinese parity.
- [x] Review repository/community metadata: license clarity, upstream data/model
  licensing, security reporting, code of conduct, issue/PR templates,
  contribution workflow, release provenance, and lightweight CI suitability.

### Task 1.2: Publish the review findings

- [x] Create `docs/open-source-quality-review-2026-07-25.md`.
- [x] List findings by severity with file/line evidence, user impact, root
  cause, proposed correction, and validation method.
- [x] Distinguish verified defects from recommendations and explicitly correct
  false positives discovered during review.

**Gate:** Every proposed code change maps to a documented finding and a test or
executable verification step. No broad refactor is approved without a concrete
reproducibility or community benefit.

---

## Phase 2: Fail Fast Before Expensive Work

### Task 2.1: Add a first-class Windows preflight

- [x] Add a PowerShell 5.1-compatible preflight command that checks supported
  Windows/PowerShell, Git, Python 3.10/3.11, writable paths, path hazards,
  available disk, network source status, WSL state, and optional AMD GPU/CDM
  prerequisites.
- [x] Separate mandatory failures from path-specific warnings so CPU, WSL CDM,
  and native CDM choices remain explicit.
- [x] Add focused tests for supported/unsupported Python and missing-tool cases.
- [x] Link the command from both READMEs and `AGENTS.md` as Step 0 before setup.

**Gate:** Tests prove unsupported Python and missing mandatory tools exit 1
with the exact corrective action; a valid machine exits 0 for its selected
path.

### Task 2.2: Harden setup and scoring entry points

- [x] Make `01-omnidocbench/setup.ps1` stop when Python 3.10/3.11 is absent
  instead of creating a known-incompatible environment.
- [x] Validate the selected Python interpreter and required config input paths
  in `03-scoring/score.ps1` before materializing or launching a run.
- [ ] Make hard-subset derivation fail when its source schema yields no usable
  pages; verify the generated manifest count and image references.
- [ ] Preserve tiny-fixture support by making full-run completeness thresholds
  explicit rather than globally rejecting small intentional tests.
- [ ] Add regression tests for every new failure mode.

**Gate:** Focused tests fail on the old behavior and pass on the corrected
behavior; the complete fast suite remains green.

### Task 2.3: Enforce the adapter output contract

- [x] Add a reusable validator for expected image stems, Markdown count,
  UTF-8 readability, empty output, duplicate/case-colliding names, and the
  adapter error log.
- [x] Invoke or document it immediately after reference inference and in the
  adapter contribution template.
- [x] Test complete, partial, malformed, and intentionally tiny outputs.

**Gate:** A complete fixture passes; missing, non-UTF-8, and empty prediction
fixtures fail with page-level diagnostics.

---

## Phase 3: Community And Automation Quality

### Task 3.1: Make the contributor path self-verifying

- [ ] Expand `CONTRIBUTING.md` with supported developer versions, one fast test
  command, script compatibility rules, setup/verify pairing, documentation
  parity, and a pull-request checklist.
- [ ] Add missing community health files where they provide real value:
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, and a pull-request template.
- [ ] Clarify upstream code, dataset, model, and generated-artifact licensing;
  do not claim rights the project does not hold.

### Task 3.2: Add lightweight continuous verification

- [ ] Add CI only for deterministic, non-GPU, non-dataset checks: Python unit
  tests, structured-data parsing, documentation links, and PowerShell syntax.
- [ ] Pin action major versions and the supported Python matrix. Do not pretend
  hosted CI validates AMD GPU, WSL CDM, or full benchmark reproduction.
- [ ] Document the boundary between CI evidence and physical-machine evidence.

**Gate:** The local equivalents of every CI job pass, workflow syntax is valid,
and no job downloads the benchmark dataset or model weights.

---

## Phase 4: Reproduce Step 0 And Step 1

### Task 4.1: Network and mirror detection

- [x] Run `scripts/detect-mirrors.ps1`.
- [x] Inspect `mirrors.env` without recording secrets and verify mandatory
  source values are usable, not comments/placeholders.
- [x] Re-run detection to prove idempotency.

**Gate:** Both runs exit 0 and `NETWORK_STATUS` is acceptable for the chosen
path. If no GitHub or dataset source is reachable, stop with human point 4.

### Task 4.2: WSL availability

- [x] Run `scripts/wsl-ensure.ps1`, then `wsl -d Ubuntu2204 -- echo OK`.
- [x] Re-run the setup to prove it is non-destructive.

**Gate:** The canonical distro starts and prints `OK`. If activation requires a
reboot, stop with human point 1. If UAC appears, stop with human point 3.

### Task 4.3: OmniDocBench code, patches, environment, and dataset

- [x] Run `eval-infra/01-omnidocbench/setup.ps1`.
- [x] Immediately run `eval-infra/01-omnidocbench/verify.ps1`.
- [x] Record Python/venv versions, upstream commit, applied patch checks,
  manifest hash, image count, and disk use.
- [x] Re-run setup and verify to prove idempotency.

**Gate:** Verify exits 0, the expected full manifest and approximately 1651
page images exist, the supported venv imports dependencies, and tracked patches
are verifiably applied.

---

## Phase 5: Reproduce CDM Toolchains

### Task 5.1: WSL compatibility/reference CDM

- [ ] Run WSL `02-cdm-environment/setup.sh` using the actual repository path.
- [ ] Immediately run `02-cdm-environment/verify.sh`.
- [ ] Re-run setup and verify to prove all nine setup stages resume/skip safely.

**Gate:** Exit 0 plus the literal `VERIFY OK`; the end-to-end CJK formula smoke
test produces a color PNG and positive identical-formula CDM F1.

### Task 5.2: Windows-native CDM, when prerequisites are available

- [ ] Run `verify-windows.ps1` before selecting native scoring.
- [ ] Record TeX Live, ImageMagick, Ghostscript, patch-sentinel, and smoke-test
  evidence. Fix only failures covered by `docs/pitfalls.md`; add newly proven
  failure modes there with Symptom -> Root Cause -> Fix -> Verify.

**Gate:** `VERIFY OK` and positive identical-formula F1. If unavailable, record
the native path as not selected; do not block the verified WSL path.

---

## Phase 6: Reproduce The Reference Adapter

### Task 6.1: Provision and verify model components

- [ ] Run VLM server setup with `-Variant hip`, then its verifier.
- [ ] Stop for human point 2 to confirm real GPU utilization and server
  stability before inference.
- [ ] Run layout-model setup, then its verifier.
- [ ] Run dependency setup and a focused import/version smoke test.
- [ ] Re-run each setup/verify pair to prove idempotency.

**Gate:** VLM `/v1/models` returns 200, GPU use is human-confirmed, layout ONNX
verification passes, and adapter imports succeed in the intended environment.

### Task 6.2: Run inference and validate predictions

- [ ] Run the reference adapter into the exact config-consumed directory
  `predictions/paddleocrvl_rocm`.
- [ ] Preserve per-page errors and runtime statistics.
- [ ] Run the adapter output validator from Task 2.3.

**Gate:** At least 95% of full dataset pages have non-empty UTF-8 Markdown,
errors are enumerated, and the adapter exits non-zero if its documented fatal
failure threshold is crossed.

---

## Phase 7: Reproduce Scoring And Benchmark Evidence

### Task 7.1: Non-CDM scoring

- [ ] Run `03-scoring/score.ps1`, then `03-scoring/verify.ps1` against the
  explicit result file/save name rather than an ambiguous newest artifact.
- [ ] Record raw metric JSON hash, sample counts, timeout/exception counters,
  runtime, and reported aggregation convention.

**Gate:** All mandatory metrics are present, numeric, finite, and non-negative;
full-run values meet the documented reproduction thresholds.

### Task 7.2: CDM scoring

- [ ] Run the selected WSL reference CDM score path and verify with
  `-WslOnly -RequireCdm`.
- [ ] If native CDM passed Task 5.2, run native CDM scoring and verify with
  `-WindowsOnly -RequireCdm`.
- [ ] Run Formula CDM diagnostics for any zero, missing, timeout, or exception
  condition and update the pitfall decision tree only with reproduced facts.

**Gate:** Selected CDM result is present, numeric, finite, positive, and above
the documented threshold; sample counts and failures are recorded.

### Task 7.3: Full verification and benchmark

- [ ] Run the appropriate `scripts/full-verify.ps1` mode for every selected
  toolchain path.
- [ ] Run one benchmark and verify its report.
- [ ] Run stability mode only after the single-run report passes and resources
  permit; report variance rather than cherry-picking the best run.

**Gate:** Full verify exits 0, benchmark verify exits 0, and the capability
report contains CPU, memory, timing, metric, and available GPU evidence.

---

## Phase 8: Documentation, Release Readiness, And Final Audit

### Task 8.1: Replace assumptions with reproduced instructions

- [ ] Update English and Chinese READMEs together with the tested happy path,
  preflight, resume behavior, expected durations/disk, verification commands,
  and explicit human-intervention points.
- [ ] Ensure every public score links to dated evidence and states engine,
  config, aggregation, dataset version, machine class, and known deviations.
- [ ] Remove or qualify claims that this machine did not reproduce.
- [ ] Keep `AGENTS.md` orchestration-only; place fixes in `docs/pitfalls.md`.

### Task 8.2: Final clean-clone simulation

- [ ] Run all fast tests and local CI equivalents.
- [ ] Run documentation/config consistency checks.
- [ ] Re-run full verification without relying on an ambiguous latest artifact.
- [ ] Inspect tracked changes, ignored generated files, and repository size.
- [ ] Perform a final severity-ordered code review of the resulting diff.

**Gate:** No unresolved critical/high finding; all selected-path verifiers pass;
the reproduction report is complete; generated artifacts and secrets remain
untracked; limitations and skipped optional paths are explicit.

## Expected Deliverables

1. This checked execution plan with incremental status updates.
2. A severity-ordered repository quality review.
3. Focused code/tests that remove reproduced friction points.
4. Community health and contributor workflow improvements.
5. A dated machine-readable/human-readable reproduction evidence report.
6. Passing fast tests, selected setup verifiers, scoring verification, full
   verification, and benchmark verification.
7. A final summary explaining each optimization in terms of user impact and
   the executable evidence that proves it.