# Phase A 工程品质提升 Implementation Plan (2026-08-01)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仓库工程品质提升到顶级开源水准:卫生、CI、一致性守卫测试、版本化,全部本机实测验收。

**Architecture:** 不改任何 setup/verify 脚本逻辑与用户体验路径;新增 CI( pytest + PSScriptAnalyzer )与一组"守卫测试"( README 双语一致性、markdown 相对链接、评分配置存在性),把人工审计发现的问题固化成 CI 强制检查。

**Tech Stack:** PowerShell 5.1/7+、Python 3.10/3.11、pytest、PSScriptAnalyzer、GitHub Actions (windows-latest)。

**Spec:** `docs/superpowers/specs/2026-08-01-open-source-quality-design.md`(Phase A 部分)

## Global Constraints

- 不修改 `eval-infra/**/setup.*`、`eval-infra/**/verify.*`、`scripts/*.ps1` 的逻辑(A2 lint 报错的最小修复除外)。
- Windows 评分相关运行必须 `PYTHONUTF8=1`。
- Commit 用 conventional commits(参照 git log 现有风格,如 `docs:`、`fix:`、`test:`、`ci:`、`chore:`)。
- PowerShell 脚本启动方式:`powershell -ExecutionPolicy Bypass -File ...`。
- 每个验收命令的真实输出存档到 `docs/phase-a-verification-2026-08-01.md`(Task 9 汇总)。
- 仓库根:`C:\Users\rocm\Desktop\omnidocbench-amd-windows`,所有命令以此 CWD。
- 已确认事实(2026-08-01 审计):pytest 基线 `76 passed`;PSScriptAnalyzer 本机未安装;`cdm_debug.py`/`cdm_diag.py` 逻辑已被 547 行的 `eval-infra/03-scoring/formula_cdm_diagnostics.py` 覆盖,可删;README.zh-CN.md:105-106 把 official-local CDM 错写为 97.36(EN 为 96.5022);git 本地对象库 419 MiB 含 323 MB 不可达 blob;远端仅 1.3 MB。

---

### Task 1: 仓库卫生——移出与删除

**Files:**
- Delete: `llama-b9892-bin-win-hip-radeon-x64.zip`、`tmp_cdm-0006_gt.txt`、`tmp_cdm-0017_gt.txt`、`tmp_cdm-0026_gt.txt`、`tmp_cdm-0039_gt.txt`、`cdm_debug.py`、`cdm_diag.py`、`tmp/`
- Move: `llama-b9892-bin-win-hip-radeon-x64/`、`llama.cpp-b9892-src/` → `C:\AIwork\tools\`
- Untouched: `adapters/mineru/`(Phase B 处理)、`predictions/`(已 gitignore)

**Interfaces:**
- Produces: 干净的工作区;`C:\AIwork\tools\llama-b9892-bin-win-hip-radeon-x64\` 保留 llama-server 二进制(VLM server setup.ps1 若引用仓库内路径,本任务验证之,见 Step 4)。

- [ ] **Step 1: 确认 VLM server setup.ps1 是否引用仓库内 llama 路径**

Run: `grep -n "llama" adapters/paddleocr-vl-1.6/01-vlm-server/setup.ps1 | head -20`
Expected: 输出显示 setup.ps1 如何定位 llama-server。若它引用仓库根的 `llama-b9892-bin-win-hip-radeon-x64/`,记录该行;若下载到自身目录(如 `adapters/paddleocr-vl-1.6/01-vlm-server/` 下),则移出无影响。

- [ ] **Step 2: 移出两个大目录**

```powershell
mkdir C:\AIwork\tools -Force
move llama-b9892-bin-win-hip-radeon-x64 C:\AIwork\tools\
move llama.cpp-b9892-src C:\AIwork\tools\
```
若 Step 1 发现 setup.ps1 引用仓库内路径,则改为在仓库内原位置创建指向 `C:\AIwork\tools\` 的 junction:`cmd /c mklink /J llama-b9892-bin-win-hip-radeon-x64 C:\AIwork\tools\llama-b9892-bin-win-hip-radeon-x64`(junction 不入 git,见 Task 2 的 gitignore)。

- [ ] **Step 3: 删除可再生垃圾**

```powershell
del llama-b9892-bin-win-hip-radeon-x64.zip, cdm_debug.py, cdm_diag.py, tmp_cdm-0006_gt.txt, tmp_cdm-0017_gt.txt, tmp_cdm-0026_gt.txt, tmp_cdm-0039_gt.txt
rmdir /s /q tmp
```

- [ ] **Step 4: 验证工作区**

Run: `git status --short`
Expected: 仅剩 `?? adapters/mineru/`、`?? eval-infra/01-omnidocbench/configs/v16-cdm-mineru-pipeline.yaml`、`?? docs/handoff-2026-07-08-formula-cdm.md`(这三项属 Phase B/归档范畴,不在 Phase A 删除);其余全部消失。

- [ ] **Step 5: Commit(无文件变更则跳过)**

若 Step 2 建了 junction 或 Step 1 发现需改 setup.ps1 路径,提交该变更;否则本任务无 commit。

---

### Task 2: .gitignore 加固 + git gc

**Files:**
- Modify: `.gitignore`(追加 6 行)

**Interfaces:**
- Produces: 防止同类垃圾再次混入的 ignore 规则。

- [ ] **Step 1: 追加 .gitignore**

在 `.gitignore` 末尾追加:

```gitignore

# Machine-local tooling archives/runtimes (re-downloadable by setup.ps1)
llama-*/
*.zip

# One-off debug scratch (diagnostics live in eval-infra/03-scoring/)
cdm_debug.py
cdm_diag.py
tmp_cdm-*.txt
tmp/
```

- [ ] **Step 2: 验证忽略生效**

Run: `git status --short --ignored | grep "^!!" | head`
Expected: 若建了 junction,`llama-b9892-bin-win-hip-radeon-x64/` 出现在 ignored 列表;无意外忽略已跟踪文件(`git ls-files` 数量仍为 107)。

Run: `git ls-files | wc -l`
Expected: `107`

- [ ] **Step 3: git gc 清除不可达对象**

```bash
git gc --prune=now --aggressive
git count-objects -vH
```
Expected: `size-pack` 从 ~419 MiB 降到 < 5 MiB;`count: 0` 附近。记录真实输出(进 Task 9 证据文档)。

- [ ] **Step 4: 确认仓库完整性**

Run: `git fsck --no-progress 2>&1 | head -5 && git log --oneline -3`
Expected: 无 `error`/`missing`;最近提交可见。

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore re-downloadable llama archives and one-off debug scratch"
```

---

### Task 3: PSScriptAnalyzer 本地安装 + lint 清零

**Files:**
- Modify: 任何被报 Error 的 `*.ps1`(最小修复,不改逻辑)

**Interfaces:**
- Produces: `Invoke-ScriptAnalyzer` 全仓库 0 Error(Warning 记录但不阻断);CI Task 6 复用同一命令。

- [ ] **Step 1: 安装 PSScriptAnalyzer(当前用户,免 UAC)**

```powershell
powershell -NoProfile -Command "Install-Module PSScriptAnalyzer -Scope CurrentUser -Force -Repository PSGallery; (Get-Module -ListAvailable PSScriptAnalyzer)[0].Version"
```
Expected: 打印版本号(如 `1.24.0`)。

- [ ] **Step 2: 全仓库扫描,输出基线**

```powershell
powershell -NoProfile -Command "Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error,Warning | Group-Object Severity | Select-Object Name,Count"
```
Expected: 打印 Error/Warning 计数(基线,进证据文档)。

- [ ] **Step 3: 逐个修复 Error(最小改动)**

```powershell
powershell -NoProfile -Command "Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error | Format-Table ScriptName,Line,RuleName,Message -AutoSize"
```
对每条 Error:读对应行,做不改变行为的最小修复(典型:`PSAvoidUsingWriteHost` 不属 Error;Error 多为语法/已弃用别名/空 catch)。修复后重跑本命令,直至 Error 计数为 0。Warning 不修(记入证据文档)。

- [ ] **Step 4: 回归验证——现有测试不受影响**

Run: `python -m pytest -q`
Expected: `76 passed`(与基线一致)。

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "style: fix PSScriptAnalyzer Error-level findings in PowerShell scripts"
```

---

### Task 4: 守卫测试(先写测试,看一致性测试失败)

**Files:**
- Create: `tests/test_readme_consistency.py`
- Create: `tests/test_markdown_links.py`
- Create: `tests/test_scoring_configs.py`
- Create: `tests/test_full_verify_params.py`

**Interfaces:**
- Produces: 四个 pytest 文件,CI(Task 6)与本地同一入口 `python -m pytest -q`。
- Consumes: 无(只读仓库文件)。

- [ ] **Step 1: 写 README 双语一致性测试**

`tests/test_readme_consistency.py`:

```python
"""Guard: README.md and README.zh-CN.md must publish identical metric numbers."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

METRIC_ROWS = ["Overall", "Edit-dist", "TEDS", "CDM"]


def extract_table_numbers(md_text: str) -> list[str]:
    """Return all numeric cells from the two metric tables (paper vs measured)."""
    numbers = []
    for line in md_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        if not any(k in line for k in METRIC_ROWS):
            continue
        numbers += re.findall(r"\d+\.\d+", line)
    return numbers


def test_metric_tables_match_between_languages():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    en_nums = extract_table_numbers(en)
    zh_nums = extract_table_numbers(zh)
    assert en_nums, "no metric numbers found in README.md"
    assert en_nums == zh_nums, (
        f"metric table mismatch:\nEN: {en_nums}\nZH: {zh_nums}"
    )


def test_official_local_cdm_value_consistent():
    """official-local Formula CDM is 96.5022 in EN; ZH must not contradict."""
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    assert "96.5022" in en
    assert "96.5022" in zh, "ZH README must cite official-local CDM 96.5022"
```

- [ ] **Step 2: 运行确认失败(Red)**

Run: `python -m pytest tests/test_readme_consistency.py -q`
Expected: `test_official_local_cdm_value_consistent` FAIL(`96.5022` 不在 ZH 中);`test_metric_tables_match_between_languages` PASS(表格已对齐)。

- [ ] **Step 3: 写 markdown 相对链接测试**

`tests/test_markdown_links.py`:

```python
"""Guard: relative links in tracked markdown files must resolve."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def tracked_markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [ROOT / line.strip() for line in out.stdout.splitlines() if line.strip()]


def test_relative_markdown_links_resolve():
    broken = []
    for md in tracked_markdown_files():
        text = md.read_text(encoding="utf-8")
        for m in LINK_RE.finditer(text):
            target = m.group(1).split("#")[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if not (md.parent / target).resolve().exists():
                broken.append(f"{md.relative_to(ROOT)}: {target}")
    assert not broken, "broken relative links:\n" + "\n".join(broken)
```

- [ ] **Step 4: 运行并修复所有死链**

Run: `python -m pytest tests/test_markdown_links.py -q`
Expected: 第一遍可能 FAIL,列出全部死链。对每个死链:目标文件存在但路径错→改链接;目标不存在且内容已过时→改链接到现存等价文档;锚点错→修锚点。逐条修复后重跑直至 PASS。记录修复清单(进证据文档)。

- [ ] **Step 5: 写评分配置存在性测试**

`tests/test_scoring_configs.py`:

```python
"""Guard: every -Config xxx.yaml referenced in README/AGENTS must exist."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "eval-infra" / "01-omnidocbench" / "configs"


def test_referenced_configs_exist():
    refs = set()
    for name in ("README.md", "README.zh-CN.md", "AGENTS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        refs |= set(re.findall(r"-Config\s+([A-Za-z0-9_.-]+\.yaml)", text))
        refs |= set(re.findall(r"configs[\\/]([A-Za-z0-9_.-]+\.yaml)", text))
    assert refs, "no config references found"
    missing = [r for r in sorted(refs) if not (CONFIG_DIR / r).is_file()]
    assert not missing, f"referenced configs missing: {missing}"
```

- [ ] **Step 6: 写 full-verify.ps1 参数 smoke 测试**

`tests/test_full_verify_params.py`:

```python
"""Guard: full-verify.ps1 keeps its documented parameter surface."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "full-verify.ps1"


def test_full_verify_documented_switches_exist():
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"param\s*\((.*?)\)", text, re.S)
    assert m, "param block not found"
    params = m.group(1)
    for switch in ("SkipWsl", "WindowsCdm", "SkipVlm"):
        assert f"${switch}" in params, f"param ${switch} missing from full-verify.ps1"
```

- [ ] **Step 7: 运行全部新测试**

Run: `python -m pytest tests/test_readme_consistency.py tests/test_markdown_links.py tests/test_scoring_configs.py tests/test_full_verify_params.py -q`
Expected: 一致性测试 1 个 FAIL(ZH 96.5022,Task 5 修);其余 PASS。

- [ ] **Step 8: Commit**

```bash
git add tests/test_readme_consistency.py tests/test_markdown_links.py tests/test_scoring_configs.py tests/test_full_verify_params.py
git commit -m "test: add guard tests for README consistency, markdown links, scoring configs"
```

---

### Task 5: 修复 README.zh-CN.md official-local CDM 数字(使守卫测试转绿)

**Files:**
- Modify: `README.zh-CN.md:105-106`

**Interfaces:**
- Consumes: Task 4 的 `test_official_local_cdm_value_consistent`。

- [ ] **Step 1: 对齐 EN 口径**

EN 原文(README.md:112-113):official-local 路线 Formula CDM `96.5022`;修正后 ROCm CDM `97.36`。
将 ZH 105-106 行("official-local 路线 Formula CDM 为 `97.36`;最新 ROCm lightweight 路线 Formula CDM 为 `97.36`")改为与 EN 一致:official-local 为 `96.5022`,ROCm 为 `97.36`,并保留"与官方 97.49 差距归因于推理后端差异"的原意。

- [ ] **Step 2: 运行一致性测试确认转绿**

Run: `python -m pytest tests/test_readme_consistency.py -q`
Expected: `2 passed`

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: 全部通过(76 + 新增数量)。

- [ ] **Step 4: Commit**

```bash
git add README.zh-CN.md
git commit -m "fix(zh-CN): correct official-local Formula CDM to 96.5022, align with EN"
```

---

### Task 6: CI workflow(.github/workflows/ci.yml)

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`(badge)、`README.zh-CN.md`(badge)

**Interfaces:**
- Consumes: Task 3 的 lint 命令、Task 4 的 pytest 入口。
- Produces: CI badge URL `https://github.com/AIwork4me/omnidocbench-amd-windows/actions/workflows/ci.yml/badge.svg`。

- [ ] **Step 1: 写 workflow**

`.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install test deps
        run: python -m pip install -U pip pytest psutil pyyaml
      - name: Run pytest
        run: python -m pytest -q

  psscriptanalyzer:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint PowerShell
        shell: pwsh
        run: |
          Install-Module PSScriptAnalyzer -Scope CurrentUser -Force -Repository PSGallery
          $errors = Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error
          if ($errors) {
            $errors | Format-Table ScriptName, Line, RuleName, Message -AutoSize | Out-String | Write-Host
            exit 1
          }
          Write-Host "PSScriptAnalyzer: 0 errors"
```

- [ ] **Step 2: 本地语法自检**

```powershell
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))" && echo YAML-OK
```
Expected: `YAML-OK`

- [ ] **Step 3: 加 badge(双语 README 第 3-7 行 badge 区追加一行)**

```markdown
[![ci](https://github.com/AIwork4me/omnidocbench-amd-windows/actions/workflows/ci.yml/badge.svg)](https://github.com/AIwork4me/omnidocbench-amd-windows/actions/workflows/ci.yml)
```

- [ ] **Step 4: Commit 并推送,观察 CI**

```bash
git add .github/workflows/ci.yml README.md README.zh-CN.md
git commit -m "ci: add pytest matrix + PSScriptAnalyzer workflow, README badges"
git push origin main
gh run list --limit 1
gh run watch
```
Expected: `gh run watch` 退出码 0,两个 job 全绿。把 run URL 记入证据文档。若红:读失败 job 日志,修复(典型:CI 环境缺依赖→补 pip install;路径大小写→修正),直至绿。

---

### Task 7: CHANGELOG.md + v1.0.0 tag

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`、`docs/windows-native-cdm-verification-2026-07-11.md`、`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md` 的事实。

- [ ] **Step 1: 写 CHANGELOG(Keep a Changelog 格式)**

`CHANGELOG.md`:

```markdown
# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- CI: pytest (3.10/3.11 matrix) + PSScriptAnalyzer on windows-latest.
- Guard tests: README EN/ZH metric consistency, markdown relative links,
  scoring-config existence, full-verify.ps1 parameter surface.
- `CHANGELOG.md`.

### Fixed
- README.zh-CN.md: official-local Formula CDM corrected to 96.5022 (EN parity).

## [1.0.0] - 2026-07-16

### Added
- Paired v16 Lightweight/Official published scores (Overall 95.99, Formula CDM 97.36).
- G4 inference speedup evidence: 1.7x (27-page stratified benchmark).
- Windows-native CDM path (`patches/omnidocbench/windows-cdm.patch` +
  `eval-infra/02-cdm-environment/verify-windows.ps1`), verified 2026-07-11.

## [0.9.0] - 2026-07-09

### Added
- First validated full-set release: PaddleOCR-VL-1.6 on OmniDocBench v1.6,
  Windows + AMD Radeon (ROCm/HIP), all four metrics.
- Idempotent setup/verify pipeline (`eval-infra/01..04`), `AGENTS.md`
  orchestration, symptom-indexed `docs/pitfalls.md`.
```

(以上数字已在审计中核实;Step 发布前用 `grep` 复核对 95.99/97.36/1.7x 三个值。)

- [ ] **Step 2: 核对数字**

Run: `grep -n "95.99\|97.36\|1.7x" README.md | head`
Expected: 三个值均出现,与 CHANGELOG 一致。

- [ ] **Step 3: Commit + tag**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG.md backfilling 2026-07 releases"
git tag -a v1.0.0 -m "Validated OmniDocBench v1.6 on Windows + AMD (PaddleOCR-VL-1.6 reference)"
git push origin main --follow-tags
```
Expected: `git tag -l` 含 `v1.0.0`;远端可见。

---

### Task 8: CONTRIBUTING.md 补强

**Files:**
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: Task 6 的 CI 事实、Task 4 的守卫测试清单。

- [ ] **Step 1: 实读现有 CONTRIBUTING.md**

Run: `cat CONTRIBUTING.md`
记录现有章节,保留其结构与语气。

- [ ] **Step 2: 追加三节(若无)**

```markdown
## Pull Request Process

1. Fork, branch from `main`, one logical change per PR.
2. Commit messages use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).
3. Before pushing, run the local verification checklist below; CI enforces it on every PR.
4. Scores or benchmark claims in docs must link to evidence (metric_result.json / release doc).

## Local Verification Checklist

```powershell
python -m pytest -q                     # all tests incl. guard tests
powershell -NoProfile -Command "Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error"   # must print nothing
```

## Adding a Model Adapter

See `adapters/_template/README.md`. The scorer never imports adapters;
the only contract is `run_adapter(img_dir, out_dir, server_url)` writing
`out_dir/<image_stem>.md` per page.
```

- [ ] **Step 3: 链接测试通过**

Run: `python -m pytest tests/test_markdown_links.py -q`
Expected: PASS(CONTRIBUTING 内链接有效)。

- [ ] **Step 4: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add PR process and local verification checklist to CONTRIBUTING"
```

---

### Task 9: Phase A 验收证据汇总

**Files:**
- Create: `docs/phase-a-verification-2026-08-01.md`

**Interfaces:**
- Consumes: Task 1-8 所有验收输出。

- [ ] **Step 1: 收集证据并写文档**

```markdown
# Phase A Verification Evidence (2026-08-01)

| 验收项 | 命令 | 结果 |
|---|---|---|
| 工作区干净 | `git status --short` | <粘贴真实输出> |
| git 对象库 | `git count-objects -vH` | size-pack: <真实值>(原 419 MiB) |
| pytest | `python -m pytest -q` | <N> passed |
| PSScriptAnalyzer | `Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error` | 0 errors(Warning <n> 条记录) |
| 双语一致性 | `python -m pytest tests/test_readme_consistency.py -q` | 2 passed |
| CI 全绿 | `gh run list --limit 1` | <run URL + conclusion: success> |
| CHANGELOG/tag | `git tag -l` | v1.0.0 |
```

- [ ] **Step 2: 全量最终回归**

Run: `python -m pytest -q && git status --short`
Expected: 全绿 + 工作区干净(除 Phase B 三项)。

- [ ] **Step 3: Commit + push**

```bash
git add docs/phase-a-verification-2026-08-01.md
git commit -m "docs: archive Phase A verification evidence (2026-08-01)"
git push origin main
```

---

## Self-Review 结论

- Spec 覆盖:A1→Task 1-2,A2→Task 3+6,A3→Task 4(守卫测试即关键路径测试扩展;adapter 契约测试归入 Phase B B1,届时有真实 adapter 可测),A4→Task 4/5/7,A5→Task 8,验收总表→Task 9。
- 无占位符;所有命令含预期输出;接口名前后一致。
- Phase B 单独出计划(需先完成 A,且需对 MinerU-ROCm 做移植前 discovery)。
