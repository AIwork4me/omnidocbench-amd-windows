"""Verify every manifest-referenced OmniDocBench image against a tree digest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_paths import through_short_repo


REPO_ROOT = Path(__file__).resolve().parents[1]


def dataset_tree_digest(
    manifest: Path, image_dir: Path, repo_root: Path = REPO_ROOT
) -> tuple[int, int, str]:
    manifest = through_short_repo(manifest, repo_root)
    image_dir = through_short_repo(image_dir, repo_root)
    pages = json.loads(manifest.read_text(encoding="utf-8"))
    refs = sorted(page["page_info"]["image_path"] for page in pages)
    tree = hashlib.sha256()
    total_bytes = 0
    for ref in refs:
        image_path = image_dir / ref
        if not image_path.is_file():
            raise FileNotFoundError(f"manifest-referenced image missing: {ref}")
        digest = hashlib.sha256()
        with image_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        size = image_path.stat().st_size
        total_bytes += size
        tree.update(ref.replace("\\", "/").encode("utf-8"))
        tree.update(b"\0")
        tree.update(str(size).encode("ascii"))
        tree.update(b"\0")
        tree.update(digest.hexdigest().encode("ascii"))
        tree.update(b"\n")
    return len(refs), total_bytes, tree.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=REPO_ROOT / "upstream-lock.json")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    expected = lock["huggingface"]["dataset"]["manifest"]
    count, total_bytes, digest = dataset_tree_digest(
        args.manifest, args.image_dir, args.repo_root
    )
    failures = []
    if count != expected["pages"]:
        failures.append(f"pages: expected {expected['pages']}, actual {count}")
    if total_bytes != expected["referenced_image_bytes"]:
        failures.append(
            f"image bytes: expected {expected['referenced_image_bytes']}, actual {total_bytes}"
        )
    if digest.lower() != expected["referenced_image_tree_sha256"].lower():
        failures.append(
            "tree SHA-256: expected "
            f"{expected['referenced_image_tree_sha256']}, actual {digest}"
        )
    if failures:
        raise SystemExit("Dataset tree lock mismatch:\n" + "\n".join(failures))
    print(f"DATASET TREE LOCK OK: {count} files, {total_bytes} bytes, {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())