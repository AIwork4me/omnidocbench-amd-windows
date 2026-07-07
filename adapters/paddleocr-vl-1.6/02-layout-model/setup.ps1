<#
.SYNOPSIS
Download the PP-DocLayoutV3 ONNX layout model for the PaddleOCR-VL-1.6 adapter.

.DESCRIPTION
Provisions the layout-detection half of the adapter. PP-DocLayoutV3 is the
page-layout detector (paragraphs, tables, figures, reading order) that
PaddleOCR-VL-ROCm runs on CPU/GPU via ONNXRuntime before cropping regions for
the VLM server (01-vlm-server/).

This script downloads exactly two files from HuggingFace (or ModelScope, per
mirrors.env):

  - inference.onnx  (~16 MB) -- the layout model weights
  - inference.yml              -- model config (image size, label map, ...)

into adapters/paddleocr-vl-1.6/models/PP-DocLayoutV3-onnx/, and writes that
directory to adapters/paddleocr-vl-1.6/.env.local under
PP_DOCLAYOUTV3_ONNX_DIR so run_adapter.py picks it up as the default
--layout-model.

Idempotent: a no-op if inference.onnx is already present.

.PARAMETER ModelDir
Local destination directory. Defaults to
adapters/paddleocr-vl-1.6/models/PP-DocLayoutV3-onnx.

.PARAMETER Source
Download source: "auto" (default), "huggingface", or "modelscope".

.PARAMETER Force
Redownload even if inference.onnx already exists.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Source modelscope
#>
[CmdletBinding()]
param(
    [string] $ModelDir,
    [ValidateSet("auto", "huggingface", "modelscope")]
    [string] $Source = "auto",
    [switch] $Force
)
$ErrorActionPreference = "Stop"

$adapterRoot = Split-Path -Parent $PSScriptRoot
$repoRoot    = Split-Path -Parent (Split-Path -Parent $adapterRoot)
if ([string]::IsNullOrWhiteSpace($ModelDir)) {
    $ModelDir = Join-Path $adapterRoot "models\PP-DocLayoutV3-onnx"
}
$envFile = Join-Path $adapterRoot ".env.local"

# --- mirrors.env (HF_OR_MS) ---
$mirrorsFile = Join-Path $repoRoot "mirrors.env"
$mirrors = @{}
if (Test-Path $mirrorsFile) {
    Get-Content $mirrorsFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.*)$") { $mirrors[$matches[1]] = $matches[2] }
    }
}
# Resolve "auto": honour mirrors.env HF_OR_MS, else prefer huggingface for this
# small model (it is mirrored on both).
if ($Source -eq "auto") {
    $Source = if ($mirrors["HF_OR_MS"]) { $mirrors["HF_OR_MS"] } else { "huggingface" }
}

$repoId = "PaddlePaddle/PP-DocLayoutV3_onnx"
$required = @("inference.onnx", "inference.yml")

# --- .env.local helpers (KEY='VALUE') ---
function Get-DotEnv {
    param([string]$Path)
    $v = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $v }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        if ($t -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
            $val = $matches[2].Trim()
            if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and $val[0] -in @("'", '"')) {
                $val = $val.Substring(1, $val.Length - 2)
            }
            $v[$matches[1]] = $val
        }
    }
    return $v
}
function Set-DotEnv {
    param([string]$Path, [hashtable]$Values)
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path) }
    foreach ($key in $Values.Keys) {
        $pat = [regex]::Escape($key)
        $quoted = "'" + (([string]$Values[$key]) -replace "'", "\'") + "'"
        $newLine = "$key=$quoted"
        $hit = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^\s*$pat\s*=") { $lines[$i] = $newLine; $hit = $true; break }
        }
        if (-not $hit) { $lines += $newLine }
    }
    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

$onnxFile = Join-Path $ModelDir "inference.onnx"
if ((Test-Path $onnxFile) -and -not $Force) {
    $sizeMB = [math]::Round((Get-Item $onnxFile).Length / 1MB, 1)
    Write-Host "PP-DocLayoutV3 ONNX already present: $onnxFile ($sizeMB MB)" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
    Write-Host "Downloading $repoId via $Source ..." -ForegroundColor Cyan
    Write-Host "  Destination: $ModelDir"
    Write-Host "  Files: $($required -join ', ')"

    # Drive the download from python so the same snippet works for both
    # huggingface_hub and modelscope. Either lib is a one-line pip install.
    $dl = @"
import sys
from pathlib import Path
model_dir = Path(r'$ModelDir')
model_dir.mkdir(parents=True, exist_ok=True)
required = $required
source = '$Source'
repo_id = '$repoId'

if source == 'huggingface':
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        sys.exit('huggingface_hub not installed. Run: pip install huggingface_hub')
    for name in required:
        p = hf_hub_download(repo_id=repo_id, filename=name, local_dir=str(model_dir))
        print(f'Downloaded {name} -> {p}')
elif source == 'modelscope':
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        try:
            from modelscope import snapshot_download
        except ImportError:
            sys.exit('modelscope not installed. Run: pip install modelscope')
    # snapshot_download fetches the whole repo snapshot; allow_patterns keeps
    # it to just the two files we need.
    p = snapshot_download(model_id=repo_id, local_dir=str(model_dir), allow_patterns=required)
    print(f'Downloaded to {p}')
else:
    sys.exit('Unknown source: ' + source)
"@
    $venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $pythonExe = if (Test-Path $venvPy) { $venvPy } else { "python" }
    $dl | & $pythonExe -
    if ($LASTEXITCODE -ne 0) { throw "PP-DocLayoutV3 download failed (source=$Source)" }
}

if (-not (Test-Path $onnxFile)) {
    throw "inference.onnx not found after download at $ModelDir"
}

# Verify both required files are present.
$missing = @($required | Where-Object { -not (Test-Path (Join-Path $ModelDir $_)) })
if ($missing.Count -gt 0) {
    throw "Model dir $ModelDir is missing: $($missing -join ', ')"
}

$resolved = (Resolve-Path $ModelDir).Path
$sizeMB = [math]::Round((Get-Item $onnxFile).Length / 1MB, 1)
Write-Host ""
Write-Host "PP-DocLayoutV3 ONNX ready: $onnxFile ($sizeMB MB)" -ForegroundColor Green

Set-DotEnv -Path $envFile -Values @{ PP_DOCLAYOUTV3_ONNX_DIR = $resolved }
Write-Host "Updated $envFile (PP_DOCLAYOUTV3_ONNX_DIR)" -ForegroundColor Green
exit 0
