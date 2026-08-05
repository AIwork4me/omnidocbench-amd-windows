from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.parse

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    path: str
    index_url: str
    artifact_url_prefix: str


SOURCE_SPECS = (
    SourceSpec("pypi", "uv.lock", "https://pypi.org/simple", "https://files.pythonhosted.org/packages/"),
    SourceSpec("tuna", "locks/uv.tuna.lock", "https://pypi.tuna.tsinghua.edu.cn/simple", "https://pypi.tuna.tsinghua.edu.cn/packages/"),
    SourceSpec("aliyun", "locks/uv.aliyun.lock", "https://mirrors.aliyun.com/pypi/simple", "https://mirrors.aliyun.com/pypi/packages/"),
)


class CatalogError(ValueError):
    pass


_MANIFEST_KEYS = ("schema_version", "normalized_graph_sha256", "locks")
_LOCK_KEYS = ("path", "index_url", "artifact_url_prefix", "sha256")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def load_lock(path: Path) -> dict:
    try:
        lock = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CatalogError(f"cannot load lock {path}: {error}") from error
    if not isinstance(lock, dict):
        raise CatalogError(f"lock is not an object: {path}")
    return lock


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _artifact(artifact: dict, source: SourceSpec) -> dict:
    url = artifact.get("url")
    if not isinstance(url, str):
        raise CatalogError(f"artifact URL is missing for {source.source_id}: {url}")
    parsed = urllib.parse.urlsplit(url)
    relative = urllib.parse.unquote(url[len(source.artifact_url_prefix):]) if url.startswith(source.artifact_url_prefix) else ""
    relative_parts = relative.split("/")
    filename = urllib.parse.unquote(PurePosixPath(parsed.path).name)
    if (
        not url.startswith(source.artifact_url_prefix)
        or parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not relative
        or PurePosixPath(relative).is_absolute()
        or "\\" in relative
        or any(part in ("", ".", "..") for part in relative_parts)
        or "/" in filename
        or "\\" in filename
    ):
        raise CatalogError(f"artifact URL is outside artifact_url_prefix for {source.source_id}: {url}")
    if not filename:
        raise CatalogError(f"artifact URL has no filename for {source.source_id}: {url}")
    normalized = copy.deepcopy(artifact)
    normalized["url"] = filename
    normalized.pop("upload-time", None)
    return normalized


def normalize_lock(lock: dict, source: SourceSpec) -> dict:
    normalized = copy.deepcopy(lock)
    for package in normalized.get("package", []):
        package_source = package.get("source", {})
        if "registry" in package_source:
            if package_source != {"registry": source.index_url}:
                raise CatalogError(f"registry mismatch for {package.get('name')}: {package_source}")
            sdist = package.get("sdist")
            wheels = package.get("wheels", [])
            if sdist is not None and not isinstance(sdist, dict):
                raise CatalogError(f"sdist must be an object for {package.get('name')}")
            if not isinstance(wheels, list):
                raise CatalogError(f"wheels must be an array for {package.get('name')}")
            if sdist is None and not wheels:
                raise CatalogError(f"registry package has no artifacts: {package.get('name')}")
            package["source"] = {"registry": "<registry>"}
            if sdist is not None:
                package["sdist"] = _artifact(sdist, source)
            if "wheels" in package:
                package["wheels"] = [_artifact(wheel, source) for wheel in wheels]
    return normalized


def normalized_graph_sha256(root: Path) -> str:
    graphs = [normalize_lock(load_lock(root / spec.path), spec) for spec in SOURCE_SPECS]
    baseline = _canonical_json(graphs[0])
    for spec, graph in zip(SOURCE_SPECS[1:], graphs[1:]):
        if _canonical_json(graph) != baseline:
            raise CatalogError(f"normalized dependency graph differs for {spec.source_id}")
    return hashlib.sha256(baseline).hexdigest()


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise CatalogError(f"cannot hash lock {path}: {error}") from error


def build_manifest(root: Path) -> dict:
    digest = normalized_graph_sha256(root)
    locks = {}
    for spec in SOURCE_SPECS:
        locks[spec.source_id] = {
            "path": spec.path,
            "index_url": spec.index_url,
            "artifact_url_prefix": spec.artifact_url_prefix,
            "sha256": _sha256(root / spec.path),
        }
    return {"schema_version": 1, "normalized_graph_sha256": digest, "locks": locks}


def _json_object_without_duplicates(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise CatalogError(f"duplicate manifest field: {key}")
        value[key] = item
    return value


def _load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_json_object_without_duplicates
        )
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"cannot load manifest {path}: {error}") from error
    if not isinstance(manifest, dict):
        raise CatalogError("manifest must be an object")
    return manifest


def validate_manifest_schema(manifest: dict) -> None:
    if tuple(manifest) != _MANIFEST_KEYS:
        raise CatalogError(f"manifest fields must be exactly {_MANIFEST_KEYS}")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise CatalogError("manifest schema_version must be 1")
    graph_hash = manifest["normalized_graph_sha256"]
    if not isinstance(graph_hash, str) or not _SHA256_RE.fullmatch(graph_hash):
        raise CatalogError("manifest normalized_graph_sha256 must be a lowercase SHA-256 hash")
    locks = manifest["locks"]
    if not isinstance(locks, dict) or tuple(locks) != tuple(spec.source_id for spec in SOURCE_SPECS):
        raise CatalogError("manifest locks must contain the fixed source IDs in order")
    for spec in SOURCE_SPECS:
        lock = locks[spec.source_id]
        if not isinstance(lock, dict) or tuple(lock) != _LOCK_KEYS:
            raise CatalogError(f"manifest lock fields must be exactly {_LOCK_KEYS} for {spec.source_id}")
        if (
            lock["path"] != spec.path
            or lock["index_url"] != spec.index_url
            or lock["artifact_url_prefix"] != spec.artifact_url_prefix
        ):
            raise CatalogError(f"manifest source metadata differs for {spec.source_id}")
        lock_hash = lock["sha256"]
        if not isinstance(lock_hash, str) or not _SHA256_RE.fullmatch(lock_hash):
            raise CatalogError(f"manifest lock sha256 must be a lowercase SHA-256 hash for {spec.source_id}")


def verify_catalog(root: Path, manifest_path: Path) -> dict:
    manifest = _load_manifest(manifest_path)
    validate_manifest_schema(manifest)
    expected = build_manifest(root)
    if manifest != expected:
        raise CatalogError("lock manifest does not match the tracked catalog")
    return manifest


def _write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(manifest, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate equivalent uv lock variants without network access.")
    parser.add_argument("--root", required=True, type=Path)
    manifest_group = parser.add_mutually_exclusive_group(required=True)
    manifest_group.add_argument("--manifest", type=Path)
    manifest_group.add_argument("--write-manifest", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest_argument = args.manifest if args.manifest is not None else args.write_manifest
    manifest_path = manifest_argument if manifest_argument.is_absolute() else root / manifest_argument
    try:
        if args.manifest is not None:
            verify_catalog(root, manifest_path)
            print(f"verified lock catalog: {manifest_path}")
        else:
            manifest = build_manifest(root)
            _write_manifest(manifest_path, manifest)
            print(f"wrote lock manifest: {manifest_path}")
    except CatalogError as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
