---
category: error
hash: 3fb5d4ba157aeae7
id: 1
layer: L3
tags: ''
title: 20260416 content log evolution
trust: 0.5
updated_at: '2026-04-17T02:12:21.890804+00:00'
---

TITLE:20260416 content log evolution
- 寫入 guardrails_knowledge（category=content-log）→ 搜尋 + Lint
- 寫入 content_log 表 → 追蹤發佈狀態 + 數據 + 審查評分
- 用本地模型做 Adversarial Review → 寫入 guardrails_knowledge（category=content-review）
- evolution_tags 追蹤同一主題的演進（如 agent-four-paths → agent-four-paths-v2）
- 每篇新文自動比對同 evolution tag 的舊文，標注差異
- lessons 欄位記錄每篇學到的教訓，下次寫文自動參考
- Hook力道（1-10）：第一句話能不能3秒抓住WARN力
- 可共用性（1-10）：讀者看完會不會想轉發
... (6 more)
