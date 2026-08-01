# Contributing

Thank you for your interest in improving OmniDocBench AMD Windows!

## Development Setup

Use the locked uv environment so local and CI checks run with the supported
Python and dependency versions:

```powershell
winget install --id astral-sh.uv -e
uv python install 3.11
uv sync --locked --all-groups
.\.venv\Scripts\python.exe -m pytest -q
```

Do not use Python 3.12 or newer for OmniDocBench. The repository pins Python
3.11 in `.python-version` and constrains supported versions in `pyproject.toml`.
When changing Python support, update both files and regenerate `uv.lock` with
`uv lock`.

Hosted CI validates deterministic tests and PowerShell/Bash syntax on Python
3.10/3.11. It does not validate WSL provisioning, AMD GPU execution,
third-party downloads, CDM, scoring, or benchmarks; those require dated
physical-machine evidence and matching verifier output.

## Adding a New Model Adapter

The most valuable contribution is a **new model adapter** — it lets other users evaluate their favorite document parsing model without rebuilding the eval infrastructure.

### Steps

1. Copy `adapters/_template/` → `adapters/<your-model>/`
2. Implement `run_adapter.py`:
   ```python
   def run_adapter(img_dir: Path, out_dir: Path, server_url: str = "") -> dict:
       """Your model: read each image → write <basename>.md"""
   ```
3. Add a `setup.ps1` if your model needs installation steps
4. Add a `README.md` explaining what/why
5. Test: run your adapter on a few OmniDocBench images → verify .md output
6. Submit a PR

Before submitting, complete the pull-request template. Keep generated datasets,
models, predictions, environments, results, credentials, and machine-local
paths out of Git. Update English and Chinese entry-point documentation together
when commands or user-visible behavior change.

### Adapter Interface

The only contract: **input** is a directory of page images (jpg/png), **output** is `<image_stem>.md` files (one Markdown per image). The eval infrastructure reads these .md files — your model's internals don't matter.

## Reporting Issues

### Bug Reports

Include:
- Which phase failed (Step 0 = scripts/detect-mirrors.ps1 + scripts/wsl-ensure.ps1, then 01-omnidocbench through 03-scoring)
- The exact error message
- Output of `scripts/detect-mirrors.ps1` (network environment)
- WSL or Windows? Windows-native CDM is supported when
  `patches/omnidocbench/windows-cdm.patch` is applied and
  `eval-infra/02-cdm-environment/verify-windows.ps1` passes; WSL CDM remains
  the compatibility/reference path.

### New Pitfall

If you hit a problem NOT in [pitfalls.md](docs/pitfalls.md), please report it! Include:
- Symptom (what you saw)
- Root cause (if you found it)
- Fix (what command fixed it)

We'll add it to the knowledge base.

## Style

- PowerShell scripts: PS 5.1 compatible (no pwsh-only features)
- Bash scripts: `set -euo pipefail`, idempotent (safe to re-run)
- Each script: `verify` companion that returns exit 0/1
- READMEs: explain **what** / **why** / **what problem it solves**
- Python dependencies: update `pyproject.toml` and commit the regenerated
  `uv.lock`; do not rely on an undocumented global package
