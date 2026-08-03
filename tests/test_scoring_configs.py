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


def test_score_cdm_sh_raises_the_wsl_open_file_limit():
    """1651-page CDM runs exhaust WSL's default 1024-file limit (Errno 24)."""
    script = (ROOT / "eval-infra" / "03-scoring" / "score-cdm.sh").read_text(encoding="utf-8")
    assert "ulimit -n 65535" in script
