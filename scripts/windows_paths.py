"""Windows path helpers for repositories containing long dataset filenames."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def short_repo_root(repo_root: Path) -> Path:
    """Return the deterministic local junction for *repo_root* when available."""
    repo_root = Path(os.path.abspath(repo_root))
    if os.name != "nt":
        return repo_root
    digest = hashlib.sha256(str(repo_root).casefold().encode("utf-8")).hexdigest()[:12]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return repo_root
    alias = Path(local_app_data) / "OmniDocBenchAMD" / digest / "repo"
    return alias if alias.is_dir() else repo_root


def through_short_repo(path: Path, repo_root: Path) -> Path:
    """Map a path inside *repo_root* through its short Windows junction."""
    absolute_path = Path(os.path.abspath(path))
    absolute_root = Path(os.path.abspath(repo_root))
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError:
        return absolute_path
    return short_repo_root(absolute_root) / relative