from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PYTHON_VERSION = REPO_ROOT / ".python-version"
SETUP = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "setup.ps1"


def test_uv_project_pins_supported_python_and_fast_test_dependencies():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert project["project"]["requires-python"] == ">=3.10,<3.12"
    assert PYTHON_VERSION.read_text(encoding="utf-8").strip() == "3.11"
    dev_dependencies = project["dependency-groups"]["dev"]
    assert any(dependency.startswith("pytest") for dependency in dev_dependencies)
    assert any(dependency.startswith("psutil") for dependency in dev_dependencies)


def test_omnidocbench_setup_prefers_uv_and_never_uses_unsupported_python():
    text = SETUP.read_text(encoding="utf-8")

    assert "Get-Command uv" in text
    assert '& $uvExe venv --python 3.11 --seed $venvDir' in text
    assert "& $uvExe sync --locked --all-groups --inexact" in text
    assert "OmniDocBench requires Python 3.10 or 3.11" in text
    assert "Creating venv from the default python anyway" not in text
    assert 'throw "OmniDocBench requires Python 3.10 or 3.11' in text
    assert 'Join-Path $venvDir "Scripts\\hf.exe"' in text
    assert "& $hfCli download opendatalab/OmniDocBench" in text
    assert '$env:HF_HUB_DISABLE_XET = "1"' in text
    assert "--max-workers 4" in text
    assert "$_.page_info.image_path" in text
    assert "Partial dataset detected" in text
    assert "function ConvertTo-ExtendedPath" in text
    assert "Test-FileExtended" in text
    assert "function Ensure-ShortRepoRoot" in text
    assert "Windows short repository path" in text
    assert '$downloadDataDir = Join-Path (Split-Path -Parent $shortRoot) "dataset-download"' in text
    assert "--local-dir $downloadDataDir" in text
    assert "ConvertTo-ExtendedPath -Path $targetPath" in text
    assert "Dataset staging source missing" in text
    assert "    huggingface-cli download" not in text
