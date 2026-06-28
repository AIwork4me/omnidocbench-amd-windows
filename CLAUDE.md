# CLAUDE.md

> This file is the **AI-agent orchestration layer**. It is written for Claude
> Code / OpenCode / similar coding agents: read it top-to-bottom and execute the
> flow below to bring the full OmniDocBench v1.6 evaluation system up from zero
> on an AMD Windows machine, then verify it produces real scores.
>
> 人工介入点（⚠️）会暂停并请你确认。Exception handling points to
> [`docs/pitfalls.md`](docs/pitfalls.md) by symptom — do **not** inline fixes here.

---

## What this repo does

It builds, from scratch on **Windows + AMD Radeon GPU**, a complete
[OmniDocBench v1.6](https://github.com/opendatalab/OmniDocBench) evaluation
system: the full 1651-page benchmark, the four standard metrics (text
Edit-distance, reading-order Edit-distance, table TEDS, formula CDM), and a
reference adapter for **PaddleOCR-VL-1.6** with validated scores.

Once the infrastructure is up, evaluating *any* document-parsing model is a
matter of writing one adapter (see `adapters/_template/`). The infra is
model-agnostic; only `adapters/` is per-model.

The repo exists because the naive path hits 20+ landmines on AMD Windows
(China-firewall network, WSL Store blocked, `\mathcolor` rendering black,
ImageMagick 6 flattening color to grayscale, two TeX Live trees disagreeing,
…). `eval-infra/02-cdm-environment/` distills the fixes into idempotent
scripts; `docs/pitfalls.md` records the debugging.

## Why an agent can run this

Every `setup.*` script is **idempotent** (self-checks before doing work) and
every setup step is followed by a **`verify.*` script that returns exit 0/1
with diagnostics**. You do not need to "know" whether a step succeeded — run
the verify, read the exit code. Re-running the whole pipeline is a no-op once
provisioned and resumes cleanly after a partial run.

---

## ⚠️ Human-intervention points

When you reach one of these, **pause and surface it to the user** with the
exact message. Do not attempt to silently work around them.

| # | When | Why human | Message to show user |
|---|---|---|---|
| ⚠️ 1 | `scripts/wsl-ensure.ps1` finishes but the distro still won't start, or it reports a missing kernel component | A fresh WSL install usually needs a **Windows reboot** before the kernel is active. An agent cannot reboot. | `⚠️ WSL installed but needs a Windows REBOOT to activate the kernel. Reboot, then re-run: wsl -d Ubuntu2204 -- echo OK. (docs/pitfalls.md#wsl)` |
| ⚠️ 2 | `01-vlm-server/setup.ps1` starts the VLM server | Confirm the **GPU is actually in use** (ROCm/HIP), and accept any first-run UAC/driver prompt. A mis-served server produces silent 0-predictions later. | `⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.` |
| ⚠️ 3 | Any installer requests **UAC / admin elevation** (ImageMagick, drivers, WSL feature enablement) | An agent cannot click an elevation prompt. | `⚠️ An installer is requesting admin (UAC). Please approve it, then tell me to continue.` |
| ⚠️ 4 | `detect-mirrors.ps1` reports **no reachable source** for GitHub or HuggingFace/ModelScope | Means the machine has no working egress at all (offline, or all mirrors blocked). Needs a human to fix networking/VPN. | `⚠️ No reachable mirror for GitHub or datasets. Check networking/VPN and re-run scripts/detect-mirrors.ps1. (docs/pitfalls.md#network)` |

Everything else is autonomous.

---

## Execution flow

Work top to bottom. Run each `verify.*` immediately after its `setup.*`; only
proceed when it exits 0. All paths are relative to the repo root. Launch
PowerShell scripts with `powershell -ExecutionPolicy Bypass -File ...`.

### Step 0 — environment + network + WSL  (Windows)

```powershell
# 0a. Probe reachable mirrors → writes mirrors.env (consumed by everything).
powershell -ExecutionPolicy Bypass -File scripts\detect-mirrors.ps1
#   On failure → ⚠️ 4 / docs/pitfalls.md#network

# 0b. Guarantee a WSL Ubuntu 22.04 distro exists (handles Store-blocked case).
powershell -ExecutionPolicy Bypass -File scripts\wsl-ensure.ps1
wsl -d Ubuntu2204 -- echo OK
#   If "missing kernel component" or distro won't start → ⚠️ 1 (reboot)
#   If wsl --install hangs/fails → docs/pitfalls.md#wsl
```

### Step 1 — OmniDocBench code + dataset  (Windows, `eval-infra/01-omnidocbench/`)

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1
#   verify exit 1 + "code missing"    → re-run setup
#   verify exit 1 + "GT manifest"      → dataset download failed → pitfalls.md#network
#   verify exit 1 + "only N images"    → partial download → re-run setup (resumes)
```

### Step 2 — CDM environment  (WSL, `eval-infra/02-cdm-environment/`) — the hardest step

```powershell
# Run the 9-step idempotent installer inside WSL.
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/setup.sh
# End-to-end verify: CJK formula → PDF → color PNG → CDM F1 > 0.
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/verify.sh
#   verify exit 1 at "IM7 not active"      → pitfalls.md#grayscale
#   verify exit 1 at "PDF→PNG"              → pitfalls.md#im7-libs or #im7-gs
#   verify exit 1 at "PNG is grayscale"     → pitfalls.md#mathcolor
#   verify exit 1 at "CJK.sty not found"    → pitfalls.md#texlive-cjk
#   verify exit 1 at "CDM F1=0"             → pitfalls.md#cdm-zero (decision tree)
```

This step is long (TeX Live 2026 + IM7 download). It is safe to re-run; each of
the 9 steps self-skips when already done.

### Step 3 — reference adapter (PaddleOCR-VL-1.6)  (Windows, `adapters/paddleocr-vl-1.6/`)

```powershell
# 3a. VLM server: llama.cpp HIP build + ~1.7 GB GGUF, starts llama-server.
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
#   → ⚠️ 2 (confirm GPU in use)
#   verify exit 1 / 500 errors → pitfalls.md#vlm

# 3b. Layout model: PP-DocLayoutV3 ONNX (~16 MB).
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1
#   model not found → pitfalls.md#layout

# 3c. Install the pipeline package (from a PaddleOCR-VL-ROCm checkout), then run.
pip install -e <path-to-PaddleOCR-VL-ROCm>
# NOTE: --out-dir must match the prediction path the scoring configs read
# (eval-infra\01-omnidocbench\configs\v16*.yaml -> predictions/paddleocrvl_rocm).
# A different name here means score.ps1 finds no predictions and every metric is 0.
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --img-dir  eval-infra\01-omnidocbench\data\images `
    --out-dir  predictions\paddleocrvl_rocm
#   → produces predictions\paddleocrvl_rocm\<stem>.md per page
```

Use `-Variant cpu` instead of `-Variant hip` on non-AMD-Radeon hardware.

### Step 4 — scoring + final verification  (Windows + WSL, `eval-infra/03-scoring/`)

```powershell
# 4a. Edit_dist + TEDS pass (Windows-native, pure Python).
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1
# 4b. CDM pass (WSL; needs Step 2's environment).
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh
# 4c. Verify all four metrics are present and non-zero.
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
#   Any "zero/non-positive" → silent run failure → see row in table below

# 4d. (Optional) full chain in one command:
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1
```

---

## Exception lookup table

When a verify fails (or a score is zero), match the symptom, read the linked
`docs/pitfalls.md` section, apply the **Fix** described there, then re-run the
verify that failed. Do not improvise a fix.

| Symptom | Read |
|---|---|
| `git clone` / `huggingface-cli` / download hangs or times out | `docs/pitfalls.md#network` |
| `wsl --install` hangs, or distro won't start after import | `docs/pitfalls.md#wsl` (reboot first) |
| `AttributeError: ... getargspec` / `distutils` on Python 3.12 | `docs/pitfalls.md#python-version` (use 3.10/3.11) |
| CDM run exits 0 but `display_formula.CDM.all == 0.0` | `docs/pitfalls.md#cdm-zero` (decision tree) |
| CDM formula PDF compiles but colors are black | `docs/pitfalls.md#mathcolor` |
| `magick --version` shows ImageMagick 6, or formula PNG is grayscale | `docs/pitfalls.md#grayscale` |
| `pdflatex: Font gkai not found` / CJK glyphs are tofu | `docs/pitfalls.md#gkaiu-map` |
| `security policy 'PDF'` from `convert` | `docs/pitfalls.md#im-policy` |
| `magick: error while loading shared libraries: libfribidi…` | `docs/pitfalls.md#im7-libs` |
| `magick` fails on PDF after IM7 install from AppImage dir | `docs/pitfalls.md#im7-gs` |
| CDM `FileNotFoundError: kpsewhich/magick/gs` on Windows | `docs/pitfalls.md#posix` (must use WSL) |
| `! LaTeX Error: File 'CJK.sty' not found` | `docs/pitfalls.md#texlive-cjk` |
| CDM passes by hand but fails under the harness (heisenbug) | `docs/pitfalls.md#two-texlive-trees` |
| `UnicodeDecodeError` mid-scoring, or mojibake in JSON/LaTeX | `docs/pitfalls.md#pythonutf8` (`PYTHONUTF8=1`) |
| `onnxruntime ... model file not found`, no predictions | `docs/pitfalls.md#layout` |
| VLM server 500 / connection refused / OOM | `docs/pitfalls.md#vlm` |

The single most-deceptive failure is **CDM F1 = 0 with no error printed** —
*everything succeeds* (LaTeX compiles, PDF rasterizes, Python imports) yet the
score is zero. Always run `eval-infra/02-cdm-environment/verify.sh` first; if it
passes, CDM scoring will produce real scores.

---

## Success criteria

The system is fully operational when **all** hold:

1. `scripts/wsl-ensure.ps1` → `wsl -d Ubuntu2204 -- echo OK` prints `OK`.
2. `eval-infra/01-omnidocbench/verify.ps1` exits 0 (code + 1651 images present).
3. `eval-infra/02-cdm-environment/verify.sh` prints `VERIFY OK` (incl. `CDM F1 for identical formulas` > 0.5).
4. `adapters/paddleocr-vl-1.6/01-vlm-server/verify.ps1` exits 0 (`curl /v1/models` 200).
5. `predictions/paddleocrvl_rocm/` contains one `.md` per dataset page (~1651).
6. `eval-infra/03-scoring/verify.ps1` exits 0 with all four metrics non-zero.

Reference targets (our validated PaddleOCR-VL-1.6 results on OmniDocBench v1.6):

| Metric | Direction | This repo (validated) | Pass threshold |
|---|---|---:|---:|
| Text Edit-distance | ↓ | 0.035 | < 0.10 |
| Reading-order Edit-distance | ↓ | 0.129 | < 0.20 |
| Table TEDS | ↑ | 0.940 | > 0.85 |
| Formula CDM | ↑ | 0.944 | > 0.85 |

A run whose metrics clear these thresholds reproduces our results. See
[`README.md`](README.md) for the full table vs. the official baseline.

---

## How to add a new model (after the infra is up)

You only touch `adapters/`. Five steps, documented in
[`adapters/_template/README.md`](adapters/_template/README.md):

1. `cp -r adapters/_template adapters/<your-model>`
2. Edit `run_adapter.py` — keep the signature
   `run_adapter(img_dir, out_dir, server_url)` and write
   `out_dir/<image_stem>.md` per page.
3. Edit `setup.ps1` to provision weights/server; write machine-local paths to a
   gitignored `.env.local`.
4. Run the adapter into `predictions/<your-model>/`.
5. Re-run `eval-infra/03-scoring/score.ps1` (+ `score-cdm.sh` for CDM) and
   `verify.ps1`. The scorer is unchanged — only the prediction path differs.

The reference adapter `adapters/paddleocr-vl-1.6/` is a complete, proven
example to copy from.

---

## Conventions for editing this repo

- **Idempotency**: every `setup.*` self-checks before doing work. Preserve this
  when editing — never make a setup step destructive to re-run.
- **Verify is the agent's eyes**: each `setup.*` is followed by a `verify.*`
  returning 0/1. When you add a setup step, add/extend its verify.
- **No fixes in CLAUDE.md**: new landmines go in `docs/pitfalls.md` as
  `Symptom → Root Cause → Fix → Verify`, then a row in the exception table
  above. Keep this file orchestration-only.
- **Codepage**: every Windows scoring run sets `PYTHONUTF8=1`. Never remove it.
- **WSL for CDM**: CDM is POSIX-only. Never attempt CDM on Windows-native.
