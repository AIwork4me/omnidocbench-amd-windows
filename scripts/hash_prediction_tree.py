"""Deterministic hash of a prediction tree against its manifest.

The hash binds a set of ``<stem>.md`` predictions to the manifest that defines
them. It is the content identity used by:

  * resume invalidation (Task: prediction change must never reuse old scores)
  * the scoring fingerprint
  * metric-result provenance sidecars

Determinism rules
-----------------
* Only manifest-listed ``<stem>.md`` files are hashed; everything else in the
  prediction directory (``_run_stats.json``, ``_errors.log``, stale files) is
  reported separately and never contributes to the tree hash.
* Hashing order is the sorted list of relative paths.
* Each entry contributes ``relative_path | byte_length | sha256``.
* ``mtime`` never participates; identical content in different directories
  yields identical hashes.
* Output JSON is written atomically (temp + ``os.replace``) without a BOM.

The manifest itself is also hashed (``manifest_sha256``) so a tree hash is
never compared across different manifests.

CLI
---
--manifest <path>   dataset manifest (list of {"page_info": {"image_path": ...}})
--pred-dir <dir>    flat prediction directory
--out <path>        write prediction-tree.json (atomic, BOM-less)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest_stems(manifest_path: Path) -> list[str]:
    """Return image stems in manifest order; raise on malformed manifests."""
    pages = json.loads(manifest_path.read_text(encoding="utf-8"))
    stems: list[str] = []
    for page in pages:
        image_path = page.get("page_info", {}).get("image_path")
        if not isinstance(image_path, str) or not image_path:
            raise ValueError(f"manifest page missing page_info.image_path: {page}")
        stems.append(Path(image_path).stem)
    return stems


def hash_prediction_tree(
    manifest_path: Path,
    pred_dir: Path,
) -> dict:
    """Compute the prediction tree hash and per-file metadata.

    Returns a dict with ``prediction_tree_sha256``, per-file ``files``
    entries (path, bytes, sha256), ``missing``, ``unexpected`` and
    ``run_stats_sha256`` (hash of ``_run_stats.json`` when present).
    """
    manifest_sha = sha256_file(manifest_path) or ""
    stems = load_manifest_stems(manifest_path)
    unique = sorted(set(stems))
    if len(unique) != len(stems):
        duplicates = sorted({s for s in stems if stems.count(s) > 1})
        raise ValueError(f"manifest contains duplicate image stems: {duplicates}")

    entries: list[dict] = []
    missing: list[str] = []
    for stem in sorted(unique):
        path = pred_dir / f"{stem}.md"
        if not path.is_file():
            missing.append(stem)
            continue
        digest = sha256_file(path)
        if digest is None:
            missing.append(stem)
            continue
        size = path.stat().st_size
        entries.append({"path": f"{stem}.md", "bytes": size, "sha256": digest})

    markdown_stems = {p.stem for p in pred_dir.glob("*.md") if p.is_file()}
    unexpected = sorted(markdown_stems - set(unique))

    canonical = json.dumps(
        {
            "manifest_sha256": manifest_sha,
            "files": entries,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    tree_sha = hashlib.sha256(canonical).hexdigest()

    return {
        "schema_version": 1,
        "prediction_tree_sha256": tree_sha,
        "manifest_sha256": manifest_sha,
        "expected": len(unique),
        "manifest_unique_stems": len(unique),
        "markdown_files": len(markdown_stems),
        "files": entries,
        "missing": missing,
        "unexpected": unexpected,
        "run_stats_sha256": sha256_file(pred_dir / "_run_stats.json"),
        "generated_at": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = hash_prediction_tree(args.manifest, args.pred_dir)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    temp = args.out.with_name(args.out.name + ".tmp")
    temp.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.replace(args.out)

    print(
        f"Prediction tree: expected={result['expected']} "
        f"files={result['markdown_files']} missing={len(result['missing'])} "
        f"unexpected={len(result['unexpected'])} "
        f"tree_sha256={result['prediction_tree_sha256'][:16]}..."
    )
    for stem in result["missing"]:
        print(f"  missing: {stem}.md", file=sys.stderr)
    for stem in result["unexpected"]:
        print(f"  unexpected: {stem}.md", file=sys.stderr)
    if result["missing"] or result["unexpected"]:
        print("NOTE: prediction tree is incomplete; scoring would use partial input.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
