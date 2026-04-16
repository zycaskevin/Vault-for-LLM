---
category: architecture
hash: 695164b68f4c6372
id: 16
layer: L2
tags: guardrails,sqlite-vec,onnx,embedding,local,踩坑
title: Guardrails Lite sqlite-vec ONNX 實作踩坑
trust: 0.95
updated_at: '2026-04-16T23:45:27.676931+00:00'
---

TITLE:Guardrails Lite sqlite-vec ONNX 實作踩坑
- sqlite-vec 的 vec0 是虛擬表，DROP 再 CREATE 會清掉所有已存的向量資料。
- ❌ ERR做法：每次連線都 `DROP TABLE IF EXISTS knowledge_vec` 再 `CREATE`。
- ✅ 正確做法：用 `CREATE VIRTUAL TABLE IF NOT EXISTS`，只在維度變更時才重建。
- vec0 搜尋返回的 distance 可能是 bytes 格式而非 float，需要處理：。
- if isinstance(dist, bytes):。
- dist = struct.unpack("f", dist)[0]。
- `pip install optimum` 不包含 ONNX 支援，需要：。
- pip install optimum[onnxruntime]。
... (17 more)
