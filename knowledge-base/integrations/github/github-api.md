# GitHub API 集成

## 概述
通過 GitHub API 實現代碼管理和自動化。

## API 端點

### 倉庫操作
```
GET /repos/{owner}/{repo}
POST /repos/{owner}/{repo}
```

### PR 操作
```
GET /repos/{owner}/{repo}/pulls
POST /repos/{owner}/{repo}/pulls
```

### Actions
```
GET /repos/{owner}/{repo}/actions/runs
POST /repos/{owner}/{repo}/actions/dispatches
```

## 認證
使用 Personal Access Token。

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/repos/zycaskevin/Guardrails
```

[Metadata]: {"category": "integration", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
