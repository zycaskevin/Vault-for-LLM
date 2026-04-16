# Guardrails YAML Frontmatter 規範

## 所有 .md 檔案統一格式

每個知識檔案的開頭必須有 YAML frontmatter：

```yaml
---
title: "知識標題"
category: "concept|technique|workflow|lesson|error|comparison|article-source|content-log"
layer: 0-3
tags: ["tag1", "tag2"]
trust: 0.0-1.0
source: "來源標識"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: "active|archived|deprecated"
---
```

## 各層規範

### L0 — 身份 (identity.md)
```yaml
---
title: "用戶身份"
layer: 0
tags: ["identity", "preferences"]
trust: 1.0
source: "user-defined"
---
```
不需要 category（只有一個身份檔案）

### L1 — 核心事實
```yaml
---
title: "當前專案與任務"
layer: 1
category: "project"
tags: ["projects", "tech-stack"]
trust: 1.0
source: "user-defined"
updated: "2026-04-16"
---
```

### L2 — 動態上下文
```yaml
---
title: "最近 Session 摘要"
layer: 2
category: "recent-sessions"
tags: ["context", "dynamic"]
trust: 0.8
source: "auto-generated"
updated: "2026-04-16"
---
```

### L3 — 深度知識（raw/）
```yaml
---
title: "WSL2 Chrome CDP 三層橋接"
layer: 3
category: "technique"
tags: ["wsl2", "chrome", "cdp", "browser"]
trust: 0.8
source: "20260416"
created: "2026-04-16"
status: "active"
---
```

### L3 — 深度知識（compiled/）
```yaml
---
title: "CDP 橋接技術"
layer: 3
category: "technique"
tags: ["cdp", "browser", "wsl2"]
trust: 0.8
source: "compiled:20260416-wsl2-chrome-cdp-bridge"
compression: "aaak"
original_tokens: 1200
compressed_tokens: 200
---
```

## 關鍵規則

1. **title 必填** — 不能為空，AI 用 title 做索引
2. **tags 至少 2 個** — Lint 用 tags 做孤立偵測
3. **trust 範圍 0-1** — 1.0 = 用戶定義，0.9 = 驗證過，0.7 = 可信，0.5 = 未驗證，0.3 以下 = 有衝突
4. **category 必填** — 用於分類搜尋和 Lint
5. **updated 每次修改時更新** — 追溯知識新鮮度

## 為什麼要 YAML frontmatter？

1. **跨 LLM 相容** — Obsidian、Claude Code、OpenClaw 都能讀
2. **結構化搜尋** — AI 不用讀全文就能判斷是否相關
3. **開源準備** — 別人拿到就能理解結構
4. **Lint 基礎** — frontmatter 是健康檢查的數據源