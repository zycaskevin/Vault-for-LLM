# Agent Install Runbook

This page is for agents installing Vault-for-LLM for a user. Prefer this
runbook over scraping the full README.

For adjacent systems, see the [PageIndex and Headroom comparison](comparisons/pageindex_headroom.md).
Vault may borrow document-tree navigation and context-budget ideas, but the
install path below keeps Vault local-first and governed.

## One-Sentence Prompt

```text
Install Vault-for-LLM for this project. Use vault-for-llm[mcp]==0.6.24, ask which database scope and optional features I want, ask whether I have an existing Obsidian vault to import, run vault setup-agent, and finish with a search/read/propose smoke test.
```

## What To Ask First

Ask these before installing extras or writing memory:

1. Should this vault be shared, private, domain-specific, or temporary?
2. Which project directory should hold `vault.db`?
3. Should MCP be enabled for this agent runtime?
4. Do you already have an Obsidian vault to import?
5. If Obsidian is connected, should ongoing sync be scheduled with cron, LaunchAgent, or n8n?
6. Do you want semantic search or Supabase sync? Do not enable either silently.

## Scope Choices

| Scope | Use when | Example project directory |
|---|---|---|
| `shared` | Multiple trusted agents should use the same confirmed project knowledge. | `~/Vaults/my-project` |
| `private` | One agent should have isolated memory for experiments or personal workflow. | `~/.vault-for-llm/agent-private` |
| `domain` | A customer, product, team, or business domain needs its own memory. | `~/Vaults/clinic-customer-service` |
| `temporary` | You are testing, benchmarking, or making a disposable demo. | `/tmp/vault-agent-*` |

One project directory equals one `vault.db`. Agents share memory only when they
use the same project directory.

## Default Install

Use the PyPI release unless the user explicitly asks for source development:

```bash
python -m pip install "vault-for-llm[mcp]==0.6.24"
vault setup-agent
```

For non-interactive installs:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp \
  --tool-profile core \
  --json
```

Change `--agent` to the runtime doing the work, such as `hermes`, `openclaw`,
`claude-code`, `opencode`, `codex`, or `n8n`.

## Optional Obsidian Import

If the user already has Obsidian notes, always preview before writing:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,obsidian_import \
  --obsidian-vault /path/to/ObsidianVault \
  --obsidian-sync all \
  --json
```

The first setup run dry-runs Obsidian import when `--obsidian-vault` is set.
Apply only after the user confirms the path and preview:

```bash
vault import obsidian \
  --vault /path/to/ObsidianVault \
  --project-dir /path/to/project \
  --compile
```

Generated sync templates live under the project `agent-install/` directory by
default and can include cron, macOS LaunchAgent, and n8n workflow JSON.

## MCP Setup

For daily agent use, prefer the small core profile:

```bash
vault-mcp --project-dir /path/to/project --tool-profile core
```

Use `maintenance` only when the agent needs curation or Obsidian import tools:

```bash
vault-mcp --project-dir /path/to/project --tool-profile maintenance
```

`vault-mcp` is local stdio. Do not expose it as an unauthenticated network
service.

## Smoke Test

After setup, verify the selected project directory:

```bash
vault add "Vault install smoke" \
  --project-dir /path/to/project \
  --content "Vault-for-LLM was installed and this smoke memory can be searched."

vault compile --project-dir /path/to/project --no-embed

vault search "installed smoke memory" \
  --project-dir /path/to/project \
  --limit 5

vault remember "Agent install decision" \
  --project-dir /path/to/project \
  --content "The user chose this Vault project directory and feature set during installation." \
  --reason "Keep install decisions reviewable before promotion."
```

For MCP-capable agents, also verify:

```text
vault_search -> vault_read_range -> answer with source
vault_memory_propose -> candidate created, not directly promoted
```

## Runtime Notes

| Runtime | Recommended setup |
|---|---|
| Hermes Agent / Nancy | Install PyPI package, configure `vault-mcp`, use `core` for daily recall and `maintenance` for curation. |
| Codex | Use CLI inside the workspace; use MCP when the selected Codex surface supports local MCP. |
| Claude Code | Configure `vault-mcp` as a local stdio MCP server, or shell out to CLI commands. |
| OpenCode | Use the same stdio MCP path as Claude Code/Codex, or CLI in shell-capable sessions. |
| OpenClaw | Use `integrations/openclaw/install.sh`, then `vault-openclaw status` and `vault-openclaw obsidian-import --vault ...` if needed. |
| n8n | Use Execute Command nodes for `vault` CLI, or import the generated n8n Obsidian sync workflow. |

## Safety Rules

- Do not install semantic or Supabase extras without asking first.
- Do not import Obsidian without a dry-run and user confirmation.
- Do not promote memory automatically in a shared vault unless the user explicitly approves.
- Do not expose local MCP over a public network.
- Do not paste secrets into memory; use the privacy gate and candidate workflow.
