# adapters/ — model adapters

One sub-directory per document-parsing model. Each adapter's only job is to
**produce Markdown**: given a directory of page images, write one
`<image_stem>.md` per page into a predictions directory. The model-agnostic
eval-infra (`../eval-infra/`) then scores those predictions against
OmniDocBench v1.6 identically, regardless of which adapter produced them.

This separation is what makes scores directly comparable across models: the
scorer, the dataset, and the CDM environment are shared, and each adapter is
only responsible for generating Markdown.

## The adapter interface contract

Every adapter implements:

```python
def run_adapter(img_dir: Path, out_dir: Path, server_url: str = "") -> dict:
    """Write out_dir/<image_stem>.md for every page image in img_dir."""
```

- **Input**: `img_dir` — a flat directory of page images (`.jpg`/`.png`/…).
- **Output**: `out_dir/<image_stem>.md` — one UTF-8 Markdown file per image,
  named `<image-basename-without-extension>.md`. The OmniDocBench matcher
  looks predictions up by that name; a missing file scores zero.
- **Robustness**: catch per-page failures and continue. A single bad page
  must not abort the run (it just scores zero).
- **No JSON**: the eval-infra never imports your adapter and never reads its
  return value; it only consumes the `.md` files you write. The `dict` return
  is for human/CLI inspection only.

`run_adapter` is exposed both as a function and as a `--img-dir / --out-dir`
CLI; see `_template/run_adapter.py`.

## Contents

| Adapter | Status | Notes |
|---|---|---|
| [`paddleocr-vl-1.6/`](paddleocr-vl-1.6/) | **Reference** (proven end-to-end) | Two engines: `lightweight`/default for the easy PaddleOCR-VL-ROCm AMD Windows path, and `official` for PaddleOCR `PaddleOCRVL` doc_parser score comparison. Both write the same flat Markdown prediction format. |
| [`_template/`](_template/) | Skeleton | Copy this to add a new model. Minimal no-op `run_adapter` + `setup.ps1` + this README's "add a model" recipe. |

## How to add a new model

1. **Copy the template:**
   ```powershell
   Copy-Item -Recurse adapters\_template adapters\<your-model>
   ```
2. **Implement `run_adapter.py`:** replace the body of `run_adapter` with
   your model's inference. Keep the signature and the
   `out_dir/<image_stem>.md` output convention.
3. **Provision your model:** edit `setup.ps1` (or split it into numbered
   sub-directories like `paddleocr-vl-1.6/` has) to download weights, start a
   server, etc. Write machine-local paths to a gitignored `.env.local`, never
   into committed code.
4. **Run it:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File adapters\<your-model>\setup.ps1
   python adapters\<your-model>\run_adapter.py `
       --img-dir  eval-infra\01-omnidocbench\data\images `
       --out-dir  predictions\<your-model>
   ```
5. **Score it:** point the scoring module (Task 5) at
   `predictions/<your-model>/` with a config template. The adapter name is
   just a path segment to the scorer.

The `_template/README.md` has the same recipe with more detail; the
`paddleocr-vl-1.6/` directory is a complete working example to crib from.

## Conventions (match these so the rest of the repo just works)

- **Idempotent `setup.ps1`**: re-running after success is a no-op (or resumes
  a partial download). Each provisioning phase checks for its own output
  before doing work.
- **`.env.local` for machine-local paths**: setup scripts write paths here;
  `run_adapter.py` reads them for defaults. `.env.local` is gitignored.
- **`mirrors.env`-aware**: setup scripts read `$repoRoot\mirrors.env` (from
  `scripts/detect-mirrors.ps1`) for `GITHUB_BASE` / `HF_OR_MS` so downloads
  work behind the China firewall. Fall back to public defaults with a warning.
- **Windows PowerShell 5.1 compatible**: no pwsh-only syntax (no ternary
  operators, no `??`, no 3-arg `Join-Path`). The repo targets Windows 11 with
  the in-box PS 5.1.
- **Numbered sub-directories** when an adapter needs multiple provisioning
  steps (`01-…`, `02-…`), each with its own `setup.ps1` (+ optional
  `verify.ps1`). Single-step adapters can keep one `setup.ps1`.
- **`verify.ps1` exits 0/1**: so `scripts/full-verify.ps1` (Task 7) can chain
  every adapter's verify step into one pre-flight check.
