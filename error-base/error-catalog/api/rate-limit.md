# API 速率限制

## 錯誤信息
```
429 Too Many Requests
Rate limit exceeded
```

## 根本原因
API 調用頻率超過限制。

## 解決方案
1. 實現指數退避
2. 緩存結果
3. 批量處理請求

## 預防措施
- 實現速率限制器
- 使用本地緩存
- 批量請求

[Metadata]: {"error_code": "API_RATE_LIMIT", "occurrences": 15, "last_occurred": "2026-03-25", "author": "Eve"}
