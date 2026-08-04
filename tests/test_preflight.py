from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.win32



REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "preflight.ps1"


def run_preflight(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PREFLIGHT),
            "-CdmPath",
            "None",
            "-Variant",
            "cpu",
            "-SkipNetwork",
            "-MinimumFreeGB",
            "0",
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_version_command(path: Path, version: str) -> Path:
    path.write_text(f"@echo off\necho {version}\n", encoding="ascii")
    return path


def test_preflight_accepts_supported_python(tmp_path: Path):
    python = make_version_command(tmp_path / "python311.cmd", "Python 3.11.9")

    result = run_preflight("-Python", str(python))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Python 3.11.9" in result.stdout
    assert "PRECHECK OK" in result.stdout


def test_preflight_rejects_unsupported_python(tmp_path: Path):
    python = make_version_command(tmp_path / "python313.cmd", "Python 3.13.1")

    result = run_preflight("-Python", str(python))

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "requires Python 3.10 or 3.11" in output
    assert "uv sync --locked --all-groups" in output


def test_preflight_rejects_explicit_missing_git(tmp_path: Path):
    missing_git = tmp_path / "missing-git.exe"

    result = run_preflight("-GitExecutable", str(missing_git))

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Git not found" in output
    assert "Install Git for Windows" in output