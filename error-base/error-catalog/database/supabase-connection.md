# Supabase 連接失敗

## 錯誤信息
```
Supabase connection failed: network error
```

## 根本原因
網絡限制導致無法訪問 Supabase API (.supabase.co)。

## 解決方案
1. 配置代理服務
2. 等待網絡恢復
3. 使用備用方案

## 預防措施
- 添加網絡狀態檢測
- 提供離線模式
- 記錄連接問題以便診斷

[Metadata]: {"error_code": "SUPABASE_CONNECTION", "occurrences": 5, "last_occurred": "2026-03-19", "author": "Eve"}
