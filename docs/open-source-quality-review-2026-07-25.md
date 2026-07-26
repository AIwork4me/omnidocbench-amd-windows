# Open-Source Quality Review - 2026-07-25

This review evaluates the repository as a community-facing reproduction system,
not only as a collection of scripts. Findings are based on executable tests or
direct control-flow evidence. Recommendations are kept separate from verified
defects.

## Executive Summary

The repository already has unusually strong foundations for hardware-dependent
evaluation: setup scripts are generally idempotent, Windows/WSL ownership is
clear, known failures are indexed by symptom, and scoring has dedicated
verifiers. The largest risks were not in the core metrics. They were breaks in
the evidence chain around those metrics: a benchmark could infer into one
prediction directory and score another, failed stages could continue, and
malformed metric values could enter verification or reports.

The changes in this review establish a stricter invariant:

> Every published result must be traceable to one explicit prediction directory,
> one exact metric file, one declared hardware platform, and a verifier that
> rejects malformed or non-finite values.

## Verified Defects

### High - Benchmark inference and scoring consumed different predictions

**Evidence:** `eval-infra/04-benchmark/run.ps1` wrote adapter output under a
benchmark-specific directory, while `v16.yaml` and `v16-cdm.yaml` pointed at
fixed reference directories. The script then searched multiple result trees for
a recent metric file. A report could therefore combine current timing/resource
data with scores from an older prediction set.

**User impact:** A benchmark report could look complete and internally
plausible without measuring the inference run it claimed to describe.

**Correction:** `score.ps1` and `score-cdm.sh` now accept an explicit prediction
directory. Each benchmark repetition gets a unique output directory; both
scorers consume it; the expected save name is computed deterministically; the
exact WSL CDM metric file is verified and copied into the run evidence folder.

**Validation:** PowerShell AST parsing passes, Bash syntax parsing passes, and
the complete Python suite passes.

### High - Benchmark continued after failed inference or scoring

**Evidence:** `eval-infra/04-benchmark/run.ps1` printed warnings for non-zero
adapter/scorer exits and continued toward report generation. It also allowed a
missing `_run_stats.json`.

**User impact:** A partial or failed run could produce a report from stale files,
turning an operational failure into misleading evidence.

**Correction:** Adapter, Windows scoring, WSL CDM scoring, scoring verification,
statistics generation, and report generation are now mandatory gates. Any
non-zero exit or missing required artifact stops the run.

**Validation:** Script parses under Windows PowerShell 5.1; static diagnostics
report no errors. Full physical validation remains gated on WSL/model setup.

### High - Mandatory metrics accepted schema-invalid `"NaN"`

**Evidence:** `eval-infra/03-scoring/verify.ps1` cast mandatory values directly
to `[double]`. Windows PowerShell accepts `[double]'NaN'`, after which both the
negative and zero checks are false and verification could end with `VERIFY OK`.
A focused regression reproduced the bypass before the fix.

**User impact:** Corrupted metric JSON could pass the project's primary scoring
gate.

**Correction:** Every mandatory metric must now be a JSON numeric type, finite,
and non-negative. Diagnostics identify the exact metric.

**Validation:** Focused regressions pass; the full Windows scoring/CDM test file
passes (`37 passed` at the time of the focused run).

### High - Benchmark report accepted invalid metric values

**Evidence:** `eval-infra/04-benchmark/report.py::extract_scores` returned raw
values. Strings, `NaN`, and infinity could reach threshold checks and Markdown
formatting.

**User impact:** The report layer had weaker validity rules than the scoring
verifier and could publish `nan`/`inf` or fail late with an opaque formatter
error.

**Correction:** Report extraction accepts only numeric, finite values (with CDM
remaining optionally absent). Invalid fields raise a named `ValueError`.

**Validation:** Parameterized tests cover string `NaN`, floating `NaN`, and
infinity. The complete report test module passes (`18 passed`).

### Medium - Scoring did expensive work before validating its inputs

**Evidence:** `eval-infra/03-scoring/score.ps1` rendered a config and launched
OmniDocBench without first validating the selected Python or whether the
configured prediction directory existed and contained Markdown.

**User impact:** A directory naming mistake could consume scoring time and
produce zero/empty results instead of an immediate corrective action.

**Correction:** The scorer now validates Python 3.10/3.11, requires exactly one
`prediction.data_path`, supports `-PredictionDir`, and rejects missing or empty
prediction directories before launching OmniDocBench. The WSL scorer applies
the same directory contract.

**Validation:** A behavioral test proves an empty override fails before scoring
with an actionable message.

### Medium - Benchmark reports were hard-coded to one machine

**Evidence:** `report.py`, `run.ps1`, and `verify.ps1` required or emitted
`AMD Ryzen AI Max+ 395` even when the benchmark ran on different AMD hardware.
The current review machine is a Ryzen AI 7 PRO 350 with Radeon 860M.

**User impact:** Reports were factually wrong on other supported Radeon systems,
and their verifier rejected otherwise valid reports.

**Correction:** `run.ps1` derives a CPU/GPU/RAM label unless `-Platform` is
provided; the title and environment snapshot use that label; verification
requires a non-empty platform rather than a specific product.

**Validation:** Report tests assert dynamic titles and reject empty platforms.

### Medium - Python environment was not reproducibly specified

**Evidence:** The baseline machine had no usable system Python and the initial
test run failed because `psutil` was an undocumented dependency. Setup could
also fall back to an unsupported interpreter.

**User impact:** A fresh Windows user could fail before dataset setup or encounter
Python 3.12/3.13 incompatibilities deep in scoring.

**Correction:** `.python-version`, `pyproject.toml`, and `uv.lock` define a
Python 3.11 environment. Setup prefers uv, rejects unsupported existing venvs,
and retains guarded 3.10/3.11 compatibility fallbacks.

**Validation:** Locked sync completed and the full fast suite passes (`86 passed`
after the current review changes).

### Medium - WSL discovery failed before provisioning on an unconfigured host

**Evidence:** With `$ErrorActionPreference = 'Stop'`, `wsl --list --quiet`
stderr became a terminating native-command error when the optional Windows
feature was absent. The script never reached its installation path.

**User impact:** The documented WSL bootstrap failed on exactly the fresh
machines it was intended to support.

**Correction:** `Get-WslDistros` temporarily treats a failed list probe as an
empty distro list and restores the caller's error preference.

**Validation:** A focused regression checks the guarded probe; the script still
requires real system-level validation in the WSL reproduction phase.

## Quality-Gap Closure - 2026-07-26

The previously open repository-level gaps now have executable closure evidence:

- `scripts/preflight.ps1` checks the selected Python, Git, disk, writable path,
  mirrors, WSL, GPU choice, and optional native-CDM prerequisites before long
  setup phases.
- `scripts/validate_predictions.py` validates exact image/manifest stems,
  UTF-8, non-empty Markdown, case collisions, coverage, and frozen errors.
- Lightweight CI, contribution guidance, security reporting, a code of conduct,
  and a pull-request template are present without claiming hardware validation.
- English and Chinese entry points document explicit prediction/config/result
  binding, WSL-vs-native CDM ownership, and the exact CPU-subset workflow.
- This machine physically reproduced an exact 200-page CPU + WSL CDM capability
  path through inference, Windows/WSL scoring, benchmark reporting, and
  parameterized full verification. It did not reproduce the 1651-page HIP path.
- Headline tables now distinguish historical 1651-page reference targets from
  this machine's dated 200-page result before displaying either score set.

## Reviewed Areas Without A Confirmed Defect

- Adapter `--engine official` dispatch is implemented correctly; the initial
  suspicion that the CLI ignored it was a false positive.
- PowerShell variable arguments preserve paths containing spaces; unquoted
  string-expansion concerns were not treated as defects without a failing call
  site.
- `PYTHONUTF8=1` remains present on Windows scoring paths.
- Adapter Markdown and error/statistics files use explicit UTF-8 writes.
- Existing setup/verify ownership and Windows/WSL architecture remain sound and
  were preserved rather than rewritten.

## Validation Snapshot

- Mirror detection: two consecutive successful runs, `NETWORK_STATUS=ok`.
- Bash syntax: modified `score-cdm.sh` parses successfully.
- PowerShell syntax: modified benchmark and repository scripts parse under the
  Windows PowerShell AST parser.
- Focused scoring/CDM suite: `37 passed` after metric hardening.
- Benchmark report suite: `18 passed`.
- Complete repository suite: `86 passed`.
- VS Code diagnostics: no errors in the touched scripts or tests.

## Release Decision

**Release-ready for the documented constrained-hardware capability scope.** The
selected 200-page CPU + WSL CDM path passes prediction, scoring, benchmark, and
parameterized full-chain gates. The deterministic suite reports `120 passed`,
and final syntax, structured-data, documentation-link, artifact-size, secret,
and diff reviews pass.

This is not a declaration that the current Radeon 860M machine reproduced the
1651-page HIP reference result or optional Windows-native CDM. Those gates stay
open in the execution plan and are stated as limitations in both entry-point
READMEs and the dated reproduction evidence.
