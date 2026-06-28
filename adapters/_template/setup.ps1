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

# repo root = two Split-Path -Parent calls from adapters/_template/
# ($PSScriptRoot = adapters/_template; one Split-Path -> adapters/; two -> repo root)
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

# --- Scaffold a .env.local template (gitignored) ----------------------------
# Adapters conventionally write machine-local paths (model weights, server URLs,
# etc.) to a gitignored .env.local so committed code stays machine-agnostic.
# We seed one here with the common adapter keys so a copy of this template has
# a concrete starting point. The user edits it (or has their real setup.ps1
# overwrite it) with actual values. Idempotent: never clobbers an existing file.
$envLocalExample = Join-Path $PSScriptRoot ".env.local.example"
$envLocal        = Join-Path $PSScriptRoot ".env.local"
$envLocalTemplate = @"
# adapters/<your-model>/.env.local -- machine-local paths (gitignored).
# Written by setup.ps1; read by run_adapter.py. KEY='VALUE' (single quotes
# recommended so paths with special chars round-trip). Edit these to match
# your machine, then run the adapter.
# After renaming <your-model>, replace ADAPTER_* with your real keys as needed.

# Where your model server listens (if it uses a server). Empty = no server.
ADAPTER_SERVER_URL='http://127.0.0.1:8080/v1'
# Model/API name your server exposes (if applicable).
ADAPTER_API_MODEL_NAME='your-model-name'
# Directory holding your model weights / assets (absolute path).
ADAPTER_MODEL_DIR='C:\path\to\your\model'
"@
if (-not (Test-Path $envLocalExample)) {
    Set-Content -LiteralPath $envLocalExample -Value $envLocalTemplate -Encoding UTF8
}
# Only create the live .env.local from the example if neither exists yet, so a
# user's hand-edited file is never overwritten on re-run.
if (-not (Test-Path $envLocal) -and -not (Test-Path $envLocalExample.Replace(".example",""))) {
    Copy-Item $envLocalExample $envLocal -Force
}

Write-Host "TODO: provision your model here." -ForegroundColor Yellow
Write-Host "  repoRoot    = $repoRoot" -ForegroundColor DarkGray
Write-Host "  GITHUB_BASE = $githubBase" -ForegroundColor DarkGray
Write-Host "  HF_OR_MS    = $hfOrMs" -ForegroundColor DarkGray
Write-Host "" -ForegroundColor Gray
Write-Host "What to replace:" -ForegroundColor Yellow
Write-Host "  1. run_adapter.py  -- implement run_adapter(img_dir, out_dir, server_url)" -ForegroundColor Gray
Write-Host "                       to call your model and write <stem>.md per page." -ForegroundColor Gray
Write-Host "  2. this setup.ps1  -- add the real provisioning (download weights, start a" -ForegroundColor Gray
Write-Host "                       server, etc.). See paddleocr-vl-1.6/ for a full example," -ForegroundColor Gray
Write-Host "                       or split into numbered sub-directories (01-..., 02-...)." -ForegroundColor Gray
Write-Host "  3. .env.local      -- seeded at $envLocal (edit the placeholder values)." -ForegroundColor Gray
Write-Host "  4. README.md       -- describe what your model is and why." -ForegroundColor Gray
Write-Host "" -ForegroundColor Gray
Write-Host "Template ready to customize. Until you replace the TODO body, this script is a" -ForegroundColor Green
Write-Host "no-op and run_adapter.py writes placeholder Markdown." -ForegroundColor Green
exit 0
