# 04-benchmark/ -- 基准测试模块

在 AMD 硬件上为 OmniDocBench v1.6 生成数据驱动的全链路能力报告。运行完整流水线
（适配器推理 + Edit_dist + TEDS + CDM 评分），全程每秒采样 GPU 显存/利用率/系统内存，
产出含质量得分、资源曲线、逐页耗时分布的 Markdown 报告。

## 产出物

| 产物 | 位置 | 说明 |
|---|---|---|
| 能力报告 | `benchmark-results/<run_id>/benchmark-report.md` | 五章完整 Markdown 报告 |
| 资源日志 | `benchmark-results/<run_id>/resource_log.jsonl` | 每秒一条 JSON（GPU 显存/利用率/RAM） |
| 阶段日志 | `benchmark-results/<run_id>/phase_log.json` | 各阶段时间戳（监控/推理/评分） |
| 稳定性报告 | `benchmark-results/reference/<qualifier>/benchmark-report.md` | 含 N 次运行的均值/标准差/分布区间 |
| 运行清单 | `benchmark-results/reference/<qualifier>/_runs_manifest.json` | 稳定性运行索引 + 逐次指标 |

## 使用方式

### 单次运行

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1
```

### 稳定性模式（N 次运行获得统计置信度）

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\run.ps1 -Stability 5
```

### 验证产出

```powershell
powershell -ExecutionPolicy Bypass -File eval-infra\04-benchmark\verify.ps1 -ReportDir benchmark-results\20260706-143000
```

## 如何阅读报告

1. **第 1 章（总览）：** 一屏看完。四项指标、总耗时、成功率。绿色对勾=全部达标。
2. **第 2 章（质量得分）：** 指标明细，每项带溯源链接。参考模式下含稳定性统计。
3. **第 3 章（计算资源）：** GPU 显存峰值/均值/曲线、系统内存。如 GPU 数据不可用会明确标注。
4. **第 4 章（推理性能）：** P50/P95/P99 耗时分布、吞吐量、失败页分析。
5. **第 5 章（环境快照）：** 平台、量化级、后端、运行编号。

## 前提条件

- 已完成 CLAUDE.md 中的步骤 0-3（WSL、数据集、CDM 环境、适配器）
- Python 包：`pip install psutil`
- GPU 监控需 `rocm-smi` 在 PATH 中（不可用时自动降级）
- 测试：`pip install pytest`

## 测试

```powershell
python -m pytest eval-infra\04-benchmark\tests\ -v
```
