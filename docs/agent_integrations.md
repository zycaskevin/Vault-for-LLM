# Agent Integrations

Vault-for-LLM is intentionally agent-runtime agnostic. The stable contract is
local files plus SQLite, exposed through CLI and optional stdio MCP.

Use it when you want project knowledge to be portable across agent systems
instead of locked inside one runtime's hidden memory.

## Integration Matrix

| System | Recommended path | Status | Notes |
|---|---|---|---|
| Hermes Agent / Nancy | MCP server plus optional scheduled CLI jobs | proven locally | Use `vault-mcp` for search/read/propose. Use cron or Hermes jobs for `vault dream`, backups, and benchmark runs. |
| OpenClaw | OpenClaw adapter in `integrations/openclaw/` or generic MCP | adapter included | Registers `vault_search`, `vault_read_range`, `vault_memory_propose`, and `vault_stats`; auto-recall is off by default. |
| n8n | CLI command node, Execute Command, HTTP wrapper, or MCP bridge | compatible | Best for workflows: compile docs, run Search QA, propose memory, backup/verify, or search before a customer-service step. |
| Codex | CLI in the workspace; MCP where the selected Codex surface supports it | compatible | Use `vault search`, `vault map read`, benchmarks, and release gates from the repo. |
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
