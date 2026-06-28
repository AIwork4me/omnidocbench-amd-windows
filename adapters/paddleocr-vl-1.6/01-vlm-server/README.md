# 01-vlm-server — PaddleOCR-VL-1.6-GGUF VLM server (llama.cpp)

Provisions and starts the **vision-language model** half of the PaddleOCR-VL-1.6
adapter. `run_adapter.py` sends each cropped region to this server's
OpenAI-compatible `/v1/chat/completions` endpoint to recover its Markdown text.

## What it does

`setup.ps1` runs three idempotent phases:

| Phase | Action | Output | Size |
|---|---|---|---|
| 1 | Download llama.cpp prebuilt Windows binary (cpu or hip/Radeon) | `models/llama.cpp/llama-server.exe` | ~17 MB (cpu) / ~321 MB (hip) |
| 2 | Download `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` weights (modelscope or huggingface) | `models/PaddleOCR-VL-1.6-GGUF/*.gguf` | ~1.7 GB |
| 3 | Start `llama-server` in the background; wait for `/v1/models` | running process + `logs/llama-server.pid` | — |

All machine-local paths are written to `adapters/paddleocr-vl-1.6/.env.local`
(gitignored). `run_adapter.py` and `verify.ps1` read the same file.

## Usage

```powershell
# CPU build (default):
powershell -ExecutionPolicy Bypass -File setup.ps1

# AMD Radeon (Ryzen AI / Radeon 8060S) -- ~10x throughput:
powershell -ExecutionPolicy Bypass -File setup.ps1 -Variant hip

# Server already provisioned; just (re)start it:
powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipDownload

# Confirm it is healthy:
powershell -ExecutionPolicy Bypass -File verify.ps1
```

## Parameters

| Param | Default | Notes |
|---|---|---|
| `-Variant` | `cpu` | `cpu` or `hip` (AMD Radeon). Use `hip` on Radeon hardware. |
| `-Tag` | `b9637` | llama.cpp release tag (known-good for PaddleOCR-VL-1.6). |
| `-Port` | `8111` | Port `llama-server` listens on. `run_adapter.py` defaults to the same. |
| `-SkipDownload` | — | Skip Phases 1-2; go straight to starting the server. |
| `-Force` | — | Redownload + re-extract even if outputs already exist. |

## Server parameters

Phase 3 launches `llama-server` with parameters tuned and **verified
byte-identical** vs a conservative config on AMD Radeon 8060S (Phase 5
parameter sweep in the source project):

- `--temp 0 --top-k 1` — deterministic decoding (no sampling noise in output).
- `-fa on -np 8 --threads 8` — flash attention, 8 parallel slots, 8 threads.
- `--reasoning-format none --reasoning off --skip-chat-parsing` — strip any
  reasoning scaffolding; the model should emit Markdown directly.
- `--mmproj <mmproj.gguf>` — added automatically if the mmproj weights are
  present (required for vision input).

## Files written

| File | Purpose |
|---|---|
| `models/llama.cpp/` | Extracted llama.cpp binaries (gitignored). |
| `models/PaddleOCR-VL-1.6-GGUF/` | GGUF weights (gitignored). |
| `.env.local` (in `adapters/paddleocr-vl-1.6/`) | `LLAMA_SERVER_EXE`, `PADDLEOCR_VL_GGUF`, `PADDLEOCR_VL_MMPROJ`, `VL_REC_API_MODEL_NAME`, `LLAMA_HOST/PORT`. Gitignored. |
| `logs/llama-server.log` | Server stdout/stderr (gitignored). |
| `logs/llama-server.pid` | Wrapper PID (gitignored). |

## Notes

- Re-running `setup.ps1` is safe. Phases 1-2 are no-ops if their outputs
  already exist; Phase 3 exits early if the server is already answering.
- The `-Variant hip` build requires an AMD Radeon GPU and the matching
  llama.cpp `hip` asset. On non-AMD hardware use `-Variant cpu` (slower but
  functional).
- `setup.ps1` reads `mirrors.env` (from `scripts/detect-mirrors.ps1`) for
  `GITHUB_BASE` and `HF_OR_MS`, so it works behind the China firewall.
