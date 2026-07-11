# Windows Native CDM Patch Reproducibility Design

Date: 2026-07-11
Status: Approved for implementation planning

## Goal

Make the two local OmniDocBench Windows CDM fixes reproducible from tracked
`omnidocbench-amd-windows` files, so a fresh checkout can install, verify, and
explain the same Windows-native CDM behavior without relying on an untracked
local `C:\Users\rocm\Desktop\OmniDocBench` working tree.

The project must preserve the open-source quality loop:

- tracked patch source of truth;
- automatic, idempotent application in the runbook;
- local environment checks for TeX Live, ImageMagick, and Ghostscript;
- scoring evidence tied to commands and logs;
- clear documentation of Windows-native CDM versus the existing WSL path.

## Current Evidence

The local OmniDocBench checkout at `C:\Users\rocm\Desktop\OmniDocBench` has two
uncommitted CDM toolchain fixes:

```text
src/metrics/cdm/modules/latex2bbox_color.py
src/metrics/cdm/modules/texlive_env.py
```

`git diff --stat` for those files reports approximately `50 insertions` and
`11 deletions`.

The local official-engine CDM rerun completed with usable metrics:

| Metric | Value |
|---|---:|
| Text Edit-distance | 0.034 |
| Reading-order Edit-distance | 0.129 |
| Table TEDS | 94.24 |
| Formula CDM | 96.50 |
| CDM samples | 2352 |
| CDM timeout | 0 |
| CDM exception | 0 |

Full local rerun evidence is recorded in:

```text
C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm\logs\official_cdm_rerun_20260711_092548.log
```

The patch source fixes these root causes:

- Windows command execution in CDM used POSIX shell assumptions, `/dev/null`,
  and string quoting that are not reliable under `cmd.exe`.
- `pdflatex` and `magick` should be launched with argv lists so paths with
  spaces and mixed slashes are safe.
- CDM temporary filenames included too much of the output path, producing long
  names during full runs.
- TeX Live's bundled Ghostscript under `tlpkg\tlgs` was not discoverable by
  ImageMagick, so `PATH` and `GS_LIB` need to include the relevant directories.
- The Windows TeX Live package set must include the package that provides
  `upgreek.sty`.

## Recommended Architecture

Adopt option A: a root-level tracked patch plus automatic runbook integration.

Create the patch at:

```text
patches/omnidocbench/windows-cdm.patch
```

This satisfies the user-facing repository layout and keeps the Windows-native
CDM fix visible as a named compatibility patch.

`eval-infra/01-omnidocbench/setup.ps1` remains the installer entry point for the
generated OmniDocBench checkout. After cloning or resuming the checkout and
after applying the existing tracked compatibility patches, it will detect and
apply `patches/omnidocbench/windows-cdm.patch`.

The patch application must be idempotent. Setup should skip application when
the target checkout already contains the expected sentinels, and it should fail
with an actionable message when the patch neither applies nor appears already
present.

## Components

### Patch File

`patches/omnidocbench/windows-cdm.patch` is generated from the current local
diff in `C:\Users\rocm\Desktop\OmniDocBench` for exactly these files:

```text
src/metrics/cdm/modules/latex2bbox_color.py
src/metrics/cdm/modules/texlive_env.py
```

It must not include unrelated local files, generated outputs, logs, or data.

Expected behavior captured by the patch:

- `run_cmd` supports both string commands and argv lists and redirects stdout
  and stderr to `subprocess.DEVNULL`.
- ImageMagick conversion uses argv calls with `magick`.
- `pdflatex` uses argv calls and normalized absolute paths.
- CDM temp filenames use a short safe prefix derived from output basename and
  sample basename.
- `build_tex_env()` adds TeX Live bundled `tlpkg\tlgs\bin` to `PATH`.
- `build_tex_env()` sets `GS_LIB` to TeX Live bundled Ghostscript resource
  directories when available.

### Setup Integration

`eval-infra/01-omnidocbench/setup.ps1` should gain one small helper or compact
section for the Windows CDM patch.

The detection sentinels should be concrete and cheap:

- `_safe_temp_prefix` appears in `latex2bbox_color.py`;
- `stdout=subprocess.DEVNULL` appears in `latex2bbox_color.py`;
- `tlpkg", "tlgs", "bin"` appears in `texlive_env.py`;
- `GS_LIB` appears in `texlive_env.py`.

If sentinels are present, setup prints a green "already present" message. If
not, setup runs `git -C <OmniDocBench> apply --check <patch>` followed by
`git -C <OmniDocBench> apply <patch>`.

### Verification

The implementation must add or extend verification so the project can prove the
Windows-native CDM path is actually ready.

Minimum verification checks:

- OmniDocBench checkout exists.
- `windows-cdm.patch` exists in the repository.
- the generated OmniDocBench checkout contains the Windows CDM patch sentinels;
- `kpsewhich upgreek.sty` succeeds when TeX Live is on `PATH`;
- `magick -version` succeeds;
- TeX Live bundled Ghostscript is discoverable when present;
- a short CDM smoke test can evaluate identical formulas and produce a positive
  score or a clear actionable failure.

This can be implemented as either:

- an extension to `eval-infra/01-omnidocbench/verify.ps1`; or
- a new focused script such as
  `eval-infra/02-cdm-environment/verify-windows.ps1`, called from the runbook
  and optionally from `scripts/full-verify.ps1`.

The implementation plan should choose the least disruptive option after reading
the surrounding scripts. The preferred behavior is that `scripts/full-verify.ps1`
can report Windows-native CDM readiness without forcing WSL when the native path
is selected.

### Documentation

Update the runbook documentation to remove stale absolute claims that CDM is
"WSL only".

The new public position:

- WSL CDM remains a supported compatibility/reference path.
- Windows-native CDM is now a supported local path when the tracked patch and
  local TeX Live/ImageMagick/Ghostscript toolchain checks pass.
- Users should trust score conclusions only after running the verification
  commands and inspecting the generated metric artifacts.

Likely files:

```text
README.md
README.zh-CN.md
AGENTS.md
docs/architecture.md
docs/pitfalls.md
eval-infra/01-omnidocbench/README.md
eval-infra/03-scoring/README.md
```

Documentation should include the final evidence command chain, not just a prose
claim.

## Error Handling

Patch drift should fail loudly. If upstream OmniDocBench changes the target
files and the patch no longer applies, setup should tell the user which patch
failed and which checkout path to inspect.

Missing TeX Live packages should be reported as toolchain failures, not scorer
failures. `upgreek.sty` is the concrete package smoke check from the local
debugging evidence.

ImageMagick/Ghostscript failures should point at `PATH` and `GS_LIB`, because
that was the local root cause for native Windows CDM rendering.

The verification script must not silently pass CDM F1 = 0 as success. A zero or
missing CDM smoke score is an actionable failure.

## Test Strategy

Add lightweight repository tests that do not require the full dataset:

- assert `patches/omnidocbench/windows-cdm.patch` exists;
- assert the patch contains the expected target files and key sentinels;
- assert `setup.ps1` references `windows-cdm.patch`;
- assert the Windows CDM verification script checks the native toolchain.

Then run operational verification on this machine:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1 -SkipDataset
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1
```

If a dedicated Windows CDM verifier is added, also run it:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1
```

If scoring scripts are updated for native CDM, run the smallest available CDM
smoke or existing local full-result verifier before making any success claim.

## Completion Gate

The work is not complete until the final report includes:

- files changed;
- exact verification commands;
- exit codes;
- key evidence lines;
- whether the patch was applied or already detected;
- whether native Windows CDM toolchain checks passed;
- any remaining limitation or manual prerequisite.

Conclusions must be based on verification data, not on code inspection alone.
