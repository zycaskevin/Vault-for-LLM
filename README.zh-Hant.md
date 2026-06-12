# Vault-for-LLM 繁體中文說明

**[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)**

> 給 LLM Agent 用的本地優先、生產級記憶層。
>
> Vault-for-LLM 會把 Markdown 專案知識轉成可攜式 SQLite 記憶庫，讓 Agent 需要時再搜尋。它處理的是讓 Agent 記憶能長期運作的無聊但重要部分：搜尋 QA、定界讀取、語意搜尋、schema migration，以及可驗證的 backup/restore。

---

## 為什麼需要它？

LLM Agent 很強，但大多數 Agent 每次開新 session 就會忘記真正重要的上下文：決策、踩坑、使用者偏好、專案設定、除錯過程都要重新教一次。

Vault-for-LLM 解決的是這件事：

1. 你把重要知識寫成 Markdown。
2. `vault compile` 把它編譯進本地 SQLite。
3. Agent 需要時再搜尋，不用把所有內容塞進 prompt。
4. 支援 MCP 的 Agent 可以在對話中直接查知識庫。

它不是要取代你的筆記軟體，也不是另一個託管向量資料庫。它的目標是讓你的專案知識**可以被 Agent 使用、被量測、也能被備份還原**。

---

## 它和一般知識庫有什麼不同？

Vault-for-LLM 不只是另一個向量資料庫。它正在往 **Agent 記憶品質控制層** 演進：

- Agent 需要時，能不能找到正確記憶？
- 能不能只讀相關段落，而不是把整篇文件塞進上下文？
- 能不能判斷一條知識是否完整、過期、重複，或缺少操作細節？
- 團隊能不能在修改 retrieval 邏輯前後，量化搜尋品質有沒有退步？
- 可重複使用的 Agent workflow，能不能變成技能共享，而不是每個專案重新摸索？

換句話說：一般 RAG 重點是「把資料找出來」；Vault-for-LLM 更關心的是「這些記憶能不能被 Agent 正確使用」。

---

## 核心原則

- **本地優先**：SQLite 是 source of truth；核心功能不需要雲端。
- **不用 embedding 也能跑**：先有關鍵字搜尋；語意搜尋是可選功能。
- **為 Agent 記憶設計**：把每次都要載入的事實，和需要時才搜尋的深知識分開。
- **定界讀取**：Document Map 讓 Agent 讀正確段落，而不是整篇文件塞進上下文。
- **可選同步**：Supabase 是可選的同步/遠端讀取目標，不是必要基礎設施。
- **CLI 優先**：這是開發者工具；核心本地流程穩定，進階 QA、語意與同步工作流仍會演進。

---

## 0.5.0 新增內容

0.5.0 把 Vault-for-LLM 從「本地關鍵字搜尋記憶庫」升級成更接近生產級的本地記憶 workflow：

- **Search QA baseline**：用固定 query set 比較搜尋品質與延遲，避免 retrieval 改動只靠感覺。
- **FTS5/BM25 關鍵字搜尋**：SQLite 支援 FTS5 時使用更快的 BM25；FTS5 不可用或 CJK 命中不足時安全 fallback 到 `LIKE`。
- **有 guardrail 的語意工作流**：可選 semantic vectors、provider validation、persistent embedding cache，以及 rebuild/warm/smoke/startup/daemon 操作指令。
- **明確的 DB schema status/migration**：用 [`vault db status/migrate`](docs/db_migrations.md) 檢查並執行 idempotent SQLite migrations。
- **本地 SQLite backup/verify/restore**：用 [`vault db backup/verify-backup/restore`](docs/db_backup_restore.md) 建立、驗證、還原備份；restore 前會拒絕非 Vault 或格式壞掉的 DB。
- **Release gates**：README command smoke、wheel smoke、version parity、secret scan、full-history privacy scan、public-boundary checks。

語意搜尋是**刻意設計成可選功能**：基礎安裝只靠關鍵字搜尋也能跑。設定真 embedding provider 後，可用 [`vault semantic ...`](docs/semantic_search.md) 重建 vectors、預熱 cache、跑 smoke checks。Deterministic hash embeddings 必須明確加 `--allow-hash`，只供 CI/本機測試使用。

0.4.3 的 repo hygiene 工具請看 [`scripts/README.md`](scripts/README.md) 與 [`docs/repo_governance.md`](docs/repo_governance.md)。

---

## 它能做什麼？

| 領域 | 能力 |
|---|---|
| 知識存儲 | 將 `raw/` Markdown 編譯進本地 SQLite |
| 搜尋 | FTS5/BM25 關鍵字搜尋與 fallback、可選向量搜尋、混合搜尋 |
| Embedding | 可選 ONNX Runtime 或 Ollama、provider guard、durable cache workflow |
| 記憶分層 | L0 身份、L1 核心事實、L2 近期上下文、L3 深知識 |
| 知識圖譜 | 自動推斷實體/關聯，支援圖譜擴展 |
| Document Map | 章節/主張導航，支援有行號範圍的 citation |
| MCP | `vault-mcp` 將 search/add/stats/map/read 工具暴露給相容 Agent |
| 品質工具 | lint、freshness、convergence、cross-validation、dedup、Search QA snapshot、semantic smoke/warm workflow |
| Repo 治理 | source checkout 內的公開邊界 gate、artifact audit、safe-only cleanup helper |
| 可選遠端同步 | Supabase sync scripts，適合團隊或遠端讀取 |
| 本機技能登錄 | 實驗中的 `vault skill` 命令，用於在本機 Vault 內共享可重用 workflow；不是託管市場 |

---

## 品質工具發展方向

這些功能目前已經存在，但成熟度不同。核心本地指令是最穩定路徑；進階 QA、語意、同步與 skill registry 工作流仍會演進：

| 工具 | 用途 | 成熟度 |
|---|---|---|
| Document Map | 導航章節/主張，並用 citation 讀取定界原文範圍 | 可用，仍在演進 |
| Search QA | 跑固定查詢集，比較 retrieval 修改前後的指標 | 可用於 deterministic regression checks |
| 收斂檢查 | 判斷知識是否具備定義、操作流程、邊界案例 | 實驗性 |
| 交叉驗證 | 用不同模型家族驗證抽取出的 claims | 實驗性 / 依賴可選模型 |
| Freshness + dedup | 標記過期知識、偵測重複條目 | 實驗性 |
| 本機技能登錄 | 在本機 SQLite 中 push/search/pull 可重複使用的 Agent workflows | 實驗性 / 僅本機 |
| Repo hygiene scripts | 稽核 generated artifacts、清理安全 cache、發布前掃描 public PR diff | source-checkout helper |

目前最穩定的路徑仍是核心流程：`vault init` → `vault add` → `vault compile` → `vault search` → `vault-mcp`。

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

### 從 PyPI 安裝

> 發布備註：GitHub source tree 目前是 `0.5.0`，但 PyPI 可能仍停在較舊版本，直到 Trusted Publisher 發布設定修好。如果你需要最新 0.5.0 source features，請先使用下方 source install。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install vault-for-llm

vault doctor
```

### 可選：語意搜尋

基礎安裝已支援關鍵字搜尋。如果要使用本地 ONNX embedding：

```bash
pip install "vault-for-llm[semantic]"
vault install-embedding --model mix
```

或使用既有 Ollama embedding model：

```bash
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
```

### 可選：MCP server

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

安全提醒：`vault-mcp` 是本機 stdio MCP server，沒有內建網路認證或使用者層級存取控制。只把它配置給你信任、且可以讀寫該 `--project-dir` 的 Agent；若要給共享或實驗性 Agent 使用，建議使用獨立 project directory。

### 開發者：從原始碼安裝

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
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

### 可選：語意工作流

語意搜尋是刻意設計成可選功能。基礎安裝只靠關鍵字搜尋也能跑。設定真 embedding provider 後，主要操作指令是：

```bash
vault semantic rebuild --persist-cache
vault search "what caused the bug" --mode semantic
vault search "what caused the bug" --mode hybrid
vault semantic smoke --qa-file benchmarks/search_qa/basic.en.json --mode semantic --pretty
vault semantic cache-stats --pretty
```

`vault search --mode semantic` 會直接讀取已儲存的 `semantic_vectors`；`--mode hybrid` 會在可用時融合關鍵字與 stored semantic index，不可用時安全 fallback。

完整 lifecycle（`warm`、`cache-prune`、`startup`、`daemon`、以及只供測試用的 `--allow-hash`）請看 [`docs/semantic_search.md`](docs/semantic_search.md)。

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
├── vault.db             # vault 產生的本地 SQLite database
└── templates/                # 起始模板
```

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
| `vault export obsidian --vault /path/to/ObsidianVault --dry-run` | 匯出單向唯讀 Markdown notes，方便用 Obsidian 瀏覽 |
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
| `vault semantic rebuild` | 設定真 embedding provider 後重建 semantic vector rows |
| `vault semantic warm` | 預先計算 QA query embeddings，不寫入 vector rows |
| `vault semantic smoke` | 一次執行 rebuild、warm 與 Search QA smoke snapshot |
| `vault semantic cache-stats` / `vault semantic cache-prune` | 檢查或清理 durable embedding cache |
| `vault semantic startup` / `vault semantic daemon` | 執行 importable startup 或 bounded daemon lifecycle hooks |
| `vault skill search "query"` | 搜尋本機實驗性技能登錄條目 |

執行 `vault <command> --help` 可查看各指令參數。

### Obsidian 匯出

如果想讓人類用 Obsidian 瀏覽已編譯的 vault，又不想改動知識庫 source of truth，可以使用：

```bash
vault export obsidian \
  --vault /path/to/ObsidianVault \
  --category technique \
  --dry-run
```

這個匯出是刻意設計成單向、唯讀：只從 `vault.db` 讀取，將 Markdown notes 寫到 `00-Vault-Knowledge/`，包含 YAML frontmatter 與 `Vault #<id>` citation；不寫回 `raw/`、`compiled/`、SQLite，也不觸發任何 remote sync。重跑會覆蓋同一組穩定路徑，不會產生重複筆記。

---

## MCP 整合

安裝 MCP extras 並啟動 server：

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

安全提醒：`vault-mcp` 是本機 stdio MCP server，沒有內建網路認證或使用者層級存取控制。只把它配置給你信任、且可以讀寫該 `--project-dir` 的 Agent；若要給共享或實驗性 Agent 使用，建議使用獨立 project directory。

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

本地 SQLite database 仍是 source of truth；Supabase 是可選的同步/遠端讀取目標。遠端表名預設使用 Vault 品牌命名；接入既有私有 schema 時，可用 `VAULT_SUPABASE_*_TABLE` 環境變數覆蓋。

```bash
# 可選整合依賴
pip install supabase

# 設定 Supabase credentials 後，依需求執行 sync script
python scripts/sync_to_supabase.py --document-map
```

---

## 目前成熟度

Vault-for-LLM 是 CLI 優先的開發者工具：

- 核心本地指令（`init`、`add`、`compile`、`search`）是最穩定路徑。
- Search QA、FTS5/BM25 關鍵字搜尋、Document Map citation reads、語意 workflow 指令已可用，但仍會演進。
- Supabase sync、MCP、本機 skill registry 等可選整合在 1.0 前仍可能調整。
- 預設安裝方式已可使用 PyPI；從原始碼安裝主要給開發者使用。

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
