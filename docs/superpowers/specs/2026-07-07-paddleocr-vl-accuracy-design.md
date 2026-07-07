# PaddleOCR-VL-1.6 Accuracy Alignment Design

Date: 2026-07-07
Status: Approved for implementation planning

## Goal

Make `omnidocbench-amd-windows` a credible AMD Ryzen AI MAX+ 395 Windows evaluation project by changing the PaddleOCR-VL-1.6 reference adapter from the current lightweight reimplementation to the official PaddleOCR `doc_parser` pipeline as the default accuracy path.

The concrete success gate is:

- PaddleOCR-VL-1.6 on OmniDocBench v1.6 must report `Overall >= 96.03`.
- The result must be supported by full-set scoring evidence, not by a narrow probe or hand-computed number.
- The existing ONNX + llama.cpp lightweight path remains available as an optional fast path, clearly labeled as lower-accuracy and not used as the default reference score.

## Evidence So Far

The current default path produces 1,649 Markdown predictions out of 1,651 pages. Missing pages cannot explain the full gap.

Current full-set scores from the existing lightweight path, as shown in the current README/raw-mixed table:

| Metric | Current | Official | Gap |
|---|---:|---:|---:|
| Overall | 94.63 | 96.33 | -1.70 |
| Text Edit-distance | 0.035 | 0.033 | +0.002 |
| Reading-order Edit-distance | 0.130 | 0.127 | +0.003 |
| Table TEDS raw aggregate | 0.930 | 0.948 | -0.018 |
| Formula CDM | 0.944 | 0.975 | -0.031 |

The existing WSL CDM run summary also contains an OmniDocBench notebook aggregation:

| Metric | Current notebook value |
|---|---:|
| Overall | 94.859 |
| Text Edit-distance | 0.0352 |
| Table TEDS | 94.103 |
| Formula CDM | 93.998 |

Important observations:

- The GGUF files are BF16, not a low-bit quantization. Metadata inspection showed BF16 tensors for the model and mmproj.
- A 12-page A/B probe changing `vllm-server` to `llama-cpp-server` did not improve formula Edit-distance and made the small table sample worse. The backend flag mismatch is an engineering bug, but not the main accuracy root cause.
- Prior handoff evidence in `../PaddleOCR-VL-ROCm/docs/superpowers/handoff/2026-06-27-resume-after-wsl.md` already ruled out simple quantization, table parser span loss, and pure llama.cpp numerical drift for the table gap.
- README currently mixes raw table TEDS and OmniDocBench notebook-style table TEDS in places. That weakens the credibility of score claims and must be fixed during implementation.

The likely root cause is architectural: the current reference adapter uses the separate `PaddleOCR-VL-ROCm` lightweight pipeline, not the official PaddleOCR `doc_parser` pipeline used by official documentation and expected framework comparisons.

## User-Approved Direction

The project will use the official PaddleOCR `doc_parser` path as the default PaddleOCR-VL-1.6 reference adapter.

The current lightweight ONNX + llama.cpp path will remain available as an optional fast path for debugging, speed comparisons, and environments where official PaddleOCR dependencies are not viable.

## Architecture

### Adapter Modes

`adapters/paddleocr-vl-1.6/` will expose two engines:

| Engine | Role | Output directory | Status |
|---|---|---|---|
| `official` | Default reference and accuracy baseline | `predictions/paddleocrvl_rocm` | Must satisfy `Overall >= 96.03` |
| `lightweight` | Optional fast/experimental path | `predictions/paddleocrvl_rocm_lightweight` | Must stay runnable, but does not define success |

`run_adapter.py` keeps the public adapter contract:

```python
def run_adapter(img_dir: Path, out_dir: Path, server_url: str = "") -> dict:
    """Write out_dir/<image_stem>.md for every page image in img_dir."""
```

The CLI gains an engine selector:

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
  --engine official `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\paddleocrvl_rocm
```

The default value is `official`.

### Official Engine

The official engine uses PaddleOCR's public API:

```python
from paddleocr import PaddleOCRVL

pipeline = PaddleOCRVL(
    pipeline_version="v1.6",
    vl_rec_backend="llama-cpp-server",
    vl_rec_server_url=server_url,
)
```

For each image:

1. Run `pipeline.predict(image_path)`.
2. Save PaddleOCR's Markdown result to `out_dir/<stem>.md`.
3. Record per-page status in `_run_stats.json`.
4. Continue on per-page failure and append diagnostics to `_errors.log`.

The exact save API must be verified against the installed PaddleOCR version during implementation. If the API produces a directory rather than a raw string, the adapter will read back the generated Markdown and copy it to the flat OmniDocBench prediction directory.

### Lightweight Engine

The lightweight engine is the current behavior:

- PP-DocLayoutV3 ONNX layout detection through `paddleocr_vl_rocm`.
- llama.cpp-served PaddleOCR-VL-1.6 GGUF VLM.
- Flat Markdown output.

It will be moved behind `--engine lightweight` and implemented as a small helper module called by `run_adapter.py`.

The setup scripts must continue to provision its dependencies because they are still useful for fast probes and constrained setups.

## Provisioning

The adapter setup must distinguish official accuracy dependencies from lightweight fast-path dependencies.

### Official Dependencies

`00-install-deps/setup.ps1` will install:

- Official `paddleocr[doc-parser]`, pinned to a version that supports PaddleOCR-VL-1.6.
- Official PaddleOCR runtime requirements needed for Windows + AMD CPU/layout + llama.cpp VLM service mode.
- Any special safetensors dependency required by the official documentation.

The script must be idempotent and must use the repo `.venv` by default.

If PaddleOCR's official package cannot run natively on Windows for this mode, the implementation must stop and document the real blocker. It must not silently fall back to the lightweight engine while claiming official-reference accuracy.

### VLM Server

`01-vlm-server/setup.ps1` remains responsible for llama.cpp and the PaddleOCR-VL-1.6 GGUF files.

It should prefer official-compatible server parameters first:

```powershell
llama-server `
  -m <PaddleOCR-VL-1.6-GGUF.gguf> `
  --mmproj <PaddleOCR-VL-1.6-GGUF-mmproj.gguf> `
  --host 127.0.0.1 `
  --port 8111 `
  --temp 0
```

Performance flags may be added only after they are shown not to change outputs on a fixed probe.

`verify.ps1` must accept either the full served model path or the basename when checking `/v1/models`, because current llama.cpp reports the full model path.

## Scoring And Score Gate

The score table must use one explicit aggregation policy.

For publication and pass/fail:

- Use OmniDocBench `*_run_summary.json.notebook_metric_summary` when available.
- Fall back to `*_metric_result.json` only when the notebook summary is absent, and label it as raw aggregate.
- Compute Overall from notebook values:
  - `Text accuracy = (1 - text_block_Edit_dist.notebook_value) * 100`
  - `display_formula_CDM.notebook_value` is already a percentage.
  - `table_TEDS.notebook_value` is already a percentage.
  - `Overall = (Text accuracy + display_formula_CDM.notebook_value + table_TEDS.notebook_value) / 3`

Implementation will add an accuracy verifier:

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify-accuracy.ps1 `
  -MinimumOverall 96.03
```

The verifier must report:

- Prediction directory and `.md` count.
- Text Edit-distance.
- Table TEDS.
- Formula CDM.
- Overall.
- PaddleOCR version.
- llama.cpp version/tag.
- GGUF metadata summary.
- Result file paths used as evidence.

It exits 0 only if `Overall >= 96.03` and all component metrics are present.

## Documentation

README, README.zh-CN, `adapters/README.md`, and the PaddleOCR adapter README must state:

- `official` is the default reference adapter and defines the validated PaddleOCR-VL-1.6 score.
- `lightweight` is optional and lower-accuracy on the current evidence.
- The target for successful AMD adaptation is `Overall >= 96.03`.
- Score tables use notebook aggregation unless explicitly labeled raw.
- Raw table TEDS and notebook table TEDS are not interchangeable.

The handoff and pitfalls docs should gain a short entry for "Overall below 96.03" that points to:

1. Check whether `--engine official` was used.
2. Check prediction count.
3. Check `verify-accuracy.ps1`.
4. Check llama-server health and model path.
5. Check PaddleOCR version.

## Validation Plan

Implementation must proceed through progressively stronger gates:

1. **Unit tests**
   - Engine selection defaults to `official`.
   - Lightweight engine remains callable.
   - Official engine copies or writes flat `<stem>.md`.
   - `.env.local` is read from the adapter directory, not only the repo root.

2. **12-page probe**
   - Use the same mixed formula/table probe created during investigation or recreate it deterministically from the manifest.
   - Run official and lightweight engines into separate directories.
   - Score both with OmniDocBench.
   - Confirm official output format is accepted by the scorer.

3. **Hard subset**
   - Run official engine on the 296 hard pages.
   - Score Edit-distance + TEDS.
   - CDM on the hard subset is optional diagnostic evidence; full-set WSL CDM remains mandatory before any public score update.

4. **Full set**
   - Run official engine on all 1,651 pages.
   - Run Windows scoring.
   - Run WSL CDM scoring.
   - Run `verify.ps1`.
   - Run `verify-accuracy.ps1 -MinimumOverall 96.03`.

Only the full-set result can update README reference numbers.

## Error Handling

- Per-page failures remain non-fatal unless more than 50% of pages fail.
- If official PaddleOCR import fails, show the install command and exit non-zero.
- If official PaddleOCR cannot save Markdown for a page, record the full traceback and continue.
- If no Markdown can be recovered from the official output format, fail the probe before running a full set.
- If `Overall < 96.03` after a full official run, do not relabel it as success. Preserve the artifacts and continue root-cause debugging from the official engine boundary.

## Out Of Scope

- Replacing OmniDocBench scoring internals.
- Changing the benchmark dataset or filtering failed pages to inflate scores.
- Claiming success from the lightweight path unless it independently reaches `Overall >= 96.03`.
- Making Docker the default path for this AMD Windows project.

## Open Implementation Decisions

These must be resolved during implementation with evidence:

- Exact PaddleOCR package version to pin.
- Exact official API method for saving Markdown from `PaddleOCRVL.predict`.
- Whether official PaddleOCR layout detection uses CPU, DirectML, or another Windows-compatible path in this configuration.
- Whether official-compatible llama.cpp flags need to be slower than the current tuned flags.

The implementation plan should treat these as discovery tasks with probes before full-set inference.
