"""Sample-based prediction equivalence check for resume-after-code-change.

Re-infers a deterministic sample of pages with the CURRENT code and compares
the fresh Markdown against the stored predictions. If the sample is
equivalent, the stored full set is representative evidence that the current
code reproduces the stored predictions, so completing the run by resuming
(reusing the stored predictions) is safe.

Equivalence is CONTENT-based, not byte-based: PaddleOCR-VL-1.6 GGUF outputs
are not byte-reproducible across independent runs (glyph-level bullet/quote
variants, and structural variance in reconstructed table HTML). Two outputs
are equivalent when their difflib similarity ratio >= --min-similarity
(default 0.95). Byte-identical outputs trivially pass.

Selection: deterministic stride sampling over the sorted stored stems (no
RNG), so the same sample is reproducible. Pages with no stored prediction are
skipped (they are the run's documented failed pages).

Usage (Windows, repo root, after the VLM server is up):

    .venv\\Scripts\\python.exe scripts\\sample_prediction_equivalence.py ^
        --img-dir eval-infra\\01-omnidocbench\\data\\images ^
        --pred-dir predictions\\paddleocrvl_hip_full_1651 ^
        --out-dir <temp-fresh-predictions> ^
        --server-url http://127.0.0.1:8123/v1 ^
        --sample-size 50 ^
        --summary-out <evidence-dir>\\sample-equivalence.json

To re-run the comparison against an existing fresh directory without new
inference, pass --compare-only <fresh-dir> instead of --out-dir.

Exit 0 = every sampled page is content-equivalent to the stored prediction.
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTER = REPO_ROOT / "adapters" / "paddleocr-vl-1.6" / "run_adapter.py"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def select_sample(stored_stems: list[str], sample_size: int) -> list[str]:
    """Deterministic stride sampling: every k-th stem of the sorted list."""
    stems = sorted(stored_stems)
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    if sample_size >= len(stems):
        return stems
    stride = len(stems) / sample_size
    selected: list[str] = []
    for i in range(sample_size):
        index = int(i * stride)
        if index < len(stems) and stems[index] not in selected:
            selected.append(stems[index])
    return selected


def build_sample_image_dir(img_dir: Path, stems: list[str], work_dir: Path) -> Path:
    """Copy the sampled pages' images into an isolated directory."""
    sample_img = work_dir / "images"
    sample_img.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        source = None
        for ext in IMAGE_EXTENSIONS:
            candidate = img_dir / f"{stem}{ext}"
            if candidate.is_file():
                source = candidate
                break
        if source is None:
            raise FileNotFoundError(f"image for stem {stem} not found in {img_dir}")
        shutil.copy2(source, sample_img / source.name)
    return sample_img


def _similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def compare_predictions(
    stored_dir: Path, fresh_dir: Path, stems: list[str], min_similarity: float = 0.95
) -> list[dict]:
    diffs: list[dict] = []
    for stem in stems:
        stored = stored_dir / f"{stem}.md"
        fresh = fresh_dir / f"{stem}.md"
        if not stored.is_file():
            diffs.append({"stem": stem, "issue": "stored prediction missing"})
            continue
        if not fresh.is_file():
            diffs.append({"stem": stem, "issue": "fresh prediction missing"})
            continue
        stored_text = stored.read_text(encoding="utf-8", errors="replace")
        fresh_text = fresh.read_text(encoding="utf-8", errors="replace")
        ratio = _similarity(stored_text, fresh_text)
        if ratio < min_similarity:
            diffs.append(
                {
                    "stem": stem,
                    "issue": "content differs",
                    "similarity": round(ratio, 4),
                    "stored_chars": len(stored_text),
                    "fresh_chars": len(fresh_text),
                }
            )
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--img-dir", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--compare-only", type=Path)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--min-similarity", type=float, default=0.95)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    stored_stems = sorted(
        p.stem for p in args.pred_dir.glob("*.md") if p.is_file()
    )
    if not stored_stems:
        print("FAIL: no stored predictions found", file=sys.stderr)
        return 1
    sample = select_sample(stored_stems, args.sample_size)
    print(f"Sampled {len(sample)} of {len(stored_stems)} stored predictions")

    fresh_dir = args.compare_only
    work_dir: Path | None = None
    try:
        if fresh_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="sample-equiv-"))
            sample_img = build_sample_image_dir(args.img_dir, sample, work_dir)
            fresh_dir = args.out_dir or (work_dir / "fresh")
            fresh_dir.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ADAPTER),
                    "--img-dir", str(sample_img),
                    "--out-dir", str(fresh_dir),
                    "--server-url", args.server_url,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                print(f"FAIL: fresh inference exited {result.returncode}", file=sys.stderr)
                print(result.stdout[-2000:], file=sys.stderr)
                print(result.stderr[-2000:], file=sys.stderr)
                return 1
        else:
            if not fresh_dir.is_dir():
                print(f"FAIL: compare-only dir not found: {fresh_dir}", file=sys.stderr)
                return 1
        diffs = compare_predictions(
            args.pred_dir, fresh_dir, sample, min_similarity=args.min_similarity
        )
        verdict = "pass" if not diffs else "fail"
        summary = {
            "sample_size": len(sample),
            "stored_total": len(stored_stems),
            "equivalent": len(sample) - len(diffs),
            "min_similarity": args.min_similarity,
            "diffs": diffs,
            "verdict": verdict,
            "pred_dir": str(args.pred_dir),
            "fresh_dir": str(fresh_dir),
            "server_url": args.server_url,
        }
        if args.summary_out:
            temp = args.summary_out.with_name(args.summary_out.name + ".tmp")
            temp.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp.replace(args.summary_out)
        if diffs:
            print(
                f"FAIL: {len(diffs)}/{len(sample)} sampled predictions differ "
                f"(similarity < {args.min_similarity})",
                file=sys.stderr,
            )
            for diff in diffs[:10]:
                print(f"  {diff['stem']}: {diff['issue']}", file=sys.stderr)
            return 1
        print(
            f"OK: {len(sample)}/{len(sample)} sampled predictions content-equivalent "
            f"(min similarity {args.min_similarity}) to the stored full set"
        )
        return 0
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

