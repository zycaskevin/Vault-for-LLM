---
category: decision
hash: ae938ac13c6d94bb
id: 6
layer: L3
tags: ''
title: 20260416 karpathy wiki vs guardrails
trust: 0.5
updated_at: '2026-04-16T23:50:07.922118+00:00'
---

TITLE:20260416 karpathy wiki vs guardrails
- | Karpathy | Guardrails | 差異 |。
- |----------|-----------|------|。
- | raw/ | raw/ (L3) | 一樣 |。
- **矛盾偵測** — 新素材進來自動比對舊 page 衝突，標出留給人判斷
- **跨頁連鎖更新** — 新 source 可能同時動到 10-15 張 page
- **Lint / 健康檢查** — 掃整座 wiki 找孤立 page、過期內容、概念缺口
- **分層服務** — L0→L1→L2→L3，不同Q拿不同層，不需要每次翻整座 wiki
- **信任分數** — 每條知識 trust 0-1，互相矛盾的資訊不會平等對待
... (14 more)
