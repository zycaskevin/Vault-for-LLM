# Agent Integrations

Vault-for-LLM is intentionally agent-runtime agnostic. The stable contract is
local files plus SQLite, exposed through CLI and optional stdio MCP.

Use it when you want project knowledge to be portable across agent systems
instead of locked inside one runtime's hidden memory.

## Agent-Facing Source Of Truth

For agent-driven installs or repo modifications, start with:

- [`AGENTS.md`](../AGENTS.md): concise operating rules for coding agents.
- [`agent_manifest.json`](../agent_manifest.json): machine-readable install,
  database scope, runtime compatibility, safety, and validation metadata.

This lets agents decide install behavior without scraping human-oriented README
sections.

## Common Agent Install Architecture

Most agent runtimes can share the same install shape:

```text
choose projectDir -> install vault -> configure CLI or stdio MCP -> verify search/read/propose
```

Use runtime-specific adapters only for convenience. The durable contract is:

- `projectDir`: controls whether agents share or isolate one `vault.db`.
- `vault` CLI: works for shell-capable agents and automation.
- `vault-mcp`: works for MCP-capable agents such as Hermes Agent, Codex,
  OpenCode, Claude Code, and generic MCP hosts.
- Candidate-first memory: shared vaults should propose memory before promotion.

## Integration Matrix

| System | Recommended path | Status | Notes |
|---|---|---|---|
| Hermes Agent / Nancy | MCP server plus optional scheduled CLI jobs | proven locally | Use `vault-mcp` for search/read/propose. Use cron or Hermes jobs for `vault dream`, backups, and benchmark runs. |
| OpenClaw | OpenClaw adapter in `integrations/openclaw/` or generic MCP | adapter included | Registers `vault_search`, `vault_read_range`, `vault_memory_propose`, and `vault_stats`; auto-recall is off by default. |
| n8n | CLI command node, Execute Command, HTTP wrapper, or MCP bridge | compatible | Best for workflows: compile docs, run Search QA, propose memory, backup/verify, or search before a customer-service step. |
| Codex | CLI in the workspace; MCP where the selected Codex surface supports it | compatible | Use `vault search`, `vault map read`, benchmarks, and release gates from the repo. |
| OpenCode | Generic stdio MCP where supported, or CLI in shell-capable sessions | compatible | Use the same project-dir and MCP contract as Claude Code/Codex; no dedicated adapter is required for basic use. |
| Claude Code | stdio MCP server or CLI commands | compatible | Configure `vault-mcp` as a local MCP server and prefer search -> bounded read -> cite. |
| Any MCP-compatible agent | `vault-mcp --project-dir <project>` | supported | Exposes retrieval, bounded reading, candidate-first memory, curation, stats, and optional remote read tools. |
| Any shell-capable automation | `vault` CLI | supported | No MCP required for init/add/compile/search/QA/backup workflows. |

## Shared Contract

All integrations should follow the same memory policy:

```text
search -> inspect/map -> bounded read -> answer with source
```

For new memory:

```text
propose candidate -> human/operator review -> promote only when approved
```

This keeps Vault useful across different agents without letting every runtime
write directly into active memory.

## Choose Database Scope At Install Time

Vault-for-LLM is bound to a project directory, not to Hermes, OpenClaw, Codex, or
any other runtime:

```text
one project directory = one vault.db
```

During agent setup, decide whether the agent should join an existing project
vault or use its own isolated vault.

| Scope | Meaning | Recommended for |
|---|---|---|
| Shared project vault | Multiple agents point to the same `projectDir` and share one `vault.db`. | Trusted agents working on the same confirmed project knowledge. |
| Agent-private vault | This agent gets its own `projectDir`. | Experiments, noisy agents, or agents that should not affect official memory. |
| Domain/customer vault | Each customer/domain gets a separate `projectDir`. | Sensitive data boundaries and client separation. |
| Temporary vault | A throwaway `projectDir`. | Demos, tests, and benchmarks. |

For shared vaults, keep direct writes restricted. Agents should use
`vault_memory_propose` and wait for human/operator review before promotion.

## Generic MCP Config

```json
{
  "mcpServers": {
    "vault": {
      "command": "vault-mcp",
      "args": ["--project-dir", "/path/to/your/project"]
    }
  }
}
```

Security note: `vault-mcp` is a local stdio server. It does not provide network
authentication or user-level access control. Only configure it for agents you
trust with the selected project directory.

## OpenClaw Adapter

Install from a source checkout:

```bash
bash integrations/openclaw/install.sh
```

The installer asks which Vault memory scope to use. Non-interactive examples:

```bash
# OpenClaw gets its own isolated vault.
bash integrations/openclaw/install.sh --scope private --non-interactive

# OpenClaw joins a shared vault also used by Hermes/Codex/n8n.
bash integrations/openclaw/install.sh \
  --scope shared \
  --project-dir ~/Vaults/my-project \
  --non-interactive
```

Then merge the printed config into `~/.openclaw/openclaw.json` and restart:

```bash
openclaw gateway restart
```

The adapter provides manual tools:

- `vault_search`
- `vault_read_range`
- `vault_memory_propose`
- `vault_stats`

It also ships `vault-openclaw`, a wrapper that can print an MCP config snippet:

```bash
vault-openclaw mcp-config
```

## n8n Patterns

Use the CLI when a workflow needs deterministic project-memory behavior:

```bash
vault search "refund policy source of truth" --limit 5
vault remember "Candidate: new support rule" --content "..." --reason "..."
vault db backup --verify
vault search-qa run --qa-file qa.json --output /tmp/searchqa.json
```

For long-running services, wrap the CLI or MCP server behind a small internal
HTTP service rather than exposing `vault-mcp` directly to the public internet.

## Codex and Claude Code Patterns

When the agent can run shell commands, the CLI is enough:

```bash
vault search "release checklist"
vault map show 12
vault map read 12 --lines 20-55
```

When the agent supports MCP, use `vault-mcp` and keep final answers grounded in
`vault_read_range` output rather than search previews.
