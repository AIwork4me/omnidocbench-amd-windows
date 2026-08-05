"""Guard: README.md and README.zh-CN.md must publish identical metric numbers."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

METRIC_ROWS = ["Overall", "Edit-dist", "TEDS", "CDM"]


def extract_table_numbers(md_text: str) -> list[str]:
    """Return all numeric cells from the two metric tables (paper vs measured)."""
    numbers = []
    for line in md_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        if not any(k in line for k in METRIC_ROWS):
            continue
        numbers += re.findall(r"\d+\.\d+", line)
    return numbers


def test_metric_tables_match_between_languages():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    en_nums = extract_table_numbers(en)
    zh_nums = extract_table_numbers(zh)
    assert en_nums, "no metric numbers found in README.md"
    assert en_nums == zh_nums, (
        f"metric table mismatch:\nEN: {en_nums}\nZH: {zh_nums}"
    )


def test_official_local_cdm_value_consistent():
    """official-local Formula CDM is 96.5022 in EN; ZH must not contradict."""
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    assert "96.5022" in en
    assert "96.5022" in zh, "ZH README must cite official-local CDM 96.5022"
    assert en.count("96.5022") == zh.count("96.5022"), (
        f"96.5022 count mismatch: EN={en.count('96.5022')} ZH={zh.count('96.5022')}"
    )
    for lang, text in (("EN", en), ("ZH", zh)):
        for line in text.splitlines():
            assert not ("official-local" in line and "97.36" in line), (
                f"{lang} README still pairs official-local with stale CDM 97.36: {line}"
            )


def test_readme_documents_ordered_strict_uv_mirror_fallback():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sources = (
        ("pypi", "https://pypi.org/simple"),
        ("tuna", "https://pypi.tuna.tsinghua.edu.cn/simple"),
        ("aliyun", "https://mirrors.aliyun.com/pypi/simple"),
    )
    positions = []
    for source_id, url in sources:
        marker = f"`{source_id}`"
        assert marker in readme
        assert f"`{url}`" in readme
        positions.append(readme.index(marker))
    assert positions == sorted(positions), "README must document pypi -> tuna -> aliyun order"
    assert "uv sync --locked --all-groups" in readme
    assert "every fallback attempt" in readme.lower()
    assert "never regenerates" in readme.lower()


def _assert_doc_delegates_strict_sync_to_authoritative_orchestrator(label, document):
    step_zero = document.split("Step 0", 1)[1].split("Step 1", 1)[0]
    assert "uv sync --locked --all-groups" not in step_zero, (
        f"{label} must not present a bare root sync as mirror fallback"
    )
    for required in (
        "scripts\\reproduce.ps1",
        "-Profile",
        "environment.python",
        "Invoke-UvCatalogSync",
        "mirrors.json",
        "locks\\manifest.json",
    ):
        assert required in document, f"{label} omits authoritative sync detail: {required}"


def test_readme_delegates_strict_sync_to_authoritative_orchestrator():
    _assert_doc_delegates_strict_sync_to_authoritative_orchestrator(
        "README", (ROOT / "README.md").read_text(encoding="utf-8")
    )


def test_agents_delegates_strict_sync_to_authoritative_orchestrator():
    _assert_doc_delegates_strict_sync_to_authoritative_orchestrator(
        "AGENTS", (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    )


def test_documented_orchestrator_really_consumes_mirrors_and_catalog():
    reproduce = (ROOT / "scripts" / "reproduce.ps1").read_text(encoding="utf-8")
    mirrors_stage = reproduce.index('Invoke-Stage -Id "environment.mirrors"')
    python_stage = reproduce.index('Invoke-Stage -Id "environment.python"')
    assert mirrors_stage < python_stage
    python_block = reproduce[python_stage : reproduce.index(
        'Invoke-Stage -Id "environment.wsl"', python_stage
    )]
    for required in (
        "Invoke-UvCatalogSync -RepoRoot $rootDir",
        "-ManifestPath $uvLockManifestPath",
        "-MirrorsPath $mirrorsJsonPath",
        '-VenvPath (Join-Path $rootDir ".venv")',
        "-EvidencePath $environmentLockFile",
    ):
        assert required in python_block


def test_pitfall_matching_source_check_is_child_process_environment_isolated():
    pitfalls = (ROOT / "docs" / "pitfalls.md").read_text(encoding="utf-8")
    block = pitfalls.split('<a id="uv-lock-mirror-mismatch"></a>', 1)[1].split(
        '<a id="wsl"></a>', 1
    )[0]
    assert "powershell -NoProfile" in block
    controlled = (
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
    for name in controlled:
        assert f'"{name}"' in block
    assert 'Remove-Item -LiteralPath "Env:$name"' in block
    assert block.index('Remove-Item -LiteralPath "Env:$name"') < block.index(
        "uv lock --check --no-config --project"
    )
    for source_id, lock_path, url in (
        ("pypi", "uv.lock", "https://pypi.org/simple"),
        ("tuna", "locks\\uv.tuna.lock", "https://pypi.tuna.tsinghua.edu.cn/simple"),
        ("aliyun", "locks\\uv.aliyun.lock", "https://mirrors.aliyun.com/pypi/simple"),
    ):
        assert f'id = "{source_id}"' in block
        assert f'lock = "{lock_path}"' in block
        assert f'url = "{url}"' in block
    assert "[IO.Path]::GetTempPath()" in block
    assert 'Copy-Item -LiteralPath "pyproject.toml"' in block
    assert 'Copy-Item -LiteralPath $source.lock -Destination (Join-Path $checkRoot "uv.lock")' in block
    assert "uv lock --check --no-config --project $checkRoot --default-index $source.url" in block
    assert "never replaces the repository-root" in block
