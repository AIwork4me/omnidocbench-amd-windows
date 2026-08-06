"""Build an OmniDocBench ground-truth manifest from available predictions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gt_manifest import page_has_empty_gt
from windows_paths import through_short_repo

REPO_ROOT = Path(__file__).resolve().parents[1]


def _accessible(path: Path) -> str:
    """Return a path Windows APIs can open even past MAX_PATH (260 chars)."""
    value = os.fspath(path)
    if os.name != "nt" or not isinstance(value, str) or value.startswith("\\\\?\\"):
        return value
    absolute = os.path.abspath(value)
    if len(absolute) >= 250:
        return "\\\\?\\" + absolute
    return value


def _read_text(path: Path, encoding: str = "utf-8") -> str:
    with open(_accessible(path), "r", encoding=encoding) as fh:
        return fh.read()


def build_subset(
    full_manifest: Path,
    prediction_dir: Path,
    output_manifest: Path,
    *,
    limit: int | None = None,
) -> list[dict]:
    prediction_dir = through_short_repo(prediction_dir, REPO_ROOT)
    pages = json.loads(full_manifest.read_text(encoding="utf-8"))
    if not isinstance(pages, list):
        raise ValueError("full manifest must contain a JSON list")

    page_by_stem: dict[str, dict] = {}
    for page in pages:
        image_path = page.get("page_info", {}).get("image_path")
        if not isinstance(image_path, str) or not image_path:
            raise ValueError("manifest page is missing page_info.image_path")
        stem = Path(image_path).stem
        if stem in page_by_stem:
            raise ValueError(f"duplicate manifest image stem: {stem}")
        page_by_stem[stem] = page

    prediction_stems: list[str] = []
    for prediction in sorted(prediction_dir.glob("*.md"), key=lambda path: path.name.casefold()):
        try:
            content = _read_text(prediction)
        except UnicodeDecodeError as error:
            raise ValueError(f"prediction is not UTF-8: {prediction.name}") from error
        page = page_by_stem.get(prediction.stem)
        empty_gt = page is not None and page_has_empty_gt(page)
        if content.strip() or empty_gt:
            # An empty prediction is usable when the page's ground truth is
            # itself empty (figures-only pages): the verifier counts those as
            # valid, so they must survive the subset build.
            prediction_stems.append(prediction.stem)

    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        prediction_stems = prediction_stems[:limit]

    missing = sorted(set(prediction_stems) - set(page_by_stem))
    if missing:
        raise ValueError(f"predictions have no ground truth: {', '.join(missing[:10])}")
    if not prediction_stems:
        raise ValueError("no usable Markdown predictions found (non-empty, or empty-GT)")
    if limit is not None and len(prediction_stems) < limit:
        raise ValueError(
            f"only {len(prediction_stems)} usable predictions found; {limit} required"
        )

    subset = [page_by_stem[stem] for stem in prediction_stems]
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(subset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return subset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build exact ground truth for the pages with usable predictions"
    )
    parser.add_argument("--full-manifest", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    subset = build_subset(
        args.full_manifest,
        args.pred_dir,
        args.output,
        limit=args.limit,
    )
    print(f"Wrote {len(subset)} pages to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
