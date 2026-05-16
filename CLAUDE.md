# Vault for LLM — CLAUDE.md

Copy this file into a project root when you want Claude Code or another AI coding agent to use a Vault-for-LLM knowledge base in that project.

---

```markdown
## Vault Knowledge Base

This project has a local-first Vault-for-LLM knowledge base. Use it as persistent project memory.

### Architecture
- **L0 User/Project Identity**: `L0-identity/identity.md` — stable identity and preferences; read at session start if present.
- **L1 Core Facts**: `L1-core-facts/current-projects.md` — stable environment and project facts; read at session start if present.
- **L2 Context**: `L2-context/recent-sessions/current.md` — recent context; read when relevant.
- **L3 Deep Knowledge**: `raw/`, `compiled/`, and the local SQLite vault — search on demand.

### Read Rules
1. At session start, read L0 + L1 if they exist and are relevant to the task.
2. When the user references past decisions, incidents, APIs, or repeated problems, search L3.
3. Prefer `vault search "query"`; if unavailable, fall back to keyword search with `rg`.
4. For long entries, use Document Map / bounded read tools when available instead of reading entire files.

### Write Rules
1. After valuable work, write a concise Markdown knowledge entry to `raw/` or use `vault add`.
2. Include YAML frontmatter with title, category, layer, tags, trust, source, and created date.
3. Run `vault compile` after writing.
4. Do not store secrets, private credentials, or unnecessary personal data.

### Search Methods
- Keyword search: `rg "keyword" raw/ compiled/`
- Title search: `rg "title:" raw/`
- Tag search: `rg "tags:.*keyword" raw/`
- Vault search: `vault search "query"`

### Write Format
Each knowledge entry uses YAML frontmatter:
\`\`\`yaml
---
title: "Entry Title"
category: "technique|concept|workflow|lesson|error|comparison|general"
layer: L3
tags: ["tag1", "tag2"]
trust: 0.0-1.0
source: "source-description"
created: "YYYY-MM-DD"
---
\`\`\`

### Environment
- Prefer `VAULT_PATH=/path/to/project` if the vault is not in the current working directory.
- `GUARDRAILS_PATH` may still work as a legacy compatibility variable in some scripts.
```

---

*Last updated: 2026-05-16*
