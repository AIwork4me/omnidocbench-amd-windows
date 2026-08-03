"""Fake integration harness for the reproduction orchestrator.

Builds a self-contained fake machine (git repo root + fake profile + fake
scoring configs) and a hooks directory of fake external scripts. With the
REPRO_* environment variables set, scripts/reproduce.ps1 runs its REAL state
machine end-to-end while every external tool (uv, wsl, dataset download, VLM
server, scorer) is a deterministic fake. No network, models or GPU required.

The fake scripts read <hooks>/behavior.json for scripted outcomes, and append
one line per invocation to <hooks>/<stage>.marker.log so tests can assert
execution order and re-run counts.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BEHAVIOR = {
    "dataset_pages": 10,
    "empty_gt_stems": [],
    "pipeline_deps_fail": False,
    "save_name": "fake_model_quick_match",
    "adapter": {
        "exit_code": 0,
        "fail_stems": [],
        "force_rewrite_stems": [],
        "content": "v1",
    },
    "win_result": {
        "text_edit_distance_page_avg": 0.03,
        "reading_order_edit_distance_page_avg": 0.13,
        "table_teds_pooled": 0.94,
        "table_teds_page_avg": 0.94,
        "formula_cdm": 0.97,
        "page_count": 10,
        "timeout_case_count": 0,
        "error_case_count": 0,
        "quick_match_timeout": 0,
        "page_timeout": 0,
    },
    "wsl_result": {
        "text_edit_distance_page_avg": 0.03,
        "reading_order_edit_distance_page_avg": 0.13,
        "table_teds_pooled": 0.94,
        "table_teds_page_avg": 0.94,
        "formula_cdm": 0.97,
        "page_count": 10,
        "timeout_case_count": 0,
        "error_case_count": 0,
        "quick_match_timeout": 0,
        "page_timeout": 0,
    },
}

_EXIT0 = "exit 0\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ps_exit0(name: str) -> None:
    _write(name, _EXIT0)


def _profile_json(
    name: str,
    *,
    run_kind: str,
    prediction_dir: str,
    prediction_manifest: str,
    owned_manifest: bool,
    expected_pages: int,
    max_pages: int | None,
    score_save_name: str,
    port: str,
    coverage: float,
    max_failed: int,
    allowed: list[str],
) -> dict:
    profile = {
        "schema_version": 1,
        "name": name,
        "description": f"fake harness {name}",
        "run_kind": run_kind,
        "model": "fake-model",
        "adapter": "fake-adapter",
        "engine": "lightweight",
        "variant": "cpu",
        "expected_pages": expected_pages,
        "max_pages": max_pages,
        "prediction_dir": prediction_dir,
        "prediction_manifest": prediction_manifest,
        "owned_manifest": owned_manifest,
        "windows_scoring_config": f"v16-{name}.yaml",
        "wsl_cdm_config": f"v16-cdm-{name}.yaml",
        "score_save_name": score_save_name,
        "server_port": port,
        "minimum_prediction_coverage": coverage,
        "maximum_failed_pages": max_failed,
        "require_gpu_backend_proof": False,
        "require_wsl_cdm": True,
        "metric_thresholds": {
            "text_edit_dist_max": 0.5,
            "reading_order_edit_dist_max": 0.5,
            "teds_min": 0.0,
            "cdm_min": 0.0,
        },
        "expected_runtime_class": "minutes",
        "max_timeout_cases": 8,
        "max_exception_cases": 4,
        "max_metric_error_cases": 8,
    }
    if allowed:
        profile["allowed_failed_page_stems"] = allowed
    return profile


def _scoring_config(pred_dir: str, manifest: str) -> str:
    return (
        "end2end_eval:\n"
        "  dataset:\n"
        '    prediction: {{ data_path: <REPO_ROOT>/{pred} }}\n'
        '    ground_truth: {{ data_path: <REPO_ROOT>/{man} }}\n'
        "    match_method: quick_match\n"
        "    match_workers: 1\n"
        "  metrics:\n"
        "    table:\n"
        "      teds_workers: 1\n"
    ).format(pred=pred_dir, man=manifest)


_FAKE_DATASET_SETUP = r"""
param()
$root = $env:REPRO_ROOT
$bh = Get-Content -Raw -Encoding UTF8 (Join-Path $env:REPRO_TEST_HOOKS "behavior.json") | ConvertFrom-Json
$pages = [int]$bh.dataset_pages
$empty = @($bh.empty_gt_stems)
$dataDir = Join-Path $root "eval-infra\01-omnidocbench\data"
New-Item -ItemType Directory -Force -Path (Join-Path $dataDir "images") | Out-Null
$manifest = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $pages; $i++) {
    $stem = "page-{0:D4}" -f $i
    $dets = @(@{ category_type = "text_block"; text = "gt text $stem" })
    if ($empty -contains $stem) { $dets = @(@{ category_type = "figure" }, @{ category_type = "text_mask"; text = "" }) }
    [void]$manifest.Add(@{ page_info = @{ image_path = "images/$stem.png" }; layout_dets = $dets })
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $dataDir "OmniDocBench.json"), ($manifest | ConvertTo-Json -Depth 8), $utf8)
for ($i = 0; $i -lt $pages; $i++) {
    $f = Join-Path $dataDir ("images\page-{0:D4}.png" -f $i)
    if (-not (Test-Path -LiteralPath $f)) { [System.IO.File]::WriteAllBytes($f, [byte[]](0x89, 0x50)) }
}
$checkout = Join-Path $root "eval-infra\01-omnidocbench\OmniDocBench"
New-Item -ItemType Directory -Force -Path $checkout | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $checkout ".git"))) {
    git -C $checkout init -q
    git -C $checkout -c user.name=fake -c user.email=fake@example.com commit -q -m seed --allow-empty
}
exit 0
"""

_FAKE_PIPELINE_DEPS = r"""
param([string] $CloneDir)
$bh = Get-Content -Raw -Encoding UTF8 (Join-Path $env:REPRO_TEST_HOOKS "behavior.json") | ConvertFrom-Json
if ($bh.pipeline_deps_fail) { Write-Host "FAKE: pipeline deps failing as scripted"; exit 1 }
New-Item -ItemType Directory -Force -Path $CloneDir | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $CloneDir ".git"))) {
    git -C $CloneDir init -q
    git -C $CloneDir -c user.name=fake -c user.email=fake@example.com commit -q -m seed --allow-empty
}
exit 0
"""

_FAKE_ADAPTER = r"""
import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--img-dir")
    parser.add_argument("--out-dir")
    parser.add_argument("--server-url")
    parser.add_argument("--gt-manifest")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    behavior: dict = {}
    hooks = os.environ.get("REPRO_TEST_HOOKS", "")
    if hooks:
        bp = Path(hooks) / "behavior.json"
        if bp.is_file():
            behavior = json.loads(bp.read_text(encoding="utf-8"))
    adapter = behavior.get("adapter", {})
    fail_stems = set(adapter.get("fail_stems", []))
    rewrite = set(adapter.get("force_rewrite_stems", []))
    content = str(adapter.get("content", "v1"))

    pages = json.loads(Path(args.gt_manifest).read_text(encoding="utf-8"))
    if args.max_pages:
        pages = pages[: args.max_pages]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stats = {
        "schema_version": 2,
        "selected_pages": 0,
        "count": len(pages),
        "ok": 0,
        "fail": 0,
        "newly_processed": 0,
        "skipped_existing": 0,
        "pages": {},
        "failed_pages": [],
        "invocations": [],
    }
    for page in pages:
        stem = Path(page["page_info"]["image_path"]).stem
        md = out / f"{stem}.md"
        empty_gt = True
        for det in page.get("layout_dets") or []:
            if det.get("ignore"):
                continue
            if any(str(det.get(f, "") or "").strip() for f in ("text", "html", "latex", "content")):
                empty_gt = False
                break
        if stem in fail_stems:
            stats["fail"] += 1
            stats["failed_pages"].append(f"{stem}.png")
            stats["pages"][f"{stem}.png"] = {"status": "failed: simulated", "seconds": 0.0, "source": "fresh"}
            continue
        if md.is_file() and args.skip_existing and stem not in rewrite:
            stats["skipped_existing"] += 1
            stats["pages"][f"{stem}.png"] = {"status": "ok", "seconds": 0.0, "source": "resumed"}
            continue
        body = "" if empty_gt else f"prediction for {stem} {content}\n"
        tmp = md.with_name(md.name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(md)
        stats["newly_processed"] += 1
        stats["pages"][f"{stem}.png"] = {"status": "ok", "seconds": 0.0, "source": "fresh"}
    stats["selected_pages"] = len(pages)
    stats["ok"] = stats["count"] - stats["fail"]
    (out / "_run_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    sys.exit(int(adapter.get("exit_code", 0)))


main()
"""

_RESULT_PS = r"""
param([string] $Config)
$root = $env:REPRO_ROOT
$bh = Get-Content -Raw -Encoding UTF8 (Join-Path $env:REPRO_TEST_HOOKS "behavior.json") | ConvertFrom-Json
$cfg = $bh.win_result
$save = [string]$bh.save_name
$resultDir = Join-Path $root "eval-infra\01-omnidocbench\OmniDocBench\result"
New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
$result = [ordered]@{
    text_block = @{ all = @{ Edit_dist = @{ ALL_page_avg = $cfg.text_edit_distance_page_avg } } }
    reading_order = @{ all = @{ Edit_dist = @{ ALL_page_avg = $cfg.reading_order_edit_distance_page_avg } } }
    table = @{
        all = @{ TEDS = @{ all = $cfg.table_teds_pooled } }
        page = @{ TEDS = @{ ALL = $cfg.table_teds_page_avg } }
        metric_debug = @{ TEDS = @{ timeout_case_count = [int]$cfg.timeout_case_count; error_case_count = [int]$cfg.error_case_count; timeout_cases = @(); error_cases = @() } }
    }
    display_formula = @{ all = @{ CDM = @{ all = $cfg.formula_cdm } } }
    match_debug = @{
        page_count = [int]$cfg.page_count
        text_match_fallback_counts = @{ quick_match_timeout = [int]$cfg.quick_match_timeout; page_timeout = [int]$cfg.page_timeout }
    }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $resultDir "${save}_metric_result.json"), ($result | ConvertTo-Json -Depth 10), $utf8)
Add-Content -LiteralPath (Join-Path $env:REPRO_TEST_HOOKS "score.marker.log") -Value ("{0} windows" -f (Get-Date).ToUniversalTime().ToString("o"))
exit 0
"""

_WSL_SHIM = r"""
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Rest)
$root = $env:REPRO_ROOT
$argsText = @($Rest) -join " "
if ($argsText -match "score-cdm\.sh") {
    $predDir = @($Rest)[-1]
    $save = (Split-Path $predDir -Leaf) + "_quick_match"
    $bh = Get-Content -Raw -Encoding UTF8 (Join-Path $env:REPRO_TEST_HOOKS "behavior.json") | ConvertFrom-Json
    $cfg = $bh.wsl_result
    $result = [ordered]@{
        text_block = @{ all = @{ Edit_dist = @{ ALL_page_avg = $cfg.text_edit_distance_page_avg } } }
        reading_order = @{ all = @{ Edit_dist = @{ ALL_page_avg = $cfg.reading_order_edit_distance_page_avg } } }
        table = @{
            all = @{ TEDS = @{ all = $cfg.table_teds_pooled } }
            page = @{ TEDS = @{ ALL = $cfg.table_teds_page_avg } }
            metric_debug = @{ TEDS = @{ timeout_case_count = [int]$cfg.timeout_case_count; error_case_count = [int]$cfg.error_case_count; timeout_cases = @(); error_cases = @() } }
        }
        display_formula = @{ all = @{ CDM = @{ all = $cfg.formula_cdm } } }
        match_debug = @{
            page_count = [int]$cfg.page_count
            text_match_fallback_counts = @{ quick_match_timeout = [int]$cfg.quick_match_timeout; page_timeout = [int]$cfg.page_timeout }
        }
    }
    $dir = $env:REPRO_WSL_RESULT_DIR
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $dir "${save}_metric_result.json"), ($result | ConvertTo-Json -Depth 10), $utf8)
    Add-Content -LiteralPath (Join-Path $env:REPRO_TEST_HOOKS "score.marker.log") -Value ("{0} wsl" -f (Get-Date).ToUniversalTime().ToString("o"))
    exit 0
} elseif ($argsText -match "wslpath") {
    Write-Output "/mnt/fake"
    exit 0
}
exit 0
"""

_FAKE_VERIFY_PS1 = r"""
param([switch] $WindowsOnly, [switch] $WslOnly, [switch] $RequireCdm, [string] $SaveName)
$root = $env:REPRO_ROOT
if ($WindowsOnly) {
    $win = Join-Path $root ("eval-infra\01-omnidocbench\OmniDocBench\result\" + $SaveName + "_metric_result.json")
    if (-not (Test-Path -LiteralPath $win)) { exit 1 }
}
if ($WslOnly) {
    $wsl = Join-Path $env:REPRO_WSL_RESULT_DIR ($SaveName + "_metric_result.json")
    if (-not (Test-Path -LiteralPath $wsl)) { exit 1 }
}
exit 0
"""

_FAKE_FULL_VERIFY = r"""
param([string] $PredictionDir, [string] $PredictionManifest, [string] $ScoreSaveName, [int] $ExpectedPages = 0, [switch] $RequireRunStatsSelected, [string[]] $AllowedFailedPageStem = @())
exit 0
"""

_FAKE_VERIFY_DATASET_TREE = "import sys\nsys.exit(0)\n"


def build_harness(
    tmp_path: Path,
    *,
    profile: str = "smoke",
    behavior: dict | None = None,
) -> dict:
    """Create a fake machine root + hooks dir. Returns env-var overrides."""
    root = tmp_path / "fake_root"
    hooks = tmp_path / "hooks"
    wsl_results = tmp_path / "wsl_results"

    # --- fake root git repo ------------------------------------------------
    root.mkdir(parents=True)
    (root / ".gitignore").write_text(
        "fp.json\noutputs/\npredictions/\nmirrors.env\n.env.local\nlogs/\n"
        "eval-infra/01-omnidocbench/data/\n"
        "eval-infra/01-omnidocbench/OmniDocBench/\n",
        encoding="utf-8",
    )
    profiles_dir = root / "scripts" / "profiles"
    configs_dir = root / "eval-infra" / "01-omnidocbench" / "configs"
    profiles_dir.mkdir(parents=True)
    configs_dir.mkdir(parents=True)

    if profile == "smoke":
        prof = _profile_json(
            "harness-smoke",
            run_kind="smoke",
            prediction_dir="outputs/harness/predictions/fake_model",
            prediction_manifest="outputs/harness/manifests/harness-smoke.json",
            owned_manifest=True,
            expected_pages=10,
            max_pages=10,
            score_save_name="fake_model_quick_match",
            port="8765",
            coverage=1.0,
            max_failed=0,
            allowed=[],
        )
    else:
        prof = _profile_json(
            "harness-full",
            run_kind="full",
            prediction_dir="outputs/harness/predictions/fake_full",
            prediction_manifest="eval-infra/01-omnidocbench/data/OmniDocBench.json",
            owned_manifest=False,
            expected_pages=1651,
            max_pages=None,
            score_save_name="fake_full_quick_match",
            port="8766",
            coverage=0.998,
            max_failed=2,
            allowed=["page-0000", "page-0001"],
        )
    effective_behavior = {
        "dataset_pages": prof["expected_pages"],
        "save_name": prof["score_save_name"],
        "win_result": {"page_count": prof["expected_pages"]},
        "wsl_result": {"page_count": prof["expected_pages"]},
    }
    if behavior:
        for key, value in behavior.items():
            if isinstance(value, dict) and isinstance(effective_behavior.get(key), dict):
                effective_behavior[key].update(value)
            else:
                effective_behavior[key] = value
    (profiles_dir / f"{prof['name']}.profile.json").write_text(
        json.dumps(prof, indent=2), encoding="utf-8"
    )
    (configs_dir / f"v16-{prof['name']}.yaml").write_text(
        _scoring_config(prof["prediction_dir"], prof["prediction_manifest"]),
        encoding="utf-8",
    )
    (configs_dir / f"v16-cdm-{prof['name']}.yaml").write_text(
        _scoring_config(prof["prediction_dir"], prof["prediction_manifest"]),
        encoding="utf-8",
    )
    shutil.copy2(REPO_ROOT / "upstream-lock.json", root / "upstream-lock.json")
    shutil.copy2(REPO_ROOT / "uv.lock", root / "uv.lock")

    # The fake adapter declares its full lifecycle through the same manifest
    # contract real adapters use. Written BEFORE the seed commit so the fake
    # tree stays clean for the formal --check-clean gate.
    fake_manifest = {
        "contract_version": 1,
        "name": "fake-adapter",
        "maturity": "experimental",
        "supported_platforms": ["windows"],
        "python_runtime_policy": "3.11",
        "lifecycle": {
            "server_setup": "adapters/fake-adapter/01-vlm-server/setup.ps1",
            "server_verify": "adapters/fake-adapter/01-vlm-server/verify.ps1",
            "backend_proof_capable": False,
            "layout_setup": "adapters/fake-adapter/02-layout-model/setup.ps1",
            "layout_verify": "adapters/fake-adapter/02-layout-model/verify.ps1",
            "install_deps": "adapters/fake-adapter/00-install-deps/setup.ps1",
            "inference_entrypoint": "adapters/fake-adapter/run_adapter.py",
            "verify_script": "",
            "resume_support": True,
        },
        "output_contract": {
            "markdown_per_page": True,
            "utf8": True,
            "stats_file": "_run_stats.json",
        },
        "required_env_vars": [],
        "human_intervention_gates": [],
    }
    fake_adapter_dir = root / "adapters" / "fake-adapter"
    fake_adapter_dir.mkdir(parents=True)
    (fake_adapter_dir / "adapter.json").write_text(
        json.dumps(fake_manifest, indent=2), encoding="utf-8"
    )

    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "-A"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=fake", "-c", "user.email=fake@example.com",
         "commit", "-q", "-m", "seed"],
        check=True,
        capture_output=True,
    )

    # --- hooks dir ----------------------------------------------------------
    hooks.mkdir(parents=True)
    (hooks / "behavior.json").write_text(
        json.dumps(_merge_behavior(effective_behavior), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for rel in (
        "scripts/wsl-ensure.ps1",
        "scripts/detect-mirrors.ps1",
        "scripts/preflight.ps1",
        "scripts/seed-locked-inputs.ps1",
        "scripts/verify-upstream-lock.ps1",
        "eval-infra/01-omnidocbench/verify.ps1",
        "adapters/fake-adapter/01-vlm-server/setup.ps1",
        "adapters/fake-adapter/01-vlm-server/verify.ps1",
        "adapters/fake-adapter/02-layout-model/setup.ps1",
        "adapters/fake-adapter/02-layout-model/verify.ps1",
    ):
        _ps_exit0(hooks / rel)
    _write(hooks / "eval-infra/01-omnidocbench/setup.ps1", _FAKE_DATASET_SETUP)
    _write(hooks / "adapters/fake-adapter/00-install-deps/setup.ps1", _FAKE_PIPELINE_DEPS)
    _write(hooks / "adapters/fake-adapter/run_adapter.py", _FAKE_ADAPTER)
    _write(hooks / "eval-infra/03-scoring/score.ps1", _RESULT_PS)
    _write(hooks / "eval-infra/03-scoring/verify.ps1", _FAKE_VERIFY_PS1)
    _write(hooks / "scripts/full-verify.ps1", _FAKE_FULL_VERIFY)
    _write(hooks / "scripts/verify_dataset_tree.py", _FAKE_VERIFY_DATASET_TREE)
    _write(hooks / "wsl.ps1", _WSL_SHIM)
    _write(hooks / "uv.ps1", "exit 0\n")

    env = {
        "REPRO_ROOT": str(root),
        "REPRO_PROFILE_DIR": str(profiles_dir),
        "REPRO_CONFIG_DIR": str(configs_dir),
        "REPRO_TEST_HOOKS": str(hooks),
        "REPRO_WSL_RESULT_DIR": str(wsl_results),
        "REPRO_TEST_PYTHON": str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "python.exe"),
    }
    return {
        "root": root,
        "hooks": hooks,
        "wsl_results": wsl_results,
        "env": env,
        "profile": prof,
    }


def _merge_behavior(behavior: dict | None) -> dict:
    merged = json.loads(json.dumps(DEFAULT_BEHAVIOR))
    if not behavior:
        return merged
    for key, value in behavior.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def set_behavior(hooks: Path, behavior: dict) -> None:
    current = json.loads((hooks / "behavior.json").read_text(encoding="utf-8"))
    for key, value in behavior.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            current[key].update(value)
        else:
            current[key] = value
    (hooks / "behavior.json").write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def score_marker_count(hooks: Path) -> int:
    marker = hooks / "score.marker.log"
    if not marker.is_file():
        return 0
    return len(marker.read_text(encoding="utf-8").splitlines())
