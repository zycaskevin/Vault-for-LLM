# Agent Install Runbook

This page is for agents installing Vault-for-LLM for a user. Keep the setup
small at first. Add optional systems only after the user says they need them.

Vault works best when the installer explains one idea clearly:

```text
Choose where the memory lives, choose who may use it, then add integrations
only when they solve a real problem.
```

For adjacent systems and design comparisons, see
[PageIndex and Headroom](comparisons/pageindex_headroom.md).

## Fast Prompt For Agents

```text
Install Vault-for-LLM for this project with vault-for-llm[mcp]==0.7.15.
Ask me where the vault database should live, whether it should be private or
shared, and whether you should use a stable Python virtualenv path instead of a
temporary one. Enable MCP by default if this agent runtime supports MCP. Ask
before enabling semantic search, Supabase, Obsidian sync, Headroom, memory
maintenance agents, or developer benchmark tools. Install optional dependencies
only after I confirm. Finish with add/search and candidate-memory smoke tests.
```

## Ask Only These First

Start with five questions. Do not open with every optional feature.

1. Should this memory be `private`, `shared`, `domain`, or `temporary`?
2. Which stable project directory should hold `vault.db`?
3. If a Python virtualenv is needed, should it live in a stable path such as
   `~/.hermes/venvs/vault-for-llm/`?
4. Which setup language should generated files use: `en`, `zh-Hant`, or `zh-CN`?
5. Should MCP be enabled for this agent runtime?

After those answers, install the core path. Then ask about optional features
only when they match the user's goal.

| Optional feature | Ask when |
|---|---|
| Obsidian import/sync | The user already has notes in Obsidian, or wants Markdown round-trips. |
| Semantic search | Keyword search is not enough, or the project has many paraphrased notes. |
| Supabase sync | Agents run on different machines, or Coze/n8n/hosted tools need remote reads. |
| Headroom | Tool output, logs, or retrieved context are too large for the model window. |
| Memory agents | The user wants profile summaries, dream reports, forgetting, or periodic curation. |
| Dev/benchmark deps | The user is contributing to Vault or running release/benchmark checks. |

## Scope Choices

One project directory equals one `vault.db`. Agents share memory only when they
use the same project directory or the same reviewed remote sync layer.

| Scope | Use when | Example |
|---|---|---|
| `private` | One agent should keep isolated memory. | `~/.vault-for-llm/private-agent` |
| `shared` | Several trusted agents use the same confirmed project knowledge. | `~/Vaults/project-memory` |
| `domain` | A customer, product, team, or business area needs its own memory. | `~/Vaults/clinic-support` |
| `temporary` | The install is a disposable test or benchmark. | `/tmp/vault-agent-*` |

Do not use `/tmp/...` as a real long-lived memory path. It is fine for smoke
tests, but it can disappear after reboot. For scheduled jobs or MCP servers,
also prefer a stable virtualenv path such as `~/.hermes/venvs/vault-for-llm/`.

## Core Install

Use the PyPI release unless the user explicitly asks for source development:

```bash
python -m pip install "vault-for-llm[mcp]==0.7.15"
vault setup-agent
```

`setup-agent` also registers the current Agent/runtime in the local registry at
`~/.vault-for-llm/agent-registry.json`. Other tools on the same machine can run
`vault update-status` to see which Agents are connected, which project vaults
they use, and which `vault automation handoff --project-dir ...` commands should
be read before starting work.
The same status payload includes `agent_update_notices`, so one updated runtime
can write `~/.vault-for-llm/update-status.json` and other local runtimes can see
whether they should upgrade or restart before using the shared project memory.
MCP-capable agents can use `vault_update_status` and
`vault_automation_handoff` from the `core` profile for the same startup flow.
Agents should read existing status first with `vault update-status --read-status`
or MCP `read_status=true`. If that file is missing, they can fall back to
`vault update-status` or MCP `vault_update_status` with `check_pypi=false`.
When an Agent knows its own runtime id, it should pass `--agent <id>` or MCP
`agent_id` so Vault returns `current_agent_notice` and `startup_checklist` for
that runtime.

For disposable smoke tests, set `VAULT_AGENT_REGISTRY_DIR` to a temporary
directory or use a clearly disposable `--agent` id. This avoids updating the
real `~/.vault-for-llm/agent-registry.json` while testing an installer flow.

After one runtime upgrades Vault, run `vault update-status --write-status` and
`vault agent doctor` so the other registered runtimes can see a fresh shared
notice. `setup-agent` writes `agent-install/refresh-update-status.sh` and
`README-agent-update-rollout.md` for this exact post-upgrade rollout.
MCP-only runtimes should call `vault_update_status` with `doctor=true`,
`agent_id=<runtime>`, and `max_status_age_minutes=1440` for the same health
check without adding another MCP tool.

The default memory layout is `hybrid`: one shared project vault plus one private
Agent vault. The generated `agent-install/hybrid-vault-layout.json` is the
public-safe coordination file for future Agents.
`setup-agent` also writes `agent-install/README-agent-adapters.md` plus Codex,
Claude Code, OpenClaw, and Hermes startup templates so common runtimes can
reuse the same update-status -> handoff -> search/read/propose startup flow.
It also writes `agent-install/README-runtime-update-playbook.md` and
`runtime-update-playbook.json`, a copyable cross-runtime rule for what to do at
startup, after one runtime upgrades Vault, and when the shared notice is stale.
Use `vault agent startup-doctor --template-dir <project>/agent-install --json`
to verify that an existing install pack still has the current fleet-aware
handoff contract.
To safely paste one generated startup template into a runtime instruction file,
preview first and then apply:

```bash
vault agent install-runtime-template --runtime codex --target ./AGENTS.md
vault agent install-runtime-template --runtime codex --target ./AGENTS.md --apply
```

The command writes a marked Vault block, replaces that block on later runs, and
backs up existing target files before changing them.
The installer also writes `agent-install/mcp-startup.json` and
`agent-install/README-mcp-startup.md`, which define the MCP startup sequence:
`vault_update_status` -> `vault_automation_handoff` -> search/read/propose.
When the handoff payload includes `fleet_health_content` or
`pipeline_receipt_content`, generated startup guides tell agents to read those
startup prefaces before the selected cycle/inbox `content`.
It also writes `agent-install/README-update-status.md`,
`agent-install/update-status-contract.json`, cron, and LaunchAgent templates for
sharing local update notices across Agent runtimes.

For an agent-run install:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --memory-layout hybrid \
  --features core,mcp \
  --tool-profile core \
  --language en \
  --json
```

Change `--agent` to the runtime doing the work, such as `hermes`, `openclaw`,
`claude-code`, `opencode`, `codex`, or `n8n`.

For long-lived installs, generate a reboot-safe virtualenv helper:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp \
  --stable-venv ~/.hermes/venvs/vault-for-llm \
  --write-stable-venv-script \
  --json
```

## Optional Feature Recipes

Use these only after the user chooses the feature.

### Semantic Search

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,semantic \
  --install-optional-deps \
  --install-embedding-model mix \
  --json
```

Semantic setup downloads a local embedding model only when
`--install-embedding-model` is passed.

### Supabase Sharing

Use simple setup first:

```bash
vault setup-agent \
  --non-interactive \
  --agent work-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase \
  --install-optional-deps \
  --supabase-setup simple \
  --supabase-sync cron \
  --remote-reader all \
  --validation-pack all \
  --json
```

Choose `--supabase-setup advanced` only when the user needs multi-agent RLS,
Coze/n8n read-only access, or sensitivity-based sharing. Remote readers should
use `SUPABASE_ANON_KEY` or another read-scoped token, not
`SUPABASE_SERVICE_ROLE_KEY`.

### Obsidian Import And Sync

Always preview the vault path before writing:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,obsidian_import \
  --obsidian-vault /path/to/ObsidianVault \
  --obsidian-sync all \
  --json
```

Apply import only after the user confirms the preview:

```bash
vault import obsidian \
  --vault /path/to/ObsidianVault \
  --project-dir ~/Vaults/project-memory \
  --compile
```

Generated sync templates can include cron, macOS LaunchAgent, and n8n workflow
JSON under `agent-install/`.

### Headroom Context Compression

Headroom is useful when the selected context is still too large after Vault
retrieval:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,headroom \
  --install-optional-deps \
  --json
```

Use Vault to choose source ranges first. Use Headroom after retrieval to reduce
large logs or tool output. Keep final citations tied to original
`vault_read_range` output, not to compressed summaries.

### Memory Maintenance Agents

Generate Profile / Dream / Forgetting guidance when the user wants the vault to
stay useful over time:

```bash
vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,memory_agents \
  --language zh-Hant \
  --json
```

This writes `agent-install/README-memory-agents.md`. It does not install a
model, schedule jobs, promote memories, or delete anything. Treat memory agents
as report-only or candidate-only until the user approves a stronger policy.

To generate scheduled report-first maintenance templates:

```bash
vault setup-agent \
  --non-interactive \
  --agent automation-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,memory_agents \
  --automation-schedule all \
  --automation-mode balanced \
  --automation-command cycle \
  --automation-write-workspace \
  --automation-include-transcripts \
  --json
```

This writes cron, macOS LaunchAgent, n8n, and README templates under
`agent-install/`. `cycle` is the default scheduled command: it writes bounded
learning-policy hints from reviewed candidate outcomes before running safe
automation. Add `--automation-command run` for a simpler maintenance-only
schedule. Add `--automation-apply` only after the user reviews
`automation_policy.yaml` and accepts reversible archive actions.
Generated schedules also write `reports/automation/inbox-latest.json` after a
successful run, so the next agent can start from the compact review inbox
instead of reading full automation reports.
Add `--automation-write-workspace` when the scheduled cycle should also write
`reports/automation/cycle-latest.json` and `reports/automation/cycle-latest.md`,
a compact daily memory workbench for the next agent.
Generated schedule README files include
`vault automation handoff --project-dir ...` as the read-only startup command
for the next agent.
Add `--automation-include-transcripts` when the next agent should also see
metadata-only paths for uncaptured transcript exports. The scheduled handoff
does not read transcript contents and does not write session candidates by
itself.
Add `--automation-capture-transcripts --automation-apply` only when the user
explicitly wants the scheduled cycle to read discovered transcript files and
write gated review candidates. This closes the transcript-to-candidate loop,
but it still never promotes active memory or includes raw transcript content in
the generated handoff.
Add `--automation-auto-promote-low-risk` only when the user explicitly wants
setup-agent to write `automation_policy.yaml` with low-risk candidate
auto-promotion enabled. Pair it with `--automation-apply` when scheduled runs
should actually promote eligible candidates; without `--apply`, scheduled runs
preview the policy only. The generated schedule README will show whether this
policy is enabled.

### Multi-Agent Roster

When several agents need different access levels:

```bash
vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase,memory_agents \
  --supabase-setup advanced \
  --remote-reader all \
  --agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation \
  --validation-pack all \
  --json
```

`--agent-roster` writes `agent-roster.json`, `AGENT_ACCESS_MATRIX.md`,
`agent-env/*.env.example`, and `agent-setup-commands.sh`.
Roster roles are intentionally fixed so access defaults stay reviewable:
`work`, `profile`, `care`, `dream`, `remote`, `automation`, and `observer`.

## MCP Profiles

Use the smallest tool profile that can do the job:

| Profile | Use when |
|---|---|
| `core` | Daily search and bounded reads. |
| `review` | Candidate memory inspection and promotion. |
| `remote` | Remote read helpers. |
| `maintenance` | Curation, Obsidian import, and memory upkeep. |
| `full` | Trusted local operator needs everything. |

Daily setup:

```bash
vault-mcp --project-dir ~/Vaults/project-memory --tool-profile core
```

`vault-mcp` is local stdio. Do not expose it as an unauthenticated network
service.

For per-tool examples and agent-facing rules, see
[`docs/mcp_tool_reference.md`](mcp_tool_reference.md).

## Smoke Test

After setup, run the generated local smoke script first:

```bash
sh ~/Vaults/project-memory/agent-install/local-smoke.sh
```

It verifies `add`, machine-readable `search --json`, `remember`, and
`candidates` without promoting or deleting memory. The equivalent manual flow is:

```bash
vault add "Vault install smoke" \
  --project-dir ~/Vaults/project-memory \
  --content "Vault-for-LLM was installed and this smoke memory can be searched."

vault compile --project-dir ~/Vaults/project-memory --no-embed

vault search "installed smoke memory" \
  --project-dir ~/Vaults/project-memory \
  --limit 5 \
  --json

vault remember "Agent install decision" \
  --project-dir ~/Vaults/project-memory \
  --content "The user chose this Vault project directory and feature set during installation." \
  --reason "Keep install decisions reviewable before promotion."

vault candidates --project-dir ~/Vaults/project-memory
```

After a real agent work session, capture transcript lessons into the same
candidate queue:

```bash
vault capture session ~/Downloads/codex-session.jsonl --project-dir ~/Vaults/project-memory --pretty
vault capture session ~/Downloads/codex-session.jsonl --project-dir ~/Vaults/project-memory --write-candidates
```

The first command previews the extracted decisions, pitfalls, workflows, and
source-of-truth lines. The second writes candidates only; it does not promote
memory, delete rows, or change permissions.

For MCP-capable agents, also verify this flow:

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
| n8n | Use Execute Command nodes for `vault` CLI, or import generated n8n workflows. |

## Safety Rules

- Do not install semantic, Supabase, Headroom, or benchmark extras without
  asking first.
- Do not import Obsidian without preview and user confirmation.
- Do not promote memory automatically in a shared vault unless the user
  explicitly approves.
- Do not expose local MCP over a public network.
- Do not paste secrets into memory; use the privacy gate and candidate workflow.
- Keep raw private conversations, persona files, and high-sensitivity profile
  notes local unless the user explicitly approves sharing reviewed summaries.

## Related Docs

- Supabase setup: [supabase_setup.md](supabase_setup.md)
- Memory governance: [memory_governance.md](memory_governance.md)
- Dream reports: [dream_workflow.md](dream_workflow.md)
- Agent integrations: [agent_integrations.md](agent_integrations.md)
- Headroom integration: [integrations/headroom.md](integrations/headroom.md)
