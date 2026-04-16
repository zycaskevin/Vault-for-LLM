# Vercel API 集成

## 概述
通過 Vercel API 實現自動化部署和管理。

## API 端點

### 部署
```
POST /v6/deployments
```

### 獲取部署列表
```
GET /v6/deployments
```

### 獲取部署詳情
```
GET /v6/deployments/{id}
```

## 認證
使用 API Token 進行認證。

```bash
curl -H "Authorization: Bearer $VERCEL_TOKEN" \
     https://api.vercel.com/v6/deployments
```

## 常見操作

### 1. 創建部署
```bash
vercel --prod
```

### 2. 回滾部署
```bash
vercel rollback <deployment-id>
```

### 3. 查看狀態
```bash
vercel ls
```

[Metadata]: {"category": "integration", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
