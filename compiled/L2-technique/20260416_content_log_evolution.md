---
category: technique
hash: 3fb5d4ba157aeae7
id: 264
layer: L2
tags: ''
title: 20260416 content log evolution
trust: 0.5
updated_at: '2026-04-16T22:55:43.664892+00:00'
---

# 社媒內容結構化 + 進化追蹤
## 流程
每篇文章產出後：
1. 寫入 guardrails_knowledge（category=content-log）→ 搜尋 + Lint
2. 寫入 content_log 表 → 追蹤發佈狀態 + 數據 + 審查評分
3. 用本地模型做 Adversarial Review → 寫入 guardrails_knowledge（category=content-review）
4. 審查評分存入 content_log.review_score（JSONB {hook:N, share:N, experience:N}）
## 進化機制
- evolution_tags 追蹤同一主題的演進（如 agent-four-paths → agent-four-paths-v2）
- 每篇新文自動比對同 evolution tag 的舊文，標注差異
... (原 11 段，取前 5 段)
