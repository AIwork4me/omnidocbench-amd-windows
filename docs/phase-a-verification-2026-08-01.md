# Phase A Verification Evidence (2026-08-01)

本文档归档 Phase A（工程质量：CI、守卫测试、仓库卫生）的全部验收证据。所有输出均为 2026-08-01 在分支 `phase-a/engineering-quality` 上实时运行所得。

## 验收总表

| 验收项 | 命令 | 结果 |
|---|---|---|
| 工作区干净 | `git status --short` | 仅剩 Phase B 三项（见下方输出），无其他改动 |
| git 对象库 | `git count-objects -vH` | `size-pack: 1.49 MiB`（原 419.07 MiB） |
| pytest | `python -m pytest -q` | 145 passed in 11.01s |
| PSScriptAnalyzer | `Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error` | Count = **0** errors |
| 双语一致性 | `python -m pytest tests/test_readme_consistency.py -q` | 2 passed |
| CI 全绿 | `gh run list --limit 3` | run [30721029441](https://github.com/AIwork4me/omnidocbench-amd-windows/actions/runs/30721029441) conclusion: **success**（PR [#3](https://github.com/AIwork4me/omnidocbench-amd-windows/pull/3)） |
| CHANGELOG/tag | `git tag -l` | 仅 `v1.6-accuracy`；**v1.0.0 尚未创建** — 打标签推迟到 PR 合并后（见下方说明） |

## 量化收益

| 指标 | 之前 | 之后 |
|---|---:|---:|
| 仓库对象库（`git count-objects -vH` size-pack） | 419.07 MiB | 1.49 MiB |
| 工作区杂项体积 | ~1.6 GB | 已删除/移出仓库 |
| 失效 Markdown 链接 | 11 处 | 0（已修复） |
| 守卫测试 | 0 | 4 个文件 / 5 个测试 |
| CI | 无 | 2 个 job 全绿 |
| ZH README 事实性错误（official-local CDM） | 97.36 | 96.5022（已修正） |

## 原始输出

### `git status --short`

```
?? adapters/mineru/
?? docs/handoff-2026-07-08-formula-cdm.md
?? eval-infra/01-omnidocbench/configs/v16-cdm-mineru-pipeline.yaml
```

三项均为 Phase B（MinerU 适配）预备工件，不属于 Phase A 范围，保留不提交。

### `git count-objects -vH`

```
count: 66
size: 161.88 KiB
in-pack: 1335
packs: 2
size-pack: 1.49 MiB
prune-packable: 0
garbage: 0
size-garbage: 0 bytes
```

### `python -m pytest -q`（全量）

```
........................................................................ [ 49%]
........................................................................ [ 99%]
.                                                                        [100%]
145 passed in 11.01s
```

### PSScriptAnalyzer

```
powershell -NoProfile -Command "(Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error).Count"
```

输出末尾为 `0`。注：本地运行时前部有 FileNotFoundException 噪声，来自 `.worktrees/` 与 `.venv/` 下的超长路径（无害；CI 的干净 checkout 中不存在这些目录，故不出现）。Error 计数为 0。

### `python -m pytest tests/test_readme_consistency.py -q`

```
..                                                                       [100%]
2 passed in 0.01s
```

### `gh run list --limit 3`

```
completed	success	Phase A: engineering quality (CI, guard tests, hygiene)	CI	phase-a/engineering-quality	pull_request	30721029441	55s	2026-08-01T22:19:59Z
completed	success	docs: de-link generated mirrors.env in 02-cdm README (untracked in CI…	CI	phase-a/engineering-quality	push	30721028259	53s	2026-08-01T22:19:56Z
completed	failure	Phase A: engineering quality (CI, guard tests, hygiene)	CI	phase-a/engineering-quality	pull_request	30720928627	48s	2026-08-01T22:17:01Z
```

最新 PR run（30721029441）success；其前的 failure（30720928627）为 mirrors.env 生成文件链接问题，已由后续 commit 修复并复跑转绿。

### `git tag -l`

```
v1.6-accuracy
```

**v1.0.0 尚未创建**：打标签（v1.0.0）明确推迟到 PR #3 合并之后执行，避免在未合并分支上打发布标签。

## 结论

Phase A 全部验收项通过（tag 项为有意推迟，非失败）。Phase B 单独出计划。
