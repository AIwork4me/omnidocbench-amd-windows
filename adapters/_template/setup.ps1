<#
.SYNOPSIS
Template provisioning script for a model adapter.

.DESCRIPTION
This is a starting point. Copy this file (and the rest of ``_template/``) into
``adapters/<your-model>/`` and replace the TODO body with whatever your model
needs to be ready to run ``run_adapter.py``: downloading weights, starting a
serving process, setting up a venv, writing paths to an env file, etc.

The PaddleOCR-VL-1.6 reference adapter splits provisioning into numbered
sub-directories (``01-vlm-server/``, ``02-layout-model/``), each with its own
``setup.ps1``. You can keep the same structure or collapse everything into one
script -- either is fine as long as ``run_adapter.py`` can run afterwards.

Conventions used by the rest of this repo (match them so ``full-verify.ps1``
can chain your verify step):
  - Idempotent: re-running after success is a no-op (or resumes a partial run).
  - Reads ``$repoRoot\mirrors.env`` for GITHUB_BASE / HF_OR_MS so downloads are
    China-firewall-aware.
  - Writes machine-local paths to a gitignored env file (``.env.local``), never
    to committed code.
  - ``$ErrorActionPreference = "Stop"``; throws on failure.
  - Windows PowerShell 5.1 compatible (no pwsh-only syntax).

.PARAMETER Force
Redownload / reprovision even if the model already appears ready.
#>
[CmdletBinding()]
param(
    [switch] $Force
)
$ErrorActionPreference = "Stop"

# repo root = three levels up from adapters/_template/
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envFile  = Join-Path $repoRoot "mirrors.env"

# --- Parse mirrors.env (KEY=VALUE; ignore comments / blanks) ---
$cfg = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.*)$") { $cfg[$matches[1]] = $matches[2] }
    }
}
$githubBase = if ($cfg["GITHUB_BASE"]) { $cfg["GITHUB_BASE"] } else { "https://github.com" }
$hfOrMs     = if ($cfg["HF_OR_MS"])    { $cfg["HF_OR_MS"] }    else { "modelscope" }

Write-Host "TODO: provision your model here." -ForegroundColor Yellow
Write-Host "  repoRoot    = $repoRoot" -ForegroundColor DarkGray
Write-Host "  GITHUB_BASE = $githubBase" -ForegroundColor DarkGray
Write-Host "  HF_OR_MS    = $hfOrMs" -ForegroundColor DarkGray
Write-Host "Replace this body with the real provisioning steps," -ForegroundColor Yellow
Write-Host "or split into numbered sub-directories like paddleocr-vl-1.6/." -ForegroundColor Yellow
Write-Host "Template setup complete (no-op)." -ForegroundColor Green
exit 0
