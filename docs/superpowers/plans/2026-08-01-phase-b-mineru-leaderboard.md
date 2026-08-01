# Phase B MinerU 移植与数据证据 Implementation Plan (2026-08-01)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 完成 `adapters/mineru/`(setup/verify/README/非CDM配置),用 ~80 页分层抽样门验证已有 1651 页 GPU 结果的可信度,产出多模型 Leaderboard 与 Strix Halo 平台证据页——全部数据可溯源。

**Architecture:** MinerU-ROCm(`C:\Users\rocm\Desktop\MinerU-ROCm`)作为外部依赖(`pip install -e --no-deps`),不入库;`adapters/mineru/` 只保留 shim + setup.ps1 + verify.ps1 + README。推理用独立 py3.12 conda 环境 `mineru-win-rocm`(ROCm torch cp312),评分用仓库 `.venv`(py3.11)。B2/B4 均设快速验证门:抽样一致→用现有产物;差异大→全量重跑。

**Tech Stack:** PowerShell、Python 3.12(推理 conda env)/ 3.11(评分 .venv)、mineru[pipeline]==3.4.4、onnxruntime-directml==1.24.4、torch 2.9.1+rocm7.2.1。

**Spec:** `docs/superpowers/specs/2026-08-01-open-source-quality-design.md`(Phase B 部分)

## Global Constraints

- PYTHONUTF8=1 贯穿推理与评分。
- 不修改 `eval-infra/**` 与 `scripts/**` 的现有逻辑(可新增 config/脚本)。
- 预测输出目录固定 `predictions\mineru_pipeline`(评分 config 已指向它)。
- `--platform windows-hip` 必须显式传递,不得从 OS 推断。
- 安装禁令:Windows 上**不得** `pip install "mineru[all]"`(会覆盖 ROCm torch);`onnxruntime-directml==1.24.4` 必须最后 `--force-reinstall --no-deps`。
- 数字铁律:任何文档中的指标数字必须可溯源到 `metric_result.json` / model card / 证据文档;MinerU 参考值 text 0.05655 / RO 0.15314 / TEDS 82.04 / CDM 83.39 / Overall 86.59。
- Conventional commits;feature 分支 `phase-b/mineru-adapter` + PR。
- 已确认事实:现有 `predictions\mineru_pipeline\` 1651 页(ok=1651 fail=0,torch 2.9.1+rocm7.2.1,DML active,slanet CPU override 511 runs);评分结果与 model card 逐字节一致;`adapters\mineru\run_adapter.py` shim 与 README 已存在(未跟踪);`v16-cdm-mineru-pipeline.yaml` 已存在(未跟踪)。

---

### Task B1: adapters/mineru 交付化

**Files:**
- Create: `adapters/mineru/setup.ps1`
- Create: `adapters/mineru/verify.ps1`
- Create: `adapters/mineru/.env.local.example`
- Modify: `adapters/mineru/README.md`(重构为模板 5 步结构)
- Create: `eval-infra/01-omnidocbench/configs/v16-mineru-pipeline.yaml`(非 CDM twin)

**Interfaces:**
- Produces: `setup.ps1`(幂等)、`verify.ps1`(exit 0/1)、`v16-mineru-pipeline.yaml` 供 B2/B3 评分命令使用。
- Consumes: `C:\Users\rocm\Desktop\MinerU-ROCm` 路径(来自 `.env.local` 的 `MINERU_ROCM_REPO`)。

- [ ] **Step 1: 写 `.env.local.example`**

```dotenv
# Copy to .env.local and fill in machine-local paths. .env.local is gitignored.
# Path to the MinerU-ROCm checkout (installed via pip install -e --no-deps).
MINERU_ROCM_REPO=C:\Users\rocm\Desktop\MinerU-ROCm
# Python 3.12 env with ROCm torch (inference only; scoring uses repo .venv).
MINERU_WIN_ROCM_PYTHON=C:\Users\rocm\miniconda3\envs\mineru-win-rocm\python.exe
```

- [ ] **Step 2: 写 `setup.ps1`(幂等;每一步自检后跳过)**

结构与命令(每步先检查后执行,已满足则打印 `SKIP`):

```powershell
#Requires -Version 5.1
param()
$ErrorActionPreference = 'Stop'
# 0. Load .env.local (fail with clear message if missing)
# 1. Check $env:MINERU_WIN_ROCM_PYTHON exists AND has torch with HIP:
#    & $py -c "import torch; assert torch.version.hip and torch.cuda.is_available()"
#    If missing: print the exact ROCm wheel install block (from MinerU-ROCm
#    docs/HANDOFF-windows-hip.md §2: 4 SDK packages + torch/torchaudio/torchvision
#    2.9.1+rocm7.2.1 cp312 wheels from https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/)
#    and exit 1 (SDK install needs human/UAC - AGENTS.md ⚠️3 pattern).
# 2. Check mineru==3.4.4 installed in that env; else:
#    & $py -m pip install "mineru[pipeline]==3.4.4"   # NEVER mineru[all]
# 3. Check mineru_rocm importable; else:
#    & $py -m pip install -e "$env:MINERU_ROCM_REPO" --no-deps
# 4. Check onnxruntime-directml==1.24.4 AND DmlExecutionProvider first; else LAST STEP:
#    & $py -m pip install --force-reinstall --no-deps "onnxruntime-directml==1.24.4"
# 5. Weights: check ~/mineru.json + models dir non-empty; else:
#    source mirrors.env HF_ENDPOINT if present, then
#    & $py -m mineru.cli.models_download -s huggingface -m pipeline   (prefetch, no lazy fetch)
# 6. Print SETUP OK + the two environment facts (torch HIP version, DML provider list).
```

- [ ] **Step 3: 写 `verify.ps1`(exit 0/1,带诊断)**

```powershell
# Checks (each prints PASS/FAIL + fix hint on FAIL, exit 1 if any FAIL):
# 1. .env.local present, MINERU_ROCM_REPO exists on disk
# 2. & $py -c torch HIP check (prints GPU name, expect Radeon 8060S or AMD)
# 3. & $py -c "import onnxruntime as ort; assert ort.get_available_providers()[0]=='DmlExecutionProvider'"
# 4. Weights dir present with layout/MFR/OCR model files (spot-check 3 filenames)
# 5. Smoke: run one dataset page through the adapter into a temp dir:
#    & $py adapters\mineru\run_adapter.py --backend pipeline --platform windows-hip `
#      --img-dir <one-page temp dir> --out-dir <temp out>
#    Copy eval-infra\01-omnidocbench\data\images\<first .png> into temp dir first.
#    Assert out .md exists and size > 100 bytes.
# End: VERIFY OK / exit code
```

- [ ] **Step 4: 运行 setup.ps1 + verify.ps1,记录真实输出**

Run: `powershell -ExecutionPolicy Bypass -File adapters\mineru\setup.ps1`
Expected: 各步 `SKIP`(环境已就绪),末尾 `SETUP OK` + torch `2.9.1+rocm7.2.1` + DML providers。

Run: `powershell -ExecutionPolicy Bypass -File adapters\mineru\verify.ps1`
Expected: 5 项 PASS + `VERIFY OK`,exit 0。smoke 页推理真实发生(GPU)。

- [ ] **Step 5: 写非 CDM 配置 `v16-mineru-pipeline.yaml`**

复制 `v16-cdm-mineru-pipeline.yaml`,删除/禁用 CDM metric 段(对照 `v16.yaml` 的 metric 列表),保持 prediction `data_path` 指向 `predictions/mineru_pipeline`,其余(dataset、match 参数)不变。

- [ ] **Step 6: 重构 `adapters/mineru/README.md` 为模板 5 步**

对照 `adapters/_template/README.md` 结构:① 复制方式(本 adapter 不可直接 cp,说明外部依赖)② run_adapter 契约与**强制参数** `--platform windows-hip` ③ setup.ps1 ④ 运行命令(**用 py3.12 env,不用 .venv**,含 PYTHONUTF8)⑤ 评分命令(两个 config)。加"环境与常见坑"小节:`mineru[all]` 禁令、DML 最后装、slanet-plus CPU override、推理/评分 Python 分离。

- [ ] **Step 7: 回归 + commit**

Run: `python -m pytest -q`
Expected: 全绿(新 config 会被 test_scoring_configs 覆盖——若 README/AGENTS 未引用则不影响)。

```bash
git add adapters/mineru/ eval-infra/01-omnidocbench/configs/v16-mineru-pipeline.yaml
git commit -m "feat: deliver MinerU adapter (setup/verify/README/non-CDM config)"
```

---

### Task B2: 80 页分层抽样验证门 + 现有结果验收

**Files:**
- Create: `scripts/sample_stratified.py`(抽样)
- Create: `scripts/compare_prediction_sets.py`(比对)
- Create: `eval-infra/01-omnidocbench/configs/v16-sample81.yaml` + `v16-sample81-mineru-repro.yaml`(样本集评分)
- Create: `docs/benchmarks/mineru-sample81-gate-2026-08-01.md`(门结论+证据)

**Interfaces:**
- Produces: 门结论(ACCEPT/REJECT)+ 证据文档;B3 依赖其 ACCEPT 结论引用 86.59 系列数字。

- [ ] **Step 1: 写 `scripts/sample_stratified.py`**

```python
"""Deterministic stratified sample of the OmniDocBench v1.6 image set.
Usage: python scripts/sample_stratified.py --img-dir <images> --per-category 9 --seed 42 --out <list.txt> [--copy-to <dir>]
Category = filename prefix up to the first '_' (book, newspaper, PPT, ...).
Sort each category's files, take every k-th (k = ceil(n/per_category)) after
seeding-offset; total ~81 pages. Prints category counts. No third-party deps.
"""
```

- [ ] **Step 2: 生成样本并核对分层**

Run: `python scripts/sample_stratified.py --img-dir eval-infra/01-omnidocbench/data/images --per-category 9 --seed 42 --out tmp_sample81.txt --copy-to tmp_sample81_images`
Expected: 输出各类别计数(≈9 类 × 9 = 81 页);类别数与数据集实际一致(记录真实输出)。

- [ ] **Step 3: 抽样集重新推理(GPU,py3.12 env)**

```powershell
$env:PYTHONUTF8 = "1"
C:\Users\rocm\miniconda3\envs\mineru-win-rocm\python.exe adapters\mineru\run_adapter.py `
  --backend pipeline --platform windows-hip `
  --img-dir tmp_sample81_images --out-dir predictions\mineru_sample81_repro
```
Expected: 81 个 .md;`_run_stats.json` ok=81 fail=0;耗时记录(进证据文档)。

- [ ] **Step 4: 写 `scripts/compare_prediction_sets.py` 并比对**

```python
"""Compare two prediction dirs page-by-page.
Outputs: exact-match rate, mean difflib.SequenceMatcher ratio, per-page
worst-10 divergences. Usage:
python scripts/compare_prediction_sets.py --a predictions/mineru_pipeline --b predictions/mineru_sample81_repro --stems tmp_sample81.txt
"""
```

Run 比对。Expected(门指标 A):exact-match ≥ 90% 或 mean ratio ≥ 0.98(推理在确定性配置下应高度一致;记录真实值)。

- [ ] **Step 5: 样本集双向评分(非 CDM,~分钟级)**

建两个样本 config(GT 不变,prediction 分别指向 `predictions/mineru_pipeline`(仅限样本 stems——用 `end2end_eval` 的页面过滤或将样本 GT/pred 拷入临时目录树)与 `predictions/mineru_sample81_repro`):

Run: `powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-sample81-mineru-repro.yaml`
Run: `powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-sample81.yaml`

Expected(门指标 B):两 config 的 text Edit-dist 差 ≤ 0.01、TEDS 差 ≤ 2 pp。

- [ ] **Step 6: 门判定 + 证据文档**

判定规则(写入文档并如实执行):
- ACCEPT = 门指标 A 与 B 均达标 → 采用现有 1651 页结果(86.59 系列),B2 完成。
- REJECT = 任一不达标 → 升级全量重跑(方案 B:删 predictions\mineru_pipeline 重推理+全量评分),并在文档记录触发原因。
文档:`docs/benchmarks/mineru-sample81-gate-2026-08-01.md`,含样本清单 hash、run_stats、比对数字、双向评分数字、门结论。

- [ ] **Step 7: (ACCEPT 路径)交叉核对 + 归档**

Run: 用 python 断言 `OmniDocBench\result\mineru_pipeline_quick_match_metric_result.json` 四指标 vs `MinerU-ROCm\model_card.pipeline.windows-hip.json` submetrics(容差 1e-6),输出 PASS/FAIL 表进证据文档。

- [ ] **Step 8: commit**

```bash
git add scripts/sample_stratified.py scripts/compare_prediction_sets.py eval-infra/01-omnidocbench/configs/v16-sample81*.yaml docs/benchmarks/mineru-sample81-gate-2026-08-01.md
git commit -m "test: add stratified-sample gate validating existing MinerU 1651-page results"
```

---

### Task B3: 多模型对比 Leaderboard

**Files:**
- Modify: `README.md` + `README.zh-CN.md`(新"Multi-model leaderboard"章节)
- Create: `docs/benchmarks/leaderboard-evidence-2026-08-01.md`(每格溯源)

**Interfaces:**
- Consumes: B2 门 ACCEPT 结论;PaddleOCR 两列数字(README 现有:paper 列 + ROCm measured 列);MinerU model card 值。
- Produces: README 表格 + 证据文档。

- [ ] **Step 1: 汇编证据文档**

`docs/benchmarks/leaderboard-evidence-2026-08-01.md`:每个数字一行,含来源文件路径与关键 JSON 键:
- PaddleOCR-VL-ROCm:Overall 95.99 / text 0.03488 / RO 0.12882 / TEDS 94.09 / CDM 97.36 ← `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md`
- PaddleOCR official(本地实测):CDM 96.5022 等 ← `docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md` 的 metric_result
- MinerU pipeline(GPU):Overall 86.59 / text 0.05655 / RO 0.15314 / TEDS 82.04 / CDM 83.39 ← `model_card.pipeline.windows-hip.json` + 本仓库 `result\mineru_pipeline_quick_match_metric_result.json` + B2 门文档
每行用脚本(grep/python 断言)复核真实值,输出贴进文档。

- [ ] **Step 2: README 双语加 Leaderboard 章节**

表格(注明口径:页面级聚合,与 OmniDocBench 官方 notebook 一致;MinerU 行为快速匹配 CDM):

```markdown
| Model | Overall | Text Edit-dist ↓ | RO Edit-dist ↓ | Table TEDS ↑ | Formula CDM ↑ |
|---|---:|---:|---:|---:|---:|
| PaddleOCR-VL-ROCm (reference) | 95.99 | 0.03488 | 0.12882 | 94.09 | 97.36 |
| PaddleOCR-VL (paper, Linux vLLM) | 96.33 | 0.033 | 0.127 | 94.76 | 97.49 |
| MinerU 3.4.4 pipeline (Windows HIP) | 86.59 | 0.05655 | 0.15314 | 82.04 | 83.39 |
```

表下注明:每格溯源见 `docs/benchmarks/leaderboard-evidence-2026-08-01.md`;MinerU 数值经 81 页分层抽样门验证(链接 B2 文档)。

- [ ] **Step 3: 守卫测试通过 + commit**

Run: `python -m pytest tests/test_readme_consistency.py tests/test_markdown_links.py -q`
Expected: 全过(双语表格数字一致——这是 test_metric_tables_match_between_languages 强制;若新表行关键词触发比对,确保双语逐格相同)。

```bash
git commit -am "docs: add multi-model leaderboard with per-cell evidence"
```

---

### Task B4: Strix Halo 平台证据页

**Files:**
- Create: `docs/benchmarks/strix-halo-ai-max395.md`
- Modify: `README.md` + `README.zh-CN.md` System Requirements 表(一行实测锚点)

**Interfaces:**
- Consumes: B2/B3 证据;现有 `benchmark-results/`、`predictions/mineru_pipeline/_run_stats.json`、G4 加速比文档。
- Produces: 平台证据页。

- [ ] **Step 1: 快速验证现有产物是否足够(用户决策门)**

检查并记录:① `benchmark-results/` 下最近一次报告内容(monitor 数据:GPU/显存/CPU 时间序列?)② `predictions/mineru_pipeline/_run_stats.json` 的起止时间 → MinerU 1651 页 wall-clock ③ PaddleOCR 全量推理耗时(现有 release 文档/benchmark-results)④ G4 1.7x 证据文件。
判定:四类数据齐全且可读 → 方案 A(汇编);任一缺失 → 对该项执行最小化新采集(如重跑 04-benchmark monitor 短采样),不得编造。

- [ ] **Step 2: 写证据页**

`docs/benchmarks/strix-halo-ai-max395.md`:平台(AI MAX+ 395 / Radeon 8060S / 128GB 统一内存 / ROCm 7.2.1 HIP 7.2.53211)、分阶段 wall-clock 表(数据集下载/CDM 环境/各模型推理/评分)、资源占用要点、G4 加速比复测引用。每个数字标注来源文件。

- [ ] **Step 3: README 锚点行 + 守卫测试 + commit**

System Requirements 表下加一行:"AI MAX+ 395 + 128GB 实测全链路数据见 `docs/benchmarks/strix-halo-ai-max395.md`"(双语)。

Run: `python -m pytest -q`(全绿)
```bash
git commit -am "docs: add Strix Halo platform evidence page with measured timings"
```

---

### Task B5: Phase B 验收汇总 + PR

**Files:**
- Create: `docs/phase-b-verification-2026-08-01.md`

- [ ] **Step 1: 汇总验收**

表:verify.ps1 exit 0 输出、抽样门结论+数字、四指标交叉核对 PASS、Leaderboard 每格溯源 OK、pytest 全绿、CI(PR)绿。

- [ ] **Step 2: push + PR + CI 绿 + 最终评审**

```bash
git push -u origin phase-b/mineru-adapter
gh pr create --title "Phase B: MinerU adapter + multi-model leaderboard + Strix Halo evidence" --body "See docs/superpowers/plans/2026-08-01-phase-b-mineru-leaderboard.md"
gh run watch
```
最终 whole-branch review(subagent-driven 流程),修复发现后合并。

---

## Self-Review 结论

- Spec 覆盖:B1→Task B1,B2→Task B2(抽样门为用户批准的验收方式),B3→Task B3,B4→Task B4(快速验证门同用户决策),验收汇总→Task B5。
- 抽样门判定规则量化(exact-match ≥90% 或 ratio ≥0.98;text diff ≤0.01;TEDS diff ≤2pp),无歧义。
- 用户铁律落实:所有 README/证据页数字必须经脚本复核真实值并贴输出。
