# Holographic 記憶系統中文搜索修復

## 錯誤信息

Holographic provider 的 FTS5 和 HRR 向量搜索在處理中文時完全失敗：
- FTS5 搜尋中文關鍵詞（如「記憶系統」）返回 0 結果
- HRR 向量相似度對中文文本返回近似隨機值（約 -0.01）
- Jaccard 詞重疊計算也因中文無空格而不工作

## 根本原因

Holographic 的三層搜索管線（FTS5 → Jaccard → HRR）都使用 `text.lower().split()` 做分詞：
1. **FTS5**：使用 `unicode61` tokenizer，對中文只做單字切分，無法匹配複合詞
2. **HRR encode_text()**：中文「記憶系統三層架構」被當成一個 token，無法分解
3. **Jaccard _tokenize()**：同上，空格分割對中文完全無效

## 解決方案

整合 jieba 中文分詞到三層搜索管線：

### 1. holographic.py — encode_text() 改用 _tokenize_mixed()
```python
def _tokenize_mixed(text: str) -> list[str]:
    # jieba 分詞 CJK 文本，空格分詞英文
    if any('\u4e00' <= ch <= '\u9fff' for ch in text_lower):
        _load_hrr_dict()  # 延遲加載自定義詞典
        seg_list = jieba.lcut(text_lower)
```

### 2. retrieval.py — _tokenize() 加入 jieba
- CJK 文本用 jieba 分詞
- 延遲加載 hrr_dict.txt 自定義詞典

### 3. store.py — content_seg 欄位 + FTS5 分詞
- 新增 `content_seg` 欄位存儲 jieba 分詞後的文本
- FTS5 trigger 改為索引 `content_seg` 而非原始 `content`
- `search_facts()` 查詢前也對查詢做分詞
- `_init_db()` 遷移：自動添加欄位、回填、重建 FTS5 索引

### 4. hrr_dict.txt — 自定義詞典
Hermes 領域詞彙（記憶系統、vLLM、Ollama、Supabase 等），確保正確分詞。

## 修復效果

| 指標 | 修復前 | 修復後 |
|------|--------|--------|
| FTS5 搜「記憶系統」 | 0 結果 | 2 結果 |
| FTS5 搜「清理」 | 0 結果 | 1 結果 |
| HRR「記憶系統架構」vs「記憶系統清理」 | -0.01 | 0.32 |
| 分詞「記憶系統三層架構」 | ['記憶系','統三層','架構'] | ['記憶系統','三層架構'] |

## 不需要 BGE-M3 / Rerank Model

- HRR 已是向量搜索（SHA-256 相位向量），不需嵌入模型
- BGE-M3 需 GPU 推理，增加延遲和顯存佔用
- 瓶頸在分詞（jieba 解決），不在向量品質
- jieba 純 Python 3MB，零額外依賴

## 預防措施

1. 新增中文/CJK 文本搜索功能時，必須使用 jieba 分詞，不可用空格分割
2. FTS5 不可依賴 unicode61 tokenizer 處理中文，必須預分詞後存入
3. 自定義詞典 `hrr_dict.txt` 需隨領域詞彙更新
4. `_load_hrr_dict()` 使用延遲加載避免 jieba 初始化開銷

## 修復文件

- `plugins/memory/holographic/holographic.py` — `_tokenize_mixed()`, `_load_hrr_dict()`
- `plugins/memory/holographic/retrieval.py` — `_tokenize()`, `_load_jieba_dict()`
- `plugins/memory/holographic/store.py` — `_segment_text()`, `content_seg` 欄位, FTS5 trigger, 遷移
- `plugins/memory/holographic/hrr_dict.txt` — 自定義詞典