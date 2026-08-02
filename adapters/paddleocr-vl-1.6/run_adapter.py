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
import html
import json
import os
import re
import shutil
import time
import traceback
from pathlib import Path
import sys

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
sys.path.insert(0, str(REPO_ROOT))
from scripts.gt_manifest import load_empty_gt_stems  # noqa: E402
from scripts.windows_paths import through_short_repo  # noqa: E402


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


def _prediction_is_reusable(md_path: Path, empty_gt: set[str] | None = None) -> bool:
    """True only when a previous prediction can be safely reused.

    A previous Markdown may be skipped only if it is a regular file and
    decodes as UTF-8. It must also be non-empty -- UNLESS the page's ground
    truth is itself empty (OmniDocBench v1.6 contains such pages: figures
    plus empty text-masks only), in which case an empty prediction is the
    correct result and regenerating it is pointless. Anything else must be
    regenerated.
    """
    if not md_path.is_file():
        return False
    try:
        content = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if content.strip():
        return True
    return bool(empty_gt) and md_path.stem in empty_gt


def _load_prior_stats(out_dir: Path) -> dict:
    """Load the previous ``_run_stats.json`` if any, upgrading v1 to v2 shape.

    v1 stats (``{count, ok, fail, engine, stats:[...]}``) are mapped onto the
    v2 ``pages`` map so a resume can keep per-page provenance. Invalid or
    missing files yield an empty v2 skeleton.
    """
    stats_path = out_dir / "_run_stats.json"
    empty = {
        "schema_version": 2,
        "engine": "lightweight",
        "selected_pages": 0,
        "newly_processed": 0,
        "skipped_existing": 0,
        "count": 0,
        "ok": 0,
        "fail": 0,
        "pages": {},
        "invocations": [],
        "failed_pages": [],
    }
    if not stats_path.is_file():
        return empty
    try:
        prior = json.loads(stats_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return empty
    if not isinstance(prior, dict):
        return empty
    if prior.get("schema_version") == 2:
        prior.setdefault("pages", {})
        prior.setdefault("invocations", [])
        prior.setdefault("failed_pages", [])
        return prior
    pages: dict[str, dict] = {}
    for entry in prior.get("stats", []) or []:
        if not isinstance(entry, dict) or "image" not in entry:
            continue
        status = "ok" if entry.get("status") == "ok" else "failed"
        pages[entry["image"]] = {
            "status": status,
            "seconds": entry.get("seconds"),
            "source": "resumed",
        }
    return {**empty, "pages": pages, "count": prior.get("count", 0)}


def _write_stats_atomic(stats_path: Path, stats: dict) -> None:
    """Atomically persist stats (temp file + os.replace) so a killed run keeps
    every completed page and its counters."""
    temp = stats_path.with_name(stats_path.name + ".tmp")
    try:
        temp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, stats_path)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _select_images(img_dir: Path, max_pages: int | None = None) -> list[Path]:
    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    if max_pages is None:
        return images
    if max_pages <= 0:
        raise ValueError("max_pages must be positive")
    return images[:max_pages]


def process_folder(
    img_dir: Path,
    out_dir: Path,
    *,
    layout_model: str,
    server_url: str,
    api_model_name: str,
    vlm_backend: str = "vllm-server",
    max_pages: int | None = None,
    skip_existing: bool = False,
    gt_manifest: str | Path | None = None,
) -> dict:
    return run_lightweight_folder(
        img_dir=img_dir,
        out_dir=out_dir,
        layout_model=layout_model,
        server_url=server_url,
        api_model_name=api_model_name,
        vlm_backend=vlm_backend,
        max_pages=max_pages,
        skip_existing=skip_existing,
        gt_manifest=gt_manifest,
    )


def run_lightweight_folder(
    *,
    img_dir: Path,
    out_dir: Path,
    layout_model: str,
    server_url: str,
    api_model_name: str,
    vlm_backend: str = "vllm-server",
    max_pages: int | None = None,
    skip_existing: bool = False,
    gt_manifest: str | Path | None = None,
) -> dict:
    """Run the pipeline over every image in ``img_dir`` and write per-page ``.md``.

    With ``skip_existing`` a previous valid prediction (regular file, UTF-8,
    non-empty -- or empty for a page whose ground truth is itself empty, per
    ``gt_manifest``) for a selected page is reused without re-prediction.
    Page-level progress is persisted atomically after every page, so a killed
    run retains all completed pages and can be resumed safely.

    Returns a summary dict with ``count``, ``ok``, ``fail``, per-image
    ``stats`` (kept for backward compatibility), plus the v2 counters
    ``newly_processed``, ``skipped_existing``, ``failed_pages``,
    ``schema_version``. Skipped valid pages count toward ``ok`` but never
    toward ``newly_processed``.
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
    empty_gt: set[str] = set()
    if gt_manifest is not None:
        gt_path = Path(gt_manifest)
        if gt_path.is_file():
            try:
                empty_gt = load_empty_gt_stems(gt_path)
            except (OSError, UnicodeDecodeError, ValueError, KeyError):
                empty_gt = set()
    out_dir.mkdir(parents=True, exist_ok=True)
    errors_path = out_dir / "_errors.log"
    stats_path = out_dir / "_run_stats.json"
    stats = _load_prior_stats(out_dir)
    stats["engine"] = "lightweight"
    stats["selected_pages"] = 0
    stats["newly_processed"] = 0
    stats["skipped_existing"] = 0
    stats["fail"] = 0
    stats["failed_pages"] = []
    invocation = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "newly_processed": 0,
        "skipped_existing": 0,
        "failed": 0,
    }
    stats["invocations"].append(invocation)

    stats_list: list[dict] = []
    images = _select_images(img_dir, max_pages)
    ok_count = 0
    for img in images:
        start = time.time()
        image_name = img.name
        md_path = out_dir / expected_md_name(image_name)
        if skip_existing and _prediction_is_reusable(md_path, empty_gt):
            stats["skipped_existing"] += 1
            invocation["skipped_existing"] += 1
            ok_count += 1
            stats_list.append(
                {"image": image_name, "status": "ok", "seconds": round(time.time() - start, 2), "source": "resumed"}
            )
            stats["pages"][image_name] = {
                "status": "ok",
                "seconds": round(time.time() - start, 2),
                "source": "resumed",
            }
            stats["ok"] = ok_count
            _write_stats_atomic(stats_path, stats)
            continue
        try:
            result = pipeline.predict(img)
            md_path.write_text(result.markdown_text, encoding="utf-8")
            stats["newly_processed"] += 1
            invocation["newly_processed"] += 1
            ok_count += 1
            stats_list.append(
                {"image": image_name, "status": "ok", "seconds": round(time.time() - start, 2), "source": "fresh"}
            )
            stats["pages"][image_name] = {
                "status": "ok",
                "seconds": round(time.time() - start, 2),
                "source": "fresh",
            }
        except Exception as exc:  # noqa: BLE001 - record failure, continue (page scored as empty otherwise)
            # Capture the full traceback so a later post-mortem can distinguish
            # a 500 from the VLM server (message is enough) from an onnxruntime
            # shape error or an internal pipeline failure (needs the traceback).
            tb = traceback.format_exc()
            stats["newly_processed"] += 1
            invocation["newly_processed"] += 1
            stats["fail"] += 1
            invocation["failed"] += 1
            stats["failed_pages"].append(image_name)
            stats_list.append(
                {
                    "image": image_name,
                    "status": f"failed: {exc}",
                    "seconds": round(time.time() - start, 2),
                    "traceback": tb,
                }
            )
            stats["pages"][image_name] = {
                "status": f"failed: {exc}",
                "seconds": round(time.time() - start, 2),
                "source": "fresh",
            }
            # Append each failure to <out_dir>/_errors.log as it happens so the
            # causes survive a killed run or a scrolled terminal. Without this
            # the per-page failures were only held in memory and printed once at
            # the end via print(summary).
            try:
                with open(errors_path, "a", encoding="utf-8") as fh:
                    fh.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {image_name}: {exc}\n{tb}\n")
            except OSError:
                pass  # never let error-logging itself abort the run
        stats["selected_pages"] = stats_list.__len__()
        stats["count"] = len(images)
        stats["ok"] = ok_count
        stats["newly_processed"] = sum(1 for s in stats_list if s["status"] == "ok" and s.get("source") == "fresh") + stats["fail"]
        invocation["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write_stats_atomic(stats_path, stats)

    summary = {
        "count": len(images),
        "ok": ok_count,
        "fail": len(images) - ok_count,
        "engine": "lightweight",
        "stats": stats_list,
        "schema_version": 2,
        "newly_processed": stats["newly_processed"],
        "skipped_existing": stats["skipped_existing"],
        "failed_pages": list(stats["failed_pages"]),
    }
    stats["selected_pages"] = len(images)
    stats["count"] = len(images)
    stats["ok"] = ok_count
    stats["newly_processed"] = summary["newly_processed"]
    _write_stats_atomic(stats_path, stats)

    # Post-loop sanity check: if the majority of pages failed (e.g. the VLM
    # server is down), surface it loudly rather than letting score.ps1 score
    # 1650 empty .md files as zero hours later. exit code 2 is distinguishable
    # from a hard crash (1) so callers/agents can route it to pitfalls.md#vlm.
    if len(images) > 0 and ok_count < 0.5 * len(images):
        import sys as _sys
        print(
            f"WARNING: {ok_count}/{len(images)} pages succeeded (< 50%). The VLM "
            f"server is likely down or unreachable -- see docs/pitfalls.md#vlm. "
            f"Per-page failures logged to {errors_path}.",
            file=_sys.stderr,
        )
        _sys.exit(2)
    return summary


def _official_result_to_markdown(result: object) -> str:
    def markdown_from_mapping(value: dict) -> str | None:
        for key in ("markdown_texts", "markdown", "md", "content", "markdown_text", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        return None

    if isinstance(result, str):
        return result

    # PaddleOCRVLResult defaults to ``pretty=True`` for display-oriented
    # Markdown, which wraps images/captions in HTML. OmniDocBench's scorer
    # expects plain evaluation Markdown, so prefer the explicit plain export.
    official_export = getattr(result, "_to_markdown", None)
    if callable(official_export):
        try:
            exported = official_export(pretty=False)
        except TypeError:
            exported = None
        if isinstance(exported, dict):
            mapped = markdown_from_mapping(exported)
            if mapped is not None:
                return mapped
        if isinstance(exported, str):
            return exported

    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return markdown
    if isinstance(markdown, dict):
        mapped = markdown_from_mapping(markdown)
        if mapped is not None:
            return mapped

    if isinstance(result, dict):
        mapped = markdown_from_mapping(result)
        if mapped is not None:
            return mapped

    json_value = getattr(result, "json", None)
    if isinstance(json_value, dict):
        mapped = markdown_from_mapping(json_value)
        if mapped is not None:
            return mapped
        res = json_value.get("res")
        if isinstance(res, dict):
            mapped = markdown_from_mapping(res)
            if mapped is not None:
                return mapped

    for method_name in ("to_markdown", "export_markdown"):
        method = getattr(result, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, str):
                return value

    raise TypeError("Official PaddleOCRVL result did not expose Markdown text.")


_CENTERED_IMAGE_DIV_RE = re.compile(
    r"<div[^>]*style=[\"'][^\"']*text-align:\s*center;?[^\"']*[\"'][^>]*>\s*"
    r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>\s*</div>",
    re.IGNORECASE | re.DOTALL,
)
_CENTERED_TEXT_DIV_RE = re.compile(
    r"<div[^>]*style=[\"'][^\"']*text-align:\s*center;?[^\"']*[\"'][^>]*>\s*(.*?)\s*</div>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_official_markdown_for_omnidocbench(markdown: str) -> str:
    """Convert official doc_parser HTML wrappers to scorer-friendly Markdown."""

    def replace_image(match: re.Match[str]) -> str:
        return f"![]({html.unescape(match.group(1))})"

    def replace_text(match: re.Match[str]) -> str:
        inner = _HTML_TAG_RE.sub("", match.group(1))
        return html.unescape(inner.strip())

    markdown = _CENTERED_IMAGE_DIV_RE.sub(replace_image, markdown)
    markdown = _CENTERED_TEXT_DIV_RE.sub(replace_text, markdown)
    return re.sub(r"\n{3,}", "\n\n", markdown)


def run_official_folder(
    *,
    img_dir: Path,
    out_dir: Path,
    server_url: str,
    api_model_name: str,
    page_retries: int = 1,
    fallback_pred_dir: Path | None = None,
    max_pages: int | None = None,
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
    images = _select_images(img_dir, max_pages)
    try:
        page_retries = max(0, int(page_retries))
    except (TypeError, ValueError):
        page_retries = 1
    fallback_pred_dir = Path(fallback_pred_dir) if fallback_pred_dir else None

    def write_error(img_name: str, exc: Exception, tb: str, attempts: int, fallback_from: Path | None = None) -> None:
        with open(errors_path, "a", encoding="utf-8") as fh:
            fh.write(
                f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {img_name}: {exc} "
                f"(attempts={attempts})\n{tb}\n"
            )
            if fallback_from is not None:
                fh.write(f"FALLBACK prediction copied from: {fallback_from}\n")

    for img in images:
        start = time.time()
        attempts = 0
        last_exc: Exception | None = None
        last_tb = ""
        for attempt in range(page_retries + 1):
            attempts = attempt + 1
            try:
                result = pipeline.predict(str(img))
                if isinstance(result, list):
                    markdown = "\n\n".join(_official_result_to_markdown(item) for item in result)
                else:
                    markdown = _official_result_to_markdown(result)
                markdown = _normalize_official_markdown_for_omnidocbench(markdown)
                (out_dir / expected_md_name(img.name)).write_text(markdown, encoding="utf-8")
                stats.append(
                    {
                        "image": img.name,
                        "status": "ok",
                        "seconds": round(time.time() - start, 2),
                        "attempts": attempts,
                    }
                )
                break
            except Exception as exc:  # noqa: BLE001 - diagnostics continue per page.
                last_exc = exc
                last_tb = traceback.format_exc()
                if attempt < page_retries:
                    time.sleep(min(2.0, 0.25 * attempts))
                    continue
        else:
            fallback_path = (
                fallback_pred_dir / expected_md_name(img.name)
                if fallback_pred_dir is not None
                else None
            )
            if fallback_path is not None and fallback_path.is_file():
                shutil.copyfile(fallback_path, out_dir / expected_md_name(img.name))
                assert last_exc is not None
                write_error(img.name, last_exc, last_tb, attempts, fallback_from=fallback_path)
                stats.append(
                    {
                        "image": img.name,
                        "status": f"fallback: {last_exc}",
                        "seconds": round(time.time() - start, 2),
                        "attempts": attempts,
                        "fallback_from": str(fallback_path),
                        "traceback": last_tb,
                    }
                )
            else:
                assert last_exc is not None
                write_error(img.name, last_exc, last_tb, attempts)
                stats.append(
                    {
                        "image": img.name,
                        "status": f"failed: {last_exc}",
                        "seconds": round(time.time() - start, 2),
                        "attempts": attempts,
                        "traceback": last_tb,
                    }
                )

    ok_count = sum(1 for s in stats if s["status"] == "ok" or s["status"].startswith("fallback:"))
    fallback_count = sum(1 for s in stats if s["status"].startswith("fallback:"))
    summary = {
        "count": len(images),
        "ok": ok_count,
        "fail": len(images) - ok_count,
        "fallback": fallback_count,
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
    page_retries: int = 1,
    fallback_pred_dir: str | Path | None = None,
    max_pages: int | None = None,
    skip_existing: bool = False,
    gt_manifest: str | Path | None = None,
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
    skip_existing : bool
        Reuse previous valid predictions instead of re-predicting (per-page
        resume). Only supported by the lightweight engine.
    gt_manifest : str | Path | None
        Dataset manifest used to decide which pages have an empty ground
        truth (their empty predictions are valid and reusable). Optional;
        without it, empty predictions are never reused.

    Returns
    -------
    dict
        Summary with ``count``, ``ok``, and per-image ``stats`` (same shape as
        :func:`process_folder`), plus v2 counters. The eval-infra ignores this;
        it only consumes the written ``.md`` files.
    """
    img_dir = through_short_repo(Path(img_dir), REPO_ROOT)
    out_dir = through_short_repo(Path(out_dir), REPO_ROOT)
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
            img_dir=img_dir,
            out_dir=out_dir,
            layout_model=default_layout,
            server_url=resolved_server,
            api_model_name=default_api_model,
            vlm_backend=vlm_backend,
            max_pages=max_pages,
            skip_existing=skip_existing,
            gt_manifest=gt_manifest,
        )
    if engine == "official":
        if skip_existing:
            raise ValueError("--skip-existing is only supported by the lightweight engine")
        return run_official_folder(
            img_dir=img_dir,
            out_dir=out_dir,
            server_url=resolved_server,
            api_model_name=default_api_model,
            page_retries=page_retries,
            fallback_pred_dir=Path(fallback_pred_dir) if fallback_pred_dir else None,
            max_pages=max_pages,
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
    parser.add_argument(
        "--page-retries",
        type=int,
        default=int(os.environ.get("PADDLEOCR_VL_PAGE_RETRIES", "1")),
        help="Per-page official-engine retries after VLM/parser failures.",
    )
    parser.add_argument(
        "--fallback-pred-dir",
        default=os.environ.get("PADDLEOCR_VL_FALLBACK_PRED_DIR"),
        help="Optional existing prediction dir to copy from when official retries still fail.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Process only the first N images in deterministic filename order.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Reuse previous valid (UTF-8, non-empty) predictions for selected "
        "pages instead of re-predicting; only missing/invalid pages are processed.",
    )
    parser.add_argument(
        "--gt-manifest",
        default=None,
        help="Dataset manifest used to recognize empty-GT pages whose empty "
        "predictions are valid and reusable.",
    )
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
            page_retries=args.page_retries,
            fallback_pred_dir=args.fallback_pred_dir,
            max_pages=args.max_pages,
            skip_existing=args.skip_existing,
            gt_manifest=args.gt_manifest,
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
            page_retries=args.page_retries,
            fallback_pred_dir=args.fallback_pred_dir,
            max_pages=args.max_pages,
            skip_existing=args.skip_existing,
            gt_manifest=args.gt_manifest,
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
