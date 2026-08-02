"""Deterministic stratified sample of the OmniDocBench v1.6 image set.

Usage: python scripts/sample_stratified.py --img-dir <images> --per-category 9 --seed 42 --out <list.txt> [--copy-to <dir>]

Category = filename prefix up to the first '_' (book, newspaper, PPT, ...).
Files with no '_' (the 296 page-<uuid> hard-subset images) fall back to the
prefix up to the first '-' so they form one "page" stratum instead of 296
singleton strata. Sort each category's files (ordinal codepoint order), take
every k-th (k = ceil(n/per_category)) after a seeded offset. Prints category
counts. No third-party deps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def category_of(name: str) -> str:
    underscore = name.find("_")
    if underscore > 0:
        return name[:underscore]
    dash = name.find("-")
    if dash > 0:
        return name[:dash]
    return name


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--img-dir", required=True, type=Path)
    parser.add_argument("--per-category", type=int, default=9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True, type=Path, help="Sample list file (one image stem per line)")
    parser.add_argument("--copy-to", type=Path, default=None, help="Optional directory to copy sampled images into")
    parser.add_argument("--gt-manifest", type=Path, default=None, help="Optional full OmniDocBench.json to filter")
    parser.add_argument("--gt-out", type=Path, default=None, help="Optional output path for the sample-only GT manifest")
    args = parser.parse_args()

    if args.per_category < 1:
        parser.error("--per-category must be >= 1")
    if not args.img_dir.is_dir():
        parser.error(f"image directory not found: {args.img_dir}")

    images = sorted(
        (p for p in args.img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda p: p.name,
    )
    if not images:
        parser.error(f"no images found in {args.img_dir}")

    by_stem: dict[str, Path] = {}
    for path in images:
        if path.stem in by_stem:
            parser.error(f"duplicate image stem with different extensions: {path.name} vs {by_stem[path.stem].name}")
        by_stem[path.stem] = path

    categories: dict[str, list[str]] = {}
    for path in images:
        categories.setdefault(category_of(path.name), []).append(path.name)

    rng = random.Random(args.seed)
    picked: list[str] = []
    print(f"images: {len(images)}  categories: {len(categories)}  per_category: {args.per_category}  seed: {args.seed}")
    print(f"{'category':<18}{'total':>6}{'stride':>7}{'picked':>7}")
    for category in sorted(categories):
        members = categories[category]
        n = len(members)
        stride = math.ceil(n / args.per_category)
        offset = rng.randrange(stride)
        chosen = members[offset::stride][: args.per_category]
        picked.extend(chosen)
        print(f"{category:<18}{n:>6}{stride:>7}{len(chosen):>7}")

    stems = sorted(Path(name).stem for name in picked)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(f"{stem}\n" for stem in stems), encoding="utf-8", newline="\n")
    print(f"sample pages: {len(stems)}")
    print(f"list: {args.out}  sha256: {sha256_of(args.out)}")

    if args.copy_to is not None:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        for stem in stems:
            shutil.copy2(by_stem[stem], args.copy_to / by_stem[stem].name)
        print(f"copied {len(stems)} images -> {args.copy_to}")

    if args.gt_manifest is not None or args.gt_out is not None:
        if args.gt_manifest is None or args.gt_out is None:
            parser.error("--gt-manifest and --gt-out must be given together")
        manifest = json.loads(args.gt_manifest.read_text(encoding="utf-8"))
        wanted = set(stems)
        filtered = [
            sample for sample in manifest
            if Path(sample["page_info"]["image_path"]).stem in wanted
        ]
        if len(filtered) != len(wanted):
            matched = {Path(s["page_info"]["image_path"]).stem for s in filtered}
            missing = sorted(wanted - matched)
            parser.error(f"GT manifest matched {len(filtered)} of {len(wanted)} sample stems; missing: {missing[:5]}")
        args.gt_out.parent.mkdir(parents=True, exist_ok=True)
        args.gt_out.write_text(json.dumps(filtered, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"gt: {args.gt_out}  pages: {len(filtered)}  sha256: {sha256_of(args.gt_out)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
