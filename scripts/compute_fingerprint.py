"""Phase-scoped reproduction fingerprints for safe -Resume gating.

A reproduction run is a pipeline of phases, each with its own inputs. A
fingerprint binds the artifacts of a phase to the inputs that produced them;
on resume, each phase's fingerprint is recomputed and compared before its
stages may be reused.

Phases
------
provisioning
    Profile file, upstream-lock.json, dataset manifest, scoring configs,
    uv.lock, repo commit and working-tree state. Computed only after the
    dataset + locks are provisioned and verified.
inference
    Provisioning fingerprint, adapter code tree, pipeline checkout commit,
    GGUF / mmproj / layout-model / llama-server hashes, backend variant,
    resolved server port, inference-relevant environment, manifest hash.
scoring
    Prediction tree hash (see hash_prediction_tree.py), manifest hash,
    OmniDocBench checkout commit, scoring configs, scoring code tree,
    save name.
evidence
    Strict prediction summary, Windows + WSL metric results, backend proof,
    final run state, verification-script hashes.

Input spec
----------
A JSON file describing the phase's inputs; each key maps to a value spec:

    {"file": "rel/path"}          sha256 of a file (null when missing)
    {"git":  "rel/path"}          current commit of a git checkout (null)
    {"tree": "rel/path"}          deterministic hash of a directory tree
    {"repo_tree": "."}            commit + `git diff --binary HEAD` + content
                                  hash of untracked (non-ignored) files
    {"env": ["NAME", ...]}        resolved values of existing env vars
    {"string": "value"}           literal value (variant, port, save name)

Working-tree state
------------------
The old ``repo_porcelain_sha256`` (hash of ``git status --porcelain`` output)
cannot detect *further* edits to an already-modified file. It is replaced by
``repo_tree_sha256``: sha256 over ``git diff --binary HEAD`` plus the content
hash of every untracked non-ignored file. Formal (full) profiles additionally
fail closed when the tree is dirty via ``--check-clean``.

Output
------
The resolved fingerprint JSON contains ``schema_version``, ``phase``,
``inputs`` (resolved values) and ``sha256`` (hash of the canonical inputs
JSON). ``--check`` deep-compares the ``inputs`` section only, so
``generated_at``-style noise never weakens the gate. ``--out`` writes
atomically (temp + replace) and only AFTER a successful ``--check`` when both
are given (a check against the same path must never compare the file to
itself).

CLI
---
--phase <name>      provisioning|inference|scoring|evidence
--inputs <path>     input spec JSON (see above)
--root <dir>        repo root; all spec paths are resolved relative to it
--out <path>        write the fingerprint (atomic)
--check <path>      compare against a previous fingerprint, exit 1 on mismatch
--check-clean       (provisioning phase) exit 1 when the repo tree is dirty
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PHASES = ("provisioning", "inference", "scoring", "evidence")
SPEC_KINDS = ("file", "git", "tree", "repo_tree", "env", "string")
TREE_IGNORE = {"__pycache__", ".git", "node_modules", ".venv", ".venv3", "models"}


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_run(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def git_commit(root: Path) -> str | None:
    out = git_run(root, "rev-parse", "HEAD")
    return out.decode("utf-8", "replace").strip() if out else None


def tree_sha256(root: Path) -> str | None:
    """Deterministic hash of a directory tree (sorted relative paths + bytes)."""
    if not root.is_dir():
        return None
    parts: list[bytes] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in TREE_IGNORE for part in Path(rel).parts):
            continue
        digest = sha256_file(path)
        if digest is None:
            continue
        parts.append(f"{rel}|{path.stat().st_size}|{digest}".encode("utf-8"))
    return hashlib.sha256(b"\x00".join(parts)).hexdigest()


def repo_tree_state(root: Path) -> dict:
    """Commit + tracked diff + untracked-content hash of a git working tree.

    ``dirty`` is True when either `git diff --binary HEAD` is non-empty or any
    untracked (non-ignored) file exists. ``state_sha256`` covers BOTH the
    binary diff and the full content of every untracked file, so further edits
    to an already-modified file change the state hash (the old porcelain-hash
    approach could not detect that).
    """
    commit = git_commit(root)
    diff = git_run(root, "diff", "--binary", "HEAD") or b""
    status = git_run(root, "status", "--porcelain", "--untracked-files=all") or b""
    lines = status.decode("utf-8", "replace").splitlines()
    untracked = sorted(line[3:] for line in lines if line.startswith("?? "))

    parts: list[bytes] = [b"tracked-diff", diff]
    for rel in untracked:
        path = root / rel
        if path.is_file():
            digest = sha256_file(path) or ""
            parts.append(f"untracked {rel}|{path.stat().st_size}|{digest}".encode("utf-8"))
    state = hashlib.sha256(b"\x00".join(parts)).hexdigest()
    return {
        "commit": commit,
        "dirty": bool(diff) or bool(untracked),
        "state_sha256": state,
    }


def resolve_spec(root: Path, spec: dict) -> object:
    kinds = [k for k in SPEC_KINDS if k in spec]
    if len(kinds) != 1:
        raise ValueError(f"input spec must have exactly one of {SPEC_KINDS}: {spec}")
    kind = kinds[0]
    value = spec[kind]
    if value is None or value == "":
        return None
    if kind == "file":
        return sha256_file(Path(value) if Path(value).is_absolute() else root / str(value))
    if kind == "git":
        return git_commit(root / str(value))
    if kind == "tree":
        return tree_sha256(root / str(value))
    if kind == "repo_tree":
        return repo_tree_state(root / str(value) if value != "." else root)
    if kind == "env":
        resolved = {}
        for name in value:
            if name in __import__("os").environ:
                resolved[name] = __import__("os").environ[name]
        return resolved
    if kind == "string":
        return str(value)
    raise ValueError(f"unsupported spec kind: {kind}")


def canonical_inputs_json(inputs: dict) -> str:
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_fingerprint(root: Path, phase: str, input_spec: dict) -> dict:
    resolved = {}
    for key, spec in input_spec.items():
        resolved[key] = resolve_spec(root, spec)
    canonical = canonical_inputs_json(resolved)
    return {
        "schema_version": 3,
        "phase": phase,
        "inputs": resolved,
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def compare_fingerprints(previous: dict, current: dict) -> list[str]:
    differing = []
    all_keys = sorted(set(previous.get("inputs", {})) | set(current.get("inputs", {})))
    prev_inputs = previous.get("inputs", {})
    curr_inputs = current.get("inputs", {})
    for key in all_keys:
        if prev_inputs.get(key) != curr_inputs.get(key):
            differing.append(key)
    return differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--check-clean", action="store_true")
    args = parser.parse_args()

    if not args.out and not args.check and not args.check_clean:
        parser.error("provide --out and/or --check and/or --check-clean")
    root: Path = args.root

    try:
        input_spec = json.loads(args.inputs.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"FAIL: cannot read input spec {args.inputs}: {error}", file=sys.stderr)
        return 1
    if not isinstance(input_spec, dict) or not input_spec:
        print("FAIL: input spec must be a non-empty JSON object", file=sys.stderr)
        return 1

    if args.check_clean:
        if args.phase != "provisioning":
            print("FAIL: --check-clean is only meaningful for the provisioning phase", file=sys.stderr)
            return 1
        state = repo_tree_state(root)
        if state["dirty"]:
            print(
                "FAIL: repo working tree is dirty (formal profile requires a clean "
                "tree; commit or stash changes before running): "
                f"commit={state['commit']}",
                file=sys.stderr,
            )
            return 1
        print("Clean-tree gate OK: no tracked modifications and no untracked files")
        return 0

    try:
        current = build_fingerprint(root, args.phase, input_spec)
    except (ValueError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    if args.check:
        if not args.check.is_file():
            print(f"FAIL: previous fingerprint not found: {args.check}", file=sys.stderr)
            return 1
        try:
            previous = json.loads(args.check.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            print(f"FAIL: previous fingerprint is unreadable: {error}", file=sys.stderr)
            return 1
        if previous.get("phase") != args.phase:
            print(
                f"FAIL: previous fingerprint phase '{previous.get('phase')}' does not "
                f"match requested phase '{args.phase}'",
                file=sys.stderr,
            )
            return 1
        differing = compare_fingerprints(previous, current)
        if differing:
            print(
                f"FAIL: fingerprint mismatch on: {', '.join(differing)}. "
                "Start a fresh run or use -ForceInference.",
                file=sys.stderr,
            )
            return 1
        print(f"Fingerprint check OK ({args.phase}): inputs unchanged")

    if args.out:
        temp = args.out.with_name(args.out.name + ".tmp")
        temp.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp.replace(args.out)
        print(f"Fingerprint written ({args.phase}): {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
