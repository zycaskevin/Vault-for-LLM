---
category: architecture
hash: e1d131616a684af8
id: 109
layer: L3
tags: test-data,experience-base,techniques
title: 20260411 test experience base techniques 233
trust: 0.5
updated_at: '2026-04-16T17:21:16.203396+00:00'
---

# 測試數據: experience-base_20260406-130632_1
## 原始文件
experience-base/lessons-learned/20260406-130632.md
## 推斷類別
techniques
## 內容片段
[Correct] 實裝 autoDream 記憶蒸餾系統：
- 配置：`config/autoDream.yaml`, `scripts/autoDream.sh`
- 觸發條件：每天 03:00 或超過 500 行
- 保留策略：score≥9 原樣保留，score≥7 保留摘要，scar 格式特殊保留
- 成果：1021 行 → 82 行（93.6% 壓縮）
---
*用於分類器測試的數據*
