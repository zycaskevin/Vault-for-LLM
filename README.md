# Guardrails 百科

> Vault user 的個人知識中樞 — 四層分層記憶系統，Supabase 優先，跨 LLM 相容。

---

## 架構

```
L0 身份    → 本地 identity.md（每次對話注入）
L1 核心事實 → 本地 L1-core-facts/（每次對話注入）
L2 脈絡    → 本地 L2-context/（每天自動更新）+ Supabase 查詢
L3 深度知識 → Supabase 搜尋（AAAK 格式，按需）+ 本地 compiled/ 備份
```

所有 L2+ 資料存放在 Supabase `guardrails_knowledge` 表（118 筆），
本地保留 L0/L1（每次對話必備）、compiled/（AAAK 壓縮備份）、raw/（原始知識）。

---

## 目錄結構

```
Guardrails/
├── README.md               ← 你在這裡
├── L0-identity/            ← 身份（每次對話注入）
│   └── identity.md
├── L1-core-facts/          ← 核心事實（每次對話注入）
│   └── current-projects.md
├── L2-context/             ← 動態上下文
│   └── recent-sessions/
│       └── current.md      ← 最近對話摘要（自動更新）
├── L3-knowledge/           ← 知識（Supabase 為主）
├── raw/                    ← 原始知識輸入
│   ├── code-snippets/
│   ├── content-analysis/
│   ├── research/
│   ├── system-logs/
│   └── web-clips/
├── compiled/               ← AAAK 壓縮備份
│   ├── axioms/
│   ├── comparisons/
│   ├── concepts/
│   ├── errors/
│   ├── techniques/
│   └── workflows/
├── scripts/                ← 維護腳本
│   └── frontmatter-spec.md ← YAML 規範
└── migrations/             ← 資料庫遷移
```

---

## AI 讀取指南

### agent runtime Agent
自動讀取 L0 + L1（注入 prompt），需要時搜尋 L2/L3（Supabase）

### Claude Code
1. 讀 CLAUDE.md（包含 L0+L1 摘要）
2. 需要深度知識時搜尋 `compiled/` 或 `raw/`
3. 也可用 `rg` 關鍵字搜尋本地檔案

### 任何 AI（通用）
1. 讀本 README 了解架構
2. 讀 L0 identity.md 了解用戶
3. 讀 L1 current-projects.md 了解當前狀態
4. 用關鍵字搜尋 raw/ 或 compiled/ 找特定知識
5. 有 Supabase 存取權限的可搜尋 guardrails_knowledge 表

---

## 維護

### 編譯器
```bash
python3 ~/.agent-runtime/scripts/guardrails_compiler_update.py
```
- raw/ → Supabase（upsert by content_hash）
- raw/ → compiled/（AAAK 6x 壓縮）
- 自動 L2 更新
- 自動 Lint 健康檢查
- 自動 Git commit（方便回滾）

### Lint 檢查項目
- 📎 孤立條目（無 tags）
- 💡 概念缺口（tag 被引用但無獨立條目）
- ⚠️ 矛盾偵測（同類別 + 信任分數差 > 0.3）

### Git 回滾
```bash
cd ~/.agent-runtime/Guardrails
git log --oneline         # 查看歷史
git checkout HEAD~1 -- .  # 回到上一個版本
```

---

## YAML Frontmatter 規範
詳見 `scripts/frontmatter-spec.md`

所有 .md 檔案開頭加 YAML：
```yaml
---
title: "知識標題"
category: "concept|technique|workflow|lesson|error|comparison"
layer: 0-3
tags: ["tag1", "tag2"]
trust: 0.0-1.0
source: "來源"
created: "YYYY-MM-DD"
---
```

---

*最後更新：2026-04-16*