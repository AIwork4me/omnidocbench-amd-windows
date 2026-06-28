# CDM 公式评测 F1=0？我们花了 3 天找到根因——并把全套搭建开源了

> OmniDocBench v1.6 全量评测（含 CDM 公式指标）在 AMD Windows 上的一键搭建。20+ 个坑压缩成一条命令，以 PaddleOCR-VL-1.6 为范例验证，搭好后可评测任何文档解析模型。

## 你是不是也遇到了这个问题？

你在 AMD Windows 上搭好了 OmniDocBench，跑完了 1651 页全量评测，Edit-dist、TEDS 都正常出分了——唯独 **CDM（公式内容距离指标）始终返回 0.0**。

2352 个公式样本，0 个异常，0 个报错。所有步骤都"成功"。但分数是零。

你开始排查：检查 TeX Live、检查 ImageMagick、检查 Ghostscript……每个组件单独测试都正常。你花了几个小时，甚至几天，找不到原因。

**我们也是。** 而且我们花了整整 3 天。

---

## 根因：一个连 OmniDocBench 官方都没记录的 Bug

CDM 的工作原理是这样的：它把公式 LaTeX 里的每个 token 染成不同颜色（`\mathcolor[RGB]{255,0,0}{x}`），编译成 PDF 后检测每种颜色的位置，再跟 ground truth 比对。

问题出在 `\mathcolor` 这个命令。

在 TeX Live 2026（也是当前最新版）中，`\mathcolor` **能编译通过，但渲染出来全是黑色**。不报错，不警告，就是没颜色。于是颜色检测找不到任何 token，F1 自然是 0。

这个 Bug 的隐蔽程度令人发指：
- `\textcolor{red}{文字}` → ✅ 正常红色
- `{\color[RGB]{255,0,0} x}` → ✅ 正常红色
- `\mathcolor[RGB]{255,0,0}{x}` → ❌ **黑色**（但编译成功，无任何报错）

**修复方法只有一行**：在 CDM 的 LaTeX 模板里，用 `\DeclareDocumentCommand` 重定义 `\mathcolor`，让它底层走 `\color`：

```latex
\DeclareDocumentCommand{\mathcolor}{O{} m m}
  {\begingroup\color[#1]{#2}#3\endgroup}
```

修复后，CDM F1 从 0.0 直接跳到 **0.944**。

---

## 但这只是 20+ 个坑中的一个

在 AMD Windows 上从零搭建 OmniDocBench v1.6 全量评测，你会踩到的坑远不止这一个。我们把每个坑都记录、定位、修复了：

| 坑 | 症状 | 根因 |
|---|---|---|
| **GitHub 不可达** | `git clone` 超时 | 国内网络封锁，需用 gitclone/ghproxy 镜像 |
| **HuggingFace 不可达** | 模型/数据集下载失败 | 需改用 ModelScope（魔搭社区） |
| **WSL 商店被墙** | `wsl --install` 失败 | `raw.githubusercontent.com` 不通，需手动导入 rootfs |
| **CDM 代码 POSIX-only** | CDM 在 Windows 上 F1=0 | OmniDocBench 用 shell 字符串调用 pdflatex/magick，`cmd.exe` 解析不了 |
| **ImageMagick 6 灰度** | CDM F1=0（另一个原因） | IM6 把彩色公式 PNG 渲染成灰度，颜色信息丢失 |
| **`\mathcolor` 黑色** | CDM F1=0（最隐蔽的原因） | TL2026 的 `\mathcolor` 渲染黑色但无报错 |
| **CJK.sty 不存在** | `pdflatex` 报错找不到 CJK.sty | Ubuntu 的 texlive 缺经典 CJK 包，需从 TL2026 复制 |
| **gkaiu 字体不在 pdftex.map** | `Font gkaiu5f at 600 not found` | 字体 map 未注册，需手动注入 |
| **IM7 AppImage 缺系统库** | `libfribidi.so.0 not found` | AppImage 不含系统依赖，需 `apt install` |
| **IM7 的 LD_LIBRARY_PATH 影子 gs** | `gs: error 256` | IM7 的 bundled lib 路径覆盖了系统 gs 的依赖 |
| **IM6 PDF 安全策略** | `security policy PDF` | IM6 默认禁止读 PDF，需改 policy.xml |
| **Windows 代码页 GBK** | `UnicodeDecodeError: 'gbk'` | OmniDocBench 读 JSON 没指定 UTF-8 |

完整版 16 条（含修复命令）在 repo 的 `docs/pitfalls.md` 里，按**症状索引**——遇到什么报错，直接查对应的章节。

---

## 解决方案：一个 Repo，一条命令

我们把整个搭建过程固化成了一个开源 repo：

**[omnidocbench-amd-windows](https://github.com/AIwork4me/omnidocbench-amd-windows)**

核心设计有三层：

**第一层：评测基础设施（模型无关，搭一次永久受益）**
- OmniDocBench 代码 + v1.6 数据集（1651 页）
- CDM 环境（WSL 内的 TL2026 + IM7 + gs + 所有修复）
- 评分脚本（Edit-dist + TEDS + CDM）

**第二层：模型适配器（换模型只换这一层）**
- PaddleOCR-VL-1.6 作为已验证参考
- `_template/` 模板，复制即可为新模型写适配器

**第三层：AI-agent 编排（CLAUDE.md）**

这是我们认为最有意思的部分。repo 里的 `CLAUDE.md` 是一份**AI agent 可执行的搭建指令**。你用 Claude Code 或 OpenCode 打开这个 repo，说一句"按 CLAUDE.md 搭建"，agent 就会自动：

1. 检测网络环境，选择最快的镜像源
2. 确保 WSL 已安装
3. 下载 OmniDocBench 代码 + 数据集
4. 搭建 CDM 环境（9 个步骤，每步自检）
5. 启动 VLM 服务器
6. 跑推理 → 评分 → 出分数

每个步骤都有 `verify` 脚本返回 exit 0/1，agent 不需要"理解"输出，只需检查退出码。遇到异常时，CLAUDE.md 指向 `pitfalls.md` 对应章节，agent 能自主排查修复。

---

## 实测成绩

以 PaddleOCR-VL-1.6（BF16 未量化，via llama.cpp HIP）为参考模型，在全量 1651 页上的成绩：

| 指标 | 本 repo | 官方 | 差距 |
|---|---:|---:|---:|
| 文本 Edit-dist ↓ | 0.035（96.5%） | 0.033 | 0.17pt |
| 阅读顺序 ↓ | 0.129（87.1%） | 0.127 | 0.19pt |
| 表格 TEDS ↑ | 0.940 | 0.948 | 0.76pt |
| 公式 CDM ↑ | 0.944 | 0.975 | 3.1pt |

文本和阅读顺序与官方差 0.2pt 以内，表格 TEDS 差 0.76pt——这些是轻量 ONNX+llama.cpp 路线 vs 官方 Paddle 原生管线的正常差异。

---

## 这意味着什么？

**如果你是 AMD Windows 用户**：你不再需要花 3 天踩坑。Clone repo → 跑脚本 → 得到分数。

**如果你在评测自己的模型**：基础设施搭一次，之后换模型只需要写一个适配器（一个函数：`run_adapter(img_dir, out_dir)`）。MinerU、Qwen-VL、GPT-4o API……同一个 OmniDocBench 基础设施，不同的适配器。

**如果你对 AI-agent 驱动的 DevOps 感兴趣**：这个 repo 的 CLAUDE.md 是一个真实的、经过验证的 AI-agent 编排案例。它不是"理论上可以用 AI 搭建"——它已经被测试过，verify 脚本是 agent 的眼睛，pitfalls.md 是 agent 的知识库。

---

## 30 秒快速开始

```bash
git clone https://github.com/AIwork4me/omnidocbench-amd-windows
cd omnidocbench-amd-windows
# 用 Claude Code 打开 → 说"按 CLAUDE.md 搭建"
# 或手动：README 里的 4 步 PowerShell 命令
```

Repo 地址：**github.com/AIwork4me/omnidocbench-amd-windows**

如果你觉得有用，给个 Star ⭐。如果你在搭建中遇到新坑，提 Issue——我们会加进 pitfalls.md。

如果你也想为自己的模型做 OmniDocBench 评测，复制 `adapters/_template/`，写一个函数，PR 过来。

---

*这不是一个脚本集合——它是一个 AI 可执行的搭建协议 + 一份用 3 天血泪换来的踩坑知识库。*
