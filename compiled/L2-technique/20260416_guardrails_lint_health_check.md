---
category: technique
hash: 49607633de6403fc
id: 267
layer: L2
tags: ''
title: 20260416 guardrails lint health check
trust: 0.5
updated_at: '2026-04-16T22:55:43.630613+00:00'
---

# Guardrails Lint 健康檢查實作
## 四個功能
1. **孤立條目偵測** — 沒有 tags（只有 category tag）的條目
2. **概念缺口** — tags 被多次引用但無對應獨立條目的概念
3. **矛盾偵測** — 同 category 內 trust 差異 > 0.3 的條目對
4. **連鎖更新** — 新條目進來後，自動更新引用相同概念的其他條目 tags
## 實作位置
guardrails_compiler_update.py 的 lint_knowledge() 和 cascade_update_tags()
## 觸發時機
每次 compiler 跑完自動執行 Lint
## 已知問題
- related:xxx 被當成 tag 計算，需要過濾
- category_tags 已排除（error/technique/workflow/comparison/concept）
- 連鎖更新目前只檢查 tag 交集，還沒做自動補 tags
## 靈感來源
Karpathy LLM Wiki 的 Lint、矛盾偵測、跨頁連鎖更新
