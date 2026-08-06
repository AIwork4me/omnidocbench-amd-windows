# OmniDocBench AMD Windows

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform: AMD ROCm](https://img.shields.io/badge/Platform-AMD_ROCm_HIP-red.svg)](https://github.com/issues?q=omnidocbench+amd)
[![OmniDocBench v1.6](https://img.shields.io/badge/OmniDocBench-v1.6-00C853.svg)](https://github.com/opendatalab/OmniDocBench)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/AIwork4me/omnidocbench-amd-windows)](https://github.com/AIwork4me/omnidocbench-amd-windows)
[![ci](https://github.com/AIwork4me/omnidocbench-amd-windows/actions/workflows/ci.yml/badge.svg)](https://github.com/AIwork4me/omnidocbench-amd-windows/actions/workflows/ci.yml)

[English](README.md) · [架构图](docs/architecture.md) · [踩坑知识库](docs/pitfalls.md) · [AGENTS.md](AGENTS.md) · [治理](GOVERNANCE.md) · [发布](RELEASE.md)

> **我们踩了 20+ 个坑才跑通 OmniDocBench CDM。这个 repo 把它们压缩成一条命令。**

**一个统一入口**在 **Windows + AMD Radeon GPU** 上搭建 [OmniDocBench](https://github.com/opendatalab/OmniDocBench) v1.6 全量评测系统
（1651 页，四项标准指标：文本 / 阅读顺序 / 表格 TEDS / **公式 CDM**），并提供完整证据包。
“一条命令”指统一编排器（`scripts\reproduce.ps1`）；首次运行仍可能需要下载、UAC/驱动提示、
WSL 或重启等人机协作步骤（见 [AGENTS.md](AGENTS.md) 的 ⚠️ 门），绝不假装完全无人值守。

**当前可信能力：** 评分与适配器输出契约与模型无关；PaddleOCR-VL-1.6 在 Radeon 8060S（gfx1151）
上是已验证的单命令参考 profile，全量结果标注为 **validated resumed**（尚未 clean-room）；
**MinerU 使用文档化的适配器工作流**，带独立的人工介入门（Python 3.12 + ROCm torch）。
参见 [`docs/hardware-support.md`](docs/hardware-support.md) 与下方[证据等级](#measured-results)。

![OmniDocBench AMD Windows 概览](overview.jpg)

<!-- benchmark-table:start -->
| Model | Backend | Run | Coverage | Text Edit-dist ↓ | Reading-order Edit-dist ↓ | Table TEDS ↑ | Formula CDM ↑ | Evidence |
|---|---|---|---:|---:|---:|---:|---:|---|
| PaddleOCR-VL-1.6 1.6 | llama.cpp GGUF (ROCm/HIP) | validated resumed | 0.9988 | 0.0353 | 0.1293 | 92.9792 | 96.5605 | [docs/reproduction-full1651-hip-2026-08-06.md](docs/reproduction-full1651-hip-2026-08-06.md) |
| PaddleOCR-VL-1.6 1.6 | llama.cpp GGUF (ROCm/HIP) | validated resumed | 0.9988 | 0.0354 | 0.1295 | 92.9766 | 96.6490 | [docs/reproduction-full1651-hip-2026-08-03.md](docs/reproduction-full1651-hip-2026-08-03.md) |
| PaddleOCR-VL-1.6 1.6 | llama.cpp GGUF (ROCm/HIP) | smoke | 1.0000 | 0.0143 | — | 100.0000 | 99.3280 | [docs/reproduction-hip-smoke-2026-08-02.md](docs/reproduction-hip-smoke-2026-08-02.md) |
| MinerU2.5-Pro-2605-1.2B 2605-1.2B | llama.cpp GGUF (HIP) | validated resumed | — | 0.0373 | 0.1225 | 93.1100 | 97.0100 | [docs/benchmarks/leaderboard-evidence-2026-08-01.md](docs/benchmarks/leaderboard-evidence-2026-08-01.md) |
| MinerU 3.4.4 3.4.4 | ROCm PyTorch + ONNX DirectML | validated resumed | — | 0.0566 | 0.1531 | 82.0400 | 83.3900 | [docs/benchmarks/mineru-sample81-gate-2026-08-01.md](docs/benchmarks/mineru-sample81-gate-2026-08-01.md) |
| PaddleOCR-VL-1.6 1.6 | llama.cpp GGUF (ROCm/HIP) | validated resumed | 0.9988 | 0.0349 | 0.1288 | 94.0900 | 97.3600 | [docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md](docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md) |
| PaddleOCR-VL-1.6 1.6 | llama.cpp GGUF (ROCm/HIP) | validated resumed | 0.9988 | 0.0340 | 0.1282 | 94.3222 | 96.9219 | [docs/windows-native-cdm-verification-2026-07-11.md](docs/windows-native-cdm-verification-2026-07-11.md) |
| PaddleOCR-VL-1.6 1.6 | llama.cpp GGUF (ROCm/HIP), official doc_parser engine | validated resumed | 0.9988 | 0.0344 | 0.1295 | 94.2393 | 96.5022 | [docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md](docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md) |
<!-- benchmark-table:end -->

## 本机实测结果

| 模型 | 后端（本机） | Overall | 文本 Edit-dist ↓ | 阅读顺序 Edit-dist ↓ | 表格 TEDS ↑ | 公式 CDM ↑ |
|---|---|---:|---:|---:|---:|---:|
| PaddleOCR-VL-1.6 | llama.cpp GGUF (ROCm/HIP) | **95.99** | 0.03488 | 0.12882 | **94.09** | **97.36** |
| MinerU2.5-Pro-2605-1.2B | llama.cpp GGUF (HIP) | 95.46 | 0.03734 | **0.12250** | 93.11 | 97.01 |
| MinerU 3.4.4 pipeline | ROCm PyTorch + ONNX DirectML | 86.59 | 0.05655 | 0.15314 | 82.04 | 83.39 |

所有行均为本机（AI MAX+ 395 / Radeon 8060S）1651 页全量实测结果；页面级聚合口径与
OmniDocBench 官方 notebook 一致；MinerU 行使用快速匹配（quick-match）CDM。每格溯源见
[`docs/benchmarks/leaderboard-evidence-2026-08-01.md`](docs/benchmarks/leaderboard-evidence-2026-08-01.md)。
MinerU pipeline 数值经 130 页分层抽样门验证
（[`docs/benchmarks/mineru-sample81-gate-2026-08-01.md`](docs/benchmarks/mineru-sample81-gate-2026-08-01.md)，
verdict ACCEPT）；MinerU2.5 数值与 MinerU-ROCm windows-hip 模型卡交叉核对（容差 1e-6）。
PaddleOCR-VL 官方引擎对比（official-local Formula CDM `96.5022`；1 个稳定 VLM-500 页面已在上游记录为
[PaddleOCR issue #18248](https://github.com/PaddlePaddle/PaddleOCR/issues/18248)）：见证据文档。

> **复现阈值：** 文本 Edit-dist < 0.10、阅读顺序 < 0.20、TEDS > 85、CDM > 85
> （原始 `metric_result.json` 中 TEDS/CDM 对应 `> 0.85`）。
> **G4 推理加速比 1.7x**（27 页分层抽样，9 类别、0 结构错配）——PaddleOCR-VL-ROCm 默认
> `vlm_max_workers=8` 即可获得此加速。Overall = (文本准确率 + CDM + TEDS) / 3，
> 其中文本准确率 = (1 − Edit_dist) × 100。阅读顺序不纳入 Overall（布局指标，非内容准确率）。

## 系统需求

| 组件 | 最低 | 推荐 |
|---|---|---|
| 操作系统 | Windows 11（WSL2） | 同左 |
| GPU | 支持 ROCm/HIP 的 AMD Radeon | Radeon 8060S / RX 7900 XT+ |
| GPU 显存 | 2 GB（版面 ONNX）+ VLM 模型体积（~1.7 GB GGUF + ctx/mmproj） | 8 GB+ |
| 内存 | 16 GB | 32 GB+ |
| 磁盘 | ~50 GB（数据集 ~3 GB + GGUF 1.7 GB + TeX Live ~5 GB + IM7 + WSL rootfs） | 100 GB SSD |
| CPU 核数 | 4（TEDS/CDM 的 worker 数随核数扩展） | 8+ |
| WSL | Ubuntu 22.04（rootfs 导入或商店安装） | 同左 |
| Python | 3.10 或 3.11（**不可** 3.12/3.13——OmniDocBench 会报错） | 3.11 |
| Python 环境 | [uv](https://docs.astral.sh/uv/) | 最新稳定版 |
| PowerShell | Windows PowerShell 5.1（自带）或 PowerShell 7+ | 同左 |

全量 1651 页运行的时间估算：步骤 1（数据集下载）较慢网络下约 15-20 分钟；步骤 2（CDM 环境）约 30 分钟（TeX Live 是大头）；步骤 3（适配器推理）取决于 GPU（CPU 数小时，Radeon HIP 数十分钟）；步骤 4（评分）约 5 分钟（Edit_dist+TEDS）+ 20-30 分钟（CDM，每条公式都要跑 LaTeX）。

参考机型（Ryzen AI MAX+ 395 + Radeon 8060S + 128 GB 统一内存）的实测全链路耗时与资源占用数据见
[`docs/benchmarks/strix-halo-ai-max395.md`](docs/benchmarks/strix-halo-ai-max395.md)。

<details>
<summary><strong>较弱机型已验核结果（Radeon 860M,200 页 CPU 运行）</strong></summary>

<br>

2026-07-26，一台 Ryzen AI 7 PRO 350 / Radeon 860M 机器完成了严格固定的
200 页 CPU fallback 运行。这是本机能力证据，**不是** 1651 页 leaderboard
全量结果。

| 指标 | 已验核 200 页结果 |
|---|---:|
| Overall（官方 notebook 聚合） | **96.6362** |
| 文本 Edit-distance | **0.02446** |
| 阅读顺序 Edit-distance | **0.11668** |
| 表格 TEDS | **96.2597** |
| 公式 CDM | **96.0949** |

确定性单 worker 评分后，Windows 与 WSL 的共同指标完全一致；CDM/TEDS 的
timeout、error、exception 均为 0。完整命令、分母、raw 值、限制与 hash 见
[`docs/reproduction-cpu-200-2026-07-26.md`](docs/reproduction-cpu-200-2026-07-26.md)。

Radeon 860M（gfx1152）无法运行本次测试的官方 Windows HIP llama.cpp：
b9637 与 b10107 都报 `ROCm error: invalid device function`。此类 GPU 应使用
`-Variant cpu`，除非已有兼容 gfx1152 的构建，因此本次已验核运行被迫回退到
CPU。该 Windows HIP 打包缺口已提交至上游
[`ggml-org/llama.cpp#26127`](https://github.com/ggml-org/llama.cpp/issues/26127)；
本地复现细节见
[`docs/llama-cpp-radeon-860m-gfx1152-issue-draft-2026-07-26.md`](docs/llama-cpp-radeon-860m-gfx1152-issue-draft-2026-07-26.md)。

</details>

## 快速开始

克隆后按需选择三个正式 reproduction profile 之一。每个 profile 都是声明式
定义（名称、后端、页数、预测目录、manifest、评分配置、save name、端口、
覆盖率与失败页预算、指标阈值），放在 `scripts/profiles/` 下；
`reproduce.ps1` 是通用的 profile 驱动编排器，路径与阶段不会按 profile
复制三份。

```bash
git clone https://github.com/AIwork4me/omnidocbench-amd-windows
cd omnidocbench-amd-windows
```

### 快速环境验证（CPU）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile cpu-smoke-10
```

固定 10 页 CPU 推理、Windows Edit-distance/TEDS 加 WSL CDM、100% 预测覆盖，
可恢复证据写到 `outputs/reproduction/cpu-smoke-10/`。这是能力 smoke test，
不是 leaderboard 结果。

### 快速 AMD GPU 验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile hip-smoke-10
```

固定 10 页 HIP llama.cpp 推理，并自动执行**后端证明**：variant 标记、HIP
二进制证据、锁定 tag、GPU offload 与 HIP/ROCm 日志证据。禁止 CPU 回退：
证明或 preflight 失败则 profile 失败。含 Windows 指标和 WSL CDM、100% 预测
覆盖。在开始数小时全量任务前先跑它。

### AMD GPU 全量 1651 页评测

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile paddleocr-vl-hip-full-1651
```

正式全量评测：PaddleOCR-VL-1.6 lightweight 管线、锁定的 OmniDocBench v1.6
数据集（恰好 1651 页）、HIP 后端并带后端证明、全部四项标准指标（文本
Edit-distance、阅读顺序 Edit-distance、表格 TEDS、公式 CDM）、强制的 WSL
CDM、严格验收（覆盖率 ≥99.8%、失败页 ≤2、manifest/stats/结果一一绑定）以及
完整证据包（`outputs/reproduction/paddleocr-vl-hip-full-1651/`）。

**全量命令可能运行数小时。** WSL CDM 仍是默认参考路径。HIP 支持取决于锁定
二进制是否覆盖你的 GPU 架构——Radeon 860M/gfx1152 当前**不是**受支持的锁定
HIP 路径（该机型请用 `-Variant cpu`，见上方 Radeon 860M 说明）。smoke 结果
不能作为 leaderboard 成绩；full 结果必须满足严格证据门槛（见
[`docs/architecture.md`](docs/architecture.md#reproduction-profiles)）。

已在 Ryzen AI MAX+ 395 / Radeon 8060S 实体机验证（2026-08-03）：全量
Profile 官方通过——1651 页选中、1649/1651 可用（0.9988）、2 个预算内的
peg-native 失败页（上游追踪
[PaddlePaddle/PaddleOCR#18248](https://github.com/PaddlePaddle/PaddleOCR/issues/18248)）、
数据集中真正的空 GT 页接受空预测；分数：text 0.035386 / 阅读顺序 0.129539 /
TEDS 0.929766（Windows），CDM 0.966490（WSL）。完整记录：
[`docs/reproduction-full1651-hip-2026-08-03.md`](docs/reproduction-full1651-hip-2026-08-03.md)。

`-Resume` 仅用于中断后：它会重新校验输入 fingerprint（profile、锁、
manifest、评分配置、pipeline commit、仓库状态），并用 `--skip-existing`
逐页续跑，已完成的页面绝不重新处理。首次运行拒绝已存在的该 profile 产物；
需要替换旧预测时用 `-ForceInference`，它只删除本 profile 的预测、自有
manifest 和以 save name 为前缀的结果文件。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -ListProfiles
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -Profile cpu-smoke-10 -DryRun
```

可执行输入锁见 [`docs/upstream-lock.md`](docs/upstream-lock.md)。

如果另一 checkout 已有锁定的 dataset/GGUF/layout，可避免重复 bulk 下载，
同时保持推理和评分为本次新生成：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 `
  -Profile cpu-smoke-10 `
  -SeedFrom "C:\path\to\existing\locked-checkout" `
  -SkipCdmSetup
```

seed 的 source 与 destination 都会完整执行 lock 校验；预测、分数、环境、
checkout 和 `.env.local` 均不会复制。

<details>
<summary><strong>手工分阶段搭建</strong></summary>

<br>

每个 `setup.*` 都是幂等的；之后跑对应的 `verify.*`。**所有命令都假定在 repo
根目录执行。**

```powershell
# 步骤 0：可复现的本地 Python + 网络 + WSL
winget install --id astral-sh.uv -e
uv python install 3.11
uv sync --locked --all-groups
powershell -ExecutionPolicy Bypass -File scripts\detect-mirrors.ps1
powershell -ExecutionPolicy Bypass -File scripts\wsl-ensure.ps1
# 官方 Windows HIP 二进制不含 Radeon 860M/gfx1152，因此该机型自动选 CPU。
$gpuNames = @(Get-CimInstance Win32_VideoController | ForEach-Object Name)
$useCpu = ($gpuNames -match 'Radeon.*860M') -or -not ($gpuNames -match 'AMD|Radeon')
$variant = if ($useCpu) { 'cpu' } else { 'hip' }
powershell -ExecutionPolicy Bypass -File scripts\preflight.ps1 -CdmPath Wsl -Variant $variant
$repoWsl = (wsl -d Ubuntu2204 -- wslpath -a $PWD.Path).Trim()

# 步骤 1：OmniDocBench 代码 + 数据集
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1

# 步骤 2：CDM 环境（WSL 兼容/参考路径）
wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/02-cdm-environment/setup.sh"
wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/02-cdm-environment/verify.sh"

# 步骤 3：参考适配器（PaddleOCR-VL-1.6）
# CPU 用户可改用下方 200 页路径，避免直接执行 1651 页全量推理。
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant $variant
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\verify.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1
.\.venv\Scripts\python.exe adapters\paddleocr-vl-1.6\run_adapter.py `
    --img-dir  eval-infra\01-omnidocbench\data\images `
    --out-dir  predictions\paddleocrvl_rocm

# 步骤 4：评分 + 最终验证
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 `
  -WindowsOnly -SaveName paddleocrvl_rocm_quick_match
wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/03-scoring/score-cdm.sh" v16-cdm.yaml predictions/paddleocrvl_rocm
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1 `
  -WslOnly -RequireCdm -SaveName paddleocrvl_rocm_quick_match
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 `
  -PredictionDir predictions\paddleocrvl_rocm `
  -ScoreSaveName paddleocrvl_rocm_quick_match
```

</details>

<details>
<summary><strong>受限硬件 200 页路径</strong></summary>

<br>

受限硬件可使用 `v16-cpu-200.yaml` 与 `v16-cdm-cpu-200.yaml` 的显式 200 页
能力路径。用它替代全量步骤 3 推理，启动 CPU server，并确定性地在 200 张图
后停止：

```powershell
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant cpu
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\verify.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\verify.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1
.\.venv\Scripts\python.exe adapters\paddleocr-vl-1.6\run_adapter.py `
    --img-dir eval-infra\01-omnidocbench\data\images `
    --out-dir predictions\paddleocrvl_cpu_860m_200 `
    --max-pages 200
.\.venv\Scripts\python.exe scripts\build_prediction_subset.py `
    --full-manifest eval-infra\01-omnidocbench\data\OmniDocBench.json `
    --pred-dir predictions\paddleocrvl_cpu_860m_200 `
    --output eval-infra\01-omnidocbench\data\OmniDocBench_cpu_200.json `
    --limit 200
.\.venv\Scripts\python.exe scripts\validate_predictions.py `
    --manifest eval-infra\01-omnidocbench\data\OmniDocBench_cpu_200.json `
    --pred-dir predictions\paddleocrvl_cpu_860m_200 `
    --min-coverage 1.0
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 `
  -Config v16-cpu-200.yaml
```

WSL CDM 使用同一预测目录与 CDM 配置，最终验证显式绑定到本次产物：

```powershell
wsl -d Ubuntu2204 bash "$repoWsl/eval-infra/03-scoring/score-cdm.sh" `
  v16-cdm-cpu-200.yaml `
  predictions/paddleocrvl_cpu_860m_200
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1 `
  -PredictionDir predictions\paddleocrvl_cpu_860m_200 `
  -PredictionManifest eval-infra\01-omnidocbench\data\OmniDocBench_cpu_200.json `
  -ScoreSaveName paddleocrvl_cpu_860m_200_quick_match
```

不得把该子集分数标记为 1651 页全量分数。已验证命令、证据哈希与限制见
[`docs/reproduction-cpu-200-2026-07-26.md`](docs/reproduction-cpu-200-2026-07-26.md)。

10 页 smoke 使用 `v16-cpu-smoke-10.yaml` 与
`v16-cdm-cpu-smoke-10.yaml`；请使用上方单入口，不要手工拼接这些命令。

</details>

Windows 原生 CDM 已受支持：`eval-infra/01-omnidocbench/setup.ps1` 会自动应用
`patches/omnidocbench/windows-cdm.patch`，并由
`eval-infra/02-cdm-environment/verify-windows.ps1` 验证。这是可选路径，需要本机
TeX Live、ImageMagick 和 Ghostscript。WSL CDM 仍保留为兼容和 reference 路径；
选择 WSL 的用户无需进行原生 CDM 验证。
`scripts/full-verify.ps1` 只有在显式传入 `-WindowsCdm` 时才检查原生路径。
可选的原生 CDM 验证独立于 WSL 快速开始路径。

想用 agent 驱动？把 **Codex、Claude Code、OpenCode，或任何能读 `AGENTS.md` 的 agent** 指向本 repo，说"按 AGENTS.md 搭建" / "Read AGENTS.md and execute the setup flow."。完整分步流程（含异常处理）见 [`AGENTS.md`](AGENTS.md)。

---

## 这个 repo 为什么存在

在 AMD Windows 上跑通 OmniDocBench v1.6 会踩 20+ 个坑：网络受限需寻找可用镜像、WSL 商店不可达、`\mathcolor` 渲染成黑色、ImageMagick 6 把彩色公式渲染成灰度、两个 TeX Live 树互相打架、Windows 代码页把 CJK 的 JSON 弄乱，等等。本 repo 把每个修复都固化成**幂等脚本** + **按症状索引的知识库** + **AI-agent 编排文件**，让下一个人（或 agent）能直接复刻，不用重新调试。

---

## 架构

三层结构。只有 `adapters/` 是模型相关的；其余都是共享基础设施。

```
eval-infra/        ← 模型无关的基础设施，搭一次永久受益
  01-omnidocbench/    OmniDocBench 代码 + v1.6 数据集（1651 页）+ 配置模板
  02-cdm-environment/ CDM 工具链：应用 windows-cdm.patch 并通过 verify-windows.ps1 的 Windows 原生路径，或 WSL 兼容/参考路径
  03-scoring/         score.ps1（Windows；verify-windows.ps1 通过后用 CDM 配置跑 CDM）· score-cdm.sh（+CDM，WSL 兼容/参考路径）· verify.ps1

adapters/          ← 模型相关，每个模型一个目录
  _template/          最小骨架，直接拷贝
  paddleocr-vl-1.6/   已验证的参考范例（ONNX 版面 + llama.cpp GGUF VLM）
  mineru/             已验证的参考范例（MinerU 3.4.4 pipeline,ROCm PyTorch + ONNX DirectML）

scripts/           ← 跨模块工具
  detect-mirrors.ps1  探测可达镜像 → 写入 mirrors.env
  wsl-ensure.ps1      保证有一个 WSL Ubuntu 22.04 实例（处理商店不可达的情况）
  full-verify.ps1     按依赖顺序串起所有 verify 脚本

docs/
  pitfalls.md         知识库，按症状索引（本 repo 最有价值的文件）
  architecture.md     数据流图 + Windows/WSL 边界
```

**唯一需要记住的架构事实：** CDM 有两条受支持的工具链路径。Windows 原生 CDM 是应用 `windows-cdm.patch` 并通过 `verify-windows.ps1` 后的本地快速路径。WSL CDM 仍是兼容性/参考路径，使用隔离的 Linux TeX Live、ImageMagick 和 Ghostscript 工具链。详见 [`docs/architecture.md`](docs/architecture.md) 和 [`docs/pitfalls.md#posix`](docs/pitfalls.md#posix)。

---

## 适配器：添加一个新模型

你只需要动 `adapters/`。每个适配器唯一的契约：

```python
def run_adapter(img_dir: Path, out_dir: Path, server_url: str = ""):
    """为 img_dir 里的每张页面图写出 out_dir/<image_stem>.md。"""
```

评分层只消费这些 `.md` 文件，从不 import 适配器。
五个步骤（完整说明见 [`adapters/_template/README.md`](adapters/_template/README.md)）：

1. `cp -r adapters/_template adapters/<your-model>`
2. 编辑 `run_adapter.py` —— 实现 `run_adapter(img_dir, out_dir, server_url)` 调用你的模型；为每页写 `out_dir/<image_stem>.md`。捕获每页失败，避免单页出错中止整轮运行。
3. 编辑 `setup.ps1`（或像参考适配器那样拆成编号子目录）来下载权重 / 启动服务。机器本地路径写入 gitignore 的 `.env.local`，绝不写进提交的代码。
4. 运行（在 repo 根目录）：`python adapters\<your-model>\run_adapter.py --img-dir eval-infra\01-omnidocbench\data\images --out-dir predictions\<your-model>`
5. 原样重跑评分器（它只读预测路径）：`eval-infra\03-scoring\score.ps1`；跑 CDM 时，在 `verify-windows.ps1` 通过后使用 `score.ps1 -Config v16-cdm.yaml`，或使用 WSL `score-cdm.sh`，再跑 `verify.ps1`。

可直接参考的已验证范例：
[`adapters/paddleocr-vl-1.6/`](adapters/paddleocr-vl-1.6/)（ONNX 版面 + llama.cpp GGUF VLM；含官方引擎评分注意事项）和
[`adapters/mineru/`](adapters/mineru/)（MinerU 3.4.4 pipeline,ROCm PyTorch + ONNX DirectML）。

---

## 故障排查

我们踩过的所有坑，全部**按症状**组织（根因 → 修复 → 验证）：[`docs/pitfalls.md`](docs/pitfalls.md)。从目录开始，找到你的症状即可。最隐蔽的一种失败是 **CDM F1 = 0 且全程没有任何报错**——所有步骤都成功，分数却是零；[`docs/pitfalls.md#cdm-zero`](docs/pitfalls.md#cdm-zero) 的决策树能解决它。

agent 驱动的流程和异常速查表见 [`AGENTS.md`](AGENTS.md)。

---

## 范围

**在范围内：** OmniDocBench v1.6、AMD Radeon / Windows、llama.cpp 服务的模型、本地单机部署、四项标准指标。

**不在范围内**（设计取舍——见 spec §8）：Docker 方案（保留为备选，不作主线）、OmniDocBench v1.5（提供配置模板，不自动化），以及 WSL、AMD GPU、模型/数据下载、CDM、评分或基准的托管验证。GitHub Actions 仅运行确定性测试与脚本语法检查；硬件相关声明仍以实体机证据为准。

## 许可证

本仓库原创代码按 [`LICENSE`](LICENSE) 中的 Apache-2.0 发布。下载的
OmniDocBench 代码/数据集、PaddleOCR/PaddleOCR-VL 权重、PP-DocLayoutV3、
llama.cpp 二进制及系统包仍受各自上游许可证和条款约束。本仓库不会重新授权
这些第三方资产；生成的 checkout、数据、模型、预测和结果均保持 gitignored。
重新分发前请检查对应上游条款。

安全问题报告见 [`SECURITY.md`](SECURITY.md)，社区行为规范见
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。托管 CI 只验证确定性测试和脚本
语法，不代替 WSL、AMD GPU、CDM、评分或 benchmark 的物理机器证据。
