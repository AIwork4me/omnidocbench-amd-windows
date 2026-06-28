# paddleocr-vl-1.6/ — reference adapter

The **proven reference adapter** for this benchmark. It wraps the
[PaddleOCR-VL-ROCm](https://github.com/) pipeline (ONNX layout detection +
llama.cpp-served GGUF VLM) and writes one `<image_stem>.md` per page, which
the model-agnostic eval-infra then scores against OmniDocBench v1.6.

It exists so that:

1. The benchmark has a known-good end-to-end score to compare future adapters
   against.
2. New adapters have a complete, working example to copy (`../_template/` is
   the minimal skeleton; this is the full one).

## Architecture (two halves)

```
                     page image
                          |
                          v
        +---------------------------------+
        | 02-layout-model (PP-DocLayoutV3) |  <- ONNX, CPU/GPU, ~16 MB
        |  detects regions + reading order |
        +---------------------------------+
                          |  cropped regions
                          v
        +---------------------------------+
        | 01-vlm-server (PaddleOCR-VL-1.6) |  <- llama.cpp / GGUF, AMD Radeon
        |  OpenAI-compatible /v1 endpoint  |
        +---------------------------------+
                          |  Markdown per region
                          v
                   run_adapter.py stitches
                   per-page <stem>.md  -->  predictions/paddleocrvl_rocm/
```

The two halves are provisioned independently because they have different
hardware profiles (layout is small/CPU-friendly; the VLM is large/GPU-friendly)
and you may swap one without the other.

## Provisioning

```powershell
# 1. VLM server (downloads llama.cpp + ~1.7 GB GGUF, starts llama-server).
powershell -ExecutionPolicy Bypass -File 01-vlm-server\setup.ps1 -Variant hip
powershell -ExecutionPolicy Bypass -File 01-vlm-server\verify.ps1

# 2. Layout model (downloads ~16 MB ONNX).
powershell -ExecutionPolicy Bypass -File 02-layout-model\setup.ps1
```

Use `-Variant cpu` instead of `-Variant hip` on non-AMD-Radeon hardware
(slower but functional).

## Prerequisite: install the pipeline package

`run_adapter.py` imports `paddleocr_vl_rocm`, the proven pipeline package from
the PaddleOCR-VL-ROCm project. Install it once into the Python you will run the
adapter with:

```powershell
# From a checkout of PaddleOCR-VL-ROCm:
pip install -e <path-to-PaddleOCR-VL-ROCm>
# (brings onnxruntime, opencv, pillow, requests, ... as dependencies)
```

If you do not have that checkout handy, see the upstream project. This repo
does not vendor the package — it is the source of truth for the pipeline and
gets its own tests there.

## Running the adapter

After provisioning + installing the package:

```powershell
# --out-dir must match the path the scoring configs read
# (eval-infra\01-omnidocbench\configs\v16*.yaml). Use paddleocrvl_rocm, not the
# adapter's own dir name, or score.ps1 finds no predictions and scores are all 0.
python run_adapter.py `
    --img-dir  ..\..\eval-infra\01-omnidocbench\data\images `
    --out-dir  ..\..\predictions\paddleocrvl_rocm
```

`run_adapter.py` reads `adapters/paddleocr-vl-1.6/.env.local` (written by the
two `setup.ps1` scripts) for `--layout-model`, `--server-url`, and
`--api-model-name` defaults, so you usually do not need to pass those flags.
CLI flags override `.env.local`, which overrides hard-coded fallbacks.

## Files

| File | Purpose |
|---|---|
| `run_adapter.py` | Inference driver. Iterates images, runs the pipeline, writes per-page `.md`. Catches per-page failures so one bad page does not abort the run. |
| `01-vlm-server/` | Provision + start the VLM server (llama.cpp). See its `README.md`. |
| `02-layout-model/` | Download the PP-DocLayoutV3 ONNX layout model. See its `README.md`. |
| `.env.local` | (gitignored) Machine-local paths written by the setup scripts. |
| `models/` | (gitignored) Downloaded binaries + weights. |
| `logs/` | (gitignored) Server logs + PID file. |

## Determinism

The VLM server is launched with `--temp 0 --top-k 1 --seed 1`, which makes
output deterministic. Combined with the fixed PP-DocLayoutV3 weights, the
adapter is reproducible: re-running it over the same dataset yields
byte-identical Markdown. This is what makes scores comparable across runs and
across machines.

## Scoring

Once `predictions/paddleocrvl_rocm/` is populated, point the scoring module
(Task 5) at it with the relevant config template (`v16.yaml` for Edit_dist +
TEDS, `v16-cdm.yaml` to add CDM). The adapter name is just a path segment to
the scorer.
