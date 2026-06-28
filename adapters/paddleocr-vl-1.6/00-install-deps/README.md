# 00-install-deps — install the `paddleocr_vl_rocm` pipeline package

Provisions the one Python dependency `run_adapter.py` actually imports:
[`paddleocr_vl_rocm`](https://github.com/AIwork4me/PaddleOCR-VL-ROCm) — the
proven inference pipeline (ONNX layout detection + OpenAI-compatible VLM
serving) from the separate **PaddleOCR-VL-ROCm** project.

`run_adapter.py` is *just* the driver; all the real work (layout ONNX, region
cropping, VLM client, Markdown stitching) lives in `paddleocr_vl_rocm`. This
repo does not vendor the package — it clones and `pip install -e`s it.

## What it does

`setup.ps1` runs two idempotent phases:

| Phase | Action | Output |
|---|---|---|
| 1 | `git clone --depth 1` PaddleOCR-VL-ROCm from `$GITHUB_BASE` | `../PaddleOCR-VL-ROCm/` (sibling checkout) |
| 2 | `pip install -e ../PaddleOCR-VL-ROCm` into the target Python | importable `paddleocr_vl_rocm` + deps (onnxruntime, opencv, pillow, …) |

The target Python defaults to the **repo-root `.venv`** created by
`eval-infra/01-omnidocbench/setup.ps1`, so the package lands in the same
interpreter that later runs `run_adapter.py` / `score.ps1`. If that `.venv` is
absent it falls back to the active `python` with a warning.

## Usage

```powershell
# Default (uses repo-root .venv if present, clones to ../PaddleOCR-VL-ROCm):
powershell -ExecutionPolicy Bypass -File 00-install-deps\setup.ps1

# Pin a specific Python:
powershell -ExecutionPolicy Bypass -File 00-install-deps\setup.ps1 -Python C:\path\to\.venv\Scripts\python.exe

# Clone into a custom location:
powershell -ExecutionPolicy Bypass -File 00-install-deps\setup.ps1 -CloneDir D:\src\PaddleOCR-VL-ROCm
```

Re-running is safe: phase 0 short-circuits if `paddleocr_vl_rocm` is already
importable; phases 1–2 skip themselves if the checkout / install exists.

## Where this fits

Run this **before** `run_adapter.py` and **after** (or alongside) the two
provisioning steps:

```
00-install-deps/setup.ps1   <- this step (pip install -e the pipeline package)
01-vlm-server/setup.ps1     <- llama.cpp + GGUF weights, starts llama-server
02-layout-model/setup.ps1   <- PP-DocLayoutV3 ONNX layout model
```

`run_adapter.py` imports `paddleocr_vl_rocm` and reads `.env.local` (written by
01/02) for the model paths — so all three must be done before it runs.

## Notes

- `setup.ps1` reads `mirrors.env` (from `scripts/detect-mirrors.ps1`) for
  `GITHUB_BASE` and `PYPI_INDEX`, so it works behind the China firewall.
- Editable (`-e`) install means edits to the PaddleOCR-VL-ROCm checkout are
  picked up immediately — useful when iterating on the pipeline.
