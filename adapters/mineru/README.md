# MinerU adapter (pipeline backend, Windows + AMD HIP)

Adapter for [MinerU 3.4.4 pipeline](https://github.com/opendatalab/MinerU)
running on AMD Radeon GPUs under Windows, via the
[MinerU-ROCm](https://github.com/AIwork4me/MinerU-ROCm) ROCm/HIP port.

Unlike `adapters/_template/`, this adapter is **not** copy-and-edit: it is a
thin shim over an external checkout (MinerU-ROCm) plus a dedicated Python 3.12
inference env. The 5 steps below mirror the template's flow.

## 1. Prerequisites (instead of `cp -r _template`)

You need two machine-local things; record them in `.env.local`:

```powershell
copy adapters\mineru\.env.local.example adapters\mineru\.env.local
# then edit .env.local:
#   MINERU_ROCM_REPO        = path to a MinerU-ROCm checkout (installed pip -e --no-deps)
#   MINERU_WIN_ROCM_PYTHON  = python.exe of a py3.12 env with ROCm torch
```

Building the py3.12 env from scratch (ROCm 7.2.1 SDK + cp312 torch wheels) is a
human step — it may trigger UAC. `setup.ps1` prints the exact wheel URLs
(MinerU-ROCm `docs/HANDOFF-windows-hip.md` §2) when the env is missing and
exits 1, per the AGENTS.md ⚠️3 pattern.

## 2. Adapter contract

`run_adapter.py` delegates to MinerU-ROCm's dispatcher and satisfies the
template contract: one UTF-8 `<image_stem>.md` per page in `--out-dir`, plus a
`_run_stats.json`. Mandatory flags for this platform:

- `--platform windows-hip` (required; selects the HIP/DirectML device policy)
- `--backend pipeline` (the MinerU 3.4 pipeline; not the VLM backend)
- `--img-dir` / `--out-dir` as usual; `--skip-existing` resumes partial runs

Per-page failures are logged and skipped by the dispatcher, so one bad page
does not abort a full run.

## 3. Provision

```powershell
powershell -ExecutionPolicy Bypass -File adapters\mineru\setup.ps1
powershell -ExecutionPolicy Bypass -File adapters\mineru\verify.ps1
```

`setup.ps1` is idempotent (each step prints SKIP when satisfied): HIP torch →
`mineru[pipeline]==3.4.4` → editable `mineru_rocm` → `onnxruntime-directml`
installed **last** → pipeline weights via `mineru-models-download` (honours
`HF_ENDPOINT` from repo-root `mirrors.env`). `verify.ps1` exits 0/1 after five
checks, ending with a real one-page GPU smoke inference (allow 1–3 min for
model warmup).

## 4. Run (full dataset)

Use the **py3.12 inference env**, not the repo `.venv` (scoring uses `.venv`;
inference must not — see "Environments and pitfalls"). From the repo root:

```powershell
$env:PYTHONUTF8 = "1"
C:\path\to\mineru-win-rocm\python.exe adapters\mineru\run_adapter.py `
  --backend pipeline --platform windows-hip `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --out-dir predictions\mineru_pipeline
```

Then validate the shared output contract:

```powershell
.\.venv\Scripts\python.exe scripts\validate_predictions.py `
  --img-dir eval-infra\01-omnidocbench\data\images `
  --pred-dir predictions\mineru_pipeline --min-coverage 0.95
```

## 5. Score

Both configs point at `predictions/mineru_pipeline`:

```powershell
# Non-CDM (Edit_dist + TEDS; runs in a minimal environment):
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 `
  -Config v16-mineru-pipeline.yaml

# With CDM for display formulas (needs the CDM environment):
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 `
  -Config v16-cdm-mineru-pipeline.yaml
```

## Environments and pitfalls

- **Never `mineru[all]`**: its VLM extra pins public torch 2.8.0 and silently
  replaces the ROCm 2.9.1 wheel. Install `mineru[pipeline]==3.4.4` only.
- **Install `onnxruntime-directml==1.24.4` last**, with
  `--force-reinstall --no-deps`, so its binary wins over the CPU ORT wheel;
  `DmlExecutionProvider` must be first in `ort.get_available_providers()`.
- **`slanet-plus.onnx` CPU override** is intentional: the table-structure model
  cannot execute its control flow on ORT 1.24.4/DirectML, so MinerU-ROCm routes
  only that model to `CPUExecutionProvider`. Seeing it on CPU is not a bug.
- **Two Pythons, by design**: inference runs on the py3.12 ROCm env
  (`MINERU_WIN_ROCM_PYTHON`); scoring runs on the repo `.venv` (py3.11). Do not
  try to unify them — torch-ROCm and the eval harness have disjoint needs.
- Set `PYTHONUTF8=1` for any adapter invocation (dataset contains CJK names).
