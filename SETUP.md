# Guardrails Setup Guide

5 分鐘建置你的 AI 百科。

## 前置需求

- Python 3.10+
- Git

不需要 Supabase、不需要 Ollama、不需要任何付費服務。

---

## 一鍵安裝

```bash
curl -sSL https://raw.githubusercontent.com/zycaskevin/guardrails-knowledge/main/scripts/guardrails_setup.sh | bash
```

或手動安裝：

```bash
# 1. Clone
git clone https://github.com/zycaskevin/guardrails-knowledge.git ~/.guardrails
cd ~/.guardrails

# 2. 建立目錄結構
mkdir -p L0-identity L1-core-facts L2-context/recent-sessions L3-knowledge
mkdir -p raw compiled/axioms compiled/concepts compiled/techniques compiled/workflows compiled/errors compiled/comparisons

# 3. 從模板建立初始檔案
cp templates/L0-identity.md L0-identity/identity.md
cp templates/L1-core-facts.md L1-core-facts/current-projects.md
```

---

## 初始設定

### Step 1：填寫身份（L0）

編輯 `L0-identity/identity.md`，填入你的資訊：

```yaml
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
- 時區

## 溝通偏好
- 語言
- 格式偏好

## 技術背景
- 使用什麼 AI 工具
- 技術棧

## 核心價值
- 你做事的方式
```

### Step 2：填寫核心事實（L1）

編輯 `L1-core-facts/current-projects.md`，列出你正在做的事。

### Step 3：加入第一條知識（L3）

在 `raw/` 資料夾建一個 .md 檔案：

```yaml
---
title: "知識標題"
category: "technique"
layer: 3
tags: ["tag1", "tag2"]
trust: 0.8
source: "20260417"
created: "2026-04-17"
status: "active"
---

# 知識標題

你踩過的坑、做過的決策、驗證過的方案。
```

### Step 4：執行編譯器

```bash
python3 scripts/guardrails_compiler.py
```

這會：
- 把 raw/ 的知識編譯到 compiled/（AAAK 6x 壓縮）
- 自動 git commit（方便回滾）
- 跑 Lint 健康檢查

---

## 讓 AI 讀取你的百科

### Hermes Agent
自動讀取（已內建）

### Claude Code
1. 把 `L0-identity/identity.md` 和 `L1-core-facts/current-projects.md` 的內容複製到你的 `CLAUDE.md`
2. AI 需要深度知識時搜尋 `compiled/` 或 `raw/`

### 任何 AI
讀 `README.md` 了解架構 → 讀 L0 → 讀 L1 → 關鍵字搜尋 raw/compiled/

---

## 升級到 Full 版（可選）

需要：
- Supabase 免費帳號
- Python 套件：`urllib3`, `hashlib`

```bash
# 設定 .env
cp .env.example .env
# 填入 SUPABASE_URL 和 SUPABASE_SERVICE_KEY

# 執行完整編譯（含雲端同步）
python3 scripts/guardrails_compiler.py
```

Full 版額外功能：
- pgvector 語意搜尋
- 多裝置同步
- 跨語言搜尋（中/英/日）
- 矛盾偵測 + 信任分數
- content_log 文章追蹤

---

## 常見問題

**Q: 我已經有 Obsidian 筆記庫了，要遷移嗎？**
A: 不需要。Guardrails 可以和 Obsidian 共存。把 Obsidian vault 當 raw/ 來源，Guardrails 負責編譯和搜尋。

**Q: 一定要分四層嗎？**
A: L0+L1 是必要的（AI 每次都要知道你是誰）。L2+L3 可選，但強烈推薦——沒有它們，AI 就是從零推理。

**Q: 信任分數有什麼用？**
A: 當兩條知識互相矛盾時，AI 優先相信高分數的。用戶定義 = 1.0，驗證過 = 0.9，可信 = 0.7，未驗證 = 0.5。

**Q: Token 成本呢？**
A: L0+L1 每次注入約 500-800 token。L3 知識用 AAAK 壓縮，搜尋時只讀壓縮版，token 消耗是原文的 1/6。

---

*有問題歡迎開 GitHub Issue*