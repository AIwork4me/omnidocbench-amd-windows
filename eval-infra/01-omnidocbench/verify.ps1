<#
.SYNOPSIS
Verify OmniDocBench eval code + v1.6 dataset are present and complete.

Checks:
  - OmniDocBench/pdf_validation.py exists (code cloned).
  - data/OmniDocBench.json exists (GT manifest downloaded).
  - data/images/ contains ~1651 page images.
  - Optional: a hard-subset manifest exists for v16-hard.yaml
    (data/OmniDocBench_hard296.json). This is a derivative file produced by
    filtering the full manifest; its absence is a WARNING, not a failure.

Exit code 0 = OK, 1 = FAIL. Suitable for chaining in full-verify.ps1 (Task 7).
#>
$ErrorActionPreference = "Stop"

function ConvertTo-ExtendedPath {
    param([string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ($fullPath.StartsWith("\\")) {
        return "\\?\UNC\" + $fullPath.Substring(2)
    }
    return "\\?\" + $fullPath
}

function Test-FileExtended {
    param([string]$Path)
    return [System.IO.File]::Exists((ConvertTo-ExtendedPath -Path $Path))
}

function Get-ShortRepoRoot {
    param([string]$RepoRoot)
    $normalizedRoot = [System.IO.Path]::GetFullPath($RepoRoot)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedRoot.ToLowerInvariant()))
    } finally {
        $sha.Dispose()
    }
    $hash = ([System.BitConverter]::ToString($hashBytes) -replace "-", "").ToLowerInvariant().Substring(0, 12)
    return Join-Path (Join-Path (Join-Path $env:LOCALAPPDATA "OmniDocBenchAMD") $hash) "repo"
}

$odbDir  = Join-Path $PSScriptRoot "OmniDocBench"
$dataDir = Join-Path $PSScriptRoot "data"

$ok = $true

# --- Code ---
$probe = Join-Path $odbDir "pdf_validation.py"
if (-not (Test-Path $probe)) {
    Write-Host "FAIL: OmniDocBench code missing (pdf_validation.py not found at $probe)." -ForegroundColor Red
    Write-Host "      Run setup.ps1 to clone the repo." -ForegroundColor DarkGray
    $ok = $false
} else {
    Write-Host "OK: OmniDocBench code present ($probe)" -ForegroundColor Green
}

# --- GT manifest ---
$manifest = Join-Path $dataDir "OmniDocBench.json"
if (-not (Test-Path $manifest)) {
    Write-Host "FAIL: GT manifest missing (OmniDocBench.json not found at $manifest)." -ForegroundColor Red
    Write-Host "      Run setup.ps1 to download the dataset." -ForegroundColor DarkGray
    $ok = $false
} else {
    Write-Host "OK: GT manifest present ($manifest)" -ForegroundColor Green
}

# --- Images (every manifest reference must exist) ---
$imgDir   = Join-Path $dataDir "images"
if (Test-Path $manifest) {
    try {
        $manifestPages = @(Get-Content -Raw -Encoding UTF8 -LiteralPath $manifest | ConvertFrom-Json)
        $imagePaths = @($manifestPages | ForEach-Object { $_.page_info.image_path } | Where-Object { $_ })
        $missingImages = @($imagePaths | Where-Object { -not (Test-FileExtended -Path (Join-Path $imgDir $_)) })
        if ($imagePaths.Count -eq 0) {
            Write-Host "FAIL: manifest contains no page_info.image_path entries." -ForegroundColor Red
            $ok = $false
        } elseif ($missingImages.Count -gt 0) {
            Write-Host ("FAIL: {0}/{1} manifest-referenced images are missing from {2}." -f $missingImages.Count, $imagePaths.Count, $imgDir) -ForegroundColor Red
            Write-Host ("      First missing: " + (($missingImages | Select-Object -First 5) -join ", ")) -ForegroundColor DarkGray
            $ok = $false
        } else {
            Write-Host ("OK: all {0} manifest-referenced page images are present." -f $imagePaths.Count) -ForegroundColor Green
            $rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
            $shortRoot = Get-ShortRepoRoot -RepoRoot $rootDir
            $shortImages = Join-Path $shortRoot "eval-infra\01-omnidocbench\data\images"
            if (-not (Test-Path -LiteralPath $shortRoot)) {
                Write-Host "FAIL: Windows short repository path missing: $shortRoot" -ForegroundColor Red
                Write-Host "      Re-run setup.ps1 so Python adapters can consume MAX_PATH images." -ForegroundColor DarkGray
                $ok = $false
            } else {
                $shortMissing = @($imagePaths | Where-Object { -not (Test-Path -LiteralPath (Join-Path $shortImages $_)) })
                if ($shortMissing.Count -gt 0) {
                    Write-Host "FAIL: $($shortMissing.Count) images are not readable through the Windows short repository path." -ForegroundColor Red
                    $ok = $false
                } else {
                    Write-Host "OK: all images are consumable through short path $shortImages" -ForegroundColor Green
                }
            }
        }
    } catch {
        Write-Host "FAIL: could not validate manifest image references: $($_.Exception.Message)" -ForegroundColor Red
        $ok = $false
    }
}

# --- Hard subset manifest (optional derivative; WARNING only) ---
$hardManifest = Join-Path $dataDir "OmniDocBench_hard296.json"
if (-not (Test-Path $hardManifest)) {
    Write-Host "WARN: hard-subset manifest missing ($hardManifest)." -ForegroundColor Yellow
    Write-Host "      Not required for the full run; v16-hard.yaml needs it." -ForegroundColor DarkGray
    Write-Host "      It is auto-derived by score.ps1 -Config v16-hard.yaml on first use." -ForegroundColor DarkGray
} else {
    Write-Host "OK: hard-subset manifest present ($hardManifest)" -ForegroundColor Green
}

if ($ok) {
    Write-Host "VERIFY OK: OmniDocBench code + dataset ready." -ForegroundColor Green
    exit 0
} else {
    Write-Host "VERIFY FAILED: see messages above." -ForegroundColor Red
    exit 1
}
