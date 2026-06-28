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
          | model weights                  | code   | CDM needs WSL:
          | via .env.local                 | + data | LaTeX + IM7 + gs
          |                                |        v
   +-------------------+                   |  +-------------------+
   | 01-vlm-server/    |                   |  | 02-cdm-environment|
   | 02-layout-model/  |                   |  | setup.sh (9 steps)|
   | (provisioning)    |                   |  | in WSL Ubuntu 22  |
   +-------------------+                   |  +-------------------+
                                           |
                              +------------+------------+
                              | eval-infra/01-omnidocbench
                              |  OmniDocBench/  (pdf_validation.py)
                              |  data/         (OmniDocBench.json + images/)
                              |  configs/      (v16*.yaml templates)
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

### 2. `eval-infra/` — model-agnostic, shared scoring infrastructure

Three numbered sub-directories, in dependency order:

| Module | Provides | Run where |
|---|---|---|
| [`01-omnidocbench`](../eval-infra/01-omnidocbench/) | OmniDocBench eval code (`pdf_validation.py`) + v1.6 dataset (GT manifest + 1651 page images) + config templates | Windows (`setup.ps1`) |
| [`02-cdm-environment`](../eval-infra/02-cdm-environment/) | A WSL environment where CDM (the formula-rendering metric) actually works: TeX Live 2026 + IM7 + gs + the `\mathcolor` fix | WSL (`setup.sh`, 9 steps) |
| [`03-scoring`](../eval-infra/03-scoring/) | The scoring scripts themselves + result verification | `score.ps1` Windows, `score-cdm.sh` WSL |

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

The single most important architectural fact: **CDM runs in WSL, everything
else runs Windows-native.** Why is in
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
     Edit_dist + TEDS  (pure Python) ◄────────────┼──── 03-scoring/score-cdm.sh:
                                                  │       Edit_dist + TEDS + CDM
   03-scoring/verify.ps1:                         │       (clean Linux PATH, no /mnt/c)
     reads metric_result.json (win or \\wsl$) ◄───┘
```

The boundary is crossed exactly twice per CDM run:

1. **Down:** `score-cdm.sh` is launched from PowerShell via
   `wsl -d Ubuntu2204 bash .../score-cdm.sh`. The script sets a clean Linux
   `PATH` so no Windows executables leak in.
2. **Up:** `verify.ps1` reads the result JSON, either from the Windows
   OmniDocBench checkout or from the WSL checkout via the `\\wsl$\Ubuntu2204\`
   share.

Everything in between (LaTeX compilation, PDF rasterization, CDM matching)
stays entirely on the Linux side.

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
