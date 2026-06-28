# 02-layout-model — PP-DocLayoutV3 ONNX layout detector

Provisions the **layout-detection** half of the PaddleOCR-VL-1.6 adapter.
`run_adapter.py` runs this ONNX model over each page image first (via
ONNXRuntime) to find paragraphs, tables, figures, and reading order, then
crops each detected region and sends it to the VLM server (`01-vlm-server/`)
for Markdown recovery.

## What it does

`setup.ps1` downloads exactly two files from HuggingFace or ModelScope into
`models/PP-DocLayoutV3-onnx/`:

| File | Purpose | Size |
|---|---|---|
| `inference.onnx` | Layout model weights (ONNXRuntime) | ~16 MB |
| `inference.yml` | Model config — image size, label map, thresholds | small |

…then writes the directory to `adapters/paddleocr-vl-1.6/.env.local` under
`PP_DOCLAYOUTV3_ONNX_DIR`, which `run_adapter.py` reads as the default
`--layout-model`.

Only these two files are needed; the rest of the upstream repo is not fetched.

## Usage

```powershell
# Default (auto source from mirrors.env):
powershell -ExecutionPolicy Bypass -File setup.ps1

# Force ModelScope:
powershell -ExecutionPolicy Bypass -File setup.ps1 -Source modelscope

# Custom location:
powershell -ExecutionPolicy Bypass -File setup.ps1 -ModelDir D:\models\layout
```

## Parameters

| Param | Default | Notes |
|---|---|---|
| `-Source` | `auto` | `auto` honours `mirrors.env` `HF_OR_MS`; else `huggingface`. Also accepts `huggingface` / `modelscope` directly. |
| `-ModelDir` | `adapters/paddleocr-vl-1.6/models/PP-DocLayoutV3-onnx` | Destination directory. |
| `-Force` | — | Redownload even if `inference.onnx` already exists. |

## Prerequisites

The downloader is driven from Python and uses one of:

- `pip install huggingface_hub` (for `-Source huggingface`), or
- `pip install modelscope` (for `-Source modelscope`).

The `paddleocr-vl-rocm` package (see `../../README.md`) brings
`onnxruntime` for actually running the model — but `setup.ps1` itself only
needs the download library.

## Why a separate step

The layout model is small and CPU-friendly, and it is **independent** of the
VLM server: you can swap VLMs (a different GGUF, a different serving stack)
without re-downloading the layout model, and vice versa. Keeping the two
provisioning concerns in `01-vlm-server/` and `02-layout-model/` mirrors that
independence.
