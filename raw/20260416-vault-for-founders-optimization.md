# Vault for Founders 啟發 — 百科六大優化

## 來源
Vault for Founders（cwlin0131 開源方案）三層對照分析

## 六大優化（已完成 4/6）

### ✅ 1. L1 過時內容更新
- current-projects.md 移除 OpenClaw 相關
- 加入 Guardrails 開源計畫、content_log、Nancy_report_bot
- 技術棧表格化

### ✅ 2. YAML Frontmatter 規範
- scripts/frontmatter-spec.md 統一格式
- title/category/layer/tags/trust/source/created 必填
- 跨 LLM 相容基礎（任何 AI 讀了 YAML 就理解結構）

### ✅ 3. Git 自動備份 + 回滾
- compiler 跑完自動 git add + commit
- AI 改壞了 `git checkout HEAD~1 -- .` 一行回滾
- .gitignore 排除敏感檔案

### ✅ 4. README 跨 LLM 指南
- 五步讀取指南（任何 AI 都能操作）
- 目錄結構清楚
- 維護命令可複製

### ⬜ 5. CLAUDE.md 橋接
- L0+L1 內容寫進 CLAUDE.md
- Claude Code 啟動時自動讀取

### ⬜ 6. One-click Setup
- 一鍵安裝腳本（開源前必備）

## 差異化定位
- Vault for Founders：純文字 + 手動維護 → 入門向
- Guardrails Lite：純文字 + 自動編譯 + Lint → 進階開發者
- Guardrails Full：+ Supabase + pgvector → 企業級