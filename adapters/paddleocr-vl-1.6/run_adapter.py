"""PaddleOCR-VL-1.6 reference adapter for OmniDocBench (standalone repo).

Mirrors OmniDocBench's ``tools/model_infer/PaddleOCR_img2md.py``: a standalone
offline script that, for each dataset image, runs the PaddleOCR-VL-ROCm
pipeline (ONNX layout detection + llama.cpp-served GGUF VLM) and writes one
``<image_basename_no_ext>.md`` file into a flat output directory.
OmniDocBench's matcher consumes those pre-generated Markdown files directly
(it never imports this adapter), so no JSON is emitted for the harness.

Per-page failures are caught and recorded so a single bad page does not abort
the run (a missing page scores zero in the harness).

Prerequisites
-------------
This adapter is *just* the inference driver. It assumes the two provisioning
steps in this directory have already run:

  1. ``01-vlm-server/setup.ps1``  -- downloads llama.cpp + the
     PaddleOCR-VL-1.6-GGUF weights, starts ``llama-server`` (OpenAI-compatible
     API), and writes their paths to ``.env.local``.
  2. ``02-layout-model/setup.ps1`` -- downloads the PP-DocLayoutV3 ONNX layout
     model and writes its path to ``.env.local``.

It also assumes the ``paddleocr-vl-rocm`` Python package is importable -- see
``../README.md`` for the one-line install. ``run_adapter`` reads the same
``.env.local`` for defaults so that, after provisioning, you can run it with
no flags.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

# NOTE: paddleocr_vl_rocm is the proven pipeline package from the
# PaddleOCR-VL-ROCm project. Install it once (see README.md); this adapter
# only drives it over a directory of images.
from paddleocr_vl_rocm import PaddleOCRVLROCm

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif")


def _read_env_local(repo_root: Path) -> dict[str, str]:
    """Parse the gitignored ``.env.local`` (KEY='VALUE' or KEY=VALUE) if present.

    setup.ps1 writes machine-local paths here; this adapter reads them for
    defaults so it can run with no CLI flags after provisioning.
    """
    values: dict[str, str] = {}
    env_file = repo_root / ".env.local"
    if not env_file.is_file():
        return values
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def expected_md_name(image_name: str) -> str:
    """Return the Markdown filename OmniDocBench's matcher looks up.

    The matcher's first lookup is ``<img_name[:-4]>.md`` (basename minus
    extension). ``Path.stem`` strips a single extension regardless of length.
    """
    return Path(image_name).stem + ".md"


def process_folder(
    img_dir: Path,
    out_dir: Path,
    *,
    layout_model: str,
    server_url: str,
    api_model_name: str,
    vlm_backend: str = "vllm-server",
) -> dict:
    """Run the pipeline over every image in ``img_dir`` and write per-page ``.md``.

    Returns a summary dict with ``count``, ``ok``, and per-image ``stats``.
    """
    if not img_dir.is_dir():
        raise SystemExit(f"Image directory not found: {img_dir}")
    pipeline = PaddleOCRVLROCm(
        layout_model_dir=layout_model,
        vlm_server_url=server_url,
        api_model_name=api_model_name,
        vlm_backend=vlm_backend,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stats: list[dict] = []
    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    for img in images:
        start = time.time()
        try:
            result = pipeline.predict(img)
            md_path = out_dir / expected_md_name(img.name)
            md_path.write_text(result.markdown_text, encoding="utf-8")
            stats.append(
                {"image": img.name, "status": "ok", "seconds": round(time.time() - start, 2)}
            )
        except Exception as exc:  # noqa: BLE001 - record failure, continue (page scored as empty otherwise)
            stats.append(
                {
                    "image": img.name,
                    "status": f"failed: {exc}",
                    "seconds": round(time.time() - start, 2),
                }
            )
    return {
        "count": len(images),
        "ok": sum(1 for s in stats if s["status"] == "ok"),
        "stats": stats,
    }


def main() -> None:
    # repo root = three levels up from adapters/paddleocr-vl-1.6/run_adapter.py
    repo_root = Path(__file__).resolve().parents[2]
    env = _read_env_local(repo_root)

    # Defaults: CLI flag > ADAPTER_* env var > .env.local > hard-coded fallback.
    # The .env.local values are written by 01-vlm-server/ and 02-layout-model/.
    default_layout = (
        os.environ.get("ADAPTER_LAYOUT_MODEL")
        or env.get("PP_DOCLAYOUTV3_ONNX_DIR")
        or str(repo_root / "adapters" / "paddleocr-vl-1.6" / "models" / "PP-DocLayoutV3-onnx")
    )
    llama_host = env.get("LLAMA_HOST") or "127.0.0.1"
    llama_port = env.get("LLAMA_PORT") or "8111"
    default_server = (
        os.environ.get("ADAPTER_SERVER_URL")
        or f"http://{llama_host}:{llama_port}/v1"
    )
    # VL_REC_API_MODEL_NAME is the model id llama-server reports at /v1/models;
    # the pipeline must ask for the same id or the server returns 404.
    default_api_model = (
        os.environ.get("ADAPTER_API_MODEL_NAME")
        or env.get("VL_REC_API_MODEL_NAME")
        or "PaddleOCR-VL-1.6-GGUF.gguf"
    )

    parser = argparse.ArgumentParser(
        description="PaddleOCR-VL-1.6 adapter for OmniDocBench: write per-page .md"
    )
    parser.add_argument("--img-dir", required=True, help="Dataset images directory.")
    parser.add_argument(
        "--out-dir", required=True, help="Output flat dir of <basename>.md predictions."
    )
    parser.add_argument("--layout-model", default=default_layout, help="PP-DocLayoutV3 ONNX dir.")
    parser.add_argument("--server-url", default=default_server, help="llama-server OpenAI API URL.")
    parser.add_argument(
        "--api-model-name",
        default=default_api_model,
        help="Model id to request at the server's /v1/models (must match what llama-server loads).",
    )
    parser.add_argument("--vlm-backend", default="vllm-server")
    args = parser.parse_args()
    summary = process_folder(
        Path(args.img_dir),
        Path(args.out_dir),
        layout_model=args.layout_model,
        server_url=args.server_url,
        api_model_name=args.api_model_name,
        vlm_backend=args.vlm_backend,
    )
    print(summary)


if __name__ == "__main__":
    main()
