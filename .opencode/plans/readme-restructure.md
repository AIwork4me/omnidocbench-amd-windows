# README 聚焦重构执行计划(已获用户批准 2026-08-02)

## 目标结构(双语镜像 README.md + README.zh-CN.md)

1. 标题 + badges + 导航(不动)
2. tagline + 一句话定位 + overview.jpg(不动)
3. **## Measured results on this machine**(原 leaderboard 上移至此,hero 表删除)
   - 3 行模型表原样(PaddleOCR-VL-1.6 95.99 / MinerU2.5-Pro-2605-1.2B 95.46 / MinerU 3.4.4 pipeline 86.59)
   - 注:全量 1651 本机实测 + 证据/门/模型卡链接 + official-engine 一行(official-local CDM `96.5022`,issue #18248,指向证据文档)
   - 引用块:复现阈值(<0.10 / <0.20 / >85 / >85,raw >0.85)+ G4 1.7x(保留唯一一次)+ Overall 公式
4. **## System Requirements**(表格不动 + Strix Halo 链接;860M 200 页 <details> 块从开头移至表格后)
5. **## Quick Start**(reproduce.ps1 主路径不动;手动分阶段 <details> 不动;200 页 CPU 路径收进新 <details>;**删除** official-engine/pretty=False 散文段与命令块——adapter README L110-137 已覆盖;保留 Windows-native CDM 段 + AGENTS.md agent 段)
6. **## Why this repo exists**(不动)
7. **## Architecture**(不动)
8. **## Adapters: add a new model**(契约 + 5 步法 + 两个已验证范例 paddleocr-vl-1.6 / mineru;契约从 Architecture 移入此节)
9. **## Troubleshooting / ## Scope / ## License**(不动)

## 删除(无迁移)

- 旧 hero 表(开头)+ 「PaddleOCR-VL-1.6 reference scores / 参考得分」整节(表重复;阈值/聚合散文被新注覆盖;96.5022 叙事已在 release 文档+证据文档)
- 重复的 G4 注(保留 leaderboard 下唯一一次)

## 硬约束

- EN/ZH 镜像;`96.5022` 双语各出现恰好 1 次(test_readme_consistency 计数断言)
- leaderboard 保持 3 行且双语数字一致(verify_leaderboard_numbers.py 第 6 节)
- 所有链接可解析(test_markdown_links);不改任何数字
- CHANGELOG.md [Unreleased] 加一行:README restructured for focus: leaderboard first, single source of metrics truth, PaddleOCR operational details moved to the adapter README.

## 验收(真实输出)

- `python -m pytest tests/test_readme_consistency.py tests/test_markdown_links.py -q` 全过
- `python scripts/verify_leaderboard_numbers.py` exit 0
- `python -m pytest -q` 全绿(当前 145)
- `wc -l` 前后对比(预期 README.md 439→~340)

## 提交

`docs: restructure README for focus — leaderboard first, single metrics source` + push main。
