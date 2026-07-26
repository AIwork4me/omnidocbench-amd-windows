# AMD Windows Clean-Room Smoke Evidence - 2026-07-26

## Status

**INTERRUPTED BY USER DURING LOCKED DATASET DOWNLOAD.** This run is not a
completed ten-page capability result and must not be represented as one.

The run proved the new single entry point from an isolated public clone through
Python provisioning, network mirror selection, WSL availability, preflight,
locked OmniDocBench checkout, and resumable short-path dataset download. The
user explicitly requested that the download stop before completion.

## Isolation

- Clone path: `C:\Users\jzhang21\OneDrive - Advanced Micro Devices Inc\Desktop\OmniDocBench Clean Room 10`
- Path intentionally contains spaces and is inside OneDrive.
- Initial public commit: `9c2eb673e9ab8e96fe01b486384ebed3a45d7f9f`
- Latest staging fix used by the interrupted run:
  `bd7cbcb6c25997e15e7508f1e7f7b53461ce0cd6`
- Before the first command, the clone had no `.venv`, `mirrors.env`, generated
  OmniDocBench checkout, dataset, adapter models, `.env.local`, predictions, or
  outputs.
- No repo-local generated artifact was copied from the development checkout.
- Machine-global package/download caches and the existing `Ubuntu2204` WSL
  distro were allowed by the clean-room definition.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile cpu-smoke-10
```

Resume command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile cpu-smoke-10 -Resume
```

## Verified Phases Before Interruption

| Phase | Result | Evidence |
|---|---|---|
| Fresh clone isolation | PASS | All repo-local generated paths absent |
| Python 3.11 environment | PASS after fix | 63 locked packages installed |
| Network/mirror selection | PASS | `NETWORK_STATUS=ok`, direct GitHub/Hugging Face |
| WSL availability | PASS | `Ubuntu2204` start probe OK |
| CPU/WSL preflight | PASS | 8 passed, 0 warnings, 0 failed |
| Locked OmniDocBench code | PASS | commit `c3e100b386d59b4ba1497786fb99b75220947c40` |
| Locked dataset staging | IN PROGRESS, then user-stopped | 2,707 staging files, 1,389,938,164 bytes retained |
| Dataset tree verification | NOT RUN | waits for complete immutable snapshot |
| Model/layout provisioning | NOT RUN | downstream of dataset gate |
| Ten-page inference | NOT RUN | no accuracy/capability claim |
| Windows/WSL scoring | NOT RUN | no score claim |

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

## Resumability Evidence

- The state file is at
  `outputs/reproduction/cpu-smoke-10/state.json` in the isolated clone.
- The short staging cache remains under
  `%LOCALAPPDATA%\OmniDocBenchAMD\1fc4efe77072\dataset-download`.
- No downloader or child Python process remained after the user-requested stop.
- The state was explicitly marked `interrupted` with the resume command.

## Completion Criteria Still Open

The clean-room acceptance remains incomplete until a resumed run passes:

1. full locked dataset manifest/tree verification;
2. locked CPU llama.cpp, GGUF/mmproj, layout model, and pipeline checkout;
3. exactly ten fresh non-empty UTF-8 predictions;
4. exact ten-page ground-truth manifest at 100% coverage;
5. finite Windows metrics and positive WSL CDM;
6. exact full verification; and
7. a second `-Resume` run proving idempotency.