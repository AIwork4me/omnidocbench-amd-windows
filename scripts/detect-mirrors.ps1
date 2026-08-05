<#
.SYNOPSIS
Detects available mirrors for OmniDocBench setup (mirror-aware).
Outputs mirrors.env for legacy consumers and ordered mirrors.json uv candidates.
#>
$ErrorActionPreference = "Stop"
# NOTE: Join-Path is nested (rather than the PS 7+ 3-arg form) so this runs on
# Windows PowerShell 5.1 as well as PowerShell 7+.
$rootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = Join-Path $rootDir "mirrors.env"
$resolvedJsonFile = Join-Path $rootDir "mirrors.json"

function Test-ProcessEnvironmentVariable($name) {
    $processEnvironment = [Environment]::GetEnvironmentVariables(
        [EnvironmentVariableTarget]::Process
    )
    return $processEnvironment.Contains($name)
}

$expectedProbeUrls = @(
    "https://huggingface.co/api/datasets/opendatalab/OmniDocBench",
    "https://modelscope.cn/api/v1/datasets/OpenDataLab/OmniDocBench",
    "https://github.com/opendatalab/OmniDocBench",
    "https://ghproxy.net/https://github.com",
    "https://ghfast.top/https://github.com",
    "https://mirrors.ustc.edu.cn/CTAN/systems/texlive/tlnet",
    "https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet",
    "https://mirror.ctan.org/systems/texlive/tlnet",
    "https://pypi.org/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple"
)

$hasTestHooks = Test-ProcessEnvironmentVariable "REPRO_TEST_HOOKS"
$hasProbeFixture = Test-ProcessEnvironmentVariable "MIRROR_PROBE_RESULTS_JSON"
$hasPublishFailure = Test-ProcessEnvironmentVariable "MIRROR_PUBLISH_FAIL_BEFORE"
if ($hasTestHooks -ne $hasProbeFixture) {
    Write-Host "ERROR: fixture injection requires both REPRO_TEST_HOOKS and MIRROR_PROBE_RESULTS_JSON." -ForegroundColor Red
    exit 1
}
if ($hasPublishFailure -and -not ($hasTestHooks -and $hasProbeFixture)) {
    Write-Host "ERROR: MIRROR_PUBLISH_FAIL_BEFORE requires REPRO_TEST_HOOKS and MIRROR_PROBE_RESULTS_JSON." -ForegroundColor Red
    exit 1
}

$script:ProbeResults = $null
$script:PublishFailBefore = $null
if ($hasTestHooks -and $hasProbeFixture) {
    try {
        $fixtureText = Get-Content -LiteralPath $env:MIRROR_PROBE_RESULTS_JSON -Raw -Encoding UTF8
        $script:ProbeResults = $fixtureText | ConvertFrom-Json -ErrorAction Stop
        if ($null -eq $script:ProbeResults) {
            throw "fixture root must be a JSON object"
        }

        $actualProbeUrls = @(
            $script:ProbeResults.PSObject.Properties | ForEach-Object { $_.Name }
        )
        foreach ($expectedUrl in $expectedProbeUrls) {
            if ($actualProbeUrls -cnotcontains $expectedUrl) {
                throw "fixture is missing exact canonical URL key: $expectedUrl"
            }
        }
        foreach ($actualUrl in $actualProbeUrls) {
            if ($expectedProbeUrls -cnotcontains $actualUrl) {
                throw "fixture contains unexpected or case-variant URL key: $actualUrl"
            }
        }
        if ($actualProbeUrls.Count -ne $expectedProbeUrls.Count) {
            throw "fixture URL key count must be exactly $($expectedProbeUrls.Count)"
        }
        foreach ($expectedUrl in $expectedProbeUrls) {
            $exactProperty = @(
                $script:ProbeResults.PSObject.Properties |
                    Where-Object { $_.Name -ceq $expectedUrl }
            )[0]
            if ($exactProperty.Value -isnot [bool]) {
                throw "fixture value must be System.Boolean for: $expectedUrl"
            }
        }
    } catch {
        Write-Host "ERROR: MIRROR_PROBE_RESULTS_JSON is malformed or unreadable: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }

    if ($hasPublishFailure) {
        $publishFailureValue = [Environment]::GetEnvironmentVariable(
            "MIRROR_PUBLISH_FAIL_BEFORE",
            [EnvironmentVariableTarget]::Process
        )
        if (@("mirrors.env", "mirrors.json") -cnotcontains $publishFailureValue) {
            Write-Host "ERROR: MIRROR_PUBLISH_FAIL_BEFORE must be exactly mirrors.env or mirrors.json." -ForegroundColor Red
            exit 1
        }
        $script:PublishFailBefore = $publishFailureValue
    }
}

function Test-Url($url, $timeoutSec = 8) {
    if ($null -ne $script:ProbeResults) {
        $probeProperty = @(
            $script:ProbeResults.PSObject.Properties |
                Where-Object { $_.Name -ceq $url }
        )[0]
        return [bool]$probeProperty.Value
    }
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec $timeoutSec -UseBasicParsing -ErrorAction Stop
        return $r.StatusCode -lt 400
    } catch { return $false }
}

function New-StagedUtf8File($path, $content, $validationKind) {
    $directory = [System.IO.Path]::GetDirectoryName($path)
    $leaf = [System.IO.Path]::GetFileName($path)
    $tempPath = Join-Path $directory ("{0}.tmp.{1}" -f $leaf, [guid]::NewGuid().ToString("N"))
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    try {
        [System.IO.File]::WriteAllText($tempPath, $content, $utf8NoBom)
        $roundTrip = [System.IO.File]::ReadAllText($tempPath, $utf8NoBom)
        if ($validationKind -eq "json") {
            [void]($roundTrip | ConvertFrom-Json -ErrorAction Stop)
        } elseif ($roundTrip -cne $content) {
            throw "staged mirrors.env did not round-trip as UTF-8"
        }
        return $tempPath
    } catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
        throw
    }
}

# Write mirrors.env from whatever $lines we have collected so far. Called both
# on the success path and from partial-failure paths so a degraded network
# still leaves a (partial) mirrors.env on disk -- downstream scripts can then
# distinguish "detect-mirrors never ran" from "ran but some sources were down"
# via the NETWORK_STATUS key, instead of cascading "mirrors.env not found"
# warnings that obscure the real (network) problem.
function Get-MirrorsEnvContent($status) {
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($l in $lines) { $out.Add($l) }
    $out.Add("NETWORK_STATUS=$status")
    return ($out -join [Environment]::NewLine) + [Environment]::NewLine
}

function Get-MirrorsJsonContent($status, $uvIndexes) {
    $document = [ordered]@{
        schema_version = 1
        network_status = $status
        uv_indexes = $uvIndexes
    }
    return ($document | ConvertTo-Json -Depth 5) + [Environment]::NewLine
}

function Invoke-PublishFailureIfRequested($targetName) {
    if ($null -ne $script:PublishFailBefore -and $script:PublishFailBefore -ceq $targetName) {
        throw "Injected mirror contract publish failure before $targetName"
    }
}

function Publish-MirrorsContracts($envContent, $jsonContent) {
    $envStage = $null
    $jsonStage = $null
    $envBackup = $null
    $jsonBackup = $null
    $envExisted = Test-Path -LiteralPath $resolvedEnvFile
    $jsonExisted = Test-Path -LiteralPath $resolvedJsonFile
    $envPublished = $false
    $jsonPublished = $false

    try {
        # Both contracts must be fully staged and validated before either
        # destination is replaced.
        $envStage = New-StagedUtf8File $resolvedEnvFile $envContent "env"
        $jsonStage = New-StagedUtf8File $resolvedJsonFile $jsonContent "json"

        if ($envExisted) {
            $envBackup = Join-Path $rootDir ("mirrors.env.backup.{0}" -f [guid]::NewGuid().ToString("N"))
            Copy-Item -LiteralPath $resolvedEnvFile -Destination $envBackup -Force
        }
        if ($jsonExisted) {
            $jsonBackup = Join-Path $rootDir ("mirrors.json.backup.{0}" -f [guid]::NewGuid().ToString("N"))
            Copy-Item -LiteralPath $resolvedJsonFile -Destination $jsonBackup -Force
        }

        Invoke-PublishFailureIfRequested "mirrors.env"
        Move-Item -LiteralPath $envStage -Destination $resolvedEnvFile -Force
        $envStage = $null
        $envPublished = $true

        Invoke-PublishFailureIfRequested "mirrors.json"
        Move-Item -LiteralPath $jsonStage -Destination $resolvedJsonFile -Force
        $jsonStage = $null
        $jsonPublished = $true
    } catch {
        $publishError = $_
        $rollbackErrors = New-Object System.Collections.Generic.List[string]

        if ($jsonPublished) {
            try {
                if ($jsonExisted) {
                    Move-Item -LiteralPath $jsonBackup -Destination $resolvedJsonFile -Force
                    $jsonBackup = $null
                } elseif (Test-Path -LiteralPath $resolvedJsonFile) {
                    Remove-Item -LiteralPath $resolvedJsonFile -Force
                }
            } catch {
                $rollbackErrors.Add("mirrors.json: $($_.Exception.Message)")
            }
        }
        if ($envPublished) {
            try {
                if ($envExisted) {
                    Move-Item -LiteralPath $envBackup -Destination $resolvedEnvFile -Force
                    $envBackup = $null
                } elseif (Test-Path -LiteralPath $resolvedEnvFile) {
                    Remove-Item -LiteralPath $resolvedEnvFile -Force
                }
            } catch {
                $rollbackErrors.Add("mirrors.env: $($_.Exception.Message)")
            }
        }

        if ($rollbackErrors.Count -gt 0) {
            throw "Mirror contract publish failed: $($publishError.Exception.Message); rollback failed: $($rollbackErrors -join '; ')"
        }
        throw $publishError
    } finally {
        foreach ($workFile in @($envStage, $jsonStage, $envBackup, $jsonBackup)) {
            if ($null -ne $workFile -and (Test-Path -LiteralPath $workFile)) {
                Remove-Item -LiteralPath $workFile -Force
            }
        }
    }
}

function Write-MirrorsContracts($status, $uvIndexes) {
    $envContent = Get-MirrorsEnvContent $status
    $jsonContent = Get-MirrorsJsonContent $status $uvIndexes
    Publish-MirrorsContracts $envContent $jsonContent
    Write-Host "mirrors.env written to $resolvedEnvFile (status: $status)" -ForegroundColor Green
    Write-Host "mirrors.json written to $resolvedJsonFile (status: $status)" -ForegroundColor Green
}

# Use ASCII "--" (not an em-dash) so the comment round-trips cleanly through any
# codepage when WriteAllLines emits it (PS 5.1 default UTF-8); an em-dash here
# showed up as mojibake on a cp936 machine.
$lines = @("# Auto-generated by detect-mirrors.ps1 - do not edit")
$degraded = $false  # set true when any source probe fails but we still write env
$datasetOffline = $false

# HuggingFace vs ModelScope.
# P12: probe the ACTUAL dataset artifact URLs, not the marketing homepages.
# A homepage staying up does NOT imply the dataset CDN / API is reachable
# (HF has had dataset-CDN outages while huggingface.co rendered normally, and
# ModelScope's dataset endpoint is on a different host than modelscope.cn).
$hf = Test-Url "https://huggingface.co/api/datasets/opendatalab/OmniDocBench"
$ms = Test-Url "https://modelscope.cn/api/v1/datasets/OpenDataLab/OmniDocBench"
if ($hf) {
    $lines += "HF_OR_MS=huggingface"
    $lines += "DATASET_URL=https://huggingface.co/datasets/opendatalab/OmniDocBench"
    $lines += "VLM_MODEL_URL=https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF"
    $lines += "LAYOUT_MODEL_URL=https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx"
} elseif ($ms) {
    $lines += "HF_OR_MS=modelscope"
    $lines += "DATASET_URL=modelscope://OpenDataLab/OmniDocBench"
    $lines += "VLM_MODEL_URL=modelscope://PaddlePaddle/PaddleOCR-VL-1.6-GGUF"
    $lines += "LAYOUT_MODEL_URL=modelscope://PaddlePaddle/PP-DocLayoutV3_onnx"
} else {
    # Neither dataset host is reachable. Keep collecting probe results so both
    # output contracts describe the completed run before the existing exit 1.
    Write-Host "ERROR: Neither HuggingFace nor ModelScope dataset endpoint is reachable." -ForegroundColor Red
    Write-Host "       Probed: huggingface.co/api/datasets/opendatalab/OmniDocBench," -ForegroundColor DarkGray
    Write-Host "                modelscope.cn/api/v1/datasets/OpenDataLab/OmniDocBench" -ForegroundColor DarkGray
    $lines += "HF_OR_MS=# UNREACHABLE (HF + ModelScope dataset endpoints both down)"
    $datasetOffline = $true
}

# GitHub vs gitclone/ghproxy.
# P6: write a partial mirrors.env (with the sources that DID probe OK) and
# WARN rather than hard-exit on GitHub failure, so a machine where ModelScope
# works but GitHub doesn't still gets a usable mirrors.env for the non-GitHub
# steps. The downstream OmniDocBench clone (setup.ps1) will fail loudly at its
# own git clone, which is the right place to surface that.
$gh = Test-Url "https://github.com/opendatalab/OmniDocBench"
if ($gh) {
    $lines += "GITHUB_BASE=https://github.com"
    $lines += "GITHUB_PROXY="
} else {
    $ghProxy = $null
    foreach ($proxy in @("https://ghproxy.net", "https://ghfast.top")) {
        if (Test-Url "$proxy/https://github.com") {
            $ghProxy = $proxy
            break
        }
    }
    if ($ghProxy) {
        $lines += "GITHUB_BASE=$ghProxy/https://github.com"
        $lines += "GITHUB_PROXY=$ghProxy"
    } else {
        # No GitHub path at all. Record it explicitly and degrade rather than
        # exit 1: the user may still want the dataset + models (HF/MS) even if
        # the OmniDocBench code clone will fail later.
        Write-Host "WARN: No GitHub access (direct or proxy). The OmniDocBench code clone" -ForegroundColor Yellow
        Write-Host "      (eval-infra/01-omnidocbench/setup.ps1) will fail until GitHub or a" -ForegroundColor Yellow
        Write-Host "      proxy comes back. Other steps (dataset/models) are unaffected." -ForegroundColor Yellow
        $lines += "GITHUB_BASE=# UNREACHABLE (github.com, ghproxy.net, ghfast.top all down)"
        $lines += "GITHUB_PROXY="
        $degraded = $true
    }
}

# CTAN (TeX Live) -- probe the ACTUAL mirror URLs, not tug.org's homepage.
# tug.org reachability does NOT imply mirror.ctan.org (the global redirector)
# is reachable; for the China audience the USTC/TUNA mirrors are typically the
# fast path, so try them FIRST and only fall back to the global redirector.
$ctanMirror = $null
foreach ($mirror in @(
    "https://mirrors.ustc.edu.cn/CTAN/systems/texlive/tlnet",
    "https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet",
    "https://mirror.ctan.org/systems/texlive/tlnet"
)) {
    if (Test-Url $mirror) { $ctanMirror = $mirror; break }
}
if ($ctanMirror) {
    $lines += "CTAN_MIRROR=$ctanMirror"
} else {
    # All CTAN mirrors unreachable. Mark it explicitly so downstream scripts can
    # distinguish "never probed" from "probed but unreachable" (a plain missing
    # key would make setup.sh silently fall back to its hardcoded default, which
    # is exactly the mirror that just failed -- compounding the outage).
    $lines += "CTAN_MIRROR=# UNREACHABLE (all CTAN mirrors down)"
    Write-Host "WARN: all CTAN mirrors unreachable; TeX Live install (setup.sh step 2) will fail until a mirror comes back." -ForegroundColor Yellow
    Write-Host "      Tried: USTC, TUNA, mirror.ctan.org." -ForegroundColor Yellow
    $degraded = $true
}

# PyPI / uv indexes. Probe all three independently in fixed priority order.
$pypi = Test-Url "https://pypi.org/simple"
$tuna = Test-Url "https://pypi.tuna.tsinghua.edu.cn/simple"
$aliyun = Test-Url "https://mirrors.aliyun.com/pypi/simple"
$uvIndexes = @(
    [ordered]@{ id = "pypi"; url = "https://pypi.org/simple"; priority = 0; reachable = [bool]$pypi },
    [ordered]@{ id = "tuna"; url = "https://pypi.tuna.tsinghua.edu.cn/simple"; priority = 1; reachable = [bool]$tuna },
    [ordered]@{ id = "aliyun"; url = "https://mirrors.aliyun.com/pypi/simple"; priority = 2; reachable = [bool]$aliyun }
)
if ($pypi) {
    $lines += "PYPI_INDEX=https://pypi.org/simple"
} elseif ($tuna) {
    $lines += "PYPI_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
} elseif ($aliyun) {
    $lines += "PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple"
} else {
    $lines += "PYPI_INDEX=# UNREACHABLE (pypi.org and Tsinghua both down)"
    Write-Host "WARN: PyPI unreachable (pypi.org, Tsinghua, and Aliyun all down); pip installs will fail." -ForegroundColor Yellow
    $degraded = $true
}

# WSL rootfs (Ubuntu base)
$lines += "UBUNTU_ROOTFS=https://mirrors.ustc.edu.cn/ubuntu-cdimage/ubuntu-base/releases/22.04/release/ubuntu-base-22.04.5-base-amd64.tar.gz"

$status = if ($datasetOffline) { "offline" } elseif ($degraded) { "degraded" } else { "ok" }
Write-MirrorsContracts $status $uvIndexes
Write-Host "Sources: $($lines[1]) | $($lines | Select-String 'GITHUB_BASE') | $($lines | Select-String 'CTAN_MIRROR')"
if ($datasetOffline) {
    exit 1
}
exit 0
