# Guardrails 百科 — 跨 LLM 相容指南

## 問題
目前 Guardrails 只被 Hermes Agent 讀取。接 Claude Code / OpenClaw 時完全讀不到知識。

## 解法：CLAUDE.md / AGENTS.md 橋接

### 方案 1：CLAUDE.md 注入 L0+L1（最簡單）
Claude Code 每次啟動自動讀 CLAUDE.md。把 L0+L1 的核心內容寫進去：

```markdown
# CLAUDE.md

## 用戶身份
[從 L0 identity.md 複製]

## 核心事實
[從 L1 current-projects.md 複製]

## Guardrails 知識庫
完整知識庫在 ~/.hermes/Guardrails/
- L2 動態上下文：L2-context/recent-sessions/current.md
- L3 深度知識：Supabase guardrails_knowledge 表
- 本地備份：compiled/ 目錄下有 AAAK 壓縮版
```

### 方案 2：UserPromptSubmit Hook（最強）
跟 Obsidian+Claude 文章一樣：
- 每次送訊息前，自動跑關鍵字搜尋 Guardrails
- 把相關知識塞進背景資料

```bash
#!/bin/bash
# ~/.claude/hooks/user-prompt-submit.sh
KEYWORDS=$(echo "$1" | grep -oP '[\x{4e00}-\x{9fff}\w]{2,}' | head -5)
RESULTS=$(cd ~/.hermes/Guardrails && rg -l "$KEYWORDS" raw/ compiled/ 2>/dev/null | head -3)
if [ -n "$RESULTS" ]; then
    echo "相關知識："
    for f in $RESULTS; do head -5 "$f"; done
fi
```

### 方案 3：README 索引（Vault for Founders 方式）
在 Guardrails 根目錄放一個詳細的 README.md，任何 AI 讀了就知道：
- 知識庫架構（L0-L3）
- 去哪找什麼
- 目錄結構

## 優先順序
1. ✅ 方案 1 先做 — CLAUDE.md 橋接
2. ⬜ 方案 3 再做 — README 索引優化
3. ⬜ 方案 2 最後做 — Hook 需要更多測試