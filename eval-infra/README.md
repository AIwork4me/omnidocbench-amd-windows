# eval-infra/ — shared, model-agnostic evaluation infrastructure

This directory holds everything needed to **score** a document-parser's Markdown
output against OmniDocBench v1.6, independent of which model produced that
output. It is provisioned once and reused by every adapter.

## Modules

| Module | Provides | Task |
|---|---|---|
| [`01-omnidocbench/`](01-omnidocbench/) | OmniDocBench eval code (`pdf_validation.py`) + v1.6 dataset (1651 pages, GT manifest) + config templates (`v16.yaml`, `v16-hard.yaml`, `v16-cdm.yaml`) | Task 2 |
| [`02-cdm-environment/`](02-cdm-environment/) | CDM scoring environment inside WSL (TeX Live 2026 + CJK/gkai + ImageMagick 7 + Ghostscript + the `\mathcolor` fix). Required **only** if a config enables CDM (e.g. `v16-cdm.yaml`). Edit_dist + TEDS work without it. Provisioned by `setup.sh` run via `wsl -d Ubuntu2204`. | Task 3 |
| `03-scoring/` | `score.ps1` / `score-cdm.sh` + verify: resolves `<REPO_ROOT>` in a config template, runs `pdf_validation.py`, collects results. | Task 5 |

## The model-agnostic principle

OmniDocBench scores a Markdown dump against a ground-truth manifest. The
**scoring code**, the **dataset**, and the **CDM environment** are properties of
the benchmark, not of any model. Adapters (`../adapters/`, Task 4) only produce
Markdown into a per-adapter `predictions/<adapter>/` directory; everything under
`eval-infra/` then scores that directory identically regardless of source.

Concretely:

- `01-omnidocbench/` is downloaded once and never depends on which adapter ran.
- `02-cdm-environment/` is the same WSL/TeX Live 2026/ImageMagick 7 stack no matter the model.
- `03-scoring/` takes a config + a predictions directory; the adapter name is just
  a path segment.

This is what makes scores directly comparable across models and keeps the per-model
setup surface small (an adapter only needs to *produce* Markdown).

## Provisioning order

The intended order is `01` → `02` (optional, CDM only) → `03`:

```powershell
powershell -ExecutionPolicy Bypass -File 01-omnidocbench/setup.ps1   # code + dataset
wsl -d Ubuntu2204 bash 02-cdm-environment/setup.sh                    # only if using CDM
# 03-scoring is invoked per-eval, not provisioned up front.
```

`scripts/full-verify.ps1` (Task 7) chains each module's `verify.ps1` to confirm
the whole stack is ready before a scoring run.
