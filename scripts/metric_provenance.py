"""Metric-result provenance sidecars: write and verify.

Every ``<save_name>_metric_result.json`` produced by a reproduction run gets a
sidecar ``<save_name>_metric_result.provenance.json`` binding the result to:

  * the prediction tree hash it was scored from (prediction_tree_sha256)
  * the manifest hash (prediction_manifest_sha256)
  * the scoring config hash (scoring_config_sha256)
  * the scorer checkout commit and scoring-code tree hash
  * the result file's own sha256 (metric_result_sha256)
  * expected_pages, save_name, aggregation_mode, platform

When a resume reuses a passed scoring stage, the sidecar is re-verified
against the CURRENT prediction tree / manifest / config / result bytes. Any
mismatch (or a missing sidecar) invalidates the stage and forces re-scoring,
so a stale score can never be reused.

CLI
---
write  --result <json> --out <sidecar.json> --prediction-tree <sha256>
       --manifest <path> --config <path> --scorer-checkout <dir>
       --scoring-code-dir <dir> --expected-pages <int> --save-name <name>
       [--aggregation-mode <mode>] --platform <windows|wsl>
verify --result <json> --out <sidecar.json>  (same inputs; recomputes and
       compares every field except generated_at; exit 1 on mismatch)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
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


def git_commit(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def tree_sha256(root: Path) -> str | None:
    if not root.is_dir():
        return None
    parts: list[bytes] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in {"__pycache__", ".git", ".venv"} for part in Path(rel).parts):
            continue
        digest = sha256_file(path)
        if digest is None:
            continue
        parts.append(f"{rel}|{path.stat().st_size}|{digest}".encode("utf-8"))
    return hashlib.sha256(b"\x00".join(parts)).hexdigest()


def build_provenance(
    result_path: Path,
    *,
    prediction_tree: str,
    manifest_path: Path,
    config_path: Path,
    scorer_checkout: Path,
    scoring_code_dir: Path,
    expected_pages: int,
    save_name: str,
    aggregation_mode: str,
    platform: str,
    generated_at: str | None,
) -> dict:
    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "prediction_tree_sha256": prediction_tree,
        "prediction_manifest_sha256": sha256_file(manifest_path),
        "scoring_config_sha256": sha256_file(config_path),
        "scorer_checkout_commit": git_commit(scorer_checkout),
        "scorer_code_sha256": tree_sha256(scoring_code_dir),
        "metric_result_sha256": sha256_file(result_path),
        "expected_pages": expected_pages,
        "save_name": save_name,
        "aggregation_mode": aggregation_mode,
        "platform": platform,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--result", type=Path, required=True, help="metric result JSON")
    common.add_argument("--out", type=Path, required=True, help="sidecar JSON path")
    common.add_argument("--prediction-tree", required=True, help="prediction tree sha256")
    common.add_argument("--manifest", type=Path, required=True)
    common.add_argument("--config", type=Path, required=True)
    common.add_argument("--scorer-checkout", type=Path, required=True, help="OmniDocBench checkout dir")
    common.add_argument("--scoring-code-dir", type=Path, required=True, help="03-scoring dir")
    common.add_argument("--expected-pages", type=int, required=True)
    common.add_argument("--save-name", required=True)
    common.add_argument("--aggregation-mode", default="teds_pooled_edit_dist_page_avg")
    common.add_argument("--platform", required=True, choices=("windows", "wsl"))

    write = sub.add_parser("write", parents=[common])
    write.set_defaults(handler=_handle_write)
    verify = sub.add_parser("verify", parents=[common])
    verify.set_defaults(handler=_handle_verify)
    return parser.parse_args(argv)


def _provenance_kwargs(args: argparse.Namespace, generated_at: str | None) -> dict:
    return dict(
        prediction_tree=args.prediction_tree,
        manifest_path=args.manifest,
        config_path=args.config,
        scorer_checkout=args.scorer_checkout,
        scoring_code_dir=args.scoring_code_dir,
        expected_pages=args.expected_pages,
        save_name=args.save_name,
        aggregation_mode=args.aggregation_mode,
        platform=args.platform,
        generated_at=generated_at,
    )


def _handle_write(args: argparse.Namespace) -> int:
    if not args.result.is_file():
        print(f"FAIL: metric result not found: {args.result}", file=sys.stderr)
        return 1
    provenance = build_provenance(args.result, **_provenance_kwargs(args, None))
    temp = args.out.with_name(args.out.name + ".tmp")
    temp.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.replace(args.out)
    print(f"Provenance written: {args.out}")
    return 0


def _handle_verify(args: argparse.Namespace) -> int:
    if not args.out.is_file():
        print(f"FAIL: provenance sidecar missing: {args.out} (scoring must re-run)", file=sys.stderr)
        return 1
    if not args.result.is_file():
        print(f"FAIL: metric result missing: {args.result}", file=sys.stderr)
        return 1
    try:
        previous = json.loads(args.out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"FAIL: provenance sidecar unreadable: {error}", file=sys.stderr)
        return 1
    current = build_provenance(args.result, **_provenance_kwargs(args, previous.get("generated_at")))
    differing = []
    for key, value in current.items():
        if key == "generated_at":
            continue
        if previous.get(key) != value:
            differing.append(f"{key} (sidecar={previous.get(key)} current={value})")
    if differing:
        print(
            "FAIL: provenance mismatch: " + "; ".join(differing)
            + " (scoring must re-run)",
            file=sys.stderr,
        )
        return 1
    print("Provenance OK: sidecar matches current prediction tree, manifest and config")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
