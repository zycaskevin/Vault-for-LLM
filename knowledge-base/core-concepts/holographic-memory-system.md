# Holographic 記憶系統

## 定義

Hermes Agent 的第三層記憶系統（L3），使用 Holographic Reduced Representation (HRR) 向量搜索 + FTS5 全文搜索 + Jaccard 詞重疊 + 信任評分的混合搜索架構。

## 核心特性

- **零外部依賴**：純 SQLite + numpy，不需要 GPU 或嵌入模型
- **確定性向量**：SHA-256 生成相位向量，不是神經網絡嵌入
- **三層搜索管線**：FTS5（召回）→ Jaccard（初排）→ HRR（重排）
- **信任評分**：0.0-1.0，支持 helpful/unhelpful 回饋訓練
- **實體解析**：自動提取和連結實體（人名、專案名等）
- **中文支持**：透過 jieba 分詞 + hrr_dict.txt 自定義詞典

## 架構

```
memory_store.db (SQLite)
├── facts           — 事實存儲（content + content_seg + tags + trust_score + hrr_vector）
├── entities        — 實體存儲（name + type + aliases）
├── fact_entities   — 事實-實體關聯
├── memory_banks    — 記憶銀行分區
└── facts_fts       — FTS5 全文搜索（索引 content_seg 分詞版）
```

## 配置

```yaml
# ~/.hermes/config.yaml
memory:
  provider: 'holographic'

plugins:
  hermes-memory-store:
    db_path: '$HER_HOME/memory_store.db'
    auto_extract: false        #不自動抽取事實，避免幻覺
    default_trust: 0.5         #新事實初始信任度
    hrr_dim: 1024              #HRR 向量維度
```

## 相關概念

- [[MEMORY.md]] — L1 記憶（每輪注入）
- [[session_search]] — L2 記憶（FTS5 搜索過去對話）
- [[jieba]] — 中文分詞庫
- [[HRR]] — Holographic Reduced Representation

## 比較

| 特性 | Holographic | ChromaDB+BGE-M3 | mem0 |
|------|-------------|-----------------|------|
| 依賴 | SQLite+numpy | Docker+GPU | API |
| 中文搜索 | ✅ jieba | ✅ 原生 | ⚠️ 有限 |
| 向量搜索 | ✅ HRR | ✅ BGE-M3 | ✅ OpenAI |
| 離線使用 | ✅ | ❌ | ❌ |
| 信任評分 | ✅ | ❌ | ❌ |
| 成本 | $0 | GPU+維護 | API費用 |