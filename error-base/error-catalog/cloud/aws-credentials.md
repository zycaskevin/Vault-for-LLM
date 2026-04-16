# AWS 憑證錯誤

## 錯誤信息
```
The security token included in the request is invalid
```

## 根本原因
AWS 訪問憑證無效或過期。

## 解決方案
1. 刷新 AWS 憑證
2. 驗證 IAM 權限
3. 檢查區域配置

## 預防措施
- 使用 IAM Role
- 定期輪換憑證
- 記錄憑證過期時間

[Metadata]: {"error_code": "AWS_CREDENTIALS", "occurrences": 3, "last_occurred": "2026-03-15", "author": "Eve"}
