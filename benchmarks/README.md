# 基準測試 (Benchmarks)

此目錄包含 Vault-for-LLM 搜尋效能與品質的基準測試工具。

## 可用的基準測試

### `search_benchmark.py` - 搜尋品質與效能基準測試

比較不同搜尋策略的效果與效能：

- 關鍵詞搜尋 vs 混合搜尋 vs 語義搜尋
- 有無 rerank 的差異
- 輕量 rerank vs cross-encoder rerank
- 有無查詢擴展的差異

**指標：**
- 精確率 (Precision@k)
- 召回率 (Recall@k)
- 歸一化折價累積增益 (NDCG@k)
- 查詢延遲 (平均、P95)

**使用方式：**

```bash
# 基礎測試（僅關鍵詞搜尋）
python3 benchmarks/search_benchmark.py

# 指定嵌入提供者進行完整測試
python3 benchmarks/search_benchmark.py --embed-provider auto

# 保存結果到指定文件
python3 benchmarks/search_benchmark.py --output results.json
```

**輸出範例：**

```
+----------------------------+-------+-------+-------+-------+-------+-------+--------+--------+----------+-----------+
|             配置             |  P@1  |  P@3  |  P@5  |  R@1  |  R@3  |  R@5  | NDCG@3 | NDCG@5 | 平均延遲(ms) | P95延遲(ms) |
+----------------------------+-------+-------+-------+-------+-------+-------+--------+--------+----------+-----------+
|          keyword_no_rerank | 0.867 | 0.378 | 0.227 | 0.713 | 0.860 | 0.860 |  0.875 |  0.865 |      0.4 |       3.0 |
| keyword_lightweight_rerank | 0.933 | 0.378 | 0.227 | 0.780 | 0.860 | 0.860 |  0.900 |  0.890 |      0.3 |       2.1 |
+----------------------------+-------+-------+-------+-------+-------+-------+--------+--------+----------+-----------+
```

### `search_qa/` - 搜尋 QA 測試集

包含用於搜尋品質評估的問答測試數據集。

- `basic.en.json` - 基礎英文測試集
- `basic.zh-Hant.json` - 基礎繁體中文測試集
- `memory_workflow.zh-Hant.json` - 記憶工作流程測試集
- `semantic_hybrid.en.json` - 語義/混合搜尋測試集

## 擴展基準測試

### 添加自定義測試數據

編輯 `search_benchmark.py` 中的 `SAMPLE_DOCUMENTS` 和 `QUERY_TEST_SET` 變量：

```python
SAMPLE_DOCUMENTS = [
    {
        "title": "文件標題",
        "content": "文件內容...",
        "category": "類別",
        "tags": ["標籤1", "標籤2"],
    },
    # ...
]

QUERY_TEST_SET = [
    {
        "query": "測試查詢",
        "relevant_docs": [1, 3],  # 相關文件的索引（1-based）
        "relevant_score": [1.0, 0.5],  # 相關性分數
    },
    # ...
]
```

### 添加新的搜尋配置

在 `main()` 函數中添加新的 `run_benchmark()` 調用：

```python
# 自定義配置
print("執行: 自定義配置...")
metrics = run_benchmark(
    db, search, QUERY_TEST_SET,
    mode="hybrid",
    use_rerank=True,
    use_query_expansion=True,
    use_llm_rewrite=True,
    name="custom_config",
)
all_metrics.append(metrics)
```
