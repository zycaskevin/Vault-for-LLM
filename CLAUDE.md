# Vault for LLM — CLAUDE.md

## How to Use
Copy this file into your project root. Your AI IDE will read it automatically on startup.

---

```markdown
## Vault Knowledge Base

You have a layered knowledge base at the project root (or GUARDRAILS_PATH env variable).

### Architecture
- **L0 User Identity**: `L0-identity/identity.md` — who the user is, read every conversation
- **L1 Core Facts**: `L1-core-facts/current-projects.md` — active projects, read every conversation
- **L2 Context**: `L2-context/recent-sessions/current.md` — recent context, read when needed
- **L3 Deep Knowledge**: `raw/` or `compiled/` — search on demand

### Read Rules
1. At conversation start, read L0 + L1
2. When user mentions past events, search L3 (use `rg` keyword first, then semantic if needed)
3. After completing valuable work, write a new entry to `raw/` (YAML frontmatter format)
4. After writing, run `vault compile`

### Search Methods
- Keyword search: `rg "keyword" raw/ compiled/`
- Title search: `rg "title:" raw/`
- Tag search: `rg "tags:.*keyword" raw/`
- Semantic search: `vault search "query"`

### Write Format
Each knowledge entry uses YAML frontmatter:
\`\`\`yaml
---
title: "Entry Title"
category: "technique|concept|workflow|lesson|error|comparison"
layer: "L0|L1|L2|L3"
tags: ["tag1", "tag2"]
trust: 0.0-1.0
source: "source-description"
created: "YYYY-MM-DD"
---
\`\`\`
```

---

*Last updated: 2026-04-19*