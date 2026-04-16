---
category: error
hash: 49607633de6403fc
id: 6
layer: L3
tags: ''
title: 20260416 guardrails lint health check
trust: 0.5
updated_at: '2026-04-16T23:45:27.624427+00:00'
---

TITLE:20260416 guardrails lint health check
- **孤立條目偵測** — 沒有 tags（只有 category tag）的條目
- **概念缺口** — tags 被多次引用但無對應獨立條目的概念
- **矛盾偵測** — 同 category 內 trust 差異 > 0.3 的條目對
- guardrails_compiler_update.py 的 lint_knowledge() 和 cascade_update_tags()。
- 每次 compiler 跑完自動執行 Lint。
- related:xxx 被當成 tag 計算，需要過濾
- category_tags 已排除（error/technique/workflow/comparison/concept）
- 連鎖更新目前只檢查 tag 交集，還沒做自動補 tags
... (2 more)
