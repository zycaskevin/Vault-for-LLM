---
title: Guardrails Lite sqlite-vec ONNX 實作踩坑
category: architecture
layer: L2
tags: guardrails,sqlite-vec,onnx,embedding,local,踩坑
trust: 0.95
source: 實測經驗
---

# Guardrails Lite sqlite-vec ONNX 實作踩坑

## 1. sqlite-vec vec0 虛擬表不能 DROP+CREATE

sqlite-vec 的 vec0 是虛擬表，DROP 再 CREATE 會清掉所有已存的向量資料。

❌ 錯誤做法：每次連線都 `DROP TABLE IF EXISTS knowledge_vec` 再 `CREATE`
✅ 正確做法：用 `CREATE VIRTUAL TABLE IF NOT EXISTS`，只在維度變更時才重建

踩坑症狀：compile 完嵌入 3 筆，但新連線後 stats 顯示 embedding_count=0，因為 vec0 表被重建了。

## 2. sqlite-vec distance 欄位可能是 bytes

vec0 搜尋返回的 distance 可能是 bytes 格式而非 float，需要處理：
```python
if isinstance(dist, bytes):
    dist = struct.unpack("f", dist)[0]
dist = float(dist)
```

不處理的話，`1.0 - dist` 計算 score 會 TypeError。

## 3. optimum[onnxruntime] 需要 extra 安裝

`pip install optimum` 不包含 ONNX 支援，需要：
```bash
pip install optimum[onnxruntime]
```
否則 `from optimum.onnxruntime import ORTModelForFeatureExtraction` 會 ImportError。

## 4. sqlite-vec 需要載入擴展才能存取 vec0 表

每次開新連線都要：
```python
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)
```
沒載入擴展就查 vec0 表 → "no such module: vec0" 錯誤。

## 5. ONNX 模型需要 Mean Pooling + Normalize

直接用 ONNX Runtime 跑 feature extraction 只得到 token embeddings，
需要手動做 Mean Pooling（乘 attention_mask）+ L2 Normalize，才能跟
sentence-transformers 的結果一致。

## 6. Git rebase 衝突處理

compiler 自動 git commit 時會把所有檔案加入，推到 GitHub 時如果
遠端有新 commit 會衝突。解法：
- .compiler_state.json / README.md 用 `--ours` 我們的版本
- 刪除的舊檔案用 `git rm`
- `GIT_EDITOR=true git rebase --continue`

## 7. 嵌入失敗要自動降級

搜尋的 auto 模式如果嵌入失敗（模型沒裝、Ollama 沒跑），
必須 try/except 降級到關鍵字搜尋，不能讓整個搜尋掛掉。