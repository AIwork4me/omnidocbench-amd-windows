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


def test_readme_runs_detector_before_manual_strict_sync():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manual = readme.split("Manual phase-by-phase setup", 1)[1].split("# Step 1:", 1)[0]
    assert manual.index("scripts\\detect-mirrors.ps1") < manual.index(
        "uv sync --locked --all-groups"
    )
