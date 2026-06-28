# \_template/ — model adapter template

Copy this directory to `adapters/<your-model>/` to add a new model. It is the
fastest path to a scored adapter.

## Files

| File | Purpose |
|---|---|
| `run_adapter.py` | The adapter. Edit `run_adapter()` to call your model. Keep the signature `run_adapter(img_dir, out_dir, server_url)` and the output convention `out_dir/<image_stem>.md`. |
| `setup.ps1` | Provisioning entry point (download weights, start a server, write paths to `.env.local`). Replace the TODO body, or split into numbered sub-directories (see `paddleocr-vl-1.6/`). |

## The interface contract

```python
def run_adapter(img_dir: Path, out_dir: Path, server_url: str = "") -> dict:
    """Write out_dir/<image_stem>.md for every page image in img_dir."""
```

- **Input**: `img_dir` — a flat directory of page images (`.jpg`/`.png`/…).
- **Output**: `out_dir/<image_stem>.md` — one UTF-8 Markdown file per image,
  named `<image-basename-without-extension>.md`. The OmniDocBench matcher
  looks predictions up by that name; a missing file scores zero.
- **Robustness**: catch per-page failures and continue. A single bad page must
  not abort the run (it just scores zero in the harness).
- **No JSON**: the eval-infra never imports your adapter and never reads its
  return value; it only consumes the `.md` files you write. The `dict` return
  is for human/CLI inspection only.

## How to add a model (5 steps)

1. `cp -r adapters/_template adapters/<your-model>` (or copy on Windows).
2. Edit `run_adapter.py` — replace the body of `run_adapter` with your model's
   inference.
3. Edit `setup.ps1` (or replace it with numbered sub-directories) to provision
   whatever your model needs. Write machine-local paths to a gitignored
   `.env.local`, never into committed code.
4. Run it against the dataset **from the repo root** (the same CWD
   `score.ps1` / `full-verify.ps1` assume):
   ```powershell
   powershell -ExecutionPolicy Bypass -File adapters\<your-model>\setup.ps1
   python adapters\<your-model>\run_adapter.py `
       --img-dir  eval-infra\01-omnidocbench\data\images `
       --out-dir  predictions\<your-model>
   ```
5. Point the scoring module at `predictions/<your-model>/` and run the scorer.

See `../paddleocr-vl-1.6/README.md` for a complete, proven reference adapter.
