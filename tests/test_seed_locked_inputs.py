from __future__ import annotations

import json
import mmap
import os
from pathlib import Path
import subprocess
import sys

import pytest


pytestmark = pytest.mark.win32

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed-locked-inputs.ps1"
PAGE_COUNT = 1651
MODEL_RELATIVE_PATHS = (
    "adapters/paddleocr-vl-1.6/models/PaddleOCR-VL-1.6-GGUF/PaddleOCR-VL-1.6-GGUF.gguf",
    "adapters/paddleocr-vl-1.6/models/PaddleOCR-VL-1.6-GGUF/PaddleOCR-VL-1.6-GGUF-mmproj.gguf",
    "adapters/paddleocr-vl-1.6/models/PP-DocLayoutV3-onnx/inference.onnx",
    "adapters/paddleocr-vl-1.6/models/PP-DocLayoutV3-onnx/inference.yml",
)


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


def _prepare_full_seed_roots(
    tmp_path: Path,
    *,
    source_image_payload: bytes,
    destination_image_payload: bytes | None,
) -> tuple[Path, Path, Path, str]:
    source_root = tmp_path / "source-root"
    destination_root = tmp_path / "destination-root"
    relative_image = "nested/page.png"
    source_data = source_root / "eval-infra" / "01-omnidocbench" / "data"
    destination_data = destination_root / "eval-infra" / "01-omnidocbench" / "data"
    source_image = source_data / "images" / relative_image
    destination_image = destination_data / "images" / relative_image
    source_image.parent.mkdir(parents=True)
    source_image.write_bytes(source_image_payload)
    if destination_image_payload is not None:
        destination_image.parent.mkdir(parents=True)
        destination_image.write_bytes(destination_image_payload)
    manifest = [{"page_info": {"image_path": relative_image}} for _ in range(PAGE_COUNT)]
    (source_data / "OmniDocBench.json").write_text(json.dumps(manifest), encoding="utf-8")
    for index, relative_path in enumerate(MODEL_RELATIVE_PATHS):
        model_file = source_root / relative_path
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_bytes(f"locked-model-{index}".encode())

    destination_scripts = destination_root / "scripts"
    destination_scripts.mkdir(parents=True)
    (destination_scripts / "verify-upstream-lock.ps1").write_text(
        """param([string] $Component, [string] $Path, [string] $LockFile)
Add-Content -LiteralPath $env:SEED_VERIFY_LOG -Value "lock:${Component}:$Path"
exit 0
""",
        encoding="utf-8",
    )
    (destination_scripts / "verify_dataset_tree.py").write_text(
        """import os
import sys
with open(os.environ["SEED_VERIFY_LOG"], "a", encoding="utf-8") as stream:
    stream.write("tree:" + " ".join(sys.argv[1:]) + "\\n")
raise SystemExit(0)
""",
        encoding="utf-8",
    )
    (destination_root / "upstream-lock.json").write_text("{}\n", encoding="utf-8")
    destination_venv = destination_root / ".venv"
    (destination_venv / "Scripts").mkdir(parents=True)
    os.link(Path(sys.executable), destination_venv / "Scripts" / "python.exe")
    (destination_venv / "pyvenv.cfg").write_text(
        (REPO_ROOT / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return source_root, destination_root, destination_image, relative_image


def _full_seed_environment(tmp_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local-app-data")
    environment["SEED_VERIFY_LOG"] = str(tmp_path / "verify.log")
    return environment


def _run_full_seed_capturing_exception(
    tmp_path: Path, source_root: Path, destination_root: Path
) -> tuple[subprocess.CompletedProcess[str], dict]:
    runner = tmp_path / "full-seed-exception-runner.ps1"
    runner.write_text(
        r'''
param([string] $SeedScript, [string] $SourceRoot, [string] $DestinationRoot)
$ErrorActionPreference = "Stop"
try {
    & $SeedScript -SourceRoot $SourceRoot -DestinationRoot $DestinationRoot
    [pscustomobject]@{ succeeded = $true; chain = @() } | ConvertTo-Json -Compress
} catch {
    $chain = @()
    $current = $_.Exception
    while ($null -ne $current) {
        $chain += [pscustomobject]@{
            type = $current.GetType().FullName
            message = $current.Message
            stack_trace = $current.StackTrace
        }
        $current = $current.InnerException
    }
    [pscustomobject]@{ succeeded = $false; chain = $chain } |
        ConvertTo-Json -Depth 10 -Compress
}
''',
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(runner),
            "-SeedScript",
            str(SEED_SCRIPT),
            "-SourceRoot",
            str(source_root),
            "-DestinationRoot",
            str(destination_root),
        ],
        cwd=REPO_ROOT,
        env=_full_seed_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    output_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert output_lines, result.stdout + result.stderr
    return result, json.loads(output_lines[-1])


def _run_full_seed(
    tmp_path: Path, source_root: Path, destination_root: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SEED_SCRIPT),
            "-SourceRoot",
            str(source_root),
            "-DestinationRoot",
            str(destination_root),
        ],
        cwd=REPO_ROOT,
        env=_full_seed_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
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


def test_dataset_image_wrapper_preserves_exception_chain_and_adds_relative_context(tmp_path: Path):
    source_payload = b"locked source payload"
    destination_payload = b"mapped destination!!!"
    source_root, destination_root, destination_image, relative_image = _prepare_full_seed_roots(
        tmp_path,
        source_image_payload=source_payload,
        destination_image_payload=destination_payload,
    )

    with destination_image.open("r+b") as mapped_file:
        with mmap.mmap(mapped_file.fileno(), 0, access=mmap.ACCESS_WRITE):
            result, captured = _run_full_seed_capturing_exception(
                tmp_path, source_root, destination_root
            )

    assert result.returncode == 0, result.stdout + result.stderr
    assert captured["succeeded"] is False
    chain = captured["chain"]
    assert chain[0]["type"] == "System.IO.IOException"
    assert relative_image in chain[0]["message"]
    assert chain[1]["type"] == "System.IO.IOException"
    assert "stop the VLM server/process" in chain[1]["message"]
    assert any("user-mapped section open" in item["message"].lower() for item in chain)
    assert any(item["stack_trace"] for item in chain[1:])
    assert destination_image.read_bytes() == destination_payload


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


def test_difference_after_four_mib_boundary_in_final_partial_block_is_replaced(tmp_path: Path):
    prefix = b"a" * (4 * 1024 * 1024)
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(prefix + b"source-tail")
    destination.write_bytes(prefix + b"stale!-tail")
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


def test_full_script_second_seed_skips_mapped_model_and_runs_all_verifiers(tmp_path: Path):
    source_root, destination_root, destination_image, _ = _prepare_full_seed_roots(
        tmp_path,
        source_image_payload=b"single physical image",
        destination_image_payload=None,
    )

    first = _run_full_seed(tmp_path, source_root, destination_root)
    assert first.returncode == 0, first.stdout + first.stderr
    mapped_model = destination_root / MODEL_RELATIVE_PATHS[0]
    before_mtime_ns = mapped_model.stat().st_mtime_ns

    with mapped_model.open("r+b") as mapped_file:
        with mmap.mmap(mapped_file.fileno(), 0, access=mmap.ACCESS_WRITE):
            second = _run_full_seed(tmp_path, source_root, destination_root)

    assert second.returncode == 0, second.stdout + second.stderr
    assert "LOCKED INPUT SEED OK" in first.stdout
    assert "LOCKED INPUT SEED OK" in second.stdout
    assert destination_image.read_bytes() == b"single physical image"
    assert mapped_model.read_bytes() == (source_root / MODEL_RELATIVE_PATHS[0]).read_bytes()
    assert mapped_model.stat().st_mtime_ns == before_mtime_ns

    verification_lines = (tmp_path / "verify.log").read_text(encoding="utf-8").splitlines()
    assert len(verification_lines) == 16
    for run_start in (0, 8):
        source_checks = verification_lines[run_start : run_start + 4]
        destination_checks = verification_lines[run_start + 4 : run_start + 8]
        assert all(str(source_root).lower() in line.lower() for line in source_checks)
        assert [line.split(":", 1)[0] for line in destination_checks] == [
            "lock",
            "tree",
            "lock",
            "lock",
        ]
        assert destination_checks[0].startswith("lock:DatasetManifest:")
        assert destination_checks[2].startswith("lock:Vlm:")
        assert destination_checks[3].startswith("lock:Layout:")
        assert all(str(source_root).lower() not in line.lower() for line in destination_checks)
        assert all(
            str(destination_root).lower() in line.lower() for line in destination_checks[1:]
        )
