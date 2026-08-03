"""Guard: full-verify.ps1 keeps its documented parameter surface."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "full-verify.ps1"


def test_full_verify_documented_switches_exist():
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"param\s*\((.*?)\)", text, re.S)
    assert m, "param block not found"
    params = m.group(1)
    for switch in ("SkipWsl", "WindowsCdm", "SkipVlm"):
        assert f"${switch}" in params, f"param ${switch} missing from full-verify.ps1"


def test_full_verify_strict_acceptance_params_exist():
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"param\s*\((.*?)\)", text, re.S)
    params = m.group(1)
    for param in ("ExpectedPages", "MinCoverage", "MaxFailedPages", "RequireRunStatsSelected"):
        assert f"${param}" in params, f"param ${param} missing from full-verify.ps1"
    assert "verify_prediction_set.py" in text, "strict mode must delegate to verify_prediction_set.py"


def test_full_verify_defaults_preserve_legacy_heuristic():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "$ExpectedPages -gt 0" in text
    assert "$MaxFailedPages -ge 0" in text
    assert "0.95" in text  # legacy default coverage threshold
