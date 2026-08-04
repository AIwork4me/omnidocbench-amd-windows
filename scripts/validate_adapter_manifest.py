"""Validate an adapter manifest (adapters/<adapter>/adapter.json).

The adapter manifest is the safety contract between the orchestrator and a
model adapter. Every script path declared by the manifest must be:

  * relative to the repository root (no absolute paths, no drive letters)
  * inside the adapter's own directory (no ".." components)
  * an existing file (fails closed when missing)

The schema also pins the output contract (markdown-per-page, UTF-8,
_run_stats.json), resume support, backend-proof capability and any
human-intervention gates the adapter needs.

CLI
---
--adapter <name>   adapter directory name (e.g. paddleocr-vl-1.6)
--root <dir>       repository root (default: parent of this script)
--strict           also require every declared script to exist on disk
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = 1

LIFECYCLE_KEYS = (
    "server_setup",
    "server_verify",
    "layout_setup",
    "layout_verify",
    "install_deps",
    "inference_entrypoint",
    "verify_script",
    "backend_proof_capable",
    "resume_support",
)

REQUIRED_ENV_HINTS = (
    "no committed machine paths: .env.local and logs/ must never be tracked"
)

MATURITIES = ("reference", "validated", "experimental")

PATH_KINDS = (
    "server_setup",
    "server_verify",
    "layout_setup",
    "layout_verify",
    "install_deps",
    "inference_entrypoint",
    "verify_script",
)


def validate_manifest(root: Path, adapter: str, strict: bool = False) -> tuple[list[str], dict]:
    errors: list[str] = []
    manifest_path = root / "adapters" / adapter / "adapter.json"
    adapter_dir = (root / "adapters" / adapter).resolve()
    if not manifest_path.is_file():
        return [f"adapter manifest not found: {manifest_path}"], {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return [f"adapter manifest is not valid JSON: {error}"], {}

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    check(data.get("contract_version") == SCHEMA_VERSION, "contract_version must be 1")
    check(isinstance(data.get("name"), str) and data["name"] == adapter,
          f"manifest name '{data.get('name')}' must equal the adapter directory name '{adapter}'")
    check(data.get("maturity") in MATURITIES, f"maturity must be one of {MATURITIES}")
    platforms = data.get("supported_platforms")
    check(isinstance(platforms, list) and platforms, "supported_platforms must be a non-empty list")
    if platforms:
        for p in platforms:
            check(p in ("windows", "linux", "macos"), f"unsupported platform '{p}'")
    check(isinstance(data.get("python_runtime_policy"), str) and data["python_runtime_policy"],
          "python_runtime_policy must be a non-empty string")

    lifecycle = data.get("lifecycle")
    check(isinstance(lifecycle, dict), "lifecycle must be an object")
    if isinstance(lifecycle, dict):
        check(isinstance(lifecycle.get("backend_proof_capable"), bool),
              "lifecycle.backend_proof_capable must be a boolean")
        check(isinstance(lifecycle.get("resume_support"), bool),
              "lifecycle.resume_support must be a boolean")
        entry = lifecycle.get("inference_entrypoint")
        check(isinstance(entry, str) and entry, "lifecycle.inference_entrypoint must be a non-empty string")
        for key in PATH_KINDS:
            value = lifecycle.get(key)
            if value is None:
                continue
            if not isinstance(value, str) or not value:
                errors.append(f"lifecycle.{key} must be a non-empty string when present")
                continue
            rel = value.replace("/", "\\")
            if re.match(r"^[A-Za-z]:[\\/]", rel) or rel.startswith("\\") or rel.startswith("/"):
                errors.append(f"lifecycle.{key} must be repo-relative (no absolute paths): {value}")
                continue
            if ".." in Path(value).parts:
                errors.append(f"lifecycle.{key} must not contain '..' path components: {value}")
                continue
            resolved = (root / value).resolve()
            try:
                resolved.relative_to(adapter_dir)
            except ValueError:
                errors.append(f"lifecycle.{key} must live inside adapters/{adapter}/: {value}")
            if strict and not (root / value).is_file():
                errors.append(f"lifecycle.{key} does not exist: {value}")

    output = data.get("output_contract")
    check(isinstance(output, dict), "output_contract must be an object")
    if isinstance(output, dict):
        check(output.get("markdown_per_page") is True,
              "output_contract.markdown_per_page must be true (one <stem>.md per page)")
        check(output.get("utf8") is True, "output_contract.utf8 must be true")
        check(isinstance(output.get("stats_file"), str) and output["stats_file"],
              "output_contract.stats_file must be a non-empty string")

    env_vars = data.get("required_env_vars")
    check(isinstance(env_vars, list), "required_env_vars must be a list")
    if isinstance(env_vars, list):
        for var in env_vars:
            check(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(var)),
                  f"required_env_vars entry is not a valid env var name: {var}")

    gates = data.get("human_intervention_gates")
    if gates is not None:
        check(isinstance(gates, list) and all(isinstance(g, str) for g in gates),
              "human_intervention_gates must be a list of strings")

    return errors, data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    errors, _ = validate_manifest(args.root, args.adapter, strict=args.strict)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"ADAPTER MANIFEST INVALID ({len(errors)} issue(s)): {args.adapter}", file=sys.stderr)
        return 1
    print(f"ADAPTER MANIFEST OK: {args.adapter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
