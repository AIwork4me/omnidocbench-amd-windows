"""Reproduction profile catalog: schema, uniqueness, and binding invariants."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = REPO_ROOT / "scripts" / "profiles"
CONFIG_DIR = REPO_ROOT / "eval-infra" / "01-omnidocbench" / "configs"
REPRODUCE = REPO_ROOT / "scripts" / "reproduce.ps1"

REQUIRED_FIELDS = {
    "schema_version": int,
    "name": str,
    "description": str,
    "run_kind": str,
    "model": str,
    "adapter": str,
    "engine": str,
    "variant": str,
    "expected_pages": int,
    "max_pages": (int, type(None)),
    "prediction_dir": str,
    "prediction_manifest": str,
    "owned_manifest": bool,
    "windows_scoring_config": str,
    "wsl_cdm_config": str,
    "score_save_name": str,
    "server_port": str,
    "minimum_prediction_coverage": (int, float),
    "maximum_failed_pages": int,
    "require_gpu_backend_proof": bool,
    "require_wsl_cdm": bool,
    "metric_thresholds": dict,
    "expected_runtime_class": str,
}
THRESHOLD_KEYS = {
    "text_edit_dist_max",
    "reading_order_edit_dist_max",
    "teds_min",
    "cdm_min",
}
EXPECTED_PROFILES = {"cpu-smoke-10", "hip-smoke-10", "paddleocr-vl-hip-full-1651"}


def load_profiles() -> dict[str, dict]:
    profiles = {}
    for path in sorted(PROFILE_DIR.glob("*.profile.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        profiles[data["name"]] = data
    return profiles


def test_exactly_the_three_formal_profiles_exist():
    assert set(load_profiles()) == EXPECTED_PROFILES


def test_profile_schema_and_types():
    for name, profile in load_profiles().items():
        assert profile["schema_version"] == 1, name
        for field, types in REQUIRED_FIELDS.items():
            assert field in profile, f"{name}: missing {field}"
            assert isinstance(profile[field], types), f"{name}: {field} type"
        assert profile["run_kind"] in {"smoke", "subset", "full"}, name
        assert profile["variant"] in {"cpu", "hip"}, name
        assert 0.0 < profile["minimum_prediction_coverage"] <= 1.0, name
        assert profile["maximum_failed_pages"] >= 0, name
        assert set(profile["metric_thresholds"]) == THRESHOLD_KEYS, name
        for key, value in profile["metric_thresholds"].items():
            assert isinstance(value, (int, float)), f"{name}: {key}"
            assert 0.0 <= value <= 1.0, f"{name}: {key} must be raw 0-1 scale"
        for field in ("prediction_dir", "prediction_manifest"):
            value = profile[field]
            assert not re.match(r"^([A-Za-z]:[\\/]|/|\\\\)", value), f"{name}: {field} absolute"
            assert "\\" not in value, f"{name}: {field} must use forward slashes"
        assert profile["server_port"].isdigit(), name


def test_names_dirs_and_save_names_are_unique():
    profiles = load_profiles()
    dirs = [p["prediction_dir"] for p in profiles.values()]
    saves = [p["score_save_name"] for p in profiles.values()]
    ports = [p["server_port"] for p in profiles.values()]
    manifests = [p["prediction_manifest"] for p in profiles.values() if p["owned_manifest"]]
    assert len(dirs) == len(set(dirs))
    assert len(saves) == len(set(saves))
    assert len(ports) == len(set(ports))
    assert len(manifests) == len(set(manifests))


def test_save_name_matches_prediction_dir_basename():
    for name, profile in load_profiles().items():
        basename = profile["prediction_dir"].rstrip("/").split("/")[-1]
        assert profile["score_save_name"] == f"{basename}_quick_match", name


def test_hip_profiles_require_hip_variant_and_gpu_proof():
    for name in ("hip-smoke-10", "paddleocr-vl-hip-full-1651"):
        profile = load_profiles()[name]
        assert profile["variant"] == "hip", name
        assert profile["require_gpu_backend_proof"] is True, name


def test_full_profile_declares_exactly_1651_pages_without_max_pages():
    profile = load_profiles()["paddleocr-vl-hip-full-1651"]
    assert profile["run_kind"] == "full"
    assert profile["expected_pages"] == 1651
    assert profile["max_pages"] is None
    assert profile["minimum_prediction_coverage"] >= 0.998
    assert profile["maximum_failed_pages"] <= 2
    assert profile["owned_manifest"] is False
    assert profile["prediction_manifest"].endswith("OmniDocBench.json")


def test_smoke_profiles_pin_ten_pages_and_full_coverage():
    for name in ("cpu-smoke-10", "hip-smoke-10"):
        profile = load_profiles()[name]
        assert profile["run_kind"] == "smoke", name
        assert profile["expected_pages"] == 10, name
        assert profile["max_pages"] == 10, name
        assert profile["minimum_prediction_coverage"] == 1.0, name
        assert profile["maximum_failed_pages"] == 0, name
        assert profile["owned_manifest"] is True, name


def test_scoring_configs_exist_and_bind_to_profile():
    for name, profile in load_profiles().items():
        for field in ("windows_scoring_config", "wsl_cdm_config"):
            config_path = CONFIG_DIR / profile[field]
            assert config_path.is_file(), f"{name}: missing {config_path.name}"
            dataset = yaml.safe_load(config_path.read_text(encoding="utf-8"))[
                "end2end_eval"
            ]["dataset"]
            prediction = dataset["prediction"]["data_path"]
            ground_truth = dataset["ground_truth"]["data_path"]
            assert prediction.rstrip("/").endswith(profile["prediction_dir"]), (
                f"{name}: {config_path.name} prediction dir mismatch: {prediction}"
            )
            manifest_name = profile["prediction_manifest"].split("/")[-1]
            assert ground_truth.endswith(manifest_name), (
                f"{name}: {config_path.name} ground truth mismatch: {ground_truth}"
            )
            assert dataset["match_method"] == "quick_match", name
        wsl_config = yaml.safe_load(
            (CONFIG_DIR / profile["wsl_cdm_config"]).read_text(encoding="utf-8")
        )
        cdm_metrics = wsl_config["end2end_eval"]["metrics"]["display_formula"]["metric"]
        assert "CDM" in cdm_metrics, f"{name}: WSL config must enable CDM"


def run_reproduce(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPRODUCE), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def test_list_profiles_outputs_three_rows():
    result = run_reproduce("-ListProfiles")
    assert result.returncode == 0, result.stdout + result.stderr
    for name in EXPECTED_PROFILES:
        assert name in result.stdout
    assert "hip" in result.stdout and "cpu" in result.stdout
    assert "1651" in result.stdout


def test_invalid_profile_fails_closed_and_lists_valid_ones():
    result = run_reproduce("-Profile", "no-such-profile", "-DryRun")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "no-such-profile" in output
    for name in EXPECTED_PROFILES:
        assert name in output


def test_dry_run_succeeds_for_all_profiles_without_side_effects():
    for name in EXPECTED_PROFILES:
        result = run_reproduce("-Profile", name, "-DryRun")
        assert result.returncode == 0, f"{name}: {result.stdout + result.stderr}"
        output = result.stdout
        profile = load_profiles()[name]
        assert profile["prediction_dir"] in output
        assert profile["score_save_name"] in output
        assert profile["windows_scoring_config"] in output
        assert profile["wsl_cdm_config"] in output
        assert "DRY RUN OK" in output
