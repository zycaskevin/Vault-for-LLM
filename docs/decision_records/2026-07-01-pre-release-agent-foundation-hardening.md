# Pre-Release Agent Foundation Hardening

## Context

Vault-for-LLM is moving toward a public-facing "agent foundation" release. The
goal is not to ship every small improvement as a separate version. Larger
agent-facing refinements should be grouped into complete pull requests, then
released as one coherent package after install and smoke validation.

The immediate pre-release scope is:

1. CLI JSON contract cleanup for commands agents commonly call.
2. Agent install template validation for Codex, Claude Code, Hermes Agent,
   OpenClaw, Coze, and n8n.
3. Obsidian-as-GUI refinement: incremental import, folder-governance rules,
   review inbox export, and wikilink-to-graph integration.
4. Gateway / Remote architecture clarity for same-machine agents, cross-host
   remote readers, Supabase adapters, and a future Vault Remote server.

## Decision

Do not publish another release until these surfaces are validated together.

The CLI contract should be machine-readable wherever agents need to automate a
check. In this pass, `vault gateway health --json` provides a non-server
readiness probe, and `vault export obsidian --json` lets installers preview the
human-readable Obsidian export without scraping prose.

Gateway remains a thin adapter boundary, not a replacement database:

- local MCP runtimes should keep using `vault-mcp` when possible;
- local scripts, non-MCP runtimes, and future devices may use Gateway;
- hosted or cross-host agents should use Supabase remote-reader templates by
  default;
- remote writes remain candidate-first unless a future reviewed multi-master
  design is explicitly introduced.

Obsidian remains the human-facing knowledge garden and review inbox, while
Vault SQLite remains the governed memory source of truth for agents.

## Consequences

- Normal users can stay in the short setup path and daily report.
- Agents can rely on JSON probes instead of parsing terminal text.
- Gateway, CLI, MCP, Supabase, and future Vault Remote servers remain adapters
  around the same governed memory model.
- Supabase near-realtime sync is still local-to-remote push; it is not active
  bidirectional multi-master sync.
- Obsidian import/export is safe and file-based first, with conflict-heavy live
  mirroring deferred until review surfaces are mature.

## Validation Targets

- JSON contract tests for Gateway health and Obsidian export.
- Setup-agent tests proving local runtime templates and hosted reader templates
  are generated together.
- Obsidian import/export tests for incremental sync, folder rules, review inbox,
  and wikilink graph edges.
- Gateway tests for token auth, read policy, candidate-first writes, and audit.
- Release-readiness checks before publishing: package build, install smoke,
  README command smoke, module-size gate, privacy scans, and Python matrix CI.
