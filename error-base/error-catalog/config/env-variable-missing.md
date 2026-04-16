# 環境變量缺失

## 錯誤信息
```
Error: Environment variable not set: SUPABASE_URL
```

## 根本原因
環境變量未正確配置。

## 解決方案
1. 檢查 .env 文件
2. 驗證環境變量名稱
3. 重啟服務

## 預防措施
- 使用環境變量管理工具
- 記錄所有必需的環境變量
- 啟動前驗證環境變量

[Metadata]: {"error_code": "ENV_VARIABLE_MISSING", "occurrences": 8, "last_occurred": "2026-03-25", "author": "Eve"}
