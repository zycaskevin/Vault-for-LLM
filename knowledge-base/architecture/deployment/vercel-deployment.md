# Vercel 部署指南

## 概述
Vercel 是 Next.js 的官方部署平台，提供了零配置的部署體驗。

## 部署配置

### 項目
- **Dashboard**: https://vercel.com/dashboard
- **Vercel CLI**: 可用於本地部署

## 部署流程

### 1. 連接 GitHub
在 Vercel Dashboard 中連接 GitHub 倉庫。

### 2. 配置環境變量
```
SUPABASE_URL=<your-supabase-url>
SUPABASE_ANON_KEY=<your-anon-key>
```

### 3. 部署
```bash
vercel --prod
```

## 常見問題

### 1. 404 NOT_FOUND
- 原因：文件結構混亂
- 解決：統一 index.html 位置

### 2. Edge Functions 錯誤
- 原因：使用了未定義的函數
- 解決：修復函數引用，驗證兼容性

[Metadata]: {"category": "deployment", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
