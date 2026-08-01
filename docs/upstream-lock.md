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