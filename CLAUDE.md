# Guardrails 百科橋接 — CLAUDE.md

## 使用方式
把下方內容複製到你的 CLAUDE.md（或任何 AI 的系統提示）。
AI 啟動時會自動讀取 L0 身份 + L1 核心事實。

---

```markdown
## Guardrails 百科

你有一個分層知識庫，位於 ~/.guardrails/（或 GUARDRAILS_PATH 環境變數指定的位置）。

### 架構
- **L0 身份**：`L0-identity/identity.md` — 每次對話都讀
- **L1 核心事實**：`L1-core-facts/current-projects.md` — 每次對話都讀
- **L2 動態上下文**：`L2-context/recent-sessions/current.md` — 需要時讀
- **L3 深度知識**：`raw/` 或 `compiled/` — 搜尋時才讀

### 讀取規則
1. 每次對話開始，先讀 L0 + L1
2. 用戶提到過去的事，搜尋 L3（先用關鍵字 `rg`，不夠再搜語意）
3. 做完有價值的事，寫入 `raw/` 一條新知識（YAML frontmatter 格式）
4. 寫完後執行 `python3 scripts/guardrails_compiler.py` 編譯

### 搜尋方式
- 關鍵字搜尋：`rg "關鍵字" ~/.guardrails/raw/ ~/.guardrails/compiled/`
- 標題搜尋：`rg "title:" ~/.guardrails/raw/`
- 標籤搜尋：`rg "tags:.*keyword" ~/.guardrails/raw/`

### 寫入格式
每條知識用 YAML frontmatter：
\`\`\`yaml
---
title: "標題"
category: "technique|concept|workflow|lesson|error|comparison"
layer: 3
tags: ["tag1", "tag2"]
trust: 0.8
source: "20260417"
created: "2026-04-17"
---
\`\`\`
```

---

## 進階：UserPromptSubmit Hook（選配）

讓 Claude Code 每次送訊息前自動搜尋相關知識：

```bash
#!/bin/bash
# 檔案：.claude/hooks/user-prompt-submit.sh

GUARDRAILS_DIR="${GUARDRAILS_PATH:-$HOME/.guardrails}"
KEYWORDS=$(echo "$1" | grep -oP '[\x{4e00}-\x{9fff}\w]{2,}' | head -5)

if [ -n "$KEYWORDS" ]; then
    RESULTS=$(cd "$GUARDRAILS_DIR" 2>/dev/null && rg -l "$KEYWORDS" raw/ compiled/ 2>/dev/null | head -3)
    if [ -n "$RESULTS" ]; then
        echo ""
        echo "[Guardrails 相關知識]"
        for f in $RESULTS; do
            head -8 "$GUARDRAILS_DIR/$f" 2>/dev/null
            echo "---"
        done
    fi
fi
```

---

*最後更新：2026-04-16*