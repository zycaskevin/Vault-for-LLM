#!/bin/bash
# Guardrails 一鍵安裝腳本
# 用法：curl -sSL https://raw.githubusercontent.com/zycaskevin/guardrails-knowledge/main/scripts/guardrails_setup.sh | bash

set -e

GUARDRAILS_DIR="${GUARDRAILS_PATH:-$HOME/.guardrails}"

echo "🛡️ Guardrails 一鍵安裝"
echo "========================"
echo "安裝目錄：$GUARDRAILS_DIR"
echo ""

# 1. Clone if not exists
if [ -d "$GUARDRAILS_DIR" ]; then
    echo "✅ 目錄已存在，跳過 clone"
else
    echo "📥 Clone Guardrails..."
    git clone https://github.com/zycaskevin/guardrails-knowledge.git "$GUARDRAILS_DIR"
fi

cd "$GUARDRAILS_DIR"

# 2. Create directory structure
echo "📁 建立目錄結構..."
mkdir -p L0-identity L1-core-facts L2-context/recent-sessions L3-knowledge
mkdir -p raw/{code-snippets,content-analysis,research,system-logs,web-clips}
mkdir -p compiled/{axioms,concepts,techniques,workflows,errors,comparisons}
mkdir -p scripts

# 3. Copy templates if L0 doesn't exist
if [ ! -f "L0-identity/identity.md" ]; then
    if [ -f "templates/L0-identity.md" ]; then
        cp templates/L0-identity.md L0-identity/identity.md
        echo "✅ L0 身份模板已建立"
    else
        cat > L0-identity/identity.md << 'EOF'
---
title: "你的名字"
layer: 0
tags: ["identity"]
trust: 1.0
source: "user-defined"
---

# 你的名字

## 基本身份
- 角色/職業，城市
- 時區：Asia/Taipei (UTC+8)

## 溝通偏好
- 語言：繁體中文
- 格式：條列式優先、短句

## 技術背景
- 使用的 AI 工具
- 技術棧

## 核心價值
- 行動導向，不只是聊天
- 知識資產化：錯誤要記錄、經驗要傳承
EOF
        echo "✅ L0 身份模板已建立（預設）"
    fi
else
    echo "✅ L0 身份已存在，跳過"
fi

# 4. Copy L1 template if not exists
if [ ! -f "L1-core-facts/current-projects.md" ]; then
    if [ -f "templates/L1-core-facts.md" ]; then
        cp templates/L1-core-facts.md L1-core-facts/current-projects.md
        echo "✅ L1 核心事實模板已建立"
    else
        cat > L1-core-facts/current-projects.md << 'EOF'
---
title: "當前專案與任務"
layer: 1
category: "project"
tags: ["projects", "tech-stack"]
trust: 1.0
source: "user-defined"
updated: "2026-04-17"
---

# 當前專案與任務

## 活躍專案
（在這裡列出你正在做的事）

## 技術棧
| 類別 | 工具 | 備註 |
|------|------|------|
| AI | 你的 AI 工具 |  |

## 待處理
（在這裡列出待辦事項）
EOF
        echo "✅ L1 核心事實模板已建立（預設）"
    fi
else
    echo "✅ L1 核心事實已存在，跳過"
fi

# 5. Init git if not already
if [ ! -d ".git" ]; then
    git init
    echo "✅ Git 初始化完成"
fi

# 6. Create .gitignore
if [ ! -f ".gitignore" ]; then
    cat > .gitignore << 'EOF'
.compiler_state.json
*.pyc
__pycache__/
.env
.DS_Store
EOF
    echo "✅ .gitignore 已建立"
fi

# 7. Initial commit
git add -A
git commit -m "初始安裝：Guardrails 百科系統" 2>/dev/null || echo "✅ Git 已有 commit"

echo ""
echo "🎉 Guardrails 安裝完成！"
echo ""
echo "下一步："
echo "1. 編輯 L0-identity/identity.md 填入你的身份"
echo "2. 編輯 L1-core-facts/current-projects.md 填入你的專案"
echo "3. 在 raw/ 加入你的第一條知識"
echo "4. 執行 python3 scripts/guardrails_compiler.py 編譯"
echo ""
echo "詳細說明：cat $GUARDRAILS_DIR/SETUP.md"