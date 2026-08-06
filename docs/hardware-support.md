# Hardware support matrix

Machine-readable: [`docs/hardware-support.json`](hardware-support.json).
Status legend: **supported** = measured on this repo's profiles with a
published evidence doc; **unsupported** = official Windows HIP binaries do not
exist (use the CPU variant); **unverified** = expected to work, not measured
in this repo yet.

| GPU | GFX arch | Status | HIP binary/tag | CPU fallback | Validated profile | Evidence |
|---|---|---|---|---|---|---|
| Radeon 8060S (Ryzen AI MAX+ 395) | gfx1151 | **supported** | llama.cpp HIP build, locked tag `b9637` | `-Variant cpu` | `paddleocr-vl-hip-full-1651`, `hip-smoke-10` | `docs/reproduction-full1651-hip-2026-08-06.md`, `docs/reproduction-full1651-hip-2026-08-03.md`, `docs/reproduction-hip-smoke-2026-08-02.md` |
| RX 7900 XTX | gfx1100 | **unverified** | same locked HIP build (RDNA3 family) | `-Variant cpu` | `hip-smoke-10` (proposed) | none yet — run the smoke profile and publish the evidence doc |
| Radeon 860M | gfx1152 | **unsupported** for HIP | official Windows HIP releases omit gfx1152 | `-Variant cpu` (validated 200-page CPU path) | `cpu-smoke-10`, `paddleocrvl_cpu_860m_200` subset | `docs/reproduction-cpu-200-2026-07-26.md`, `docs/llama-cpp-radeon-860m-gfx1152-issue-draft-2026-07-26.md` |

## Rules

1. A GPU row may only be marked **supported** after a committed evidence doc
   shows the HIP backend proof passing and real scores.
2. **unverified** rows must state exactly what was and was not measured.
3. The CPU variant is always available as a fallback; CPU smoke results are
   provisioning evidence, not benchmark rows (see
   `docs/benchmark-evidence-policy.md`).
