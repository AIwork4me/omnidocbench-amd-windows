# Real-machine validation checklist

The automated suite (pytest + CI) proves the state machine, hashing and
evidence gates. It does **not** prove GPU offload, CDM rendering or real
scores. Before any benchmark claim, run the following on the actual machine
and record the outputs. Only a clean-room full run on a fresh checkout (and,
for `independent`, a second machine) upgrades the evidence level of a row.

## 0. Baseline

- [ ] `git rev-parse HEAD` recorded for the evidence doc.
- [ ] `git status --porcelain` empty (formal profiles require a clean tree).
- [ ] `uv sync --locked --all-groups` succeeds.
- [ ] `uv run pytest -q` green (303+ tests on Windows).

## 1. Network + WSL

- [ ] `powershell -ExecutionPolicy Bypass -File scripts\detect-mirrors.ps1` exits 0 (no ⚠️ 4).
- [ ] `wsl -d Ubuntu2204 -- echo OK` prints OK (or native-Windows CDM verified).

## 2. CDM

- [ ] WSL: `wsl -d Ubuntu2204 bash <repo>/eval-infra/02-cdm-environment/verify.sh` prints `VERIFY OK`.
- [ ] Native: `eval-infra\02-cdm-environment\verify-windows.ps1` prints `VERIFY OK` with positive identical-formula F1 (if using the native path).

## 3. HIP acceptance (Radeon 8060S / other gfx1151)

- [ ] `scripts\preflight.ps1 -CdmPath Wsl -Variant hip` exits 0.
- [ ] `reproduce.ps1 -Profile hip-smoke-10` passes; `backend-proof.json` shows
      `actual_gpu_layers >= 1`, `log.freshness` OK, `inference.request` 200,
      process.identity OK.
- [ ] GPU utilization confirmed while the server runs (Task Manager / rocm-smi),
      per AGENTS.md ⚠️ 2.
- [ ] Server start time file `adapters\paddleocr-vl-1.6\logs\llama-server.started`
      is newer than the log content.

## 4. Full 1651-page run (only for evidence-level upgrades)

- [ ] Fresh checkout of the exact commit (clean-room) — NOT resumed from an
      older checkout's artifacts.
- [ ] `reproduce.ps1 -Profile paddleocr-vl-hip-full-1651` completes with
      `REPRODUCTION OK`.
- [ ] `prediction-summary.json`: `expected = 1651`, `unknown_failures = []`,
      `known_allowed_failures` ⊆ the profile allowlist, `verdict = pass`,
      `selected_pages = 1651`.
- [ ] `metrics-summary.json` canonical keys present; WSL↔Windows shared
      metrics agree within tolerance (assert-metrics `cross-platform` OK).
- [ ] `fingerprint.provisioning/inference/scoring/evidence.json` all exist and
      resume `--check` passes on a second invocation.
- [ ] `artifact-hashes.json` includes prediction tree + both provenance hashes.
- [ ] Record the prediction_tree_sha256 in `benchmarks/index.json` for the row.

## 5. Independent reproduction (only for the `independent` level)

- [ ] A second machine repeats section 4 on its own fresh checkout.
- [ ] Its prediction_tree_sha256 and scores are recorded in a new evidence doc;
      the row is then relabelled `independent`.

## 6. Release

- [ ] `scripts\release-gate.ps1 -Tag vX.Y.Z -WriteArtifacts` passes on the tag.
