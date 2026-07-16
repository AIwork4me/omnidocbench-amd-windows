# OmniDocBench AMD Windows

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform: AMD ROCm](https://img.shields.io/badge/Platform-AMD_ROCm_HIP-red.svg)](https://github.com/issues?q=omnidocbench+amd)
[![OmniDocBench v1.6](https://img.shields.io/badge/OmniDocBench-v1.6-00C853.svg)](https://github.com/opendatalab/OmniDocBench)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/AIwork4me/omnidocbench-amd-windows)](https://github.com/AIwork4me/omnidocbench-amd-windows)

[English](README.md) · [架构图](docs/architecture.md) · [踩坑知识库](docs/pitfalls.md) · [AGENTS.md](AGENTS.md)

> **我们踩了 20+ 个坑才跑通 OmniDocBench CDM。这个 repo 把它们压缩成一条命令。**

在 **Windows + AMD Radeon GPU** 上从零搭建 [OmniDocBench](https://github.com/opendatalab/OmniDocBench) v1.6 全量评测系统
（1651 页，四项标准指标：文本 / 阅读顺序 / 表格 TEDS / **公式 CDM**）。模型无关——换任何文档解析模型只需写一个
[适配器](adapters/)。以 PaddleOCR-VL-1.6 为已验证参考。

![OmniDocBench AMD Windows 概览](overview.jpg)

| 指标 | PaddleOCR-VL (论文) | PaddleOCR-VL-ROCm (实测) |
|---:|---:|---:|
| 整体 Overall | 96.33 | **95.99** |
| 文本 Edit-dist | 0.033 | 0.03488 |
| 阅读顺序 Edit-dist | 0.127 | 0.12882 |
| 表格 TEDS | 94.76 | **94.09** |
| 公式 CDM | 97.49 | **97.36** |

> Overall = (文本准确率 + CDM + TEDS) / 3，其中文本准确率 = (1 − Edit_dist) × 100。阅读顺序不纳入 Overall（布局指标，非内容准确率）。

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
| PowerShell | Windows PowerShell 5.1（自带）或 PowerShell 7+ | 同左 |

全量 1651 页运行的时间估算：步骤 1（数据集下载）国内网络约 15-20 分钟；步骤 2（CDM 环境）约 30 分钟（TeX Live 是大头）；步骤 3（适配器推理）取决于 GPU（CPU 数小时，Radeon HIP 数十分钟）；步骤 4（评分）约 5 分钟（Edit_dist+TEDS）+ 20-30 分钟（CDM，每条公式都要跑 LaTeX）。

### 快速开始

克隆，然后跑四个搭建阶段。每个 `setup.*` 都是幂等的；之后跑对应的 `verify.*`。**所有命令都假定在 repo 根目录执行。**

```bash
git clone https://github.com/AIwork4me/omnidocbench-amd-windows
cd omnidocbench-amd-windows
```

```powershell
# 步骤 0：环境 + 网络 + WSL
powershell -ExecutionPolicy Bypass -File scripts\detect-mirrors.ps1
powershell -ExecutionPolicy Bypass -File scripts\wsl-ensure.ps1

# 步骤 1：OmniDocBench 代码 + 数据集
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\setup.ps1
powershell -ExecutionPolicy Bypass -File eval-infra\01-omnidocbench\verify.ps1

# 可选的原生 CDM 验证（optional；需要本机 TeX Live、ImageMagick 和 Ghostscript）。
# 使用下方 WSL 兼容/参考路径时跳过此项。
powershell -ExecutionPolicy Bypass -File eval-infra\02-cdm-environment\verify-windows.ps1

# 步骤 2：CDM 环境（WSL 兼容/参考路径）
# 把 /mnt/c/<path-to-repo> 换成你 clone 的 WSL 路径。
wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/02-cdm-environment/setup.sh
wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/02-cdm-environment/verify.sh

# 步骤 3：参考适配器（PaddleOCR-VL-1.6）
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\01-vlm-server\setup.ps1 -Variant hip
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\02-layout-model\setup.ps1
powershell -ExecutionPolicy Bypass -File adapters\paddleocr-vl-1.6\00-install-deps\setup.ps1
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --img-dir  eval-infra\01-omnidocbench\data\images `
    --out-dir  predictions\paddleocrvl_rocm

# 步骤 4：评分 + 最终验证
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1
# 原生 Windows CDM 路径：verify-windows.ps1 通过后运行：
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\score.ps1 -Config v16-cdm.yaml
# WSL CDM 兼容/参考路径：
wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/03-scoring/score-cdm.sh
powershell -ExecutionPolicy Bypass -File eval-infra\03-scoring\verify.ps1
# 或一次性跑完：
powershell -ExecutionPolicy Bypass -File scripts\full-verify.ps1
```

Windows 原生 CDM 已受支持：`eval-infra/01-omnidocbench/setup.ps1` 会自动应用
`patches/omnidocbench/windows-cdm.patch`，并由
`eval-infra/02-cdm-environment/verify-windows.ps1` 验证。这是可选路径，需要本机
TeX Live、ImageMagick 和 Ghostscript。WSL CDM 仍保留为兼容和 reference 路径；
选择 WSL 的用户无需进行原生 CDM 验证。
`scripts/full-verify.ps1` 只有在显式传入 `-WindowsCdm` 时才检查原生路径。

如果用 PaddleOCR 官方 `PaddleOCRVL` engine 跑基准评测，请用
`_to_markdown(pretty=False)` 导出评测型 Markdown。默认 pretty Markdown
面向展示，可能因为 HTML 图片/标题包装导致 OmniDocBench Text Edit-distance
被放大。

这些本地分数默认采用 OmniDocBench 官方 leaderboard notebook
（`tools/generate_result_tables.ipynb`）一致的 page-level 聚合口径。最新
Windows AMD llama.cpp/GGUF official-local 路线 Formula CDM 为 `96.5022`；
最新 ROCm lightweight 路线 Formula CDM 为 `97.36`。相对官方 `97.49`
的剩余差距，主要来自官方 Linux vLLM-style 路径与本项目 Windows AMD
llama.cpp/GGUF 路径之间的推理后端/模型输出差异。official-local 路线仍有
1 页稳定 VLM 500，已在上游记录为
[PaddleOCR issue #18248](https://github.com/PaddlePaddle/PaddleOCR/issues/18248)。

```powershell
python adapters\paddleocr-vl-1.6\run_adapter.py `
    --engine official `
    --img-dir eval-infra\01-omnidocbench\data\images `
    --out-dir predictions\paddleocr_official_prettyfalse_full_2026-07-09
```

想用 agent 驱动？把 **Codex、Claude Code、OpenCode，或任何能读 `AGENTS.md` 的 agent** 指向本 repo，说"按 AGENTS.md 搭建" / "Read AGENTS.md and execute the setup flow."。完整分步流程（含异常处理）见 [`AGENTS.md`](AGENTS.md)。

---

## 这个 repo 为什么存在

在 AMD Windows 上跑通 OmniDocBench v1.6 会踩 20+ 个坑：国内网络封锁、WSL 商店被墙、`\mathcolor` 渲染成黑色、ImageMagick 6 把彩色公式渲染成灰度、两个 TeX Live 树互相打架、Windows 代码页把 CJK 的 JSON 弄乱，等等。本 repo 把每个修复都固化成**幂等脚本** + **按症状索引的知识库** + **AI-agent 编排文件**，让下一个人（或 agent）能直接复刻，不用重新调试。

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

scripts/           ← 跨模块工具
  detect-mirrors.ps1  探测可达镜像 → 写入 mirrors.env
  wsl-ensure.ps1      保证有一个 WSL Ubuntu 22.04 实例（处理商店被墙的情况）
  full-verify.ps1     按依赖顺序串起所有 verify 脚本

docs/
  pitfalls.md         知识库，按症状索引（本 repo 最有价值的文件）
  architecture.md     数据流图 + Windows/WSL 边界
```

**唯一需要记住的架构事实：** CDM 有两条受支持的工具链路径。Windows 原生 CDM 是应用 `windows-cdm.patch` 并通过 `verify-windows.ps1` 后的本地快速路径。WSL CDM 仍是兼容性/参考路径，使用隔离的 Linux TeX Live、ImageMagick 和 Ghostscript 工具链。详见 [`docs/architecture.md`](docs/architecture.md) 和 [`docs/pitfalls.md#posix`](docs/pitfalls.md#posix)。

每个适配器唯一的契约：

```python
def run_adapter(img_dir: Path, out_dir: Path, server_url: str = ""):
    """为 img_dir 里的每张页面图写出 out_dir/<image_stem>.md。"""
```

评分层只消费这些 `.md` 文件，从不 import 适配器。

---

## PaddleOCR-VL-1.6 参考得分

我们在 OmniDocBench v1.6（全量 1651 页）上由本 repo 复现的已验证结果。
PaddleOCR official engine 使用 `paddleocr.PaddleOCRVL`，并强制
`_to_markdown(pretty=False)` 输出评测型 Markdown。PaddleOCR-VL-ROCm engine
是默认的 AMD Windows 本地参考路径。命令、运行统计和根因说明见
[`docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md`](docs/release-paddleocr-vl-1.6-amd-windows-2026-07-09.md)。

| 指标 | PaddleOCR-VL (论文) | PaddleOCR-VL-ROCm (实测) |
|---:|---:|---:|
| 整体 Overall | 96.33 | **95.99** |
| 文本 Edit-dist | 0.033 | 0.03488 |
| 阅读顺序 Edit-dist | 0.127 | 0.12882 |
| 表格 TEDS | 94.76 | **94.09** |
| 公式 CDM | 97.49 | **97.36** |

> Overall = (文本准确率 + CDM + TEDS) / 3，其中文本准确率 = (1 − Edit_dist) × 100。阅读顺序不纳入 Overall（布局指标，非内容准确率）。

跑基准评测时，PaddleOCR 官方 `PaddleOCRVL` engine 必须用
`_to_markdown(pretty=False)` 导出 Markdown。默认 pretty Markdown 面向展示，
会引入 HTML 图片/标题包装，可能放大 OmniDocBench Text Edit-distance。

这些行使用 OmniDocBench 官方 leaderboard/notebook page-level 聚合口径；
底层 raw `metric_result` all-values 保留在对应产物中用于审计。official-local
路线 Formula CDM 为 `96.5022`，ROCm lightweight 路线 Formula CDM 为
`97.36`；相对 `97.49` 的剩余差距主要来自官方 Linux vLLM-style 基线与
本机 Windows AMD llama.cpp/GGUF server 路径的推理后端/模型输出差异。本轮
official-local 仍有 1 个稳定 VLM 500 页面：
`newspaper_The Times UK_0801@magazinesclubnew_page_031.png`，
已记录为 [PaddleOCR issue #18248](https://github.com/PaddlePaddle/PaddleOCR/issues/18248)。
CDM 环境问题见
[`docs/pitfalls.md#mathcolor`](docs/pitfalls.md#mathcolor) 和
[`docs/pitfalls.md#cdm-zero`](docs/pitfalls.md#cdm-zero)。

一次全新运行要达到“复现我们的结果”，需要满足的门槛：文本编辑距离 < 0.10、
阅读顺序 < 0.20、按公开表格百分制口径 TEDS > 85、CDM > 85。若查看原始
`metric_result.json`，TEDS/CDM 对应阈值是 `> 0.85`。

---

## 如何添加一个新模型

你只需要动 `adapters/`。五个步骤（完整说明见 [`adapters/_template/README.md`](adapters/_template/README.md)）：

1. `cp -r adapters/_template adapters/<your-model>`
2. 编辑 `run_adapter.py` —— 实现 `run_adapter(img_dir, out_dir, server_url)` 调用你的模型；为每页写 `out_dir/<image_stem>.md`。捕获每页失败，避免单页出错中止整轮运行。
3. 编辑 `setup.ps1`（或像参考适配器那样拆成编号子目录）来下载权重 / 启动服务。机器本地路径写入 gitignore 的 `.env.local`，绝不写进提交的代码。
4. 运行（在 repo 根目录）：`python adapters\<your-model>\run_adapter.py --img-dir eval-infra\01-omnidocbench\data\images --out-dir predictions\<your-model>`
5. 原样重跑评分器（它只读预测路径）：`eval-infra\03-scoring\score.ps1`；跑 CDM 时，在 `verify-windows.ps1` 通过后使用 `score.ps1 -Config v16-cdm.yaml`，或使用 WSL `score-cdm.sh`，再跑 `verify.ps1`。

参考适配器 [`adapters/paddleocr-vl-1.6/`](adapters/paddleocr-vl-1.6/) 是一个完整、已验证的范例，可以直接参考。

---

## 故障排查

我们踩过的所有坑，全部**按症状**组织（根因 → 修复 → 验证）：[`docs/pitfalls.md`](docs/pitfalls.md)。从目录开始，找到你的症状即可。最隐蔽的一种失败是 **CDM F1 = 0 且全程没有任何报错**——所有步骤都成功，分数却是零；[`docs/pitfalls.md#cdm-zero`](docs/pitfalls.md#cdm-zero) 的决策树能解决它。

agent 驱动的流程和异常速查表见 [`AGENTS.md`](AGENTS.md)。

---

## 范围

**在范围内：** OmniDocBench v1.6、AMD Radeon / Windows、llama.cpp 服务的模型、本地单机部署、四项标准指标。

**不在范围内**（设计取舍——见 spec §8）：Docker 方案（保留为备选，不作主线）、OmniDocBench v1.5（提供配置模板，不自动化）、非 AMD GPU 适配器（提供模板，欢迎社区贡献）、CI/CD（用本地 verify 脚本，不上 GitHub Actions）。

## 许可证

评测代码与数据集的条款以上游 [OmniDocBench](https://github.com/opendatalab/OmniDocBench) 许可证为准。本 repo 中的基础设施与适配器代码按原样提供，用于复现该基准。
