<#
.SYNOPSIS
Download OmniDocBench eval code (GitHub) + v1.6 dataset (1651 pages).

Model-agnostic: this infrastructure is required for ANY model's evaluation.
The eval code lives in OmniDocBench/ (git checkout); the dataset (ground-truth
manifest + 1651 page images) lives in data/.

.DESCRIPTION
Steps:
  1. Read mirrors.env (written by scripts/detect-mirrors.ps1) for GITHUB_BASE
     and the dataset source (HF_OR_MS / DATASET_URL).
  2. Clone OmniDocBench from $GITHUB_BASE/opendatalab/OmniDocBench.git (depth 1)
     into OmniDocBench/  -- skipped if pdf_validation.py already present.
  3. Download the v1.6 dataset into data/ -- skipped if OmniDocBench.json present.
     - modelscope: `modelscope download --dataset OpenDataLab/OmniDocBench --local_dir data`
    - huggingface: locked `.venv\Scripts\hf.exe download ...`
  4. Create a repo-root .venv (Python 3.10/3.11 -- OmniDocBench is NOT 3.12+
     compatible) and pip install the OmniDocBench runtime deps into it. The
     venv is what eval-infra/03-scoring/score.ps1 runs pdf_validation.py with.
     Skipped if .venv is already importable.

The dataset download (~1651 PNGs, ~18 min on a slow link) is idempotent: re-running
setup.ps1 after a partial/interrupted download resumes via the HF/MS CLI's own cache.

.PARAMETER SkipDataset
Skip the dataset download (use when you only need the eval code). Code clone is
always attempted if missing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1
  powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipDataset
#>
[CmdletBinding()]
param(
    [switch] $SkipDataset
)
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

function Ensure-ShortRepoRoot {
    param([string]$RepoRoot)
    $normalizedRoot = [System.IO.Path]::GetFullPath($RepoRoot)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedRoot.ToLowerInvariant()))
    } finally {
        $sha.Dispose()
    }
    $hash = ([System.BitConverter]::ToString($hashBytes) -replace "-", "").ToLowerInvariant().Substring(0, 12)
    $alias = Join-Path (Join-Path (Join-Path $env:LOCALAPPDATA "OmniDocBenchAMD") $hash) "repo"
    $aliasParent = Split-Path -Parent $alias
    New-Item -ItemType Directory -Force -Path $aliasParent | Out-Null
    if (Test-Path -LiteralPath $alias) {
        $item = Get-Item -LiteralPath $alias -Force
        $target = (@($item.Target) -join "")
        if ([System.IO.Path]::GetFullPath($target) -ne $normalizedRoot) {
            Remove-Item -LiteralPath $alias -Force
        }
    }
    if (-not (Test-Path -LiteralPath $alias)) {
        New-Item -ItemType Junction -Path $alias -Target $normalizedRoot | Out-Null
    }
    return $alias
}

# NOTE: Join-Path is nested (rather than the PS 7+ 3-arg form) so this runs on
# Windows PowerShell 5.1 as well as PowerShell 7+.
$rootDir  = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)  # repo root
$envFile  = Join-Path $rootDir "mirrors.env"
$shortRoot = Ensure-ShortRepoRoot -RepoRoot $rootDir
Write-Host "Windows short repository path: $shortRoot" -ForegroundColor DarkGray
$lockFile = Join-Path $rootDir "upstream-lock.json"
$lockVerify = Join-Path $rootDir "scripts\verify-upstream-lock.ps1"
$treeVerify = Join-Path $rootDir "scripts\verify_dataset_tree.py"
if (-not (Test-Path -LiteralPath $lockFile)) { throw "Upstream lock missing: $lockFile" }
$upstreamLock = Get-Content -Raw -Encoding UTF8 -LiteralPath $lockFile | ConvertFrom-Json
$odbCommit = [string]$upstreamLock.git.omnidocbench.commit
$datasetRevision = [string]$upstreamLock.huggingface.dataset.revision

# --- Parse mirrors.env (KEY=VALUE lines; ignore comments / blanks) ---
$cfg = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.*)$") { $cfg[$matches[1]] = $matches[2] }
    }
} else {
    Write-Host "WARN: mirrors.env not found at $envFile; using defaults." -ForegroundColor Yellow
    Write-Host "      Run scripts/detect-mirrors.ps1 first for a China-firewall-aware setup." -ForegroundColor Yellow
}
$githubBase = if ($cfg["GITHUB_BASE"]) { $cfg["GITHUB_BASE"] } else { "https://github.com" }
$hfOrMs    = if ($cfg["HF_OR_MS"])    { $cfg["HF_OR_MS"] }    else { "modelscope" }
# PyPI index (from detect-mirrors.ps1). Fall back to Tsinghua (China-friendly)
# then pypi.org. Used by the venv install in step 4.
$pypiIndex = if ($cfg["PYPI_INDEX"]) { $cfg["PYPI_INDEX"] } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }

# --- 1. Clone OmniDocBench eval code ---
$odbDir = Join-Path $PSScriptRoot "OmniDocBench"
$probe  = Join-Path $odbDir "pdf_validation.py"
$gitHead = Join-Path $odbDir ".git\HEAD"
if (-not (Test-Path $probe)) {
    $repoUrl = "$githubBase/opendatalab/OmniDocBench.git"
    # Resumable clone: if a .git exists (partial/interrupted clone), resume via
    # fetch+reset instead of nuking the dir and re-downloading from scratch. A
    # bare Remove-Item on re-run would discard everything already fetched.
    if (Test-Path $gitHead) {
        Write-Host "Incomplete clone detected; fetching locked commit $odbCommit ..." -ForegroundColor Cyan
        git -C $odbDir fetch --depth 1 origin $odbCommit
        if ($LASTEXITCODE -eq 0) {
            git -C $odbDir checkout --detach --force FETCH_HEAD
        } else {
            Write-Host "git fetch failed; removing partial clone and retrying fresh." -ForegroundColor Yellow
            Remove-Item -Recurse -Force $odbDir
            git init -q $odbDir
            git -C $odbDir remote add origin $repoUrl
            git -C $odbDir fetch --depth 1 origin $odbCommit
            if ($LASTEXITCODE -eq 0) { git -C $odbDir checkout --detach FETCH_HEAD }
        }
    } else {
        Write-Host "Fetching locked OmniDocBench commit $odbCommit from $repoUrl ..." -ForegroundColor Cyan
        git init -q $odbDir
        git -C $odbDir remote add origin $repoUrl
        git -C $odbDir fetch --depth 1 origin $odbCommit
        if ($LASTEXITCODE -eq 0) { git -C $odbDir checkout --detach FETCH_HEAD }
    }
    if ($LASTEXITCODE -ne 0) { throw "git clone failed for OmniDocBench (URL: $repoUrl)" }
    if (-not (Test-Path $probe)) { throw "Clone succeeded but pdf_validation.py missing in $odbDir" }
    Write-Host "OmniDocBench code cloned to $odbDir" -ForegroundColor Green
} else {
    Write-Host "OmniDocBench code already present: $probe" -ForegroundColor Green
}
& powershell -ExecutionPolicy Bypass -File $lockVerify -Component OmniDocBench -Path $odbDir
if ($LASTEXITCODE -ne 0) { throw "OmniDocBench checkout does not match upstream-lock.json" }

# --- 1a. Apply repo-maintained OmniDocBench compatibility patches -----------
# The OmniDocBench checkout is a generated dependency and is ignored by this
# repo. Keep local scoring compatibility fixes reproducible by applying tracked
# patch files after clone/resume. Idempotency is handled with a reverse patch
# check: if the patch can be reversed cleanly, it is already applied.
$patchDir = Join-Path $PSScriptRoot "patches"
$formulaPatch = Join-Path $patchDir "0001-formula-cdm-normalization.patch"
$timeoutPatch = Join-Path $patchDir "0002-timeout-fallback-long-text-span.patch"
$rootPatchDir = Join-Path $rootDir "patches\omnidocbench"
$windowsCdmPatch = Join-Path $rootPatchDir "windows-cdm.patch"
if (Test-Path $formulaPatch) {
    $formulaFile = Join-Path $odbDir "src\core\preprocess\formula_cdm.py"
    $formulaTest = Join-Path $odbDir "tests\test_formula_cdm_normalization.py"
    $formulaApplied = (
        (Test-Path $formulaFile) -and
        (Test-Path $formulaTest) -and
        (Select-String -LiteralPath $formulaFile -Pattern "pred_cdm_alt" -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $formulaFile -Pattern "\overrightarrow" -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $formulaFile -Pattern "_EMPTY_ARRAY_SPEC_RE" -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $formulaTest -Pattern "test_sanitize_formula_fixes_empty_array_column_spec" -SimpleMatch -Quiet)
    )
    if ($formulaApplied) {
        Write-Host "Formula CDM normalization patch already present." -ForegroundColor Green
    } else {
        Write-Host "Applying Formula CDM normalization patch ..." -ForegroundColor Cyan
        git -C $odbDir apply --check $formulaPatch
        if ($LASTEXITCODE -ne 0) {
            throw "Formula CDM normalization patch does not apply cleanly. Inspect $formulaPatch and $odbDir."
        }
        git -C $odbDir apply $formulaPatch
        if ($LASTEXITCODE -ne 0) { throw "Formula CDM normalization patch failed." }
        Write-Host "Formula CDM normalization patch applied." -ForegroundColor Green
    }
}
if (Test-Path $timeoutPatch) {
    $timeoutFile = Join-Path $odbDir "src\dataset\end2end_dataset.py"
    $timeoutTest = Join-Path $odbDir "tests\test_timeout_fallback_long_text_span.py"
    $timeoutApplied = (
        (Test-Path $timeoutFile) -and
        (Test-Path $timeoutTest) -and
        (Select-String -LiteralPath $timeoutFile -Pattern "int(len(gt_norm) / 24) + 4" -SimpleMatch -Quiet) -and
        (Select-String -LiteralPath $timeoutTest -Pattern "test_local_text_span_fallback_recovers_long_text_split_across_many_predictions" -SimpleMatch -Quiet)
    )
    if ($timeoutApplied) {
        Write-Host "Timeout fallback long-text span patch already present." -ForegroundColor Green
    } else {
        Write-Host "Applying timeout fallback long-text span patch ..." -ForegroundColor Cyan
        git -C $odbDir apply --unidiff-zero --check $timeoutPatch
        if ($LASTEXITCODE -ne 0) {
            throw "Timeout fallback long-text span patch does not apply cleanly. Inspect $timeoutPatch and $odbDir."
        }
        git -C $odbDir apply --unidiff-zero $timeoutPatch
        if ($LASTEXITCODE -ne 0) { throw "Timeout fallback long-text span patch failed." }
        Write-Host "Timeout fallback long-text span patch applied." -ForegroundColor Green
    }
}

if (Test-Path $windowsCdmPatch) {
    git -C $odbDir apply --reverse --check $windowsCdmPatch
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Windows native CDM patch already present." -ForegroundColor Green
    } else {
        Write-Host "Applying Windows native CDM patch ..." -ForegroundColor Cyan
        git -C $odbDir apply --check $windowsCdmPatch
        if ($LASTEXITCODE -ne 0) {
            throw "Windows native CDM patch does not apply cleanly. Inspect $windowsCdmPatch and $odbDir."
        }
        git -C $odbDir apply $windowsCdmPatch
        if ($LASTEXITCODE -ne 0) { throw "Windows native CDM patch failed." }
        Write-Host "Windows native CDM patch applied." -ForegroundColor Green
    }
} else {
    Write-Host "WARN: Windows native CDM patch missing: $windowsCdmPatch" -ForegroundColor Yellow
}

# --- 1b. Create repo-root .venv + install OmniDocBench deps ---
# OmniDocBench is NOT Python 3.12+ compatible (uses inspect.getargspec /
# distutils removed in 3.12). Prefer uv + the repo's pinned Python 3.11 so a
# fresh machine does not depend on the Windows `py` launcher. Retain py/python
# as compatibility fallbacks, but never create a known-incompatible venv.
#
# The venv lives at <repo>/.venv so eval-infra/03-scoring/score.ps1 can target
# .venv\Scripts\python.exe directly instead of relying on a bare `python` that
# may be 3.13. Idempotent: skipped if .venv\Scripts\python.exe already exists
# and the deps are importable there.
$venvDir = Join-Path $rootDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvReady = $false
$venvExists = Test-Path $venvPython
if (Test-Path $venvPython) {
    $venvVersion = & $venvPython --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $venvVersion -notmatch "Python 3\.(10|11)\.") {
        throw "Existing .venv must use Python 3.10 or 3.11 (found: '$venvVersion'). Remove $venvDir and re-run setup.ps1."
    }
    # Probe: can the venv import the core OmniDocBench deps?
    $probePy = "import importlib; [importlib.import_module(m) for m in ('pylatexenc','PIL','numpy','pandas','yaml','Levenshtein','apted')]"
    & $venvPython -c $probePy *> $null
    if ($LASTEXITCODE -eq 0) { $venvReady = $true }
}

if ($venvReady) {
    Write-Host ".venv already provisioned with OmniDocBench deps: $venvPython" -ForegroundColor Green
} else {
    # Locate uv from PATH or its standard per-user install location. Using an
    # explicit path also handles a terminal opened before uv updated PATH.
    $uvExe = $null
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $uvExe = $uvCommand.Source
    } else {
        $uvUserExe = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
        if (Test-Path $uvUserExe) { $uvExe = $uvUserExe }
    }

    if (-not $venvExists) {
        if ($uvExe) {
            Write-Host "Creating .venv with uv-managed Python 3.11 ..." -ForegroundColor Cyan
            & $uvExe venv --python 3.11 --seed $venvDir
            if ($LASTEXITCODE -ne 0) { throw "uv venv failed. Run 'uv python install 3.11' and retry." }
        } else {
            # Compatibility fallback for users who already manage Python with
            # python.org. Guard command discovery before invoking either tool.
            $basePy = $null
            if (Get-Command py -ErrorAction SilentlyContinue) {
                foreach ($ver in @("-3.11", "-3.10")) {
                    $test = & py $ver --version 2>$null
                    if ($LASTEXITCODE -eq 0 -and $test -match "Python 3\.(10|11)\.") {
                        $basePy = "py $ver"
                        Write-Host "Using Python $ver for venv: $test" -ForegroundColor DarkGray
                        break
                    }
                }
            }
            if (-not $basePy -and (Get-Command python -ErrorAction SilentlyContinue)) {
                $sysVer = & python --version 2>&1
                if ($LASTEXITCODE -eq 0 -and $sysVer -match "Python 3\.(10|11)\.") {
                    $basePy = "python"
                }
            }
            if (-not $basePy) {
                throw "OmniDocBench requires Python 3.10 or 3.11. Install uv, run 'uv python install 3.11', and re-run setup.ps1."
            }

            Write-Host "Creating .venv at $venvDir ..." -ForegroundColor Cyan
            Invoke-Expression "$basePy -m venv `"$venvDir`""
            if ($LASTEXITCODE -ne 0) { throw "venv creation failed (interpreter: $basePy)" }
        }
    }

    if ($uvExe -and (Test-Path (Join-Path $rootDir "uv.lock"))) {
        Write-Host "Syncing locked OmniDocBench environment with uv (index: $pypiIndex) ..." -ForegroundColor Cyan
        $previousUvIndex = $env:UV_DEFAULT_INDEX
        try {
            $env:UV_DEFAULT_INDEX = $pypiIndex
            # --inexact preserves model-adapter packages installed by later
            # setup phases when this idempotent infrastructure step is rerun.
            & $uvExe sync --locked --all-groups --inexact --python $venvPython
        } finally {
            $env:UV_DEFAULT_INDEX = $previousUvIndex
        }
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed (index: $pypiIndex). Re-run setup.ps1; if it persists see docs/pitfalls.md#network."
        }
    } else {
        # Compatibility path for source archives or older clones without the
        # lock file. Keep the dependency list aligned with pyproject.toml.
        $deps = "apted beautifulsoup4 evaluate func-timeout Levenshtein loguru lxml numpy pandas Pillow psutil pylatexenc PyYAML scipy tabulate tqdm nltk matplotlib"
        Write-Host "Installing OmniDocBench deps into .venv (index: $pypiIndex) ..." -ForegroundColor Cyan
        $depsArgs = $deps -split ' '
        & $venvPython -m pip install -i $pypiIndex $depsArgs
        if ($LASTEXITCODE -ne 0) {
            throw "pip install of OmniDocBench deps failed (index: $pypiIndex). Re-run setup.ps1; if it persists see docs/pitfalls.md#network."
        }
    }
    Write-Host "OmniDocBench deps installed into .venv" -ForegroundColor Green
}

if ($SkipDataset) {
    Write-Host "Skipping dataset download (-SkipDataset)." -ForegroundColor Yellow
    Write-Host "OmniDocBench code setup complete." -ForegroundColor Green
    exit 0
}

# --- 2. Download v1.6 dataset (1651 pages + GT manifest) ---
$dataDir  = Join-Path $PSScriptRoot "data"
$manifest = Join-Path $dataDir "OmniDocBench.json"
if (Test-Path $manifest) {
    $imgDir = Join-Path $dataDir "images"
    try {
        $manifestPages = @(Get-Content -Raw -Encoding UTF8 -LiteralPath $manifest | ConvertFrom-Json)
        $imagePaths = @($manifestPages | ForEach-Object { $_.page_info.image_path } | Where-Object { $_ })
    } catch {
        throw "Dataset manifest is invalid JSON: $manifest. $($_.Exception.Message)"
    }
    if ($imagePaths.Count -eq 0) {
        throw "Dataset manifest contains no page_info.image_path entries: $manifest"
    }
    $missingImages = @($imagePaths | Where-Object { -not (Test-FileExtended -Path (Join-Path $imgDir $_)) })
    if ($missingImages.Count -eq 0) {
        & powershell -ExecutionPolicy Bypass -File $lockVerify -Component DatasetManifest -Path $manifest
        if ($LASTEXITCODE -ne 0) { throw "Dataset manifest does not match upstream-lock.json" }
        & $venvPython $treeVerify --manifest $manifest --image-dir $imgDir --lock $lockFile
        if ($LASTEXITCODE -ne 0) { throw "Dataset image tree does not match upstream-lock.json" }
        Write-Host "Dataset already complete: $manifest ($($imagePaths.Count)/$($imagePaths.Count) referenced images)." -ForegroundColor Green
        Write-Host "OmniDocBench setup complete." -ForegroundColor Green
        exit 0
    }
    Write-Host "Partial dataset detected: $($imagePaths.Count - $missingImages.Count)/$($imagePaths.Count) referenced images present; resuming download." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if ($hfOrMs -eq "huggingface") {
    Write-Host "Downloading OmniDocBench v1.6 dataset from HuggingFace ..." -ForegroundColor Cyan
    $hfCli = Join-Path $venvDir "Scripts\hf.exe"
    if (-not (Test-Path -LiteralPath $hfCli)) {
        $legacyHfCli = Join-Path $venvDir "Scripts\huggingface-cli.exe"
        if (Test-Path -LiteralPath $legacyHfCli) { $hfCli = $legacyHfCli }
    }
    if (-not (Test-Path -LiteralPath $hfCli)) {
        throw "Hugging Face CLI missing from the locked environment. Run 'uv sync --locked --all-groups' and retry."
    }
    $previousDisableXet = $env:HF_HUB_DISABLE_XET
    try {
        # Xet token endpoints are prone to anonymous 429 responses on large
        # snapshots. Ordinary HTTP is resumable and avoids that extra token
        # request; modest concurrency is friendlier to public rate limits.
        $env:HF_HUB_DISABLE_XET = "1"
        & $hfCli download opendatalab/OmniDocBench `
            --repo-type dataset --revision $datasetRevision --local-dir $dataDir --max-workers 4
    } finally {
        $env:HF_HUB_DISABLE_XET = $previousDisableXet
    }
    if ($LASTEXITCODE -ne 0) { throw "Hugging Face dataset download failed; re-run setup.ps1 to resume, or see docs/pitfalls.md#network." }

    # On systems with LongPathsEnabled=0, the Hub client can report success
    # while skipping files whose full destination exceeds MAX_PATH. Recover
    # only those manifest references through a short temp root, then copy via
    # the Win32 extended-path prefix. This avoids requiring admin registry
    # changes or forcing users to relocate a OneDrive clone.
    if (Test-Path -LiteralPath $manifest) {
        $manifestPages = @(Get-Content -Raw -Encoding UTF8 -LiteralPath $manifest | ConvertFrom-Json)
        $imagePaths = @($manifestPages | ForEach-Object { $_.page_info.image_path } | Where-Object { $_ })
        $imgDir = Join-Path $dataDir "images"
        $missingImages = @($imagePaths | Where-Object { -not (Test-FileExtended -Path (Join-Path $imgDir $_)) })
        $longMissing = @($missingImages | Where-Object { (Join-Path $imgDir $_).Length -ge 260 })
        if ($longMissing.Count -gt 0) {
            $recoveryRoot = Join-Path $env:TEMP "omnidocbench-hf-longpath"
            Write-Host "Recovering $($longMissing.Count) MAX_PATH dataset files through $recoveryRoot ..." -ForegroundColor Yellow
            foreach ($imagePath in $longMissing) {
                $remotePath = "images/$imagePath"
                & $hfCli download opendatalab/OmniDocBench $remotePath `
                    --repo-type dataset --revision $datasetRevision --local-dir $recoveryRoot
                if ($LASTEXITCODE -ne 0) { throw "Long-path recovery download failed: $remotePath" }
                $sourcePath = Join-Path (Join-Path $recoveryRoot "images") $imagePath
                if (-not (Test-Path -LiteralPath $sourcePath)) { throw "Long-path recovery source missing: $sourcePath" }
                $targetPath = Join-Path $imgDir $imagePath
                [System.IO.File]::Copy($sourcePath, (ConvertTo-ExtendedPath -Path $targetPath), $true)
            }
        }
    }
} else {
    Write-Host "Downloading OmniDocBench v1.6 dataset from ModelScope ..." -ForegroundColor Cyan
    Write-Host "(~1651 images; this can take ~18 minutes on a slow link.)" -ForegroundColor DarkGray
    modelscope download --dataset OpenDataLab/OmniDocBench --local_dir $dataDir
    if ($LASTEXITCODE -ne 0) { throw "modelscope download failed" }
}

if (-not (Test-Path $manifest)) {
    throw "Download reported success but $manifest is missing. Inspect $dataDir."
}
$manifestPages = @(Get-Content -Raw -Encoding UTF8 -LiteralPath $manifest | ConvertFrom-Json)
$imagePaths = @($manifestPages | ForEach-Object { $_.page_info.image_path } | Where-Object { $_ })
$imgDir = Join-Path $dataDir "images"
$missingImages = @($imagePaths | Where-Object { -not (Test-FileExtended -Path (Join-Path $imgDir $_)) })
if ($imagePaths.Count -eq 0 -or $missingImages.Count -gt 0) {
    throw "Dataset download is incomplete: $($imagePaths.Count - $missingImages.Count)/$($imagePaths.Count) manifest-referenced images present. Re-run setup.ps1 to resume."
}
& powershell -ExecutionPolicy Bypass -File $lockVerify -Component DatasetManifest -Path $manifest
if ($LASTEXITCODE -ne 0) { throw "Dataset manifest does not match upstream-lock.json" }
& $venvPython $treeVerify --manifest $manifest --image-dir $imgDir --lock $lockFile
if ($LASTEXITCODE -ne 0) { throw "Dataset image tree does not match upstream-lock.json" }

Write-Host "Dataset downloaded to $dataDir ($($imagePaths.Count) referenced images verified)" -ForegroundColor Green
Write-Host "OmniDocBench setup complete." -ForegroundColor Green
exit 0
