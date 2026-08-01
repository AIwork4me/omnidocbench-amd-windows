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
