# Reproduction Evidence - 2026-07-25

This report records what was executed on the named machine during a fresh-clone
review. A published reference result is not treated as reproduced here until
the corresponding command and verifier have passed on this machine.

## Scope And Status

| Phase | Status | Evidence |
|---|---|---|
| Repository clone and integrity | PASS | Clean clone at commit `0718be0044fa8505afcafcf8b580d714887ba20c`, tag `v1.6-accuracy` |
| Generated-artifact ignore rules | PASS | Representative venv, model, data, prediction, log, result, and benchmark paths are ignored |
| PowerShell syntax baseline | PASS | All repository `.ps1` files parsed with the Windows PowerShell AST parser |
| uv/Python environment | PASS | uv `0.11.32`, uv-managed Python `3.11.15`, locked repo `.venv` |
| Python test baseline | PASS | `uv sync --locked --all-groups`; final deterministic suite `120 passed` |
| Network and mirror detection | PASS | Two consecutive probes selected reachable GitHub, Hugging Face, PyPI, USTC CTAN, and Ubuntu rootfs sources |
| Windows preflight | PASS | Selected WSL/HIP path: 8 passed, 1 warning; runtime HIP/VRAM confirmation intentionally remains for the VLM-server human gate |
| WSL provisioning | PASS | Ubuntu 22.04 installed, normalized to canonical `Ubuntu2204`, direct start verifier prints `OK`, idempotent rerun passes |
| OmniDocBench code and dataset | PASS | Upstream `c3e100b386d59b4ba1497786fb99b75220947c40`; 1651 manifest references present and Python-consumable through deterministic short path; idempotent setup/verify passes |
| WSL CDM environment | PASS | Nine setup stages and idempotent rerun pass; four-color PNG; identical-formula CDM F1 `1.0` |
| Windows-native CDM environment | SKIPPED | Optional path assessed; patch/Python pass, native TeX Live/ImageMagick/Ghostscript absent; WSL selected |
| Reference adapter | PASS (CPU fallback) | VLM/layout/dependencies and idempotent reruns pass; 200-page frozen output is 200/200 UTF-8 Markdown with zero frozen errors |
| Radeon 860M HIP path | BLOCKED (documented) | b9637/b10107 reproduce gfx1152 `invalid device function`; CPU asset used honestly |
| Non-CDM scoring | PASS | Deterministic Windows workers `1/1`; shared metrics verified; zero timeout/error/exception |
| CDM scoring | PASS | Deterministic WSL run: CDM raw `0.9533025830`, notebook `96.09493370`; 271 samples, zero failures |
| Full verification | PASS | Exact 200-page parameters: `9 passed, 0 failed, 1 optional skip` |
| Benchmark report | PASS | CPU fallback report generated; benchmark verifier `5/5` |

## Repository Baseline

| Item | Observed value |
|---|---|
| Remote | `https://github.com/AIwork4me/omnidocbench-amd-windows.git` |
| Branch | `main` tracking `origin/main` |
| Commit | `0718be0044fa8505afcafcf8b580d714887ba20c` |
| Exact tag | `v1.6-accuracy` |
| Baseline worktree | Clean before review changes |
| Git | `2.55.0.windows.3` |
| GitHub CLI | `2.96.0` |

## Machine Baseline

| Item | Observed value |
|---|---|
| OS | Windows 11 Enterprise, version `10.0.26200`, build `26200`, 64-bit |
| PowerShell | Windows PowerShell `5.1.26100.8875`, Desktop edition |
| Execution policy | `Unrestricted` |
| CPU | AMD Ryzen AI 7 PRO 350 with Radeon 860M, 16 logical processors |
| Memory | 31.2 GiB visible |
| GPU | AMD Radeon 860M Graphics, driver `32.0.22032.14003` |
| Disk | C: 943.7 GiB total, 824.2 GiB free at baseline |
| uv | `0.11.32`, installed at `%USERPROFILE%\.local\bin\uv.exe` |
| Python | uv-managed CPython `3.11.15` in the repo `.venv` |
| Python launcher | Missing; no longer required by the primary setup path |
| pytest | `9.1.1` in the locked local environment |
| WSL | BLOCKED: Windows reports that WSL is not installed |

The integrated GPU's `AdapterRAM` value reported by WMI is not accepted as
physical VRAM evidence because shared-memory adapters commonly expose an
inaccurate placeholder. Runtime GPU tooling and the model server must provide
the usable-memory evidence later.

## Commands And Outcomes

| Command/check | Exit | Outcome |
|---|---:|---|
| `git status --short --branch` | 0 | `main...origin/main`; clean before review edits |
| `git remote get-url origin` | 0 | Expected GitHub repository |
| `git rev-parse HEAD` | 0 | Baseline commit recorded above |
| `git describe --tags --exact-match` | 0 | `v1.6-accuracy` |
| Representative `git check-ignore -v` checks | 0 | All generated artifact examples ignored |
| PowerShell AST parse of repository `.ps1` files | 0 | `POWERSHELL_PARSE_OK` |
| `python --version` | non-zero | Microsoft Store alias; no Python installed |
| `wsl --status` | non-zero | WSL not installed; interactive installation prompt was cancelled, with no system change |
| `uv python install 3.11` | 0 | Installed uv-managed CPython `3.11.15` |
| `uv venv --python 3.11 --seed .venv` | 0 | Created the repository-local environment |
| Initial `python -m pytest -q` | 1 | `69 passed, 7 failed`; all failures were missing runtime/test dependency `psutil` |
| `uv lock` and `uv sync --locked --all-groups` | 0 | Locked 76 packages and synchronized the local environment |
| `.venv\Scripts\python.exe -m pytest -q` | 0 | `78 passed` after uv environment integration tests were added |
| First `scripts\detect-mirrors.ps1` run | 0 | `NETWORK_STATUS=ok`; direct GitHub and Hugging Face selected, with USTC CTAN and Ubuntu rootfs mirrors |
| Second `scripts\detect-mirrors.ps1` run | 0 | Same source selection; idempotent rewrite of `mirrors.env` |
| Focused scoring/CDM regression suite | 0 | `37 passed`; mandatory metrics now reject non-numeric/non-finite values |
| Benchmark report regression suite | 0 | `18 passed`; invalid scores and empty hardware identity are rejected |
| Git Bash parse of `score-cdm.sh` | 0 | `BASH_SYNTAX_OK` after prediction-directory override support |
| PowerShell AST parse of revised benchmark orchestrator | 0 | `POWERSHELL_PARSE_OK` |
| Final fast suite for this review slice | 0 | `86 passed` |
| Focused preflight tests | 0 | `3 passed`: Python 3.11 accepted, Python 3.13 and explicit missing Git rejected with corrective actions |
| `preflight.ps1 -CdmPath None -Variant hip` | 0 | `7 passed, 2 warnings, 0 failed`; disk, Git, Python, mirrors, writable path, and AMD GPU detected |
| `preflight.ps1 -CdmPath Wsl -Variant hip` | 1 | Correct fail-fast result: canonical Ubuntu2204 distro missing |
| First `scripts\wsl-ensure.ps1` run | 0 | Installed Ubuntu 22.04, exported/unregistered/imported it as canonical `Ubuntu2204`; exposed a false-success shell-quoting defect in the final probe |
| `wsl -d Ubuntu2204 -- echo OK` | 0 | Proved the distro/kernel were healthy and no reboot was required |
| Focused WSL probe regressions | 0 | `2 passed`; direct `echo OK` probe now checks both output and exit code |
| Second `scripts\wsl-ensure.ps1` run + verifier | 0 | No-op provisioning; `WSL start probe: OK`; canonical verifier prints `OK` |
| Post-provision WSL/HIP preflight | 0 | `8 passed, 1 warning, 0 failed`; warning reserves real GPU-use confirmation for VLM-server setup |
| Prediction-contract validator tests | 0 | `5 passed`: complete/tiny UTF-8 output accepted; missing, malformed, empty, and case-colliding cases covered |
| First Step 1 setup | 1 | Clone/patch/venv succeeded; dataset failed before download because the script assumed a global `huggingface-cli` |
| Locked Hugging Face retry | 1 | `.venv\Scripts\hf.exe` resumed to 897 images, then Xet token API returned HTTP 429 |
| Non-Xet HTTP retry | 1 (intentional gate) | Resumed to all ordinary-path files; post-download manifest check rejected apparent `1557/1651` instead of reporting false success |
| Dataset verifier against partial state | 1 (expected) | Exact manifest-reference diagnostics proved partial data could not pass |
| Dataset encoding/path investigation | 0 | Explicit UTF-8 reduced false missing paths from 94 to 8; all remaining targets had 267-character full paths with `LongPathsEnabled=0` |
| MAX_PATH recovery and short-root validation | 0 | Extended path storage plus deterministic `%LOCALAPPDATA%\OmniDocBenchAMD\84fe5fcc200d\repo` junction made all 1651 images visible/openable to normal Python |
| Final Step 1 setup + verifier | 0 | Code, patches, manifest, every reference, and Python consumer path pass; idempotent rerun performs no download |
| Dataset provenance | 0 | Upstream `c3e100b386d59b4ba1497786fb99b75220947c40`; manifest SHA-256 `A45CD84B04AD8B793E775089640E6B681209ABEA33EAD54C1828DDCA35FAE496`; data bytes `1551486734` before short-root alias |
| Focused path/scoring/adapter regressions | 0 | `59 passed` after short-root routing and exact dataset checks |
| WSL CDM setup + verify + idempotent rerun | 0 | TeX Live 2026, IM7, Ghostscript, CJK and venv pass; color PNG 4 colors; identical CDM F1 `1.0` |
| Single-page CPU inference gate | 0 | `1/1` page, non-empty UTF-8 Markdown, 28.67 s, zero errors |
| Frozen CPU capability subset | 0 | Exact 200-page manifest; 200/200 predictions; 100% usable; 15,757.58 s wall-clock window |
| Deterministic Windows scoring | 0 | Page match/TEDS workers `1/1`; TEDS 75 samples; zero timeout/error/exception; metric SHA-256 `E12DDF49E054189C669BEF65BBFC4973887987B7CE2C9D7D2E4F87175DE9EE22` |
| Deterministic WSL CDM scoring | 0 | Shared metric delta vs Windows `0.0`; CDM 271 samples, TEDS 75 samples; zero failures; metric SHA-256 `DFCB758484B4D187FF9C5B5B6ECB1DD6A18E615CEC99479E62BC9B7526AACF87` |
| Benchmark verifier | 0 | `5/5` checks passed for `benchmark-results/20260726-cpu-200` |
| Parameterized full verify | 0 | `9 passed, 0 failed, 1 skipped`; skip is optional Windows-native CDM |
| Final tracked Python compilation | 0 | Every tracked Python file compiled successfully |
| Final PowerShell/Bash syntax gates | 0 | Repository PowerShell AST parse and all selected Bash `-n` checks passed |
| Final structured-data check | 0 | Every tracked JSON/YAML file parsed successfully |
| Final documentation-link check | 0 | 442 tracked/release-scope Markdown files; no missing local target |
| Final deterministic test suite | 0 | `120 passed` in the locked `.venv` |
| Final release-claim check | 0 | English/Chinese first screens distinguish historical 1651-page targets from this machine's 200-page CPU evidence; native CDM remains explicitly skipped |

## Review Changes

| Artifact | Purpose |
|---|---|
| `docs/superpowers/plans/2026-07-25-open-source-quality-reproduction.md` | Ordered implementation and reproduction plan with mandatory gates |
| `docs/reproduction-2026-07-25.md` | This evidence ledger; updated only after executable checks |
| `.python-version`, `pyproject.toml`, `uv.lock` | Reproducible Python 3.11 environment managed by uv |
| `tests/test_uv_environment.py` | Regression coverage for uv setup and unsupported-Python failure behavior |
| `docs/open-source-quality-review-2026-07-25.md` | Severity-ordered verified findings, fixes, false positives, and open gaps |
| Scoring input/metric validation | Explicit prediction-directory contract, fail-fast Python/input checks, numeric finite metric gates |
| Benchmark evidence binding | Unique per-run predictions, exact score artifacts, mandatory stage exits, dynamic hardware identity |
| `scripts/preflight.ps1`, `tests/test_preflight.py` | One actionable prerequisite report before expensive setup, with behavioral regression coverage |
| `scripts/wsl-ensure.ps1`, `tests/test_wsl_ensure.py` | Direct checked distro start probe; prevents shell-quoting errors from being reported as successful provisioning |
| `scripts/validate_predictions.py`, `tests/test_prediction_validator.py` | Reusable image-to-Markdown completeness, encoding, collision, and error-accounting gate |
| `scripts/windows_paths.py` and setup short-root junction | No-admin Windows MAX_PATH compatibility for adapters, validators, and scoring without rewriting upstream data |
| `docs/reproduction-cpu-200-2026-07-26.md` | Final physical-machine report with scores, denominators, hashes, timing provenance, and GPU limitation |

## Evidence Rules For Remaining Work

- Record exact commands and exit codes; summarize large logs without secrets.
- Record upstream/model versions and hashes wherever the source exposes them.
- Record artifact counts and result file hashes, not only a final PASS message.
- Keep skipped optional paths visibly marked `NOT RUN` or `SKIPPED`.
- Stop at the human-intervention points defined by `AGENTS.md`.
- Do not mark the project reproduced until prediction, scoring, CDM, full-chain,
  and benchmark gates for the selected path have all passed.