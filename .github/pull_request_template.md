## Summary

Describe the user-facing problem and the smallest implemented correction.

## Validation

- [ ] `uv sync --locked --all-groups`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q`
- [ ] Modified PowerShell scripts parse under Windows PowerShell 5.1
- [ ] Modified Bash scripts pass `bash -n`
- [ ] Setup changes were followed immediately by their verifier
- [ ] English and Chinese entry-point documentation remain aligned
- [ ] No datasets, models, predictions, virtual environments, credentials, or machine-local paths are tracked

## Hardware Evidence

State `not applicable` for deterministic CI-only changes. For GPU, CDM, scoring,
or benchmark changes, include hardware, driver/backend, exact config, artifact
hashes, sample counts, failures/timeouts, and verifier output.
