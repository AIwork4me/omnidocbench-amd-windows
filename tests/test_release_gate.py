"""Guard: release-gate.ps1 keeps its documented checks (executed by the gate
itself on tagged commits; these tests keep the script's surface honest)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.win32


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "release-gate.ps1"


def test_release_gate_parses():
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "$tokens=$null;$errors=$null;"
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{GATE}',[ref]$tokens,[ref]$errors);"
            "if($errors.Count){$errors|% Message;exit 1}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_gate_reads_version_before_tag_check():
    tag = "v-test-tag-that-does-not-exist"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(GATE), "-Tag", tag],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert f"tag {tag} does not exist" in output
    assert "Cannot index into a null array" not in output


def test_release_gate_checks_are_declared():
    text = GATE.read_text(encoding="utf-8")
    for required in (
        "pyproject.toml",
        "CHANGELOG.md",
        "render_benchmark_tables.py",
        "validate_benchmark_index.py",
        "validate_adapter_manifest.py",
        "status --porcelain",
        "Verified devices",
        "Unverified devices",
        "Known limitations",
        "Evidence levels",
        "SHA256SUMS",
        "sbom",
        "locks\\uv.tuna.lock",
        "locks\\uv.aliyun.lock",
        "locks\\manifest.json",
        "verify_uv_lock_variants.py",
    ):
        assert required in text, f"release gate missing check/artifact: {required}"


@pytest.mark.parametrize(
    ("relative_path", "mode"),
    [
        ("locks/uv.tuna.lock", "corrupt"),
        ("locks/uv.tuna.lock", "missing"),
        ("locks/uv.aliyun.lock", "corrupt"),
        ("locks/uv.aliyun.lock", "missing"),
        ("locks/manifest.json", "corrupt"),
        ("locks/manifest.json", "missing"),
    ],
)
def test_release_gate_fails_closed_for_each_catalog_artifact(relative_path, mode):
    """Execute the gate: this proves the verifier is invoked, not merely named."""
    path = REPO_ROOT / relative_path
    original = path.read_bytes()
    try:
        if mode == "corrupt":
            if relative_path.endswith(".json"):
                manifest = json.loads(original)
                manifest["normalized_graph_sha256"] = "0" * 64
                path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
            else:
                # A TOML comment preserves parse/graph semantics while changing
                # the raw lock hash recorded in the manifest.
                path.write_bytes(original + b"\n# release-gate-corruption\n")
        else:
            path.unlink()
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(GATE),
                "-Tag",
                "v-release-gate-catalog-test",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    finally:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "tag v-release-gate-catalog-test does not exist" not in output
    if mode == "missing":
        assert "required release file is missing" in output
        assert relative_path.replace("/", "\\") in output
    else:
        assert "uv lock catalog verification failed" in output.lower()


def test_release_hash_catalog_keeps_canonical_and_mirror_locks_distinct():
    text = GATE.read_text(encoding="utf-8")
    hash_block = text.split("# SHA256SUMS over the release-critical artifacts", 1)[1]
    for required in (
        '"uv.lock"',
        '"locks\\uv.tuna.lock"',
        '"locks\\uv.aliyun.lock"',
        '"locks\\manifest.json"',
    ):
        assert required in hash_block


def test_single_version_source_consistency():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    import re

    match = re.search(r'^version = "([^"]+)"$', pyproject, re.M)
    assert match, "pyproject.toml must declare a version"
    version = match.group(1)
    assert version != "0.0.0", "version must not be the 0.0.0 placeholder"
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog, f"CHANGELOG has no {version} section"
    citation = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert f'version: "{version}"' in citation, "CITATION.cff version mismatch"


def test_release_notes_template_documented():
    release_doc = (REPO_ROOT / "RELEASE.md").read_text(encoding="utf-8")
    for section in ("Verified devices", "Unverified devices", "Known limitations", "Evidence levels"):
        assert section in release_doc
