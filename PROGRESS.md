# Vault-for-LLM Public Release Progress

Last updated: 2026-05-16 23:31 CST

## Current Task: Public README and Positioning Cleanup

### Goal
Make the repository present Vault-for-LLM as an open-source, local-first memory layer for LLM agents, not as an internal/private knowledge base.

### Scope
- Replace the GitHub default `README.md` with public product positioning.
- Keep `README.zh-Hant.md` and `README.zh-CN.md` aligned with the same positioning.
- Make CLI help use the public command name `vault`.
- Sanitize public docs so SQLite is described as the local source of truth and Supabase as optional sync infrastructure.
- Remove or rewrite obvious private paths, internal dashboards, personal names, and internal agent wiring from public-facing Markdown.

### Public Repository Constraints
- Public-facing brand: **Vault-for-LLM**, `vault`, `vault-mcp`.
- Core promise: local-first SQLite knowledge vault for LLM agents.
- SQLite is the source of truth; Supabase is optional sync/read infrastructure.
- Historical implementation names such as `guardrails_lite` and `guardrails.db` may remain for compatibility, but should be framed as legacy implementation details in public docs.
- Advanced features such as convergence, cross-validation, Search QA, skills, and Supabase sync should be marked alpha/experimental.

### Verification Checklist
- [ ] `vault --help` shows `usage: vault`.
- [ ] README files do not mention private/internal systems.
- [ ] Markdown scan has no obvious private path/dashboard/personal-name leakage in public docs.
- [ ] `git diff --check` passes.
- [ ] Targeted tests or CLI smoke checks pass.
- [ ] Graphify report is rebuilt after code/doc changes.
- [ ] Changes are reviewed before commit.
