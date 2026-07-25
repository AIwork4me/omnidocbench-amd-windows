"""Validate the image-to-Markdown contract shared by all adapters."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_paths import through_short_repo


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
REPO_ROOT = Path(__file__).resolve().parents[1]


def case_collisions(names: list[str]) -> list[list[str]]:
    grouped: dict[str, list[str]] = {}
    for name in names:
        grouped.setdefault(name.casefold(), []).append(name)
    return [values for values in grouped.values() if len(values) > 1]


def validate_predictions(
    image_dir: Path,
    prediction_dir: Path,
    *,
    minimum_coverage: float = 0.95,
) -> list[str]:
    image_dir = through_short_repo(image_dir, REPO_ROOT)
    prediction_dir = through_short_repo(prediction_dir, REPO_ROOT)
    failures: list[str] = []
    if not 0.0 <= minimum_coverage <= 1.0:
        return ["minimum coverage must be between 0 and 1"]
    if not image_dir.is_dir():
        return [f"image directory not found: {image_dir}"]
    if not prediction_dir.is_dir():
        return [f"prediction directory not found: {prediction_dir}"]

    images = sorted(
        path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        return [f"image directory contains no supported images: {image_dir}"]

    image_names = [path.name for path in images]
    image_stems = [path.stem for path in images]
    for collision in case_collisions(image_stems):
        failures.append(f"case-colliding image stems: {', '.join(collision)}")

    markdown_files = sorted(prediction_dir.glob("*.md"))
    markdown_names = [path.name for path in markdown_files]
    markdown_stems = [path.stem for path in markdown_files]
    for collision in case_collisions(markdown_names):
        failures.append(f"case-colliding prediction names: {', '.join(collision)}")

    expected = set(image_stems)
    produced = set(markdown_stems)
    missing = sorted(expected - produced)
    unexpected = sorted(produced - expected)
    if missing:
        preview = ", ".join(missing[:10])
        suffix = " ..." if len(missing) > 10 else ""
        failures.append(f"missing predictions ({len(missing)}): {preview}{suffix}")
    if unexpected:
        preview = ", ".join(unexpected[:10])
        suffix = " ..." if len(unexpected) > 10 else ""
        failures.append(f"unexpected predictions ({len(unexpected)}): {preview}{suffix}")

    readable_nonempty = 0
    for markdown_path in markdown_files:
        try:
            content = markdown_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            failures.append(f"prediction is not UTF-8: {markdown_path.name} ({error})")
            continue
        if not content.strip():
            failures.append(f"prediction is empty: {markdown_path.name}")
            continue
        if markdown_path.stem in expected:
            readable_nonempty += 1

    coverage = readable_nonempty / len(images)
    if coverage < minimum_coverage:
        failures.append(
            f"usable prediction coverage {readable_nonempty}/{len(images)} "
            f"({coverage:.2%}) is below required {minimum_coverage:.2%}"
        )

    errors_path = prediction_dir / "_errors.log"
    error_entries = 0
    if errors_path.is_file():
        try:
            error_entries = sum(
                1
                for line in errors_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("[")
            )
        except UnicodeDecodeError as error:
            failures.append(f"_errors.log is not UTF-8 ({error})")

    stats_path = prediction_dir / "_run_stats.json"
    if stats_path.is_file():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            failures.append(f"_run_stats.json is invalid UTF-8 JSON ({error})")
        else:
            if stats.get("count") != len(images):
                failures.append(
                    f"_run_stats.json count={stats.get('count')!r} does not match "
                    f"image count={len(images)}"
                )

    print(f"Images: {len(images)}")
    print(f"Markdown files: {len(markdown_files)}")
    print(f"Usable coverage: {readable_nonempty}/{len(images)} ({coverage:.2%})")
    print(f"Error-log entries: {error_entries}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one non-empty UTF-8 Markdown prediction per image"
    )
    parser.add_argument("--img-dir", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--min-coverage", type=float, default=0.95)
    args = parser.parse_args()

    failures = validate_predictions(
        args.img_dir,
        args.pred_dir,
        minimum_coverage=args.min_coverage,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        print(f"PREDICTION VERIFY FAILED ({len(failures)} issue(s))", file=sys.stderr)
        return 1
    print("PREDICTION VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())