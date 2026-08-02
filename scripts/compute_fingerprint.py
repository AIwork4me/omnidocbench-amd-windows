"""Compute/compare the reproduction fingerprint for safe -Resume gating.

The fingerprint binds a run's inference+scoring artifacts to the inputs that
produced them. Recompute it before resuming; any difference means the previous
state was produced by different inputs and must not be reused silently.

Keys
----
profile_sha256, upstream_lock_sha256, dataset_manifest_sha256,
windows_scoring_config_sha256, wsl_cdm_config_sha256, pipeline_checkout_commit,
repo_commit, repo_dirty (git status --porcelain non-empty)

Heavy artifact bytes (GGUF, mmproj, layout ONNX) are pinned transitively by
upstream_lock_sha256: verify-upstream-lock.ps1 re-verifies those files against
the lock before every inference, so re-hashing gigabytes per resume is neither
necessary nor cheaper than the lock check.

CLI
---
--out <path>        write fingerprint.json
--check <path>      compare against a previously written fingerprint; exit 1
                    and list every differing key
--root <path>       repository root (default: parent of this script)
--profile <path>    profile JSON (default: profiles/cpu-smoke-10.profile.json)
--manifest <path>   dataset manifest (default: profile's prediction_manifest)
--pipeline <path>   pipeline checkout dir (default: outputs/checkouts/PaddleOCR-VL-ROCm)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def git_dirty(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def build_fingerprint(
    root: Path,
    profile_path: Path,
    manifest_path: Path,
    configs: list[Path],
    pipeline_dir: Path,
) -> dict:
    fingerprint = {
        "profile_sha256": sha256_file(profile_path),
        "upstream_lock_sha256": sha256_file(root / "upstream-lock.json"),
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "windows_scoring_config_sha256": sha256_file(configs[0]) if configs else None,
        "wsl_cdm_config_sha256": sha256_file(configs[1]) if len(configs) > 1 else None,
        "pipeline_checkout_commit": None,
        "repo_commit": git_commit(root),
        "repo_dirty": git_dirty(root),
    }
    if (pipeline_dir / ".git").is_dir():
        fingerprint["pipeline_checkout_commit"] = git_commit(pipeline_dir)
    return fingerprint


def compare_fingerprints(previous: dict, current: dict) -> list[str]:
    differing = []
    all_keys = sorted(set(previous) | set(current))
    for key in all_keys:
        if previous.get(key) != current.get(key):
            differing.append(key)
    return differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--pipeline", type=Path)
    parser.add_argument("--windows-config", type=Path)
    parser.add_argument("--wsl-config", type=Path)
    args = parser.parse_args()
    if not args.out and not args.check:
        parser.error("provide --out and/or --check")
    root: Path = args.root
    profile_path = args.profile or root / "scripts" / "profiles" / "cpu-smoke-10.profile.json"
    manifest_path = args.manifest or root / "eval-infra" / "01-omnidocbench" / "data" / "OmniDocBench_cpu_smoke_10.json"
    pipeline_dir = args.pipeline or root / "outputs" / "checkouts" / "PaddleOCR-VL-ROCm"
    configs = [
        args.windows_config
        or root / "eval-infra" / "01-omnidocbench" / "configs" / "v16-cpu-smoke-10.yaml",
        args.wsl_config
        or root / "eval-infra" / "01-omnidocbench" / "configs" / "v16-cdm-cpu-smoke-10.yaml",
    ]
    current = build_fingerprint(root, profile_path, manifest_path, configs, pipeline_dir)
    if args.out:
        args.out.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Fingerprint written: {args.out}")
    if args.check:
        if not args.check.is_file():
            print(f"FAIL: previous fingerprint not found: {args.check}", file=__import__("sys").stderr)
            return 1
        previous = json.loads(args.check.read_text(encoding="utf-8"))
        differing = compare_fingerprints(previous, current)
        if differing:
            print(
                f"FAIL: fingerprint mismatch on: {', '.join(differing)}. "
                "Start a fresh run or use -ForceInference.",
                file=__import__("sys").stderr,
            )
            return 1
        print("Fingerprint check OK: inputs unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
