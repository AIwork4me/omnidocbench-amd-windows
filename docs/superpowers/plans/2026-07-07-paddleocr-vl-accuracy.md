# PaddleOCR-VL-1.6 Accuracy Alignment Implementation Plan

> **For rocm:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan step-by-step.

**Goal:** Make the official PaddleOCR `doc_parser` path the default PaddleOCR-VL-1.6 reference adapter for accuracy on AMD Windows, keep the current ONNX plus llama.cpp path as an explicit lightweight fast path, and add an accuracy verifier that fails below Overall 96.03.

**Approved design:** `docs/superpowers/specs/2026-07-07-paddleocr-vl-accuracy-design.md`

**Primary success target:** Full OmniDocBench v1.6 PaddleOCR-VL-1.6 reference run on AMD Windows must produce notebook-style Overall `>= 96.03` for the default `official` engine.

**Secondary success target:** The current lightweight engine remains runnable into `predictions/paddleocrvl_rocm_lightweight` and is clearly labeled as a fast path, not the reference accuracy baseline.

**Known diagnosis:** Current full run has only two failed pages and notebook-style Overall about 94.86. The missing pages do not explain the gap. The largest losses are table TEDS and formula CDM. A 12-page backend probe showed current vLLM-style outputs outperform direct llama.cpp server outputs on table pages, so the accuracy fix must align with the official PaddleOCR `doc_parser` pipeline rather than only changing HTTP backend flags.

## Implementation Overview

Change the adapter from a single implicit lightweight path to a dispatcher with two engines:

1. `official` default:
   - Uses official `paddleocr` `PaddleOCRVL` doc_parser pipeline.
   - Uses the configured llama.cpp server URL via `vl_rec_backend="llama-cpp-server"` and `vl_rec_server_url`.
   - Writes one Markdown file per input image to the configured output directory.
   - Uses `predictions/paddleocrvl_rocm` as the default output directory in docs and commands.

2. `lightweight` optional:
   - Moves the existing `paddleocr_vl_rocm` ONNX plus VLM code into a named engine.
   - Writes to `predictions/paddleocrvl_rocm_lightweight` in docs and validation commands.
   - Keeps the old CLI controls that matter for debugging: layout model, API model name, VLM backend.

Add a strict accuracy verifier:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify-accuracy.ps1 `
  -MinimumOverall 96.03 `
  -RunSummary \\wsl$\Ubuntu2204\root\OmniDocBench\result\paddleocrvl_rocm_cdm_quick_match_run_summary.json
```

The verifier must prefer the notebook-style run summary because the project has already found that raw `metric_result.json` TEDS aggregation and notebook-style page aggregation are not interchangeable.

## Files To Change

- `adapters/paddleocr-vl-1.6/run_adapter.py`
- `adapters/paddleocr-vl-1.6/00-install-deps/setup.ps1`
- `adapters/paddleocr-vl-1.6/01-vlm-server/setup.ps1`
- `adapters/paddleocr-vl-1.6/01-vlm-server/verify.ps1`
- `eval-infra/03-scoring/verify-accuracy.ps1` new
- `tests/test_paddleocr_vl_adapter.py` new
- `tests/test_verify_accuracy.py` new
- `tests/fixtures/accuracy_run_summary_pass.json` new
- `tests/fixtures/accuracy_run_summary_fail.json` new
- `README.md`
- `README.zh-CN.md`
- `adapters/paddleocr-vl-1.6/README.md`
- `adapters/README.md`
- `docs/pitfalls.md`
- `docs/handoff-2026-07-07.md`

## Task 1: Add Adapter Tests For Engine Selection And Markdown Writing

**Objective:** Lock the new public contract before changing the adapter.

**Files:**
- Create `tests/test_paddleocr_vl_adapter.py`.

**Test strategy:**
- Load `adapters/paddleocr-vl-1.6/run_adapter.py` by file path with `importlib.util.spec_from_file_location`.
- Do not import PaddleOCR in tests.
- Monkeypatch the engine functions so tests verify dispatch and output conventions without model downloads.
- Verify `.env.local` is read from `adapters/paddleocr-vl-1.6/.env.local`, not the repo root.

**Test code to add:**

```python
from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "adapters" / "paddleocr-vl-1.6" / "run_adapter.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("paddleocr_vl_run_adapter", ADAPTER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_engine_is_official(tmp_path, monkeypatch):
    adapter = load_adapter()
    img_dir = tmp_path / "images"
    out_dir = tmp_path / "predictions"
    img_dir.mkdir()
    (img_dir / "page.png").write_bytes(b"fake")

    calls = []

    def fake_official(**kwargs):
        calls.append(kwargs)
        output = Path(kwargs["out_dir"])
        output.mkdir(parents=True, exist_ok=True)
        (output / "page.md").write_text("# official\n", encoding="utf-8")
        return {"count": 1, "ok": 1, "fail": 0, "engine": "official"}

    monkeypatch.setattr(adapter, "run_official_folder", fake_official)

    result = adapter.run_adapter(img_dir, out_dir, server_url="http://127.0.0.1:8111")

    assert result == {"count": 1, "ok": 1, "fail": 0, "engine": "official"}
    assert calls[0]["img_dir"] == Path(img_dir)
    assert calls[0]["out_dir"] == Path(out_dir)
    assert calls[0]["server_url"] == "http://127.0.0.1:8111"


def test_lightweight_engine_is_explicit(tmp_path, monkeypatch):
    adapter = load_adapter()
    img_dir = tmp_path / "images"
    out_dir = tmp_path / "predictions"
    img_dir.mkdir()
    (img_dir / "page.png").write_bytes(b"fake")

    calls = []

    def fake_lightweight(**kwargs):
        calls.append(kwargs)
        return {"count": 1, "ok": 1, "fail": 0, "engine": "lightweight"}

    monkeypatch.setattr(adapter, "run_lightweight_folder", fake_lightweight)

    result = adapter.run_adapter(
        img_dir,
        out_dir,
        server_url="http://127.0.0.1:8111",
        engine="lightweight",
    )

    assert result["engine"] == "lightweight"
    assert calls[0]["img_dir"] == Path(img_dir)


def test_expected_md_name_preserves_image_stem():
    adapter = load_adapter()

    assert adapter.expected_md_name("abc.page-01.png") == "abc.page-01.md"
    assert adapter.expected_md_name("scan.JPG") == "scan.md"


def test_env_local_is_read_from_adapter_directory(tmp_path, monkeypatch):
    adapter = load_adapter()
    adapter_env = Path(adapter.__file__).resolve().parent / ".env.local"
    original_text = adapter_env.read_text(encoding="utf-8") if adapter_env.exists() else None
    try:
        adapter_env.write_text(
            "VL_REC_SERVER_URL=http://example.test:8111\n"
            "VL_REC_API_MODEL_NAME=OfficialModelName\n",
            encoding="utf-8",
        )
        env = adapter._read_env_local(adapter.ADAPTER_DIR)

        assert env["VL_REC_SERVER_URL"] == "http://example.test:8111"
        assert env["VL_REC_API_MODEL_NAME"] == "OfficialModelName"
    finally:
        if original_text is None:
            adapter_env.unlink(missing_ok=True)
        else:
            adapter_env.write_text(original_text, encoding="utf-8")
```

**Run and expect failure before implementation:**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_paddleocr_vl_adapter.py -q
```

Expected failure:

```text
FAILED tests/test_paddleocr_vl_adapter.py::test_default_engine_is_official
FAILED tests/test_paddleocr_vl_adapter.py::test_lightweight_engine_is_explicit
```

**Commit after green:** `test: cover PaddleOCR-VL adapter engine dispatch`

## Task 2: Refactor `run_adapter.py` Into Official Default Plus Lightweight Optional Engine

**Objective:** Implement the tested adapter contract while preserving the existing public `run_adapter(img_dir, out_dir, server_url)` call shape.

**Files:**
- Modify `adapters/paddleocr-vl-1.6/run_adapter.py`.

**Implementation details:**

1. Add module constants:

```python
ADAPTER_DIR = Path(__file__).resolve().parent
REPO_ROOT = ADAPTER_DIR.parents[1]
DEFAULT_SERVER_URL = "http://127.0.0.1:8111"
DEFAULT_ENGINE = "official"
LIGHTWEIGHT_DEFAULT_OUT_DIR = REPO_ROOT / "predictions" / "paddleocrvl_rocm_lightweight"
OFFICIAL_DEFAULT_OUT_DIR = REPO_ROOT / "predictions" / "paddleocrvl_rocm"
```

2. Keep `_read_env_local`, but pass `ADAPTER_DIR` so it reads `adapters/paddleocr-vl-1.6/.env.local`.

```python
def _read_env_local(adapter_dir: Path = ADAPTER_DIR) -> dict[str, str]:
    env_path = adapter_dir / ".env.local"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values
```

3. Keep current image naming:

```python
def expected_md_name(image_name: str) -> str:
    return f"{Path(image_name).stem}.md"
```

4. Add `run_lightweight_folder` by moving the existing `process_folder` body into a function with this signature:

```python
def run_lightweight_folder(
    *,
    img_dir: Path,
    out_dir: Path,
    layout_model: Path,
    server_url: str,
    api_model_name: str,
    vlm_backend: str,
) -> dict[str, int | str]:
    ...
```

Return shape:

```python
return {
    "count": count,
    "ok": ok,
    "fail": fail,
    "engine": "lightweight",
}
```

5. Add official result Markdown extraction. The official PaddleOCR pipeline has changed result helpers across releases, so implement an ordered extractor with explicit failures instead of assuming one method exists.

```python
def _official_result_to_markdown(result: object) -> str:
    if isinstance(result, str):
        return result

    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return markdown

    for method_name in ("to_markdown", "export_markdown", "save_to_markdown"):
        method = getattr(result, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, str):
                return value

    json_value = getattr(result, "json", None)
    if isinstance(json_value, dict):
        for key in ("markdown", "md", "content"):
            value = json_value.get(key)
            if isinstance(value, str):
                return value

    raise TypeError(
        "Official PaddleOCRVL result did not expose markdown via "
        "markdown, to_markdown(), export_markdown(), save_to_markdown(), or json"
    )
```

6. Add official folder runner.

```python
def run_official_folder(
    *,
    img_dir: Path,
    out_dir: Path,
    server_url: str,
    pipeline_version: str = "v1.6",
) -> dict[str, int | str]:
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise RuntimeError(
            "Official engine requires PaddleOCR doc_parser dependencies. "
            "Run adapters\\paddleocr-vl-1.6\\00-install-deps\\setup.ps1."
        ) from exc

    img_dir = Path(img_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    error_log = out_dir / "_errors.log"
    stats_path = out_dir / "_run_stats.json"
    for path in (error_log, stats_path):
        path.unlink(missing_ok=True)

    pipeline = PaddleOCRVL(
        pipeline_version=pipeline_version,
        vl_rec_backend="llama-cpp-server",
        vl_rec_server_url=server_url,
    )

    images = sorted(
        p for p in img_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    count = len(images)
    ok = 0
    fail = 0

    for image_path in images:
        try:
            result = pipeline.predict(str(image_path))
            if isinstance(result, list):
                markdown = "\n\n".join(_official_result_to_markdown(item) for item in result)
            else:
                markdown = _official_result_to_markdown(result)
            (out_dir / expected_md_name(image_path.name)).write_text(markdown, encoding="utf-8")
            ok += 1
            print(f"[OK] {image_path.name}")
        except Exception as exc:
            fail += 1
            with error_log.open("a", encoding="utf-8") as fh:
                fh.write(f"{image_path.name}\t{type(exc).__name__}: {exc}\n")
            print(f"[FAIL] {image_path.name}: {exc}")

    stats = {"count": count, "ok": ok, "fail": fail, "engine": "official"}
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    if count and fail > count / 2:
        raise SystemExit(2)
    return stats
```

7. Add dispatcher:

```python
def run_adapter(
    img_dir: str | Path,
    out_dir: str | Path,
    server_url: str = "",
    *,
    engine: str = DEFAULT_ENGINE,
    layout_model: str | Path | None = None,
    api_model_name: str | None = None,
    vlm_backend: str = "vllm-server",
) -> dict[str, int | str]:
    env = _read_env_local(ADAPTER_DIR)
    server_url = server_url or env.get("VL_REC_SERVER_URL") or DEFAULT_SERVER_URL
    engine = engine.lower().strip()

    if engine == "official":
        return run_official_folder(
            img_dir=Path(img_dir),
            out_dir=Path(out_dir),
            server_url=server_url,
            pipeline_version=env.get("PADDLEOCR_VL_PIPELINE_VERSION", "v1.6"),
        )

    if engine == "lightweight":
        return run_lightweight_folder(
            img_dir=Path(img_dir),
            out_dir=Path(out_dir),
            layout_model=Path(layout_model) if layout_model else _layout_default(),
            server_url=server_url,
            api_model_name=api_model_name or env.get("VL_REC_API_MODEL_NAME") or _api_model_default(),
            vlm_backend=vlm_backend,
        )

    raise ValueError(f"Unsupported engine '{engine}'. Use official or lightweight.")
```

8. Update CLI:

```python
parser.add_argument(
    "--engine",
    choices=["official", "lightweight"],
    default=os.environ.get("PADDLEOCR_VL_ENGINE", DEFAULT_ENGINE),
    help="Adapter engine. official is the reference accuracy path; lightweight is the fast ONNX plus llama.cpp path.",
)
```

Default `--out-dir` must remain optional and depend on engine:

```python
default_out_dir = OFFICIAL_DEFAULT_OUT_DIR if args.engine == "official" else LIGHTWEIGHT_DEFAULT_OUT_DIR
out_dir = Path(args.out_dir) if args.out_dir else default_out_dir
```

**Run tests:**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_paddleocr_vl_adapter.py -q
```

Expected:

```text
4 passed
```

**Manual smoke without model import:**

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py --help
```

Expected:

```text
--engine {official,lightweight}
```

**Commit:** `feat: make official PaddleOCRVL adapter the default`

## Task 3: Verify Official PaddleOCR Markdown API Against Installed Package

**Objective:** Replace the generic `_official_result_to_markdown` fallbacks with the exact official API path if the installed PaddleOCR version exposes a preferred save method.

**Commands:**

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1 -Mode official
.venv\Scripts\python.exe - <<'PY'
from paddleocr import PaddleOCRVL
import inspect

print("PaddleOCRVL:", PaddleOCRVL)
print("init:", inspect.signature(PaddleOCRVL))
pipeline = PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="llama-cpp-server", vl_rec_server_url="http://127.0.0.1:8111")
print("predict:", inspect.signature(pipeline.predict))
PY
```

If PowerShell here-doc syntax is inconvenient on Windows, use:

```powershell
@'
from paddleocr import PaddleOCRVL
import inspect
print("PaddleOCRVL:", PaddleOCRVL)
print("init:", inspect.signature(PaddleOCRVL))
pipeline = PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="llama-cpp-server", vl_rec_server_url="http://127.0.0.1:8111")
print("predict:", inspect.signature(pipeline.predict))
'@ | .venv\Scripts\python.exe -
```

Then run one-page prediction on an existing image:

```powershell
$probe = Join-Path $env:TEMP "odb_official_api_probe"
Remove-Item -Recurse -Force $probe -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$probe\images" | Out-Null
Copy-Item (Get-ChildItem eval-infra\01-omnidocbench\data\images\*.jpg, eval-infra\01-omnidocbench\data\images\*.png | Select-Object -First 1).FullName "$probe\images"
python adapters\paddleocr-vl-1.6\run_adapter.py --engine official --img-dir "$probe\images" --out-dir "$probe\pred"
Get-ChildItem "$probe\pred"
```

Expected:

```text
_run_stats.json
007cac05dc9676ad25c67ce1344547839b6c9d586558529e20a09564d2fb12cf.md
```

If the official result object exposes a better method such as `save_to_markdown(save_path=...)`, update `_official_result_to_markdown` and add a unit test with a fake object that matches the observed method signature.

**Commit if code changed:** `fix: use official PaddleOCRVL markdown export API`

## Task 4: Update Dependency Installer For Official And Lightweight Modes

**Objective:** Make the official doc_parser dependencies the default install while preserving lightweight dependencies for the optional path.

**Files:**
- Modify `adapters/paddleocr-vl-1.6/00-install-deps/setup.ps1`.

**PowerShell behavior:**

Add parameters:

```powershell
param(
  [ValidateSet("all", "official", "lightweight")]
  [string]$Mode = "all"
)
```

Default `all` installs both:
- Official: `paddleocr[doc-parser]` package version that supports `PaddleOCRVL(pipeline_version="v1.6")`.
- Lightweight: current `PaddleOCR-VL-ROCm` clone and editable install.

Use idempotent checks:

```powershell
function Test-OfficialPaddleOCRVL {
  & $Python -c "from paddleocr import PaddleOCRVL; p=PaddleOCRVL; print('PaddleOCRVL OK')" *> $null
  return ($LASTEXITCODE -eq 0)
}

function Test-LightweightPaddleOCRVL {
  & $Python -c "import paddleocr_vl_rocm; print('paddleocr_vl_rocm OK')" *> $null
  return ($LASTEXITCODE -eq 0)
}
```

Official install command:

```powershell
& $Python -m pip install --upgrade "paddleocr[doc-parser]==3.6.0"
```

Record the package pin in the script:

```powershell
$OfficialPaddleOCRPackage = "paddleocr[doc-parser]==3.6.0"
```

This pin is deliberate: PaddleOCR 3.6.0 is the dated PaddleOCR release that introduced PaddleOCR-VL-1.6. The implementation step still verifies `PaddleOCRVL(pipeline_version="v1.6")` by import and one-page prediction before full scoring.

Keep the existing mirror handling and clone path for lightweight. Keep the current `pip install -e "$CloneDir[gpu]"` behavior in the lightweight section.

**Verification commands:**

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1 -Mode official
.venv\Scripts\python.exe -c "from paddleocr import PaddleOCRVL; print(PaddleOCRVL)"

powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1 -Mode lightweight
.venv\Scripts\python.exe -c "import paddleocr_vl_rocm; print('lightweight ok')"
```

Expected:

```text
PaddleOCRVL
lightweight ok
```

**Commit:** `build: install official PaddleOCR doc parser dependencies`

## Task 5: Align llama.cpp Server Setup And Verification With Official Path

**Objective:** Make VLM server setup official-compatible by default and remove the false model-name warning when `/v1/models` returns a full path.

**Files:**
- Modify `adapters/paddleocr-vl-1.6/01-vlm-server/setup.ps1`.
- Modify `adapters/paddleocr-vl-1.6/01-vlm-server/verify.ps1`.

**Setup changes:**

1. Keep the current HIP and CPU variant support.
2. Add a `-ServerMode` parameter:

```powershell
param(
  [ValidateSet("hip", "cpu")]
  [string]$Variant = "hip",
  [ValidateSet("official", "fast")]
  [string]$ServerMode = "official"
)
```

3. For `official`, start llama-server with only compatibility flags:

```powershell
$Args = @(
  "-m", $ModelPath,
  "--mmproj", $MmprojPath,
  "--host", "127.0.0.1",
  "--port", "$Port",
  "--temp", "0"
)
```

4. Keep current tuned flags under `-ServerMode fast`. The fast mode is for the lightweight adapter and can be used only after fixed-probe output equivalence is shown.

5. Write `.env.local` to the adapter directory with:

```text
VL_REC_SERVER_URL=http://127.0.0.1:8111
VL_REC_API_MODEL_NAME=PaddleOCR-VL-1.6-GGUF.gguf
PADDLEOCR_VL_ENGINE=official
```

**Verify changes:**

Update model matching to accept:

```powershell
$expectedModel = $envValues["VL_REC_API_MODEL_NAME"]
$matchesExpected = $false
foreach ($id in $ids) {
  if ($id -eq $expectedModel) { $matchesExpected = $true }
  if ([System.IO.Path]::GetFileName($id) -eq $expectedModel) { $matchesExpected = $true }
  if ($id -like "*$expectedModel") { $matchesExpected = $true }
}
```

If `$matchesExpected` is false, keep a warning but do not fail. `/v1/models` 200 remains the health criterion.

**Commands:**

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip -ServerMode official
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
```

Expected:

```text
HTTP 200 from /v1/models
```

Human intervention point remains active:

```text
⚠️ VLM server started. Please confirm GPU utilization (e.g. rocm-smi / Task Manager) and that the server stays up, then I will continue.
```

**Commit:** `fix: align PaddleOCRVL server mode with official adapter`

## Task 6: Add Accuracy Verifier And Fixture Tests

**Objective:** Add a command that enforces Overall `>= 96.03` using notebook-style aggregation.

**Files:**
- Create `eval-infra/03-scoring/verify-accuracy.ps1`.
- Create `tests/test_verify_accuracy.py`.
- Create `tests/fixtures/accuracy_run_summary_pass.json`.
- Create `tests/fixtures/accuracy_run_summary_fail.json`.

**Fixture pass file:**

```json
{
  "overall_notebook": 96.04,
  "metrics": {
    "text_block_Edit_dist": { "notebook_value": 0.03 },
    "display_formula_CDM": { "notebook_value": 94.5 },
    "table_TEDS": { "notebook_value": 96.1 },
    "reading_order_Edit_dist": { "notebook_value": 0.12 }
  }
}
```

**Fixture fail file:**

```json
{
  "overall_notebook": 94.85,
  "metrics": {
    "text_block_Edit_dist": { "notebook_value": 0.035 },
    "display_formula_CDM": { "notebook_value": 93.99 },
    "table_TEDS": { "notebook_value": 94.10 },
    "reading_order_Edit_dist": { "notebook_value": 0.129 }
  }
}
```

**PowerShell verifier behavior:**

```powershell
param(
  [double]$MinimumOverall = 96.03,
  [string]$RunSummary = "",
  [string]$SaveName = "paddleocrvl_rocm_cdm_quick_match",
  [string]$ResultDir = "",
  [switch]$AllowMissing
)
```

If `-RunSummary` is omitted:
- First check `\\wsl$\Ubuntu2204\root\OmniDocBench\result\$SaveName` plus `_run_summary.json`.
- Then check `eval-infra\01-omnidocbench\OmniDocBench\result\$SaveName` plus `_run_summary.json`.
- Then search both result directories for `*run_summary.json` and pick the newest file containing the save name.

Implementation core:

```powershell
$summary = Get-Content -LiteralPath $RunSummary -Raw -Encoding UTF8 | ConvertFrom-Json
$overall = [double]$summary.overall_notebook
if ($overall -lt $MinimumOverall) {
  Write-Host ("VERIFY ACCURACY FAIL: Overall {0:N4} < required {1:N2}" -f $overall, $MinimumOverall)
  exit 1
}
Write-Host ("VERIFY ACCURACY OK: Overall {0:N4} >= required {1:N2}" -f $overall, $MinimumOverall)
exit 0
```

Also print the component metrics if available:

```powershell
foreach ($name in @("text_block_Edit_dist", "display_formula_CDM", "table_TEDS", "reading_order_Edit_dist")) {
  if ($summary.metrics.$name) {
    Write-Host ("  {0}: {1}" -f $name, $summary.metrics.$name.notebook_value)
  }
}
```

**Test code:**

```python
from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "eval-infra" / "03-scoring" / "verify-accuracy.ps1"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def run_verify(summary: Path, minimum: str = "96.03") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RunSummary",
            str(summary),
            "-MinimumOverall",
            minimum,
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_verify_accuracy_passes_when_overall_meets_threshold():
    result = run_verify(FIXTURES / "accuracy_run_summary_pass.json")

    assert result.returncode == 0, result.stdout
    assert "VERIFY ACCURACY OK" in result.stdout


def test_verify_accuracy_fails_when_overall_is_below_threshold():
    result = run_verify(FIXTURES / "accuracy_run_summary_fail.json")

    assert result.returncode == 1
    assert "VERIFY ACCURACY FAIL" in result.stdout
```

**Run and expect failure before script exists:**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_verify_accuracy.py -q
```

Expected first failure:

```text
The argument 'eval-infra\03-scoring\verify-accuracy.ps1' to the -File parameter does not exist.
```

**Run after implementation:**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_verify_accuracy.py -q
```

Expected:

```text
2 passed
```

**Commit:** `feat: enforce PaddleOCRVL reference accuracy threshold`

## Task 7: Update Documentation And Pitfalls

**Objective:** Make the official default and lightweight optional path obvious to future users and agents.

**Files:**
- `README.md`
- `README.zh-CN.md`
- `adapters/README.md`
- `adapters/paddleocr-vl-1.6/README.md`
- `docs/pitfalls.md`
- `docs/handoff-2026-07-07.md`

**README changes:**

Add a reference adapter section with this command block:

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1 -Mode all
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip -ServerMode official
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine official `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\paddleocrvl_rocm
```

Add lightweight command block:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine lightweight `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\paddleocrvl_rocm_lightweight
```

Add scoring verification:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify-accuracy.ps1 -MinimumOverall 96.03
```

Clarify:
- `predictions/paddleocrvl_rocm` is the reference accuracy output.
- `predictions/paddleocrvl_rocm_lightweight` is a fast optional path.
- Raw `metric_result.json` table TEDS and notebook-style run summary table TEDS are different aggregations.
- The reference pass criterion for PaddleOCR-VL-1.6 is Overall `>= 96.03`, matching official 96.33 minus 0.30 tolerance.

**Pitfalls changes:**

Add entries:

```markdown
### PaddleOCR-VL Overall below 96.03

**Symptom:** The full run succeeds and writes about 1651 Markdown files, but `verify-accuracy.ps1` reports Overall below 96.03.

**Root cause:** The run is not using the official PaddleOCR `doc_parser` pipeline, or it is using a server mode that changes official output behavior.

**Fix:** Re-run `00-install-deps/setup.ps1 -Mode all`, start `01-vlm-server/setup.ps1 -ServerMode official`, and run `run_adapter.py --engine official --out-dir predictions\paddleocrvl_rocm`.

**Verify:** Re-run scoring and `verify-accuracy.ps1 -MinimumOverall 96.03`.
```

```markdown
### Lightweight adapter scored as reference

**Symptom:** `predictions\paddleocrvl_rocm_lightweight` is scored as if it were the reference PaddleOCR-VL-1.6 result.

**Root cause:** The lightweight ONNX plus llama.cpp path is intended for quick iteration and debugging, not the official accuracy baseline.

**Fix:** Use `predictions\paddleocrvl_rocm` for the official reference adapter and keep lightweight results in a separate prediction directory.

**Verify:** Check `_run_stats.json` contains `"engine": "official"` before final scoring.
```

**Handoff update:**

Append a dated note:

```markdown
## 2026-07-07 Accuracy Alignment Decision

The project now treats official PaddleOCR `doc_parser` as the default PaddleOCR-VL-1.6 reference adapter. The previous ONNX plus llama.cpp implementation remains available as `--engine lightweight` and should write to `predictions/paddleocrvl_rocm_lightweight`.

Reference acceptance is Overall >= 96.03, enforced by `eval-infra/03-scoring/verify-accuracy.ps1`.
```

**Verification:**

```powershell
rg -n "paddleocrvl_rocm_lightweight|verify-accuracy|96\.03|--engine official" README.md README.zh-CN.md adapters docs
```

Expected:

```text
matches in README.md, README.zh-CN.md, adapters/paddleocr-vl-1.6/README.md, docs/pitfalls.md, docs/handoff-2026-07-07.md
```

**Commit:** `docs: document official PaddleOCRVL accuracy path`

## Task 8: Run Focused Validation On Unit Tests And 12-Page Probe

**Objective:** Verify the wiring before spending hours on a full benchmark run.

**Commands:**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_paddleocr_vl_adapter.py tests\test_verify_accuracy.py -q
python adapters\paddleocr-vl-1.6\run_adapter.py --help
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
```

Expected:

```text
6 passed
--engine {official,lightweight}
HTTP 200 from /v1/models
```

Create 12-page probe using the same page IDs from the diagnostic run:

```powershell
$probe = Join-Path $env:TEMP "odb_official_probe_20260707"
Remove-Item -Recurse -Force $probe -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$probe\images" | Out-Null
$ids = @(
  "007cac05dc9676ad25c67ce1344547839b6c9d586558529e20a09564d2fb12cf",
  "00d03082d26d25d88ac7a74b747a839a379920c508cd79feb67e6ba80161c3de",
  "00eb340a56addb5bdf46399114e0fbd003ba6a64b4eed13cbe36986f4570e834",
  "01b7ee0d049fb764f89e7838c1b94f89052b5fc9dafcce79e5dac10479993dd5",
  "02ed4061123eaaf55058a92c90fcd9022888d4f5eaeed7e40eb347d7e455a11f",
  "04e589e31d5159ebd2c2da80ea58ac9d752c1c6a462c4261268ccab11873faa",
  "007ee244c97031f3289aab895e7820460dba870a5cc42e6140e21d87d2b16890",
  "01b68e5f8b14d6742984529f7c0d9e72bbf5a48278309094645994dc05e78267",
  "01c012eaf019f59aedb5f64b9841d362dc5ca7d112702d80121258acc6dfd9f2",
  "01fb16f1206f137c164e5efc8250d714e29a0fb911012a44573e0272a923ba2f",
  "0214c5ff7e84a706543aeab8b17c5658df2b1cb9871b39433cd22fc31a5f7582",
  "02bb6e9e7f9b65670c51fe6e6383958b4a0bfda721fc8c910c142f29e38075f0"
)
foreach ($id in $ids) {
  $img = Get-ChildItem eval-infra\01-omnidocbench\data\images -Filter "$id.*" | Select-Object -First 1
  Copy-Item $img.FullName "$probe\images"
}
python adapters\paddleocr-vl-1.6\run_adapter.py --engine official --img-dir "$probe\images" --out-dir "$probe\pred_official"
Get-Content "$probe\pred_official\_run_stats.json"
```

Expected:

```json
{
  "count": 12,
  "ok": 12,
  "fail": 0,
  "engine": "official"
}
```

If official engine fails on more than half the probe pages, stop and inspect `_errors.log`. Do not run the full benchmark until the probe is healthy.

**Commit if fixes are made:** `fix: stabilize official PaddleOCRVL probe run`

## Task 9: Run Full Official Adapter, Score, And Enforce Accuracy

**Objective:** Produce the real reference result and prove it meets the user-approved threshold.

**Pre-checks:**

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/verify.sh
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
```

Expected:

```text
VERIFY OK
HTTP 200 from /v1/models
```

Run official adapter:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine official `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\paddleocrvl_rocm
```

Verify prediction count and engine:

```powershell
(Get-ChildItem predictions\paddleocrvl_rocm\*.md).Count
Get-Content predictions\paddleocrvl_rocm\_run_stats.json
```

Expected:

```text
1651
```

and:

```json
{
  "count": 1651,
  "ok": 1651,
  "fail": 0,
  "engine": "official"
}
```

If a few pages fail but the count remains near 1651, continue scoring only if failures are fewer than 10. If failures are 10 or more, inspect `_errors.log` first.

Score:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify-accuracy.ps1 -MinimumOverall 96.03
```

Expected:

```text
VERIFY OK
VERIFY ACCURACY OK: Overall 96.0300 or higher
```

Record final metrics in `docs/handoff-2026-07-07.md`:

```markdown
## 2026-07-07 Official Adapter Full-Run Result

- Engine: official PaddleOCR doc_parser
- Predictions: predictions/paddleocrvl_rocm
- Pages: fill from `predictions/paddleocrvl_rocm\_run_stats.json`
- Overall notebook: fill from `*_run_summary.json`
- Text Edit-distance: fill from `*_run_summary.json`
- Formula CDM: fill from `*_run_summary.json`
- Table TEDS notebook: fill from `*_run_summary.json`
- Reading-order Edit-distance: fill from `*_run_summary.json`
- Accuracy gate: PASS, Overall >= 96.03
```

**Commit:** `test: record official PaddleOCRVL accuracy verification`

## Task 10: Run Lightweight Smoke To Preserve Optional Path

**Objective:** Ensure the old fast path still runs after refactor.

**Commands:**

```powershell
$probe = Join-Path $env:TEMP "odb_lightweight_smoke_20260707"
Remove-Item -Recurse -Force $probe -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$probe\images" | Out-Null
Copy-Item (Get-ChildItem eval-infra\01-omnidocbench\data\images\*.jpg, eval-infra\01-omnidocbench\data\images\*.png | Select-Object -First 3).FullName "$probe\images"
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine lightweight `
  --img-dir "$probe\images" `
  --out-dir "$probe\pred_lightweight"
Get-Content "$probe\pred_lightweight\_run_stats.json"
```

Expected:

```json
{
  "count": 3,
  "ok": 3,
  "fail": 0,
  "engine": "lightweight"
}
```

If this fails because the lightweight package is not installed, run:

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1 -Mode lightweight
```

Then repeat the smoke.

**Commit if fixes are made:** `fix: preserve lightweight PaddleOCRVL adapter path`

## Task 11: Full Regression Verification

**Objective:** Prove the repo is coherent after all changes.

**Commands:**

```powershell
git diff --check
.venv\Scripts\python.exe -m pytest tests\test_paddleocr_vl_adapter.py tests\test_verify_accuracy.py -q
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify-accuracy.ps1 -MinimumOverall 96.03
```

Expected:

```text
no git diff --check errors
6 passed
VERIFY OK
VERIFY ACCURACY OK
```

If `scripts\full-verify.ps1` is too expensive after a just-completed full score, run the component verifies instead and state that full-verify was skipped because the identical component checks already passed:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/verify.sh
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify-accuracy.ps1 -MinimumOverall 96.03
```

**Final commit:** `chore: verify PaddleOCRVL official accuracy baseline`

## Task 12: Self-Review Before Handoff

**Objective:** Catch confusing wording, path mismatches, and accidental reference to lightweight results as the official baseline.

**Commands:**

```powershell
git status --short
git diff --stat
git diff -- adapters\paddleocr-vl-1.6\run_adapter.py eval-infra\03-scoring\verify-accuracy.ps1 README.md README.zh-CN.md
rg -n "paddleocrvl_rocm_lightweight|PADDLEOCR_VL_ENGINE|verify-accuracy|96\.03|Overall" .
```

Review checklist:

- `run_adapter.py` default engine is `official`.
- `run_adapter.py` `run_adapter(img_dir, out_dir, server_url)` still works.
- Official output directory in docs is `predictions\paddleocrvl_rocm`.
- Lightweight output directory in docs is `predictions\paddleocrvl_rocm_lightweight`.
- Accuracy verifier reads notebook-style `overall_notebook`.
- `verify.ps1` still checks non-zero metrics; `verify-accuracy.ps1` adds the strict 96.03 gate.
- README and handoff do not claim raw TEDS is interchangeable with notebook TEDS.
- No existing unrelated dirty files are reverted.

**Completion criteria:**

- Unit tests pass.
- Official probe produces Markdown and `_run_stats.json` with `"engine": "official"`.
- Full official predictions exist for about 1651 pages.
- Standard scorer verifies all four metrics are non-zero.
- Accuracy verifier passes Overall `>= 96.03`.
- Lightweight smoke still produces Markdown.
