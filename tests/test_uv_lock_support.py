from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest


pytestmark = pytest.mark.win32

REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPORT = REPO_ROOT / "scripts" / "uv-lock-support.ps1"
CONTROLLED = [
    "UV_INDEX",
    "UV_DEFAULT_INDEX",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_INDEX_STRATEGY",
    "UV_NO_INDEX",
    "UV_FIND_LINKS",
    "UV_CONFIG_FILE",
    "UV_NO_CONFIG",
    "UV_PROJECT_ENVIRONMENT",
]
SOURCES = [
    ("pypi", "https://pypi.org/simple", 0, "uv.lock"),
    ("tuna", "https://pypi.tuna.tsinghua.edu.cn/simple", 1, "locks/uv.tuna.lock"),
    ("aliyun", "https://mirrors.aliyun.com/pypi/simple", 2, "locks/uv.aliyun.lock"),
]


def ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(tmp_path: Path, body: str, *, env: dict[str, str] | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    driver = tmp_path / "driver.ps1"
    driver.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f". {ps_quote(SUPPORT)}\n"
        + body,
        encoding="utf-8",
    )
    process_env = os.environ.copy()
    if env is not None:
        for name in CONTROLLED:
            process_env.pop(name, None)
        process_env.update(env)
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(driver),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=process_env,
    )


def json_result(result: subprocess.CompletedProcess[str]) -> object:
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout + result.stderr
    return json.loads(lines[-1])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo with spaces"
    (root / "locks").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(REPO_ROOT / "uv.lock", root / "uv.lock")
    shutil.copy2(REPO_ROOT / "locks" / "uv.tuna.lock", root / "locks" / "uv.tuna.lock")
    shutil.copy2(REPO_ROOT / "locks" / "uv.aliyun.lock", root / "locks" / "uv.aliyun.lock")
    shutil.copy2(REPO_ROOT / "locks" / "manifest.json", root / "locks" / "manifest.json")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Uv Tests"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root


def mirrors_document(*, reachable: tuple[bool, bool, bool] = (True, True, True)) -> dict:
    return {
        "schema_version": 1,
        "network_status": "ok",
        "uv_indexes": [
            {"id": source_id, "url": url, "priority": priority, "reachable": is_reachable}
            for (source_id, url, priority, _), is_reachable in zip(SOURCES, reachable, strict=True)
        ],
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def read_function(tmp_path: Path, function: str, path: Path, repo_root: Path | None = None):
    repo_arg = "" if repo_root is None else f" -RepoRoot {ps_quote(repo_root)}"
    result = run_ps(
        tmp_path,
        f"$value = {function} -Path {ps_quote(path)}{repo_arg}\n"
        "$value | ConvertTo-Json -Depth 8 -Compress\n",
    )
    return result, json_result(result)


def invoke_sync(
    tmp_path: Path,
    root: Path,
    *,
    mirrors: dict | None = None,
    behavior: dict | None = None,
    inherited_env: dict[str, str] | None = None,
    preexisting_evidence: bytes | None = None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mirrors_path = tmp_path / "mirrors contract.json"
    write_json(mirrors_path, mirrors if mirrors is not None else mirrors_document())
    behavior_path = tmp_path / "behavior.json"
    write_json(behavior_path, behavior or {})
    runner_log = tmp_path / "uv runner.jsonl"
    verifier_log = tmp_path / "verifier.log"
    evidence = tmp_path / "evidence with spaces.json"
    if preexisting_evidence is not None:
        evidence.write_bytes(preexisting_evidence)
    venv = root / "venv with spaces"
    body = f"""
$script:Root = {ps_quote(root)}
$script:Behavior = Get-Content -Raw -Encoding UTF8 -LiteralPath {ps_quote(behavior_path)} | ConvertFrom-Json
$script:RunnerLog = {ps_quote(runner_log)}
$script:VerifierLog = {ps_quote(verifier_log)}
$script:Attempt = 0
function Get-TestEnvironmentState {{
    $all = [Environment]::GetEnvironmentVariables([EnvironmentVariableTarget]::Process)
    $state = [ordered]@{{}}
    foreach ($name in @({', '.join(ps_quote(name) for name in CONTROLLED)})) {{
        $state[$name] = [ordered]@{{
            present = $all.Contains($name)
            value = $(if ($all.Contains($name)) {{ [string]$all[$name] }} else {{ $null }})
        }}
    }}
    return $state
}}
$runner = {{
    param([string[]] $Arguments)
    $script:Attempt += 1
    $projectIndex = [Array]::IndexOf($Arguments, '--project')
    $indexIndex = [Array]::IndexOf($Arguments, '--default-index')
    $project = $Arguments[$projectIndex + 1]
    $url = $Arguments[$indexIndex + 1]
    $sourceId = @{{
        'https://pypi.org/simple' = 'pypi'
        'https://pypi.tuna.tsinghua.edu.cn/simple' = 'tuna'
        'https://mirrors.aliyun.com/pypi/simple' = 'aliyun'
    }}[$url]
    $entry = [ordered]@{{
        attempt = $script:Attempt
        source_id = $sourceId
        arguments = @($Arguments)
        project = $project
        project_files = @((Get-ChildItem -LiteralPath $project -Force | Sort-Object Name | ForEach-Object Name))
        environment = Get-TestEnvironmentState
    }}
    [IO.File]::AppendAllText($script:RunnerLog, (($entry | ConvertTo-Json -Depth 8 -Compress) + "`n"), (New-Object Text.UTF8Encoding($false)))
    $action = $script:Behavior.$sourceId
    if ($null -ne $action) {{
        if ([bool]$action.mutate_root_lock) {{ [IO.File]::AppendAllText((Join-Path $script:Root 'uv.lock'), "`nmutation") }}
        if ([bool]$action.mutate_worktree) {{ [IO.File]::WriteAllText((Join-Path $script:Root 'runner-mutation.txt'), 'mutation') }}
        if ([bool]$action.remove_project) {{ Remove-Item -LiteralPath $project -Recurse -Force }}
        if ([bool]$action.throw) {{ throw "runner throw for $sourceId" }}
        if ([bool]$action.multi_output) {{ Write-Output ([int]0); Write-Output ([int]1); return }}
        if ([bool]$action.host_diagnostic) {{ Write-Host "runner diagnostic for $sourceId" }}
        if ($null -ne $action.exit_code) {{ return [int]$action.exit_code }}
    }}
    return [int]0
}}
$verifier = {{
    param([string] $RepoRoot, [string] $ManifestPath)
    [IO.File]::WriteAllText($script:VerifierLog, "$RepoRoot|$ManifestPath")
    if ([bool]$script:Behavior.verifier_mutates) {{ [IO.File]::WriteAllText((Join-Path $RepoRoot 'verifier-mutation.txt'), 'mutation') }}
    if ([bool]$script:Behavior.verifier_throws) {{ throw 'verifier throw' }}
    if ([bool]$script:Behavior.verifier_multi_output) {{ Write-Output ([int]0); Write-Output ([int]1); return }}
    if ($null -ne $script:Behavior.verifier_code) {{ return [int]$script:Behavior.verifier_code }}
    return [int]0
}}
$caught = $null
$selected = $null
try {{
    $selected = Invoke-UvCatalogSync -RepoRoot {ps_quote(root)} -ManifestPath {ps_quote(root / 'locks' / 'manifest.json')} `
        -MirrorsPath {ps_quote(mirrors_path)} -VenvPath {ps_quote(venv)} -EvidencePath {ps_quote(evidence)} `
        -UvRunner $runner -VerifierRunner $verifier
}} catch {{
    $caught = $_.Exception.Message
}}
$output = [ordered]@{{
    ok = ($null -eq $caught)
    error = $caught
    selected = $selected
    after_environment = Get-TestEnvironmentState
}}
$output | ConvertTo-Json -Depth 10 -Compress
"""
    result = run_ps(tmp_path, body, env=inherited_env)
    parsed = json_result(result)
    log_entries = []
    if runner_log.exists():
        log_entries = [json.loads(line) for line in runner_log.read_text(encoding="utf-8").splitlines()]
    return {
        "process": result,
        "result": parsed,
        "log": log_entries,
        "runner_log": runner_log,
        "verifier_log": verifier_log,
        "evidence": evidence,
    }


def test_read_manifest_returns_exact_fixed_records(tmp_path: Path):
    root = make_repo(tmp_path)
    _, records = read_function(tmp_path, "Read-UvLockManifest", root / "locks" / "manifest.json", root)

    assert [record["source_id"] for record in records] == ["pypi", "tuna", "aliyun"]
    assert all(
        list(record) == ["source_id", "path", "index_url", "artifact_url_prefix", "sha256"]
        for record in records
    )
    assert [record["path"] for record in records] == [source[3] for source in SOURCES]


def test_read_mirrors_returns_only_reachable_candidates_in_fixed_order(tmp_path: Path):
    path = tmp_path / "mirrors.json"
    write_json(path, mirrors_document(reachable=(False, True, True)))

    _, candidates = read_function(tmp_path, "Read-UvMirrorCandidates", path)

    assert [candidate["id"] for candidate in candidates] == ["tuna", "aliyun"]
    assert all(list(candidate) == ["id", "url", "priority", "reachable"] for candidate in candidates)


def manifest_mutations(root: Path):
    original = json.loads((root / "locks" / "manifest.json").read_text(encoding="utf-8"))
    cases = []
    value = json.loads(json.dumps(original)); value.pop("normalized_graph_sha256"); cases.append(("missing-field", value))
    value = json.loads(json.dumps(original)); value["extra"] = 1; cases.append(("unknown-field", value))
    value = json.loads(json.dumps(original)); value["schema_version"] = "1"; cases.append(("schema-type", value))
    value = json.loads(json.dumps(original)); value["normalized_graph_sha256"] = "A" * 64; cases.append(("graph-hash", value))
    value = json.loads(json.dumps(original)); value["locks"]["pypi"]["extra"] = True; cases.append(("lock-extra", value))
    value = json.loads(json.dumps(original)); value["locks"]["pypi"]["index_url"] += "/"; cases.append(("url-alias", value))
    value = json.loads(json.dumps(original)); value["locks"]["pypi"]["sha256"] = "0" * 63; cases.append(("lock-hash-format", value))
    value = json.loads(json.dumps(original)); value["locks"]["pypi"]["sha256"] = "0" * 64; cases.append(("lock-hash-mismatch", value))
    value = json.loads(json.dumps(original)); value["locks"]["unknown"] = value["locks"].pop("pypi"); cases.append(("unknown-id", value))
    value = json.loads(json.dumps(original)); value["locks"] = {"tuna": value["locks"]["tuna"], "pypi": value["locks"]["pypi"], "aliyun": value["locks"]["aliyun"]}; cases.append(("id-order", value))
    return cases


@pytest.mark.parametrize("case_index", range(10))
def test_manifest_schema_and_hash_fail_closed_before_runner(tmp_path: Path, case_index: int):
    root = make_repo(tmp_path)
    name, invalid = manifest_mutations(root)[case_index]
    write_json(root / "locks" / "manifest.json", invalid)

    outcome = invoke_sync(tmp_path, root)

    assert not outcome["result"]["ok"], name
    assert not outcome["runner_log"].exists(), name
    assert not outcome["evidence"].exists(), name


def candidate_mutations():
    original = mirrors_document()
    cases = []
    value = json.loads(json.dumps(original)); value.pop("network_status"); cases.append(("missing-field", value))
    value = json.loads(json.dumps(original)); value["extra"] = 1; cases.append(("unknown-field", value))
    value = json.loads(json.dumps(original)); value["schema_version"] = True; cases.append(("schema-type", value))
    value = json.loads(json.dumps(original)); value["network_status"] = 1; cases.append(("status-type", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][0]["extra"] = 1; cases.append(("candidate-extra", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][0]["id"] = "unknown"; cases.append(("unknown-id", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][1]["id"] = "pypi"; cases.append(("duplicate-id", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][0]["url"] += "/"; cases.append(("url-alias", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][0]["url"] = "http://pypi.org/simple"; cases.append(("non-https", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][0]["priority"] = 1; cases.append(("priority", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"] = [value["uv_indexes"][1], value["uv_indexes"][0], value["uv_indexes"][2]]; cases.append(("order", value))
    value = json.loads(json.dumps(original)); value["uv_indexes"][0]["reachable"] = 1; cases.append(("reachable-type", value))
    return cases


@pytest.mark.parametrize("case_index", range(12))
def test_mirror_schema_and_unknown_sources_fail_closed_before_runner(tmp_path: Path, case_index: int):
    root = make_repo(tmp_path)
    name, invalid = candidate_mutations()[case_index]

    outcome = invoke_sync(tmp_path, root, mirrors=invalid)

    assert not outcome["result"]["ok"], name
    assert not outcome["runner_log"].exists(), name
    assert not outcome["evidence"].exists(), name


def test_missing_lock_variant_fails_before_runner(tmp_path: Path):
    root = make_repo(tmp_path)
    (root / "locks" / "uv.aliyun.lock").unlink()

    outcome = invoke_sync(tmp_path, root)

    assert not outcome["result"]["ok"]
    assert not outcome["runner_log"].exists()


def test_fallback_isolated_projects_exact_argv_environment_and_provenance(tmp_path: Path):
    root = make_repo(tmp_path)
    (root / "uv.toml").write_text('default-index = "https://evil.example/simple"', encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "uv.toml"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "external config"], check=True)
    inherited = {
        name: ("" if index == 1 else f"inherited-{index}")
        for index, name in enumerate(CONTROLLED)
        if index != 0
    }
    outcome = invoke_sync(
        tmp_path,
        root,
        behavior={"pypi": {"exit_code": 41}, "tuna": {"exit_code": 42}, "aliyun": {"exit_code": 0}},
        inherited_env=inherited,
    )

    assert outcome["result"]["ok"], outcome["result"]["error"]
    assert [entry["source_id"] for entry in outcome["log"]] == ["pypi", "tuna", "aliyun"]
    project_paths = []
    for entry, (_, url, _, _) in zip(outcome["log"], SOURCES, strict=True):
        args = entry["arguments"]
        project = Path(entry["project"])
        project_paths.append(project)
        assert args == [
            "sync", "--locked", "--all-groups", "--no-config", "--project", str(project),
            "--default-index", url, "--index-strategy", "first-index",
        ]
        assert "--frozen" not in args
        assert set(entry["project_files"]) == {"pyproject.toml", "uv.lock"}
        assert project.parent.resolve() == Path(tempfile.gettempdir()).resolve()
        assert project.name.startswith("omnidocbench-uv-")
        assert entry["environment"]["UV_PROJECT_ENVIRONMENT"] == {
            "present": True,
            "value": str(root / "venv with spaces"),
        }
        for name in CONTROLLED[:-1]:
            assert entry["environment"][name] == {"present": False, "value": None}
    assert len(set(project_paths)) == 3
    assert all(not path.exists() for path in project_paths)
    expected_after = {
        name: {"present": name in inherited, "value": inherited.get(name)}
        for name in CONTROLLED
    }
    assert outcome["result"]["after_environment"] == expected_after

    raw = outcome["evidence"].read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    evidence = json.loads(raw.decode("utf-8"))
    assert list(evidence) == [
        "schema_version", "selected_source_id", "selected_index_url", "selected_lock_path",
        "selected_lock_sha256", "normalized_graph_sha256", "pyproject_sha256", "uv_version",
        "completed_at", "failed_candidates",
    ]
    manifest = json.loads((root / "locks" / "manifest.json").read_text(encoding="utf-8"))
    assert evidence["schema_version"] == 1 and type(evidence["schema_version"]) is int
    assert evidence["selected_source_id"] == "aliyun"
    assert evidence["selected_index_url"] == SOURCES[2][1]
    assert evidence["selected_lock_path"] == SOURCES[2][3]
    assert evidence["selected_lock_sha256"] == sha256(root / SOURCES[2][3])
    assert evidence["normalized_graph_sha256"] == manifest["normalized_graph_sha256"]
    assert evidence["pyproject_sha256"] == sha256(root / "pyproject.toml")
    assert evidence["uv_version"] == "uv 0.11.16"
    assert evidence["completed_at"].endswith("Z")
    assert [item["source_id"] for item in evidence["failed_candidates"]] == ["pypi", "tuna"]
    assert [item["exit_code"] for item in evidence["failed_candidates"]] == [41, 42]
    assert not list(outcome["evidence"].parent.glob(outcome["evidence"].name + ".tmp.*"))
    assert outcome["result"]["selected"] == evidence


def test_all_sources_failure_is_aggregated_and_preserves_existing_evidence(tmp_path: Path):
    root = make_repo(tmp_path)
    sentinel = b'{"sentinel":"old"}\r\n'
    outcome = invoke_sync(
        tmp_path,
        root,
        behavior={source_id: {"exit_code": 50 + priority} for source_id, _, priority, _ in SOURCES},
        preexisting_evidence=sentinel,
    )

    assert not outcome["result"]["ok"]
    error = outcome["result"]["error"]
    for source_id, _, priority, _ in SOURCES:
        assert source_id in error and str(50 + priority) in error
    assert outcome["evidence"].read_bytes() == sentinel
    assert not list(tmp_path.glob("evidence with spaces.json.tmp.*"))


def test_runner_throw_without_mutation_falls_back_after_restore_and_cleanup(tmp_path: Path):
    root = make_repo(tmp_path)
    inherited = {"UV_INDEX": "", "UV_DEFAULT_INDEX": "before"}
    outcome = invoke_sync(
        tmp_path,
        root,
        behavior={"pypi": {"throw": True}, "tuna": {"exit_code": 0}},
        inherited_env=inherited,
    )

    assert outcome["result"]["ok"]
    assert [entry["source_id"] for entry in outcome["log"]] == ["pypi", "tuna"]
    assert not Path(outcome["log"][0]["project"]).exists()
    assert outcome["result"]["after_environment"]["UV_INDEX"] == {"present": True, "value": ""}
    evidence = json.loads(outcome["evidence"].read_text(encoding="utf-8"))
    assert evidence["failed_candidates"][0]["exit_code"] == -1
    assert "runner throw for pypi" in evidence["failed_candidates"][0]["error"]


@pytest.mark.parametrize(
    ("action", "error_text"),
    [
        ({"exit_code": 7, "mutate_root_lock": True}, "canonical uv.lock changed"),
        ({"throw": True, "mutate_root_lock": True}, "canonical uv.lock changed"),
        ({"exit_code": 7, "mutate_worktree": True}, "repository status changed"),
        ({"throw": True, "mutate_worktree": True}, "repository status changed"),
        ({"exit_code": 0, "mutate_worktree": True}, "repository status changed"),
    ],
)
def test_any_repository_mutation_aborts_without_fallback(tmp_path: Path, action: dict, error_text: str):
    root = make_repo(tmp_path)
    outcome = invoke_sync(tmp_path, root, behavior={"pypi": action, "tuna": {"exit_code": 0}})

    assert not outcome["result"]["ok"]
    assert error_text in outcome["result"]["error"]
    assert [entry["source_id"] for entry in outcome["log"]] == ["pypi"]
    assert not Path(outcome["log"][0]["project"]).exists()
    assert not outcome["verifier_log"].exists()
    assert not outcome["evidence"].exists()


def test_cleanup_error_wins_over_runner_error_but_immutability_still_runs(tmp_path: Path):
    root = make_repo(tmp_path)
    outcome = invoke_sync(
        tmp_path,
        root,
        behavior={"pypi": {"throw": True, "remove_project": True}, "tuna": {"exit_code": 0}},
    )

    assert not outcome["result"]["ok"]
    assert "cleanup" in outcome["result"]["error"].lower() or "cannot find path" in outcome["result"]["error"].lower()
    assert "runner throw" not in outcome["result"]["error"]
    assert [entry["source_id"] for entry in outcome["log"]] == ["pypi"]


def test_immutability_wins_over_cleanup_and_runner_errors(tmp_path: Path):
    root = make_repo(tmp_path)
    outcome = invoke_sync(
        tmp_path,
        root,
        behavior={"pypi": {"throw": True, "remove_project": True, "mutate_root_lock": True}},
    )

    assert not outcome["result"]["ok"]
    assert "canonical uv.lock changed" in outcome["result"]["error"]
    assert "runner throw" not in outcome["result"]["error"]
    assert [entry["source_id"] for entry in outcome["log"]] == ["pypi"]


def test_verifier_must_be_exact_and_read_only(tmp_path: Path):
    root = make_repo(tmp_path)
    outcome = invoke_sync(tmp_path, root, behavior={"verifier_mutates": True})

    assert not outcome["result"]["ok"]
    assert "repository status changed" in outcome["result"]["error"]
    assert not outcome["evidence"].exists()


def test_runner_and_verifier_pipeline_output_must_be_exactly_one_integer(tmp_path: Path):
    first_root = make_repo(tmp_path / "first")
    runner_outcome = invoke_sync(
        tmp_path / "first-run",
        first_root,
        behavior={"pypi": {"multi_output": True}, "tuna": {"exit_code": 0}},
    )
    assert runner_outcome["result"]["ok"]
    assert [entry["source_id"] for entry in runner_outcome["log"]] == ["pypi", "tuna"]
    failed = json.loads(runner_outcome["evidence"].read_text(encoding="utf-8"))["failed_candidates"]
    assert "exactly one integer" in failed[0]["error"]

    second_root = make_repo(tmp_path / "second")
    verifier_outcome = invoke_sync(
        tmp_path / "second-run",
        second_root,
        behavior={"verifier_multi_output": True},
    )
    assert not verifier_outcome["result"]["ok"]
    assert "exactly one integer" in verifier_outcome["result"]["error"]
    assert not verifier_outcome["evidence"].exists()


def test_host_diagnostics_do_not_pollute_runner_return(tmp_path: Path):
    root = make_repo(tmp_path)
    outcome = invoke_sync(tmp_path, root, behavior={"pypi": {"host_diagnostic": True, "exit_code": 0}})

    assert outcome["result"]["ok"]
    assert "runner diagnostic for pypi" in outcome["process"].stdout


def test_remove_validated_temp_project_accepts_only_safe_direct_child(tmp_path: Path):
    temp_root = Path(tempfile.gettempdir()).resolve()
    valid = Path(tempfile.mkdtemp(prefix="omnidocbench-uv-"))
    survivor = Path(tempfile.mkdtemp(prefix="omnidocbench-uv-"))
    nested = survivor / "nested"
    nested.mkdir()
    nonprefix = Path(tempfile.mkdtemp(prefix="not-omnidocbench-uv-"))
    repo = make_repo(tmp_path)
    try:
        body = f"""
$results = [ordered]@{{}}
foreach ($pair in @(
    @('temp-root', {ps_quote(temp_root)}),
    @('nonprefix', {ps_quote(nonprefix)}),
    @('nested', {ps_quote(nested)}),
    @('repo', {ps_quote(repo)})
)) {{
    try {{ Remove-ValidatedUvTempProject -Path $pair[1]; $results[$pair[0]] = 'deleted' }}
    catch {{ $results[$pair[0]] = $_.Exception.Message }}
}}
Remove-ValidatedUvTempProject -Path {ps_quote(valid)}
$results['valid_exists'] = Test-Path -LiteralPath {ps_quote(valid)}
$results | ConvertTo-Json -Compress
"""
        result = run_ps(tmp_path, body)
        values = json_result(result)
        assert all("refusing" in values[name].lower() for name in ["temp-root", "nonprefix", "nested", "repo"])
        assert values["valid_exists"] is False
        assert survivor.exists() and nested.exists() and nonprefix.exists() and repo.exists()
    finally:
        shutil.rmtree(valid, ignore_errors=True)
        shutil.rmtree(survivor, ignore_errors=True)
        shutil.rmtree(nonprefix, ignore_errors=True)


def test_remove_validated_temp_project_rejects_junction(tmp_path: Path):
    target = tmp_path / "junction target"
    target.mkdir(parents=True)
    (target / "sentinel.txt").write_text("keep", encoding="utf-8")
    junction = Path(tempfile.gettempdir()) / f"omnidocbench-uv-{os.urandom(8).hex()}"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("cannot create a junction on this Windows host")
    try:
        ps_result = run_ps(
            tmp_path,
            f"try {{ Remove-ValidatedUvTempProject -Path {ps_quote(junction)}; 'deleted' }} catch {{ $_.Exception.Message }}\n",
        )
        assert ps_result.returncode == 0
        assert "refusing" in ps_result.stdout.lower()
        assert junction.exists()
        assert (target / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    finally:
        subprocess.run(["cmd", "/c", "rmdir", str(junction)], check=False)


def test_one_environment_restore_failure_does_not_skip_other_restores_or_cleanup(tmp_path: Path):
    root = make_repo(tmp_path)
    mirrors = tmp_path / "mirrors.json"
    write_json(mirrors, mirrors_document())
    log = tmp_path / "project.txt"
    env = {name: f"before-{index}" for index, name in enumerate(CONTROLLED)}
    body = f"""
$script:OriginalRestore = ${{function:Restore-UvProcessEnvironmentVariable}}
$script:RestoreFailed = $false
function Restore-UvProcessEnvironmentVariable {{
    param([string] $Name, [bool] $Present, [AllowNull()][string] $Value)
    if ($Name -ceq 'UV_INDEX' -and -not $script:RestoreFailed) {{
        $script:RestoreFailed = $true
        throw 'injected single restore failure'
    }}
    & $script:OriginalRestore -Name $Name -Present $Present -Value $Value
}}
$runner = {{
    param([string[]] $Arguments)
    [IO.File]::WriteAllText({ps_quote(log)}, $Arguments[[Array]::IndexOf($Arguments, '--project') + 1])
    return [int]9
}}
$verifier = {{ param([string] $RepoRoot, [string] $ManifestPath); return [int]0 }}
$errorText = $null
try {{
    Invoke-UvCatalogSync -RepoRoot {ps_quote(root)} -ManifestPath {ps_quote(root / 'locks' / 'manifest.json')} `
        -MirrorsPath {ps_quote(mirrors)} -VenvPath {ps_quote(root / '.venv')} -EvidencePath {ps_quote(tmp_path / 'evidence.json')} `
        -UvRunner $runner -VerifierRunner $verifier | Out-Null
}} catch {{ $errorText = $_.Exception.Message }}
$all = [Environment]::GetEnvironmentVariables([EnvironmentVariableTarget]::Process)
$after = [ordered]@{{}}
foreach ($name in @({', '.join(ps_quote(name) for name in CONTROLLED)})) {{
    $after[$name] = $(if ($all.Contains($name)) {{ [string]$all[$name] }} else {{ $null }})
}}
[ordered]@{{error=$errorText; after=$after; project=[string](Get-Content -Raw -LiteralPath {ps_quote(log)})}} | ConvertTo-Json -Compress
"""
    result = run_ps(tmp_path, body, env=env)
    parsed = json_result(result)

    assert "injected single restore failure" in parsed["error"]
    for name in CONTROLLED[1:]:
        assert parsed["after"][name] == env[name]
    assert not Path(parsed["project"]).exists()
