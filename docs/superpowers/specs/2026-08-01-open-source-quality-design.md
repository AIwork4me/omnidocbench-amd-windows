# 顶级开源品质提升设计(2026-08-01)

## 1. 目标与成功标准

把 `omnidocbench-amd-windows` 打造成有评测数据支撑、易学易用的顶级开源项目,
目标用户:**Windows + AMD RYZEN AI MAX+ 395 / Radeon 8060S / 128GB 共享内存**
笔记本平台用户,目标是轻松搭建 OmniDocBench v1.6 评测平台并完成文档解析模型评测。

铁律:**所有优化必须有核验,不能空口胡说,必须实做、有数据、有证据。**
每个交付物带退出码 / pytest 输出 / 真实分数作为验收,不写无证据声明。

## 2. 审计发现(2026-08-01,均有证据)

| # | 问题 | 证据 |
|---|---|---|
| 1 | 工作区混杂 ~1 GB 未跟踪二进制 | `git status`: `llama-b9892-bin-win-hip-radeon-x64.zip/`、`llama.cpp-b9892-src/`、`tmp/`、`cdm_debug.py`、`cdm_diag.py`、`tmp_cdm-*.txt`、`adapters/mineru/` |
| 2 | 本地 git 对象库 419 MiB,含 323 MB 不可达 blob(llama zip 曾被 commit 后删除) | `git verify-pack`: blob `42eaa135` = 323,256,489 bytes(含 `ggml-base.dll` 的 zip) |
| 3 | 远端仓库干净(1.3 MB),问题仅在本地 | GitHub API: `size_KB: 1301` |
| 4 | 无 CI:`.github/` 只有 issue 模板;README "Out of scope" 明确排除 CI,与顶级品质目标冲突 | `.github/` 列表、README.md:271-274 |
| 5 | `adapters/mineru/` 半成品且未跟踪 | `git status` 未跟踪;仅有 `v16-cdm-mineru-pipeline.yaml`,无非 CDM 配置 |
| 6 | 测试仅 6 个文件,无 lint/typecheck 配置,无 CI 守护 | `git ls-files`: tests/ 4 个 + 04-benchmark/tests/ 2 个 |
| 7 | 平台定位漂移:README 泛写 "AMD Radeon",缺 AI MAX+ 395 专属实测锚点 | README.md:36 |
| 8 | README EN/ZH 指标表历史不一致,需逐格核对现状 | git log 07b24fd/4dd869c 修过,未验证 |

优势(保留):AGENTS.md 编排层、症状索引 pitfalls.md、幂等 setup/verify、
分数证据链(release notes、verification docs)。

## 3. 方案选择

用户已批准**方案 1:双轨两期,全部本机实测验收**(Phase A 工程品质先行,
Phase B 能力与数据随后)。否决:方案 2 骨架大重构(破坏 AGENTS.md 编排,
风险高收益低);方案 3 最小修复(达不到目标)。

## 4. Phase A 设计 — 工程品质与开箱体验

原则:**不动任何 setup/verify 脚本逻辑(除非 lint 报错),不改变用户体验路径,风险低。**

### A1 仓库卫生
- 移出仓库:`llama-b9892-bin-win-hip-radeon-x64/`、`llama.cpp-b9892-src/`
  → `C:\AIwork\tools\`(仓库外)。
- 删除(可再生):`llama-b9892-bin-win-hip-radeon-x64.zip`、`tmp_cdm-*.txt`、
  `tmp/`、`cdm_debug.py`、`cdm_diag.py`(删除前确认诊断逻辑已存在于
  `eval-infra/03-scoring/formula_cdm_diagnostics.py`;若根目录版本有独有逻辑,
  先合并再删)。
- `.gitignore` 增补:`llama-*`、`tmp*/`、`cdm_*.py`、`*.zip` 等模式。
- `git gc --prune=now` 清除 419 MiB 不可达对象。
- **验收**:`git count-objects -vH` size-pack 从 419 MiB 降到 <5 MiB;
  `git status` 干净(除 `adapters/mineru/`,它在 B1 处理)。

### A2 CI(`.github/workflows/ci.yml`)
- Job 1 `pytest`: windows-latest,Python 3.10/3.11 矩阵,跑 `tests/` +
  `eval-infra/04-benchmark/tests/`。
- Job 2 `PSScriptAnalyzer`: 所有 `*.ps1` lint,Error 级即失败。
- Job 3 `markdown-links`: 检查 README/docs 内相对链接有效性。
- README 加 CI badge。
- **验收**:推送分支后 CI 全绿(链接存档);本地 `Invoke-ScriptAnalyzer` 0 Error。

### A3 测试扩展
- 新增:`scripts/full-verify.ps1` 参数解析 smoke test;`score.ps1` 配置路径
  校验测试;`run_adapter.py` 契约测试(mock server,不依赖 GPU)。
- **验收**:本地 `python -m pytest` 全绿,输出存档 `docs/`。

### A4 文档一致性与版本化
- 逐格核对 README EN/ZH 指标表(脚本化 grep 数字交叉比对)。
- 核对 AGENTS.md 与 README 命令一致性(setup.sh 存在性、verify-windows.ps1 位置)。
- 新建 `CHANGELOG.md`(Keep a Changelog),回填 2026-07-09 / 07-11 / 07-16
  三个 release;打 git tag `v1.0.0`。
- **验收**:交叉比对脚本输出零差异报告。

### A5 CONTRIBUTING 补强
- 实读现有文件,补 PR 流程、conventional commits 规范(现 git log 已是)、
  本地验证清单(pytest + PSScriptAnalyzer)。
- **验收**:文档评审 + CI 强制 lint 链接。

## 5. Phase B 设计 — 评测能力与数据证据

依赖:Phase A 全部完成并提交后启动。B1→B2 先行(全量推理+评分数小时,可后台),
B3/B4 依赖 B2 数据。

### B1 完成 `adapters/mineru/`(以已验证的 MinerU-ROCm 为基座移植)
- **基座**:`C:\Users\rocm\Desktop\MinerU-ROCm` 是本机 GPU 上已成功运行的方案,
  含 `adapter/run_adapter.py`、`adapter/setup` 与完整评测产物
  (`model_card.pipeline.windows-hip.json`:2026-07-23 实测 Overall 86.59、
  text_edit_dist 0.05655、TEDS 82.04、CDM 83.39、RO 0.15314,硬件即
  AI MAX+ 395 / Radeon 8060S,后端 ROCm PyTorch + ONNX Runtime DirectML)。
  B1 是**移植适配**,不是从零开发。
- 对照 `adapters/_template` 契约(`run_adapter(img_dir, out_dir, server_url)`
  + `out_dir/<stem>.md`)把 MinerU-ROCm adapter 收敛进本仓库 `adapters/mineru/`。
- 补 `setup.ps1`(权重下载,幂等)+ `verify.ps1`。
- 补非 CDM 评分配置(现有仅 `v16-cdm-mineru-pipeline.yaml`,不对称)。
- **验收**:模板 README 五步可执行;`verify.ps1` exit 0。

### B2 MinerU 全量复测(本机 AI MAX+ 395,1651 页,GPU 路径已验证)
- 在本仓库评分管线(harness)下全量推理 + 四项指标评分,保证与
  PaddleOCR-VL 数字同口径可比。
- 与 MinerU-ROCm 2026-07-23 model card 数字交叉核对;偏差须在文档中解释
  (评分口径、quick_match 等),不接受无解释偏差。
- **验收**:`predictions/mineru/` 1651 个 .md;
  `eval-infra/03-scoring/verify.ps1` exit 0;四指标真实数字 + 与 model card
  的核对结论写入 `docs/benchmarks/`。

### B3 多模型对比 Leaderboard(README 新章节)
- 表:PaddleOCR-VL-ROCm / PaddleOCR official / MinerU(pipeline, GPU)× 四指标
  + 推理耗时 + 显存峰值。
- 每格数字链接到证据(release doc / metric_result.json 存档于 `docs/benchmarks/`);
  MinerU 列同时引用 MinerU-ROCm 的 windows-hip model card 作为外部佐证。
- **验收**:表格每格可溯源。

### B4 Strix Halo 平台证据页
- `docs/benchmarks/strix-halo-ai-max395.md`:分阶段 wall-clock、GPU/显存占用
  (复用 `eval-infra/04-benchmark/monitor.py`)、G4 加速比复测。
- README "System Requirements" 加实测锚点行:"AI MAX+ 395 + 128GB 实测全链路 X 小时"。
- **验收**:`eval-infra/04-benchmark/run.ps1` 报告入库,数据可复算。

## 6. 不做的事(YAGNI)

- 不重排目录骨架(src/ 布局、MkDocs 文档站)。
- 不改 setup/verify 脚本逻辑、不改 AGENTS.md 编排结构(除 A4 的命令一致性修正)。
- 不做 GPU CI runner(自托管 runner 脆弱;GPU 验证保留本地 full-verify.ps1)。
- 不支持非 AMD 平台(adapter 模板已够,社区贡献)。

## 7. 验收总表

| 交付物 | 验收命令/证据 |
|---|---|
| A1 仓库卫生 | `git count-objects -vH` <5 MiB;`git status` 干净 |
| A2 CI | CI 全绿链接;本地 PSScriptAnalyzer 0 Error |
| A3 测试 | `python -m pytest` 全绿输出存档 |
| A4 文档一致性 | 交叉比对零差异报告;CHANGELOG.md;tag v1.0.0 |
| A5 CONTRIBUTING | 评审通过 |
| B1 MinerU adapter | `verify.ps1` exit 0 |
| B2 MinerU 实测 | 1651 预测 + verify exit 0 + 四指标数字 |
| B3 Leaderboard | 每格可溯源 |
| B4 平台证据页 | benchmark 报告入库可复算 |
