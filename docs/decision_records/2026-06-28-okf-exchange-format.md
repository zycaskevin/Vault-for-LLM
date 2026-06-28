# OKF As Exchange Format

Date: 2026-06-28

## Decision

Vault-for-LLM should support OKF-style Markdown bundles as an import/export
exchange format, not replace the SQLite-backed vault with OKF files.

OKF is useful because it standardizes portable agent knowledge as Markdown
concept files with frontmatter. Vault is still responsible for governance,
retrieval, review, lifecycle automation, access metadata, MCP integration, and
the local GUI.

## Boundary

```text
OKF      portable file bundle for agent knowledge
Vault    local memory engine and governance/runtime layer
```

Vault should be able to consume OKF bundles and publish OKF bundles. It should
not become only an OKF editor.

## Safe Defaults

- Import OKF as memory candidates by default.
- Require `type` in concept frontmatter.
- Treat broken Markdown links as warnings.
- Preserve unknown frontmatter fields when possible.
- Exclude private/restricted memory from OKF export unless explicitly requested.
- Export Vault governance metadata as custom frontmatter fields.

## Rationale

OKF is intentionally small and portable. That is its strength. It does not define
privacy gates, candidate review, temporal validity, search quality checks,
automation feedback, or multi-agent access policy.

Vault should add those missing production-minded layers while staying compatible
with a plain Markdown bundle that other tools can read.

## Follow-Up Work

1. Implement `vault okf validate`.
2. Implement `vault import okf`.
3. Implement `vault export okf`.
4. Add tests for concept frontmatter, `index.md`, `log.md`, broken-link
   warnings, safe export filters, and search/bounded-read behavior after import.
