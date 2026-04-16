# 記憶系統清理與重構經驗

## 背景

2026-04-15 進行 Hermes Agent 記憶系統全面清理，消除 Hermes/Nancy 時期遺留物，啟用 holographic 記憶 provider。

## 教訓

### 1. 遺留系統清理要果斷
- Hermes → Hermes 遷移後，Hermes 遺留物（ChromaDB、MEMORY_OPENCLAW.md、services/）佔用空間且造成混淆
- **最佳實踐**：遷移完成後立即清理舊系統遺留，不要拖延。設置明確的「過渡期最後日期」
- 本次清理回收：services/(1.3MB/38腳本)、24個廢棄scripts、.hermes/(148KB)、3個Nancy skills

### 2. 記憶系統三層架構
- L1：MEMORY.md / USER.md（每輪注入，有容量限制）
- L2：session_search（FTS5 搜索過去對話）
- L3：holographic provider（結構化事實存儲 + HRR 向量 + 信任評分）
- **重點**：L1 有硬性字數限制（MEMORY 2200字 / USER 1375字），超過會截斷，必須定期壓縮

### 3. 中文/CJK 搜索需要專門處理
- holographic provider 原始設計只考慮英文，`text.lower().split()` 對中文完全失效
- 解決方案：整合 jieba 分詞到三層搜索管線
- 詳見 error-base: `memory/holographic-chinese-search-fix.md`

### 4. state.db 需要定期維護
- cron sessions 大量堆積（2168個，98%是定時任務），DB 增長到 115MB
- 清理無用 session 後降至 52MB
- **最佳實踐**：定期清理 >3天的 cron session，≤2 messages 的 session 直接刪

### 5. Holographic provider 選擇理由
- 評估了 9 個替代方案（mem0、hindsight、honcho 等）
- holographic 勝出原因：零外部依賴、純 SQLite+numpy、本地優先、信任評分機制
- 不需要 BGE-M3/rerank model — 瓶頸在分詞不在向量品質

### 6. auto_extract 設為 False 的考量
- holographic 的 `auto_extract: False` 表示不自動從對話中抽取事實
- 優點：避免幻覺事實被存入 L3
- 缺點：需要手動用 `fact_store add` 存入
- **建議**：初期手動管理，信任度高後再考慮啟用 auto_extract

## 最佳實踐

| 操作 | 指令 | 頻率 |
|------|------|------|
| 壓縮 L1 記憶 | `memory(replace)` 或 `write_file` | 當超過 80% |
| 清理 state.db | 批量刪除舊 cron sessions | 每月 |
| 更新 hrr_dict.txt | 新增領域詞彙 | 當分詞不準確時 |
| 驗證 L3 搜索 | `fact_store search 中文查詢` | 修復後驗證 |
| 重建 FTS5 索引 | 刪除並重建 facts_fts 表 | 當搜索失效時 |