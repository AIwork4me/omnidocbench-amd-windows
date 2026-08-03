# HIP smoke reproduction evidence — 2026-08-02/03

Machine: AMD Ryzen AI MAX+ 395 / Radeon 8060S (gfx1151), Windows 11, WSL
Ubuntu 22.04.5. Repo branch `feat/reproduction-profiles`.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile hip-smoke-10
```

## Result: PASS (all 19 stages)

- HIP backend proof: PASS — variant markers (env + repaired `.variant`),
  `ggml-hip.dll` + `libhipblas.dll` beside the exe, locked tag b9637, server
  PID alive, `/v1/models` lists the expected model, `LLAMA_GPU_LAYERS=99`,
  HIP/ROCm log markers present, no CPU-fallback markers.
- Inference: 10/10 pages, 45.5 s.
- Windows scoring (10 pages): text Edit-dist `0.00737`, reading-order
  `0.01429`, TEDS `1.0`.
- WSL CDM scoring (10 pages): CDM `0.99328`, shared metrics bit-identical to
  Windows (same values above), page_count 10.
- `scripts/full-verify.ps1`: 8 passed, 0 failed, 2 skipped.
- Evidence pack complete under `outputs/reproduction/hip-smoke-10/`
  (state.json, profile.resolved.json, fingerprint.json, hardware.json,
  backend-proof.json, artifact-hashes.json, prediction-summary.json,
  metrics-summary.json, report.md).

## Resume verification

`reproduce.ps1 -Profile hip-smoke-10 -Resume` (twice) completed in ~25 s:
all non-always-run passed stages skipped; always-run safety stages re-ran
(WSL, preflight, fingerprint check OK, CDM env, server, backend proof, input
locks); inference ran with `--skip-existing` and reprocessed **0** pages
(10 skipped); adapter `_run_stats.json` records invocation 2 and 3 as
`newly_processed=0, skipped_existing=10`.

## Fingerprint gate

A committed code change between runs correctly makes `-Resume` refuse (repo
commit key mismatch) until a fresh run or `-ForceInference`; `-ForceInference`
purged only the profile's own predictions/manifest/save-name-scoped results
(both Windows and WSL result roots) and cleared the fingerprint.

## Full-run outcome (same machine, same day)

See [`reproduction-full1651-hip-2026-08-03.md`](reproduction-full1651-hip-2026-08-03.md).
