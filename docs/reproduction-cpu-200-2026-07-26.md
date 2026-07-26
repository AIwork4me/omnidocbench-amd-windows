# Verified 200-Page CPU Reproduction - 2026-07-26

## Result

This machine completed the approved constrained-hardware reproduction path:
exactly 200 OmniDocBench v1.6 pages, PaddleOCR-VL-1.6 GGUF inference through a
real CPU llama.cpp binary, deterministic Windows non-CDM scoring, deterministic
WSL CDM scoring, benchmark verification, and parameterized full-chain
verification.

This is **not** a 1651-page leaderboard result. It is physical-machine
capability evidence for a Radeon 860M system whose published Windows HIP
llama.cpp binaries cannot execute gfx1152 kernels.

## Machine And Software

| Item | Observed value |
|---|---|
| OS | Windows 11 Enterprise, build 26200 |
| CPU | AMD Ryzen AI 7 PRO 350, 16 logical processors |
| GPU | AMD Radeon 860M, driver `32.0.22032.14003` |
| RAM | 31.2 GiB |
| Inference backend | llama.cpp b9637 CPU binary, `LLAMA_GPU_LAYERS=0` |
| Model | PaddleOCR-VL-1.6 GGUF + mmproj |
| Layout model | PP-DocLayoutV3 ONNX |
| Adapter checkout | `AIwork4me/PaddleOCR-VL-ROCm@f0cb4014be5f9f98593f6b08afbc2404f049df4d` |
| Windows Python | CPython 3.11.15, locked uv environment |
| WSL | Ubuntu 22.04.5, Python 3.10.12 |
| CDM tools | TeX Live 2026, ImageMagick 7.1.2-26, Ghostscript 9.55.0 |

## Inference Evidence

| Item | Value |
|---|---:|
| Exact manifest pages | 200 |
| Non-empty UTF-8 Markdown predictions | 200 |
| Prediction contract coverage | 100.00% |
| Frozen error entries | 0 |
| Wall-clock window | 15,757.58 s (4 h 22 m 38 s) |
| Throughput | 0.8 pages/min |
| Median completion interval | 67.3 s/page |
| P95 completion interval | 178.9 s/page |
| P99 completion interval | 253.4 s/page |
| Slowest completion interval | 441.3 s |

Timing was reconstructed from prediction file completion timestamps because the
run was intentionally stopped at the 200-success threshold. These are
wall-clock completion intervals, not model-internal latency samples.

## Deterministic Scores

Both scoring paths used `match_workers: 1` and `teds_workers: 1`. Windows and
WSL produced exactly equal values for every shared metric (absolute delta 0.0).

| Metric | Windows raw | WSL raw | Notebook/page aggregation |
|---|---:|---:|---:|
| Text Edit-distance | 0.0244595641 | 0.0244595641 | 0.0244595641 (184 pages) |
| Formula Edit-distance | 0.0796343659 | 0.0796343659 | same raw metric |
| Table TEDS | 0.9650268714 | 0.9650268714 | 96.25965184 (57 pages) |
| Reading-order Edit-distance | 0.1166805990 | 0.1166805990 | 0.1166805990 (196 pages) |
| Formula CDM | N/A | 0.9533025830 | 96.09493370 (58 pages) |
| Overall | N/A | N/A | 96.63620971 |

The WSL run processed 271 CDM formula samples and 75 TEDS table samples with
zero timeout, error, or exception cases. Page matching also recorded zero
quick-match and page timeouts.

## Toolchain Verification

- WSL CDM setup completed all nine stages and passed an idempotent rerun.
- CDM smoke test rendered a four-color PNG and scored identical formulas at F1
  `1.0`.
- VLM server and exact served model ID passed verification.
- Layout ONNX setup and verification passed.
- Prediction validator passed `200/200`, with zero frozen errors.
- Windows exact metric verifier passed.
- WSL exact metric verifier passed with required positive CDM.
- Benchmark verifier passed all 5 checks.
- Parameterized full verification passed `9`, failed `0`, skipped `1` optional
  check. The skip was Windows-native CDM; WSL is the selected verified path.

## GPU Limitation

The Radeon 860M is gfx1152. Official Windows HIP llama.cpp releases b9637 and
b10107 both reproduced `ROCm error: invalid device function`; b9637 also failed
at multimodal `IM2COL`. `HSA_OVERRIDE_GFX_VERSION=11.0.0` did not change the
result, and this machine has no HIP SDK/`hipcc` for a local gfx1152 build.
Therefore this report uses the real CPU asset rather than claiming GPU
acceleration. Reproduction details are in
`docs/llama-cpp-radeon-860m-gfx1152-issue-draft-2026-07-26.md`.

## Artifact Hashes

| Artifact | SHA-256 |
|---|---|
| 200-page manifest | `E660467F7807A512C1DFB492EC88A2C1AC2F6F43540CAE4453B9D58E7CE01199` |
| Windows metric result | `E12DDF49E054189C669BEF65BBFC4973887987B7CE2C9D7D2E4F87175DE9EE22` |
| WSL CDM metric result | `DFCB758484B4D187FF9C5B5B6ECB1DD6A18E615CEC99479E62BC9B7526AACF87` |
| Capability report | `A5D59087CEBB6F917756E4657FDF109CE019D5080C771713A524B36CEE4BCB6C` |
| Main GGUF | `F3AE46EC885050ACF4B3D31944431E1FD90D50664FB09126AF4A3C050BA14EE8` |
| mmproj GGUF | `204D757D7610D9B3FAAB10D506D69E5B244E32BF765E2BAB2D0167E65E0A058A` |
| PP-DocLayoutV3 ONNX | `45BF71750B00739A41FC209F132EB104A4D6B5BB29483C9078164D8B87CF28BA` |

Generated datasets, models, predictions, raw results, and benchmark working
artifacts remain gitignored. The committed report records enough hashes and
commands to audit the local evidence without publishing third-party assets.
