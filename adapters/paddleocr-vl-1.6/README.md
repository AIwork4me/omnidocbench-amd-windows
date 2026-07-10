# paddleocr-vl-1.6/ — reference adapter

The **proven reference adapter** for this benchmark. It writes one
`<image_stem>.md` per page, which the model-agnostic eval-infra then scores
against OmniDocBench v1.6.

It exposes two engines:

- `lightweight` (default): the
  [PaddleOCR-VL-ROCm](https://github.com/AIwork4me/PaddleOCR-VL-ROCm) pipeline
  with ONNX layout detection plus llama.cpp-served GGUF VLM. This is the easy
  local AMD Windows path used by the quick start.
- `official`: PaddleOCR's `paddleocr.PaddleOCRVL` doc_parser path connected to
  the same Windows AMD llama.cpp/GGUF VLM server. This is the closest
  score-comparison path to the public PaddleOCR-VL-1.6 baseline.

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
# 0. Install the pipeline package (clones PaddleOCR-VL-ROCm, pip install -e).
powershell -ExecutionPolicy Bypass -File 00-install-deps\setup.ps1

# 1. VLM server (downloads llama.cpp + ~1.7 GB GGUF, starts llama-server).
powershell -ExecutionPolicy Bypass -File 01-vlm-server\setup.ps1 -Variant hip
powershell -ExecutionPolicy Bypass -File 01-vlm-server\verify.ps1

# 2. Layout model (downloads ~16 MB ONNX).
powershell -ExecutionPolicy Bypass -File 02-layout-model\setup.ps1
powershell -ExecutionPolicy Bypass -File 02-layout-model\verify.ps1
```

Use `-Variant cpu` instead of `-Variant hip` on non-AMD-Radeon hardware
(slower but functional).

## Prerequisite: install the pipeline package

`run_adapter.py` imports `paddleocr_vl_rocm`, the proven pipeline package from
the [PaddleOCR-VL-ROCm](https://github.com/AIwork4me/PaddleOCR-VL-ROCm) project.
`00-install-deps/setup.ps1` provisions it for you — it clones the repo and runs
`pip install -e` into the target Python:

```powershell
powershell -ExecutionPolicy Bypass -File 00-install-deps\setup.ps1
```

To do it manually instead (from a checkout of PaddleOCR-VL-ROCm):

```powershell
git clone https://github.com/AIwork4me/PaddleOCR-VL-ROCm ../PaddleOCR-VL-ROCm
pip install -e ../PaddleOCR-VL-ROCm
# (brings onnxruntime, opencv, pillow, requests, ... as dependencies)
```

This repo does not vendor the package — it is the source of truth for the
pipeline and gets its own tests there.

## Running the adapter

After provisioning + installing the package, **run from the repo root** (the
same CWD `score.ps1` / `full-verify.ps1` assume):

```powershell
# Default lightweight engine.
# --out-dir must match the path the scoring configs read
# (eval-infra\01-omnidocbench\configs\v16*.yaml). Use paddleocrvl_rocm, not the
# adapter's own dir name, or score.ps1 finds no predictions and scores are all 0.
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --img-dir  eval-infra\01-omnidocbench\data\images `
    --out-dir  predictions\paddleocrvl_rocm
```

`run_adapter.py` reads `adapters/paddleocr-vl-1.6/.env.local` (written by the
two `setup.ps1` scripts) for `--layout-model`, `--server-url`, and
`--api-model-name` defaults, so you usually do not need to pass those flags.
CLI flags override `.env.local`, which overrides hard-coded fallbacks.

### Official engine Markdown mode

For diagnostics, `run_adapter.py` also supports `--engine official`, which uses
the official `paddleocr.PaddleOCRVL` doc_parser package instead of the local
`paddleocr_vl_rocm` lightweight path.

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --engine official `
    --img-dir eval-infra\01-omnidocbench\data\images `
    --out-dir predictions\paddleocr_official_prettyfalse_full_2026-07-09
```

Important: PaddleOCRVL's default Markdown export is presentation-oriented:
`_to_markdown(pretty=True)` wraps centered images and captions in HTML
`<div>`/`<img>` tags. OmniDocBench's parser/scorer expects evaluation-oriented
plain Markdown, where images are written as `![](imgs/...)`. The official
engine therefore defaults to `_to_markdown(pretty=False)` before writing
prediction `.md` files.

If you call PaddleOCRVL directly for benchmark scoring, use:

```python
markdown = result._to_markdown(pretty=False)["markdown_texts"]
```

Using the default pretty Markdown can inflate Text Edit-distance by changing
the text candidates that OmniDocBench matches.

## Validated scores

Full OmniDocBench v1.6 results from this repo:

| Metric | Official baseline | PaddleOCR official engine | PaddleOCR-VL-ROCm engine |
|---|---:|---:|---:|
| Overall | 96.33 | 95.8600 | 95.2524 |
| Text Edit-distance | 0.033 | 0.03446 | 0.03397 |
| Reading-order Edit-distance | 0.127 | 0.12929 | 0.12833 |
| Table TEDS | 94.76 | 94.2187 | 94.3216 |
| Formula CDM | 97.49 | 96.8074 | 94.8326 |

The remaining Formula CDM gap is attributed to inference backend/model-output
differences between the public Linux vLLM-style path and this Windows AMD
llama.cpp/GGUF path, after the determinant-array CDM normalization fix.

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
