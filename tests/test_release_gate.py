"""Guard: release-gate.ps1 keeps its documented checks (executed by the gate
itself on tagged commits; these tests keep the script's surface honest)."""
from __future__ import annotations

import subprocess
from pathlib import Path

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
    ):
        assert required in text, f"release gate missing check/artifact: {required}"


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
