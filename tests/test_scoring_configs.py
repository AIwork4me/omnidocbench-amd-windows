"""Guard: every -Config xxx.yaml referenced in README/AGENTS must exist."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "eval-infra" / "01-omnidocbench" / "configs"


def test_referenced_configs_exist():
    refs = set()
    for name in ("README.md", "README.zh-CN.md", "AGENTS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        refs |= set(re.findall(r"-Config\s+([A-Za-z0-9_.-]+\.yaml)", text))
        refs |= set(re.findall(r"configs[\\/]([A-Za-z0-9_.-]+\.yaml)", text))
    assert refs, "no config references found"
    missing = [r for r in sorted(refs) if not (CONFIG_DIR / r).is_file()]
    assert not missing, f"referenced configs missing: {missing}"
