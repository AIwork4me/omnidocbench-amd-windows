# eval-infra/ — shared, model-agnostic evaluation infrastructure

This directory holds everything needed to **score** a document-parser's Markdown
output against OmniDocBench v1.6, independent of which model produced that
output. It is provisioned once and reused by every adapter.

## Modules

| Module | Provides | Task |
|---|---|---|
| [`01-omnidocbench/`](01-omnidocbench/) | OmniDocBench eval code (`pdf_validation.py`) + v1.6 dataset (1651 pages, GT manifest) + config templates (`v16.yaml`, `v16-hard.yaml`, `v16-cdm.yaml`) | Task 2 |
| [`02-cdm-environment/`](02-cdm-environment/) | CDM scoring environment: Windows-native CDM is supported after `windows-cdm.patch` is applied and `verify-windows.ps1` passes; WSL CDM remains the compatibility/reference path using TeX Live 2026 + CJK/gkai + ImageMagick 7 + Ghostscript + the `\mathcolor` fix. Required **only** if a config enables CDM (e.g. `v16-cdm.yaml`). Edit_dist + TEDS work without it. | Task 3 |
| `03-scoring/` | CDM scoring paths: native Windows uses `score.ps1 -Config v16-cdm.yaml` after `verify-windows.ps1`; WSL compatibility/reference uses `score-cdm.sh`. Both resolve `<REPO_ROOT>` in a config template, run `pdf_validation.py`, and collect results. | Task 5 |
| [`04-benchmark/`](04-benchmark/) | Capability reports: GPU/RAM profiling, per-page timing, score stability across N runs. Observe-only -- zero adapter changes required. | `run.ps1` Windows, `verify.ps1` Windows |

## The model-agnostic principle

OmniDocBench scores a Markdown dump against a ground-truth manifest. The
**scoring code**, the **dataset**, and the **CDM environment** are properties of
the benchmark, not of any model. Adapters (`../adapters/`, Task 4) only produce
Markdown into a per-adapter `predictions/<adapter>/` directory; everything under
`eval-infra/` then scores that directory identically regardless of source.

Concretely:

- `01-omnidocbench/` is downloaded once and never depends on which adapter ran.
- `02-cdm-environment/` provides the same model-agnostic CDM toolchain choice no matter the model: native Windows after `windows-cdm.patch` + `verify-windows.ps1`, or the WSL TeX Live 2026/ImageMagick 7 compatibility/reference path.
- `03-scoring/` takes a config + a predictions directory; the adapter name is just
  a path segment. For CDM, run `score.ps1 -Config v16-cdm.yaml` after the
  native verifier passes, or use the WSL compatibility/reference `score-cdm.sh`
  path.

This is what makes scores directly comparable across models and keeps the per-model
setup surface small (an adapter only needs to *produce* Markdown).

## Provisioning order

The intended order is `01` → `02` (optional, CDM only) → `03`:

```powershell
powershell -ExecutionPolicy Bypass -File 01-omnidocbench/setup.ps1   # code + dataset
wsl -d Ubuntu2204 bash 02-cdm-environment/setup.sh                    # WSL CDM path only
# 03-scoring is invoked per-eval, not provisioned up front.
```

For Windows-native CDM, apply `patches/omnidocbench/windows-cdm.patch` during
OmniDocBench setup and confirm `02-cdm-environment/verify-windows.ps1` passes.
For native-only full verification, run
`scripts\full-verify.ps1 -SkipWsl -WindowsCdm` (add `-SkipVlm` when the VLM
service is intentionally not running). `-WindowsCdm` without `-SkipWsl` is
dual-path verification: it checks both native Windows CDM and the WSL
compatibility/reference path. WSL CDM remains the compatibility/reference path
and uses the WSL setup and verifier above.

`scripts/full-verify.ps1` (Task 7) chains each module's `verify.ps1` to confirm
the whole stack is ready before a scoring run.
