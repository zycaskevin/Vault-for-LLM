# Vault-for-LLM 繁體中文說明

**[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)**

> 給 LLM Agent 用的本地優先記憶層。
>
> Vault-for-LLM 會在你的專案裡建立一個可攜式 SQLite 知識庫。你可以用 Markdown 寫筆記，把它們編譯成可搜尋、可引用的結構化記憶，並透過 `vault` CLI 或 `vault-mcp` 讓 AI Agent 在對話中查詢。

---

## 為什麼需要它？

LLM Agent 很強，但大多數 Agent 每次開新 session 就會忘記上下文：決策、踩坑、使用者偏好、專案設定、除錯過程都要重新教一次。

Vault-for-LLM 解決的是這件事：

1. 你把重要知識寫成 Markdown。
2. `vault compile` 把它編譯進本地 SQLite。
3. Agent 需要時再搜尋，不用把所有內容塞進 prompt。
4. 支援 MCP 的 Agent 可以在對話中直接查知識庫。

它不是要取代你的筆記軟體，而是讓你的筆記**可以被 Agent 使用**。

---

## 核心原則

- **本地優先**：SQLite 是 source of truth；核心功能不需要雲端。
- **不用 embedding 也能跑**：先有關鍵字搜尋；語意搜尋是可選功能。
- **為 Agent 記憶設計**：把每次都要載入的事實，和需要時才搜尋的深知識分開。
- **定界讀取**：Document Map 讓 Agent 讀正確段落，而不是整篇文件塞進上下文。
- **可選同步**：Supabase 是可選的同步/遠端讀取目標，不是必要基礎設施。
- **Alpha、CLI 優先**：目前是開發者工具，API 與體驗仍在演進。

---

## 它能做什麼？

| 領域 | 能力 |
|---|---|
| 知識存儲 | 將 `raw/` Markdown 編譯進本地 SQLite |
| 搜尋 | 關鍵字搜尋、可選向量搜尋、混合搜尋 |
| Embedding | 可選 ONNX Runtime 或 Ollama |
| 記憶分層 | L0 身份、L1 核心事實、L2 近期上下文、L3 深知識 |
| 知識圖譜 | 自動推斷實體/關聯，支援圖譜擴展 |
| Document Map | 章節/主張導航，支援有行號範圍的 citation |
| MCP | `vault-mcp` 將 search/add/stats/map/read 工具暴露給相容 Agent |
| 品質工具 | lint、freshness、convergence、cross-validation、dedup、Search QA snapshot |
| 可選遠端同步 | Supabase sync scripts，適合團隊或遠端讀取 |
| 技能共享 | 實驗中的 `vault skill` 技能市場命令 |

---

## 架構

```text
L0 Identity        → 使用者/專案是誰；每次 session 載入
L1 Core Facts      → 穩定環境與專案事實；每次 session 載入
L2 Recent Context  → 近期決策、事故、工作上下文
L3 Deep Knowledge  → 經驗、API、架構、踩坑；需要時搜尋

Markdown raw/  →  vault compile  →  SQLite database  →  vault search / MCP tools
```

這樣可以讓 Agent 的 prompt 保持小，但需要時仍能查到深層記憶。

---

## 安裝

### 目前 Alpha：從原始碼安裝

Vault-for-LLM 目前尚未發布到 PyPI。請先從 GitHub repository 安裝：

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

vault doctor
```

### 可選：語意搜尋

基礎安裝已支援關鍵字搜尋。如果要使用本地 ONNX embedding：

```bash
pip install -e ".[semantic]"
vault install-embedding --model mix
```

或使用既有 Ollama embedding model：

```bash
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
```

### 可選：MCP server

```bash
pip install -e ".[mcp]"
vault-mcp --project-dir /path/to/your/project
```

---

## 快速開始

```bash
# 1. 在專案裡建立 vault
vault init

# 2. 新增第一筆知識
vault add "First lesson" --content "The bug was caused by X. The fix was Y."

# 3. 編譯 Markdown 進本地 SQLite vault
vault compile

# 4. 之後搜尋
vault search "what caused the bug"
```

你也可以直接把 Markdown 檔放到 `raw/`，再執行 `vault compile`。

範例：

```markdown
---
title: "Postgres migration pitfall"
category: "error"
layer: L3
tags: ["postgres", "migration"]
trust: 0.8
source: "project-notes"
created: "2026-05-16"
---

# Postgres migration pitfall

記錄壞在哪裡、為什麼壞、下次怎麼避免。
```

---

## 目錄結構

```text
your-project/
├── L0-identity/              # 使用者或專案身份，每次 session 載入
│   └── identity.md
├── L1-core-facts/            # 穩定事實，每次 session 載入
│   └── current-projects.md
├── L2-context/               # 近期上下文、決策、事故
│   └── recent-sessions/
├── L3-knowledge/             # 可搜尋的深知識
├── raw/                      # 原始 Markdown 知識條目
├── compiled/                 # 編譯/壓縮後的知識 artifact
├── guardrails.db             # vault 產生的本地 SQLite database
└── templates/                # 起始模板
```

### 歷史命名說明

部分內部模組與檔名仍沿用歷史名稱 `guardrails_lite` / `guardrails.db`。公開產品名稱是 **Vault-for-LLM**，公開命令是 `vault` 與 `vault-mcp`。這些舊命名會在 alpha 階段為了相容性暫時保留。

---

## CLI 指令參考

| 指令 | 用途 |
|---|---|
| `vault init` | 初始化專案 vault |
| `vault doctor` | 檢查本地環境與可選依賴 |
| `vault add "Title" --content "..."` | 新增知識條目 |
| `vault add "Title" --file note.md` | 從 Markdown 檔新增條目 |
| `vault import long-doc.md` | 匯入並分塊長文件 |
| `vault compile` | 編譯 `raw/` 到 SQLite + `compiled/` |
| `vault search "query"` | 搜尋知識庫 |
| `vault search "query" --graph-expand 2` | 搜尋並加上圖譜擴展 |
| `vault list` | 列出知識條目 |
| `vault stats` | 顯示 vault 統計 |
| `vault lint` | 執行品質檢查 |
| `vault map build` | 建立/回填 Document Map |
| `vault map show <id>` | 顯示條目的章節地圖 |
| `vault map read <id> --lines 10-30` | 讀取定界行號範圍 |
| `vault graph build` | 建立推斷知識圖譜 |
| `vault graph show` | 顯示圖譜統計 |
| `vault converge` | 實驗性自問收斂檢查 |
| `vault cross-validate` | 實驗性跨模型驗證 |
| `vault freshness` | 實驗性新鮮度/複習排程 |
| `vault dedup` | 偵測或合併重複條目 |
| `vault search-qa run` | 執行 Search QA metrics snapshot |
| `vault skill search "query"` | 搜尋實驗性技能市場條目 |

執行 `vault <command> --help` 可查看各指令參數。

---

## MCP 整合

安裝 MCP extras 並啟動 server：

```bash
pip install -e ".[mcp]"
vault-mcp --project-dir /path/to/your/project
```

MCP server 設定範例：

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

目前 MCP tools 包含：

- `vault_search`
- `vault_add`
- `vault_stats`
- `vault_map_show`
- `vault_read_range`
- 若設定了可選 Supabase sync，還有 `vault_remote_map_show` / `vault_remote_read_range`

---

## 可選 Supabase sync

Vault-for-LLM 的核心用法是本地-only。Supabase 支援是給需要團隊同步或遠端讀取的人使用。

本地 SQLite database 仍是 source of truth；Supabase 是同步目標。

```bash
# alpha 階段請手動安裝
pip install supabase

# 設定 Supabase credentials 後，依需求執行 sync script
python scripts/sync_to_supabase.py --document-map
```

---

## 目前成熟度

Vault-for-LLM 仍是 alpha：

- 公開 CLI 是 `vault`，但部分內部名稱仍含 `guardrails`。
- convergence、cross-validation、Search QA、skills、Supabase sync 等進階功能仍在演進。
- 預設安裝方式是從原始碼本地開發。
- 穩定版前，API 與 schema 可能變動。

如果你想走最穩路線，先從這四個指令開始：

```bash
vault init
vault add
vault compile
vault search
```

---

## 開發

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

部分測試路徑會需要 ONNX、MCP 或 Supabase 等可選依賴。

---

## 授權

MIT
