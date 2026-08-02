"""Compare two prediction dirs page-by-page.

Outputs: exact-match rate, mean difflib.SequenceMatcher ratio, per-page
worst-10 divergences. Usage:
python scripts/compare_prediction_sets.py --a predictions/mineru_pipeline --b predictions/mineru_sample81_repro --stems tmp_sample81.txt
"""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path


def read_page(directory: Path, stem: str) -> str | None:
    path = directory / f"{stem}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def first_diff_line(a: str, b: str) -> tuple[str, str]:
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    for index in range(max(len(a_lines), len(b_lines))):
        a_line = a_lines[index] if index < len(a_lines) else "<missing>"
        b_line = b_lines[index] if index < len(b_lines) else "<missing>"
        if a_line != b_line:
            return a_line, b_line
    return "", ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", required=True, type=Path, help="Reference prediction dir")
    parser.add_argument("--b", required=True, type=Path, help="Candidate prediction dir")
    parser.add_argument("--stems", required=True, type=Path, help="List file with one page stem per line")
    parser.add_argument("--json", type=Path, default=None, help="Optional machine-readable summary output")
    parser.add_argument("--worst", type=int, default=10, help="Number of worst divergences to print")
    args = parser.parse_args()

    stems = [line.strip() for line in args.stems.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not stems:
        parser.error(f"no stems in {args.stems}")

    pages = []
    missing_a: list[str] = []
    missing_b: list[str] = []
    for stem in stems:
        content_a = read_page(args.a, stem)
        content_b = read_page(args.b, stem)
        if content_a is None:
            missing_a.append(stem)
        if content_b is None:
            missing_b.append(stem)
        if content_a is None or content_b is None:
            pages.append({"stem": stem, "exact": False, "ratio": 0.0,
                          "len_a": len(content_a or ""), "len_b": len(content_b or "")})
            continue
        ratio = 1.0 if content_a == content_b else difflib.SequenceMatcher(None, content_a, content_b).ratio()
        pages.append({"stem": stem, "exact": content_a == content_b, "ratio": ratio,
                      "len_a": len(content_a), "len_b": len(content_b),
                      "content_a": content_a, "content_b": content_b})

    exact_count = sum(1 for page in pages if page["exact"])
    mean_ratio = sum(page["ratio"] for page in pages) / len(pages)
    min_ratio = min(page["ratio"] for page in pages)

    print(f"pages compared : {len(pages)}")
    print(f"missing in a   : {len(missing_a)} {missing_a[:5] if missing_a else ''}")
    print(f"missing in b   : {len(missing_b)} {missing_b[:5] if missing_b else ''}")
    print(f"EXACT_MATCH    : {exact_count}/{len(pages)} = {exact_count / len(pages):.4f}")
    print(f"MEAN_RATIO     : {mean_ratio:.6f}")
    print(f"MIN_RATIO      : {min_ratio:.6f}")

    divergent = sorted((page for page in pages if not page["exact"]), key=lambda page: page["ratio"])
    print(f"\nworst-{args.worst} divergences:")
    for page in divergent[: args.worst]:
        print(f"  {page['stem']}  ratio={page['ratio']:.4f}  len_a={page['len_a']}  len_b={page['len_b']}")
        if "content_a" in page:
            a_line, b_line = first_diff_line(page["content_a"], page["content_b"])
            print(f"    a| {a_line[:120]}")
            print(f"    b| {b_line[:120]}")

    if args.json is not None:
        summary = {
            "a": str(args.a),
            "b": str(args.b),
            "stems": str(args.stems),
            "pages": len(pages),
            "exact_count": exact_count,
            "exact_rate": exact_count / len(pages),
            "mean_ratio": mean_ratio,
            "min_ratio": min_ratio,
            "missing_a": missing_a,
            "missing_b": missing_b,
            "per_page": [
                {"stem": page["stem"], "exact": page["exact"], "ratio": page["ratio"],
                 "len_a": page["len_a"], "len_b": page["len_b"]}
                for page in pages
            ],
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"\nsummary json: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
