# Windows Upstream Lock

`upstream-lock.json` is the executable content contract for every external
input consumed by the AMD Windows reference path. Mirrors may change transport;
they may not change bytes.

## Locked Inputs

- OmniDocBench and PaddleOCR-VL-ROCm Git commits.
- llama.cpp release tag/commit plus CPU and HIP Windows ZIP hashes.
- PaddleOCR-VL GGUF and mmproj Hugging Face revision, sizes, and SHA-256.
- PP-DocLayoutV3 ONNX/YAML revision, sizes, and SHA-256.
- OmniDocBench dataset revision, manifest hash, and a deterministic tree digest
  over all 1,651 referenced images.
- Ubuntu Base fallback rootfs and ImageMagick AppImage sizes and SHA-256.
- Expected WSL CDM toolchain versions.

Setup scripts fail closed before executing or scoring mismatched content.
`scripts/verify-upstream-lock.ps1` validates individual Windows artifacts and
Git checkouts. `scripts/verify_dataset_tree.py` validates the complete dataset
through the repository's MAX_PATH-safe short-root junction.

## Update Procedure

1. Update only one upstream component at a time.
2. Download from the canonical source and verify any upstream checksum/signature.
3. Record immutable revision, exact byte size, and SHA-256 in
   `upstream-lock.json`.
4. Run corruption and commit-mismatch tests:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q tests\test_upstream_lock.py
   ```

5. Run the relevant setup and verifier twice to prove lock enforcement and
   idempotency.
6. Perform a new isolated `cpu-smoke-10` clean-room run. A lock update is not
   releasable based only on unit tests or old predictions.
7. Record the new public commit, machine versions, artifact hashes, and evidence
   file under `docs/`.

Never replace a hash merely because a mirror returned different content.
Investigate the source/revision first.

## 2026-08-02 update: WSL CDM TeX Live tlpdb re-lock (evidence-based)

**Reason:** the WSL TL2026 `texlive.tlpdb` on the Ryzen AI MAX+ 395 /
Radeon 8060S machine did not match the lock. Investigation (not a mirror
change):

- The lock recorded tlpdb `4,871,636` bytes / sha `4013c1ec…`, tlmgr
  revision `79639` — a tree built on the 2026-07-26 reference machine
  (Radeon 860M constrained machine).
- On this machine a `scheme-infraonly` install-tl run on 2026-07-07
  replaced the tlpdb with the 290-package infra-only database (1,387,786
  bytes), while the installed files (8,053 packages, 498 MB tree) remained
  intact — the 20,342,364-byte tlpdb backup
  `texlive.tlpdb.main.dcc1eb96ab0617262ce39e8fad083b3e` survived.
- No reachable mirror serves the exact 2026-07-26 snapshot (texlive.info
  and CTAN tlnet-archives unreachable; live CTAN tlpdb is now ~20 MB and
  has moved on), so the previous tlpdb hash was not reproducible on this
  machine at all.

**Fix (evidence-gated):** restore the tlpdb to the installed-package state
from the local tlmgr backup, then re-verify the whole CDM pipeline
end-to-end with the repo's own `verify.sh` standard:

- `pdflatex` compile of a `\mathcolor` CJK document: OK
- `magick` PDF→PNG: 4 colors (not grayscale — `\mathcolor` fix active)
- identical-formula CDM F1 = 1.0 (`src.metrics.cdm_metric`)
- ImageMagick 7.1.2-26 and Ghostscript 9.55.0 unchanged (they already
  matched the lock)
- WSL odb-venv re-synced to `requirements.lock.txt` (was stale) and
  `verify_requirements_lock.py` passes
- `eval-infra/02-cdm-environment/verify.sh` prints `VERIFY OK`

**New lock values:** `texlive_tlpdb_bytes=20342364`,
`texlive_tlpdb_sha256=2c6aad37ea703d5ed5bbf7f2321dec6929c6201ecfcd284c06be40d3166d8d6c`,
`texlive_tlmgr_revision=79491` (tlmgr 2026-06-27). Ubuntu 22.04.5 / Python
3.10.12 / TL2026 / IM 7.1.2-26 / gs >= 9.55.0 unchanged. `verified_at` now
2026-08-02 (previous value recorded as `verified_at_previous`).