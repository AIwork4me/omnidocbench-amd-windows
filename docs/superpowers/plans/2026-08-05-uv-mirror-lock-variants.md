# UV Mirror Lock Variants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make profile-driven bootstrap perform a strict, reproducible `uv sync --locked --all-groups` with verified failover from PyPI to Tsinghua to Aliyun without ever modifying the canonical root `uv.lock`.

**Architecture:** A Python verifier owns semantic comparison of the three tracked lockfiles and their deterministic manifest. A focused PowerShell support module validates the pre-bootstrap JSON contracts, isolates all uv configuration, runs source-specific temporary-project syncs, and emits environment provenance; `detect-mirrors.ps1` supplies ordered reachability data and `reproduce.ps1` orchestrates the stages and fingerprints the normalized dependency graph.

**Tech Stack:** Python 3.10/3.11 stdlib (`tomllib`, with locked `tomli` fallback), uv 0.11.x, Windows PowerShell 5.1, pytest, JSON/TOML, git

## Global Constraints

- The root `uv.lock` remains the canonical PyPI lock and is read-only during generation and sync.
- The only supported source IDs and PEP 503 indexes are `pypi=https://pypi.org/simple`, `tuna=https://pypi.tuna.tsinghua.edu.cn/simple`, and `aliyun=https://mirrors.aliyun.com/pypi/simple` in that order.
- Allowed artifact prefixes are exactly `https://files.pythonhosted.org/packages/`, `https://pypi.tuna.tsinghua.edu.cn/packages/`, and `https://mirrors.aliyun.com/pypi/packages/` for those IDs respectively.
- Canonical PyPI artifacts must declare valid non-negative integer sizes; a mirror may omit size, but a declared mirror size must equal canonical and missing values are projected only in the in-memory normalized graph.
- Every exact source-specific registry annotation is normalized recursively, including nested dependency sources; unknown or mixed registry annotations fail closed.
- Every environment installation remains `uv sync --locked --all-groups`; `--frozen`, unlocked resolution, package upgrades, and string-rewritten lockfiles are forbidden.
- All PowerShell must parse and run under Windows PowerShell 5.1; use nested two-argument `Join-Path`, no ternary syntax, and `$ErrorActionPreference = "Stop"`.
- All task-owned temporary projects are outside the repository and are deleted only after their resolved absolute path is proven to be under `[System.IO.Path]::GetTempPath()` and to use the `omnidocbench-uv-` prefix.
- Snapshot and restore `UV_INDEX`, `UV_DEFAULT_INDEX`, `UV_INDEX_URL`, `UV_EXTRA_INDEX_URL`, `UV_INDEX_STRATEGY`, `UV_NO_INDEX`, `UV_FIND_LINKS`, `UV_CONFIG_FILE`, `UV_NO_CONFIG`, and `UV_PROJECT_ENVIRONMENT`, preserving absent versus present-with-empty values.
- `mirrors.json` and environment-lock evidence are generated, machine-local artifacts; the three lockfiles and `locks/manifest.json` are tracked release inputs.
- Follow TDD. Each numbered task is implemented by a fresh subagent, then independently checked for specification compliance and code quality before the next task starts.

---

## File responsibility map

- `scripts/verify_uv_lock_variants.py`: canonical source catalog, strict manifest schema, TOML parsing, URL-origin validation, normalized graph construction, graph digest, manifest generation/check CLI.
- `scripts/generate-uv-lock-variants.ps1`: isolated uv relock workflow, staged three-lock validation, backup/atomic replacement/rollback, live `uv lock --check` gates.
- `scripts/uv-lock-support.ps1`: PowerShell-only manifest and `mirrors.json` validation, uv environment snapshot/restore, source failover, root-lock/worktree immutability checks, environment-lock provenance.
- `scripts/detect-mirrors.ps1`: independent PEP 503 probes and atomic `mirrors.json` generation while retaining `mirrors.env` for non-uv consumers.
- `scripts/reproduce.ps1`: stage ordering, helper invocation, normalized-graph fingerprint input, evidence path wiring.
- `scripts/repro-evidence.ps1`: include the environment-lock record in `artifact-hashes.json`.
- `scripts/release-gate.ps1`: fail releases when the tracked lock catalog is missing, stale, or semantically divergent.
- `tests/test_uv_lock_variants.py`: deterministic unit tests for lock parsing, normalization, origin allowlists, manifest schema, mutations, and CLI.
- `tests/test_uv_lock_generation.py`: fake-uv tests for canonical-copy generation, rollback, root immutability, and exact commands.
- `tests/test_detect_mirrors.py`: fixture-driven probe matrix and atomic JSON contract tests.
- `tests/test_uv_lock_support.py`: PowerShell support-module behavior, environment restoration, candidate validation, fallback, cleanup, and provenance.
- `tests/harness_fake.py`, `tests/test_reproduce_harness.py`, `tests/test_windows_reproduce.py`, `tests/test_repro_artifacts.py`, `tests/test_fingerprint.py`, `tests/test_release_gate.py`: end-to-end stage, resume, fingerprint, evidence, and release regressions.
- `.gitignore`, `README.md`, `AGENTS.md`, `docs/pitfalls.md`: generated-file policy and operator guidance.

---

### Task 1: Correct live mirror semantics in the offline verifier

**Files:**
- Modify: `scripts/verify_uv_lock_variants.py`
- Modify: `tests/test_uv_lock_variants.py`

**Interfaces:**
- Preserve: `SOURCE_SPECS: tuple[SourceSpec, ...]` in fixed `pypi`, `tuna`, `aliyun` order.
- Preserve: `normalize_lock(lock: dict, source: SourceSpec) -> dict`.
- Preserve: `verify_catalog(root: Path, manifest_path: Path) -> dict` and both existing CLI modes.
- Add internal canonical size-map/projection helpers; do not expose network behavior.

- [ ] **Step 1: Add failing live-shape tests before changing production code**

Extend the existing minimal-lock fixture so size can be removed or changed per
source and a dependency can carry `source = { registry = <index> }`. Add these
required tests:

```python
def test_mirror_missing_sizes_projects_canonical_sizes(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    remove_all_artifact_sizes(root / "locks" / "uv.aliyun.lock")
    assert len(verifier.normalized_graph_sha256(root)) == 64


def test_canonical_missing_size_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    remove_one_artifact_size(root / "uv.lock")
    with pytest.raises(verifier.CatalogError, match="canonical artifact size"):
        verifier.build_manifest(root)


def test_wrong_declared_mirror_size_is_rejected(tmp_path):
    root = write_three_lock_catalog(tmp_path)
    change_one_artifact_size(root / "locks" / "uv.tuna.lock", 999)
    with pytest.raises(verifier.CatalogError, match="mirror artifact size"):
        verifier.build_manifest(root)


def test_nested_registry_sources_normalize(tmp_path):
    root = write_three_lock_catalog(tmp_path, nested_registry_sources=True)
    assert len(verifier.normalized_graph_sha256(root)) == 64
```

Also cover one missing mirror size, equal declared mirror size, boolean/negative
canonical size, canonical size mutation invalidating an existing manifest,
unknown and mixed nested registry objects, and significant direct/Git/path
sources.

- [ ] **Step 2: Run the focused tests and confirm the red state**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_variants.py -q
```

Expected: mirror omission and exact nested-source tests fail with normalized
graph differences; canonical-missing and wrong-mirror-size tests do not yet
raise the required diagnostics.

- [ ] **Step 3: Recursively normalize exact registry annotations**

Add a recursive transformation and call it from `normalize_lock` after artifact
URL normalization:

```python
def _normalize_registry_sources(value: object, source: SourceSpec) -> object:
    if isinstance(value, dict):
        if "registry" in value:
            if value != {"registry": source.index_url}:
                raise CatalogError(
                    f"registry annotation must exactly match {source.source_id}: {value}"
                )
            return {"registry": "<registry>"}
        return {key: _normalize_registry_sources(item, source) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_registry_sources(item, source) for item in value]
    return value
```

This must normalize package and nested dependency registry objects. It must not
change direct, Git, path, marker, URL, or arbitrary string values.

- [ ] **Step 4: Project canonical sizes only for matching mirror artifacts**

Artifact identity is `(package name, package version, role, decoded filename,
SHA-256)`. Build the canonical map from the already URL-normalized PyPI graph:

```python
def _canonical_artifact_sizes(graph: dict) -> dict[tuple[str, str, str, str, str], int]:
    sizes = {}
    for key, artifact in _iter_artifacts(graph):
        size = artifact.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise CatalogError(f"canonical artifact size is missing or invalid: {key}")
        if key in sizes:
            raise CatalogError(f"duplicate canonical artifact identity: {key}")
        sizes[key] = size
    return sizes


def _project_canonical_sizes(
    graph: dict,
    canonical_sizes: dict[tuple[str, str, str, str, str], int],
    source: SourceSpec,
) -> dict:
    projected = copy.deepcopy(graph)
    seen = set()
    for key, artifact in _iter_artifacts(projected):
        if key not in canonical_sizes:
            raise CatalogError(f"mirror artifact is absent from canonical lock: {key}")
        declared = artifact.get("size")
        canonical = canonical_sizes[key]
        if declared is None:
            artifact["size"] = canonical
        elif isinstance(declared, bool) or not isinstance(declared, int) or declared < 0 or declared != canonical:
            raise CatalogError(f"mirror artifact size differs for {source.source_id}: {key}")
        seen.add(key)
    if seen != set(canonical_sizes):
        raise CatalogError(f"mirror artifact set differs for {source.source_id}")
    return projected
```

`_iter_artifacts` must yield stable keys for sdist and each wheel without
reordering the graph. `normalized_graph_sha256` must normalize canonical first,
validate its sizes, normalize each mirror, project only missing sizes, compare
canonical JSON bytes, and hash the canonical normalized bytes. Raw tracked
mirror locks are never rewritten.

- [ ] **Step 5: Complete mutation and manifest regression coverage**

Retain all existing URL, schema, version, dependency, marker, artifact hash,
direct URL and CLI atomicity tests. Split size coverage into omission versus
numeric mutation. Prove canonical size changes alter the normalized digest and
invalidate the old manifest; prove missing mirror size does not. Add a fixture
matching live output where Tsinghua omits four sizes, Aliyun omits all sizes,
and all three locks have nested dependency registry annotations.

- [ ] **Step 6: Run focused and full verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_variants.py tests\test_uv_environment.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: focused and full suites pass with pristine output.

- [ ] **Step 7: Commit the Task 1 correction**

```powershell
git add scripts\verify_uv_lock_variants.py tests\test_uv_lock_variants.py
git commit -m "fix: normalize live uv mirror metadata"
```

Independent gate: a fresh reviewer must verify canonical-size authority,
omission-only projection, declared-size mismatch rejection, recursive exact
registry normalization, raw lock immutability, deterministic digest behavior,
and complete RED/GREEN evidence before Task 2 resumes.

---

### Task 2: Generate and track the three-lock catalog atomically

**Files:**
- Create: `scripts/generate-uv-lock-variants.ps1`
- Create: `tests/test_uv_lock_generation.py`
- Create: `locks/uv.tuna.lock`
- Create: `locks/uv.aliyun.lock`
- Create: `locks/manifest.json`
- Read only: `uv.lock`
- Read only: `pyproject.toml`

**Interfaces:**
- Consumes: Task 1 CLI generation/check modes.
- Produces: `generate-uv-lock-variants.ps1 -RepoRoot <path> -UvExecutable <path> -PythonExecutable <path>`.
- Produces: tracked `locks/manifest.json` schema v1 and two source-specific lockfiles.

- [ ] **Step 1: Write fake-uv red tests for exact generation commands**

The fake uv executable must log argv, assert that every temporary project starts with byte-identical copies of `pyproject.toml` and canonical `uv.lock`, rewrite only its temporary lock fixture, and support a configured failure on the Tsinghua or Aliyun source. At least one success fixture must match the measured live shape: Tsinghua omits four artifact sizes, Aliyun omits every artifact size, and all locks carry exact source-specific nested dependency registry annotations. The staged verifier must accept that fixture without editing the generated locks. Assert each mirror uses:

```text
lock --no-config --project <external-temp> --default-index <exact-url>
lock --check --no-config --project <external-temp> --default-index <exact-url>
```

Assert the canonical PyPI temporary project uses only `lock --check --no-config --project <external-temp> --default-index https://pypi.org/simple`. Also assert no argv contains `--upgrade`, the repository root lock hash is unchanged, and a configured replacement failure leaves every pre-existing tracked catalog file byte-identical.

- [ ] **Step 2: Run the generator tests and confirm the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_generation.py -q
```

Historical RED already captured in the Task 2 report: the focused test failed
because `scripts/generate-uv-lock-variants.ps1` was absent. On resume, retain
that evidence and require the current generator suite to pass, including the
new measured missing-size/nested-source fixture; do not manufacture a second
absence failure by deleting the partial implementation.

- [ ] **Step 3: Write the isolated generation workflow**

Use these parameters and guards:

```powershell
[CmdletBinding()]
param(
    [string] $RepoRoot = "",
    [string] $UvExecutable = "uv",
    [string] $PythonExecutable = ""
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
```

Windows PowerShell 5.1 evaluates parameter default expressions before
`$PSScriptRoot` is populated, so repository-root resolution must occur after
the `param` block. A regression test invokes the script without `-RepoRoot`
from an unrelated current directory.

Resolve `$RepoRoot`, calculate the canonical root lock hash once, and create one `omnidocbench-uv-generate-<guid>` directory under the OS temp directory. Within it create separate `pypi`, `tuna`, and `aliyun` uv projects plus a distinct `catalog-stage\locks` directory. Copy canonical `pyproject.toml` and `uv.lock` into each uv project before invocation. Clear and restore all controlled uv variables in `finally`, retaining absent-versus-empty state.

When `-PythonExecutable` is empty, resolve it to `<RepoRoot>\.venv\Scripts\python.exe`; throw before creating staging files if it or the uv executable cannot be resolved.

Use the exact source loop and command construction below; `$savedUvEnvironment` stores `[ordered]@{present=<bool>; value=<string-or-null>}` for every controlled name:

```powershell
$sources = @(
    [ordered]@{ id = "tuna"; url = "https://pypi.tuna.tsinghua.edu.cn/simple"; path = "locks\uv.tuna.lock" },
    [ordered]@{ id = "aliyun"; url = "https://mirrors.aliyun.com/pypi/simple"; path = "locks\uv.aliyun.lock" }
)

$canonicalTemp = Join-Path $tempRoot "pypi"
New-Item -ItemType Directory -Force -Path $canonicalTemp | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "pyproject.toml") -Destination (Join-Path $canonicalTemp "pyproject.toml")
Copy-Item -LiteralPath (Join-Path $RepoRoot "uv.lock") -Destination (Join-Path $canonicalTemp "uv.lock")
& $UvExecutable lock --check --no-config --project $canonicalTemp `
    --default-index "https://pypi.org/simple"
if ($LASTEXITCODE -ne 0) { throw "canonical PyPI lock check failed: $LASTEXITCODE" }

foreach ($source in $sources) {
    $project = Join-Path $tempRoot $source.id
    Copy-Item -LiteralPath (Join-Path $RepoRoot "pyproject.toml") -Destination (Join-Path $project "pyproject.toml")
    Copy-Item -LiteralPath (Join-Path $RepoRoot "uv.lock") -Destination (Join-Path $project "uv.lock")
    & $UvExecutable lock --no-config --project $project --default-index $source.url
    if ($LASTEXITCODE -ne 0) { throw "uv lock failed for $($source.id): $LASTEXITCODE" }
    & $UvExecutable lock --check --no-config --project $project --default-index $source.url
    if ($LASTEXITCODE -ne 0) { throw "uv lock --check failed for $($source.id): $LASTEXITCODE" }
}

$catalogStage = Join-Path $tempRoot "catalog-stage"
$catalogLocks = Join-Path $catalogStage "locks"
New-Item -ItemType Directory -Force -Path $catalogLocks | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "uv.lock") -Destination (Join-Path $catalogStage "uv.lock")
Copy-Item -LiteralPath (Join-Path (Join-Path $tempRoot "tuna") "uv.lock") -Destination (Join-Path $catalogLocks "uv.tuna.lock")
Copy-Item -LiteralPath (Join-Path (Join-Path $tempRoot "aliyun") "uv.lock") -Destination (Join-Path $catalogLocks "uv.aliyun.lock")
& $PythonExecutable (Join-Path $RepoRoot "scripts\verify_uv_lock_variants.py") `
    --root $catalogStage --write-manifest (Join-Path $catalogLocks "manifest.json")
if ($LASTEXITCODE -ne 0) { throw "staged lock manifest generation failed: $LASTEXITCODE" }
& $PythonExecutable (Join-Path $RepoRoot "scripts\verify_uv_lock_variants.py") `
    --root $catalogStage --manifest (Join-Path $catalogLocks "manifest.json")
if ($LASTEXITCODE -ne 0) { throw "staged lock catalog verification failed: $LASTEXITCODE" }
```

Only `catalog-stage\locks\uv.tuna.lock`, `catalog-stage\locks\uv.aliyun.lock`, and `catalog-stage\locks\manifest.json` feed the same-volume replacement files. The per-source uv project locks are never copied directly to tracked destinations.

- [ ] **Step 4: Add atomic replacement and rollback**

Stage the two variants and manifest beside their final destinations, hash and back up any existing destination, then use `Move-Item -Force` one file at a time. On any exception, restore every original from its backup and remove destinations that did not previously exist. Recalculate `uv.lock` before exit and throw if it differs. Cleanup only the resolved, prefix-validated OS-temp directory.

Represent each replacement as `[ordered]@{destination; staged; existed; backup}` and use this rollback shape:

```powershell
try {
    foreach ($item in $replacements) {
        if ($item.existed) { Copy-Item -LiteralPath $item.destination -Destination $item.backup }
        Move-Item -LiteralPath $item.staged -Destination $item.destination -Force
    }
} catch {
    for ($i = $replacements.Count - 1; $i -ge 0; $i--) {
        $item = $replacements[$i]
        if ($item.existed -and (Test-Path -LiteralPath $item.backup)) {
            Copy-Item -LiteralPath $item.backup -Destination $item.destination -Force
        } elseif (-not $item.existed -and (Test-Path -LiteralPath $item.destination)) {
            Remove-Item -LiteralPath $item.destination -Force
        }
    }
    throw
}
```

- [ ] **Step 5: Pass fake-uv generation and rollback tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_generation.py tests\test_uv_lock_variants.py -q
```

Expected: all pass; the failure-path cases prove no partial catalog update.

- [ ] **Step 6: Generate the real variants and validate all sources currently reachable**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\generate-uv-lock-variants.ps1
.\.venv\Scripts\python.exe scripts\verify_uv_lock_variants.py --root . --manifest locks\manifest.json
uv lock --check --no-config --project . --default-index https://pypi.org/simple
```

For Tsinghua and Aliyun, copy `pyproject.toml` plus the matching tracked variant as `uv.lock` into external temporary projects and run `uv lock --check --no-config --project <temp> --default-index <source-url>`. Expected: each reachable source exits 0; unreachable sources are explicitly recorded as network-dependent SKIP. Confirm `git diff --exit-code -- uv.lock` exits 0.

- [ ] **Step 7: Commit Task 2**

```powershell
git add scripts\generate-uv-lock-variants.ps1 tests\test_uv_lock_generation.py locks\uv.tuna.lock locks\uv.aliyun.lock locks\manifest.json
git commit -m "feat: add source-specific uv lock catalog"
```

Independent gate: review exact source URLs and artifact prefixes, real lock graph digest equality, no package/hash drift, root-lock immutability, replacement rollback, and live-check evidence before Task 3.

---

### Task 3: Emit a strict ordered mirror-candidate document

**Files:**
- Modify: `scripts/detect-mirrors.ps1:1-149`
- Create: `tests/test_detect_mirrors.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: root `mirrors.json` schema v1 with all three fixed uv entries.
- Retains: root `mirrors.env` for dataset, model, GitHub, CTAN, WSL and legacy `PYPI_INDEX` consumers.
- Test seam: `REPRO_TEST_HOOKS` plus `MIRROR_PROBE_RESULTS_JSON`; reject fixture injection unless both are present.

- [ ] **Step 1: Write fixture-driven red tests**

Run `detect-mirrors.ps1` in a temporary repository root with deterministic probe results. Test all-up, PyPI-down/Tsinghua-up, only-Aliyun-up, all-PyPI-sources-down, dataset-offline, malformed fixture, and two successive writes. Assert exact JSON keys, types, fixed array order, canonical URLs/priorities, reachability booleans, status, UTF-8 parseability, and absence of `.tmp.*` leftovers.

- [ ] **Step 2: Run the focused test and confirm the red state**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_detect_mirrors.py -q
```

Expected: FAIL because no `mirrors.json` is produced.

- [ ] **Step 3: Add independent uv probes and exact JSON output**

Probe all three exact PEP 503 roots regardless of dataset/GitHub/CTAN results, always construct:

```powershell
$uvIndexes = @(
    [ordered]@{ id = "pypi";  url = "https://pypi.org/simple"; priority = 0; reachable = [bool]$pypi },
    [ordered]@{ id = "tuna";  url = "https://pypi.tuna.tsinghua.edu.cn/simple"; priority = 1; reachable = [bool]$tuna },
    [ordered]@{ id = "aliyun"; url = "https://mirrors.aliyun.com/pypi/simple"; priority = 2; reachable = [bool]$aliyun }
)
```

Write `[ordered]@{schema_version=1; network_status=$status; uv_indexes=$uvIndexes}` to a same-directory temporary file using UTF-8 without BOM, parse it back, then `Move-Item -Force` to `mirrors.json`. `PYPI_INDEX` remains the first reachable URL in the same order, or the existing explicit unreachable marker.

- [ ] **Step 4: Make partial/offline paths write both contracts before exiting**

Remove the current early dataset-offline exit. Collect all probe results, atomically write `mirrors.env` and `mirrors.json`, then exit 1 for the existing human-intervention condition. This guarantees that every completed detector run leaves all three uv entries, including the offline case.

- [ ] **Step 5: Ignore only the generated candidate file**

Add exactly:

```gitignore
mirrors.json
```

Do not ignore `locks/` or any tracked lock catalog file.

- [ ] **Step 6: Run focused, parse, and existing network tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_detect_mirrors.py tests\test_windows_cdm_patch_flow.py -q
powershell -NoProfile -Command "$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('scripts\detect-mirrors.ps1',[ref]$t,[ref]$e);if($e.Count){$e|% Message;exit 1}"
```

Expected: all tests pass and the parser emits no errors.

- [ ] **Step 7: Commit Task 3**

```powershell
git add .gitignore scripts\detect-mirrors.ps1 tests\test_detect_mirrors.py
git commit -m "feat: detect ordered uv mirror candidates"
```

Independent gate: review all-up/degraded/offline schemas, probe independence, JSON atomicity, legacy env compatibility, and production rejection of test fixtures before Task 4.

---

### Task 4: Isolated strict-sync and fallback support module

**Files:**
- Create: `scripts/uv-lock-support.ps1`
- Create: `tests/test_uv_lock_support.py`

**Interfaces:**
- Produces: `Read-UvLockManifest -Path <path> -RepoRoot <path>` returning exact validated lock records.
- Produces: `Read-UvMirrorCandidates -Path <path>` returning only reachable fixed candidates in priority order.
- Produces: `Remove-ValidatedUvTempProject -Path <path>` deleting only a resolved direct child of the OS temp root whose name starts with `omnidocbench-uv-`.
- Produces: `Invoke-UvCatalogSync -RepoRoot <path> -ManifestPath <path> -MirrorsPath <path> -VenvPath <path> -EvidencePath <path> -UvRunner <scriptblock> -VerifierRunner <scriptblock>` returning the selected-source record.
- `UvRunner` contract: `param([string[]] $Arguments); return [int]`; diagnostics go to host/information/error streams and pipeline output is exactly one integer.
- `VerifierRunner` contract: `param([string] $RepoRoot, [string] $ManifestPath); return [int]`.

- [ ] **Step 1: Write red tests for strict schema and unknown-source rejection**

From pytest, dot-source the module in Windows PowerShell and serialize returned objects to JSON. Assert missing/unknown fields, IDs, URL aliases, priority/order changes, duplicate IDs, non-HTTPS URLs, type mismatches, missing variants, and bad lock hashes fail before the fake uv log is created.

- [ ] **Step 2: Write red tests for fallback, isolation, cleanup and provenance**

Use a fake `UvRunner` that logs exact arguments and either returns configured codes or throws a configured exception. Cover `pypi -> tuna -> aliyun`, all-source failure, inherited controlled variables (absent, empty, and non-empty), external `uv.toml`, root-lock mutation on a failed attempt, worktree mutation on a failed attempt, mutation on a successful attempt, and paths containing spaces. Add these mandatory exception cases:

1. runner throws without mutation: environment restores, temp cleanup succeeds, and the next source is attempted;
2. runner throws after root-lock or worktree mutation: environment restores and temp cleanup runs, then the immutability error aborts without a next source;
3. runner throws and deliberately removes its own temp project: the immutability check still runs, then cleanup failure wins over the runner error;
4. runner throws, removes its temp project, and mutates the root lock: the immutability error wins over both cleanup and runner errors.

Assert the precedence exactly as `immutability > cleanup > runner`, and assert mutation aborts immediately without invoking the next candidate. Assert every sync argv contains:

```text
sync --locked --all-groups --no-config --project <external-temp> --default-index <url> --index-strategy first-index
```

and never contains `--frozen` or an unlock operation. Test `Remove-ValidatedUvTempProject` directly: it must reject the OS temp root itself, a non-prefixed direct child, a nested child under a valid prefixed directory, and a repository directory; it must delete one existing `omnidocbench-uv-<guid>` direct child and only that child.

- [ ] **Step 3: Run focused tests and confirm the red state**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_support.py -q
```

Expected: FAIL because the support module is absent.

- [ ] **Step 4: Implement exact JSON validation and pre-sync hashes**

Reject any candidate or manifest shape not matching the approved schemas. Map candidate ID to the manifest record and require exact URL equality. Before mutating environment or creating `.venv`, calculate selected lock SHA-256 and compare it with the manifest; calculate canonical `uv.lock` SHA-256 and capture `git -C <root> status --porcelain=v1 --untracked-files=all` as an ordered string array.

Use an exact-key helper for both JSON contracts:

```powershell
function Assert-ExactJsonKeys {
    param($Object, [string[]] $Expected, [string] $Label)
    $actual = @($Object.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) {
        throw "$Label keys must be exactly [$($Expected -join ', ')]; got [$($actual -join ', ')]"
    }
}
```

After schema validation, build `$manifestById` only from the three fixed IDs and compare `(Get-FileHash -Algorithm SHA256).Hash.ToLowerInvariant()` to the corresponding lowercase manifest hash before calling the runner. Capture `$baselineRootLockSha256` and `$baselineGitStatus` once, and define:

```powershell
function Remove-ValidatedUvTempProject {
    param([string] $Path)
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\")
    $parent = [System.IO.Path]::GetDirectoryName($resolved).TrimEnd("\")
    $leaf = [System.IO.Path]::GetFileName($resolved)
    if (-not [string]::Equals($parent, $tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not $leaf.StartsWith("omnidocbench-uv-", [System.StringComparison]::Ordinal)) {
        throw "refusing to delete unvalidated uv temp project: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}


function Assert-UvSyncRepositoryUnchanged {
    param([string] $RepoRoot, [string] $ExpectedLockSha256, [string[]] $ExpectedGitStatus)
    $actualLock = (Get-FileHash -LiteralPath (Join-Path $RepoRoot "uv.lock") -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualStatus = @(& git -C $RepoRoot status --porcelain=v1 --untracked-files=all)
    if ($actualLock -cne $ExpectedLockSha256) { throw "canonical uv.lock changed during uv sync" }
    if (($actualStatus -join "`n") -cne ($ExpectedGitStatus -join "`n")) { throw "repository status changed during uv sync" }
}
```

- [ ] **Step 5: Implement isolated candidate attempts**

For each reachable candidate, create a new validated OS-temp directory, copy repository `pyproject.toml` and the selected tracked variant to temporary `uv.lock`, set `UV_PROJECT_ENVIRONMENT` to the absolute repository venv, clear all controlled variables, and call `UvRunner`. Record `[ordered]@{source_id; index_url; lock_path; lock_sha256; exit_code; error}` for an ordinary transport/sync failure and continue. Always restore environment and cleanup the validated task-owned temporary directory in `finally`; immediately after that `finally`, call `Assert-UvSyncRepositoryUnchanged` before recording failure or entering the next iteration. A mutation exception is fatal and is never treated as a candidate failure.

Use this presence-preserving environment pattern and exact sync argument list:

```powershell
$controlled = @("UV_INDEX", "UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL",
    "UV_INDEX_STRATEGY", "UV_NO_INDEX", "UV_FIND_LINKS", "UV_CONFIG_FILE",
    "UV_NO_CONFIG", "UV_PROJECT_ENVIRONMENT")
$saved = [ordered]@{}
foreach ($name in $controlled) {
    $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    $saved[$name] = [ordered]@{ present = ($null -ne $item); value = $(if ($null -eq $item) { $null } else { [string]$item.Value }) }
}
$runnerException = $null
$cleanupException = $null
$immutabilityException = $null
$exitCode = -1
try {
    foreach ($name in $controlled) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
    $env:UV_PROJECT_ENVIRONMENT = $VenvPath
    $arguments = @("sync", "--locked", "--all-groups", "--no-config", "--project", $project,
        "--default-index", $candidate.url, "--index-strategy", "first-index")
    $exitCode = [int](& $UvRunner $arguments)
} catch {
    $runnerException = $_
} finally {
    try {
        foreach ($name in $controlled) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
            if ($saved[$name].present) { Set-Item -LiteralPath "Env:$name" -Value $saved[$name].value }
        }
        Remove-ValidatedUvTempProject -Path $project
    } catch {
        $cleanupException = $_
    }
}
try {
    Assert-UvSyncRepositoryUnchanged -RepoRoot $RepoRoot `
        -ExpectedLockSha256 $baselineRootLockSha256 -ExpectedGitStatus $baselineGitStatus
} catch {
    $immutabilityException = $_
}
if ($null -ne $immutabilityException) { throw $immutabilityException }
if ($null -ne $cleanupException) { throw $cleanupException }
if ($null -ne $runnerException) {
    $exitCode = -1
    $errorText = $runnerException.Exception.Message
}
```

Only after the three post-attempt exception checks may the loop record `$exitCode`/`$errorText` and continue to the next candidate. This makes a thrown runner eligible for source fallback while ensuring its repository mutation or cleanup failure wins and aborts the loop.

- [ ] **Step 6: Validate success and write provenance atomically**

After the first successful sync and its mandatory per-attempt immutability check, invoke `VerifierRunner`, then call `Assert-UvSyncRepositoryUnchanged` again because the verifier is also required to be read-only. On all-source exhaustion, call the same assertion once more before throwing the aggregated error. Write UTF-8-no-BOM evidence atomically with these exact fields:

```json
{
  "schema_version": 1,
  "selected_source_id": "aliyun",
  "selected_index_url": "https://mirrors.aliyun.com/pypi/simple",
  "selected_lock_path": "locks/uv.aliyun.lock",
  "selected_lock_sha256": "<64 lowercase hex>",
  "normalized_graph_sha256": "<64 lowercase hex>",
  "pyproject_sha256": "<64 lowercase hex>",
  "uv_version": "uv 0.11.16",
  "completed_at": "<UTC ISO-8601>",
  "failed_candidates": []
}
```

On exhaustion, throw one error listing every attempted source ID and exit code. Restore every controlled variable in `finally`, preserving absent versus empty.

Write the record through a sibling temp and parse it before replacement:

```powershell
$json = $record | ConvertTo-Json -Depth 8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$tempEvidence = "$EvidencePath.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
[System.IO.File]::WriteAllText($tempEvidence, $json, $utf8NoBom)
[void](Get-Content -Raw -Encoding UTF8 -LiteralPath $tempEvidence | ConvertFrom-Json)
Move-Item -LiteralPath $tempEvidence -Destination $EvidencePath -Force
```

- [ ] **Step 7: Run support-module tests and parser gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_support.py -q
powershell -NoProfile -Command "$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('scripts\uv-lock-support.ps1',[ref]$t,[ref]$e);if($e.Count){$e|% Message;exit 1}"
```

Expected: all tests pass, no temp directories remain, and parser output is empty.

- [ ] **Step 8: Commit Task 4**

```powershell
git add scripts\uv-lock-support.ps1 tests\test_uv_lock_support.py
git commit -m "feat: add isolated uv lock failover"
```

Independent gate: inspect fail-closed validation, environment restoration on every exit, cleanup target safety, error aggregation, immutability checks, and provenance bytes before Task 5.

---

### Task 5: Wire mirror detection, strict sync, fingerprint, and evidence into the orchestrator

**Files:**
- Modify: `scripts/reproduce.ps1:88-182, 205-217, 511-544, 586-613, 982-992`
- Modify: `tests/harness_fake.py:346-514`
- Modify: `tests/test_reproduce_harness.py:72-118` and append uv scenarios
- Modify: `tests/test_windows_reproduce.py:176-267`
- Modify: `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: Task 3 `mirrors.json`; Task 4 module; Task 1 verifier.
- Produces: `<evidenceDir>/environment-lock.json` before `inputs.fingerprint`.
- Produces: provisioning input `uv_normalized_graph_sha256 = @{ string = $lockManifest.normalized_graph_sha256 }`.

- [ ] **Step 1: Extend the fake harness and write failing orchestration tests**

Make fake `detect-mirrors.ps1` write exact `mirrors.json`; copy all three lockfiles and manifest into fake root before its seed commit; replace the zero-only fake uv with one that logs argv, records controlled environment variables, and reads `uv_fail_source_ids` from `behavior.json`. Add assertions for stage order `environment.mirrors < environment.python < environment.wsl`, exact fallback order, stale `mirrors.env` ignored by uv selection, root lock unchanged, environment restoration, and `environment-lock.json` contents.

- [ ] **Step 2: Run harness tests and confirm the red state**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_reproduce_harness.py tests\test_windows_reproduce.py tests\test_fingerprint.py -q
```

Expected: new tests fail because Python still runs before mirror detection and no normalized digest/provenance is wired.

- [ ] **Step 3: Load the support module and define owned paths**

Immediately after the existing evidence/profile dot-sources, add:

```powershell
. (Join-Path $script:RealRepoRoot "scripts\uv-lock-support.ps1")
```

Define `$uvLockManifestPath`, `$mirrorsJsonPath`, and `$environmentLockFile` in the unified artifact path block. Include only `$environmentLockFile` in the profile-owned evidence purge set; never include tracked lock catalog paths.

- [ ] **Step 4: Move detection before Python and invoke strict sync**

Move the unchanged `environment.mirrors` stage before `environment.python`. Replace `PYPI_INDEX -> UV_INDEX_URL` mutation with:

```powershell
$uvRunner = {
    param([string[]] $UvArguments)
    Invoke-ReproUv -Arguments $UvArguments | Out-Host
    return [int]$script:ReproLastExit
}
$verifierRunner = {
    param([string] $CatalogRoot, [string] $ManifestPath)
    Invoke-ReproPython -Relative "scripts\verify_uv_lock_variants.py" -Arguments @("--root", $CatalogRoot, "--manifest", $ManifestPath) | Out-Host
    return [int]$script:ReproLastExit
}
Invoke-ReproUv -Arguments @("--no-config", "python", "install", "3.11") | Out-Host
Assert-LastExit "uv python install"
Invoke-UvCatalogSync -RepoRoot $rootDir -ManifestPath $uvLockManifestPath `
    -MirrorsPath $mirrorsJsonPath -VenvPath (Join-Path $rootDir ".venv") `
    -EvidencePath $environmentLockFile -UvRunner $uvRunner `
    -VerifierRunner $verifierRunner | Out-Null
```

Keep `UV_LINK_MODE=copy` scoped and restored as before. Update the dry-run command string to show the detector first and the strict source fallback contract.

- [ ] **Step 5: Add normalized graph to provisioning fingerprint**

Read and validate `locks/manifest.json` before constructing the spec, then add exactly:

```powershell
uv_lock_sha256 = @{ file = (Join-Path $rootDir "uv.lock") }
uv_normalized_graph_sha256 = @{ string = $lockManifest.normalized_graph_sha256 }
```

Do not add selected source ID, selected URL, or selected variant hash. Extend fingerprint tests so changing only `mirrors.json`/environment-lock selection remains stable, while changing `normalized_graph_sha256` makes `--check fingerprint.provisioning.json` fail.

- [ ] **Step 6: Pass focused integration tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_reproduce_harness.py tests\test_windows_reproduce.py tests\test_fingerprint.py tests\test_uv_lock_support.py -q
```

Expected: all pass; fake PyPI/Tsinghua failures select Aliyun with exact attempts and no root-lock/worktree changes.

- [ ] **Step 7: Commit Task 5**

```powershell
git add scripts\reproduce.ps1 tests\harness_fake.py tests\test_reproduce_harness.py tests\test_windows_reproduce.py tests\test_fingerprint.py
git commit -m "feat: orchestrate strict uv mirror failover"
```

Independent gate: execute the harness, inspect state ordering and failure diagnostics, verify source switching does not change the provisioning fingerprint, and confirm a graph digest change invalidates resume before Task 6.

---

### Task 6: Release gate, evidence hash, and operator documentation

**Files:**
- Modify: `scripts/repro-evidence.ps1:366-420`
- Modify: `scripts/release-gate.ps1:1-118`
- Modify: `tests/test_repro_artifacts.py`
- Modify: `tests/test_release_gate.py`
- Modify: `tests/test_readme_consistency.py`
- Modify: `README.md:240-245, 360-386`
- Modify: `docs/pitfalls.md:43-74, 169-185`
- Modify: `AGENTS.md:114-125, 278-290`

**Interfaces:**
- Consumes: `<evidenceDir>/environment-lock.json` from Task 5.
- Produces: `artifact-hashes.json.environment_lock` SHA-256.
- Release check: Task 1 CLI over the tracked catalog plus inclusion of both variants and manifest in release SHA256SUMS.

- [ ] **Step 1: Write failing evidence and release tests**

Assert `Write-ArtifactHashes` accepts `-EnvironmentLockFile`, emits `environment_lock`, and hashes the exact record. Assert the release gate names `locks/uv.tuna.lock`, `locks/uv.aliyun.lock`, `locks/manifest.json`, and `verify_uv_lock_variants.py`, and its parser stays clean. Add README consistency assertions for three source IDs and strict `--locked` fallback.

- [ ] **Step 2: Run the focused tests and confirm the red state**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_repro_artifacts.py tests\test_release_gate.py tests\test_readme_consistency.py -q
```

Expected: new assertions fail because the evidence and release surfaces do not yet contain the catalog.

- [ ] **Step 3: Bind environment provenance into artifact hashes**

Add `[string] $EnvironmentLockFile = ""` to `Write-ArtifactHashes`, assign `$hashes.environment_lock = Get-FileSha256 $EnvironmentLockFile`, and pass `$environmentLockFile` from `reproduce.ps1` evidence.pack. Keep the environment-lock file itself authoritative; do not duplicate its source fields in `artifact-hashes.json`.

- [ ] **Step 4: Gate and hash the full release catalog**

Before release success, execute the locked Python interpreter against:

```powershell
scripts\verify_uv_lock_variants.py --root $rootDir --manifest locks\manifest.json
```

Fail on non-zero. Add the two variants and manifest to both required-file checks and SHA256SUMS. The root lock remains a separate canonical release artifact.

- [ ] **Step 5: Document symptom, cause, fix, and verification**

Update the setup order to run `detect-mirrors.ps1` before orchestrated Python sync. In `docs/pitfalls.md`, add a dedicated anchored entry for `uv sync --locked` reporting `lockfile needs to be updated` under inherited/mirror indexes: explain single-source uv locks, direct users to the generator only when dependency inputs intentionally change, and verify with the catalog verifier plus matching `uv lock --check`. Add only an exception-table pointer in AGENTS.md; do not inline the fix there.

- [ ] **Step 6: Run focused docs/evidence/release checks**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_repro_artifacts.py tests\test_release_gate.py tests\test_readme_consistency.py tests\test_markdown_links.py -q
powershell -NoProfile -Command "$paths='scripts\repro-evidence.ps1','scripts\release-gate.ps1','scripts\reproduce.ps1';foreach($p in $paths){$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$t,[ref]$e);if($e.Count){$e|% Message;exit 1}}"
```

Expected: all tests pass and all three scripts parse under Windows PowerShell 5.1.

- [ ] **Step 7: Commit Task 6**

```powershell
git add scripts\repro-evidence.ps1 scripts\release-gate.ps1 scripts\reproduce.ps1 tests\test_repro_artifacts.py tests\test_release_gate.py tests\test_readme_consistency.py README.md docs\pitfalls.md AGENTS.md
git commit -m "docs: document strict uv mirror failover"
```

Independent gate: verify documentation matches actual commands, the release gate fails for each catalog corruption, environment provenance is hashed, links resolve, and no fix logic was inlined into AGENTS.md before Task 7.

---

### Task 7: Full regression, live-source acceptance, and HIP smoke continuation

**Files:**
- No planned source changes.
- Generated only: `mirrors.env`, `mirrors.json`, `.venv/`, and `outputs/reproduction/hip-smoke-10/`.

**Interfaces:**
- Consumes: complete implementation from Tasks 1-6.
- Produces: verified test output, live source check matrix, `hip-smoke-10` evidence pack, and independent acceptance decision.

- [ ] **Step 1: Run static and focused gates from a clean task commit**

```powershell
git diff --check
.\.venv\Scripts\python.exe scripts\verify_uv_lock_variants.py --root . --manifest locks\manifest.json
.\.venv\Scripts\python.exe -m pytest tests\test_uv_lock_variants.py tests\test_uv_lock_generation.py tests\test_detect_mirrors.py tests\test_uv_lock_support.py tests\test_reproduce_harness.py tests\test_repro_artifacts.py tests\test_fingerprint.py tests\test_release_gate.py -q
```

Expected: no diff errors, catalog verifier exits 0, all focused tests pass.

- [ ] **Step 2: Run the complete repository suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: the entire suite passes with no new skip or xfail introduced for mirror behavior.

- [ ] **Step 3: Run real detector and per-source network acceptance**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\detect-mirrors.ps1
```

For every entry whose `reachable` is true, use its matching tracked lock in an external temporary project and run both `uv lock --check --no-config ... --default-index <url>` and `uv sync --locked --all-groups --no-config ... --default-index <url> --index-strategy first-index` with a separate temporary venv. Record exit code, uv version, elapsed time, and lock SHA. Record genuinely unreachable entries as SKIP with the detector result; do not weaken deterministic fake-source acceptance.

- [ ] **Step 4: Confirm caller environment and repository are unchanged**

Compare before/after values and presence for all controlled uv variables, canonical `uv.lock` SHA-256, and `git status --porcelain=v1 --untracked-files=all`. Expected: exact equality except for documented gitignored generated files and evidence.

- [ ] **Step 5: Resume the blocked HIP smoke profile**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile hip-smoke-10 `
  -SeedFrom C:\Users\rocm\Desktop\omnidocbench-amd-windows `
  -SkipCdmSetup `
  -Resume
```

If the prior state cannot be resumed because the approved dependency fingerprint changed, start the same profile fresh only after preserving the failed state/evidence directory for diagnosis. Expected: strict environment sync selects a verified source, backend proof remains HIP with no CPU fallback, 10-page inference/scoring completes, and the evidence pack passes final verification.

- [ ] **Step 6: Independently audit the acceptance evidence**

A fresh subagent that made no implementation edits must inspect test output, all three source attempts, `environment-lock.json`, provisioning fingerprint spec/result, state stage order, backend proof, prediction summary, metrics summary, artifact hashes, root-lock hash, and git status. It must return `APPROVED` with no critical or important issues before the mirror blocker is declared fixed.

- [ ] **Step 7: Record the accepted task state**

If Task 7 required no tracked fixes, do not create an empty commit. If acceptance exposed a defect, return to the owning earlier task, add a red regression test, fix it, repeat that task's independent review, and rerun Task 7 from Step 1.

Completion gate: only after the independent audit approves may the next project milestone—formal `paddleocr-vl-hip-full-1651` reproduction—begin.
