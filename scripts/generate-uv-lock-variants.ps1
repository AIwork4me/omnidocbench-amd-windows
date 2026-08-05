[CmdletBinding()]
param(
    [string] $RepoRoot = "",
    [string] $UvExecutable = "uv",
    [string] $PythonExecutable = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

function Resolve-RequiredExecutable {
    param(
        [Parameter(Mandatory = $true)] [string] $Value,
        [Parameter(Mandatory = $true)] [string] $Description
    )

    if (Test-Path -LiteralPath $Value -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Value).Path
    }
    $command = Get-Command $Value -CommandType Application, ExternalScript -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        throw "$Description cannot be resolved: $Value"
    }
    if (-not [string]::IsNullOrEmpty($command.Source)) {
        return $command.Source
    }
    return $command.Path
}

function Remove-OwnedTemporaryDirectory {
    param([Parameter(Mandatory = $true)] [string] $Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $resolvedPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
    $temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $temporaryPrefix = $temporaryBase
    if (-not $temporaryPrefix.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $temporaryPrefix += [System.IO.Path]::DirectorySeparatorChar
    }
    $leaf = [System.IO.Path]::GetFileName($resolvedPath)
    if (
        -not $resolvedPath.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not $leaf.StartsWith("omnidocbench-uv-generate-", [System.StringComparison]::Ordinal)
    ) {
        throw "refusing to clean unowned temporary directory: $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

function Set-PresentEnvironmentVariable {
    param(
        [Parameter(Mandatory = $true)] [string] $Name,
        [AllowEmptyString()] [string] $Value
    )

    if (
        $Value.Length -eq 0 -and
        [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
    ) {
        $nativeType = [System.Management.Automation.PSTypeName] "OmniDocBenchNativeEnvironment"
        if ($null -eq $nativeType.Type) {
            Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;

public static class OmniDocBenchNativeEnvironment
{
    [DllImport("kernel32.dll", EntryPoint = "SetEnvironmentVariableW",
        CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetEnvironmentVariable(string name, string value);
}
'@
        }
        if (-not [OmniDocBenchNativeEnvironment]::SetEnvironmentVariable($Name, [string]::Empty)) {
            throw "failed to restore empty process environment variable: $Name"
        }
        return
    }
    Set-Item -LiteralPath "Env:$Name" -Value $Value
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$canonicalProjectPath = Join-Path $RepoRoot "pyproject.toml"
$canonicalLockPath = Join-Path $RepoRoot "uv.lock"
$verifierPath = Join-Path $RepoRoot "scripts\verify_uv_lock_variants.py"
foreach ($requiredPath in @($canonicalProjectPath, $canonicalLockPath, $verifierPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "required repository file is missing: $requiredPath"
    }
}

if ([string]::IsNullOrEmpty($PythonExecutable)) {
    $PythonExecutable = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}
$UvExecutable = Resolve-RequiredExecutable -Value $UvExecutable -Description "uv executable"
$PythonExecutable = Resolve-RequiredExecutable -Value $PythonExecutable -Description "Python executable"

$canonicalLockHash = (Get-FileHash -LiteralPath $canonicalLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
$controlledUvEnvironment = @(
    "UV_INDEX",
    "UV_DEFAULT_INDEX",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_INDEX_STRATEGY",
    "UV_NO_INDEX",
    "UV_FIND_LINKS",
    "UV_CONFIG_FILE",
    "UV_NO_CONFIG",
    "UV_PROJECT_ENVIRONMENT"
)
$savedUvEnvironment = [ordered]@{}
foreach ($name in $controlledUvEnvironment) {
    $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    $savedUvEnvironment[$name] = [ordered]@{
        present = ($null -ne $item)
        value = $(if ($null -eq $item) { $null } else { [string] $item.Value })
    }
}

$sources = @(
    [ordered]@{ id = "tuna"; url = "https://pypi.tuna.tsinghua.edu.cn/simple"; path = "locks\uv.tuna.lock" },
    [ordered]@{ id = "aliyun"; url = "https://mirrors.aliyun.com/pypi/simple"; path = "locks\uv.aliyun.lock" }
)

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("omnidocbench-uv-generate-" + [guid]::NewGuid().ToString("N"))
$stagedArtifacts = @()
$backupArtifacts = @()
$replacements = @()
$failureMessages = New-Object System.Collections.Generic.List[string]

try {
    foreach ($name in $controlledUvEnvironment) {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }

    New-Item -ItemType Directory -Path $tempRoot | Out-Null

    $canonicalTemp = Join-Path $tempRoot "pypi"
    New-Item -ItemType Directory -Force -Path $canonicalTemp | Out-Null
    Copy-Item -LiteralPath $canonicalProjectPath -Destination (Join-Path $canonicalTemp "pyproject.toml")
    Copy-Item -LiteralPath $canonicalLockPath -Destination (Join-Path $canonicalTemp "uv.lock")
    & $UvExecutable lock --check --no-config --project $canonicalTemp `
        --default-index "https://pypi.org/simple"
    if ($LASTEXITCODE -ne 0) { throw "canonical PyPI lock check failed: $LASTEXITCODE" }

    foreach ($source in $sources) {
        $project = Join-Path $tempRoot $source.id
        New-Item -ItemType Directory -Force -Path $project | Out-Null
        Copy-Item -LiteralPath $canonicalProjectPath -Destination (Join-Path $project "pyproject.toml")
        Copy-Item -LiteralPath $canonicalLockPath -Destination (Join-Path $project "uv.lock")
        & $UvExecutable lock --no-config --project $project --default-index $source.url
        if ($LASTEXITCODE -ne 0) { throw "uv lock failed for $($source.id): $LASTEXITCODE" }
        & $UvExecutable lock --check --no-config --project $project --default-index $source.url
        if ($LASTEXITCODE -ne 0) { throw "uv lock --check failed for $($source.id): $LASTEXITCODE" }
    }

    $catalogStage = Join-Path $tempRoot "catalog-stage"
    $catalogLocks = Join-Path $catalogStage "locks"
    New-Item -ItemType Directory -Force -Path $catalogLocks | Out-Null
    Copy-Item -LiteralPath $canonicalLockPath -Destination (Join-Path $catalogStage "uv.lock")
    Copy-Item -LiteralPath (Join-Path (Join-Path $tempRoot "tuna") "uv.lock") -Destination (Join-Path $catalogLocks "uv.tuna.lock")
    Copy-Item -LiteralPath (Join-Path (Join-Path $tempRoot "aliyun") "uv.lock") -Destination (Join-Path $catalogLocks "uv.aliyun.lock")
    & $PythonExecutable $verifierPath `
        --root $catalogStage --write-manifest (Join-Path $catalogLocks "manifest.json")
    if ($LASTEXITCODE -ne 0) { throw "staged lock manifest generation failed: $LASTEXITCODE" }
    & $PythonExecutable $verifierPath `
        --root $catalogStage --manifest (Join-Path $catalogLocks "manifest.json")
    if ($LASTEXITCODE -ne 0) { throw "staged lock catalog verification failed: $LASTEXITCODE" }

    $catalogDestination = Join-Path $RepoRoot "locks"
    New-Item -ItemType Directory -Force -Path $catalogDestination | Out-Null
    $replacementId = [guid]::NewGuid().ToString("N")
    $replacementSpecs = @(
        [ordered]@{ name = "uv.tuna.lock"; source = (Join-Path $catalogLocks "uv.tuna.lock") },
        [ordered]@{ name = "uv.aliyun.lock"; source = (Join-Path $catalogLocks "uv.aliyun.lock") },
        [ordered]@{ name = "manifest.json"; source = (Join-Path $catalogLocks "manifest.json") }
    )
    foreach ($spec in $replacementSpecs) {
        $destination = Join-Path $catalogDestination $spec.name
        $staged = Join-Path $catalogDestination ("." + $spec.name + ".omnidocbench-stage-" + $replacementId)
        $backup = Join-Path $catalogDestination ("." + $spec.name + ".omnidocbench-backup-" + $replacementId)
        Copy-Item -LiteralPath $spec.source -Destination $staged
        $stagedArtifacts += $staged
        $existed = Test-Path -LiteralPath $destination -PathType Leaf
        $originalHash = $null
        if ($existed) {
            $originalHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $replacements += [ordered]@{
            destination = $destination
            staged = $staged
            existed = $existed
            backup = $backup
            sha256 = $originalHash
            replaced = $false
        }
    }

    foreach ($item in $replacements) {
        if ($item.existed) {
            Copy-Item -LiteralPath $item.destination -Destination $item.backup
            $backupArtifacts += $item.backup
        }
    }
    foreach ($item in $replacements) {
        Move-Item -LiteralPath $item.staged -Destination $item.destination -Force
        $item.replaced = $true
    }
} catch {
    [void] $failureMessages.Add("main operation: $($_.Exception.Message)")
}

# Staged files are no longer needed after replacement. A cleanup failure is
# recorded, but cannot prevent environment restoration or later invariants.
foreach ($artifact in $stagedArtifacts) {
    try {
        if (Test-Path -LiteralPath $artifact) {
            Remove-Item -LiteralPath $artifact -Force
        }
    } catch {
        [void] $failureMessages.Add("staged replacement cleanup: $($_.Exception.Message)")
    }
}

# Restore every controlled variable independently. Windows PowerShell's Env:
# provider deletes empty values, so the native API preserves present-with-empty.
foreach ($name in $controlledUvEnvironment) {
    try {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        if ($savedUvEnvironment[$name].present) {
            Set-PresentEnvironmentVariable -Name $name -Value $savedUvEnvironment[$name].value
        }
    } catch {
        [void] $failureMessages.Add("environment restore for ${name}: $($_.Exception.Message)")
    }
}

# Temp cleanup and root immutability are separate finalizers: both always run.
try {
    Remove-OwnedTemporaryDirectory -Path $tempRoot
} catch {
    [void] $failureMessages.Add("temporary directory cleanup: $($_.Exception.Message)")
}

try {
    $finalCanonicalLockHash = (Get-FileHash -LiteralPath $canonicalLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($finalCanonicalLockHash -cne $canonicalLockHash) {
        throw "canonical uv.lock changed during lock variant generation"
    }
} catch {
    [void] $failureMessages.Add("root lock immutability: $($_.Exception.Message)")
}

# The catalog is not committed until every pre-commit postcondition above has
# passed. Before this point, every failure uses the complete backup set.
if ($failureMessages.Count -ne 0) {
    # Roll back every target independently and report every rollback failure.
    $rollbackFailed = $false
    for ($i = $replacements.Count - 1; $i -ge 0; $i--) {
        $item = $replacements[$i]
        try {
            if ($item.existed) {
                if (Test-Path -LiteralPath $item.backup -PathType Leaf) {
                    Copy-Item -LiteralPath $item.backup -Destination $item.destination -Force
                    $restoredHash = (Get-FileHash -LiteralPath $item.destination -Algorithm SHA256).Hash.ToLowerInvariant()
                    if ($restoredHash -cne $item.sha256) {
                        throw "restored catalog hash differs: $($item.destination)"
                    }
                } elseif ($item.replaced) {
                    throw "rollback backup is missing: $($item.backup)"
                }
            } elseif (Test-Path -LiteralPath $item.destination) {
                Remove-Item -LiteralPath $item.destination -Force
            }
        } catch {
            $rollbackFailed = $true
            [void] $failureMessages.Add("catalog rollback for $($item.destination): $($_.Exception.Message)")
        }
    }

    # Staged artifacts are never recovery material and are always best-effort.
    foreach ($artifact in $stagedArtifacts) {
        try {
            if (Test-Path -LiteralPath $artifact) {
                Remove-Item -LiteralPath $artifact -Force
            }
        } catch {
            [void] $failureMessages.Add("post-rollback artifact cleanup for ${artifact}: $($_.Exception.Message)")
        }
    }

    if ($rollbackFailed) {
        $preserved = @(
            $backupArtifacts | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
        )
        if ($preserved.Count -ne 0) {
            [void] $failureMessages.Add("recovery backups preserved after rollback failure: $($preserved -join ', ')")
        }
    } else {
        # Once rollback is complete, backups are redundant. Cleanup remains
        # best-effort and each path is attempted once.
        foreach ($artifact in $backupArtifacts) {
            try {
                if (Test-Path -LiteralPath $artifact) {
                    Remove-Item -LiteralPath $artifact -Force
                }
            } catch {
                [void] $failureMessages.Add("post-rollback backup cleanup for ${artifact}: $($_.Exception.Message)")
            }
        }
    }

    throw ("uv lock catalog generation failed:`n - " + ($failureMessages -join "`n - "))
}

# Commit point: replacements, environment restoration, temporary cleanup, and
# root immutability have all succeeded. Backup disposal can no longer trigger
# rollback, because partial disposal makes rollback ambiguous. Cleanup errors
# remain explicit and failed backup paths are preserved for manual recovery.
$postCommitCleanupMessages = New-Object System.Collections.Generic.List[string]
$preservedPostCommitBackups = @()
foreach ($artifact in $backupArtifacts) {
    try {
        if (Test-Path -LiteralPath $artifact) {
            Remove-Item -LiteralPath $artifact -Force
        }
    } catch {
        $preservedPostCommitBackups += $artifact
        [void] $postCommitCleanupMessages.Add("backup cleanup for ${artifact}: $($_.Exception.Message)")
    }
}

if ($postCommitCleanupMessages.Count -ne 0) {
    $preserved = @(
        $preservedPostCommitBackups | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    )
    if ($preserved.Count -ne 0) {
        [void] $postCommitCleanupMessages.Add("recovery backups preserved: $($preserved -join ', ')")
    }
    throw ("uv lock catalog committed but post-commit cleanup failed:`n - " + ($postCommitCleanupMessages -join "`n - "))
}

Write-Host "Generated and verified uv lock catalog in $catalogDestination"
