# Vault-for-LLM 繁體中文說明

**[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)**

> 給 LLM Agent 用的本地優先、以生產實務為目標的記憶工作流。
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

更大的 roadmap 是：Vault-for-LLM 是記憶核心，Hermes Agent、OpenClaw、
Claude Code、Codex、n8n、機器人、車上助理、智能家居 Agent 是手，模型是
運算工具。詳見 [vision document](docs/vision.md)。

它也不是只為文件設計，而是以使用者為中心設計。Vault 可以保存專案知識，也可以承載經過審核的使用者側寫：穩定工作偏好、溝通邊界、近期狀態摘要、長期互動模式，讓 Agent 不用每個 session 都像第一天認識你。這些側寫記憶仍然要被治理：原始私密互動留在私有層，可信任 Agent 只共享短版、審核過的摘要。

更自動化的用法，是替使用者設計 1-2 個專屬記憶 Agent：

- **Profile agent**：維護使用者穩定側寫、偏好、照顧摘要與不同 Agent 的互動邊界，不暴露原始私密聊天。
- **Dream / forgetting agent**：定期做 dream report、去重、標記過期、建議 promote/archive，讓資料庫會整理，也會忘掉低價值或已過期的上下文。

這讓 Vault 不只適合今天的聊天 Agent。未來如果要接具身 Agent、長期助理，或更泛用的 world-model workflow，同一套治理結構也能同時保存使用者脈絡、專案狀態、有來源的知識，以及安全的記憶淡忘。

核心設計原則是 **Progressive Memory Disclosure**：Agent 先看到小而安全的摘要，再逐層打開 topic map、搜尋候選、定界來源段落；只有任務和權限真的需要時，才讀 raw 或 archived memory。這樣記憶金庫長大後仍然能保持高效、可審查、可回溯。

如果想看它和 Mem0、Letta/MemGPT、Zep、LangGraph memory 的定位差異，請看 [memory system comparison](docs/memory_system_comparison.md)。白話版：Vault-for-LLM 偏向本地、可審查、候選制的專案記憶，重視 retrieval QA 與定界引用；如果你需要託管式個人化記憶、完整 stateful-agent runtime，或企業級 temporal graph memory，其他系統可能更合適。

如果想看它和 PageIndex / Headroom 這類相鄰系統的關係，請看
[PageIndex and Headroom comparison](docs/comparisons/pageindex_headroom.md)。
白話版：Vault 可以借鑑 PageIndex 的文件樹導航，也可以選擇性搭配
Headroom 的 context budget，但核心仍是本地、可治理、可引用的專案記憶。

---

## 核心原則

- **本地優先**：SQLite 是 source of truth；核心功能不需要雲端。
- **不用 embedding 也能跑**：先有關鍵字搜尋；語意搜尋是可選功能。
- **為 Agent 記憶設計**：把每次都要載入的事實，和需要時才搜尋的深知識分開。
- **治理式讀取**：共用 vault 的 Agent 可傳 `agent_id` 和敏感度上限，先過濾 private/restricted memory 再做定界讀取。
- **定界讀取**：Document Map 讓 Agent 讀正確段落，而不是整篇文件塞進上下文。
- **可選同步**：Supabase 是可選的同步/遠端讀取目標，不是必要基礎設施。
- **CLI 優先**：這是開發者工具；核心本地流程穩定，進階 QA、語意與同步工作流仍會演進。

---

## 可用在哪些 Agent 系統？

Vault-for-LLM 不是綁死在某一個 Agent runtime 上。它的共通介面很簡單：
本地 Markdown + SQLite，透過 CLI 和可選的 stdio MCP 給不同系統使用。

| 系統 | 使用方式 |
|---|---|
| Hermes Agent / Nancy | 設定 `vault-mcp`，讓 Agent 使用 search/read/propose tools；用 CLI 跑 dream report、backup、onboarding benchmark。 |
| OpenClaw | 使用 repo 內建的 [`integrations/openclaw/`](integrations/openclaw/) adapter，註冊 `vault_search`、`vault_read_range`、`vault_memory_propose`、`vault_stats`；也可走 generic MCP。 |
| n8n | 在 Execute Command node 呼叫 `vault` CLI，或包成內部 HTTP service / MCP bridge，放進 workflow 自動化。 |
| Codex | 在 repo/workspace 裡直接使用 CLI；若所用 Codex surface 支援本機 MCP，也可接 `vault-mcp`。 |
| OpenCode | 支援 MCP 時走和 Claude Code/Codex 相同的 generic local MCP；也可在 shell-capable session 裡呼叫 CLI。 |
| Claude Code | 把 `vault-mcp` 設成 local stdio MCP server，或在可跑 shell 的 session 中使用 CLI。 |
| 任何 MCP-compatible Agent | 執行 `vault-mcp --project-dir <project>`，照 `vault_search` → `vault_read_range` → 帶來源回答的流程使用。 |

更多設定範例請看 [Agent Integrations](docs/agent_integrations.md)，裡面包含 OpenClaw adapter、n8n、Codex、Claude Code 與 generic MCP 的接法。

### 給 Agent 的安裝契約

很多 Vault-for-LLM 的安裝和 repo 修改會由 Agent 代做，不一定是人手動照 README 操作。Agent 在設定 MCP、選資料庫 scope、或寫入記憶前，應先讀：

- [`AGENTS.md`](AGENTS.md)：給 coding agent 的簡短操作守則。
- [`agent_manifest.json`](agent_manifest.json)：機器可讀的安裝、scope、安全、runtime、驗證資訊。
- [`docs/agent_install.md`](docs/agent_install.md)：給 Hermes、Codex、Claude Code、OpenClaw、OpenCode、n8n 和其他 Agent 的短版安裝 runbook。

人類使用者不需要手動照每條指令安裝。你可以直接對 Agent 說：

```text
幫這個專案安裝 Vault-for-LLM。先讀 AGENTS.md 和 agent_manifest.json，
問我要 shared 還是 private vault，問我要開哪些 optional features，
選到 optional features 後問我要不要現在安裝對應 dependencies，
如果選 semantic，問我要不要下載本地 ONNX embedding model，
問我有沒有既有 Obsidian vault 要匯入，設定 CLI/MCP，需要時做第一次
Obsidian 匯入，再問我要不要開後續自動同步，詢問長 tool output 是否需要
Headroom context 壓縮，問我要不要產生 Profile / Dream / Forgetting
memory-agent 指引，最後跑 search/read/propose smoke test。
```

Hermes Agent、Codex、OpenCode、Claude Code、OpenClaw 和其他 MCP-capable agent 可以共用同一套安裝架構：

```text
選 projectDir -> 選 optional features -> 詢問 Obsidian -> 安裝 vault -> 設定 CLI/MCP -> 第一次匯入/同步確認 -> 驗證 search/read/propose
```

各 runtime 的 adapter 應該保持很薄；真正穩定的契約是共同的
`projectDir`、`vault` CLI、`vault-mcp`，以及候選制記憶流程。

Agent 安裝時也應該詢問要不要開可選功能，而不是全部預設裝上：

| 功能 | 預設 | 安裝指令 | 什麼時候問 |
|---|---|---|---|
| `core` | 是 | `python -m pip install vault-for-llm==0.6.34` | 永遠需要：本地 Markdown、SQLite、keyword search。 |
| `mcp` | MCP-capable agent 建議開 | `python -m pip install "vault-for-llm[mcp]==0.6.34"` | runtime 可以接 local stdio MCP tools。 |
| `obsidian_import` | 否 | core CLI 內建 | 使用者已經有 Obsidian vault，想讓 Agent 也能查這些筆記。 |
| `semantic` | 否 | `python -m pip install "vault-for-llm[semantic]"` | 使用者想要 embedding-backed semantic/hybrid search。 |
| `supabase` | 否 | `python -m pip install "vault-for-llm[supabase]"` | 使用者想要 optional remote sync/read path。 |
| `headroom` | 否 | `python -m pip install headroom-ai` | Agent 常讀很長的 logs、terminal output 或大量檢索內容，需要送進 LLM 前先做可選壓縮。 |
| `memory_agents` | 否 | 不需額外依賴 | 使用者想啟用 Profile / Dream / Forgetting agent 指引，預設 report-only / candidate-only。 |
| `dev` | 否 | `python -m pip install -e ".[dev]"` | source checkout、benchmark、PR 或 release validation。 |

選好 optional features 後，`vault setup-agent` 可以直接替 Agent 安裝對應的
Python 依賴。互動模式會先詢問是否現在安裝；非互動模式請明確加
`--install-optional-deps`。如果選了 semantic，也可以加
`--install-embedding-model mix`，下載並設定預設的本地 ONNX embedding model。

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --features core,mcp,semantic,supabase,headroom \
  --language zh-Hant \
  --install-optional-deps \
  --install-embedding-model mix \
  --supabase-setup simple \
  --supabase-sync cron \
  --json
```

不要偷偷開 semantic、Supabase 或 Headroom extras；semantic 和 Supabase 會增加較重的依賴、模型/provider 設定，或遠端憑證；Headroom 只有在真的有 context window 或 token 壓力時才需要。若開啟 Headroom，正式引用仍要回到原始 `vault_read_range` 內容，不要引用壓縮摘要。

對 Obsidian，Agent 應主動詢問 vault 路徑，先跑 `--dry-run`，使用者確認後做第一次匯入，再詢問要不要用 cron、LaunchAgent、n8n 或 host agent 排程同一條 `vault import obsidian --compile` 來做後續自動同步。

### 選擇 Vault project scope

Vault-for-LLM 綁定的是 `project-dir`，不是某一個 Agent runtime：

```text
一個 project directory = 一個 vault.db
```

如果 Hermes、OpenClaw、Codex、Claude Code、n8n 都指向同一個
`--project-dir`，它們就共用同一份 governed project memory。指向不同資料夾時，就會使用彼此隔離的資料庫。

| Scope | 適合情境 | project-dir 範例 |
|---|---|---|
| Shared project vault | 多個可信 Agent 協作同一份已確認的專案知識 | `~/Vaults/my-project` |
| Agent-private vault | 某個 Agent 做實驗、比較吵、或不完全可信 | `~/.openclaw/workspace/vault-project` |
| Domain/customer vault | 不同客戶或業務資料需要隔離 | `~/Vaults/clinic-customer-service` |
| Temporary vault | Demo、測試、benchmark | `/tmp/vault-benchmark-*` |

`/tmp/...` 是一次性測試工作目錄，不是套件真正安裝的位置，也不適合拿來當長期共享記憶庫。正式共用時，請選穩定路徑，例如 `~/Vaults/my-project`，並讓每個可信 Agent 都指向同一個 `project-dir`。若要跑排程工作，Python virtualenv 也應放在穩定路徑，例如 `~/.hermes/venvs/vault-for-llm/`；放在 `/tmp/...` 的 venv 重開機後可能消失。

共用 vault 時，建議讓 Agent 使用 `vault_memory_propose`，不要直接寫入正式記憶，避免多 Agent 一起把 active memory 弄亂。

如果 Agent 跑在不同主機上，本機 `project-dir` 就不能直接共用。這時候可選的 Supabase sync 可以作為遠端共享讀取/同步層：每台主機保留自己的本地 SQLite vault，再把已核准的知識、Document Map、摘要、hash 和 metadata 同步到同一個 Supabase project。這樣 Hermes 在一台機器、Codex 在另一台、n8n 在伺服器上，也能讀到共同的 project-memory view；但 Supabase 仍然不是本地核心功能的必要依賴。

---

## 目前原始碼狀態：v0.6.34

目前 source tree 已包含 v0.6.34 的 agent integration、OpenClaw adapter、Obsidian 匯入同步、benchmark proof 與品質 gate，並保留候選制記憶 workflow 與搜尋增強。白話說，Vault 現在不像一個誰都能亂塞紙條的抽屜，比較像一間有櫃台的小圖書館：

- **候選制記憶**：Agent 想記東西時，先交到櫃台（`vault remember` / `vault_memory_propose`），由 privacy、duplicate、metadata、quality gates 檢查，再決定能不能上架。
- **比較安全的召回**：keyword search 有弱匹配門檻，應該找不到的 query 比較不會硬抓一筆不相關記憶回來；可用 `--min-score` 調整。
- **Search QA hard negatives**：固定題庫可以寫 `expected_no_results: true`，同時檢查「該找到的有沒有找到」和「不該找到時有沒有亂認親」。
- **CI Search QA gate**：release readiness CI 會跑公開 fixture，檢查 top-k、MRR、no-result precision、citation-policy 與 mode gate。
- **Dream 先出報告再整理**：`vault dream` 先寫 report / plan；`apply_safe` 只做很小的 metadata 修正，並保留 backup/rollback 路徑。
- **有 guardrail 的語意工作流**：可選 semantic vectors、provider validation、persistent embedding cache，以及 CI/本機用 deterministic hash smoke tests。
- **明確的 DB schema status/migration**：用 [`vault db status/migrate`](docs/db_migrations.md) 檢查並執行 idempotent SQLite migrations。
- **本地 SQLite backup/verify/restore**：用 [`vault db backup/verify-backup/restore`](docs/db_backup_restore.md) 建立、驗證、還原備份；restore 前會拒絕非 Vault 或格式壞掉的 DB。
- **Release gates**：README command smoke、wheel smoke、version parity、secret scan、full-history privacy scan、artifact audit、public-boundary checks。

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
| MCP | `vault-mcp` 將 search/add/stats/map/read 與候選制記憶工具暴露給相容 Agent（[MCP 記憶流程](docs/mcp_memory_workflow.md)） |
| 記憶整理器 | `vault remember`、`vault promote`、MCP propose/promote 工具，讓 autonomous memory write 先經過 gate |
| Dream 報告 | `vault dream` 產生 report-first 記憶整理摘要，找出過期、重複、不完整或 metadata 弱的知識（[Dream workflow](docs/dream_workflow.md)） |
| 品質工具 | lint、freshness、convergence、cross-validation、dedup、Search QA snapshot、semantic smoke/warm workflow |
| Repo 治理 | source checkout 內的公開邊界 gate、artifact audit、safe-only cleanup helper |
| Agent 整合 | Hermes Agent、OpenClaw、n8n、Codex、Claude Code 與 generic MCP-compatible agents 的 CLI/MCP 使用方式（[整合指南](docs/agent_integrations.md)） |
| 未來檢索層 | Document Map 樹狀導航與 Headroom context-budget 整合設計（[tree navigation](docs/design/document_tree_navigation.md)、[Headroom notes](docs/integrations/headroom.md)） |
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

目前最穩定的路徑仍是核心流程：`vault init` → `vault add`/`vault remember` → `vault compile`/`vault promote` → `vault search` → `vault-mcp`。Autonomous agent 建議使用 `vault_memory_propose`，不要直接用 `vault_add` 寫入未審核記憶。

可以把 direct `vault_add` 想成讓人直接走進倉庫把紙條塞上架；它還是留給可信腳本使用，但日常 Agent 記憶應該先走候選櫃台：先提案、檢查 gates、再 promote。

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

L0-L3 描述的是記憶深度與用途，不是權限本身。多 Agent 安裝時，建議保留
L0-L3 的穩定骨架，再用 `scope`、`sensitivity`、`owner_agent`、
`allowed_agents`、`status`、`memory_type`、`expires_at` 這類 metadata
決定哪些要私有、哪些可共享、哪些能同步到 Supabase 或 Obsidian。詳見
[`docs/memory_governance.md`](docs/memory_governance.md)。

使用者人格側寫不要整包塞進 L0：最小身份放 L0，穩定工作偏好放 L1，近期狀態
或照顧摘要放 L2 並加過期時間，深層分析或原始私密互動放 private L3 或獨立
private vault。

### Agent 記憶生命週期

```text
對話 / 任務
  → 提出候選記憶
  → privacy + duplicate + metadata + quality gates
  → 列出 / 審查候選記憶
  → promote 已審核記憶
  → raw Markdown + SQLite active knowledge
  → search / map / read_range 召回
  → dream report 做整理與安全 metadata 修正
```

用故事講：Agent 先寫一張紙條，櫃台檢查它安不安全、有沒有重複、值不值得留下；通過後圖書館員才把它上架。之後 Agent 要用時，不是把整間圖書館搬進 prompt，而是查目錄、找到書架、只讀需要的段落。

---

## 安裝

### 從 PyPI 安裝

Vault-for-LLM `0.6.34` 已發布到 PyPI。

如果要讓 Agent 代為安裝，可以直接把這段交給 Hermes Agent、Codex、OpenCode、Claude Code、OpenClaw，或其他能執行本機指令的 Agent：

```text
幫這個專案安裝 Vault-for-LLM。使用 PyPI 套件 vault-for-llm[mcp]==0.6.34。
先詢問 vault database 要 shared、private、domain-specific 還是 temporary。
逐項詢問 MCP、semantic search、Supabase sync、Headroom context 壓縮與 dev/benchmark dependencies。
若我選了 optional features，詢問是否現在安裝對應 dependencies。
若我選了 semantic，詢問是否下載本地 ONNX embedding model。
詢問我是否有既有 Obsidian vault 要匯入。
執行 vault setup-agent，設定 CLI/MCP，Obsidian 先 dry-run 再匯入，
最後跑 search/read/propose smoke test。
```

手動安裝：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "vault-for-llm[mcp]==0.6.34"

vault setup-agent
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
vault-mcp --project-dir /path/to/your/project --tool-profile core
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

### 候選制 Agent 記憶

Autonomous agent 或未審核記憶，建議走候選流程。這是 PR27 後的推薦路徑：

```bash
vault remember "Memory title" \
  --content "Markdown memory content" \
  --reason "Why this is worth remembering"

vault candidates --include-gates

# 審核後
vault promote mem_xxxxxxxxxxxx --confirm
```

`vault candidates` 會列出待審記憶，預設不傾倒完整原文。MCP agent
應使用 `vault_memory_propose`、`vault_memory_candidates` 和 `vault_memory_promote`；詳見 [MCP 記憶流程](docs/mcp_memory_workflow.md)。

| Gate | 白話工作 |
|---|---|
| Privacy | 「這是不是像密鑰或私人資料？」 |
| Duplicate | 「我們是不是已經有這條或很像的記憶？」 |
| Metadata | 「至少有標題、內容、原因嗎？」 |
| Quality | 「這條記憶之後找得到、用得上嗎？」 |

### Search QA：檢查記憶召回健不健康

Search QA 像是給 vault 的小考。有些題目應該找到指定記憶，有些 hard-negative 題目應該什麼都找不到。這可以同時抓兩種錯：該記得卻忘了，以及不該回卻亂回。

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.zh-Hant.json \
  --mode keyword \
  --min-score 0.34 \
  --output /tmp/searchqa.json
```

Fixture 可用 `expected_no_results: true` 表示「這題正確答案是不要回任何結果」。詳見 [Search QA benchmarking guide](docs/search_qa_benchmarking.md)。

### Dream 記憶整理報告

```bash
vault dream --mode report --limit 50 --write-report
```

報告會寫到 `reports/dream/`。`apply_safe` 只會做很窄的 metadata 修正，並輸出 plan 與 backup path，若整理結果不符合預期可以 rollback。詳見 [dream workflow](docs/dream_workflow.md)。

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

Search QA 也可以跑 semantic/hybrid snapshot，但 QA 指令必須使用和 `vault semantic rebuild` 相同的 provider/model/dimension 與 vector kind。若使用 deterministic hash provider 做本機 smoke test，請在 rebuild 和 `vault search-qa run` 都傳入相同的 `--allow-hash --hash-dim N`；hash vectors 只驗證流程與 JSON 形狀，不代表真實語意搜尋品質。

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
| `vault setup-agent` | 啟動互動式 Agent 安裝精靈，並可產生 Obsidian 自動同步模板 |
| `vault doctor` | 檢查本地環境與可選依賴 |
| `vault add "Title" --content "..."` | 新增知識條目 |
| `vault add "Title" --file note.md` | 從 Markdown 檔新增條目 |
| `vault import long-doc.md` | 匯入並分塊長文件 |
| `vault import obsidian --vault /path/to/ObsidianVault --dry-run` | 預覽把既有 Obsidian notes 匯入 `raw/obsidian/` |
| `vault compile` | 編譯 `raw/` 到 SQLite + `compiled/` |
| `vault search "query"` | 搜尋知識庫；可用 `--min-score` 調整弱匹配抑制 |
| `vault search "query" --graph-expand 2` | 搜尋並加上圖譜擴展 |
| `vault export obsidian --vault /path/to/ObsidianVault --dry-run` | 匯出單向唯讀 Markdown notes，方便用 Obsidian 瀏覽 |
| `vault list` | 列出知識條目 |
| `vault remove <id> --confirm` | 刪除已確認 ID 的知識條目 |
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
| `vault search-qa run` | 執行 Search QA snapshot、hard-negative 檢查與召回指標 |
| `vault semantic rebuild` | 設定真 embedding provider 後重建 semantic vector rows |
| `vault semantic warm` | 預先計算 QA query embeddings，不寫入 vector rows |
| `vault semantic smoke` | 一次執行 rebuild、warm 與 Search QA smoke snapshot |
| `vault semantic cache-stats` / `vault semantic cache-prune` | 檢查或清理 durable embedding cache |
| `vault semantic startup` / `vault semantic daemon` | 執行 importable startup 或 bounded daemon lifecycle hooks |
| `vault skill search "query"` | 搜尋本機實驗性技能登錄條目 |

執行 `vault <command> --help` 可查看各指令參數。

### Agent 安裝精靈

使用 [`docs/agent_install.md`](docs/agent_install.md) 搭配 `vault setup-agent`
或別名 `vault install-agent`，可以讓 Agent 依序詢問資料庫 scope、optional
features（MCP、semantic、Supabase、Headroom、dev）、安裝語言、是否立即安裝已選功能的 dependencies、既有 Obsidian vault 路徑、是否做第一次匯入，以及是否產生 cron、LaunchAgent 或 n8n 自動同步模板。若選 semantic 並確認安裝依賴，精靈也可以下載並設定本地 ONNX embedding model。
`headroom` 是進階可選的 context 壓縮功能，不是 Vault 記憶治理的必要條件；只有在長 logs、大量 tool output 或 token 壓力明確時才建議開啟。

```bash
vault setup-agent

vault setup-agent \
  --non-interactive \
  --agent hermes \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --features core,mcp,obsidian_import \
  --obsidian-vault ~/Documents/ObsidianVault \
  --import-obsidian \
  --obsidian-sync all
```

### Obsidian 匯出

如果想讓人類用 Obsidian 瀏覽已編譯的 vault，又不想改動知識庫 source of truth，可以使用：

```bash
vault export obsidian \
  --vault /path/to/ObsidianVault \
  --category technique \
  --dry-run
```

這個匯出是刻意設計成單向、唯讀：只從 `vault.db` 讀取，將 Markdown notes 寫到 `00-Vault-Knowledge/`，包含 YAML frontmatter 與 `Vault #<id>` citation；不寫回 `raw/`、`compiled/`、SQLite，也不觸發任何 remote sync。重跑會覆蓋同一組穩定路徑，不會產生重複筆記。

### Obsidian 匯入與同步

如果使用者已經有很多 Obsidian 筆記，Agent 可以把這些 Markdown notes 反向匯入 Vault：

```bash
vault import obsidian \
  --vault /path/to/ObsidianVault \
  --dry-run

vault import obsidian \
  --vault /path/to/ObsidianVault \
  --compile
```

匯入流程會把使用者自己寫的 notes 複製到 `raw/obsidian/`，在 frontmatter 保留原始 Obsidian 路徑與 content hash，並預設跳過 `.obsidian/`、`.trash/`、`.git/` 和 `00-Vault-Knowledge/`。這樣 Vault 自己匯出的瀏覽用筆記，不會又被吃回來當成 source。

第一次接上既有 Obsidian vault 時，建議先跑 `--dry-run`。重跑是 idempotent：沒變的 note 會跳過，有變的 note 會更新同一個 raw path；只有加上 `--compile` 才會把匯入內容寫進 `vault.db`。如果要自動同步，可以用 cron、LaunchAgent、n8n 或 Agent installer 定期執行同一條命令；第一版不需要常駐 watcher。

---

## MCP 整合

安裝 MCP extras 並啟動 server：

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project --tool-profile core
```

安全提醒：`vault-mcp` 是本機 stdio MCP server，沒有內建網路認證或使用者層級存取控制。只把它配置給你信任、且可以讀寫該 `--project-dir` 的 Agent；若要給共享或實驗性 Agent 使用，建議使用獨立 project directory。

MCP server 設定範例：

```json
{
  "mcpServers": {
    "vault": {
      "command": "vault-mcp",
      "args": ["--project-dir", "/path/to/your/project", "--tool-profile", "core"]
    }
  }
}
```

MCP 可以用 tool profiles 控制暴露給 Agent 的工具數量：

| Profile | 適合情境 |
|---|---|
| `core` | 日常 Agent 使用，只暴露 `vault_search`、`vault_read_range`、`vault_memory_propose`、`vault_stats` |
| `review` | 需要審核並 promote 候選記憶 |
| `remote` | 需要讀取 Supabase 同步的跨主機記憶視圖 |
| `maintenance` | 排程或人工整理 freshness/convergence |
| `full` | 完整相容模式，包含 `vault_add` 等進階/舊工具 |

`full` 仍是預設值以維持相容；正式 Agent session 建議使用 `--tool-profile core` 以減少 tool schema token。

跨主機或 hosted agent 使用 `remote` profile 時，建議走
`vault_remote_search` → `vault_remote_map_show` → `vault_remote_read_range`。
`vault_remote_search` 會呼叫 [`docs/supabase_read_policy.sql`](docs/supabase_read_policy.sql)
提供的 `vault_search_readable` RPC，只回傳安全 metadata 與摘要，不把 service role key
或原始全文交給一般 Agent。

---

## 可選 Supabase sync

Vault-for-LLM 的核心用法是本地-only。Supabase 支援是給需要團隊同步或遠端讀取的人使用。

本地 SQLite database 仍是 source of truth；Supabase 是可選的同步/遠端讀取目標。遠端表名預設使用 Vault 品牌命名；接入既有私有 schema 時，可用 `VAULT_SUPABASE_*_TABLE` 環境變數覆蓋。

這對「不同主機上的 Agent 要共享記憶」特別有用。例如 Hermes Agent 在工作站、Codex 在筆電、OpenClaw 在另一台機器、n8n 在伺服器上，都可以各自保留 local Vault，同時把已確認的記憶同步到同一個 Supabase project，形成跨主機可讀的共同記憶視圖。

知識與技能同步採最小披露預設：metadata、summary、hash、Document Map rows 與 claims 會同步，但不包含完整 `content_raw`。只有明確加上 `--include-content` 時才會同步全文；若 privacy scan 判定為 fail，仍不會上傳全文。

預設先走 simple sync。RLS、多 Agent allow-list、Coze read-only access 屬於 advanced setup；需要時再看 [`docs/supabase_setup.md`](docs/supabase_setup.md)。

```bash
# 可選整合依賴
pip install supabase

# 設定 Supabase credentials 後，依需求執行 sync script
python -m scripts.sync_to_supabase --db /path/to/project/vault.db --document-map --health

# 或讓 setup-agent 產生每日 cron、LaunchAgent、n8n 範本
vault setup-agent \
  --non-interactive \
  --agent nancy \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,supabase \
  --language zh-Hant \
  --install-optional-deps \
  --supabase-setup simple \
  --supabase-sync cron \
  --json
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

## 搜尋品質（Search QA 基準測試）

### 證據摘要

Vault-for-LLM 量測的是 retrieval 與專案記憶 QA 層，不只是筆記資料庫。這些數字是證據探針，不是任何資料量都保證相同；換成更大或不同語料時，應該用 repo 內建 benchmark 重新測。

| Probe | 結果 | 注意事項 |
|---|---:|---|
| Repo onboarding fixture | Vault top-k/source/read-range guidance `28/28`；Codex transcript baseline `7/28`；Hermes/Nancy transcript baseline `3/28` | 28 題 source-aware project benchmark；private transcripts 不提交進 repo |
| Candidate-first memory | promotion 前 active-memory pollution 為 `0` | candidate proposals 不會自動進正式記憶 |
| LoCoMo hierarchical retrieval probe | official-scored categories 上 Any evidence@50 `97.7%`、All evidence@50 `90.5%` | 只代表 retrieval evidence score；不是官方 answer/judge leaderboard score |

可重跑的 repo fixture 與 exported-session 對照流程請看 [Agent Onboarding Benchmark](docs/agent_onboarding_benchmark.md)。

### Search QA fixture

Vault-for-LLM 提供確定性的 Search QA 基準測試，用於在程式碼變動前後量測檢索品質。以下結果使用英文 fixtures（`benchmarks/search_qa/basic.en.json`），對照全新編譯的資料庫（keyword/FTS5 模式）：

| 指標 | 數值 |
|---|---|
| total_cases | 3 |
| top-1 recall | 2/3 ≈ **67%** |
| top-k recall | 2/3 ≈ **67%** |
| no-result precision | 1.0 |
| Mean Reciprocal Rank | 0.67 |

基準測試涵蓋：
- `en_document_map_read_range` — "tool-gated reading map navigation read_range evidence" → 期望 "Tool-gated Reading"
- `en_citation_policy_boundary` — "citation policy boundary final answer support" → 期望 "Citation Policy Boundary"
- `en_no_result_control` — 隨機字串查詢 → 期望無結果（假陽性檢查）

繁體中文版 fixture（`basic.zh-Hant.json`）也存在，但因使用相同合成知識，指標相同。

在本機執行：

```bash
python -m pytest tests/test_search_quality_metrics.py -v
```

語義/混合模式需要 embedding 模型（CI smoke 用 `--allow-hash`）。
語義模式結果可能不同 — keyword search 是穩定的基準。

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

Apache-2.0
