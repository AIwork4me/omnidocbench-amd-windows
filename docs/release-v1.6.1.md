# Release notes: v1.6.1 (2026-08-06)

## Verified devices

- AMD Ryzen AI MAX+ 395 / Radeon 8060S (gfx1151), Windows 11 + WSL Ubuntu
  22.04.5, HIP llama.cpp backend (`b9637`), uv 0.11.16.
- Full 1651-page OmniDocBench v1.6 run passed on 2026-08-06 (commit
  dfd8962): Text ED 0.035251, Reading-order ED 0.129328, Table TEDS
  92.9792 (pooled 0-100), Formula CDM 96.5605 (0-100), coverage 0.998789.

## Unverified devices

- AMD Radeon 860M / gfx1152 (official Windows HIP releases omit it; use the
  CPU variant there).
- Other AMD/Windows combinations, NVIDIA, macOS, Linux native; WSL is
  verified only with Ubuntu 22.04.

## Known limitations

- The 2026-08-06 full-set evidence is a **validated resumed** run, not
  clean-room: it required one failed-stage resume, and the first
  prediction-check attempt hit a Windows MAX_PATH issue that was completed
  with a machine-local shim before the permanent tracked fix (commit
  252a6e2) landed.
- Two pages fail deterministically on the upstream peg-native parser
  (PaddlePaddle/PaddleOCR#18248) and are allowlisted within the 2-page
  budget.
- `validate_predictions.py`, `build_prediction_subset.py`, and
  `metric_provenance.py` still use short-path assumptions; they are not
  formal evidence gates and their real inputs do not exceed MAX_PATH.

## Evidence levels

- 2026-08-06 full run: **validated resumed** (this release's headline row).
- 2026-08-03 full run: **validated resumed** (see
  docs/reproduction-full1651-hip-2026-08-03.md).
- 2026-08-02 HIP smoke: **smoke** (10 pages).
- No clean-room or independent full-set row is claimed in this release.
