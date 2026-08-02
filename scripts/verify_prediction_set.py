"""Strict prediction-set acceptance for reproduction profiles.

Extends validate_predictions.py with the full-benchmark gates the formal
paddleocr-vl-hip-full-1651 profile requires:

  * manifest page count must equal --expected-pages exactly
  * every expected stem must have a prediction that is a regular file,
    UTF-8-decodable and non-empty
  * usable coverage >= --min-coverage
  * failed pages (missing + invalid) <= --max-failed-pages
  * with --require-selected, _run_stats.json selected_pages must equal
    --expected-pages (proves the adapter selected the full set)
  * unexpected (non-manifest) predictions are always reported

All missing/invalid pages are listed individually. Writes an optional
prediction-summary.json (atomic, BOM-less).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def validate_prediction_set(
    manifest_path: Path,
    pred_dir: Path,
    *,
    expected_pages: int | None = None,
    min_coverage: float = 0.95,
    max_failed_pages: int | None = None,
    require_selected: bool = False,
) -> tuple[list[str], dict]:
    failures: list[str] = []
    if not pred_dir.is_dir():
        return [f"prediction directory not found: {pred_dir}"], {}
    try:
        pages = json.loads(manifest_path.read_text(encoding="utf-8"))
        image_names = [page["page_info"]["image_path"] for page in pages]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        return [f"manifest is invalid: {manifest_path} ({error})"], {}

    if expected_pages is not None and len(image_names) != expected_pages:
        failures.append(
            f"manifest has {len(image_names)} pages but expected exactly {expected_pages} "
            f"(a {len(image_names)}-page run is not the full set)"
        )
    expected = {Path(name).stem for name in image_names}
    expected_count = len(image_names)

    markdown_stems = {p.stem for p in pred_dir.glob("*.md") if p.is_file()}
    unexpected = sorted(expected.symmetric_difference(markdown_stems) - expected)
    missing = sorted(expected - markdown_stems)

    invalid: list[str] = []
    valid = 0
    for stem in sorted(expected):
        path = pred_dir / f"{stem}.md"
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            invalid.append(f"{stem}.md (not UTF-8)")
            continue
        if not content.strip():
            invalid.append(f"{stem}.md (empty)")
            continue
        valid += 1

    failed = sorted(set(missing) | {name.split(" (")[0] for name in invalid})
    coverage = valid / expected_count if expected_count else 0.0

    if missing:
        preview = ", ".join(missing[:10])
        suffix = " ..." if len(missing) > 10 else ""
        message = f"missing predictions ({len(missing)}): {preview}{suffix}"
        if max_failed_pages is None or len(missing) > max_failed_pages:
            failures.append(message)
        else:
            print(f"NOTE: {message}", file=sys.stderr)
    if invalid:
        preview = ", ".join(invalid[:10])
        suffix = " ..." if len(invalid) > 10 else ""
        message = f"invalid predictions ({len(invalid)}): {preview}{suffix}"
        if max_failed_pages is None or len(invalid) > max_failed_pages:
            failures.append(message)
        else:
            print(f"NOTE: {message}", file=sys.stderr)
    if unexpected:
        preview = ", ".join(unexpected[:10])
        suffix = " ..." if len(unexpected) > 10 else ""
        failures.append(f"unexpected predictions ({len(unexpected)}): {preview}{suffix}")
    if coverage < min_coverage:
        failures.append(
            f"usable coverage {valid}/{expected_count} ({coverage:.4f}) is below "
            f"required {min_coverage:.4f}"
        )
    if max_failed_pages is not None and len(failed) > max_failed_pages:
        failures.append(
            f"failed pages {len(failed)} exceeds maximum allowed {max_failed_pages}"
        )

    selected = None
    if require_selected:
        stats_path = pred_dir / "_run_stats.json"
        if not stats_path.is_file():
            failures.append(f"_run_stats.json missing in {pred_dir} (required to prove the selected set)")
        else:
            try:
                stats = json.loads(stats_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                failures.append(f"_run_stats.json is invalid: {error}")
            else:
                selected = stats.get("selected_pages")
                if selected != expected_count:
                    failures.append(
                        f"_run_stats.json selected_pages={selected} does not equal "
                        f"expected {expected_count}"
                    )

    summary = {
        "expected": expected_count,
        "markdown_files": len(markdown_stems),
        "valid": valid,
        "missing": missing,
        "invalid": invalid,
        "unexpected": unexpected,
        "failed_pages": failed,
        "coverage": round(coverage, 6),
        "selected_pages": selected,
        "verdict": "pass" if not failures else "fail",
    }
    return failures, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--max-failed-pages", type=int)
    parser.add_argument("--require-selected", action="store_true")
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    failures, summary = validate_prediction_set(
        args.manifest,
        args.pred_dir,
        expected_pages=args.expected_pages,
        min_coverage=args.min_coverage,
        max_failed_pages=args.max_failed_pages,
        require_selected=args.require_selected,
    )
    if args.summary_out:
        temp = args.summary_out.with_name(args.summary_out.name + ".tmp")
        temp.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp.replace(args.summary_out)

    print(
        f"Prediction set: expected={summary['expected']} "
        f"valid={summary['valid']}/{summary['expected']} "
        f"failed={len(summary['failed_pages'])} coverage={summary['coverage']:.4f}"
    )
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if failures:
        print(f"PREDICTION SET VERIFY FAILED ({len(failures)} issue(s))", file=sys.stderr)
        return 1
    print("PREDICTION SET VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
