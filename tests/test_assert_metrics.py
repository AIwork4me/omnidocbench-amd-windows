"""assert-metrics.ps1: metric sanity gates with profile thresholds."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "assert-metrics.ps1"
PROFILE = REPO_ROOT / "scripts" / "profiles" / "paddleocr-vl-hip-full-1651.profile.json"


def _metric_result(tmp_path, *, text=0.034, ro=0.129, teds=0.942393, cdm=0.965022):
    return {
        "text_block": {"all": {"Edit_dist": {"ALL_page_avg": text}}},
        "display_formula": {
            "all": {
                "Edit_dist": {"ALL_page_avg": ro},
                "CDM": {"all": cdm},
            }
        },
        "table": {"all": {"TEDS": {"all": teds}}},
        "reading_order": {"all": {"Edit_dist": {"ALL_page_avg": ro}}},
    }


def _run(tmp_path, *, payload, profile=PROFILE, not_older_than=None, require_cdm=False):
    result_path = tmp_path / "metric_result.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    args = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-MetricResult", str(result_path),
        "-Profile", str(profile),
    ]
    if require_cdm:
        args += ["-RequireCdm"]
    if not_older_than:
        args += ["-NotOlderThan", not_older_than]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def test_reference_values_pass_full_profile(tmp_path):
    result = _run(tmp_path, payload=_metric_result(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr


def test_nan_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["table"]["all"]["TEDS"]["all"] = float("nan")
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0


def test_infinite_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["text_block"]["all"]["Edit_dist"]["ALL_page_avg"] = float("inf")
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0


def test_negative_edit_dist_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"] = -0.01
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0


def test_missing_cdm_fails_full_profile(tmp_path):
    payload = _metric_result(tmp_path)
    del payload["display_formula"]["all"]["CDM"]
    result = _run(tmp_path, payload=payload, require_cdm=True)
    assert result.returncode != 0
    assert "CDM" in result.stdout


def test_missing_cdm_passes_when_not_required(tmp_path):
    payload = _metric_result(tmp_path)
    del payload["display_formula"]["all"]["CDM"]
    result = _run(tmp_path, payload=payload)
    assert result.returncode == 0, result.stdout + result.stderr


def test_zero_cdm_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["display_formula"]["all"]["CDM"]["all"] = 0.0
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0


def test_percentage_scale_teds_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["table"]["all"]["TEDS"]["all"] = 94.2393
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0
    assert "scale" in result.stdout.lower()


def test_percentage_scale_cdm_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["display_formula"]["all"]["CDM"]["all"] = 96.5022
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0
    assert "scale" in result.stdout.lower()


def test_threshold_violation_fails(tmp_path):
    payload = _metric_result(tmp_path)
    payload["table"]["all"]["TEDS"]["all"] = 0.1
    result = _run(tmp_path, payload=payload)
    assert result.returncode != 0
    assert "TEDS" in result.stdout


def test_stale_result_fails(tmp_path):
    result_path = tmp_path / "metric_result.json"
    result_path.write_text(json.dumps(_metric_result(tmp_path)), encoding="utf-8")
    # mtime in the past; NotOlderThan = now (in the future relative to file)
    import datetime

    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    result = _run(tmp_path, payload=_metric_result(tmp_path), not_older_than=future)
    assert result.returncode != 0
    assert "stale" in result.stdout.lower()


def test_fresh_result_passes_freshness(tmp_path):
    result = _run(tmp_path, payload=_metric_result(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
