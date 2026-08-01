<#
.SYNOPSIS
Validate prerequisites before downloads, model setup, or scoring.

.DESCRIPTION
Checks the repository path, free disk, Git, the locked Python environment,
mirror detection output, the selected inference variant, and one CDM path.
All checks run before the script returns so a new user gets one actionable
prerequisite report instead of discovering failures during long setup phases.

.PARAMETER CdmPath
WSL compatibility/reference path (Wsl), native Windows CDM (Windows), or only
common prerequisites (None). Default: Wsl.

.PARAMETER Variant
Reference adapter backend: hip requires an AMD display adapter; cpu does not.

.PARAMETER Python
Python executable to validate. Defaults to .venv\Scripts\python.exe.

.PARAMETER GitExecutable
Git executable to validate. Defaults to git from PATH.

.PARAMETER SkipNetwork
Skip mirrors.env validation. Intended for focused offline tests only.
#>
[CmdletBinding()]
param(
    [ValidateSet("Wsl", "Windows", "None")]
    [string] $CdmPath = "Wsl",
    [ValidateSet("hip", "cpu")]
    [string] $Variant = "hip",
    [string] $Python = "",
    [string] $GitExecutable = "",
    [double] $MinimumFreeGB = 50,
    [switch] $SkipNetwork
)
$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $PSScriptRoot
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$passed = New-Object System.Collections.Generic.List[string]

function Add-Pass([string] $Message) {
    $script:passed.Add($Message)
    Write-Host "PASS  $Message" -ForegroundColor Green
}

function Add-Warn([string] $Message) {
    $script:warnings.Add($Message)
    Write-Host "WARN  $Message" -ForegroundColor Yellow
}

function Add-Fail([string] $Message) {
    $script:failures.Add($Message)
    Write-Host "FAIL  $Message" -ForegroundColor Red
}

Write-Host "=== OmniDocBench AMD Windows preflight ===" -ForegroundColor Cyan
Write-Host "Repo: $rootDir" -ForegroundColor DarkGray
Write-Host "Variant: $Variant | CDM path: $CdmPath" -ForegroundColor DarkGray

# Repository path and write access.
if ($rootDir.Length -gt 180) {
    Add-Warn "Repository path is $($rootDir.Length) characters; deeply nested generated paths may approach Windows path limits."
} else {
    Add-Pass "Repository path length: $($rootDir.Length) characters"
}
$writeProbe = Join-Path $rootDir ".preflight-write-$PID.tmp"
try {
    Set-Content -LiteralPath $writeProbe -Value "ok" -Encoding ASCII
    Remove-Item -LiteralPath $writeProbe -Force
    Add-Pass "Repository directory is writable"
} catch {
    Add-Fail "Repository directory is not writable: $($_.Exception.Message)"
}

# Disk capacity on the repository drive.
try {
    $rootPath = [System.IO.Path]::GetPathRoot($rootDir)
    $drive = New-Object System.IO.DriveInfo($rootPath)
    $freeGB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    if ($freeGB -lt $MinimumFreeGB) {
        Add-Fail "Only $freeGB GiB free on $rootPath; at least $MinimumFreeGB GiB is required."
    } else {
        Add-Pass "Free disk: $freeGB GiB on $rootPath"
    }
} catch {
    Add-Fail "Could not determine repository-drive free space: $($_.Exception.Message)"
}

# Git is mandatory for the upstream checkouts and patches.
$gitCommand = $null
if ([string]::IsNullOrWhiteSpace($GitExecutable)) {
    $resolvedGit = Get-Command git -ErrorAction SilentlyContinue
    if ($resolvedGit) { $gitCommand = $resolvedGit.Source }
} elseif (Test-Path -LiteralPath $GitExecutable -PathType Leaf) {
    $gitCommand = $GitExecutable
}
if (-not $gitCommand) {
    Add-Fail "Git not found. Install Git for Windows, reopen PowerShell, and re-run preflight."
} else {
    try {
        $gitVersion = & $gitCommand --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $gitVersion -match '^git version ') {
            Add-Pass "$gitVersion"
        } else {
            Add-Fail "Git could not run: $gitCommand ($gitVersion)"
        }
    } catch {
        Add-Fail "Git could not run: $gitCommand ($($_.Exception.Message))"
    }
}

# The local Python is mandatory and must match OmniDocBench's supported range.
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $rootDir ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Add-Fail "Locked Python not found: $Python. Run 'uv python install 3.11' and 'uv sync --locked --all-groups'."
} else {
    try {
        $pythonVersion = & $Python --version 2>&1
        if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.(10|11)\.') {
            Add-Fail "OmniDocBench requires Python 3.10 or 3.11 (found: '$pythonVersion'). Run 'uv sync --locked --all-groups'."
        } else {
            Add-Pass "$pythonVersion ($Python)"
        }
    } catch {
        Add-Fail "Python could not run: $Python ($($_.Exception.Message))"
    }
}

# Mirror detection is the network contract consumed by all setup phases.
if ($SkipNetwork) {
    Add-Warn "Network source validation skipped"
} else {
    $mirrorsFile = Join-Path $rootDir "mirrors.env"
    if (-not (Test-Path -LiteralPath $mirrorsFile -PathType Leaf)) {
        Add-Fail "mirrors.env missing. Run scripts\detect-mirrors.ps1."
    } else {
        $mirrorValues = @{}
        Get-Content -LiteralPath $mirrorsFile | ForEach-Object {
            if ($_ -match '^([^#=]+)=(.*)$') { $mirrorValues[$matches[1].Trim()] = $matches[2].Trim() }
        }
        $requiredMirrorKeys = @("DATASET_URL", "VLM_MODEL_URL", "LAYOUT_MODEL_URL", "GITHUB_BASE", "PYPI_INDEX")
        $missingMirrorKeys = @($requiredMirrorKeys | Where-Object { [string]::IsNullOrWhiteSpace($mirrorValues[$_]) })
        if ($mirrorValues["NETWORK_STATUS"] -ne "ok" -or $missingMirrorKeys.Count -gt 0) {
            Add-Fail "Network sources are incomplete ($($missingMirrorKeys -join ', ')). Re-run scripts\detect-mirrors.ps1; see docs/pitfalls.md#network."
        } else {
            Add-Pass "Network sources selected (NETWORK_STATUS=ok)"
        }
    }
}

# HIP requires an AMD adapter. Shared-memory WMI values are not treated as VRAM evidence.
if ($Variant -eq "hip") {
    try {
        $gpuNames = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name } | Where-Object { $_ })
        $amdGpus = @($gpuNames | Where-Object { $_ -match 'AMD|Radeon' })
        if ($amdGpus.Count -eq 0) {
            Add-Fail "No AMD/Radeon display adapter found for -Variant hip. Use -Variant cpu or install the supported driver."
        } else {
            Add-Pass "AMD GPU detected: $($amdGpus -join ' + ')"
            Add-Warn "Usable VRAM and HIP execution must still be confirmed after the VLM server starts."
        }
    } catch {
        Add-Fail "Could not query display adapters: $($_.Exception.Message)"
    }
} else {
    Add-Pass "CPU adapter variant selected; AMD GPU is not mandatory"
}

if ($CdmPath -eq "Wsl") {
    $wslCommand = Get-Command wsl -ErrorAction SilentlyContinue
    if (-not $wslCommand) {
        Add-Fail "WSL command not found. Run scripts\wsl-ensure.ps1, then reboot if Windows requests it."
    } else {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $distrosOutput = wsl --list --quiet 2>$null
            $wslListExit = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        $distros = ((@($distrosOutput) -join "`n") -replace "`0", "").Trim()
        if ($wslListExit -ne 0) {
            Add-Fail "WSL is not active. Run scripts\wsl-ensure.ps1; a Windows reboot may be required."
        } elseif ($distros -notmatch '(?m)^Ubuntu2204$') {
            Add-Fail "WSL distro Ubuntu2204 is missing. Run scripts\wsl-ensure.ps1."
        } else {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $wslProbe = wsl -d Ubuntu2204 -- echo OK 2>$null
                $wslProbeExit = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
            if ($wslProbeExit -ne 0 -or ((@($wslProbe) -join "") -replace "`0", "").Trim() -ne "OK") {
                Add-Fail "Ubuntu2204 is registered but cannot start. A Windows reboot may be required."
            } else {
                Add-Pass "WSL Ubuntu2204 starts successfully"
            }
        }
    }
} elseif ($CdmPath -eq "Windows") {
    foreach ($tool in @("pdflatex", "magick", "gswin64c")) {
        if (Get-Command $tool -ErrorAction SilentlyContinue) {
            Add-Pass "Native CDM tool found: $tool"
        } else {
            Add-Fail "Native CDM tool missing: $tool. Install it or use -CdmPath Wsl."
        }
    }
} else {
    Add-Warn "CDM toolchain checks skipped; this mode cannot validate Formula CDM readiness"
}

Write-Host ""
Write-Host "Summary: $($passed.Count) passed, $($warnings.Count) warnings, $($failures.Count) failed" -ForegroundColor Cyan
if ($failures.Count -gt 0) {
    Write-Host "PRECHECK FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "PRECHECK OK" -ForegroundColor Green
exit 0