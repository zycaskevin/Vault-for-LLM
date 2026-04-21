# Vault Knowledge Base憲法 — SCHEMA.md

> 本文件是所有 Agent（agent runtime、Claude Code、OpenCode）操作百科時的唯一規範源。
> 任何 Agent 進入百科，先讀 SCHEMA.md，再動手。

_建立：2026-04-22 | 靈感：花叔 Obsidian 橙皮書 + Karpathy LLM Wiki_

---

## 1. 三層架構

```
raw/        → 第一層：源材料（不可變，只增不改）
compiled/   → 第二層：結構化知識（AI 維護，compiler 自動生成）
output/     → 第三層：查詢產物（報告、分析、回答）
```

**數據流**：raw → compiled → output（單向，不回流）
**Supabase**：L2+ 同步副本，所有 Agent 共享的 source of truth

---

## 2. 命名規範

### raw/ 檔案
- 格式：`YYYYMMDD-簡述.md`
- 例：`20260422-wsl2-chrome-cdp-bridge.md`
- 子目錄分類可選（code-snippets/、research/、web-clips/ 等），不超過 2 層

### compiled/ 檔案
- 格式：`YYYYMMDD_test_{category}_{序號}.md`（compiler 自動生成，勿手動改名）
- 例：`20260411_test_error_base_techniques_162.md`
- 子目錄按類別：`L3-architecture/`、`L2-architecture/`

### Supabase
- 表 `guardrails_knowledge`：id, title, content, category, tags, embedding, trust, source, created_at, updated_at
- 表 `gr_entities`：id, name, type, description, created_at
- 表 `gr_edges`：id, source_entity, target_entity, relation_type, weight
- 表 `gr_entity_knowledge`：id, entity_id, knowledge_id

---

## 3. Frontmatter 規規範（鐵律）

### 必填字段（五字段 + summary）

```yaml
---
title: "知識標題"
category: "concept|technique|workflow|lesson|error|comparison|article-source|content-log"
layer: 0-3
tags: ["tag1", "tag2"]
summary: "一句話摘要（30-80字，讓 AI 不用讀全文就能判斷相關性）"
trust: 0.0-1.0
source: "來源標識"
created: "YYYY-MM-DD"
---
```

### summary 欄位（⭐ 新增鐵律）
- **每條知識必須有 summary**
- 30-80 字，一句話說清楚「這條知識講什麼」
- 寫法：假設有人問「這條筆記講啥」，你怎麼用一句話回答？那就是 summary
- compiled/ 檔案的 summary 由 compiler 自動生成
- raw/ 檔案的 summary 由寫入者提供，AI 可補充

### 可選字段

```yaml
updated: "YYYY-MM-DD"
status: "active|archived|deprecated"
compression: "aaak"           # 僅 compiled/
original_tokens: 1200         # 僅 compiled/
compressed_tokens: 200        # 僅 compiled/
```

---

## 4. 標籤體系

### 領域標籤（一級，不超過 20 個）
| 標籤 | 涵蓋 |
|------|------|
| `llm` | 模型、推理、部署 |
| `tools` | 開發工具、CLI、IDE |
| `infra` | WSL2、Docker、網路、GPU |
| `data` | 資料庫、向量搜尋、Supabase |
| `content` | 文章、影片、社媒 |
| `workflow` | 自動化、cron、agent |
| `security` | 安全、審計、防護 |
| `testing` | 測試、QA、CI/CD |
| `design` | UI/UX、設計、圖片生成 |
| `business` | 接案、定價、Upwork |

### 類型標籤（二級）
| 標籤 | 用途 |
|------|------|
| `pitfall` | 踩坑記錄 |
| `best-practice` | 最佳實踐 |
| `architecture` | 架構決策 |
| `integration` | 跨系統整合 |
| `observation` | AI 行為觀察 |

### 狀態標籤
- `stub` — 存根，需擴充
- `mature` — 成熟，已驗證

### 規則
- 標籤用英文小寫，多詞用连字符
- **不要自創新的一級標籤**，如有需要先更新本文件
- 嵌套不超過 2 層（如 `llm/vllm` 可接受，`llm/vllm/quant/gguf` 則否）

---

## 5. 人 vs AI 產出邊界

### raw/ — 人的領地
- 來源：用戶手動寫入、Agent 觀察後記錄
- 規則：**只增不改** — 未經用戶確認，AI 不能修改或刪除 raw/ 內容
- 信任度：最高，是 source of truth

### compiled/ — AI 的領地
- 來源：compiler 從 raw/ 自動編譯
- 規則：AI 可以自由更新、重新生成
- 信任度：中等，衍生數據可隨時重新生成

### agent-outputs/ — Agent 會話產物
- 規則：暫存，定期清理或編譯進 compiled/
- 信任度：低，需人工審核後才能升級

### output/ — 查詢產物
- 規則：基於 compiled/ 生產，好的 output 可以反哺 compiled/

---

## 6. 知識生命週期

```
寫入 raw/ → compiler 編譯到 compiled/ → 同步 Supabase
                                              ↓
                                  query → output/（按需生成）
                                              ↓
                              好的 output 反哺 compiled/（人工觸發）
                                              ↓
                               過時 → status: deprecated → archived
```

### 狀態轉換
- `active` → `deprecated`（不再適用，如舊版 API 已下線）
- `active` → `archived`（項目結束，知識保留但不活躍）
- `deprecated` / `archived` 的知識仍可搜索到，但 AI 回答時會標注時效性

---

## 7. Compiler 行為規範

### 觸發
- 手動：`python3 scripts/guardrails_compiler.py`
- 自動：每日 06:00 cron（daily_knowledge_sync.py）
- 即時：寫入 raw/ 後建議立即編譯

### Compiler 保證
1. raw/ 原文不動
2. compiled/ 採 AAAK 壓縮（axioms + analogies + applications + keys）
3. 每條 compiled 帶 frontmatter（含 summary）
4. 編譯完自動更新 INDEX.md

### Compiler 禁止
1. 不刪除 raw/ 檔案
2. 不修改已確認的 compiled/ 內容（只追加更新的）
3. 不編造不存在的知識

---

## 8. INDEX.md 生成規範

Compiler 完成後，自動生成 `INDEX.md` 在根目錄：

```markdown
# Vault Knowledge Base索引

_最後更新：YYYY-MM-DD | 共 N 筆_

## 按類別
| 類別 | 數量 | 關鍵詞 |
|------|------|--------|
| error | 42 | ... |
| technique | 38 | ... |

## 按最近更新（Top 20）
| 標題 | 日期 | Summary |
|------|------|---------|
| ... | ... | ... |

## 待擴充（stub）
- [[stub-1]] — 一句話描述
```

---

## 9. 搜尋優先級

1. **INDEX.md** — 快速定位（AI 先掃索引，不用逐文件遍歷）
2. **frontmatter summary** — 判斷相關性
3. **關鍵字 grep** — `rg "關鍵字" raw/ compiled/`
4. **向量搜尋** — `guardrails_wakeup.py --search`（Supabase）
5. **圖譜擴展** — `guardrails search "X" --graph-expand 1`（Lite）

---

## 10. 術語表

| 標準用詞 | 不用 |
|----------|------|
| Vault | 百科、知識庫（指系統時用 Vault） |
| raw/ | 原始檔、源檔 |
| compiled/ | 編譯檔、壓縮檔 |
| compiler | 編譯器 |
| Supabase | 雲端、遠端（指這個 DB 時用 Supabase） |
| Lite | 本地版、離線版 |
| AAAK | 壓縮格式（Axioms+Analogies+Applications+Keys） |
| trust | 信任度、可信度 |
| summary | 摘要 |

---

_Vault Knowledge Base憲法 · 第一次建立 2026-04-22_
_Inspired by: Karpathy LLM Wiki three-layer architecture_