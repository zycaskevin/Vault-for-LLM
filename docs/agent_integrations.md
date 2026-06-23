# Agent Integrations

Vault-for-LLM is intentionally agent-runtime agnostic. The stable contract is
local files plus SQLite, exposed through CLI and optional stdio MCP.

Use it when you want project knowledge to be portable across agent systems
instead of locked inside one runtime's hidden memory.

## Agent-Facing Source Of Truth

For agent-driven installs or repo modifications, start with:

- [`AGENTS.md`](../AGENTS.md): concise operating rules for coding agents.
- [`docs/agent_install.md`](agent_install.md): short install runbook for agents.
- [`agent_manifest.json`](../agent_manifest.json): machine-readable install,
  database scope, runtime compatibility, safety, and validation metadata.

This lets agents decide install behavior without scraping human-oriented README
sections.

Adjacent-system notes:

- [`docs/comparisons/pageindex_headroom.md`](comparisons/pageindex_headroom.md):
  how Vault should borrow from PageIndex and Headroom without becoming either.
- [`docs/design/document_tree_navigation.md`](design/document_tree_navigation.md):
  proposed Document Map-backed tree navigation flow.
- [`docs/integrations/headroom.md`](integrations/headroom.md): optional
  Headroom layering for context-budget workflows.

## Common Agent Install Architecture

Most agent runtimes can share the same install shape:

```text
choose projectDir -> choose optional features -> install vault -> configure CLI or stdio MCP -> verify search/read/propose
```

Use runtime-specific adapters only for convenience. The durable contract is:

- `projectDir`: controls whether agents share or isolate one `vault.db`.
- `vault` CLI: works for shell-capable agents and automation.
- `vault-mcp`: works for MCP-capable agents such as Hermes Agent, Codex,
  OpenCode, Claude Code, and generic MCP hosts.
- Candidate-first memory: shared vaults should propose memory before promotion.
- MCP tool profiles: use `--tool-profile core` for daily agent sessions to
  reduce tool-schema tokens.

## Optional Feature Prompts

Agent installers should ask before installing optional features. Keep the
default small and local.

| Feature | Default | Install when | Install command |
|---|---|---|---|
| `core` | yes | Always: Markdown, SQLite, keyword search, local CLI. | `python -m pip install vault-for-llm==0.6.24` |
| `mcp` | yes for MCP-capable agents | The runtime can connect local stdio MCP tools. | `python -m pip install "vault-for-llm[mcp]==0.6.47"` |
| `obsidian_import` | no | The user already has an Obsidian vault and wants those notes searchable through Vault. | built into core CLI |
| `semantic` | no | The user wants embedding-backed semantic or hybrid search. | `python -m pip install "vault-for-llm[semantic]"` |
| `supabase` | no | The user wants optional remote sync/read paths. | `python -m pip install "vault-for-llm[supabase]"` |
| `dev` | no | Source checkout, benchmarks, PR work, or release validation. | `python -m pip install -e ".[dev]"` |

Obsidian follow-up:

```bash
vault import obsidian --vault /path/to/ObsidianVault --project-dir /path/to/project --dry-run
vault import obsidian --vault /path/to/ObsidianVault --project-dir /path/to/project --compile
```

Ask for the Obsidian vault path, run the dry-run first, then ask whether to
schedule the same `--compile` command with cron, LaunchAgent, n8n, or the host
agent for automatic sync.

Semantic follow-up:

```bash
vault install-embedding --model mix
vault semantic rebuild --project-dir /path/to/project --persist-cache --pretty
```

Supabase follow-up:

```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_ROLE_KEY=...
python -m scripts.sync_to_supabase --db /path/to/project/vault.db --document-map --health

# after applying docs/supabase_read_policy.sql, non-MCP automation can read remotely
vault remote smoke --agent-id remote-agent --query "deployment SOP" --json
vault remote search "deployment SOP" --agent-id remote-agent --json
vault remote map 12 --compact --json
vault remote read 12 --node-uid node_install --json

vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,supabase \
  --install-optional-deps \
  --supabase-sync cron \
  --remote-reader all \
  --agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation \
  --validation-pack all \
  --json
```

`--remote-reader all` writes:

- `README-remote-reader.md` for the reader workflow and safety notes.
- `remote-reader-smoke.sh` for a local shell smoke test.
- `n8n-remote-reader.workflow.json` for workflow automation.
- `coze-supabase-vault-openapi.json` for a Coze/OpenAPI connector to the Supabase RPC.
- `remote-reader.env.example` with anon-key placeholders only.

Remote readers should use `SUPABASE_ANON_KEY` or a scoped authenticated token.
Keep `SUPABASE_SERVICE_ROLE_KEY` only on trusted sync hosts.

`--agent-roster` writes a reviewed multi-agent access matrix and per-agent env
examples. `--validation-pack all` writes live verification files for remote CLI,
n8n, and Coze so the operator can prove the hosted paths work after real
credentials are configured.

Supabase is a sync/read target, not the source of truth. Ask again before using
`--include-content`.

## Integration Matrix

| System | Recommended path | Status | Notes |
|---|---|---|---|
| Hermes Agent | MCP server plus optional scheduled CLI jobs | proven locally | Use `vault-mcp` for search/read/propose. Use cron or Hermes jobs for `vault dream`, backups, and benchmark runs. |
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
search -> bounded read -> answer with source
```

In shared or multi-agent vaults, search/read calls should include the agent
identity (`agent_id`) and, when appropriate, a `max_sensitivity` cap. Only pass
`include_private=true` when the user or local policy explicitly allows that
agent to read its owner/allow-list private memory.

Use map/inspect tools only when the agent needs section navigation before
choosing a bounded read range.

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
      "args": ["--project-dir", "/path/to/your/project", "--tool-profile", "core"]
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
vault remote smoke --agent-id n8n --query "refund policy" --json
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

For token-sensitive agents, use `vault-mcp --tool-profile core`. This exposes
only `vault_search`, `vault_read_range`, `vault_memory_propose`, and
`vault_stats`. Use `review`, `remote`, `maintenance`, or `full` only when those
extra tools are needed. For cross-host Supabase readers, the `remote` profile
adds `vault_remote_search`, `vault_remote_map_show`, and
`vault_remote_read_range`; use them in that order so hosted agents search safe
summaries before asking for bounded evidence.
