# AMD Windows Clean-Room Smoke Evidence - 2026-07-26

## Status

**PASS: AMD Windows provisioning, ten fresh CPU predictions, Windows scoring,
WSL CDM, exact full verification, and idempotent resume.**

Per the approved acceptance policy, the dataset download gate required the
locked immutable snapshot to start successfully and make sustained progress;
it did not require downloading the same 3.3 GB again. After 1,389,938,164 bytes
were staged, the user stopped the download. Bulk dataset/GGUF/layout bytes were
then copied from an existing checkout only after source lock verification and
were verified again at the destination. Inference, the ten-page manifest,
Windows score, and WSL CDM score were newly produced in the isolated clone.

## Isolation

- Clone path: `C:\Users\jzhang21\OneDrive - Advanced Micro Devices Inc\Desktop\OmniDocBench Clean Room 10`
- Path intentionally contains spaces and is inside OneDrive.
- Initial public commit: `9c2eb673e9ab8e96fe01b486384ebed3a45d7f9f`
- Public commit used for the successful inference/scoring run:
  `9768ed868c701a73432fe1309e84f6a2b8e64d98`
- Before the first command, the clone had no `.venv`, `mirrors.env`, generated
  OmniDocBench checkout, dataset, adapter models, `.env.local`, predictions, or
  outputs.
- No prediction, score, environment, generated checkout, `.env.local`, or run
  state was copied from the development checkout.
- The existing dataset/GGUF/layout bytes were explicitly seeded from the
  development checkout after complete source verification; destination files
  passed the same manifest/tree/model locks before use.
- Machine-global package caches and the existing `Ubuntu2204` WSL/CDM toolchain
  were allowed by the acceptance definition.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile cpu-smoke-10
```

Bandwidth-saving command used after the download-start gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile cpu-smoke-10 -Resume `
  -SeedFrom "C:\path\to\existing\locked-checkout" `
  -SkipCdmSetup
```

## Verified Phases

| Phase | Result | Evidence |
|---|---|---|
| Fresh clone isolation | PASS | All repo-local generated paths absent |
| Python 3.11 environment | PASS after fix | 63 locked packages installed |
| Network/mirror selection | PASS | `NETWORK_STATUS=ok`, direct GitHub/Hugging Face |
| WSL availability | PASS | `Ubuntu2204` start probe OK |
| CPU/WSL preflight | PASS | 8 passed, 0 warnings, 0 failed |
| Locked OmniDocBench code | PASS | commit `c3e100b386d59b4ba1497786fb99b75220947c40` |
| Locked dataset download start | PASS | 2,707 staging files, 1,389,938,164 bytes before user stop |
| Seed source/destination locks | PASS | 1,651 images, 1,446,322,066 bytes, tree SHA `11edca7c...f0a6` on both sides |
| Locked model/layout | PASS | GGUF, mmproj, ONNX and YAML SHA-256 verified before and after copy |
| Locked pipeline checkout | PASS | `f0cb4014be5f9f98593f6b08afbc2404f049df4d` |
| Ten-page inference | PASS | 10/10, zero failures, 803 model seconds |
| Exact manifest/coverage | PASS | 10 pages, 100% coverage |
| Windows scoring | PASS | finite mandatory metrics, no timeout/error/exception |
| WSL CDM scoring | PASS | CDM raw `0.99328`, 25 samples, no timeout/exception |
| Exact full verification | PASS | 8 passed, 0 failed, 2 optional skips |
| Second `-Resume` | PASS | expensive phases skipped; volatile WSL/server/locks/full verify rerun |

## Ten-Page Metrics

| Metric | Raw value |
|---|---:|
| Text Edit-distance | 0.0073720839556528 |
| Formula Edit-distance | 0.026286048568268782 |
| Table TEDS | 1.0 |
| Reading-order Edit-distance | 0.014285714285714285 |
| Formula CDM (`all`) | 0.99328 |
| Formula CDM (page aggregation) | 0.9953333333333333 |

All shared Windows/WSL metric deltas were exactly `0.0`. The ten-page subset
contains only one table and 25 formula samples, so these values are capability
smoke evidence, not accuracy estimates or leaderboard results.

## Timing

| Phase | Seconds |
|---|---:|
| Python environment | 59.71 |
| Lock-verified bulk seed | 39.70 |
| CPU VLM start/verify | 5.76 |
| Pipeline checkout/install | 50.17 |
| Ten-page CPU inference | 805.83 |
| Exact manifest/validation | 2.56 |
| Windows scoring | 581.79 |
| WSL CDM scoring | 45.30 |
| Exact full verification | 17.27 |

## Friction Found And Fixed

### OneDrive uv hardlink failure

First run failed with Windows Cloud Files error `396` when uv tried to hardlink
from its cache into a OneDrive clone. `scripts/reproduce.ps1` now scopes
`UV_LINK_MODE=copy` around locked environment setup. Published fix:
`809284155b8b4caef413719da4fc7ed97a2bf75b`.

### Hugging Face local-dir MAX_PATH failure

The Hub client created long `.cache/huggingface/download/*.incomplete` names
under the 90-character OneDrive path. A junction was insufficient because the
client resolved it back to the original path. Dataset downloads now use a real
short staging directory under `%LOCALAPPDATA%\OmniDocBenchAMD\<clone-hash>\`,
then copy locked manifest-referenced files into the clone with Win32 extended
paths. Published fix: `bd7cbcb6c25997e15e7508f1e7f7b53461ce0cd6`.

### PowerShell lock verifier CI compatibility

GitHub's Windows PowerShell environment did not expose `Get-FileHash`. The lock
verifier now computes SHA-256 through .NET streaming APIs, preserving Windows
PowerShell 5.1 compatibility. The orchestrator also persists `interrupted`
state through a trap. Published fix:
`645c42e`.

### Lock-verified seed path edge cases

The accepted bandwidth-saving path exposed PowerShell 5.1 top-level JSON array
behavior, wildcard characters in filenames, source/destination MAX_PATH, seeded
model discovery, and uv editable-build hardlinks. Fixes were published through
`9768ed8`; all inputs are verified before and after copy.

## Artifact Hashes

| Artifact | SHA-256 |
|---|---|
| Ten-page manifest | `CA24A7F932B0FACB6EA4F02519FBC3A9491270D2379A90567B30DD1D4F20A9AD` |
| Prediction tree | `1988E29DC037AF171E116E0256097E2E1741C821EC37A9DBFD35595801A1E5A1` |
| Windows metric result | `D8CA1A56331E512DCC1924963B9A0C254F88261F28B247CECCE1BD93AB0EA8B2` |
| WSL CDM metric result | `6D04495469AC5945EBC3BCE7A21F687BB1D43AB77CB7E7858F31F18BA56A616B` |
| Final state | `4CB7308B28C70617F483E553720698F777F46994FA86C49726C8D98AD99C8EE7` |

The state reports `passed`, records the public run commit and seed provenance,
and contains 50 phase records including failed attempts that led to fixes.