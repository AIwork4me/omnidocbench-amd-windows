$script:UvSourceSpecs = @(
    [ordered]@{
        id = "pypi"
        path = "uv.lock"
        index_url = "https://pypi.org/simple"
        artifact_url_prefix = "https://files.pythonhosted.org/packages/"
        priority = 0
    },
    [ordered]@{
        id = "tuna"
        path = "locks/uv.tuna.lock"
        index_url = "https://pypi.tuna.tsinghua.edu.cn/simple"
        artifact_url_prefix = "https://pypi.tuna.tsinghua.edu.cn/packages/"
        priority = 1
    },
    [ordered]@{
        id = "aliyun"
        path = "locks/uv.aliyun.lock"
        index_url = "https://mirrors.aliyun.com/pypi/simple"
        artifact_url_prefix = "https://mirrors.aliyun.com/pypi/packages/"
        priority = 2
    }
)

$script:UvControlledEnvironmentVariables = @(
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

if (-not ("OmniDocBenchUvNativeEnvironment" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class OmniDocBenchUvNativeEnvironment
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetEnvironmentVariable(string name, string value);
}
"@ -ErrorAction Stop | Out-Null
}

function Assert-ExactJsonKeys {
    param($Object, [string[]] $Expected, [string] $Label)

    if ($null -eq $Object) {
        throw "$Label must be a JSON object"
    }
    $actual = @($Object.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) {
        throw "$Label keys must be exactly [$($Expected -join ', ')]; got [$($actual -join ', ')]"
    }
}

function Assert-LowercaseSha256 {
    param($Value, [string] $Label)

    if ($Value -isnot [string] -or $Value -cnotmatch '\A[0-9a-f]{64}\z') {
        throw "$Label must be a lowercase SHA-256 hash"
    }
}

function Read-StrictJsonFile {
    param([string] $Path, [string] $Label)

    try {
        $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
        $value = $text | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "cannot read $Label at ${Path}: $($_.Exception.Message)"
    }
    if ($null -eq $value -or $value -is [Array] -or $value -is [string] -or $value.GetType().IsPrimitive) {
        throw "$Label must be a JSON object"
    }
    return $value
}

function Read-UvLockManifest {
    param([string] $Path, [string] $RepoRoot)

    $resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
    $manifest = Read-StrictJsonFile -Path $Path -Label "uv lock manifest"
    Assert-ExactJsonKeys $manifest @("schema_version", "normalized_graph_sha256", "locks") "uv lock manifest"
    if ($manifest.schema_version -isnot [int] -or $manifest.schema_version -ne 1) {
        throw "uv lock manifest schema_version must be the integer 1"
    }
    Assert-LowercaseSha256 $manifest.normalized_graph_sha256 "uv lock manifest normalized_graph_sha256"
    Assert-ExactJsonKeys $manifest.locks @("pypi", "tuna", "aliyun") "uv lock manifest locks"

    $lockIds = @($manifest.locks.PSObject.Properties.Name)
    $expectedIds = @($script:UvSourceSpecs | ForEach-Object { $_.id })
    if (($lockIds -join "`n") -cne ($expectedIds -join "`n")) {
        throw "uv lock manifest source IDs must be exactly pypi, tuna, aliyun in priority order"
    }

    $records = @()
    foreach ($spec in $script:UvSourceSpecs) {
        $lock = $manifest.locks.($spec.id)
        Assert-ExactJsonKeys $lock @("path", "index_url", "artifact_url_prefix", "sha256") "uv lock manifest record $($spec.id)"
        if ($lock.path -isnot [string] -or $lock.path -cne $spec.path) {
            throw "uv lock manifest path differs for $($spec.id)"
        }
        if ($lock.index_url -isnot [string] -or $lock.index_url -cne $spec.index_url) {
            throw "uv lock manifest index_url differs for $($spec.id)"
        }
        if ($lock.artifact_url_prefix -isnot [string] -or $lock.artifact_url_prefix -cne $spec.artifact_url_prefix) {
            throw "uv lock manifest artifact_url_prefix differs for $($spec.id)"
        }
        Assert-LowercaseSha256 $lock.sha256 "uv lock manifest sha256 for $($spec.id)"

        $lockPath = Join-Path $resolvedRoot $spec.path
        if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
            throw "uv lock variant is missing for $($spec.id): $lockPath"
        }
        $actualHash = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
        if ($actualHash -cne $lock.sha256) {
            throw "uv lock variant sha256 differs for $($spec.id)"
        }
        $records += [pscustomobject][ordered]@{
            source_id = $spec.id
            path = $spec.path
            index_url = $spec.index_url
            artifact_url_prefix = $spec.artifact_url_prefix
            sha256 = $lock.sha256
        }
    }
    return $records
}

function Read-UvMirrorCandidates {
    param([string] $Path)

    $document = Read-StrictJsonFile -Path $Path -Label "mirrors contract"
    Assert-ExactJsonKeys $document @("schema_version", "network_status", "uv_indexes") "mirrors contract"
    if ($document.schema_version -isnot [int] -or $document.schema_version -ne 1) {
        throw "mirrors contract schema_version must be the integer 1"
    }
    if ($document.network_status -isnot [string] -or @("ok", "degraded", "offline") -cnotcontains $document.network_status) {
        throw "mirrors contract network_status must be exactly ok, degraded, or offline"
    }
    if ($document.uv_indexes -isnot [Array] -or $document.uv_indexes.Count -ne 3) {
        throw "mirrors contract uv_indexes must contain exactly three candidates"
    }

    $reachable = @()
    for ($index = 0; $index -lt $script:UvSourceSpecs.Count; $index += 1) {
        $candidate = $document.uv_indexes[$index]
        $spec = $script:UvSourceSpecs[$index]
        Assert-ExactJsonKeys $candidate @("id", "url", "priority", "reachable") "mirrors candidate $index"
        if ($candidate.id -isnot [string] -or $candidate.id -cne $spec.id) {
            throw "mirrors candidate IDs must be exactly pypi, tuna, aliyun in priority order"
        }
        if ($candidate.url -isnot [string] -or $candidate.url -cne $spec.index_url) {
            throw "mirrors candidate URL differs for $($spec.id)"
        }
        if (-not $candidate.url.StartsWith("https://", [StringComparison]::Ordinal)) {
            throw "mirrors candidate URL must use HTTPS for $($spec.id)"
        }
        if ($candidate.priority -isnot [int] -or $candidate.priority -ne $spec.priority) {
            throw "mirrors candidate priority differs for $($spec.id)"
        }
        if ($candidate.reachable -isnot [bool]) {
            throw "mirrors candidate reachable must be boolean for $($spec.id)"
        }
        if ($candidate.reachable) {
            $reachable += [pscustomobject][ordered]@{
                id = $candidate.id
                url = $candidate.url
                priority = $candidate.priority
                reachable = $candidate.reachable
            }
        }
    }
    return $reachable
}

function Get-UvProcessEnvironmentState {
    param([string[]] $Names)

    $environment = [Environment]::GetEnvironmentVariables([EnvironmentVariableTarget]::Process)
    $saved = [ordered]@{}
    foreach ($name in $Names) {
        $isPresent = $environment.Contains($name)
        $saved[$name] = [ordered]@{
            present = $isPresent
            value = $(if ($isPresent) { [string]$environment[$name] } else { $null })
        }
    }
    return $saved
}

function Restore-UvProcessEnvironmentVariable {
    param([string] $Name, [bool] $Present, [AllowNull()][string] $Value)

    if (-not $Present) {
        [Environment]::SetEnvironmentVariable($Name, $null, [EnvironmentVariableTarget]::Process)
        return
    }
    if (-not [OmniDocBenchUvNativeEnvironment]::SetEnvironmentVariable($Name, $Value)) {
        $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "failed to restore process environment variable $Name (Win32 error $code)"
    }
}

function Remove-ValidatedUvTempProject {
    param([string] $Path)

    try {
        $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    } catch {
        throw "uv temp project cleanup failed because the path cannot be resolved: $Path"
    }
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\")
    $resolvedFull = [IO.Path]::GetFullPath($resolved).TrimEnd("\")
    $parent = [IO.Path]::GetDirectoryName($resolvedFull).TrimEnd("\")
    $leaf = [IO.Path]::GetFileName($resolvedFull)
    $item = Get-Item -LiteralPath $resolved -Force -ErrorAction Stop
    $isReparsePoint = (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    if (-not [string]::Equals($parent, $tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not $leaf.StartsWith("omnidocbench-uv-", [StringComparison]::Ordinal) -or
        $isReparsePoint) {
        throw "refusing to delete unvalidated uv temp project: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
}

function Get-UvRepositoryStatus {
    param([string] $RepoRoot)

    $status = @(& git -C $RepoRoot status --porcelain=v1 --untracked-files=all 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "cannot inspect repository status: $($status -join [Environment]::NewLine)"
    }
    return @($status | ForEach-Object { [string]$_ })
}

function Assert-UvSyncRepositoryUnchanged {
    param([string] $RepoRoot, [string] $ExpectedLockSha256, [string[]] $ExpectedGitStatus)

    $actualLock = (Get-FileHash -LiteralPath (Join-Path $RepoRoot "uv.lock") -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    $actualStatus = @(Get-UvRepositoryStatus -RepoRoot $RepoRoot)
    if ($actualLock -cne $ExpectedLockSha256) {
        throw "canonical uv.lock changed during uv sync"
    }
    if (($actualStatus -join "`n") -cne ($ExpectedGitStatus -join "`n")) {
        throw "repository status changed during uv sync"
    }
}

function Test-ExactIntegerPipelineResult {
    param([object[]] $Output, [string] $Label)

    if ($Output.Count -ne 1 -or $Output[0] -isnot [int]) {
        throw "$Label must return exactly one integer on the pipeline"
    }
    return [int]$Output[0]
}

function Write-UvSyncEvidence {
    param([string] $EvidencePath, $Record)

    $tempEvidence = "$EvidencePath.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    try {
        $json = $Record | ConvertTo-Json -Depth 8
        $utf8NoBom = New-Object Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($tempEvidence, $json, $utf8NoBom)
        [void](Get-Content -Raw -Encoding UTF8 -LiteralPath $tempEvidence | ConvertFrom-Json -ErrorAction Stop)
        Move-Item -LiteralPath $tempEvidence -Destination $EvidencePath -Force -ErrorAction Stop
    } finally {
        if (Test-Path -LiteralPath $tempEvidence) {
            Remove-Item -LiteralPath $tempEvidence -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-UvCatalogSync {
    param(
        [string] $RepoRoot,
        [string] $ManifestPath,
        [string] $MirrorsPath,
        [string] $VenvPath,
        [string] $EvidencePath,
        [scriptblock] $UvRunner,
        [scriptblock] $VerifierRunner
    )

    $resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
    $manifestRecords = @(Read-UvLockManifest -Path $ManifestPath -RepoRoot $resolvedRoot)
    $candidates = @(Read-UvMirrorCandidates -Path $MirrorsPath)
    $manifestDocument = Read-StrictJsonFile -Path $ManifestPath -Label "uv lock manifest"

    $manifestById = @{}
    foreach ($record in $manifestRecords) {
        $manifestById[$record.source_id] = $record
    }
    foreach ($candidate in $candidates) {
        if (-not $manifestById.ContainsKey($candidate.id)) {
            throw "reachable mirror candidate has no fixed lock record: $($candidate.id)"
        }
        if ($candidate.url -cne $manifestById[$candidate.id].index_url) {
            throw "reachable mirror candidate URL does not match its lock record: $($candidate.id)"
        }
    }

    $pyprojectPath = Join-Path $resolvedRoot "pyproject.toml"
    if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf)) {
        throw "pyproject.toml is missing: $pyprojectPath"
    }
    $canonicalLockPath = Join-Path $resolvedRoot "uv.lock"
    $baselineRootLockSha256 = (Get-FileHash -LiteralPath $canonicalLockPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    $baselineGitStatus = @(Get-UvRepositoryStatus -RepoRoot $resolvedRoot)
    $pyprojectSha256 = (Get-FileHash -LiteralPath $pyprojectPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    $absoluteVenvPath = [IO.Path]::GetFullPath($VenvPath)
    $failedCandidates = @()

    foreach ($candidate in $candidates) {
        $lockRecord = $manifestById[$candidate.id]
        $selectedLockPath = Join-Path $resolvedRoot $lockRecord.path
        $selectedLockSha256 = (Get-FileHash -LiteralPath $selectedLockPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
        if ($selectedLockSha256 -cne $lockRecord.sha256) {
            throw "uv lock variant sha256 changed before sync for $($candidate.id)"
        }

        $saved = Get-UvProcessEnvironmentState -Names $script:UvControlledEnvironmentVariables
        $project = Join-Path ([IO.Path]::GetFullPath([IO.Path]::GetTempPath())) ("omnidocbench-uv-" + [guid]::NewGuid().ToString("N"))
        $projectCreated = $false
        $runnerException = $null
        $cleanupException = $null
        $immutabilityException = $null
        $exitCode = -1
        $errorText = $null

        try {
            [void][IO.Directory]::CreateDirectory($project)
            $projectCreated = $true
            Copy-Item -LiteralPath $pyprojectPath -Destination (Join-Path $project "pyproject.toml") -Force -ErrorAction Stop
            Copy-Item -LiteralPath $selectedLockPath -Destination (Join-Path $project "uv.lock") -Force -ErrorAction Stop

            foreach ($name in $script:UvControlledEnvironmentVariables) {
                Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
            }
            $env:UV_PROJECT_ENVIRONMENT = $absoluteVenvPath
            $arguments = @(
                "sync", "--locked", "--all-groups", "--no-config", "--project", $project,
                "--default-index", $candidate.url, "--index-strategy", "first-index"
            )
            $runnerOutput = @(& $UvRunner $arguments)
            $exitCode = Test-ExactIntegerPipelineResult -Output $runnerOutput -Label "UvRunner"
        } catch {
            $runnerException = $_
        } finally {
            $cleanupErrors = New-Object Collections.Generic.List[string]
            foreach ($name in $script:UvControlledEnvironmentVariables) {
                try {
                    $state = $saved[$name]
                    Restore-UvProcessEnvironmentVariable -Name $name -Present ([bool]$state.present) -Value $state.value
                } catch {
                    $cleanupErrors.Add("environment ${name}: $($_.Exception.Message)")
                }
            }
            if ($projectCreated) {
                try {
                    Remove-ValidatedUvTempProject -Path $project
                } catch {
                    $cleanupErrors.Add("temp project: $($_.Exception.Message)")
                }
            }
            if ($cleanupErrors.Count -gt 0) {
                $cleanupException = New-Object Exception ("uv sync cleanup failed: " + ($cleanupErrors -join "; "))
            }
        }

        try {
            Assert-UvSyncRepositoryUnchanged -RepoRoot $resolvedRoot `
                -ExpectedLockSha256 $baselineRootLockSha256 -ExpectedGitStatus $baselineGitStatus
        } catch {
            $immutabilityException = $_
        }
        if ($null -ne $immutabilityException) {
            throw $immutabilityException
        }
        if ($null -ne $cleanupException) {
            throw $cleanupException
        }
        if ($null -ne $runnerException) {
            $exitCode = -1
            $errorText = $runnerException.Exception.Message
        } elseif ($exitCode -ne 0) {
            $errorText = "uv sync exited with code $exitCode"
        }

        if ($exitCode -ne 0) {
            $failedCandidates += [pscustomobject][ordered]@{
                source_id = $candidate.id
                index_url = $candidate.url
                lock_path = $lockRecord.path
                lock_sha256 = $lockRecord.sha256
                exit_code = $exitCode
                error = $errorText
            }
            continue
        }

        $verifierException = $null
        $verifierImmutabilityException = $null
        $verifierExitCode = -1
        try {
            $verifierOutput = @(& $VerifierRunner $resolvedRoot $ManifestPath)
            $verifierExitCode = Test-ExactIntegerPipelineResult -Output $verifierOutput -Label "VerifierRunner"
        } catch {
            $verifierException = $_
        }
        try {
            Assert-UvSyncRepositoryUnchanged -RepoRoot $resolvedRoot `
                -ExpectedLockSha256 $baselineRootLockSha256 -ExpectedGitStatus $baselineGitStatus
        } catch {
            $verifierImmutabilityException = $_
        }
        if ($null -ne $verifierImmutabilityException) {
            throw $verifierImmutabilityException
        }
        if ($null -ne $verifierException) {
            throw $verifierException
        }
        if ($verifierExitCode -ne 0) {
            throw "uv lock verifier exited with code $verifierExitCode"
        }

        $evidenceRecord = [pscustomobject][ordered]@{
            schema_version = 1
            selected_source_id = $candidate.id
            selected_index_url = $candidate.url
            selected_lock_path = $lockRecord.path
            selected_lock_sha256 = $lockRecord.sha256
            normalized_graph_sha256 = $manifestDocument.normalized_graph_sha256
            pyproject_sha256 = $pyprojectSha256
            uv_version = "uv 0.11.16"
            completed_at = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffffffZ", [Globalization.CultureInfo]::InvariantCulture)
            failed_candidates = @($failedCandidates)
        }
        Write-UvSyncEvidence -EvidencePath $EvidencePath -Record $evidenceRecord
        return $evidenceRecord
    }

    Assert-UvSyncRepositoryUnchanged -RepoRoot $resolvedRoot `
        -ExpectedLockSha256 $baselineRootLockSha256 -ExpectedGitStatus $baselineGitStatus
    $attemptSummary = if ($failedCandidates.Count -eq 0) {
        "no reachable candidates"
    } else {
        ($failedCandidates | ForEach-Object { "$($_.source_id)=$($_.exit_code)" }) -join ", "
    }
    throw "uv sync failed for all reachable sources: $attemptSummary"
}
