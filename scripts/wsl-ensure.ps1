<#
.SYNOPSIS
Ensures a WSL Ubuntu 22.04 distro named "Ubuntu2204" is installed.

Handles two cases:
  1. The standard `wsl --install` path (creates a distro named "Ubuntu-22.04").
  2. The China-network case where `wsl --install` fails (Store blocked):
     import a rootfs tarball from the USTC mirror as "Ubuntu2204".

.DESCRIPTION
All scripts in this repo address the WSL distro as **Ubuntu2204** (no dot, no
dash). That is the canonical name everywhere (CLAUDE.md, full-verify.ps1,
score-cdm.sh, the module READMEs, the \\wsl$\Ubuntu2204\ UNC path, ...).

`wsl --install -d Ubuntu-22.04` creates a distro named **Ubuntu-22.04**
(with a dot and dash) -- which then does NOT match the `Ubuntu2204` references,
so every `wsl -d Ubuntu2204 ...` call downstream fails with "not found" even
though a perfectly good distro exists. This script normalizes that: if
`Ubuntu-22.04` exists but `Ubuntu2204` does not, it renames the former to the
latter via export/unregister/import.

Idempotent: a no-op if `Ubuntu2204` already exists and is startable.
#>
$ErrorActionPreference = "Stop"

# Canonical distro name used by every other script in this repo.
$DistroName = "Ubuntu2204"
# Name `wsl --install` produces for the Ubuntu 22.04 image.
$InstallName = "Ubuntu-22.04"

# wsl --list writes UTF-16LE text with embedded NUL bytes; PowerShell 5.1
# captures those NULs, which breaks -match on the distro name. Strip them.
function Get-WslDistros {
    $cleaned = (wsl --list --quiet 2>$null) | ForEach-Object { ($_ -replace "`0","").Trim() } | Where-Object { $_ }
    return ($cleaned -join "`n")
}

# Rename $From -> $To via export/unregister/import. Used to normalize the
# "Ubuntu-22.04" distro that `wsl --install` creates into the canonical
# "Ubuntu2204" name the rest of the repo expects. No-op if $To already exists.
function Rename-WslDistro {
    param([string]$From, [string]$To)
    $distros = Get-WslDistros
    if ($distros -match [regex]::Escape($To)) {
        Write-Host "  Distro '$To' already exists; no rename needed." -ForegroundColor DarkGray
        return
    }
    if (-not ($distros -match [regex]::Escape($From))) {
        Write-Host "  Source distro '$From' not found; nothing to rename." -ForegroundColor DarkGray
        return
    }
    $tarball = Join-Path $env:TEMP "${From}_rename.tar.gz"
    $importDir = "C:\WSL\$To"
    Write-Host "  Renaming WSL distro '$From' -> '$To' ..." -ForegroundColor Cyan
    Write-Host "    export -> $tarball" -ForegroundColor DarkGray
    wsl --export $From $tarball
    if ($LASTEXITCODE -ne 0) { throw "wsl --export $From failed" }
    Write-Host "    unregister $From" -ForegroundColor DarkGray
    wsl --unregister $From
    if ($LASTEXITCODE -ne 0) { throw "wsl --unregister $From failed" }
    New-Item -ItemType Directory -Force -Path $importDir | Out-Null
    Write-Host "    import as $To -> $importDir" -ForegroundColor DarkGray
    wsl --import $To $importDir $tarball --version 2
    if ($LASTEXITCODE -ne 0) { throw "wsl --import $To failed" }
    Remove-Item -Force $tarball -ErrorAction SilentlyContinue
    Write-Host "  Renamed '$From' -> '$To'." -ForegroundColor Green
}

# --- Check if the canonical distro already exists ----------------------------
$distros = Get-WslDistros
if ($distros -match $DistroName) {
    Write-Host "WSL $DistroName already installed." -ForegroundColor Green
    # Escape the $ so WSL (bash) evaluates whoami/hostname, not PowerShell.
    # Without the backtick-escaping PowerShell would interpolate the WINDOWS
    # user/host here, printing a misleading "OK" host string.
    wsl -d $DistroName -- bash -c 'echo "WSL OK: $(whoami)@$(hostname)"'
    exit 0
}

# --- Try standard install first ----------------------------------------------
# `wsl --install -d Ubuntu-22.04 --no-launch` creates a distro named
# "Ubuntu-22.04" (NOT Ubuntu2204). We normalize it below.
Write-Host "Attempting wsl --install ..." -ForegroundColor Cyan
wsl --install -d $InstallName --no-launch 2>$null
$installOk = ($LASTEXITCODE -eq 0 -and ((Get-WslDistros) -match "Ubuntu"))

if ($installOk) {
    Write-Host "WSL installed via wsl --install (as '$InstallName')." -ForegroundColor Green
    # Normalize the distro name to the canonical Ubuntu2204 the rest of the
    # repo expects. This is the fix for the Ubuntu-22.04 vs Ubuntu2204 mismatch.
    Rename-WslDistro -From $InstallName -To $DistroName
} else {
    Write-Host "wsl --install failed (likely Store blocked). Falling back to rootfs import." -ForegroundColor Yellow

    # Read mirror URL from mirrors.env
    # NOTE: Join-Path is nested (rather than the PS 7+ 3-arg form) so this runs on
    # Windows PowerShell 5.1 as well as PowerShell 7+.
    $envFile = Join-Path (Join-Path $PSScriptRoot "..") "mirrors.env"
    $rootfsUrl = "https://mirrors.ustc.edu.cn/ubuntu-cdimage/ubuntu-base/releases/22.04/release/ubuntu-base-22.04.5-base-amd64.tar.gz"
    if (Test-Path $envFile) {
        $cfg = Get-Content $envFile | Where-Object { $_ -match "^UBUNTU_ROOTFS=" }
        if ($cfg) { $rootfsUrl = ($cfg -split "=", 2)[1] }
    }

    # Download rootfs. Try the configured mirror first, then a second independent
    # source (Tsinghua's ubuntu-cdimage mirror) before giving up. If USTC is
    # specifically down (a narrow but real failure mode), the second source
    # often still works.
    $tarball = "$env:TEMP\ubuntu-22.04.tar.gz"
    $rootfsSources = @(
        $rootfsUrl,
        "https://mirrors.tuna.tsinghua.edu.cn/ubuntu-cdimage/ubuntu-base/releases/22.04/release/ubuntu-base-22.04.5-base-amd64.tar.gz"
    )
    $downloaded = $false
    foreach ($src in $rootfsSources) {
        Write-Host "Downloading Ubuntu rootfs from $src ..." -ForegroundColor Cyan
        try {
            Invoke-WebRequest -Uri $src -OutFile $tarball -TimeoutSec 300 -ErrorAction Stop
            $downloaded = $true
            break
        } catch {
            Write-Host "  download from $src failed: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    if (-not $downloaded) {
        # Both sources failed. Give actionable recovery instead of a raw
        # WebException so a blocked user has a path forward.
        Write-Host "FAILED: could not download the Ubuntu rootfs from any mirror." -ForegroundColor Red
        Write-Host "  Tried: $($rootfsSources -join ', ')" -ForegroundColor Yellow
        Write-Host "  Things to try:" -ForegroundColor Yellow
        Write-Host "    1) Check your network / VPN (corporate firewalls often block these hosts)." -ForegroundColor Yellow
        Write-Host "    2) Download the rootfs manually from https://cloud-images.ubuntu.com/releases/22.04/release/" -ForegroundColor Yellow
        Write-Host "       and place it at $tarball, then re-run this script." -ForegroundColor Yellow
        Write-Host "    3) If you already have an Ubuntu distro under a different name," -ForegroundColor Yellow
        Write-Host "       rename it to 'Ubuntu2204' (see docs/pitfalls.md#distro-name)." -ForegroundColor Yellow
        throw "Ubuntu rootfs download failed from all mirrors; see messages above."
    }

    # Import directly under the canonical name.
    $installDir = "C:\WSL\$DistroName"
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    wsl --import $DistroName $installDir $tarball --version 2
    if ($LASTEXITCODE -ne 0) { throw "WSL import failed" }
}

# --- Final verify under the canonical name -----------------------------------
# (Re-check the rename happened; if wsl --install left a stray Ubuntu-22.04
# alongside a now-existing Ubuntu2204, that's fine -- the canonical name wins.)
if (-not ((Get-WslDistros) -match $DistroName)) {
    throw "WSL provisioning finished but distro '$DistroName' is still not registered. Inspect 'wsl --list'."
}
# Escape $ so WSL evaluates the command substitution (not PowerShell).
wsl -d $DistroName -- bash -c 'echo "WSL OK: $(whoami)@$(hostname) | $(grep VERSION= /etc/os-release)"'
Write-Host "WSL $DistroName ready." -ForegroundColor Green
Write-Host "NOTE: If this is a fresh WSL install, a system REBOOT may be required before WSL works." -ForegroundColor Yellow
exit 0
