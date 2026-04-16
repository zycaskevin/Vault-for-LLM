# Supabase 設置指南

## 概述
Supabase 是開源的 Firebase 替代方案，提供 PostgreSQL 數據庫、認證、存儲等功能。

## 項目配置

### Mobile Hermes V2
- **URL**: https://ajmhntwhgenyfitivwuy.supabase.co
- **Region**: 新加坡
- **Project ID**: ajmhntwhgenyfitivwuy

### 舊實例
- **URL**: https://zmttlqmallluooqxswqy.supabase.co
- **Project Ref**: zmttlqmallluooqxswqy

## 表結構

### 核心表
- `users`: 用戶信息
- `conversations`: 對話記錄
- `messages`: 消息記錄
- `memory`: 記憶存儲
- `tasks`: 任務管理

## Edge Functions

### 部署命令
```bash
supabase functions deploy <function-name>
```

### 環境變量
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY

[Metadata]: {"category": "architecture", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
