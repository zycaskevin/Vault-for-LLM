# Vault-for-LLM 繁體中文說明

**[繁體中文](README.zh-Hant.md) | [简体中文](README.zh-CN.md) | [English](README.md)**

> 🧠 本地優先、開源的四層分層知識管理系統，讓任何 LLM Agent 擁有持久、可搜尋的記憶。
> 零雲端依賴。零 Docker。零 PyTorch。`pip install` 即可使用。

---

## 這是什麼？

Vault-for-LLM 是一個專為 LLM Agent 設計的**四層分層知識庫**。它完全在本機運行，使用 SQLite + sqlite-vec + ONNX 嵌入模型，讓你的 AI Agent 能夠記住東西。

### 核心特色

- **四層架構**（L0–L3）— 結構化知識注入
- **混合搜尋**：關鍵字 + 語意向量搜尋（ONNX，無需 GPU）
- **知識圖譜**：自動推斷實體與關係邊，支援 BFS 擴展
- **AAAK 壓縮**：6 倍壓縮率，大幅減少 token 消耗
- **信任評分**：每筆知識都有信心分數（0.0–1.0）
- **品質檢查**：自動 lint 與矛盾偵測
- **CLI 優先**：20+ 指令，完整管理生命週期

---

## 架構說明

```
L0 身份層      → 使用者是誰（每次對話注入）
L1 核心事實    → 環境與活躍專案（每次對話注入）
L2 動態情境    → 近期決策與除錯記錄（每日自動更新）
L3 深度知識    → 架構、技術、經驗（按需搜尋）
```

### 為什麼要分層？

| 層級 | 載入時機 | Token 成本 | 範例 |
|------|----------|-----------|------|
| L0 | 每次對話 | 極低（<100） | 使用者名稱、角色、偏好 |
| L1 | 每次對話 | 低（<500） | 作業系統、安裝工具、活躍專案 |
| L2 | 需要時 | 中（<2000） | 昨天修了什麼 bug、最近的技術決策 |
| L3 | 按需搜尋 | 按需 | 某框架的踩坑筆記、API 用法 |

---

## 快速開始

```bash
# 安裝
pip install -e .

# 初始化專案
vault init

# 新增知識
vault add "我的第一筆知識" --content "今天學到的東西"

# 編譯（raw/ → 資料庫 + compiled/）
vault compile

# 搜尋
vault search "我要找的關鍵字"

# 健康檢查
vault doctor
```

詳細安裝選項請參閱 [INSTALL.md](INSTALL.md)。

---

## 目錄結構

```
你的專案/
├── guardrails.yaml          ← 專案設定（vault init 自動產生）
├── L0-identity/             ← 使用者身份（每次對話注入）
│   └── identity.md
├── L1-core-facts/           ← 核心事實（每次對話注入）
│   └── current-projects.md
├── L2-context/              ← 動態情境（每日自動更新）
│   └── recent-sessions/
│       └── current.md
├── L3-knowledge/            ← 深度知識（按需搜尋）
├── raw/                     ← 原始知識輸入（你的 .md 檔案放這裡）
├── compiled/                ← AAAK 壓縮備份（自動產生）
└── templates/               ← L0/L1/L2 乾淨模板
```

---

## AI 整合指南

### 通用 LLM Agent

1. 閱讀 `L0-identity/identity.md` 了解使用者
2. 閱讀 `L1-core-facts/current-projects.md` 了解現況
3. 使用 `vault search "查詢"` 進行語意搜尋

### Claude Code / Cursor / 任何 AI IDE

1. 將 `CLAUDE.md` 複製到專案根目錄
2. 深度知識搜尋：使用 `rg "關鍵字" raw/ compiled/`
3. 或使用 `vault search "查詢"`

---

## CLI 指令參考

| 指令 | 說明 |
|------|------|
| `vault init` | 初始化新專案 |
| `vault doctor` | 環境健康診斷 |
| `vault add "標題" --content "內容"` | 新增知識條目 |
| `vault add "標題" --file 檔案.md` | 從檔案匯入 |
| `vault import 長文.md` | 匯入長文件（自動分塊） |
| `vault compile` | 編譯 raw/ → 資料庫 + compiled/ |
| `vault search "查詢"` | 搜尋（自動：關鍵字 + 語意） |
| `vault search "查詢" --graph-expand 1` | 搜尋 + 知識圖譜擴展 |
| `vault list` | 列出所有條目 |
| `vault stats` | 顯示資料庫統計 |
| `vault lint` | 執行品質檢查 |
| `vault dedup` | 偵測語意重複知識 |
| `vault dedup --dry-run` | 預覽合併計畫（不修改資料） |
| `vault dedup --merge` | 自動合併重複（保留高信任度） |
| `vault graph build` | 建立知識圖譜 |
| `vault graph show` | 顯示圖譜摘要 |
| `vault graph export --format mermaid` | 匯出 Mermaid 圖譜 |
| `vault graph expand <id>` | 從指定節點展開圖譜 |
| `vault config set <key> <value>` | 設定配置（如嵌入後端） |

---

## MCP Server（Claude Code / Cursor / OpenClaw）

讓 AI Agent 直接透過 MCP 協定操作知識庫：

```bash
# 安裝 MCP 依賴
pip install "guardrails-knowledge[mcp]"

# 啟動（在含有 guardrails.db 的專案目錄執行）
vault-mcp

# 或指定路徑
vault-mcp --project-dir /path/to/your/project
```

加入 Claude Code 設定（`~/.claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "vault": {
      "command": "vault-mcp",
      "args": ["--project-dir", "/path/to/your/project"]
    }
  }
}
```

可用工具：`vault_search`、`vault_add`、`vault_get`、`vault_list`、`vault_stats`

---

## 知識檔案格式

所有 `.md` 檔案使用 YAML frontmatter：

```yaml
---
title: "知識標題"
category: "concept|technique|workflow|lesson|error|comparison"
layer: "L0|L1|L2|L3"
tags: ["標籤1", "標籤2"]
trust: 0.0-1.0
source: "來源說明"
created: "YYYY-MM-DD"
---
```

### 信任評分指南

| 範圍 | 含義 |
|------|------|
| 0.9+ | 經實際驗證 |
| 0.7–0.8 | 來自文件，高信心 |
| 0.5–0.6 | 一般知識，尚未驗證 |
| < 0.3 | 未驗證，需要審核 |

---

## 編譯器

```bash
vault compile
```

執行流程：
- `raw/` → 資料庫（以內容雜湊去重）
- `raw/` → `compiled/`（AAAK 6 倍壓縮）
- 自動 L2 更新 + lint 健康檢查 + git commit

---

## 技術棧

| 元件 | 技術 | 原因 |
|------|------|------|
| 資料庫 | SQLite + sqlite-vec | 零設定、可攜帶、向量搜尋 |
| 嵌入模型 | ONNX Runtime（~150MB） | 不需 PyTorch/GPU |
| 搜尋 | 混合（關鍵字 + 向量） | 兩全其美 |
| 圖譜 | SQLite（實體 + 邊） | 輕量關係追蹤 |
| 壓縮 | AAAK 格式 | 6 倍大小縮減 |

---

## 系統需求

- Python 3.10+
- ~150MB（ONNX 嵌入模型，選用）
- 不需要 GPU、不需要 Docker、不需要雲端帳號

---

## 授權

MIT License — 詳見 [LICENSE](LICENSE)。

---

*為開發者打造 — 讓你的 AI Agent 真正記住事情。*
