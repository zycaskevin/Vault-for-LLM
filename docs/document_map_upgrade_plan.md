# Guardrails 百科 Document Map 升級計畫

> **For Hermes:** 如果要開始實作，先用 `subagent-driven-development` 拆任務；每個 Task 由 fresh subagent 執行，主 agent 只做規格審查與驗收。

**Goal:** 把 Guardrails 從「整篇知識條目搜尋」升級成「先看知識地圖、再工具化讀局部原文」的 Agent-native 百科。

**Architecture:** 借鑑 PageIndex 的核心洞察：Document Map + tool-gated reading。保留現有 SQLite + embedding + graph + Supabase 架構，不重寫系統；新增一層 `knowledge_nodes` 結構索引，讓 Agent 先讀 metadata/structure，再按行號讀取局部內容並帶引用回答。

**Tech Stack:** Python、SQLite、sqlite-vec、Guardrails Lite CLI、MCP server、Supabase sync、現有 Graph / Reranker / AAAK claims。

**狀態日期:** 2026-05-08

---

## 0. 現況盤點

### 已有能力

| 模組 | 現況 | 來源 |
|---|---|---|
| SQLite 主庫 | `guardrails.db` schema v5，363 條本地知識 | `mcp_guardrails_guardrails_stats` / SQLite |
| Supabase 同步 | local → Supabase 單向同步已可用 | `scripts/sync_to_supabase.py` |
| Search | keyword / vector / hybrid / graph_expand / rerank 已存在 | `guardrails_lite/guardrails_search.py` |
| AAAK claims | `simple_aaak_compress()` 已提取最多 10 條 claims + 行號 | `guardrails_lite/guardrails_compile.py` |
| Convergence / freshness | DB 欄位與腳本已存在；目前 346 complete / 6 partial / 10 unknown，avg freshness 0.858 | stats |
| Graph | 21,926 edges，479 entities；God nodes 是 `GuardrailsDB`、`EmbeddingProvider`、`GuardrailsGraph`、`GuardrailsSearch` | `graphify-out/GRAPH_REPORT.md` |

### 目前真正的缺口

1. **知識粒度仍偏「整篇」**：AAAK claims 有行號，但沒有可查詢的章節樹 / 節點索引。
2. **Agent 讀取不受控**：搜尋結果仍容易把整篇 content_preview 塞回上下文，沒有強制工具化局部讀取。
3. **引用能力不穩定**：best_claim 有行號來源，但回答流程沒有硬性要求 `line_start-line_end` citation。
4. **搜尋結果可解釋性不足**：知道哪篇相關，但不知道「哪一節、哪幾行」最相關。
5. **多來源同步風險**：MCP add 若不回寫本地 raw/db，會被 local sync 覆蓋；此點已有百科踩坑條目，但流程仍需產品化成守門機制。

---

## 1. 核心設計：Guardrails Document Map

### 1.1 什麼是 Document Map

每條百科知識不再只是一個 blob，而是拆成可導航地圖：

```text
Knowledge Entry
├── metadata
│   ├── title / layer / category / tags / trust / freshness
│   ├── summary / source / created_at / updated_at
│   └── content_hash
├── structure
│   ├── H1 / H2 / H3 節點
│   ├── 每個節點的 summary
│   ├── 每個節點的 line_start / line_end
│   └── parent-child path
├── claims
│   ├── atomic claim
│   ├── source_span: L12-L14
│   └── node_id
└── readable ranges
    ├── get_range_content(entry_id, L12-L30)
    └── cite: entry_id + title + line range
```

### 1.2 Agent 讀取協議

將 PageIndex 的三個工具抽象映射到 Guardrails：

| PageIndex 模式 | Guardrails 工具 | 用途 |
|---|---|---|
| `get_document_metadata` | `guardrails_get_metadata(entry_id)` | 看這條知識是否值得打開 |
| `get_document_structure` | `guardrails_get_structure(entry_id)` | 看章節樹、節點摘要、行號範圍 |
| `get_page_content` | `guardrails_read_range(entry_id, start_line, end_line)` | 只讀需要的局部原文 |

### 1.3 設計原則

- **Map first, read second**：Agent 不能第一步讀全文。
- **Range-limited context**：每次讀取預設最多 80 行；超過必須分段。
- **Citation required**：輸出涉及百科事實時，應附 `#id title Lx-Ly`。
- **Vector as recall, map as reasoning**：向量負責找候選，Document Map 負責判斷和定位。
- **Backward compatible**：不破壞現有 `knowledge` 表、AAAK、search CLI。
- **Local-first source of truth**：所有長期知識以 `~/Guardrails-knowledge/` 本地主庫為準，再同步 Supabase。

---

## 2. DB Schema 設計

### 2.1 新增 `knowledge_nodes`

```sql
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    INTEGER NOT NULL,
    node_uid        TEXT NOT NULL,
    parent_uid      TEXT NOT NULL DEFAULT '',
    level           INTEGER NOT NULL DEFAULT 0,
    heading         TEXT NOT NULL DEFAULT '',
    path            TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    line_start      INTEGER NOT NULL,
    line_end        INTEGER NOT NULL,
    token_estimate  INTEGER NOT NULL DEFAULT 0,
    content_hash    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (knowledge_id) REFERENCES knowledge(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_nodes_uid
ON knowledge_nodes(knowledge_id, node_uid);

CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_knowledge
ON knowledge_nodes(knowledge_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_path
ON knowledge_nodes(path);
```

### 2.2 新增 `knowledge_claims`

> 目前 claims 被塞在 `content_aaak` 裡。升級後保留 AAAK 格式，但同步寫入結構表，方便搜尋、引用、驗證。

```sql
CREATE TABLE IF NOT EXISTS knowledge_claims (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    INTEGER NOT NULL,
    node_uid        TEXT NOT NULL DEFAULT '',
    claim_uid       TEXT NOT NULL,
    claim           TEXT NOT NULL,
    line_start      INTEGER NOT NULL,
    line_end        INTEGER NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.7,
    source          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (knowledge_id) REFERENCES knowledge(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_claims_uid
ON knowledge_claims(knowledge_id, claim_uid);

CREATE INDEX IF NOT EXISTS idx_knowledge_claims_knowledge
ON knowledge_claims(knowledge_id);
```

### 2.3 可選：節點向量表

第一階段先不建節點向量，避免過度工程。若搜尋品質不足，再新增：

```sql
-- Phase 2 optional
-- knowledge_node_embeddings(node_id, embedding)
```

---

## 3. 新工具 / CLI / MCP 介面

### 3.1 Python API

新增檔案：`guardrails_lite/guardrails_map.py`

核心類：`GuardrailsMap`

方法：

```python
class GuardrailsMap:
    def build_for_entry(self, knowledge_id: int) -> dict: ...
    def build_all(self, limit: int | None = None) -> dict: ...
    def get_metadata(self, knowledge_id: int) -> dict: ...
    def get_structure(self, knowledge_id: int, max_depth: int = 3) -> list[dict]: ...
    def read_range(self, knowledge_id: int, start_line: int, end_line: int) -> dict: ...
    def find_relevant_nodes(self, query: str, limit: int = 10) -> list[dict]: ...
```

### 3.2 CLI

在 `guardrails_lite/guardrails_cli.py` 新增命令：

```bash
guardrails map build --id 405
guardrails map build --all
guardrails map show 405
guardrails map read 405 --lines 12-40
guardrails map query "PageIndex Document Map"
```

### 3.3 MCP tools

在 `guardrails_lite/guardrails_mcp.py` 新增 tools：

```text
guardrails_get_metadata(entry_id)
guardrails_get_structure(entry_id, max_depth=3)
guardrails_read_range(entry_id, start_line, end_line)
guardrails_map_query(query, limit=10)
```

### 3.4 Search 結果升級

`guardrails_search.py` 搜尋結果新增欄位：

```json
{
  "id": 405,
  "title": "...",
  "best_claim": "...",
  "best_span": "L12-L14",
  "best_node": {
    "node_uid": "h2-core-design",
    "heading": "核心設計",
    "path": "摘要 > 核心設計",
    "line_start": 12,
    "line_end": 40
  },
  "recommended_next_tool": "guardrails_read_range"
}
```

---

## 4. 實作路線圖

## Phase A — 穩定地圖層，不動搜尋主路徑

**目標：** 新增 Document Map 資料結構與 builder，但不改現有 search 行為。

### Task A1: DB schema migration

**Objective:** 在 `GuardrailsDB._init_tables()` 建立 `knowledge_nodes` 和 `knowledge_claims`。

**Files:**
- Modify: `guardrails_lite/guardrails_db.py`
- Test: `tests/test_document_map.py`

**驗收：**

```bash
cd /home/zycas/Guardrails-knowledge
conda run -n guardrails-lite python -m pytest tests/test_document_map.py -v
sqlite3 guardrails.db ".schema knowledge_nodes"
sqlite3 guardrails.db ".schema knowledge_claims"
```

### Task A2: Markdown section parser

**Objective:** 從 `content_raw` 解析 H1/H2/H3 章節、行號範圍、parent path。

**Files:**
- Create: `guardrails_lite/guardrails_map.py`
- Test: `tests/test_document_map.py`

**規則：**
- 沒有標題的內容建立 root node。
- H2 的 parent 是最近 H1；H3 的 parent 是最近 H2。
- line_end 是下一個同級/上級 heading 前一行。
- node_uid 用 slug + 行號，避免同名標題衝突。

### Task A3: Claims table backfill

**Objective:** 把現有 `content_aaak` 裡的 CLAIMS 解析到 `knowledge_claims`。

**Files:**
- Modify: `guardrails_lite/guardrails_map.py`
- Test: `tests/test_document_map.py`

**驗收：**

```bash
conda run -n guardrails-lite guardrails map build --id 405
sqlite3 guardrails.db "select claim,line_start,line_end from knowledge_claims where knowledge_id=405 limit 5;"
```

### Task A4: CLI read-only commands

**Objective:** 增加 `guardrails map show/read/query`。

**Files:**
- Modify: `guardrails_lite/guardrails_cli.py`
- Test: `tests/test_document_map_cli.py`

**驗收：**

```bash
guardrails map show 405
guardrails map read 405 --lines 1-40
guardrails map query "tool-gated reading"
```

---

## Phase B — Tool-gated Reading，讓 Agent 先看地圖再讀局部

**目標：** 搜尋結果不再只是整篇 preview，而是回傳最相關節點與下一步工具建議。

### Task B1: Map-aware search result enrichment

**Objective:** `GuardrailsSearch.search()` 結果新增 `best_span`、`best_node`、`recommended_next_tool`。

**Files:**
- Modify: `guardrails_lite/guardrails_search.py`
- Test: `tests/test_search_map_integration.py`

**驗收：** 搜 `PageIndex` 時，結果 #405 必須附帶命中節點與行號。

### Task B2: MCP tools

**Objective:** 暴露 metadata / structure / read_range / map_query 四個 MCP 工具。

**Files:**
- Modify: `guardrails_lite/guardrails_mcp.py`
- Test: `tests/test_guardrails_mcp_map.py`

**驗收：** Hermes MCP tool 能讀 #405 的 structure，再讀指定 line range。

### Task B3: Range limit and citation guard

**Objective:** `read_range` 預設最多 80 行；超過回錯誤並提示分段。回傳固定 citation。

**Example return:**

```json
{
  "entry_id": 405,
  "title": "PageIndex 的可借鑑價值：Document Map + Tool-gated Reading",
  "range": "L1-L40",
  "citation": "#405 PageIndex 的可借鑑價值 L1-L40",
  "content": "..."
}
```

---

## Phase C — 編譯器整合，讓每次 compile 自動更新地圖

**目標：** raw 變更 → compile → AAAK / embeddings / Document Map 一起更新。

### Task C1: Compile hook

**Objective:** `guardrails compile` 完成每條新增/更新知識後，自動 `build_for_entry()`。

**Files:**
- Modify: `guardrails_lite/guardrails_compile.py`
- Test: `tests/test_compile_document_map.py`

**注意：** 若 map build 失敗，不應破壞知識主表寫入；應記錄 warning 並讓 compile 整體完成。

### Task C2: Incremental rebuild

**Objective:** content_hash 未變的 entry 跳過 map rebuild。

**驗收：** 連跑兩次 compile，第二次 map rebuild count = 0。

### Task C3: Supabase sync schema

**Objective:** 決定是否同步 `knowledge_nodes` / `knowledge_claims` 到 Supabase。

**建議：**
- P0 只本地使用。
- P1 同步 `knowledge_claims`，因 MCP search 可顯示 best_span。
- P2 再同步完整 `knowledge_nodes`，支援雲端 dashboard / API。

---

## Phase D — 搜尋品質與評測

**目標：** 不只做功能，還要證明搜尋真的變準。

### Task D1: 建立 Search QA Set

**Files:**
- Create: `tests/fixtures/search_queries.yaml`

**最小集合：**

```yaml
- query: "PageIndex Document Map"
  expected_id: 405
  expected_terms: ["Document Map", "tool-gated"]
- query: "MCP add 被 local sync 覆蓋"
  expected_title_contains: "MCP add 與 local sync"
- query: "Hermes Dashboard 狀態同步表"
  expected_terms: ["hermes_guardrails_health", "hermes_agent_sessions"]
```

### Task D2: Before/after metrics

**Metrics:**

| 指標 | 目標 |
|---|---|
| Top-1 hit rate | ≥ 80% |
| Top-3 hit rate | ≥ 95% |
| citation coverage | ≥ 90% 搜尋結果有 best_span |
| read_range over-limit violations | 0 |
| compile regression | `tests/test_e2e.py` 全過 |

### Task D3: Dashboard health integration

**Objective:** 把 Document Map 覆蓋率寫入 `hermes_guardrails_health`。

**新指標：**

```text
map_coverage = entries_with_nodes / total_entries
claim_coverage = entries_with_claims / total_entries
citation_coverage = search_results_with_best_span / sampled_search_results
```

---

## Phase E — Agent 行為接入

**目標：** 讓 Nancy / Harness / 其他 profile 真正改變讀百科方式。

### Task E1: 更新 guardrails skill

**Files:**
- Modify: `/home/zycas/.hermes/skills/guardrails/SKILL.md`

**新增規則：**

```text
查長知識條目時：先 search → get_structure → read_range；不要直接讀全文。
回答百科內容時，優先附 #id + line range citation。
```

### Task E2: 更新 Hermes System prompt / SOUL 相關操作提示

不改人格，只加工具紀律：涉及百科引用時使用 Document Map 工具。

### Task E3: Handoff 模板增加 citations

大型開發 handoff 的「關鍵依據」欄位應支援：

```text
- Guardrails #405 L12-L40: Document Map + tool-gated reading
```

---

## 5. 不做什麼（Non-goals）

1. **不重寫 Guardrails 成 PageIndex fork**：PageIndex 是啟發，不是依賴。
2. **不取消向量搜尋**：vector / keyword / graph 都保留；Document Map 是定位與閱讀層。
3. **不一開始同步所有節點到 Supabase**：先本地穩定，再決定雲端 schema。
4. **不讓 LLM 自由生成不存在的引用**：citation 必須來自 `read_range()` 回傳。
5. **不一次塞完整 raw content 給 Agent**：除非用戶明確要求全文導出。

---

## 6. 風險與對策

| 風險 | 影響 | 對策 |
|---|---|---|
| Schema migration 破壞現有 DB | 高 | 只新增表，不改 knowledge 主表；先備份 `guardrails.db` |
| Map parser 對中文 Markdown 不穩 | 中 | 測試 fixture 覆蓋中文標題、無標題、重複標題 |
| 搜尋 rerank 仍把無關結果排前 | 中 | 建 Search QA set；用 Top-1/Top-3 指標驗收 |
| compile 變慢 | 中 | content_hash 增量 rebuild；先不做節點 embedding |
| MCP 工具太多 Agent 不會用 | 中 | 更新 skill + system discipline；search 結果加 `recommended_next_tool` |
| Supabase schema 同步複雜 | 中 | Phase C 先本地；雲端同步拆 P1/P2 |
| 引用行號因 raw 改動失效 | 中 | compile 時重建 map；citation 回傳 content_hash |

---

## 7. 驗收標準

### 功能驗收

```bash
cd /home/zycas/Guardrails-knowledge
conda run -n guardrails-lite python -m pytest tests/test_e2e.py -v
conda run -n guardrails-lite python -m pytest tests/test_document_map.py -v
conda run -n guardrails-lite python -m pytest tests/test_search_map_integration.py -v
```

### 行為驗收

對這個問題：

```text
PageIndex 對 Guardrails 百科有什麼可借鑑？
```

理想流程應該是：

1. `guardrails search "PageIndex Guardrails"` 找到 #405。
2. `guardrails_get_structure(405)` 看到「摘要 / 具體模式 / 為什麼重要 / 適用場景 / 設計原則」。
3. `guardrails_read_range(405, relevant_lines)` 只讀必要範圍。
4. 回答附引用：`#405 Lx-Ly`。

### 品質驗收

| 指標 | 最低要求 | 理想要求 |
|---|---:|---:|
| map_coverage | 80% | 95% |
| claim_coverage | 60% | 85% |
| search Top-3 | 90% | 95% |
| citation coverage | 80% | 90% |
| compile regression | 0 fail | 0 fail |

---

## 8. 推薦實作順序

### Sprint 1：Map 可用

1. A1 DB schema migration
2. A2 Markdown section parser
3. A3 claims table backfill
4. A4 CLI read-only commands

**交付物：** 可以對 #405 執行 `guardrails map show/read`。

### Sprint 2：Agent 可用

1. B1 search result enrichment
2. B2 MCP tools
3. B3 range limit and citation guard
4. E1 更新 guardrails skill

**交付物：** Nancy 查百科時能先看 structure，再 read_range。

### Sprint 3：自動化與評測

1. C1 compile hook
2. C2 incremental rebuild
3. D1 Search QA set
4. D2 before/after metrics

**交付物：** 每次 compile 自動更新 Document Map，並有搜尋品質報告。

### Sprint 4：Dashboard / Supabase

1. C3 Supabase sync schema decision
2. D3 Dashboard health integration
3. E3 Handoff citations

**交付物：** Dashboard 可看到 map coverage / citation coverage。

---

## 9. 對 Arthur 的產品判斷

這次升級不是「技術潔癖」，而是把百科從資料庫變成真正的 Agent 大腦：

- 以前：Agent 搜到一篇文章，自己猜哪段重要。
- 升級後：Agent 先看地圖，再打開必要段落，最後帶行號引用回答。

最小可行版本不大：**先做本地 Document Map + CLI read_range + search 結果行號**，就能立刻改善 Nancy 查百科時的準確度和可驗證性。

如果要開工，建議先做 **Sprint 1 + Sprint 2**，不要一開始碰 Supabase 大改。
