# 03-scoring — Edit_dist + TEDS + CDM scoring + verification

The last layer of `eval-infra/`. Consumes adapter predictions + the
OmniDocBench dataset + the CDM environment (Tasks 2–4) and produces scores.

Three scripts, one goal: a `*_metric_result.json` whose four mandatory metrics
are all non-zero, verified by `verify.ps1`.

| Script | Runs | Scores | Env |
|---|---|---|---|
| [`score.ps1`](score.ps1) | Windows-native | Edit_dist + TEDS (text_block, display_formula, table, reading_order) | Windows + Python 3.10/3.11 |
| [`score-cdm.sh`](score-cdm.sh) | WSL | Edit_dist + TEDS **+ CDM** (display_formula gets a CDM score too) | WSL + CDM env (Task 3) |
| [`verify.ps1`](verify.ps1) | Windows | — (reads result JSON) | Windows |

## Why two scoring scripts

CDM (the formula-rendering metric) is the only OmniDocBench metric that shells
out to non-Python tools (`pdflatex`, `magick`, `gs`, `kpsewhich`). On Windows
three things break:

1. The CDM code calls POSIX shell commands (`shlex`, `os.path` POSIX semantics).
2. ImageMagick 6 silently renders color formulas as **grayscale** → CDM F1 = 0
   with no error.
3. TeX Live on Windows can't reliably compile the CDM template's `\mathcolor`.

So CDM must run in WSL, where `eval-infra/02-cdm-environment` provisions the
working LaTeX + ImageMagick 7 + Ghostscript toolchain. Everything else
(Edit_dist, TEDS, reading order) runs fine Windows-native. Splitting them lets
you iterate fast on the pure-Python metrics (seconds per run on the hard
subset) and only pay the WSL round-trip when you need CDM.

## Usage

### Edit_dist + TEDS (fast, Windows)

```powershell
# Default: full 1651-page set (v16.yaml). ~25 min.
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1

# 296-page hard subset (v16-hard.yaml). ~5 min.
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-hard.yaml
```

### + CDM (slow, WSL — needs the CDM environment from Task 3)

```powershell
# First provision the CDM environment (one-time, ~30 min):
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/setup.sh

# Then score with CDM (uses v16-cdm.yaml; ~40 min on the full set):
wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/03-scoring/score-cdm.sh
```

### Verify

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
```

Prints `OK` for each of the 4 mandatory metrics and exits 0 only if all are
non-zero. A metric at exactly `0.0` is treated as a silent run failure (e.g.
CDM F1=0 from the IM6 grayscale bug, or all-zeros from a missing predictions
dir) even though `pdf_validation.py` exited 0.

## Configs and result paths

`score.ps1` / `score-cdm.sh` read a **template** from
[`../01-omnidocbench/configs/`](../01-omnidocbench/configs/) (`v16.yaml`,
`v16-hard.yaml`, `v16-cdm.yaml`) and resolve the literal `<REPO_ROOT>`
placeholder to this repo's absolute path. The rendered config is written into
the OmniDocBench checkout next to `pdf_validation.py`.

OmniDocBench writes results to `<checkout>/result/` (relative to the
`pdf_validation.py` CWD), named:

```
<save_name>_metric_result.json     ← the scores; consumed by verify.ps1
<save_name>_run_summary.json       ← environment + runtime report
<save_name>_<category>_result.json ← per-category breakdown
```

where `save_name = <prediction-dir-basename>_<match_method>`, e.g.
`paddleocrvl_rocm_quick_match`. The CDM config uses a `_cdm`-suffixed
predictions dir (`paddleocrvl_rocm_cdm`) so its `save_name`
(`paddleocrvl_rocm_cdm_quick_match`) doesn't clobber the Edit_dist-only run.

| Config | Predictions dir | save_name |
|---|---|---|
| `v16.yaml` | `predictions/paddleocrvl_rocm` | `paddleocrvl_rocm_quick_match` |
| `v16-hard.yaml` | `predictions/paddleocrvl_rocm_hard` | `paddleocrvl_rocm_hard_quick_match` |
| `v16-cdm.yaml` | `predictions/paddleocrvl_rocm_cdm` | `paddleocrvl_rocm_cdm_quick_match` |

> The prediction dir name comes from whichever adapter produced the Markdown.
> To score a different adapter, point the config's `prediction.data_path` at
> that adapter's predictions dir (see [`adapters/README.md`](../../adapters/README.md)).

## PYTHONUTF8 and the Windows UTF-8 trap

Both scripts set `PYTHONUTF8=1`. On Windows the default console codepage
(cp1252 / cp936) corrupts the UTF-8 JSON OmniDocBench reads and writes, and
corrupts the CJK LaTeX the CDM template compiles. Symptom: a `metric_result.json`
that's valid JSON but contains mojibake, or a `UnicodeDecodeError` mid-run.
`PYTHONUTF8=1` forces Python into UTF-8 mode for all file I/O. Never run a
scoring pass without it.

## Decision tree: CDM F1 = 0

If `verify.ps1` warns `display_formula.CDM = 0`, walk
[`../../docs/pitfalls.md#cdm-zero`](../../docs/pitfalls.md#cdm-zero). The short
version:

1. Is `magick --version` showing IM7 (not IM6)? → `#grayscale`
2. Is `\mathcolor` actually emitting color in the rendered PNG? → `#mathcolor`
3. Are CJK glyphs present (not tofu) in the formula PDF? → `#gkaiu-map`
4. Did you run in WSL (not Windows)? → `#posix`

## Prerequisites

- **OmniDocBench code + dataset** — from
  [`../01-omnidocbench`](../01-omnidocbench/README.md) (Task 2).
- **A predictions directory** — from an adapter in
  [`../../adapters/`](../../adapters/) (Task 4).
- **CDM environment (CDM runs only)** — from
  [`../02-cdm-environment`](../02-cdm-environment/README.md) (Task 3).
- **Python 3.10/3.11** — OmniDocBench is not 3.12-compatible
  (`#python-version`). The venv created by `02-omnidocbench/setup.ps1` pins 3.11.

## Related

- [`../01-omnidocbench/configs/`](../01-omnidocbench/configs/) — the config
  templates these scripts render.
- [`../../docs/pitfalls.md`](../../docs/pitfalls.md) — full diagnosis of every
  scoring failure mode.
- [`../../docs/architecture.md`](../../docs/architecture.md) — where this module
  sits in the data flow.
