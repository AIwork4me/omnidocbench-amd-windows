"""Sample-based prediction equivalence check for resume-after-code-change.

Re-infers a deterministic sample of pages with the CURRENT code and compares
the fresh Markdown byte-for-byte against the stored predictions. If the sample
is fully identical, the stored full set is representative evidence that the
current code reproduces the stored predictions, so completing the run by
resuming (reusing the stored predictions) is safe.

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

Exit 0 = every sampled page reproduces byte-identically.
"""
from __future__ import annotations

import argparse
import json
import shutil
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


def compare_predictions(stored_dir: Path, fresh_dir: Path, stems: list[str]) -> list[dict]:
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
        stored_bytes = stored.read_bytes()
        fresh_bytes = fresh.read_bytes()
        if stored_bytes != fresh_bytes:
            diffs.append(
                {
                    "stem": stem,
                    "issue": "bytes differ",
                    "stored_bytes": len(stored_bytes),
                    "fresh_bytes": len(fresh_bytes),
                }
            )
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--img-dir", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--sample-size", type=int, default=50)
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

    work_dir = Path(tempfile.mkdtemp(prefix="sample-equiv-"))
    try:
        sample_img = build_sample_image_dir(args.img_dir, sample, work_dir)
        fresh_dir = args.out_dir or (work_dir / "fresh")
        fresh_dir.mkdir(parents=True, exist_ok=True)
        import subprocess

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
            check=False,
        )
        if result.returncode != 0:
            print(f"FAIL: fresh inference exited {result.returncode}", file=sys.stderr)
            print(result.stdout[-2000:], file=sys.stderr)
            print(result.stderr[-2000:], file=sys.stderr)
            return 1
        diffs = compare_predictions(args.pred_dir, fresh_dir, sample)
        verdict = "pass" if not diffs else "fail"
        summary = {
            "sample_size": len(sample),
            "stored_total": len(stored_stems),
            "identical": len(sample) - len(diffs),
            "diffs": diffs,
            "verdict": verdict,
            "pred_dir": str(args.pred_dir),
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
                f"FAIL: {len(diffs)}/{len(sample)} sampled predictions differ",
                file=sys.stderr,
            )
            for diff in diffs[:10]:
                print(f"  {diff['stem']}: {diff['issue']}", file=sys.stderr)
            return 1
        print(
            f"OK: {len(sample)}/{len(sample)} sampled predictions byte-identical "
            "to the stored full set"
        )
        return 0
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
