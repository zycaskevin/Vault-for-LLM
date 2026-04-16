# Vector 維度不匹配

## 錯誤信息
```
Vector dimension mismatch: expected 1024, got 2048
```

## 根本原因
數據庫使用 1024 維度，但配置使用 2048 維度。

## 解決方案
1. 刪除舊數據庫: `rm -rf /root/.hermes/memory/lancedb-pro`
2. 重啟 Gateway
3. 重新初始化記憶系統

## 預防措施
修改 embedding 配置時，必須重新創建數據庫。

[Metadata]: {"error_code": "VECTOR_DIMENSION_MISMATCH", "occurrences": 2, "last_occurred": "2026-03-18", "author": "Eve"}
