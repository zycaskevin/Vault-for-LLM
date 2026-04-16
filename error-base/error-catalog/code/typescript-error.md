# TypeScript 編譯錯誤

## 錯誤信息
```
error TS2307: Cannot find module './module'
```

## 根本原因
模塊路徑錯誤或模塊未安裝。

## 解決方案
1. 檢查模塊路徑
2. 安裝缺失的依賴
3. 配置 tsconfig.json

## 預防措施
- 使用統一的路徑別名
- 定期檢查依賴完整性

[Metadata]: {"error_code": "TYPESCRIPT_COMPILE", "occurrences": 5, "last_occurred": "2026-03-25", "author": "Eve"}
