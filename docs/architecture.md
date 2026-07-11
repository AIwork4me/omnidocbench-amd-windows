# Architecture

How the pieces fit. Read this alongside the top-level [README](../README.md)
and the per-module READMEs.

## The data flow

```
                                  OmniDocBench v1.6 (1651 pages)
                                  GT manifest + page images
                                              |
                                              v
   +-------------------+    Markdown     +-------------------+    scores    +-------------------+
   | adapters/<model>/ |  .md per page   | eval-infra/       |  metric_     | verify.ps1       |
   |  run_adapter.py   | ----------------| 03-scoring/       | ------------>| all 4 metrics    |
   |  (one per model)  |  predictions/   |  score[.ps1|.sh]  |  result.json | non-zero?        |
   +-------------------+    <model>/     +-------------------+              +-------------------+
          ^                                ^        |
          | model weights                  | code   | CDM paths: native Windows
          | via .env.local                 | + data | or WSL reference stack
          |                                |        v
   +-------------------+                   |  +-------------------+
   | 01-vlm-server/    |                   |  | 02-cdm-environment|
   | 02-layout-model/  |                   |  | Win: patch+verify |
   | (provisioning)    |                   |  | WSL: setup.sh     |
   +-------------------+                   |  +-------------------+
                                           |
                              +------------+------------+
                               | eval-infra/01-omnidocbench
                               |  OmniDocBench/  (pdf_validation.py)
                               |  data/         (OmniDocBench.json + images/)
                               |  configs/      (v16*.yaml templates)
                               +---------------------------+
                                            |
                               +------------+------------+
                               | eval-infra/04-benchmark/
                               |  monitor.py (1 Hz sampler)
                               |  report.py (Markdown report)
                               |  run.ps1 (orchestrator)
                               +---------------------------+
```

Arrows show data dependency (producer → consumer). Everything flows rightward:
adapters produce Markdown, the scoring layer scores it, verify checks the
scores.

## The three layers

### 1. `adapters/` — model-specific, produces Markdown

One sub-directory per document-parsing model. Each adapter's **only** job:
given a directory of page images, write one `<image_stem>.md` per page into a
predictions directory. Nothing else. The adapter never imports eval code and
never reads scores — it only emits Markdown.

This is the only layer you touch to add a model. See
[`adapters/README.md`](../adapters/README.md) for the interface contract.

The PaddleOCR-VL-1.6 reference adapter exposes two engines that share this same
contract: `lightweight`/default for the local PaddleOCR-VL-ROCm AMD Windows
path, and `official` for PaddleOCR's `PaddleOCRVL` doc_parser path. They differ
only in how predictions are generated; the dataset, matcher, CDM environment,
and scoring scripts are identical.

### 2. `eval-infra/` — model-agnostic, shared scoring infrastructure

Three numbered sub-directories, in dependency order:

| Module | Provides | Run where |
|---|---|---|
| [`01-omnidocbench`](../eval-infra/01-omnidocbench/) | OmniDocBench eval code (`pdf_validation.py`) + v1.6 dataset (GT manifest + 1651 page images) + config templates | Windows (`setup.ps1`) |
| [`02-cdm-environment`](../eval-infra/02-cdm-environment/) | CDM toolchains: Windows-native after `windows-cdm.patch` + `verify-windows.ps1`, and the WSL TeX Live 2026 + IM7 + gs reference path | Windows PowerShell or WSL (`setup.sh`, 9 steps) |
| [`03-scoring`](../eval-infra/03-scoring/) | The scoring scripts themselves + result verification | Native Windows: `score.ps1 -Config v16-cdm.yaml` after `verify-windows.ps1`; WSL compatibility/reference: `score-cdm.sh` |
| [`04-benchmark`](../eval-infra/04-benchmark/) | Capability reports with GPU/RAM profiling + stability statistics | Windows (`run.ps1`) |

The numbering encodes the dependency: `02-cdm-environment` copies the
OmniDocBench code that `01-omnidocbench` cloned; `03-scoring` consumes both.

### 3. `scripts/` + `docs/` — environment + knowledge

- [`scripts/detect-mirrors.ps1`](../scripts/detect-mirrors.ps1) probes for
  reachable mirrors and writes `mirrors.env` (consumed by every download).
- [`scripts/wsl-ensure.ps1`](../scripts/wsl-ensure.ps1) guarantees a WSL
  Ubuntu 22.04 instance exists (handles the Store-blocked case).
- [`docs/pitfalls.md`](pitfalls.md) — the knowledge base, by symptom.
- [`docs/architecture.md`](architecture.md) — this file.

## The Windows / WSL boundary

CDM has two supported toolchain paths. Windows-native CDM is the local fast path
when `windows-cdm.patch` is applied and `verify-windows.ps1` passes. WSL CDM
remains the compatibility/reference path with an isolated Linux TeX Live,
ImageMagick, and Ghostscript stack. Why is in
[`pitfalls.md#posix`](pitfalls.md#posix) and [`pitfalls.md#grayscale`](pitfalls.md#grayscale).

```
   WINDOWS (PowerShell, Python 3.11)              │     WSL Ubuntu 22.04
                                                  │
   detect-mirrors.ps1 ──> mirrors.env ────────────┼──> setup.sh reads CTAN/GH/PyPI
   wsl-ensure.ps1 ─────> Ubuntu2204 distro ◄──────┼──── (rootfs import if Store blocked)
                                                  │
   adapters/*/setup.ps1 ──> predictions/<model>/  │
                                                  │     02-cdm-environment/
   01-omnidocbench/setup.ps1:                     │       setup.sh (9 steps):
     git clone OmniDocBench ──────────────────────┼──> /root/OmniDocBench (copy)
     download dataset (1651 imgs) ────────────────┼──>  /root/odb-venv
                                                  │       TL2026 + IM7 + gs
   03-scoring/score.ps1:                          │
     Edit_dist + TEDS, or + CDM after              │
     verify-windows.ps1 ◄─────────────────────────┼──── 03-scoring/score-cdm.sh:
                                                  │       Edit_dist + TEDS + CDM
   03-scoring/verify.ps1:                         │       (clean Linux PATH, no /mnt/c)
     reads metric_result.json (win or \\wsl$) ◄───┘
```

The WSL CDM compatibility/reference path crosses the boundary exactly twice per
CDM run:

1. **Down:** `score-cdm.sh` is launched from PowerShell via
   `wsl -d Ubuntu2204 bash .../score-cdm.sh`. The script sets a clean Linux
   `PATH` so no Windows executables leak in.
2. **Up:** `verify.ps1` reads the result JSON, either from the Windows
   OmniDocBench checkout or from the WSL checkout via the `\\wsl$\Ubuntu2204\`
   share.

For that WSL path, LaTeX compilation, PDF rasterization, and CDM matching stay
entirely on the Linux side. The native Windows path instead uses the
`windows-cdm.patch`-enabled checkout and is validated by
`verify-windows.ps1`, without requiring WSL.

## Config → save_name → result mapping

The scoring layer renders a config **template** (`<REPO_ROOT>` placeholder) into
a concrete config, then runs `pdf_validation.py`. The result file naming is
deterministic:

```
config template                 predictions dir              save_name                                   result file
─────────────                   ───────────────              ─────────                                  ───────────
v16.yaml                        predictions/paddleocrvl_rocm paddleocrvl_rocm_quick_match               <save_name>_metric_result.json
v16-hard.yaml                   predictions/..._hard         paddleocrvl_rocm_hard_quick_match          "         _run_summary.json
v16-cdm.yaml                    predictions/..._cdm          paddleocrvl_rocm_cdm_quick_match           "         _<category>_result.json
v16-official-prettyfalse-full   predictions/paddleocr_...    paddleocr_official_prettyfalse_...         "
v16-cdm-official-prettyfalse    predictions/paddleocr_...    paddleocr_official_prettyfalse_...         "
```

`save_name = basename(prediction_path) + "_" + match_method`. The `_cdm` suffix
on the CDM predictions dir is deliberate — it gives the CDM run a different
`save_name` so it doesn't clobber the Edit_dist-only run's results.

## Idempotency everywhere

Every `setup.*` script self-checks before doing work (`Test-Path`, `dpkg -s`,
`kpsewhich`, `[ -x ... ]`, `[ -d ... ]`). Re-running after success is fast and
prints `already installed`/`already present` per step. This is what makes the
repo safe to point an agent at: re-running the whole pipeline is a no-op once
provisioned, and resumes cleanly after a partial/interrupted run.

## Where to look next

- Adding a model → [`adapters/README.md`](../adapters/README.md)
- Why CDM is hard → [`eval-infra/02-cdm-environment/README.md`](../eval-infra/02-cdm-environment/README.md)
- Debugging a failure → [`pitfalls.md`](pitfalls.md)
