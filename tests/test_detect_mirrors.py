from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


pytestmark = pytest.mark.win32

REPO_ROOT = Path(__file__).resolve().parents[1]
DETECT_MIRRORS = REPO_ROOT / "scripts" / "detect-mirrors.ps1"

HF = "https://huggingface.co/api/datasets/opendatalab/OmniDocBench"
MS = "https://modelscope.cn/api/v1/datasets/OpenDataLab/OmniDocBench"
GITHUB = "https://github.com/opendatalab/OmniDocBench"
GH_PROXY = "https://ghproxy.net/https://github.com"
GH_FAST = "https://ghfast.top/https://github.com"
CTAN_USTC = "https://mirrors.ustc.edu.cn/CTAN/systems/texlive/tlnet"
CTAN_TUNA = "https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet"
CTAN_GLOBAL = "https://mirror.ctan.org/systems/texlive/tlnet"
PYPI = "https://pypi.org/simple"
TUNA = "https://pypi.tuna.tsinghua.edu.cn/simple"
ALIYUN = "https://mirrors.aliyun.com/pypi/simple"

UV_INDEXES = [
    {"id": "pypi", "url": PYPI, "priority": 0, "reachable": True},
    {"id": "tuna", "url": TUNA, "priority": 1, "reachable": True},
    {"id": "aliyun", "url": ALIYUN, "priority": 2, "reachable": True},
]


def all_up_fixture() -> dict[str, bool]:
    return {
        HF: True,
        MS: True,
        GITHUB: True,
        GH_PROXY: True,
        GH_FAST: True,
        CTAN_USTC: True,
        CTAN_TUNA: True,
        CTAN_GLOBAL: True,
        PYPI: True,
        TUNA: True,
        ALIYUN: True,
    }


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(DETECT_MIRRORS, scripts / DETECT_MIRRORS.name)
    return root


def run_detector(
    root: Path,
    fixture: dict[str, bool] | str,
    *,
    enable_hooks: bool = True,
    enable_fixture: bool = True,
) -> subprocess.CompletedProcess[str]:
    hooks = root / ".test-hooks"
    hooks.mkdir(exist_ok=True)
    fixture_path = root / "probe-results.json"
    if isinstance(fixture, str):
        fixture_path.write_text(fixture, encoding="utf-8")
    else:
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    env = os.environ.copy()
    env.pop("REPRO_TEST_HOOKS", None)
    env.pop("MIRROR_PROBE_RESULTS_JSON", None)
    if enable_hooks:
        env["REPRO_TEST_HOOKS"] = str(hooks)
    if enable_fixture:
        env["MIRROR_PROBE_RESULTS_JSON"] = str(fixture_path)

    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / DETECT_MIRRORS.name),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def read_contract(root: Path) -> tuple[dict[str, object], str]:
    raw = (root / "mirrors.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    document = json.loads(raw.decode("utf-8"))
    env_text = (root / "mirrors.env").read_text(encoding="utf-8-sig")
    return document, env_text


def assert_uv_contract(
    document: dict[str, object], *, status: str, reachable: list[bool]
) -> None:
    assert list(document) == ["schema_version", "network_status", "uv_indexes"]
    assert document["schema_version"] == 1
    assert type(document["schema_version"]) is int
    assert document["network_status"] == status

    expected = [dict(item) for item in UV_INDEXES]
    for item, is_reachable in zip(expected, reachable, strict=True):
        item["reachable"] = is_reachable
    assert document["uv_indexes"] == expected
    for item in document["uv_indexes"]:
        assert list(item) == ["id", "url", "priority", "reachable"]
        assert type(item["priority"]) is int
        assert type(item["reachable"]) is bool


def assert_no_temp_files(root: Path) -> None:
    assert not list(root.glob("mirrors.env.tmp.*"))
    assert not list(root.glob("mirrors.json.tmp.*"))


def test_all_sources_up_writes_exact_ordered_contract(tmp_path: Path):
    root = make_repo(tmp_path)

    result = run_detector(root, all_up_fixture())

    assert result.returncode == 0, result.stdout + result.stderr
    document, env_text = read_contract(root)
    assert_uv_contract(document, status="ok", reachable=[True, True, True])
    assert "PYPI_INDEX=https://pypi.org/simple\n" in env_text.replace("\r\n", "\n")
    assert "NETWORK_STATUS=ok\n" in env_text.replace("\r\n", "\n")
    assert_no_temp_files(root)


def test_pypi_down_tuna_up_selects_tuna_and_preserves_probe_results(tmp_path: Path):
    root = make_repo(tmp_path)
    fixture = all_up_fixture()
    fixture[PYPI] = False

    result = run_detector(root, fixture)

    assert result.returncode == 0, result.stdout + result.stderr
    document, env_text = read_contract(root)
    assert_uv_contract(document, status="ok", reachable=[False, True, True])
    assert "PYPI_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple" in env_text


def test_only_aliyun_up_selects_aliyun(tmp_path: Path):
    root = make_repo(tmp_path)
    fixture = all_up_fixture()
    fixture[PYPI] = False
    fixture[TUNA] = False

    result = run_detector(root, fixture)

    assert result.returncode == 0, result.stdout + result.stderr
    document, env_text = read_contract(root)
    assert_uv_contract(document, status="ok", reachable=[False, False, True])
    assert "PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple" in env_text


def test_all_pypi_sources_down_writes_degraded_contract(tmp_path: Path):
    root = make_repo(tmp_path)
    fixture = all_up_fixture()
    fixture[PYPI] = False
    fixture[TUNA] = False
    fixture[ALIYUN] = False

    result = run_detector(root, fixture)

    assert result.returncode == 0, result.stdout + result.stderr
    document, env_text = read_contract(root)
    assert_uv_contract(document, status="degraded", reachable=[False, False, False])
    assert "PYPI_INDEX=# UNREACHABLE (pypi.org and Tsinghua both down)" in env_text
    assert "NETWORK_STATUS=degraded" in env_text


def test_dataset_offline_writes_both_contracts_before_existing_exit(tmp_path: Path):
    root = make_repo(tmp_path)
    fixture = all_up_fixture()
    fixture[HF] = False
    fixture[MS] = False

    result = run_detector(root, fixture)

    assert result.returncode == 1, result.stdout + result.stderr
    document, env_text = read_contract(root)
    assert_uv_contract(document, status="offline", reachable=[True, True, True])
    assert "HF_OR_MS=# UNREACHABLE (HF + ModelScope dataset endpoints both down)" in env_text
    assert "PYPI_INDEX=https://pypi.org/simple" in env_text
    assert "NETWORK_STATUS=offline" in env_text
    assert_no_temp_files(root)


def test_malformed_probe_fixture_is_rejected(tmp_path: Path):
    root = make_repo(tmp_path)

    result = run_detector(root, "{ definitely-not-json")

    assert result.returncode != 0
    assert "MIRROR_PROBE_RESULTS_JSON" in result.stdout + result.stderr
    assert not (root / "mirrors.env").exists()
    assert not (root / "mirrors.json").exists()


def test_successive_runs_atomically_replace_both_contracts(tmp_path: Path):
    root = make_repo(tmp_path)
    first = all_up_fixture()
    first[PYPI] = False
    first[TUNA] = False
    first[ALIYUN] = False
    second = all_up_fixture()

    first_result = run_detector(root, first)
    second_result = run_detector(root, second)

    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    assert second_result.returncode == 0, second_result.stdout + second_result.stderr
    document, env_text = read_contract(root)
    assert_uv_contract(document, status="ok", reachable=[True, True, True])
    assert "PYPI_INDEX=https://pypi.org/simple" in env_text
    assert "UNREACHABLE (pypi.org and Tsinghua both down)" not in env_text
    assert_no_temp_files(root)


@pytest.mark.parametrize(
    ("enable_hooks", "enable_fixture"),
    [(False, True), (True, False)],
)
def test_fixture_injection_requires_both_production_guards(
    tmp_path: Path, enable_hooks: bool, enable_fixture: bool
):
    root = make_repo(tmp_path)

    result = run_detector(
        root,
        all_up_fixture(),
        enable_hooks=enable_hooks,
        enable_fixture=enable_fixture,
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "REPRO_TEST_HOOKS" in output
    assert "MIRROR_PROBE_RESULTS_JSON" in output
    assert not (root / "mirrors.env").exists()
    assert not (root / "mirrors.json").exists()
