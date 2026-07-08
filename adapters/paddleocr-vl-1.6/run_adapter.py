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
This adapter is *just* the inference driver. It assumes the three provisioning
steps in this directory have already run:

  0. ``00-install-deps/setup.ps1`` -- clones PaddleOCR-VL-ROCm and runs
     ``pip install -e`` so the ``paddleocr_vl_rocm`` package is importable.
  1. ``01-vlm-server/setup.ps1``  -- downloads llama.cpp + the
     PaddleOCR-VL-1.6-GGUF weights, starts ``llama-server`` (OpenAI-compatible
     API), and writes their paths to ``.env.local``.
  2. ``02-layout-model/setup.ps1`` -- downloads the PP-DocLayoutV3 ONNX layout
     model and writes its path to ``.env.local``.

``run_adapter`` reads the same ``.env.local`` for defaults so that, after
provisioning, you can run it with no flags.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from pathlib import Path

# NOTE: paddleocr_vl_rocm is the proven pipeline package from the
# PaddleOCR-VL-ROCm project. Install it once (see README.md); this adapter
# only drives it over a directory of images.
#
# The import is deferred (see process_folder) so the module stays importable
# -- and so `--help` works -- on a machine that has NOT yet installed
# paddleocr_vl_rocm. Importing it at module top level made every `python
# run_adapter.py --help` crash with ModuleNotFoundError before argparse ran.

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif")
ADAPTER_DIR = Path(__file__).resolve().parent
REPO_ROOT = ADAPTER_DIR.parents[1]
DEFAULT_ENGINE = "lightweight"


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
    return run_lightweight_folder(
        img_dir=img_dir,
        out_dir=out_dir,
        layout_model=layout_model,
        server_url=server_url,
        api_model_name=api_model_name,
        vlm_backend=vlm_backend,
    )


def run_lightweight_folder(
    *,
    img_dir: Path,
    out_dir: Path,
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
    # Lazy import: paddleocr_vl_rocm is a heavyweight optional dependency
    # (the PaddleOCR-VL-ROCm pipeline). Importing it here -- rather than at
    # module top level -- keeps the module importable and `--help` working on
    # machines that have not installed it yet.
    from paddleocr_vl_rocm import PaddleOCRVLROCm

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
            # Capture the full traceback so a later post-mortem can distinguish
            # a 500 from the VLM server (message is enough) from an onnxruntime
            # shape error or an internal pipeline failure (needs the traceback).
            tb = traceback.format_exc()
            stats.append(
                {
                    "image": img.name,
                    "status": f"failed: {exc}",
                    "seconds": round(time.time() - start, 2),
                    "traceback": tb,
                }
            )
            # Append each failure to <out_dir>/_errors.log as it happens so the
            # causes survive a killed run or a scrolled terminal. Without this
            # the per-page failures were only held in memory and printed once at
            # the end via print(summary).
            try:
                with open(out_dir / "_errors.log", "a", encoding="utf-8") as fh:
                    fh.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {img.name}: {exc}\n{tb}\n")
            except OSError:
                pass  # never let error-logging itself abort the run

    # Persist the full per-page summary to disk (JSON) so it survives a killed
    # run and is machine-parseable for post-run sanity checks.
    try:
        with open(out_dir / "_run_stats.json", "w", encoding="utf-8") as fh:
            summary = {
                "count": len(images),
                "ok": sum(1 for s in stats if s["status"] == "ok"),
                "fail": sum(1 for s in stats if s["status"] != "ok"),
                "engine": "lightweight",
                "stats": stats,
            }
            json.dump(summary, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass

    ok_count = sum(1 for s in stats if s["status"] == "ok")
    # Post-loop sanity check: if the majority of pages failed (e.g. the VLM
    # server is down), surface it loudly rather than letting score.ps1 score
    # 1650 empty .md files as zero hours later. exit code 2 is distinguishable
    # from a hard crash (1) so callers/agents can route it to pitfalls.md#vlm.
    if len(images) > 0 and ok_count < 0.5 * len(images):
        import sys as _sys
        print(
            f"WARNING: {ok_count}/{len(images)} pages succeeded (< 50%). The VLM "
            f"server is likely down or unreachable -- see docs/pitfalls.md#vlm. "
            f"Per-page failures logged to {out_dir / '_errors.log'}.",
            file=_sys.stderr,
        )
        _sys.exit(2)
    return {
        "count": len(images),
        "ok": ok_count,
        "fail": len(images) - ok_count,
        "engine": "lightweight",
        "stats": stats,
    }


def _official_result_to_markdown(result: object) -> str:
    if isinstance(result, str):
        return result

    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return markdown

    if isinstance(result, dict):
        for key in ("markdown", "md", "content", "markdown_text"):
            value = result.get(key)
            if isinstance(value, str):
                return value

    json_value = getattr(result, "json", None)
    if isinstance(json_value, dict):
        for key in ("markdown", "md", "content", "markdown_text"):
            value = json_value.get(key)
            if isinstance(value, str):
                return value

    for method_name in ("to_markdown", "export_markdown"):
        method = getattr(result, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, str):
                return value

    raise TypeError("Official PaddleOCRVL result did not expose Markdown text.")


def run_official_folder(
    *,
    img_dir: Path,
    out_dir: Path,
    server_url: str,
    api_model_name: str,
) -> dict:
    if not img_dir.is_dir():
        raise SystemExit(f"Image directory not found: {img_dir}")
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise RuntimeError(
            "Official engine requires PaddleOCR. Run 00-install-deps/setup.ps1 first."
        ) from exc

    pipeline = PaddleOCRVL(
        pipeline_version="v1.6",
        vl_rec_backend="llama-cpp-server",
        vl_rec_server_url=server_url,
        vl_rec_api_model_name=api_model_name,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    errors_path = out_dir / "_errors.log"
    stats_path = out_dir / "_run_stats.json"
    errors_path.unlink(missing_ok=True)
    stats_path.unlink(missing_ok=True)

    stats: list[dict] = []
    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    for img in images:
        start = time.time()
        try:
            result = pipeline.predict(str(img))
            if isinstance(result, list):
                markdown = "\n\n".join(_official_result_to_markdown(item) for item in result)
            else:
                markdown = _official_result_to_markdown(result)
            (out_dir / expected_md_name(img.name)).write_text(markdown, encoding="utf-8")
            stats.append(
                {"image": img.name, "status": "ok", "seconds": round(time.time() - start, 2)}
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics continue per page.
            tb = traceback.format_exc()
            stats.append(
                {
                    "image": img.name,
                    "status": f"failed: {exc}",
                    "seconds": round(time.time() - start, 2),
                    "traceback": tb,
                }
            )
            with open(errors_path, "a", encoding="utf-8") as fh:
                fh.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {img.name}: {exc}\n{tb}\n")

    ok_count = sum(1 for s in stats if s["status"] == "ok")
    summary = {
        "count": len(images),
        "ok": ok_count,
        "fail": len(images) - ok_count,
        "engine": "official",
        "stats": stats,
    }
    stats_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(images) > 0 and ok_count < 0.5 * len(images):
        import sys as _sys

        print(
            f"WARNING: {ok_count}/{len(images)} pages succeeded (< 50%). See "
            f"{errors_path} for per-page failures.",
            file=_sys.stderr,
        )
        _sys.exit(2)
    return summary


def _read_adapter_env() -> dict[str, str]:
    values = _read_env_local(ADAPTER_DIR)
    root_values = _read_env_local(REPO_ROOT)
    return {**root_values, **values}


def run_adapter(
    img_dir,
    out_dir,
    server_url: str = "",
    *,
    engine: str = DEFAULT_ENGINE,
    layout_model: str | None = None,
    api_model_name: str | None = None,
    vlm_backend: str = "vllm-server",
) -> dict:
    """Adapter interface contract: images -> one ``<stem>.md`` per page.

    This is the documented entry point every adapter in this repo exposes
    (see ``adapters/README.md`` -> "The adapter interface contract"). It wraps
    :func:`process_folder`, resolving the remaining pipeline defaults
    (layout model, API model name) from ``.env.local`` / ``ADAPTER_*`` env
    vars the same way the CLI does, so a caller only needs the three documented
    arguments.

    Parameters
    ----------
    img_dir : str | Path
        Flat directory of dataset page images.
    out_dir : str | Path
        Output directory; one ``<image_stem>.md`` is written per page.
    server_url : str
        OpenAI-compatible ``/v1`` URL of the VLM server (e.g.
        ``http://127.0.0.1:8111/v1``). Empty string = resolve from
        ``ADAPTER_SERVER_URL`` env var or ``.env.local``.

    Returns
    -------
    dict
        Summary with ``count``, ``ok``, and per-image ``stats`` (same shape as
        :func:`process_folder`). The eval-infra ignores this; it only consumes
        the written ``.md`` files.
    """
    env = _read_adapter_env()
    repo_root = REPO_ROOT

    # Defaults: ADAPTER_* env var > .env.local > hard-coded fallback.
    default_layout = (
        layout_model
        or os.environ.get("ADAPTER_LAYOUT_MODEL")
        or env.get("PP_DOCLAYOUTV3_ONNX_DIR")
        or str(repo_root / "adapters" / "paddleocr-vl-1.6" / "models" / "PP-DocLayoutV3-onnx")
    )
    llama_host = env.get("LLAMA_HOST") or "127.0.0.1"
    llama_port = env.get("LLAMA_PORT") or "8111"
    resolved_server = (
        server_url
        or os.environ.get("ADAPTER_SERVER_URL")
        or f"http://{llama_host}:{llama_port}/v1"
    )
    # VL_REC_API_MODEL_NAME is the model id llama-server reports at /v1/models;
    # the pipeline must ask for the same id or the server returns 404.
    default_api_model = (
        api_model_name
        or os.environ.get("ADAPTER_API_MODEL_NAME")
        or env.get("VL_REC_API_MODEL_NAME")
        or "PaddleOCR-VL-1.6-GGUF.gguf"
    )

    engine = (engine or DEFAULT_ENGINE).strip().lower()
    if engine == "lightweight":
        return run_lightweight_folder(
            img_dir=Path(img_dir),
            out_dir=Path(out_dir),
            layout_model=default_layout,
            server_url=resolved_server,
            api_model_name=default_api_model,
            vlm_backend=vlm_backend,
        )
    if engine == "official":
        return run_official_folder(
            img_dir=Path(img_dir),
            out_dir=Path(out_dir),
            server_url=resolved_server,
            api_model_name=default_api_model,
        )
    raise ValueError("Unsupported engine '%s'. Use lightweight or official." % engine)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PaddleOCR-VL-1.6 adapter for OmniDocBench: write per-page .md"
    )
    parser.add_argument("--img-dir", required=True, help="Dataset images directory.")
    parser.add_argument(
        "--out-dir", required=True, help="Output flat dir of <basename>.md predictions."
    )
    parser.add_argument(
        "--engine",
        choices=["lightweight", "official"],
        default=os.environ.get("PADDLEOCR_VL_ENGINE", DEFAULT_ENGINE),
        help="Adapter engine for subset diagnostics.",
    )
    parser.add_argument("--layout-model", default=None, help="PP-DocLayoutV3 ONNX dir (default: .env.local).")
    parser.add_argument("--server-url", default="", help="llama-server OpenAI API URL (default: .env.local).")
    parser.add_argument(
        "--api-model-name",
        default=None,
        help="Model id to request at the server's /v1/models (must match what llama-server loads).",
    )
    parser.add_argument("--vlm-backend", default="vllm-server")
    args = parser.parse_args()

    # Route through the documented contract (run_adapter) when no advanced
    # overrides are given, so the CLI exercises the same path callers of
    # run_adapter() do. When layout-model / api-model-name / vlm-backend are
    # explicitly overridden, fall through to process_folder() to honor them.
    advanced_override = args.layout_model or args.api_model_name or args.vlm_backend != "vllm-server"
    if not advanced_override:
        summary = run_adapter(
            Path(args.img_dir),
            Path(args.out_dir),
            args.server_url,
            engine=args.engine,
        )
    else:
        summary = run_adapter(
            Path(args.img_dir),
            Path(args.out_dir),
            args.server_url,
            engine=args.engine,
            layout_model=args.layout_model,
            api_model_name=args.api_model_name,
            vlm_backend=args.vlm_backend,
        )
    print(summary)


def _layout_default() -> str:
    repo_root = REPO_ROOT
    env = _read_adapter_env()
    return (
        os.environ.get("ADAPTER_LAYOUT_MODEL")
        or env.get("PP_DOCLAYOUTV3_ONNX_DIR")
        or str(repo_root / "adapters" / "paddleocr-vl-1.6" / "models" / "PP-DocLayoutV3-onnx")
    )


def _api_model_default() -> str:
    env = _read_adapter_env()
    return (
        os.environ.get("ADAPTER_API_MODEL_NAME")
        or env.get("VL_REC_API_MODEL_NAME")
        or "PaddleOCR-VL-1.6-GGUF.gguf"
    )


if __name__ == "__main__":
    main()
