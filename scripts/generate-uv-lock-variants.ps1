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
$replacementArtifacts = @()

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
    $replacements = @()
    foreach ($spec in $replacementSpecs) {
        $destination = Join-Path $catalogDestination $spec.name
        $staged = Join-Path $catalogDestination ("." + $spec.name + ".omnidocbench-stage-" + $replacementId)
        $backup = Join-Path $catalogDestination ("." + $spec.name + ".omnidocbench-backup-" + $replacementId)
        Copy-Item -LiteralPath $spec.source -Destination $staged
        $replacementArtifacts += $staged
        $replacementArtifacts += $backup
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
        }
    }

    try {
        foreach ($item in $replacements) {
            if ($item.existed) { Copy-Item -LiteralPath $item.destination -Destination $item.backup }
            Move-Item -LiteralPath $item.staged -Destination $item.destination -Force
        }
    } catch {
        for ($i = $replacements.Count - 1; $i -ge 0; $i--) {
            $item = $replacements[$i]
            if ($item.existed -and (Test-Path -LiteralPath $item.backup)) {
                Copy-Item -LiteralPath $item.backup -Destination $item.destination -Force
            } elseif (-not $item.existed -and (Test-Path -LiteralPath $item.destination)) {
                Remove-Item -LiteralPath $item.destination -Force
            }
        }
        throw
    }

    Write-Host "Generated and verified uv lock catalog in $catalogDestination"
} finally {
    foreach ($artifact in $replacementArtifacts) {
        if (Test-Path -LiteralPath $artifact) {
            Remove-Item -LiteralPath $artifact -Force
        }
    }
    foreach ($name in $controlledUvEnvironment) {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        if ($savedUvEnvironment[$name].present) {
            Set-Item -LiteralPath "Env:$name" -Value $savedUvEnvironment[$name].value
        }
    }
    Remove-OwnedTemporaryDirectory -Path $tempRoot
    $finalCanonicalLockHash = (Get-FileHash -LiteralPath $canonicalLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($finalCanonicalLockHash -cne $canonicalLockHash) {
        throw "canonical uv.lock changed during lock variant generation"
    }
}
