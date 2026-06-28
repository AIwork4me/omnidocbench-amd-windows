# Contributing

Thank you for your interest in improving OmniDocBench AMD Windows!

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

### Adapter Interface

The only contract: **input** is a directory of page images (jpg/png), **output** is `<image_stem>.md` files (one Markdown per image). The eval infrastructure reads these .md files — your model's internals don't matter.

## Reporting Issues

### Bug Reports

Include:
- Which phase failed (Step 0 = scripts/detect-mirrors.ps1 + scripts/wsl-ensure.ps1, then 01-omnidocbench through 03-scoring)
- The exact error message
- Output of `scripts/detect-mirrors.ps1` (network environment)
- WSL or Windows? (CDM runs in WSL)

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
