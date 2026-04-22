# Guardrails 優化計畫 v2 — 從 MindForge 提煉

> 來源：MindForge 技術文分析，對照 Guardrails 現有架構
> 日期：2026-04-22
> 狀態：待審核

---

## 現狀盤點

| 項目 | Guardrails 現狀 | MindForge 做法 | 差距 |
|------|----------------|---------------|------|
| 知識觸發 | 人工 + Cron 掃描 | KAL 自問收斂 | 沒有「學會了沒」的自動判斷 |
| 知識粒度 | 條目級（整篇 AAAK） | 原子主張 + source_span | 搜尋和引用粒度粗 |
| 驗證機制 | trust_adjustment（指標式） | 跨家族 LLM 交叉驗證 | 沒用模型驗證提取品質 |
| 搜尋管線 | keyword + vector + hybrid + graph_expand | HFQ 5-step（含 Reranker） | 缺 Reranker 重排序 |
| 新鮮度 | trust_adjustment 線性衰減（30天-5%） | FSRS 間隔重複 | 沒有 freshness 欄位和驗證週期 |
| 知識入口 | CLI + Cron + session harvest | MCP + Browser Plugin + PWA | 只有 CLI 和 Cron |

---

## P0-1：KAL 自問收斂（Knowledge Acquisition Loop）

### 目標
讓 Compiler 跑完後自動判斷「這條知識是否足夠完整」，不足就標記待補充。

### 設計

```
新增欄位：knowledge.convergence_status
  - 'complete'  — 自問通過，知識充足
  - 'partial'   — 自問未通過，需補充
  - 'unknown'   — 未執行自問（預設）

新增腳本：scripts/convergence_check.py
  1. 讀取 trust < 0.7 或 convergence_status = 'partial' 的條目
  2. 對每條生成 3 個自問問題（基於 title + content_raw）
  3. 用本地模型嘗試回答，評分 0-1
  4. 平均分 >= 0.7 → status='complete'，否則 → status='partial'
  5. 輸出報告：哪些條目需要補充、缺什麼

自問問題生成策略：
  - 從 title 提取核心概念
  - 從 content_raw 提取關鍵事實
  - 生成 3 題：一題定義、一題操作、一題邊界案例
  - 例：條目「sqlite-vec 踩坑」→ Q1: sqlite-vec 是什麼？ Q2: 怎麼正確載入？ Q3: 什麼情況會失敗？
```

### DB Schema 變更

```sql
ALTER TABLE knowledge ADD COLUMN convergence_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE knowledge ADD COLUMN convergence_score REAL DEFAULT NULL;
ALTER TABLE knowledge ADD COLUMN convergence_checked_at TEXT NOT NULL DEFAULT '';
```

### 實作範圍
1. `guardrails_db.py` — 新增欄位 + `update_convergence()` 方法
2. `scripts/convergence_check.py` — 自問收斂腳本（新檔案）
3. `guardrails_compile.py` — compile 完成後觸發 convergence_check
4. 測試：`tests/test_convergence.py`

---

## P0-2：原子主張 + Source Span

### 目標
把一條知識從「整篇文章」拆成多個可獨立檢索的原子主張，每個主張帶原文定位。

### 設計

```
不新建表，在 AAAK 壓縮階段增加結構化輸出：

content_aaak 格式（新增 claims 段）：
---
TITLE: sqlite-vec 踩坑
CLAIMS:
- [C1] sqlite-vec 擴展需每次連線重新載入 (L12-14)
- [C2] WAL 模式建議搭配使用 (L15-16)
- [C3] 虛擬表找不到是常見錯誤 (L10-11)
KEY:VALUES:
EXT: sqlite-vec
EXT: 擴展
EXT: 踩坑
---

搜尋時的改進：
  - 向量搜尋：用 claims 作為最小檢索單位
  - 引用時：回報 [C2] 而非「這篇文章說」
```

### 實作範圍
1. `guardrails_compile.py` — 修改 `simple_aaak_compress()` 增加 claims 提取
2. `guardrails_search.py` — 搜尋結果附帶 best_claim 和 source_span
3. `guardrails_db.py` — content_aaak 格式相容（新格式向後相容，沒有 CLAIMS 段也能正常顯示）
4. 測試：在 `test_e2e.py` 增加 claims 格式測試

---

## P1-1：跨模型不對稱驗證

### 目標
信任分數不再只靠指標計算，加上 LLM 交叉驗證提升準確度。

### 設計

```
新增腳本：scripts/cross_validate.py
  1. 篩選目標：trust < 0.7 或 convergence_status = 'partial'
  2. 本地 Qwen 提取該條目的核心主張（3-5 條）
  3. 雲端 Claude/GLM-5.1 驗證每條主張的真實性
  4. 驗證結果：
     - 全部通過 → trust += 0.1
     - 部分通過 → 標記 convergence_status = 'partial'
     - 全部失敗 → trust -= 0.2

成本控制：
  - 每天只驗證 20 條（低 trust 優先）
  - 雲端模型只用於驗證（1 條知識 ≈ 200 tokens）
  - 預估成本：< $0.01/天

觸發方式：
  - Cron 每日 23:30 執行（在 contradiction_check 之後）
  - 或手動：python3 scripts/cross_validate.py --limit 10
```

### 實作範圍
1. `scripts/cross_validate.py` — 新腳本
2. `guardrails_db.py` — 新增驗證結果記錄（lint_cache 表可複用）
3. Cron 排程更新
4. 測試：mock 雲端 API 測試邏輯

---

## P1-2：搜尋 Reranker

### 目標
搜尋結果先用語意相似度排序，再用圖譜深度加權，最終輸出品質更高的排序。

### 設計

```
現有搜尋管線：
  keyword | vector | hybrid → graph_expand

升級為：
  hybrid → rerank(cosine + graph_depth + trust + freshness) → graph_expand

Reranker 評分公式：
  score = cosine_sim × 0.5
        + graph_depth_bonus(0.1 per hop, max 0.2)
        + trust × 0.15
        + freshness × 0.15

  freshness = 1.0 - min(days_since_update / 365, 0.5)

不引入額外模型，純公式計算。未來可替換為 BGE-Reranker。
```

### 實作範圍
1. `guardrails_search.py` — 新增 `_rerank()` 方法
2. `guardrails_search.py` — `search()` 增加 `use_rerank=True` 參數
3. CLI 增加 `--rerank` 旗標
4. 測試：比較 rerank 前後搜尋品質

---

## P2-1：新鮮度追蹤

### 目標
知識有保存期限，過期要重新驗證。

### 設計

```
複用 trust_adjustment.py 已有的時間衰減邏輯，但額外：

新增欄位：knowledge.last_verified
  - 每次 convergence_check 或 cross_validate 通過 → 更新 last_verified
  - 超過 90 天未驗證 → freshness = 0.5
  - 超過 180 天 → freshness = 0.3

新增腳本：scripts/freshness_check.py
  1. 列出 last_verified 超過 90 天的條目
  2. 嘗試用最新資料重新驗證（搜尋來源 URL 或關鍵字）
  3. 標記 stale 條目
```

### DB Schema 變更

```sql
ALTER TABLE knowledge ADD COLUMN last_verified TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge ADD COLUMN freshness REAL NOT NULL DEFAULT 1.0;
```

### 實作範圍
1. `guardrails_db.py` — 新增欄位 + `update_freshness()` 方法
2. `scripts/freshness_check.py` — 新腳本
3. `trust_adjustment.py` — 計算時加入 freshness 因子
4. 測試

---

## P2-2：MCP 注入介面

### 目標
讓任何 AI agent 能透過 MCP 協議直接寫入 Guardrails 百科。

### 設計

```
新增：vault/guardrails_mcp.py

MCP Tools 暴露：
  - guardrails_search(query, mode, limit) — 搜尋知識
  - guardrails_add(title, content, category, tags) — 新增知識
  - guardrails_stats() — 百科統計

接入方式：
  1. agent runtime native MCP（config.yaml 設定）
  2. 獨立 MCP server（stdio transport）

不涉及 Browser Plugin（需要 API server，工作量大，P3）
```

### 實作範圍
1. `vault/guardrails_mcp.py` — MCP server（新檔案）
2. `~/.agent-runtime/config.yaml` — MCP 設定
3. 測試：用 `mcporter` 驗證連線

---

## 實作順序

```
Phase 1 — 基礎設施（DB schema + KAL）
  1. guardrails_db.py schema 升級（4 新欄位）
  2. convergence_check.py（P0-1）
  3. 原子主張 claims 格式（P0-2）

Phase 2 — 搜尋品質提升
  4. Reranker（P1-2）
  5. 跨模型驗證（P1-1）

Phase 3 — 長期維護
  6. 新鮮度追蹤（P2-1）
  7. MCP 注入（P2-2）
```

## 測試計畫

每個 Phase 完成後跑完整測試：

```bash
cd /home/user/Guardrails-knowledge
conda run -n guardrails-lite python tests/test_e2e.py  # 現有 33/33 必須全過
conda run -n guardrails-lite python tests/test_convergence.py  # 新增
conda run -n guardrails-lite python tests/test_rerank.py  # 新增
```

回歸測試重點：
- DB schema 升級不破壞現有資料
- AAAK 壓縮向後相容（舊格式仍可讀）
- 搜尋結果排序不退化
- 圖譜功能不受影響