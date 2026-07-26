from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK = REPO_ROOT / "upstream-lock.json"
VERIFY = REPO_ROOT / "scripts" / "verify-upstream-lock.ps1"
TREE_VERIFY = REPO_ROOT / "scripts" / "verify_dataset_tree.py"
REQUIREMENTS_VERIFY = REPO_ROOT / "scripts" / "verify_requirements_lock.py"


def run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(VERIFY), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_lock_has_immutable_git_and_huggingface_revisions():
    lock = json.loads(LOCK.read_text(encoding="utf-8"))

    assert lock["schema_version"] == 1
    for entry in lock["git"].values():
        assert len(entry["commit"]) == 40
    for name in ("vlm", "layout", "dataset"):
        assert len(lock["huggingface"][name]["revision"]) == 40

    verifier = VERIFY.read_text(encoding="utf-8")
    assert "[System.Security.Cryptography.SHA256]::Create()" in verifier
    assert "[System.IO.File]::OpenRead" in verifier
    assert "Get-FileHash" not in verifier


def test_file_verifier_accepts_exact_bytes_and_rejects_corruption(tmp_path: Path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"locked bytes")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    import hashlib

    lock["huggingface"]["dataset"]["manifest"] = {
        "file": artifact.name,
        "bytes": artifact.stat().st_size,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "pages": 1,
    }
    test_lock = tmp_path / "lock.json"
    test_lock.write_text(json.dumps(lock), encoding="utf-8")

    ok = run_verify("-Component", "DatasetManifest", "-Path", str(artifact), "-LockFile", str(test_lock))
    assert ok.returncode == 0, ok.stdout + ok.stderr

    artifact.write_bytes(b"corrupt")
    bad = run_verify("-Component", "DatasetManifest", "-Path", str(artifact), "-LockFile", str(test_lock))
    assert bad.returncode != 0
    assert "size mismatch" in bad.stdout + bad.stderr or "SHA-256 mismatch" in bad.stdout + bad.stderr


def test_git_verifier_rejects_wrong_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "file.txt").write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    lock["git"]["omnidocbench"]["commit"] = "0" * 40
    test_lock = tmp_path / "lock.json"
    test_lock.write_text(json.dumps(lock), encoding="utf-8")

    result = run_verify("-Component", "OmniDocBench", "-Path", str(repo), "-LockFile", str(test_lock))
    assert result.returncode != 0
    output = result.stdout + result.stderr
    normalized = " ".join(output.split())
    assert "commit mismatch" in normalized
    assert "expected " + "0" * 40 in normalized


def test_dataset_tree_verifier_accepts_exact_tree_and_rejects_change(tmp_path: Path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "a.png").write_bytes(b"a")
    (images / "b.png").write_bytes(b"bb")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {"page_info": {"image_path": "a.png"}},
                {"page_info": {"image_path": "b.png"}},
            ]
        ),
        encoding="utf-8",
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location("dataset_tree", TREE_VERIFY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    count, total_bytes, digest = module.dataset_tree_digest(manifest, images)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    lock["huggingface"]["dataset"]["manifest"].update(
        {
            "pages": count,
            "referenced_image_bytes": total_bytes,
            "referenced_image_tree_sha256": digest,
        }
    )
    test_lock = tmp_path / "lock.json"
    test_lock.write_text(json.dumps(lock), encoding="utf-8")
    command = [
        sys.executable,
        str(TREE_VERIFY),
        "--manifest",
        str(manifest),
        "--image-dir",
        str(images),
        "--lock",
        str(test_lock),
    ]
    ok = subprocess.run(command, capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    (images / "b.png").write_bytes(b"changed")
    bad = subprocess.run(command, capture_output=True, text=True, check=False)
    assert bad.returncode != 0
    assert "Dataset tree lock mismatch" in bad.stdout + bad.stderr


def test_requirements_verifier_reports_missing_active_pin(tmp_path: Path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "definitely-not-installed-package==1.2.3 \\\n"
        "    --hash=sha256:" + "0" * 64 + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(REQUIREMENTS_VERIFY), str(requirements)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "missing: definitely-not-installed-package" in result.stdout + result.stderr