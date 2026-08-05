from __future__ import annotations

import mmap
import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.win32

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed-locked-inputs.ps1"


def _extract_powershell_function(source: str, name: str) -> str:
    start = source.index(f"function {name}")
    opening_brace = source.index("{", start)
    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated PowerShell function: {name}")


def _run_copy_locked_file(tmp_path: Path, source: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    script_source = SEED_SCRIPT.read_text(encoding="utf-8")
    runner = tmp_path / "copy-locked-file-runner.ps1"
    runner.write_text(
        "\n\n".join(
            (
                'param([string] $Source, [string] $Destination)\n$ErrorActionPreference = "Stop"',
                _extract_powershell_function(script_source, "ConvertTo-ExtendedPath"),
                _extract_powershell_function(script_source, "Read-FileBlock"),
                _extract_powershell_function(script_source, "Test-FileContentEqual"),
                _extract_powershell_function(script_source, "Copy-LockedFile"),
                "Copy-LockedFile $Source $Destination\nWrite-Output 'COPY OK'",
            )
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(runner),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_mapped_identical_destination_is_skipped_without_modification(tmp_path: Path):
    payload = (b"locked-input\x00" * 8192) + b"end"
    source = tmp_path / "source.gguf"
    destination = tmp_path / "destination.gguf"
    source.write_bytes(payload)
    destination.write_bytes(payload)
    before_mtime_ns = destination.stat().st_mtime_ns

    with destination.open("r+b") as mapped_file:
        with mmap.mmap(mapped_file.fileno(), 0, access=mmap.ACCESS_WRITE) as mapped_destination:
            result = _run_copy_locked_file(tmp_path, source, destination)
            assert mapped_destination[:16] == payload[:16]

    assert result.returncode == 0, result.stdout + result.stderr
    assert "COPY OK" in result.stdout
    assert destination.read_bytes() == payload
    assert destination.stat().st_mtime_ns == before_mtime_ns


def test_mapped_different_destination_fails_closed_with_actionable_diagnostic(tmp_path: Path):
    source_payload = b"locked source payload"
    destination_payload = b"mapped destination!!!"
    assert len(source_payload) == len(destination_payload)
    source = tmp_path / "source.gguf"
    destination = tmp_path / "destination.gguf"
    source.write_bytes(source_payload)
    destination.write_bytes(destination_payload)

    with destination.open("r+b") as mapped_file:
        with mmap.mmap(mapped_file.fileno(), 0, access=mmap.ACCESS_WRITE):
            result = _run_copy_locked_file(tmp_path, source, destination)

    diagnostic = result.stdout + result.stderr
    assert result.returncode != 0, diagnostic
    assert destination.read_bytes() == destination_payload
    assert destination.name.lower() in diagnostic.lower()
    assert "user-mapped section open" in diagnostic.lower()
    assert "stop the vlm server/process" in diagnostic.lower()
    assert "then rerun" in diagnostic.lower()


def test_missing_destination_is_seeded(tmp_path: Path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "missing" / "destination.bin"
    source.write_bytes(b"new locked bytes")

    result = _run_copy_locked_file(tmp_path, source, destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert destination.read_bytes() == source.read_bytes()


def test_different_unlocked_destination_is_replaced(tmp_path: Path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"locked source payload")
    destination.write_bytes(b"stale! destination!!!")
    assert source.stat().st_size == destination.stat().st_size

    result = _run_copy_locked_file(tmp_path, source, destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert destination.read_bytes() == source.read_bytes()


def test_same_physical_file_through_hardlink_alias_is_skipped_safely(tmp_path: Path):
    source = tmp_path / "source.bin"
    destination_alias = tmp_path / "destination-alias.bin"
    payload = b"same physical file"
    source.write_bytes(payload)
    os.link(source, destination_alias)
    before_mtime_ns = destination_alias.stat().st_mtime_ns

    result = _run_copy_locked_file(tmp_path, source, destination_alias)

    assert result.returncode == 0, result.stdout + result.stderr
    assert source.read_bytes() == payload
    assert destination_alias.read_bytes() == payload
    assert destination_alias.stat().st_mtime_ns == before_mtime_ns


def test_partial_rerun_skips_mapped_identical_file_then_seeds_missing_file(tmp_path: Path):
    existing_source = tmp_path / "existing-source.bin"
    existing_destination = tmp_path / "existing-destination.bin"
    missing_source = tmp_path / "missing-source.bin"
    missing_destination = tmp_path / "partial" / "missing-destination.bin"
    existing_payload = b"already seeded locked bytes"
    missing_payload = b"remaining locked bytes"
    existing_source.write_bytes(existing_payload)
    existing_destination.write_bytes(existing_payload)
    missing_source.write_bytes(missing_payload)
    before_mtime_ns = existing_destination.stat().st_mtime_ns

    with existing_destination.open("r+b") as mapped_file:
        with mmap.mmap(mapped_file.fileno(), 0, access=mmap.ACCESS_WRITE):
            existing_result = _run_copy_locked_file(
                tmp_path, existing_source, existing_destination
            )
            missing_result = _run_copy_locked_file(
                tmp_path, missing_source, missing_destination
            )

    assert existing_result.returncode == 0, existing_result.stdout + existing_result.stderr
    assert missing_result.returncode == 0, missing_result.stdout + missing_result.stderr
    assert existing_destination.read_bytes() == existing_payload
    assert existing_destination.stat().st_mtime_ns == before_mtime_ns
    assert missing_destination.read_bytes() == missing_payload
