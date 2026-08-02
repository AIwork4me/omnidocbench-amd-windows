"""HIP/CPU backend proof: assert-backend-proof.ps1 against fixture logs/envs."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSERT = (
    REPO_ROOT
    / "adapters"
    / "paddleocr-vl-1.6"
    / "01-vlm-server"
    / "assert-backend-proof.ps1"
)
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "backend-proof"
LOCK = REPO_ROOT / "upstream-lock.json"


@pytest.fixture()
def adapter_dir(tmp_path):
    """A fake adapter tree: .env.local + models/llama.cpp exe/dlls + logs."""
    adapter = tmp_path / "adapter"
    llama = adapter / "models" / "llama.cpp"
    logs = adapter / "logs"
    llama.mkdir(parents=True)
    logs.mkdir()
    (llama / "llama-server.exe").write_bytes(b"fake exe")
    return adapter


def _env_file(adapter: Path, *, variant: str, gpu_layers: str = "0", tag: str = "b9637", model: str = "PaddleOCR-VL-1.6-GGUF.gguf"):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    locked_tag = lock["git"]["llama_cpp"]["tag"]
    values = {
        "LLAMA_VARIANT": variant,
        "LLAMA_SERVER_EXE": str(adapter / "models" / "llama.cpp" / "llama-server.exe"),
        "LLAMA_TAG": locked_tag if tag == "locked" else tag,
        "LLAMA_PORT": "8122",
        "LLAMA_GPU_LAYERS": gpu_layers,
        "VL_REC_API_MODEL_NAME": model,
    }
    lines = [f"{key}='{value}'" for key, value in values.items()]
    (adapter / ".env.local").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _install_variant(adapter: Path, variant: str, with_hip_dlls: bool):
    llama = adapter / "models" / "llama.cpp"
    (llama / ".variant").write_text(variant + "\n", encoding="utf-8")
    if with_hip_dlls:
        (llama / "ggml-hip.dll").write_bytes(b"hip")
        (llama / "libhipblas.dll").write_bytes(b"blas")
    else:
        for name in ("ggml-hip.dll", "libhipblas.dll"):
            path = llama / name
            if path.exists():
                path.unlink()


def _run_proof(adapter: Path, log_file: Path, expected_variant: str) -> subprocess.CompletedProcess:
    out = adapter / "backend-proof.json"
    return subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ASSERT),
            "-EnvFile", str(adapter / ".env.local"),
            "-LogFile", str(log_file),
            "-PidFile", str(adapter / "pid"),
            "-ExpectedVariant", expected_variant,
            "-LockFile", str(LOCK),
            "-OutFile", str(out),
            "-SkipHttp",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_hip_log_and_env_pass(adapter_dir):
    _env_file(adapter_dir, variant="hip", gpu_layers="99", tag="locked")
    _install_variant(adapter_dir, "hip", with_hip_dlls=True)
    result = _run_proof(adapter_dir, FIXTURES / "hip.log", "hip")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BACKEND PROOF OK" in result.stdout
    proof = json.loads((adapter_dir / "backend-proof.json").read_text(encoding="utf-8"))
    assert proof["requested_variant"] == "hip"
    assert proof["server"]["sha256"]
    assert proof["log_evidence"]["markers_found"]


def test_cpu_log_and_env_pass(adapter_dir):
    _env_file(adapter_dir, variant="cpu", gpu_layers="0", tag="locked")
    _install_variant(adapter_dir, "cpu", with_hip_dlls=False)
    result = _run_proof(adapter_dir, FIXTURES / "cpu.log", "cpu")
    assert result.returncode == 0, result.stdout + result.stderr


def test_cpu_log_fails_hip_profile(adapter_dir):
    _env_file(adapter_dir, variant="hip", gpu_layers="99", tag="locked")
    _install_variant(adapter_dir, "hip", with_hip_dlls=True)
    result = _run_proof(adapter_dir, FIXTURES / "cpu.log", "hip")
    assert result.returncode != 0
    assert "no HIP/ROCm runtime marker" in result.stdout


def test_truncated_log_fails_hip_profile(adapter_dir):
    _env_file(adapter_dir, variant="hip", gpu_layers="99", tag="locked")
    _install_variant(adapter_dir, "hip", with_hip_dlls=True)
    result = _run_proof(adapter_dir, FIXTURES / "truncated.log", "hip")
    assert result.returncode != 0
    assert "no HIP/ROCm runtime marker" in result.stdout


def test_variant_mismatch_fails(adapter_dir):
    _env_file(adapter_dir, variant="cpu", gpu_layers="0", tag="locked")
    _install_variant(adapter_dir, "cpu", with_hip_dlls=False)
    result = _run_proof(adapter_dir, FIXTURES / "hip.log", "hip")
    assert result.returncode != 0
    assert "LLAMA_VARIANT=cpu does not match requested hip" in result.stdout


def test_missing_offload_fails_hip(adapter_dir):
    _env_file(adapter_dir, variant="hip", gpu_layers="0", tag="locked")
    _install_variant(adapter_dir, "hip", with_hip_dlls=True)
    result = _run_proof(adapter_dir, FIXTURES / "hip.log", "hip")
    assert result.returncode != 0
    assert "LLAMA_GPU_LAYERS=0 proves no GPU offload" in result.stdout


def test_hip_dlls_on_cpu_profile_fail(adapter_dir):
    _env_file(adapter_dir, variant="cpu", gpu_layers="0", tag="locked")
    _install_variant(adapter_dir, "cpu", with_hip_dlls=True)
    result = _run_proof(adapter_dir, FIXTURES / "cpu.log", "cpu")
    assert result.returncode != 0
    assert "CPU build must NOT contain ggml-hip.dll" in result.stdout


def test_wrong_tag_fails(adapter_dir):
    _env_file(adapter_dir, variant="hip", gpu_layers="99", tag="b9999")
    _install_variant(adapter_dir, "hip", with_hip_dlls=True)
    result = _run_proof(adapter_dir, FIXTURES / "hip.log", "hip")
    assert result.returncode != 0
    assert "does not match locked" in result.stdout


def test_utf16_log_is_parsed(adapter_dir, tmp_path):
    utf16_log = tmp_path / "hip-utf16.log"
    text = (FIXTURES / "hip.log").read_text(encoding="utf-8")
    utf16_log.write_text(text, encoding="utf-16")
    _env_file(adapter_dir, variant="hip", gpu_layers="99", tag="locked")
    _install_variant(adapter_dir, "hip", with_hip_dlls=True)
    result = _run_proof(adapter_dir, utf16_log, "hip")
    assert result.returncode == 0, result.stdout + result.stderr
