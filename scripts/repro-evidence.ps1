<#
.SYNOPSIS
Evidence-pack helpers for reproduce.ps1 (dot-sourceable, PowerShell 5.1).

.DESCRIPTION
Atomic JSON writes and machine-hardware/artifact fingerprinting used to build
the per-profile evidence pack under outputs/reproduction/<profile>/.
This file defines functions only; it performs no work at dot-source time.
#>
if (-not $script:ReproRoot) { $script:ReproRoot = Split-Path -Parent $PSScriptRoot }

function Save-JsonAtomic {
    param([string] $Path, $Value, [int] $Depth = 12)
    $directory = Split-Path -Parent $Path
    if ($directory) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
    $temp = "$Path.tmp.$PID"
    try {
        $Value | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $temp -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
    }
}

function Get-FileSha256 {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        $bytes = $sha.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $sha.Dispose()
    }
}

function Get-HardwareInfo {
    $info = [ordered]@{}
    $cpu = @()
    try {
        $cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { "$($_.Name) ($($_.NumberOfCores)) cores" } | Where-Object { $_ })
    } catch { }
    $info.cpu = $cpu
    $gpu = @()
    $driver = @()
    try {
        $gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name } | Where-Object { $_ })
        $driver = @(Get-CimInstance Win32_VideoController | ForEach-Object { "$($_.Name) driver $($_.DriverVersion)" } | Where-Object { $_ })
    } catch { }
    $info.gpu = $gpu
    $info.gpu_driver = $driver
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $info.windows = "$($os.Caption) $($os.Version) build $($os.BuildNumber)"
    } catch {
        $info.windows = "unknown"
    }
    $wsl = ""
    if (Get-Command wsl -ErrorAction SilentlyContinue) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $wslVersion = wsl -l -v 2>$null
            if ($LASTEXITCODE -eq 0) { $wsl = ((@($wslVersion) -join "`n") -replace "`0", "").Trim() }
        } catch { }
        finally { $ErrorActionPreference = $previousErrorActionPreference }
    }
    $info.wsl = $wsl
    return $info
}

function Write-ArtifactHashes {
    param([string] $EvidenceDir, $Profile, [string] $PipelineCheckout, [string] $EnvFile)
    $hashes = [ordered]@{}
    $hashes.profile_file = Get-FileSha256 $Profile.ProfilePath
    $hashes.upstream_lock = Get-FileSha256 (Join-Path $script:ReproRoot "upstream-lock.json")
    $hashes.prediction_manifest = Get-FileSha256 $Profile.ManifestAbs
    $hashes.windows_scoring_config = Get-FileSha256 $Profile.ConfigWindowsAbs
    $hashes.wsl_cdm_config = Get-FileSha256 $Profile.ConfigWslAbs
    $hashes.pipeline_checkout_commit = $null
    if (Test-Path -LiteralPath (Join-Path $PipelineCheckout ".git")) {
        $commit = (& git -C $PipelineCheckout rev-parse HEAD 2>$null).Trim()
        if ($LASTEXITCODE -eq 0) { $hashes.pipeline_checkout_commit = $commit }
    }
    $hashes.vlm_model = $null
    $hashes.vlm_mmproj = $null
    $hashes.layout_model = $null
    $hashes.server_exe = $null
    if (Test-Path -LiteralPath $EnvFile -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $EnvFile) {
            $t = $line.Trim()
            if ($t -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
                $val = $matches[2].Trim()
                if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and $val[0] -in @("'", '"')) {
                    $val = $val.Substring(1, $val.Length - 2)
                }
                if ($matches[1] -eq "PADDLEOCR_VL_GGUF") { $hashes.vlm_model = Get-FileSha256 $val }
                elseif ($matches[1] -eq "PADDLEOCR_VL_MMPROJ") { $hashes.vlm_mmproj = Get-FileSha256 $val }
                elseif ($matches[1] -eq "LLAMA_SERVER_EXE") { $hashes.server_exe = Get-FileSha256 $val }
            }
        }
    }
    Save-JsonAtomic -Path (Join-Path $EvidenceDir "artifact-hashes.json") -Value $hashes
    return $hashes
}
