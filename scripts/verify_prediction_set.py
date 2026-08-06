"""Strict prediction-set acceptance for reproduction profiles.

This verifier is the SINGLE source of truth for the prediction-summary.json
schema consumed by the evidence pack (no other component may write that file).
It implements the full-benchmark gates the formal profiles require:

  * manifest page count must equal --expected-pages exactly
  * duplicate image stems in the manifest fail the run
  * every expected stem must have a prediction that is a regular file,
    UTF-8-decodable and non-empty -- EXCEPT pages whose ground truth is
    itself empty (OmniDocBench v1.6 contains such pages: figures plus
    empty text-masks only); for those, an empty prediction is correct and
    counts as valid (empty_gt_valid)
  * usable coverage >= --min-coverage
  * failed pages (missing + invalid) <= --max-failed-pages
  * with --require-selected, _run_stats.json selected_pages must equal
    --expected-pages (proves the adapter selected the full set)
  * unexpected (non-manifest) predictions are always reported
  * with --allowed-failed-page-stems (formal profiles), failures outside the
    allowlist are a hard failure (unknown_failures) regardless of the total
    budget; failures inside the allowlist are permitted up to
    --max-failed-pages; allowed stems that now succeed are reported as
    recovered_known_failures. Without an allowlist the legacy budget semantics
    apply (missing/invalid pages pass when within --max-failed-pages).
  * with --require-selected, _run_stats.json per-page failed status must agree
    with the actual missing/invalid prediction files

Summary schema (written atomically, BOM-less):
  expected, manifest_unique_stems, markdown_files, valid, empty_gt_valid,
  missing, invalid, unexpected, known_allowed_failures, unknown_failures,
  recovered_known_failures, coverage, selected_pages,
  prediction_tree_sha256 (from --prediction-tree-json), verdict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from gt_manifest import load_empty_gt_stems

REPO_ROOT = Path(__file__).resolve().parent.parent


def _accessible(path: Path) -> str:
    """Return a path Windows APIs can open even past MAX_PATH (260 chars).

    Long manifest stems can push a prediction path past 260 UTF-16 units on
    Windows; Python's os.stat()/open() then fail with WinError 3 even though
    directory enumeration still sees the file. The extended-length ``\\?\``
    prefix restores access. Non-Windows and short paths are unchanged.
    """
    value = os.fspath(path)
    if os.name != "nt" or not isinstance(value, str) or value.startswith("\\\\?\\"):
        return value
    absolute = os.path.abspath(value)
    if len(absolute) >= 250:
        return "\\\\?\\" + absolute
    return value


def _is_file(path: Path) -> bool:
    return os.path.isfile(_accessible(path))


def _read_text(path: Path, encoding: str = "utf-8") -> str:
    with open(_accessible(path), "r", encoding=encoding) as fh:
        return fh.read()


def validate_prediction_set(
    manifest_path: Path,
    pred_dir: Path,
    *,
    expected_pages: int | None = None,
    min_coverage: float = 0.95,
    max_failed_pages: int | None = None,
    require_selected: bool = False,
    allowed_failed_page_stems: set[str] | None = None,
    prediction_tree_sha256: str | None = None,
) -> tuple[list[str], dict]:
    failures: list[str] = []
    allowed = allowed_failed_page_stems or set()
    if not os.path.isdir(_accessible(pred_dir)):
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
    if len(expected) != expected_count:
        duplicates = sorted(
            {Path(name).stem for name in image_names}
            if len({Path(name).stem for name in image_names}) < expected_count
            else set()
        )
        seen = set()
        dup = sorted(s for s in expected if s in seen or seen.add(s))
        failures.append(f"manifest contains duplicate image stems: {dup}")
    empty_gt = load_empty_gt_stems(manifest_path)

    # Use scandir's DirEntry data (FindFirstFileW) so >260-char names are still
    # visible; a Path.is_file() call would stat and fail on those paths.
    markdown_stems = {
        Path(entry.name).stem
        for entry in os.scandir(pred_dir)
        if entry.is_file() and entry.name.lower().endswith(".md")
    }
    unexpected = sorted(expected.symmetric_difference(markdown_stems) - expected)
    missing = sorted(expected - markdown_stems)

    invalid: list[str] = []
    invalid_stems: list[str] = []
    valid = 0
    empty_gt_valid = 0
    for stem in sorted(expected):
        path = pred_dir / f"{stem}.md"
        if not _is_file(path):
            continue
        try:
            content = _read_text(path)
        except (OSError, UnicodeDecodeError):
            invalid.append(f"{stem}.md (not UTF-8)")
            invalid_stems.append(stem)
            continue
        if not content.strip():
            if stem in empty_gt:
                # Empty prediction for an empty-GT page is correct.
                valid += 1
                empty_gt_valid += 1
            else:
                invalid.append(f"{stem}.md (empty, GT non-empty)")
                invalid_stems.append(stem)
            continue
        valid += 1

    failed = sorted(set(missing) | set(invalid_stems))
    known_allowed_failures = sorted(set(failed) & allowed)
    unknown_failures = sorted(set(failed) - allowed)
    recovered_known_failures = sorted(allowed - set(failed))
    coverage = valid / expected_count if expected_count else 0.0

    # Without an allowlist the legacy budget semantics apply: missing/invalid
    # pages are permitted up to --max-failed-pages. With an allowlist (formal
    # profiles) only allowlisted failures are permitted, still within the
    # total budget; anything else is a hard failure.
    strict = bool(allowed)
    if missing:
        if strict:
            unknown_missing = sorted(set(missing) - allowed)
        else:
            unknown_missing = missing
        if unknown_missing:
            preview = ", ".join(unknown_missing[:10])
            suffix = " ..." if len(unknown_missing) > 10 else ""
            if max_failed_pages is None or len(unknown_missing) > max_failed_pages:
                failures.append(
                    f"missing predictions ({len(unknown_missing)}): {preview}{suffix}"
                )
            else:
                print(
                    f"NOTE: missing predictions ({len(unknown_missing)}): {preview}{suffix}",
                    file=sys.stderr,
                )
        elif missing:
            print(
                f"NOTE: missing predictions all on the known-failure allowlist "
                f"({len(missing)}): {', '.join(missing)}",
                file=sys.stderr,
            )
    if invalid:
        if strict:
            unknown_invalid = sorted(set(invalid_stems) - allowed)
        else:
            unknown_invalid = invalid_stems
        if unknown_invalid:
            preview = ", ".join(
                f"{stem}.md" for stem in unknown_invalid[:10]
            )
            suffix = " ..." if len(unknown_invalid) > 10 else ""
            if max_failed_pages is None or len(unknown_invalid) > max_failed_pages:
                failures.append(
                    f"invalid predictions ({len(unknown_invalid)}): {preview}{suffix}"
                )
            else:
                print(
                    f"NOTE: invalid predictions ({len(unknown_invalid)}): {preview}{suffix}",
                    file=sys.stderr,
                )
        elif invalid:
            print(
                f"NOTE: invalid predictions all on the known-failure allowlist "
                f"({len(invalid)}): {', '.join(invalid)}",
                file=sys.stderr,
            )
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
    if strict and unknown_failures:
        preview = ", ".join(unknown_failures[:10])
        suffix = " ..." if len(unknown_failures) > 10 else ""
        failures.append(
            f"unknown failed pages ({len(unknown_failures)}) outside the allowlist "
            f"are not permitted: {preview}{suffix}"
        )

    selected = None
    if require_selected:
        stats_path = pred_dir / "_run_stats.json"
        if not _is_file(stats_path):
            failures.append(f"_run_stats.json missing in {pred_dir} (required to prove the selected set)")
        else:
            try:
                stats = json.loads(_read_text(stats_path))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                failures.append(f"_run_stats.json is invalid: {error}")
            else:
                selected = stats.get("selected_pages")
                if selected != expected_count:
                    failures.append(
                        f"_run_stats.json selected_pages={selected} does not equal "
                        f"expected {expected_count}"
                    )
                stats_failed = {
                    Path(name).stem
                    for name in (stats.get("failed_pages") or [])
                    if isinstance(name, str)
                }
                missing_not_recorded = sorted(set(missing) - stats_failed)
                if missing_not_recorded:
                    failures.append(
                        f"stats failed_pages does not cover missing predictions: "
                        f"{missing_not_recorded}"
                    )
                actual_failed = set(missing) | set(invalid_stems)
                page_map = stats.get("pages") or {}
                if not isinstance(page_map, dict):
                    failures.append("_run_stats.json has no per-page 'pages' map")
                else:
                    # stats keys are image file names ("a.png"); match by stem.
                    stats_stems = {Path(name).stem: entry for name, entry in page_map.items()}
                    for stem in sorted(actual_failed):
                        entry = stats_stems.get(stem)
                        if entry is None or str(entry.get("status", "")).startswith("ok"):
                            failures.append(
                                f"_run_stats.json marks {stem} as ok but its prediction "
                                f"is missing or invalid"
                            )
                    for stem, entry in stats_stems.items():
                        status = str(entry.get("status", ""))
                        if not status.startswith("ok") and stem not in actual_failed:
                            failures.append(
                                f"_run_stats.json marks {stem} as failed but its "
                                f"prediction file is present and valid"
                            )

    summary = {
        "expected": expected_count,
        "manifest_unique_stems": len(expected),
        "markdown_files": len(markdown_stems),
        "valid": valid,
        "empty_gt_valid": empty_gt_valid,
        "missing": missing,
        "invalid": invalid,
        "unexpected": unexpected,
        "failed_pages": failed,
        "known_allowed_failures": known_allowed_failures,
        "unknown_failures": unknown_failures,
        "recovered_known_failures": recovered_known_failures,
        "coverage": round(coverage, 6),
        "selected_pages": selected,
        "prediction_tree_sha256": prediction_tree_sha256,
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
    parser.add_argument(
        "--allowed-failed-page-stems",
        action="append",
        default=[],
        help="repeatable: known-failure page stems permitted within the failed-page budget",
    )
    parser.add_argument(
        "--prediction-tree-json",
        type=Path,
        help="prediction-tree.json from hash_prediction_tree.py; its sha256 is recorded in the summary",
    )
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    prediction_tree_sha256 = None
    if args.prediction_tree_json is not None:
        try:
            tree = json.loads(args.prediction_tree_json.read_text(encoding="utf-8"))
            prediction_tree_sha256 = tree.get("prediction_tree_sha256")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            print(f"FAIL: cannot read prediction tree json: {error}", file=sys.stderr)
            return 1
        if not prediction_tree_sha256:
            print("FAIL: prediction-tree.json has no prediction_tree_sha256", file=sys.stderr)
            return 1

    allowed = set()
    for raw in args.allowed_failed_page_stems:
        for stem in raw.split(","):
            stem = stem.strip()
            if stem:
                allowed.add(stem)

    failures, summary = validate_prediction_set(
        args.manifest,
        args.pred_dir,
        expected_pages=args.expected_pages,
        min_coverage=args.min_coverage,
        max_failed_pages=args.max_failed_pages,
        require_selected=args.require_selected,
        allowed_failed_page_stems=allowed,
        prediction_tree_sha256=prediction_tree_sha256,
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
        f"failed={len(summary['failed_pages'])} "
        f"known_allowed={len(summary['known_allowed_failures'])} "
        f"unknown={len(summary['unknown_failures'])} "
        f"recovered_known={len(summary['recovered_known_failures'])} "
        f"coverage={summary['coverage']:.4f}"
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
