# OmniDocBench AMD Windows

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform: AMD ROCm](https://img.shields.io/badge/Platform-AMD_ROCm_HIP-red.svg)](https://github.com/issues?q=omnidocbench+amd)
[![OmniDocBench v1.6](https://img.shields.io/badge/OmniDocBench-v1.6-00C853.svg)](https://github.com/opendatalab/OmniDocBench)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/AIwork4me/omnidocbench-amd-windows)](https://github.com/AIwork4me/omnidocbench-amd-windows)

> **Setting up OmniDocBench CDM took us 20+ debugging sessions. This repo distills them into one command.**

One-command setup of [OmniDocBench](https://github.com/opendatalab/OmniDocBench) v1.6 full evaluation
(1651 pages) on **Windows + AMD Radeon GPUs** (ROCm/HIP). All four standard metrics: text Edit-distance,
reading-order Edit-distance, table TEDS, **formula CDM**. Model-agnostic — swap any document parsing
model via [adapters](adapters/). PaddleOCR-VL-1.6 ships as the validated reference.

| Metric | PaddleOCR-VL-1.6 (ours) | Official | Gap |
|---|---:|---:|---:|
| Text Edit-dist ↓ | **0.035** (96.5%) | 0.033 | 0.17pt |
| Reading-order ↓ | **0.129** (87.1%) | 0.127 | 0.19pt |
| Table TEDS ↑ | **0.940** | 0.948 | 0.76pt |
| Formula CDM ↑ | **0.944** | 0.975 | 3.1pt |

### Quick Start

```bash
git clone https://github.com/AIwork4me/omnidocbench-amd-windows
cd omnidocbench-amd-windows
# Point Claude Code or OpenCode at this repo → say "按 CLAUDE.md 搭建"
# Or follow the manual steps in the sections below.
```

[中文文档](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Pitfalls KB](docs/pitfalls.md) · [CLAUDE.md](CLAUDE.md)

---

## Why this repo exists

Bringing OmniDocBench v1.6 up on AMD Windows hits 20+ landmines: China-firewall
network blocks, WSL Store blocked, `\mathcolor` rendering black, ImageMagick 6
flattening color formulas to grayscale, two TeX Live trees disagreeing, Windows
codepage corrupting CJK JSON, and more. This repo distills every fix into
**idempotent scripts** plus a **symptom-indexed knowledge base** and an
**AI-agent orchestration file** so the next person (or agent) reproduces it
without re-debugging.

## Quick start

Point **Claude Code** (or OpenCode, or any agent that reads `CLAUDE.md`) at this
repo. The orchestration file walks the agent through the full setup with
explicit human-intervention points:

```
git clone <this-repo>
cd omnidocbench-amd-windows
# Then in your agent: "Read CLAUDE.md and execute the setup flow."
```

Manual equivalent — the high-level flow (each `setup.*` is idempotent; run the
`verify.*` after each):

```powershell
# Step 0: environment + network + WSL
powershell -ExecutionPolicy Bypass -File scripts\detect-mirrors.ps1
powershell -ExecutionPolicy Bypass -File scripts\wsl-ensure.ps1

# Step 1: OmniDocBench code + dataset
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1

# Step 2: CDM environment (WSL) — the hardest step
wsl -d Ubuntu2204 bash /mnt/c/.../eval-infra/02-cdm-environment/setup.sh
wsl -d Ubuntu2204 bash /mnt/c/.../eval-infra/02-cdm-environment/verify.sh

# Step 3: reference adapter (PaddleOCR-VL-1.6)
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --img-dir eval-infra\01-omnidocbench\data\images `
    --out-dir predictions\paddleocr-vl-1.6

# Step 4: scoring + final verification
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1
wsl -d Ubuntu2204 bash /mnt/c/.../eval-infra/03-scoring/score-cdm.sh
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
# Or all-at-once:
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1
```

Full step-by-step with exception handling: [`CLAUDE.md`](CLAUDE.md).

---

## Architecture

Three layers. Only `adapters/` is per-model; everything else is shared.

```
eval-infra/        ← model-agnostic infrastructure, set up once
  01-omnidocbench/    OmniDocBench code + v1.6 dataset (1651 pages) + config templates
  02-cdm-environment/ CDM toolchain in WSL: TeX Live 2026 + ImageMagick 7 + gs + the \mathcolor fix
  03-scoring/         score.ps1 (Edit_dist+TEDS, Windows) · score-cdm.sh (+CDM, WSL) · verify.ps1

adapters/          ← model-specific, one directory per model
  _template/          minimal skeleton to copy
  paddleocr-vl-1.6/   validated reference (ONNX layout + llama.cpp GGUF VLM)

scripts/           ← cross-cutting tools
  detect-mirrors.ps1  probe reachable mirrors → mirrors.env
  wsl-ensure.ps1      guarantee a WSL Ubuntu 22.04 distro (handles Store-blocked)
  full-verify.ps1     chain every verify in dependency order

docs/
  pitfalls.md         knowledge base, indexed by symptom (the most valuable file)
  architecture.md     data-flow diagrams + the Windows/WSL boundary
```

**The one architectural fact to remember:** CDM (the formula-rendering metric)
runs in **WSL** because OmniDocBench's CDM code shells out to POSIX-only
commands (`pdflatex`, `magick`, `gs`, `kpsewhich`) and ImageMagick 6 silently
flattens color formulas to grayscale. Everything else runs Windows-native. See
[`docs/architecture.md`](docs/architecture.md) and
[`docs/pitfalls.md#posix`](docs/pitfalls.md#posix).

Each adapter's only contract:

```python
def run_adapter(img_dir: Path, out_dir: Path, server_url: str = ""):
    """Write out_dir/<image_stem>.md for every page image in img_dir."""
```

The scoring layer consumes those `.md` files and never imports the adapter.

---

## PaddleOCR-VL-1.6 reference scores

Our validated results on OmniDocBench v1.6 (full 1651-page set), reproduced by
this repo. The adapter is deterministic (`--temp 0 --top-k 1 --seed 1`), so
these numbers are reproducible across runs and machines.

| Metric | Direction | This repo<br>(PaddleOCR-VL-1.6) | Official 1.6 | Gap |
|---|:---:|---:|---:|---:|
| Text Edit-distance | ↓ | **0.035** (96.5%) | 0.033 (96.7%) | 0.17 pt |
| Reading-order Edit-distance | ↓ | **0.129** (87.1%) | 0.127 (87.3%) | 0.19 pt |
| Table TEDS | ↑ | **0.940** | 0.948 | 0.76 pt |
| Formula CDM | ↑ | **0.944** | 0.975 | 3.1 pt |

The CDM gap (3.1 pt) is the known cost of the GGUF quantization + the
`\mathcolor` rendering override required for the color-bbox matcher to work at
all on AMD Windows; see [`docs/pitfalls.md#mathcolor`](docs/pitfalls.md#mathcolor).

These are the success thresholds a fresh run must clear to count as
reproducing our results: Text Edit-dist < 0.10 · Reading-order < 0.20 ·
TEDS > 0.85 · CDM > 0.85.

---

## How to add a new model

You only touch `adapters/`. Five steps (full detail in
[`adapters/_template/README.md`](adapters/_template/README.md)):

1. `cp -r adapters/_template adapters/<your-model>`
2. Edit `run_adapter.py` — implement `run_adapter(img_dir, out_dir, server_url)`
   to call your model; write `out_dir/<image_stem>.md` per page. Catch per-page
   failures so one bad page doesn't abort the run.
3. Edit `setup.ps1` (or split into numbered sub-directories like the reference
   adapter) to provision weights / start a server. Write machine-local paths to
   a gitignored `.env.local`, never into committed code.
4. Run it: `python run_adapter.py --img-dir <dataset-images> --out-dir ..\..\predictions\<your-model>`
5. Re-run the scorer unchanged (it only reads the prediction path):
   `eval-infra\03-scoring\score.ps1` (+ `score-cdm.sh` for CDM), then `verify.ps1`.

The reference adapter [`adapters/paddleocr-vl-1.6/`](adapters/paddleocr-vl-1.6/)
is a complete, proven example to copy from.

---

## Troubleshooting

Everything we hit, organized **by symptom** (Root Cause → Fix → Verify):
[`docs/pitfalls.md`](docs/pitfalls.md). Start at the table of contents and find
your symptom. The single most-deceptive failure is **CDM F1 = 0 with no error
printed** — everything succeeds yet the score is zero; the decision tree at
[`docs/pitfalls.md#cdm-zero`](docs/pitfalls.md#cdm-zero) resolves it.

For the agent-driven flow and the exception lookup table, see
[`CLAUDE.md`](CLAUDE.md).

---

## Scope

**In scope:** OmniDocBench v1.6, AMD Radeon / Windows, llama.cpp-served models,
local single-machine setups, the four standard metrics.

**Out of scope** (by design — see spec §8): Docker-based setups (kept as a
fallback, not the main path), OmniDocBench v1.5 (config template provided, not
automated), non-AMD GPU adapters (template provided, community contributions
welcome), CI/CD (local verify scripts, not GitHub Actions).

## License

See the upstream [OmniDocBench](https://github.com/opendatalab/OmniDocBench)
license for the eval code and dataset terms. The infrastructure and adapter
code in this repo is provided as-is for reproducing the benchmark.
