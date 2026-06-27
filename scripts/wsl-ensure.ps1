<#
.SYNOPSIS
Ensures WSL Ubuntu 22.04 is installed. Handles the China-network case
where wsl --install fails (Store blocked) by importing a rootfs from USTC.
#>
$ErrorActionPreference = "Stop"

# wsl --list writes UTF-16LE text with embedded NUL bytes; PowerShell 5.1
# captures those NULs, which breaks -match on the distro name. Strip them.
function Get-WslDistros {
    $cleaned = (wsl --list --quiet 2>$null) | ForEach-Object { ($_ -replace "`0","").Trim() } | Where-Object { $_ }
    return ($cleaned -join "`n")
}

# Check if WSL distro already exists
$distros = Get-WslDistros
if ($distros -match "Ubuntu2204") {
    Write-Host "WSL Ubuntu2204 already installed." -ForegroundColor Green
    wsl -d Ubuntu2204 -- echo "WSL OK: $(whoami)@$(hostname)"
    exit 0
}

# Try standard install first
Write-Host "Attempting wsl --install..." -ForegroundColor Cyan
wsl --install -d Ubuntu-22.04 --no-launch 2>$null
if ($LASTEXITCODE -eq 0 -and ((Get-WslDistros) -match "Ubuntu")) {
    Write-Host "WSL installed via wsl --install." -ForegroundColor Green
    exit 0
}

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

# Download rootfs
$tarball = "$env:TEMP\ubuntu-22.04.tar.gz"
Write-Host "Downloading Ubuntu rootfs from $rootfsUrl ..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $rootfsUrl -OutFile $tarball -TimeoutSec 300

# Import
$installDir = "C:\WSL\Ubuntu2204"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
wsl --import Ubuntu2204 $installDir $tarball --version 2
if ($LASTEXITCODE -ne 0) { throw "WSL import failed" }

# Verify
wsl -d Ubuntu2204 -- echo "WSL OK: $(cat /etc/os-release | grep VERSION=)"
Write-Host "WSL Ubuntu2204 imported successfully." -ForegroundColor Green
Write-Host "NOTE: If this is a fresh WSL install, a system REBOOT may be required before WSL works." -ForegroundColor Yellow
exit 0
