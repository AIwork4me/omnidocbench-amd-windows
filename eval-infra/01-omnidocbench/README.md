# 01-omnidocbench — eval code + v1.6 dataset + config templates

## What this is

The model-agnostic evaluation infrastructure for OmniDocBench v1.6. Every model
adapter (PaddleOCR-VL-1.6 and any future one) is scored against the **same**
ground-truth dataset with the **same** scoring code, so scores are directly
comparable. This module provisions exactly that shared code + dataset.

It contains three things:

1. **Eval code** — a shallow clone of [`opendatalab/OmniDocBench`](https://github.com/opendatalab/OmniDocBench)
   in `OmniDocBench/`. Provides `pdf_validation.py` (the scorer: Edit_dist, TEDS,
   CDM, reading-order) and the dataset loader. This is the upstream source of
   truth for how a Markdown dump is scored.
2. **Dataset** — OmniDocBench v1.6 (1651 page images + the `OmniDocBench.json`
   ground-truth manifest) in `data/`. Downloaded from ModelScope (or
   HuggingFace, per `mirrors.env`). ~18 minutes on a slow link.
3. **Config templates** — YAML configs consumed by `pdf_validation.py`. They
   use a `<REPO_ROOT>` placeholder that the scoring module (Task 5) replaces
   with the absolute repo path at runtime, so the templates are
   machine-independent and committed.

## Why it's a separate module

The OmniDocBench eval code and dataset never change between models. Putting them
behind a one-time `setup.ps1` means:

- Switching adapters (Task 4) does not re-download 1651 images.
- The dataset is downloaded **once**, idempotently, with resume support from the
  underlying HF/MS CLI cache.
- Configs are versioned in the repo (machine-agnostic) rather than hand-edited
  per machine.

## What problem it solves

Without this module, each model's evaluator would (a) clone OmniDocBench
independently, (b) re-download the dataset, and (c) carry its own machine-specific
config — making cross-model score comparison unreliable and the setup fragile.
This module makes those three concerns a single, verified, shared dependency.

## Usage

```powershell
# 1. Provision code + dataset (idempotent; re-run resumes a partial download).
powershell -ExecutionPolicy Bypass -File setup.ps1

# Code only (skip the ~18-min dataset download):
powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipDataset

# 2. Verify everything is present.
powershell -ExecutionPolicy Bypass -File verify.ps1
```

`setup.ps1` reads `../../mirrors.env` (produced by `scripts/detect-mirrors.ps1`)
for `GITHUB_BASE` and the dataset source (`HF_OR_MS`). If `mirrors.env` is
absent it falls back to GitHub + ModelScope with a warning.

## Expected result

| Artifact | Location | Check |
|---|---|---|
| Eval code | `OmniDocBench/pdf_validation.py` | present |
| Windows CDM patch | `patches/omnidocbench/windows-cdm.patch` | auto-applied by `setup.ps1`; verified by `verify-windows.ps1` |
| GT manifest | `data/OmniDocBench.json` | present |
| Page images | `data/images/*.png` | ~1651 files |
| Hard manifest | `data/OmniDocBench_hard296.json` | **derivative** (auto-derived by `score.ps1 -Config v16-hard.yaml`); absence is a WARNING, not a failure |

`verify.ps1` exits 0 when code + GT manifest + ≥1000 images are present.

## Config templates

| Config | Metrics | Ground truth | Predictions dir | Notes |
|---|---|---|---|---|
| `v16.yaml` | Edit_dist + TEDS (no CDM) | full (1651) | `paddleocrvl_rocm` | minimal env; default |
| `v16-hard.yaml` | Edit_dist + TEDS (no CDM) | hard (296) | `paddleocrvl_rocm_hard` | needs filtered manifest |
| `v16-cdm.yaml` | Edit_dist + TEDS **+ CDM** | full (1651) | `paddleocrvl_rocm_cdm` | needs CDM env (Task 3) |
| `v16-official-prettyfalse-full-2026-07-09.yaml` | Edit_dist + TEDS (no CDM) | full (1651) | `paddleocr_official_prettyfalse_full_2026-07-09` | PaddleOCR official engine with `_to_markdown(pretty=False)` |
| `v16-cdm-official-prettyfalse-full-2026-07-09.yaml` | Edit_dist + TEDS **+ CDM** | full (1651) | `paddleocr_official_prettyfalse_full_2026-07-09` | WSL CDM pair for the published official-engine score |

The hard-subset manifest (`OmniDocBench_hard296.json`) is **not** part of the
dataset download; `score.ps1 -Config v16-hard.yaml` auto-derives it from the
full manifest (filtering for `subset in {equation_hard, layout_hard, table_hard}`)
on first use. The `prediction` paths point under
`<REPO_ROOT>/predictions/<adapter>/`, which each adapter populates before scoring.

The `official-prettyfalse` configs are not a separate benchmark. They score the
same OmniDocBench v1.6 ground truth against predictions produced by the
PaddleOCR official `PaddleOCRVL` doc_parser engine. The default `v16*.yaml`
configs score the PaddleOCR-VL-ROCm engine used by the quick start.

## Notes

- The dataset download is **not** committed (see repo `.gitignore`: `OmniDocBench_data/`
  and analogous paths). `data/` is gitignored by the parent rules' spirit; it is
  reproducible from `setup.ps1`.
- The upstream `opendatalab/OmniDocBench` default branch is v1.6; `--depth 1`
  is sufficient. If you need the v1.5 matching algorithm, check out the v1.5
  branch inside the clone (not handled here).
