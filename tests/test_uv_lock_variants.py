from __future__ import annotations

import json
from pathlib import Path
import re
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
    artifact_sizes: tuple[object | None, ...] = (10, 20),
    nested_registry_sources: bool = False,
    dependency_source: str | None = None,
) -> str:
    if len(artifact_sizes) < 2:
        raise ValueError("fixture needs an sdist and at least one wheel")

    def size_field(size: object | None) -> str:
        if size is None:
            return ""
        if isinstance(size, bool):
            size = str(size).lower()
        return f", size = {size}"

    dependency_fields = ['name = "demo"', 'marker = "python_version >= \'3.10\'"']
    if nested_registry_sources:
        dependency_fields.append(f'source = {{ registry = "{index_url}" }}')
    elif dependency_source is not None:
        dependency_fields.append(f"source = {{ {dependency_source} }}")
    dependency_fields.append('note = "https://example.invalid/literal"')
    dependency = "{ " + ", ".join(dependency_fields) + " }"

    wheels = []
    for index, size in enumerate(artifact_sizes[1:]):
        wheel_suffix = "py3-none-any.whl" if index == 0 else f"{index}-py3-none-any.whl"
        wheels.append(
            f'    {{ url = "{artifact_prefix}demo-{version}-{wheel_suffix}", '
            f'hash = "{artifact_hash}"{size_field(size)}, '
            'upload-time = "2026-01-01T00:00:00Z" },'
        )
    wheel_text = "\n".join(wheels)

    return f'''version = 1
revision = 1
requires-python = ">=3.10"

[[package]]
name = "demo"
version = "{version}"
source = {{ registry = "{index_url}" }}
sdist = {{ url = "{artifact_prefix}demo-{version}.tar.gz", hash = "{artifact_hash}"{size_field(artifact_sizes[0])}, upload-time = "2026-01-01T00:00:00Z" }}
wheels = [
{wheel_text}
]

[[package]]
name = "root"
version = "0.0.0"
source = {{ virtual = "." }}
dependencies = [{dependency}]
'''


def write_three_lock_catalog(
    root: Path,
    *,
    artifact_sizes_by_source: dict[str, tuple[object | None, ...]] | None = None,
    nested_registry_sources: bool = False,
    dependency_source: str | None = None,
) -> Path:
    for spec in verifier.SOURCE_SPECS:
        path = root / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact_sizes = (artifact_sizes_by_source or {}).get(spec.source_id, (10, 20))
        path.write_text(
            _lock_text(
                spec.index_url,
                spec.artifact_url_prefix,
                artifact_sizes=artifact_sizes,
                nested_registry_sources=nested_registry_sources,
                dependency_source=dependency_source,
            ),
            encoding="utf-8",
        )
    return root


def remove_all_artifact_sizes(path: Path) -> None:
    text = re.sub(r", size = (?:-?\d+|true|false)", "", path.read_text(encoding="utf-8"))
    path.write_text(text, encoding="utf-8")


def remove_one_artifact_size(path: Path) -> None:
    text = re.sub(
        r", size = (?:-?\d+|true|false)", "", path.read_text(encoding="utf-8"), count=1
    )
    path.write_text(text, encoding="utf-8")


def change_one_artifact_size(path: Path, size: object) -> None:
    replacement = str(size).lower() if isinstance(size, bool) else str(size)
    text, count = re.subn(
        r"(?<=size = )(?:-?\d+|true|false)", replacement, path.read_text(encoding="utf-8"), count=1
    )
    assert count == 1
    path.write_text(text, encoding="utf-8")


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


@pytest.mark.parametrize(
    "suffix",
    [
        "%2Fetc%2Fdemo.whl",
        "nested%5Cdemo.whl",
        "/etc/demo.whl",
        "nested//demo.whl",
        "/nested/demo.whl",
    ],
    ids=["encoded-slash", "encoded-backslash", "decoded-absolute", "repeated-separator", "leading-separator"],
)
def test_decoded_unsafe_artifact_relative_location_is_rejected(tmp_path, suffix):
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


def test_valid_nested_mirror_artifact_path_is_accepted(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    for spec in verifier.SOURCE_SPECS:
        path = root / spec.path
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                spec.artifact_url_prefix, spec.artifact_url_prefix + "nested/path/"
            ),
            encoding="utf-8",
        )

    assert verifier.build_manifest(root)["normalized_graph_sha256"]


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
        ('name = "demo", marker', 'name = "other", marker', "dependency edge"),
        ('marker = "python_version >= \'3.10\'"', 'marker = "sys_platform == \'win32\'"', "marker"),
        ("sha256:" + "1" * 64, "sha256:" + "2" * 64, "artifact hash"),
        ('source = { virtual = "." }', 'source = { url = "https://example.invalid/direct.whl" }', "direct URL"),
    ],
)
def test_semantic_lock_mutations_are_rejected(tmp_path, old, new, description):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")

    with pytest.raises(verifier.CatalogError):
        verifier.build_manifest(root)


def test_unknown_registry_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    path = root / "uv.lock"
    path.write_text(
        path.read_text(encoding="utf-8").replace("https://pypi.org/simple", "https://evil.example/simple"),
        encoding="utf-8",
    )

    with pytest.raises(verifier.CatalogError, match="registry annotation"):
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

    with pytest.raises(verifier.CatalogError, match="registry annotation"):
        verifier.build_manifest(root)


def test_mirror_missing_sizes_projects_canonical_sizes(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    mirror_path = root / "locks" / "uv.aliyun.lock"
    before = mirror_path.read_bytes()
    remove_all_artifact_sizes(mirror_path)
    omitted = mirror_path.read_bytes()

    assert before != omitted
    assert len(verifier.normalized_graph_sha256(root)) == 64
    assert mirror_path.read_bytes() == omitted


def test_one_missing_mirror_size_projects_canonical_size_without_changing_digest(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    expected = verifier.normalized_graph_sha256(root)
    remove_one_artifact_size(root / "locks" / "uv.tuna.lock")

    assert verifier.normalized_graph_sha256(root) == expected


def test_canonical_missing_size_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    remove_one_artifact_size(root / "uv.lock")

    with pytest.raises(verifier.CatalogError, match="canonical artifact size"):
        verifier.build_manifest(root)


@pytest.mark.parametrize("size", [True, -1], ids=["boolean", "negative"])
def test_invalid_canonical_size_is_rejected(tmp_path, size):
    root = write_three_lock_catalog(tmp_path)
    change_one_artifact_size(root / "uv.lock", size)

    with pytest.raises(verifier.CatalogError, match="canonical artifact size"):
        verifier.build_manifest(root)


def test_wrong_declared_mirror_size_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    change_one_artifact_size(root / "locks" / "uv.tuna.lock", 999)

    with pytest.raises(verifier.CatalogError, match="mirror artifact size"):
        verifier.build_manifest(root)


def test_equal_declared_mirror_size_is_accepted(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    change_one_artifact_size(root / "locks" / "uv.tuna.lock", 10)

    assert len(verifier.normalized_graph_sha256(root)) == 64


def test_canonical_size_mutation_changes_digest_and_invalidates_manifest(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    manifest = verifier.build_manifest(root)
    manifest_path = root / "locks" / "manifest.json"
    _write_manifest(manifest_path, manifest)

    for spec in verifier.SOURCE_SPECS:
        change_one_artifact_size(root / spec.path, 11)

    assert verifier.normalized_graph_sha256(root) != manifest["normalized_graph_sha256"]
    with pytest.raises(verifier.CatalogError, match="manifest does not match"):
        verifier.verify_catalog(root, manifest_path)


def test_nested_registry_sources_normalize(tmp_path):
    root = write_three_lock_catalog(tmp_path, nested_registry_sources=True)

    assert len(verifier.normalized_graph_sha256(root)) == 64
    for spec in verifier.SOURCE_SPECS:
        normalized = verifier.normalize_lock(verifier.load_lock(root / spec.path), spec)
        assert normalized["package"][1]["dependencies"][0]["source"] == {
            "registry": "<registry>"
        }


@pytest.mark.parametrize(
    "replacement",
    [
        'source = { registry = "https://evil.example/simple" }',
        'source = { registry = "https://pypi.org/simple", url = "https://example.invalid/demo" }',
    ],
    ids=["unknown", "mixed"],
)
def test_invalid_nested_registry_source_is_rejected(tmp_path, replacement):
    root = write_three_lock_catalog(tmp_path, nested_registry_sources=True)
    path = root / "uv.lock"
    text = path.read_text(encoding="utf-8")
    annotation = 'source = { registry = "https://pypi.org/simple" }'
    prefix, separator, suffix = text.rpartition(annotation)
    assert separator
    path.write_text(prefix + replacement + suffix, encoding="utf-8")

    with pytest.raises(verifier.CatalogError, match="registry annotation"):
        verifier.build_manifest(root)


@pytest.mark.parametrize(
    "dependency_source",
    [
        'url = "https://example.invalid/demo.whl"',
        'git = "https://example.invalid/demo.git?rev=abc"',
        'path = "../demo"',
        "direct = true",
    ],
    ids=["url", "git", "path", "direct"],
)
def test_significant_non_registry_nested_values_are_preserved(tmp_path, dependency_source):
    root = write_three_lock_catalog(tmp_path, dependency_source=dependency_source)

    assert len(verifier.normalized_graph_sha256(root)) == 64
    for spec in verifier.SOURCE_SPECS:
        raw = verifier.load_lock(root / spec.path)
        normalized = verifier.normalize_lock(raw, spec)
        raw_dependency = raw["package"][1]["dependencies"][0]
        normalized_dependency = normalized["package"][1]["dependencies"][0]
        assert normalized_dependency == raw_dependency


def test_non_registry_nested_source_mutation_is_significant(tmp_path):
    root = write_three_lock_catalog(tmp_path, dependency_source='path = "../demo"')
    path = root / "locks" / "uv.tuna.lock"
    path.write_text(
        path.read_text(encoding="utf-8").replace('path = "../demo"', 'path = "../other"'),
        encoding="utf-8",
    )

    with pytest.raises(verifier.CatalogError, match="normalized dependency graph differs"):
        verifier.build_manifest(root)


def test_live_mirror_metadata_shape_normalizes(tmp_path):
    canonical_sizes = (10, 20, 30, 40, 50, 60)
    root = write_three_lock_catalog(
        tmp_path,
        artifact_sizes_by_source={
            "pypi": canonical_sizes,
            "tuna": (None, None, None, None, 50, 60),
            "aliyun": (None, None, None, None, None, None),
        },
        nested_registry_sources=True,
    )

    assert root.joinpath("locks", "uv.tuna.lock").read_text(encoding="utf-8").count("size =") == 2
    assert "size =" not in root.joinpath("locks", "uv.aliyun.lock").read_text(encoding="utf-8")
    assert len(verifier.normalized_graph_sha256(root)) == 64


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
