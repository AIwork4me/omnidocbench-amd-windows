"""Executable PowerShell tests for owned-artifact resolution and scoped reset.

These tests execute the REAL repro-profiles.ps1 / repro-evidence.ps1 functions
(no string assertions): Resolve-ProfileArtifacts must produce every owned path
a run may create or delete, and Reset-ReproProfileArtifacts must remove exactly
the current profile's artifacts while tolerating missing ones.
"""
from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.win32


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES = REPO_ROOT / "scripts" / "repro-profiles.ps1"
EVIDENCE = REPO_ROOT / "scripts" / "repro-evidence.ps1"


def run_ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )


def ps_json(script: str):
    result = run_ps(script)
    assert result.returncode == 0, result.stdout + result.stderr
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"PS output is not JSON: {error}\nSTDOUT: {result.stdout[:2000]}\nSTDERR: {result.stderr[:2000]}"
        ) from error


def test_artifact_resolution_covers_every_owned_path(tmp_path):
    data = ps_json(
        r"""
        . '{profiles}'
        . '{evidence}'
        $profile = Get-ReproProfile -Name "cpu-smoke-10"
        $artifacts = Resolve-ProfileArtifacts -Profile $profile -RootDir '{root}'
        [pscustomobject]@{{
            state_file = $artifacts.StateFile
            fingerprint = $artifacts.FingerprintFile
            inference_fingerprint = $artifacts.InferenceFingerprintFile
            scoring_fingerprint = $artifacts.ScoringFingerprintFile
            evidence_fingerprint = $artifacts.EvidenceFingerprintFile
            prediction_summary = $artifacts.PredictionSummaryFile
            prediction_tree = $artifacts.PredictionTreeFile
            windows_result = $artifacts.WindowsResult
            windows_provenance = $artifacts.WindowsProvenance
            wsl_result = $artifacts.WslResult
            wsl_provenance = $artifacts.WslProvenance
            prediction_dir = $artifacts.PredictionDir
            manifest = $artifacts.Manifest
            full_manifest = $artifacts.FullManifest
            save_name = $artifacts.SaveName
        }} | ConvertTo-Json
        """.format(profiles=PROFILES, evidence=EVIDENCE, root=tmp_path)
    )
    assert data["save_name"] == "paddleocrvl_cpu_smoke_10_quick_match"
    assert data["prediction_dir"].endswith("predictions\\paddleocrvl_cpu_smoke_10")
    assert data["state_file"].endswith("outputs\\reproduction\\cpu-smoke-10\\state.json")
    assert data["fingerprint"].endswith("fingerprint.json")
    assert data["inference_fingerprint"].endswith("fingerprint.inference.json")
    assert data["windows_provenance"].endswith(
        "paddleocrvl_cpu_smoke_10_quick_match_metric_result.provenance.json"
    )
    assert data["windows_result"].endswith("_metric_result.json")
    assert data["wsl_result"]  # UNC or test override; never empty
    assert data["manifest"].endswith("OmniDocBench_cpu_smoke_10.json")
    assert data["full_manifest"].endswith("data\\OmniDocBench.json")


def _reset_script(
    tmp_path: Path,
    *,
    with_fingerprint: bool,
    with_prediction_dir: bool,
    with_owned_manifest: bool,
    with_scores: bool,
) -> str:
    t = tmp_path
    (t / "foreign").mkdir(parents=True, exist_ok=True)
    (t / "winres").mkdir(parents=True, exist_ok=True)
    (t / "wslres").mkdir(parents=True, exist_ok=True)
    files = []
    if with_fingerprint:
        files.append("fingerprint.json")
    if with_prediction_dir:
        (t / "owned").mkdir(parents=True, exist_ok=True)
        (t / "owned" / "a.md").write_text("a", encoding="utf-8")
    if with_owned_manifest:
        (t / "owned").mkdir(parents=True, exist_ok=True)
        (t / "owned" / "manifest.json").write_text("{}", encoding="utf-8")
    if with_scores:
        (t / "winres" / "fake_quick_match_metric_result.json").write_text("{}", encoding="utf-8")
        (t / "winres" / "fake_quick_match_metric_result.provenance.json").write_text("{}", encoding="utf-8")
        (t / "wslres" / "fake_quick_match_metric_result.json").write_text("{}", encoding="utf-8")
    # Foreign artifacts must always survive.
    (t / "foreign" / "b.md").write_text("b", encoding="utf-8")
    (t / "winres" / "foreign_quick_match_metric_result.json").write_text("{}", encoding="utf-8")
    return r"""
        . '{profiles}'
        . '{evidence}'
        $profile = [pscustomobject]@{{
            name = "fake"
            owned_manifest = $true
            score_save_name = "fake_quick_match"
            SaveName = "fake_quick_match"
        }}
        $artifacts = [pscustomobject]@{{
            EvidenceDir = '{ev}'
            StateFile = '{ev}\state.json'
            FingerprintFile = '{ev}\fingerprint.json'
            InferenceFingerprintFile = '{ev}\fingerprint.inference.json'
            ScoringFingerprintFile = '{ev}\fingerprint.scoring.json'
            EvidenceFingerprintFile = '{ev}\fingerprint.evidence.json'
            PredictionSummaryFile = '{ev}\prediction-summary.json'
            PredictionTreeFile = '{ev}\prediction-tree.json'
            BackendProofFile = '{ev}\backend-proof.json'
            WindowsResult = '{t}\winres\fake_quick_match_metric_result.json'
            WindowsProvenance = '{t}\winres\fake_quick_match_metric_result.provenance.json'
            WslResult = '{t}\wslres\fake_quick_match_metric_result.json'
            WslProvenance = '{t}\wslres\fake_quick_match_metric_result.provenance.json'
            PredictionDir = '{t}\owned'
            PredictionRel = 'outputs\fake'
            Manifest = '{t}\owned\manifest.json'
            ManifestRel = 'outputs\fake.json'
            FullManifest = '{t}\full.json'
            PipelineCheckout = '{t}\checkout'
            SaveName = 'fake_quick_match'
            WindowsResultDir = '{t}\winres'
            WslResultDir = '{t}\wslres'
        }}
        $removed = @(Reset-ReproProfileArtifacts -Profile $profile -Artifacts $artifacts)
        [pscustomobject]@{{
            removed_count = $removed.Count
            owned_exists = Test-Path -LiteralPath '{t}\owned'
            foreign_exists = Test-Path -LiteralPath '{t}\foreign\b.md'
            foreign_score_exists = Test-Path -LiteralPath '{t}\winres\foreign_quick_match_metric_result.json'
            fingerprint_exists = Test-Path -LiteralPath '{ev}\fingerprint.json'
            win_score_exists = Test-Path -LiteralPath '{t}\winres\fake_quick_match_metric_result.json'
            wsl_score_exists = Test-Path -LiteralPath '{t}\wslres\fake_quick_match_metric_result.json'
        }} | ConvertTo-Json
        """.format(
        profiles=PROFILES, evidence=EVIDENCE,
        t=t, ev=t / "ev",
    )


def test_reset_with_no_artifacts_is_a_noop(tmp_path):
    data = ps_json(_reset_script(tmp_path, with_fingerprint=False, with_prediction_dir=False, with_owned_manifest=False, with_scores=False))
    assert data["removed_count"] == 0
    assert data["owned_exists"] is False
    assert data["foreign_exists"] is True


def test_reset_with_fingerprint_only_removes_it(tmp_path):
    data = ps_json(_reset_script(tmp_path, with_fingerprint=True, with_prediction_dir=False, with_owned_manifest=False, with_scores=False))
    assert data["fingerprint_exists"] is False
    assert data["foreign_exists"] is True


def test_reset_removes_predictions_manifest_and_scores(tmp_path):
    data = ps_json(_reset_script(tmp_path, with_fingerprint=True, with_prediction_dir=True, with_owned_manifest=True, with_scores=True))
    assert data["owned_exists"] is False
    assert data["win_score_exists"] is False
    assert data["wsl_score_exists"] is False
    assert data["foreign_exists"] is True
    assert data["foreign_score_exists"] is True
    assert data["removed_count"] >= 3


def test_reset_without_prediction_dir_does_not_fail(tmp_path):
    data = ps_json(_reset_script(tmp_path, with_fingerprint=True, with_prediction_dir=False, with_owned_manifest=True, with_scores=True))
    assert data["removed_count"] >= 2
    assert data["foreign_exists"] is True


def _artifact_hash_script(tmp_path: Path, environment_lock: Path) -> str:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    required = {
        "profile": tmp_path / "profile.json",
        "upstream": tmp_path / "upstream-lock.json",
        "manifest": tmp_path / "manifest.json",
        "windows_config": tmp_path / "windows.yaml",
        "wsl_config": tmp_path / "wsl.yaml",
    }
    for path in required.values():
        path.write_text("{}\n", encoding="utf-8")
    return r"""
        . '{evidence}'
        $script:ReproRoot = '{root}'
        $profile = [pscustomobject]@{{
            ProfilePath = '{profile}'
            ManifestAbs = '{manifest}'
            ConfigWindowsAbs = '{windows_config}'
            ConfigWslAbs = '{wsl_config}'
            PredictionDirAbs = '{predictions}'
            server_port = '8765'
        }}
        New-Item -ItemType Directory -Force -Path '{predictions}' | Out-Null
        $null = Write-ArtifactHashes -EvidenceDir '{evidence_dir}' `
            -Profile $profile -PipelineCheckout '{checkout}' -EnvFile '{env_file}' `
            -EnvironmentLockFile '{environment_lock}'
        Get-Content -Raw -Encoding UTF8 -LiteralPath '{artifact_hashes}'
        """.format(
        evidence=EVIDENCE,
        root=tmp_path,
        profile=required["profile"],
        manifest=required["manifest"],
        windows_config=required["windows_config"],
        wsl_config=required["wsl_config"],
        predictions=tmp_path / "predictions",
        evidence_dir=evidence_dir,
        checkout=tmp_path / "checkout",
        env_file=tmp_path / "adapter.env",
        environment_lock=environment_lock,
        artifact_hashes=evidence_dir / "artifact-hashes.json",
    )


def test_artifact_hashes_bind_exact_environment_lock_bytes(tmp_path):
    environment_lock = tmp_path / "evidence" / "environment-lock.json"
    environment_lock.parent.mkdir()
    exact_bytes = (
        b'{\r\n  "schema_version": 1,\r\n'
        b'  "selected_source_id": "tuna",\r\n'
        b'  "note": "exact bytes, not reserialized"\r\n}\r\n'
    )
    environment_lock.write_bytes(exact_bytes)

    hashes = ps_json(_artifact_hash_script(tmp_path, environment_lock))

    assert hashes["environment_lock"] == hashlib.sha256(exact_bytes).hexdigest()
    assert "selected_source_id" not in hashes
    assert "selected_index_url" not in hashes
    assert "selected_lock_sha256" not in hashes


def test_artifact_hashes_fail_closed_when_environment_lock_is_missing(tmp_path):
    missing = tmp_path / "evidence" / "environment-lock.json"

    result = run_ps(_artifact_hash_script(tmp_path, missing))

    assert result.returncode != 0
    assert "environment-lock" in result.stdout + result.stderr


def test_reproduce_passes_authoritative_environment_lock_to_artifact_hashes():
    text = (REPO_ROOT / "scripts" / "reproduce.ps1").read_text(encoding="utf-8")
    after_save = text.split('Invoke-Stage -Id "evidence.pack"', 1)[1].split(
        "fingerprint.evidence.spec.json", 1
    )[0]
    assert "-EnvironmentLockFile $environmentLockFile" in after_save
