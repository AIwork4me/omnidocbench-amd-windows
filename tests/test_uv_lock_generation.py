from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import tomllib

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPOSITORY_ROOT / "scripts" / "generate-uv-lock-variants.ps1"
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_uv_lock_variants.py"

SOURCES = {
    "pypi": ("https://pypi.org/simple", "https://files.pythonhosted.org/packages/"),
    "tuna": (
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://pypi.tuna.tsinghua.edu.cn/packages/",
    ),
    "aliyun": (
        "https://mirrors.aliyun.com/pypi/simple",
        "https://mirrors.aliyun.com/pypi/packages/",
    ),
}

CONTROLLED_UV_ENVIRONMENT = (
    "UV_INDEX",
    "UV_DEFAULT_INDEX",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_INDEX_STRATEGY",
    "UV_NO_INDEX",
    "UV_FIND_LINKS",
    "UV_CONFIG_FILE",
    "UV_NO_CONFIG",
    "UV_PROJECT_ENVIRONMENT",
)


def _lock_text(source_id: str) -> str:
    index_url, artifact_prefix = SOURCES[source_id]

    def artifact(package: str, role: str, ordinal: int) -> str:
        extension = ".tar.gz" if role == "sdist" else "-py3-none-any.whl"
        size = "" if source_id == "aliyun" or (source_id == "tuna" and ordinal < 4) else f", size = {(ordinal + 1) * 10}"
        return (
            f'{{ url = "{artifact_prefix}{package}-1.0{extension}", '
            f'hash = "sha256:{str(ordinal + 1) * 64}"{size}, '
            'upload-time = "2026-01-01T00:00:00Z" }'
        )

    packages = []
    for position, package in enumerate(("alpha", "beta", "gamma")):
        dependency = ""
        if position < 2:
            dependency = (
                f'dependencies = [{{ name = "{("beta", "gamma")[position]}", '
                f'source = {{ registry = "{index_url}" }} }}]\n'
            )
        packages.append(
            f'''[[package]]
name = "{package}"
version = "1.0"
source = {{ registry = "{index_url}" }}
{dependency}sdist = {artifact(package, "sdist", position * 2)}
wheels = [
    {artifact(package, "wheel", position * 2 + 1)},
]
'''
        )

    return f'''version = 1
revision = 1
requires-python = ">=3.10"

{chr(10).join(packages)}'''


FAKE_UV = r"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

SOURCES = {
    "https://pypi.org/simple": "pypi",
    "https://pypi.tuna.tsinghua.edu.cn/simple": "tuna",
    "https://mirrors.aliyun.com/pypi/simple": "aliyun",
}
CONTROLLED = json.loads(os.environ["FAKE_UV_CONTROLLED"])


arguments = sys.argv[1:]
with open(os.environ["FAKE_UV_LOG"], "a", encoding="utf-8", newline="\n") as log:
    log.write(json.dumps(arguments) + "\n")

if arguments[0] != "lock" or "--project" not in arguments or "--default-index" not in arguments:
    raise SystemExit(90)
if any(name in os.environ for name in CONTROLLED):
    raise SystemExit(91)

project = Path(arguments[arguments.index("--project") + 1])
index_url = arguments[arguments.index("--default-index") + 1]
source_id = SOURCES[index_url]
expected_project = Path(os.environ["FAKE_UV_EXPECTED_PROJECT"]).read_bytes()
expected_canonical = Path(os.environ["FAKE_UV_EXPECTED_LOCK"]).read_bytes()
if (project / "pyproject.toml").read_bytes() != expected_project:
    raise SystemExit(92)

lock_path = project / "uv.lock"
generated = Path(os.environ[f"FAKE_UV_GENERATED_{source_id.upper()}"]).read_bytes()
is_check = "--check" in arguments
expected_lock = expected_canonical if source_id == "pypi" or not is_check else generated
if lock_path.read_bytes() != expected_lock:
    raise SystemExit(93)

if not is_check:
    if os.environ.get("FAKE_UV_FAIL_SOURCE") == source_id:
        raise SystemExit(43)
    lock_path.write_bytes(generated)
"""


def _make_test_repository(tmp_path: Path, *, existing_catalog: bool = False) -> tuple[Path, Path]:
    root = tmp_path / "repository"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(VERIFIER, root / "scripts" / VERIFIER.name)
    if GENERATOR.exists():
        shutil.copy2(GENERATOR, root / "scripts" / GENERATOR.name)
    (root / "pyproject.toml").write_bytes(b"[project]\nname='fixture'\nversion='0.0.0'\n")
    (root / "uv.lock").write_text(_lock_text("pypi"), encoding="utf-8")
    if existing_catalog:
        locks = root / "locks"
        locks.mkdir()
        (locks / "uv.tuna.lock").write_bytes(b"old tuna catalog\x00\n")
        (locks / "uv.aliyun.lock").write_bytes(b"old aliyun catalog\xff\n")
        (locks / "manifest.json").write_bytes(b"old manifest\r\n")

    fake_dir = tmp_path / "fake-uv"
    fake_dir.mkdir()
    (fake_dir / "fake_uv.py").write_text(textwrap.dedent(FAKE_UV), encoding="utf-8")
    for source_id in SOURCES:
        (fake_dir / f"generated-{source_id}.lock").write_text(_lock_text(source_id), encoding="utf-8")
    fake_executable = fake_dir / "fake-uv.cmd"
    fake_executable.write_text(f'@"{sys.executable}" "%~dp0fake_uv.py" %*\n', encoding="utf-8")
    return root, fake_executable


def _catalog_bytes(root: Path) -> dict[str, bytes]:
    return {
        name: (root / "locks" / name).read_bytes()
        for name in ("uv.tuna.lock", "uv.aliyun.lock", "manifest.json")
    }


def _environment(root: Path, tmp_path: Path, fail_source: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    for position, name in enumerate(CONTROLLED_UV_ENVIRONMENT):
        environment[name] = "" if position % 2 else f"poison-{name}"
    environment.update(
        {
            "FAKE_UV_LOG": str(tmp_path / "uv-argv.jsonl"),
            "FAKE_UV_EXPECTED_PROJECT": str(root / "pyproject.toml"),
            "FAKE_UV_EXPECTED_LOCK": str(root / "uv.lock"),
            "FAKE_UV_CONTROLLED": json.dumps(CONTROLLED_UV_ENVIRONMENT),
            "FAKE_UV_GENERATED_PYPI": str(tmp_path / "fake-uv" / "generated-pypi.lock"),
            "FAKE_UV_GENERATED_TUNA": str(tmp_path / "fake-uv" / "generated-tuna.lock"),
            "FAKE_UV_GENERATED_ALIYUN": str(tmp_path / "fake-uv" / "generated-aliyun.lock"),
        }
    )
    if fail_source is not None:
        environment["FAKE_UV_FAIL_SOURCE"] = fail_source
    return environment


def _run_generator(
    root: Path,
    fake_uv: Path,
    environment: dict[str, str],
    *,
    fail_replacement_for: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        "-RepoRoot",
        str(root),
        "-UvExecutable",
        str(fake_uv),
        "-PythonExecutable",
        sys.executable,
    ]
    if fail_replacement_for is None:
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / GENERATOR.name),
            *arguments,
        ]
    else:
        def quote(value: object) -> str:
            return "'" + str(value).replace("'", "''") + "'"

        invocation = " ".join(["&", quote(root / "scripts" / GENERATOR.name), *map(quote, arguments)])
        script = rf'''$script:blockedDestination = [IO.Path]::GetFullPath({quote(fail_replacement_for)})
function Move-Item {{
    [CmdletBinding()]
    param([string] $LiteralPath, [string] $Destination, [switch] $Force)
    if ([IO.Path]::GetFullPath($Destination) -eq $script:blockedDestination) {{
        throw "injected replacement failure"
    }}
    Microsoft.PowerShell.Management\Move-Item @PSBoundParameters
}}
try {{ {invocation} }} catch {{ Write-Error $_; exit 1 }}
'''
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    return subprocess.run(command, text=True, capture_output=True, check=False, env=environment)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generator_uses_exact_isolated_uv_commands_and_preserves_canonical_lock(tmp_path):
    root, fake_uv = _make_test_repository(tmp_path)
    canonical_hash = _sha256(root / "uv.lock")

    result = _run_generator(root, fake_uv, _environment(root, tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in (tmp_path / "uv-argv.jsonl").read_text().splitlines()]
    assert len(calls) == 5
    expected = [
        ("pypi", True),
        ("tuna", False),
        ("tuna", True),
        ("aliyun", False),
        ("aliyun", True),
    ]
    temp_roots: set[Path] = set()
    for call, (source_id, check) in zip(calls, expected):
        project = Path(call[call.index("--project") + 1])
        url = SOURCES[source_id][0]
        expected_call = ["lock"]
        if check:
            expected_call.append("--check")
        expected_call.extend(["--no-config", "--project", str(project), "--default-index", url])
        assert call == expected_call
        assert "--upgrade" not in call
        assert not project.is_relative_to(root)
        assert project.name == source_id
        assert project.parent.name.startswith("omnidocbench-uv-generate-")
        temp_roots.add(project.parent)
    assert len(temp_roots) == 1
    assert not next(iter(temp_roots)).exists()
    assert _sha256(root / "uv.lock") == canonical_hash

    manifest = json.loads((root / "locks" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert list(manifest["locks"]) == ["pypi", "tuna", "aliyun"]


def test_generated_catalog_preserves_the_measured_live_lock_shape_byte_for_byte(tmp_path):
    root, fake_uv = _make_test_repository(tmp_path)

    result = _run_generator(root, fake_uv, _environment(root, tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    for source_id, expected_missing_sizes in (("pypi", 0), ("tuna", 4), ("aliyun", 6)):
        tracked = root / "uv.lock" if source_id == "pypi" else root / "locks" / f"uv.{source_id}.lock"
        if source_id != "pypi":
            expected_bytes = (tmp_path / "fake-uv" / f"generated-{source_id}.lock").read_bytes()
            assert tracked.read_bytes() == expected_bytes

        lock = tomllib.loads(tracked.read_text(encoding="utf-8"))
        artifacts = []
        nested_registries = []
        for package in lock["package"]:
            artifacts.extend(([package["sdist"]] if "sdist" in package else []) + package.get("wheels", []))
            nested_registries.extend(
                dependency["source"]["registry"]
                for dependency in package.get("dependencies", [])
            )
        assert sum("size" not in artifact for artifact in artifacts) == expected_missing_sizes
        if source_id == "aliyun":
            assert expected_missing_sizes == len(artifacts)
        assert nested_registries
        assert set(nested_registries) == {SOURCES[source_id][0]}

    assert "verified lock catalog:" in result.stdout


def test_default_repo_root_is_resolved_from_the_generator_location(tmp_path):
    root, fake_uv = _make_test_repository(tmp_path)
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / GENERATOR.name),
            "-UvExecutable",
            str(fake_uv),
            "-PythonExecutable",
            sys.executable,
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=_environment(root, tmp_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "locks" / "manifest.json").is_file()


def test_whitespace_repo_root_is_resolved_from_the_generator_location(tmp_path):
    root, fake_uv = _make_test_repository(tmp_path)
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / GENERATOR.name),
            "-RepoRoot",
            "   ",
            "-UvExecutable",
            str(fake_uv),
            "-PythonExecutable",
            sys.executable,
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=_environment(root, tmp_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "locks" / "manifest.json").is_file()


@pytest.mark.parametrize("fail_source", ["tuna", "aliyun"])
def test_uv_generation_failure_leaves_preexisting_catalog_byte_identical(tmp_path, fail_source):
    root, fake_uv = _make_test_repository(tmp_path, existing_catalog=True)
    before = _catalog_bytes(root)
    canonical_hash = _sha256(root / "uv.lock")

    result = _run_generator(root, fake_uv, _environment(root, tmp_path, fail_source))

    assert result.returncode != 0
    assert _catalog_bytes(root) == before
    assert _sha256(root / "uv.lock") == canonical_hash


def test_atomic_replacement_failure_rolls_back_every_catalog_file(tmp_path):
    root, fake_uv = _make_test_repository(tmp_path, existing_catalog=True)
    before = _catalog_bytes(root)
    canonical_hash = _sha256(root / "uv.lock")

    result = _run_generator(
        root,
        fake_uv,
        _environment(root, tmp_path),
        fail_replacement_for=root / "locks" / "uv.aliyun.lock",
    )

    assert result.returncode != 0
    assert "injected replacement failure" in result.stderr
    assert _catalog_bytes(root) == before
    assert _sha256(root / "uv.lock") == canonical_hash
