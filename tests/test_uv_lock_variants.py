from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import verify_uv_lock_variants as verifier


def _lock_text(
    index_url: str,
    artifact_prefix: str,
    *,
    version: str = "1.0",
    artifact_hash: str = "sha256:" + "1" * 64,
) -> str:
    return f'''version = 1
revision = 1
requires-python = ">=3.10"

[[package]]
name = "demo"
version = "{version}"
source = {{ registry = "{index_url}" }}
sdist = {{ url = "{artifact_prefix}demo-{version}.tar.gz", hash = "{artifact_hash}", size = 10, upload-time = "2026-01-01T00:00:00Z" }}
wheels = [
    {{ url = "{artifact_prefix}demo-{version}-py3-none-any.whl", hash = "{artifact_hash}", size = 20, upload-time = "2026-01-01T00:00:00Z" }},
]

[[package]]
name = "root"
version = "0.0.0"
source = {{ virtual = "." }}
dependencies = [{{ name = "demo" }}]
'''


def write_three_lock_catalog(root: Path) -> Path:
    for spec in verifier.SOURCE_SPECS:
        path = root / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_lock_text(spec.index_url, spec.artifact_url_prefix), encoding="utf-8")
    return root


def mutate_artifact_url(root: Path, source_id: str, replacement: str) -> None:
    spec = next(spec for spec in verifier.SOURCE_SPECS if spec.source_id == source_id)
    path = root / spec.path
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'{spec.artifact_url_prefix}demo-1.0.tar.gz', replacement
        ),
        encoding="utf-8",
    )


def test_canonical_pypi_cdn_is_distinct_from_index(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    manifest = verifier.build_manifest(root)
    assert manifest["locks"]["pypi"]["index_url"] == "https://pypi.org/simple"
    assert manifest["locks"]["pypi"]["artifact_url_prefix"] == "https://files.pythonhosted.org/packages/"


@pytest.mark.parametrize("source_id", ["pypi", "tuna", "aliyun"])
def test_artifact_outside_declared_prefix_is_rejected(tmp_path, source_id):
    root = write_three_lock_catalog(tmp_path)
    mutate_artifact_url(root, source_id, "https://evil.example/packages/demo.whl")
    with pytest.raises(verifier.CatalogError, match="artifact_url_prefix"):
        verifier.build_manifest(root)


@pytest.mark.parametrize("suffix", ["../demo.whl", "%2E%2E/demo.whl", "demo.whl?download=1"])
def test_unsafe_artifact_url_within_prefix_is_rejected(tmp_path, suffix):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "https://files.pythonhosted.org/packages/demo-1.0.tar.gz",
            "https://files.pythonhosted.org/packages/" + suffix,
        ),
        encoding="utf-8",
    )

    with pytest.raises(verifier.CatalogError, match="artifact_url_prefix"):
        verifier.build_manifest(root)


@pytest.mark.parametrize("source_id", ["pypi", "tuna", "aliyun"])
def test_each_declared_origin_normalizes_to_the_same_registry_graph(tmp_path, source_id):
    root = write_three_lock_catalog(tmp_path)
    spec = next(spec for spec in verifier.SOURCE_SPECS if spec.source_id == source_id)

    normalized = verifier.normalize_lock(verifier.load_lock(root / spec.path), spec)

    package = normalized["package"][0]
    assert package["source"] == {"registry": "<registry>"}
    assert package["sdist"]["url"] == "demo-1.0.tar.gz"
    assert package["wheels"][0]["url"] == "demo-1.0-py3-none-any.whl"
    assert "upload-time" not in package["sdist"]


@pytest.mark.parametrize(
    ("old", "new", "description"),
    [
        ('version = "1.0"', 'version = "2.0"', "package version"),
        ('dependencies = [{ name = "demo" }]', 'dependencies = [{ name = "other" }]', "dependency edge"),
        ('dependencies = [{ name = "demo" }]', 'dependencies = [{ name = "demo", marker = "sys_platform == \'win32\'" }]', "marker"),
        ("sha256:" + "1" * 64, "sha256:" + "2" * 64, "artifact hash"),
        ("size = 10", "size = 11", "artifact size"),
        ('source = { virtual = "." }', 'source = { url = "https://example.invalid/direct.whl" }', "direct URL"),
    ],
)
def test_semantic_lock_mutations_are_rejected(tmp_path, old, new, description):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")

    with pytest.raises(verifier.CatalogError, match="normalized dependency graph differs"):
        verifier.build_manifest(root)


def test_unknown_registry_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    path.write_text(
        path.read_text(encoding="utf-8").replace("https://pypi.org/simple", "https://evil.example/simple"),
        encoding="utf-8",
    )

    with pytest.raises(verifier.CatalogError, match="registry mismatch"):
        verifier.build_manifest(root)


def test_mixed_registry_source_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'source = { registry = "https://pypi.org/simple" }',
            'source = { registry = "https://pypi.org/simple", url = "https://example.invalid/demo" }',
        ),
        encoding="utf-8",
    )

    with pytest.raises(verifier.CatalogError, match="registry mismatch"):
        verifier.build_manifest(root)


def test_registry_package_without_artifacts_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    text = path.read_text(encoding="utf-8")
    artifact_lines = (
        'sdist = { url = "https://files.pythonhosted.org/packages/demo-1.0.tar.gz", hash = "sha256:'
        + "1" * 64
        + '", size = 10, upload-time = "2026-01-01T00:00:00Z" }\n'
        'wheels = [\n'
        '    { url = "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl", hash = "sha256:'
        + "1" * 64
        + '", size = 20, upload-time = "2026-01-01T00:00:00Z" },\n'
        ']\n'
    )
    path.write_text(text.replace(artifact_lines, ""), encoding="utf-8")

    with pytest.raises(verifier.CatalogError, match="no artifacts"):
        verifier.build_manifest(root)


def _write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_verify_catalog_accepts_the_exact_generated_manifest(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    manifest = verifier.build_manifest(root)
    manifest_path = root / "locks" / "manifest.json"
    _write_manifest(manifest_path, manifest)

    assert verifier.verify_catalog(root, manifest_path) == manifest


@pytest.mark.parametrize(
    "mutation",
    [
        lambda manifest: manifest.__setitem__("unexpected", True),
        lambda manifest: manifest["locks"]["pypi"].__setitem__("unexpected", True),
        lambda manifest: manifest["locks"]["pypi"].__setitem__("sha256", "A" * 64),
    ],
    ids=["unknown-top-level", "unknown-lock-field", "bad-hash"],
)
def test_verify_catalog_rejects_invalid_manifest_schema(tmp_path, mutation):
    root = write_three_lock_catalog(tmp_path)
    manifest = verifier.build_manifest(root)
    mutation(manifest)
    manifest_path = root / "locks" / "manifest.json"
    _write_manifest(manifest_path, manifest)

    with pytest.raises(verifier.CatalogError):
        verifier.verify_catalog(root, manifest_path)


def test_verify_catalog_rejects_duplicate_manifest_fields(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    manifest = verifier.build_manifest(root)
    manifest_path = root / "locks" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"schema_version":1,"schema_version":1,' + json.dumps(manifest)[1:], encoding="utf-8"
    )

    with pytest.raises(verifier.CatalogError, match="duplicate"):
        verifier.verify_catalog(root, manifest_path)


def test_cli_generates_utf8_manifest_then_verifies_it(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    script = Path(verifier.__file__)
    command = [sys.executable, str(script), "--root", str(root)]

    write_result = subprocess.run(
        [*command, "--write-manifest", "locks/manifest.json"], text=True, capture_output=True, check=False
    )

    manifest_path = root / "locks" / "manifest.json"
    assert write_result.returncode == 0, write_result.stderr
    assert not manifest_path.read_bytes().startswith(b"\xef\xbb\xbf")
    verify_result = subprocess.run(
        [*command, "--manifest", "locks/manifest.json"], text=True, capture_output=True, check=False
    )
    assert verify_result.returncode == 0, verify_result.stderr


def test_cli_does_not_replace_manifest_when_catalog_is_invalid(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    manifest_path = root / "locks" / "manifest.json"
    manifest_path.write_text("existing manifest", encoding="utf-8")
    mutate_artifact_url(root, "pypi", "https://evil.example/packages/demo.whl")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(verifier.__file__)),
            "--root",
            str(root),
            "--write-manifest",
            "locks/manifest.json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert manifest_path.read_text(encoding="utf-8") == "existing manifest"


def test_python_310_tomli_fallback_is_declared():
    source = Path(verifier.__file__).read_text(encoding="utf-8")
    assert "except ModuleNotFoundError" in source
    assert "import tomli as tomllib" in source
