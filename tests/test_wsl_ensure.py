from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.win32



REPO_ROOT = Path(__file__).resolve().parents[1]
WSL_ENSURE = REPO_ROOT / "scripts" / "wsl-ensure.ps1"


def test_wsl_list_probe_treats_uninstalled_feature_as_no_distros():
    text = WSL_ENSURE.read_text(encoding="utf-8")
    function = text.split("function Get-WslDistros {", 1)[1].split(
        "function Rename-WslDistro", 1
    )[0]

    assert '$ErrorActionPreference = "Continue"' in function
    assert "$output = wsl --list --quiet 2>$null" in function
    assert "$listExit = $LASTEXITCODE" in function
    assert 'if ($listExit -ne 0) { return "" }' in function
    assert "$ErrorActionPreference = $previousErrorActionPreference" in function


def test_wsl_start_probe_is_direct_and_checked():
    text = WSL_ENSURE.read_text(encoding="utf-8")
    function = text.split("function Test-WslDistro {", 1)[1].split(
        "function Rename-WslDistro", 1
    )[0]

    assert "$probeOutput = wsl -d $Name -- echo OK" in function
    assert "$probeExit = $LASTEXITCODE" in function
    assert '$cleaned -eq "OK"' in function
    assert "-- bash -c" not in text
    assert "registered but cannot start" in text


def test_rootfs_fallback_rejects_content_that_does_not_match_lock():
    text = WSL_ENSURE.read_text(encoding="utf-8")

    assert "upstream-lock.json" in text
    assert "-Component UbuntuRootfs -Path $tarball" in text
    assert "downloaded content failed upstream lock verification" in text
    assert "Remove-Item -LiteralPath $tarball" in text