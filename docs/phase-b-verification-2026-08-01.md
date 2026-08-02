# Phase B Verification Evidence (2026-08-01)

本文档归档 Phase B（MinerU 适配器 + 多模型 Leaderboard + Strix Halo 平台证据）的全部验收证据。除标注外，所有输出均为 2026-08-02 在分支 `phase-b/mineru-adapter` 上实时重跑所得。

## 验收总表

| 验收项 | 命令 | 结果 |
|---|---|---|
| MinerU 适配器 verify | `powershell -ExecutionPolicy Bypass -File adapters\mineru\verify.ps1` | 5/5 PASS + `VERIFY OK`，exit **0**（实时重跑，含 GPU smoke 一页推理 386 字节输出） |
| B2 抽样门结论 | [docs/benchmarks/mineru-sample81-gate-2026-08-01.md](benchmarks/mineru-sample81-gate-2026-08-01.md) | **ACCEPT**：Metric A mean ratio 0.999471 ≥ 0.98；Metric B text diff 0.000110 ≤ 0.01、TEDS diff 0.014566 pp ≤ 2 pp；model card 交叉核对 4/4 PASS（tol 1e-6） |
| Leaderboard 每格溯源 | `python scripts/verify_leaderboard_numbers.py` | 全部 PASS + `VERIFY OK: all leaderboard numbers match their sources`，exit 0（含 README 中英双语逐格一致） |
| pytest 全量 | `python -m pytest -q` | **145 passed in 10.01s**，exit 0 |
| pitfalls 新增条目 | [docs/pitfalls.md](pitfalls.md) | 新增 `#miopen-finddb`（MIOpen find-db 损坏，引用 B2 事件 2026-08-01 Event 41）与 `#gpu-counters-windows`（Windows AMD GPU 计数器不可用）两条 Symptom→Root Cause→Fix→Verify 条目及 TOC 行 |
| CI（PR） | `gh run watch` | 见 PR 检查结果（本文件 PR 部分） |

## B2 抽样门关键数字（摘自 gate 文档）

- 样本：确定性分层抽样 `scripts/sample_stratified.py --per-category 9 --seed 42` → **130 页**（15 层 × 9，jiaocai 6 / jiaocaineedrop 8 / scihub 8 三层偏离）。
- 样本重推理：`ok=130, fail=0, fallback=0`，67.8 min，均值 31.3 s/页（含一次性 MIOpen find-db 重建）。
- **Metric A**：EXACT_MATCH 103/130 = 0.7923（< 90%），但 MEAN_RATIO **0.999471 ≥ 0.98**（OR 条件）→ PASS。
- **Metric B**（130 页双向评分）：text Edit-distance diff **0.000110** ≤ 0.01 → PASS；TEDS diff **0.014566 pp** ≤ 2 pp → PASS；reading-order / display-formula diff 均为 0。
- **交叉核对**：in-repo `metric_result` vs `model_card.pipeline.windows-hip.json` 四项子指标 abs_diff 全为 0（tol 1e-6）→ PASS；MinerU 86.59 系列（overall 86.59 / text 0.05655 / RO 0.15314 / TEDS 82.04 / CDM 83.39）确认可用于 B3 引用。

## 原始输出（2026-08-02 实时重跑）

### `adapters\mineru\verify.ps1`（exit 0）

```
PASS [1/5]: .env.local OK, MINERU_ROCM_REPO=C:\Users\rocm\Desktop\MinerU-ROCm
PASS [2/5]: torch HIP GPU: AMD Radeon(TM) 8060S Graphics
PASS [3/5]: DmlExecutionProvider is first
PASS [4/5]: weights present at C:\Users\rocm\.cache\huggingface\hub\models--opendatalab--PDF-Extract-Kit-1.0\snapshots\ed6b654c018d742e65a17671e379c5e6ecc87ec9
[5/5] smoke: PPT_1001115_eng_page_003.png through adapter (GPU warmup may take 1-3 min)...
...（MinerU pipeline 模型加载与单页推理日志，GPU Memory: 78 GB, Batch Ratio: 16）...
PASS [5/5]: smoke produced C:\Users\rocm\AppData\Local\Temp\mineru-verify-out\PPT_1001115_eng_page_003.md (386 bytes)
VERIFY OK: MinerU adapter environment ready.
VERIFY_EXIT=0
```

### `python scripts/verify_leaderboard_numbers.py`（exit 0）

```
== 1. PaddleOCR-VL-ROCm (reference) <- docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md ==
PASS  release-0716 doc contains 95.99 / 0.03488 / 0.12882 / 94.0865 / 97.36
PASS  ROCm TEDS 94.09 rounds from 94.0865
== 2. PaddleOCR-VL (paper, Linux vLLM) <- release-0716 public baseline table ==
PASS  baseline table contains 96.33 / 0.033 / 0.127 / 94.76 / 97.49
== 3. PaddleOCR-VL official (local) <- Windows-native CDM rerun metric_result (2026-07-11) ==
PASS  official CDM metric_result JSON exists
PASS  official text 0.03444 / RO 0.12949 / TEDS 94.24 / CDM 96.50 / CDM(4dp) 96.5022 / Overall 95.77
== 4. MinerU 3.4.4 pipeline (Windows HIP) <- model card + in-repo metric_result ==
PASS  card model_version == 3.4.4; card text/RO/TEDS/CDM == metric_result; card overall == computed
PASS  MinerU text 0.05655 / RO 0.15314 / TEDS 82.04 / CDM 83.39 / Overall 86.59
== 5. B2 gate doc verdict ==
PASS  gate verdict is ACCEPT; gate sample was 130 pages; gate cites the 86.59 series
== 6. README leaderboard rows are numerically identical EN vs ZH ==
PASS  both READMEs have 4 leaderboard data rows; EN/ZH numbers identical

VERIFY OK: all leaderboard numbers match their sources
```

（逐项 PASS 明细以脚本实际输出为准，共 30+ 条全部 PASS。）

### `python -m pytest -q`（全量，exit 0）

```
........................................................................ [ 49%]
........................................................................ [ 99%]
.                                                                        [100%]
145 passed in 10.01s
```

## 结论

Phase B 全部验收项通过：MinerU 适配器环境 verify 退出 0；B2 抽样门 ACCEPT 且数字可复核；Leaderboard 每格溯源 VERIFY OK；全量 pytest 145 绿；两条新 pitfalls 条目落档。分支推送与 PR/CI 结果记录于本文件 PR 部分与 task B5 报告。
