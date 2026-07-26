"""Verify installed distributions exactly match active pins in a requirements lock."""
from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def locked_requirements(path: Path) -> list[Requirement]:
    logical_lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw[:1].isspace():
            continue
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        requirement_text = re.split(r"\s+--hash=", line.rstrip("\\").strip(), maxsplit=1)[0].strip()
        if requirement_text:
            logical_lines.append(requirement_text)
    return [Requirement(line) for line in logical_lines]


def verify(path: Path) -> list[str]:
    installed = {
        canonicalize_name(dist.metadata["Name"]): dist.version
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    failures: list[str] = []
    for requirement in locked_requirements(path):
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name)
        version = installed.get(name)
        if version is None:
            failures.append(f"missing: {requirement.name}")
        elif version not in requirement.specifier:
            failures.append(
                f"version mismatch: {requirement.name} expected {requirement.specifier}, actual {version}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements", type=Path)
    args = parser.parse_args()
    failures = verify(args.requirements)
    if failures:
        raise SystemExit("Requirements lock mismatch:\n" + "\n".join(failures))
    print(f"REQUIREMENTS LOCK OK: {args.requirements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())