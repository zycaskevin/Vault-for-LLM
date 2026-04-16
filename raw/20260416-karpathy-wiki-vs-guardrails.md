# Karpathy LLM Wiki vs Guardrails 百科對照分析

## 骨架對照
| Karpathy | Guardrails | 差異 |
|----------|-----------|------|
| raw/ | raw/ (L3) | 一樣 |
| wiki/ (compiled pages) | compiled/ + Supabase AAAK | AAAK 是給 LLM 讀的壓縮格式，不是給人讀的長文 |
| schema / CLAUDE.md | L0 identity + L1 core facts | Guardrails 多了信任分數和實體關聯 |
| index.md | L2 dynamic context | 自動生成，不是手動維護的 MOC |

## Karpathy 做得好的（我們要帶回來）
1. **矛盾偵測** — 新素材進來自動比對舊 page 衝突，標出留給人判斷
2. **跨頁連鎖更新** — 新 source 可能同時動到 10-15 張 page
3. **Lint / 健康檢查** — 掃整座 wiki 找孤立 page、過期內容、概念缺口

## 我們比他好的
1. **分層服務** — L0→L1→L2→L3，不同問題拿不同層，不需要每次翻整座 wiki
2. **信任分數** — 每條知識 trust 0-1，互相矛盾的資訊不會平等對待
3. **AAAK 壓縮** — 6x 壓縮，LLM 讀更少 token
4. **自動化** — L2 自動從 state.db 拉 session 摘要、自動統計活躍技能

## 核心分歧：容器問題
- 兩條路都用 LLM 做 compound，bookkeeping 成本都壓得下來
- Karpathy 的 wiki page 是主題聚合，要決定「併進哪張 page」— 這是永遠的分類問題
- LYT 原子卡片繞開了分類問題：一張卡一個概念，連結取代分類
- 我們站在原子化這邊，但 category（error/technique/workflow/comparison/concept）本身也是分類
- 編譯器自動分類但邏輯很粗糙（看關鍵字），跟 Karpathy 的「主題邊界在哪」是同一個問題

## 待實作
- 矛盾偵測：compiler 跑完自動比對新舊條目衝突
- 連鎖更新：新條目引用的實體，自動更新相關條目
- 概念缺口 Lint：多次被提到但沒有獨立條目的概念
- 孤立條目偵測：沒有 tag 也沒有 related 關聯的條目