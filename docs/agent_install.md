# Agent Install Runbook

This page is for agents installing Vault-for-LLM for a user. Prefer this
runbook over scraping the full README.

For adjacent systems, see the [PageIndex and Headroom comparison](comparisons/pageindex_headroom.md).
Vault may borrow document-tree navigation and context-budget ideas, but the
install path below keeps Vault local-first and governed.

## One-Sentence Prompt

```text
Install Vault-for-LLM for this project. Use vault-for-llm[mcp]==0.6.40, ask which database scope I want, ask for a stable project directory, ask whether any Python virtualenv you create should live in a stable path such as ~/.hermes/venvs/vault-for-llm/ instead of /tmp, ask for setup language when this is a manual CLI install, ask separately about MCP, semantic search, Supabase sync, Supabase remote reader templates for shell/n8n/Coze, Headroom context compression, Profile / Dream / Forgetting memory-agent guidance, and dev/benchmark dependencies, install selected optional dependencies when I confirm, ask whether semantic should download a local ONNX embedding model, ask whether I have an existing Obsidian vault to import, run vault setup-agent with --stable-venv or --write-stable-venv-script when a long-lived venv is needed, and finish with a search/read/propose smoke test.
```

## What To Ask First

Ask these before installing extras or writing memory:

1. Should this vault be shared, private, domain-specific, or temporary?
2. Which project directory should hold `vault.db`?
3. If I create or move a Python virtualenv, should it use a stable path such as `~/.hermes/venvs/vault-for-llm/` instead of `/tmp`?
4. Which setup language should generated installer output use (`en`, `zh-Hant`, or `zh-CN`)?
5. Should MCP be enabled for this agent runtime?
6. Do you already have an Obsidian vault to import?
7. If Obsidian is connected, should ongoing sync be scheduled with cron, LaunchAgent, or n8n?
8. Do you want optional semantic search and embedding workflow dependencies?
9. Do you want optional Supabase sync/read dependencies for remote or cross-host memory?
10. If Supabase is selected, should I generate a simple setup guide, advanced RLS notes, or no guide?
11. Do you want optional Headroom context compression for long logs, tool output, or large retrieved context?
12. If Supabase is selected, should I generate remote reader templates for shell, n8n, Coze, or all?
13. Do you want developer/benchmark dependencies for source work or release validation?
14. If any optional feature is selected, should I install its Python dependencies now?
15. If semantic is selected, should I download and configure a local ONNX embedding model now?
16. If Supabase is selected, should I generate daily sync templates for cron, LaunchAgent, or n8n?
17. Should user profile/persona memory stay private by default, with only reviewed summaries shared?
18. Should Profile / Dream / Forgetting memory-agent guidance be generated?
19. Should I generate `agent-install/setup-stable-venv.sh` for a reboot-safe Python environment?

Keep MCP defaulting to yes for MCP-capable runtimes. Keep semantic, Supabase,
Headroom, and dev dependencies defaulting to no unless the user confirms.
When the user confirms optional dependency installation, pass
`--install-optional-deps`. For semantic local model setup, pass
`--install-embedding-model mix` or the selected `zh`/`en`/`mix` model.
For long-lived agent installs or scheduled jobs, pass `--write-stable-venv-script`
or `--stable-venv ~/.hermes/venvs/vault-for-llm` so the installer writes
`agent-install/setup-stable-venv.sh`.

## Scope Choices

| Scope | Use when | Example project directory |
|---|---|---|
| `shared` | Multiple trusted agents should use the same confirmed project knowledge. | `~/Vaults/my-project` |
| `private` | One agent should have isolated memory for experiments or personal workflow. | `~/.vault-for-llm/agent-private` |
| `domain` | A customer, product, team, or business domain needs its own memory. | `~/Vaults/clinic-customer-service` |
| `temporary` | You are testing, benchmarking, or making a disposable demo. | `/tmp/vault-agent-*` |

One project directory equals one `vault.db`. Agents share memory only when they
use the same project directory.

`/tmp/...` directories are disposable test workspaces, not package install
locations and not stable shared vaults. Do not reuse a version-labelled temp
path such as `/tmp/vault-install-test-0.6.24` as a real project memory path.
For shared memory, choose a stable directory such as `~/Vaults/my-project`.
For long-lived installs, also use a stable Python virtualenv path. Hermes profile
installs should prefer a path such as `~/.hermes/venvs/vault-for-llm/`;
temporary venvs under `/tmp/...` can disappear after reboot and should not be
used by scheduled jobs.

## Default Install

Use the PyPI release unless the user explicitly asks for source development:

```bash
python -m pip install "vault-for-llm[mcp]==0.6.40"
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

To install selected optional dependencies immediately:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,semantic,supabase,headroom,memory_agents \
  --language en \
  --install-optional-deps \
  --install-embedding-model mix \
  --write-stable-venv-script \
  --supabase-setup simple \
  --remote-reader all \
  --agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation \
  --validation-pack all \
  --json
```

To install Supabase support and generate a daily cron template:

```bash
vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,supabase \
  --language zh-Hant \
  --install-optional-deps \
  --supabase-setup simple \
  --supabase-sync cron \
  --remote-reader all \
  --agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation \
  --validation-pack all \
  --json
```

Use simple Supabase setup by default. Only choose `--supabase-setup advanced`
when the user explicitly asks for multi-agent RLS, Coze/n8n read-only access, or
sensitivity-based sharing.

When remote readers are needed, use `--remote-reader shell|n8n|coze|all`. This
writes `agent-install/README-remote-reader.md`, a shell smoke script, a n8n
workflow, a Coze OpenAPI connector template, and an env example. Remote readers
must use `SUPABASE_ANON_KEY` or an authenticated read token, not
`SUPABASE_SERVICE_ROLE_KEY`.

When several agents should share a governed memory system, pass
`--agent-roster`. The format is:

```text
agent_id:role[:scope[:max_sensitivity]]
```

Example:

```bash
--agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation
```

This writes `agent-roster.json`, `AGENT_ACCESS_MATRIX.md`,
`agent-env/*.env.example`, and `agent-setup-commands.sh`.

For real external verification, pass `--validation-pack remote|n8n|coze|all`.
This writes `README-live-validation.md`, `validate-remote-reader.sh`,
`VALIDATE-n8n.md`, and/or `VALIDATE-coze.md`.

To generate Profile / Dream / Forgetting agent guidance:

```bash
vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,memory_agents \
  --language zh-Hant \
  --json
```

This writes `agent-install/README-memory-agents.md`. It does not install a
model, schedule jobs, promote memories, or delete anything. Treat memory agents
as report-only or candidate-only until the user approves a stronger policy.

## Memory Governance Defaults

Keep `L0` through `L3` as memory depth layers. Do not treat them as permissions.
For access and sync decisions, prefer frontmatter or remote-table metadata:

```yaml
scope: private | project | shared | public
sensitivity: low | medium | high | restricted
owner_agent: profile-agent
allowed_agents: ["profile-agent", "work-agent", "product-agent"]
status: candidate | reviewed | active | archived
memory_type: identity | user_profile | context | decision | pitfall | procedure | care_summary
expires_at: 2026-07-01
```

For user profile memory:

- `L0`: minimal identity only.
- `L1`: durable work preferences and collaboration rules.
- `L2`: recent state or care summaries, with expiry.
- private `L3` or a private vault: deep analysis and raw private interaction history.

When agents share Supabase or Obsidian sync, share reviewed summaries and project
knowledge. Keep raw private conversations, persona files, and high-sensitivity
profile notes local to the owning agent unless the user explicitly says
otherwise. See [memory governance layers](memory_governance.md).

The generated Supabase sync command uses an explicit database path:

```bash
python -m scripts.sync_to_supabase --db /path/to/project/vault.db --document-map --health
```

Keep `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the project `.env` or
another reviewed environment source before enabling the scheduled job.

## Optional Headroom Compression

Headroom is not part of Vault's core memory governance. Offer it only when the
user has long logs, large terminal output, large RAG/tool results, or clear
context-window/token pressure:

```bash
python -m pip install headroom-ai

vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,headroom \
  --tool-profile core \
  --json
```

Or let the setup wizard install it after the user confirms:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,headroom \
  --install-optional-deps \
  --json
```

Use Vault first to decide what to search and which bounded source range to
read. Use Headroom after retrieval only when the selected context is still too
large. Keep final citations tied to original `vault_read_range` output, not to
compressed summaries.

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

Use `review` when a trusted operator or agent needs to inspect and promote
candidate memory:

```bash
vault-mcp --project-dir /path/to/project --tool-profile review
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

vault candidates --project-dir /path/to/project
```

For MCP-capable agents, also verify:

```text
vault_search -> vault_read_range -> answer with source
vault_memory_propose -> candidate created, not directly promoted
vault_memory_candidates -> candidate review queue visible in review profile
```

## Runtime Notes

| Runtime | Recommended setup |
|---|---|
| Hermes Agent | Install PyPI package, configure `vault-mcp`, use `core` for daily recall and `maintenance` for curation. |
| Codex | Use CLI inside the workspace; use MCP when the selected Codex surface supports local MCP. |
| Claude Code | Configure `vault-mcp` as a local stdio MCP server, or shell out to CLI commands. |
| OpenCode | Use the same stdio MCP path as Claude Code/Codex, or CLI in shell-capable sessions. |
| OpenClaw | Use `integrations/openclaw/install.sh`, then `vault-openclaw status` and `vault-openclaw obsidian-import --vault ...` if needed. |
| n8n | Use Execute Command nodes for `vault` CLI, or import the generated n8n Obsidian sync workflow. |

## Safety Rules

- Do not install semantic, Supabase, or Headroom extras without asking first.
- Do not import Obsidian without a dry-run and user confirmation.
- Do not promote memory automatically in a shared vault unless the user explicitly approves.
- Do not expose local MCP over a public network.
- Do not paste secrets into memory; use the privacy gate and candidate workflow.
