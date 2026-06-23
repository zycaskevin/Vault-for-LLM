# Vault-for-LLM

Local-first project memory for AI agents.

Vault-for-LLM turns project notes, decisions, bugs, SOPs, Obsidian notes, and
agent-written memory candidates into a portable SQLite vault that agents can
search, read in bounded ranges, cite, test, back up, and sync when needed.

It is not trying to replace your model, your wiki, or hosted memory systems.
It sits between them: a small governed memory layer that helps agents reuse
project knowledge without losing source, scope, or reviewability.

The default path is agent-driven: ask your coding agent to install Vault, choose
where the database should live, and run a small search/read/propose smoke test.
Manual commands are still here, but they are no longer the main story.

## Why It Exists

Most agent failures are practical, not mysterious:

- a new session forgets why a decision was made
- an agent reads the wrong outdated note
- useful fixes stay buried in chat history
- private observations get mixed with shared project knowledge
- a team cannot tell whether retrieval is actually working

Vault-for-LLM is built for that practical gap. It gives agents a place to ask:

> What has this project already learned, where did it come from, and am I
> allowed to use it?

## What You Get

- **Local-first memory** - Markdown and SQLite by default. No cloud service is
  required for core use.
- **Agent-friendly retrieval** - CLI and MCP tools for search, bounded reads,
  candidate memory, Document Map inspection, and optional remote reads.
- **Candidate-first writes** - agents can propose memory before it becomes
  active knowledge.
- **Governance metadata** - scope, sensitivity, owner agent, allowed agents,
  memory type, and expiry travel with each memory.
- **Obsidian bridge** - import existing Obsidian notes into Vault, or export
  compiled Vault knowledge back into Obsidian-readable Markdown.
- **Optional remote sharing** - Supabase sync and read-only RPC templates let
  agents on different machines share reviewed memory.
- **Report-first automation** - generated cron, LaunchAgent, and n8n templates
  can run memory maintenance without silently deleting or promoting memory.
- **Measurable recall** - Search QA and onboarding benchmarks measure whether
  agents can find the right source, not just sound confident.

## When To Use It

Use Vault-for-LLM when:

- you work with Claude Code, Codex, Hermes Agent, OpenClaw, OpenCode, n8n, or
  another agent that needs project context across sessions
- you want a shared project memory without giving every agent raw private notes
- you already have Markdown or Obsidian notes and want agents to search them
  with citations
- you need local-first storage but optional Supabase sharing for other hosts
- you care about retrieval quality enough to test it

Do not start here if you only need a hosted vector database, a personal notes
app, or an automatic conversation memory product.

## Install

### Agent-Driven Install

For most users, the right path is to ask an agent to install it:

```text
Install Vault-for-LLM for this project. Use vault-for-llm[mcp]==0.6.59.
Ask whether the vault should be shared, private, domain-specific, or temporary.
Ask for a stable project directory and generate a stable venv script for
long-lived agent jobs. Ask separately about MCP, semantic search, Supabase,
Obsidian import, Headroom compression, and memory-agent guidance. Install only
the optional dependencies I approve. Finish with a search/read/propose smoke test.
```

The agent should use the guided installer:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "vault-for-llm[mcp]==0.6.59"

vault setup-agent
```

For non-interactive agent installs:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --features core,mcp,supabase,headroom \
  --write-stable-venv-script \
  --supabase-setup simple \
  --remote-reader shell \
  --automation-schedule cron \
  --json
```

This can generate `agent-install/setup-stable-venv.sh`, so scheduled jobs and
MCP commands do not depend on a disposable `/tmp` virtualenv.

### Manual Quickstart

```bash
pip install "vault-for-llm[mcp]==0.6.59"

vault init ~/Vaults/demo
vault add "First lesson" \
  --content "The bug was caused by a missing cache key. The fix was adding provider metadata." \
  --project-dir ~/Vaults/demo
vault compile --project-dir ~/Vaults/demo --no-embed
vault search "cache key" --project-dir ~/Vaults/demo
```

## Daily Agent Flow

The intended loop is simple:

1. **Search first** - find likely source notes.
2. **Read bounded ranges** - avoid dumping whole documents into context.
3. **Answer with sources** - keep citations tied to original Vault content.
4. **Propose memory** - let agents suggest new lessons as candidates.
5. **Review before promotion** - keep active memory clean and auditable.

For MCP-capable runtimes:

```bash
vault-mcp --project-dir ~/Vaults/my-project --tool-profile core
```

Recommended core tools:

- `vault_search`
- `vault_read_range`
- `vault_memory_propose`
- `vault_stats`

MCP guides:

- Practical tool reference: [docs/mcp_tool_reference.md](docs/mcp_tool_reference.md)
- Workflow and token-budget guidance: [docs/mcp_memory_workflow.md](docs/mcp_memory_workflow.md)

## Memory Model

Vault uses depth layers for how memory is used:

| Layer | Purpose |
|---|---|
| `L0` | identity and project framing |
| `L1` | stable facts, rules, and preferences |
| `L2` | active context, summaries, current work |
| `L3` | detailed knowledge, SOPs, bugs, decisions, source notes |

Access is not controlled by layer alone. Use governance metadata for policy:

- `scope`: private, project, shared, public
- `sensitivity`: low, medium, high, restricted
- `owner_agent`
- `allowed_agents`
- `memory_type`
- `expires_at`

Searches record lightweight usage counters (`access_count`, `citation_count`,
`last_accessed_at`). The default lightweight reranker uses these signals as a
small, saturated boost, so frequently useful memories can rise slightly without
overriding source relevance, trust, freshness, or access policy.

Short-lived memories with `expires_at` can be moved to `status: archived`
instead of deleted:

```bash
vault usage stats
vault usage archive-expired --apply
```

Design notes: [docs/memory_governance.md](docs/memory_governance.md).

Policy-based automation lets agents handle routine maintenance while humans
keep ownership of the rules:

```bash
vault automation plan --write-policy
vault automation run
vault automation run --apply
vault automation cycle --apply
```

Balanced automation can pre-fill the memory candidate queue with Dream and
Forgetting suggestions when `--apply` is used, but it still never promotes
candidates or hard-deletes memory. Use `conservative` mode when scheduled jobs
should only write reports.

`vault automation eval` reads promoted/rejected/blocked candidate outcomes and
shows which suggestion sources are earning trust over time. The signal guides
future curation priority; it does not override review, privacy, or access
policy.

For scheduled agents, `vault automation eval --write-learning-policy` also
writes `reports/automation/learning_policy.json`. That file contains bounded
priority hints, such as preferring a suggestion source that is often promoted
or downgrading one that is often rejected. The bounds are deliberately small
and never authorize auto-promotion, deletion, or privacy bypass.

Dream and scheduled automation can read that policy on the next run. They use
it to annotate and sort candidate suggestions, so reviewers see better-ranked
cleanup work first while the formal promote/reject decision remains explicit.
`vault automation cycle` runs that feedback-to-curation loop in one command:
evaluate reviewed outcomes, write the bounded learning policy, then run safe
automation so Dream can consume the latest hints.

Agent installers can generate cron, LaunchAgent, or n8n templates with
`vault setup-agent --automation-schedule cron|launchagent|n8n|all`. Scheduled
templates default to `vault automation cycle`, so long-running agents can learn
from reviewed outcomes before the next maintenance pass. The schedule is still
report-first unless the user explicitly opts into `--automation-apply`; pass
`--automation-command run` for a simpler maintenance-only schedule.

Automation details: [docs/automation.md](docs/automation.md).

## Memory Maintenance Agents

Vault can generate guidance for Profile, Dream, and Forgetting agents. These
agents are conservative by default: Dream runs produce reports first, cleanup
checks look for stale entries, duplicates, and weak metadata, and `apply_safe`
paths should create backups so rollback remains possible. Promotion, deletion,
archive, or expiry actions should stay candidate-only until a user-approved
policy allows stronger automation.

Setup guide: [docs/agent_install.md](docs/agent_install.md).
Governance details: [docs/memory_governance.md](docs/memory_governance.md).

## Integrations

| System | Path |
|---|---|
| Claude Code / Codex / OpenCode | CLI or local stdio MCP |
| Hermes Agent / OpenClaw | CLI, MCP, generated agent install files |
| n8n | generated Supabase sync and remote-reader workflow templates |
| Coze or hosted agents | Supabase read-only RPC and OpenAPI template |
| Obsidian | import existing notes, export compiled Vault knowledge |
| Headroom | optional compression after Vault has narrowed context |

Start here: [docs/agent_integrations.md](docs/agent_integrations.md).

## Optional Supabase Sharing

SQLite remains the source of truth. Supabase is optional.

Use it when agents on different machines or hosted platforms need to read a
shared, filtered copy of reviewed project memory.

```bash
pip install "vault-for-llm[supabase]==0.6.59"
python -m scripts.sync_to_supabase --db ~/Vaults/my-project/vault.db --document-map --health
```

Setup guide: [docs/supabase_setup.md](docs/supabase_setup.md).
Read policy template: [docs/supabase_read_policy.sql](docs/supabase_read_policy.sql).

## Obsidian

Import an existing Obsidian vault:

```bash
vault import obsidian --vault ~/Documents/ObsidianVault --project-dir ~/Vaults/my-project --dry-run
vault import obsidian --vault ~/Documents/ObsidianVault --project-dir ~/Vaults/my-project --compile
```

Export compiled Vault knowledge back into Obsidian-readable notes:

```bash
vault export obsidian --project-dir ~/Vaults/my-project --vault ~/Documents/ObsidianVault
```

The importer skips `.obsidian`, `.trash`, `.git`, and generated Vault export
folders by default.

## Retrieval Quality

Vault includes lightweight QA tools so retrieval can be tested instead of
trusted by intuition alone.

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --output /tmp/vault-searchqa.json
```

Current evidence is intentionally described as retrieval evidence, not final
answer quality:

- project onboarding benchmark: Vault found source-backed project memory across
  28/28 tasks in local proof runs
- LoCoMo retrieval probes: hierarchical session + local evidence-window
  retrieval reached high evidence recall in official-scored categories
- official answerer/judge scores are separate and require model-provider runs

More detail: [docs/agent_onboarding_benchmark.md](docs/agent_onboarding_benchmark.md) and
[docs/search_qa_benchmarking.md](docs/search_qa_benchmarking.md).

## Maturity

| Area | Status |
|---|---|
| local SQLite, Markdown compile, keyword search | stable |
| CLI setup, candidate memory, bounded reads | usable |
| MCP tools | usable, profile selection recommended |
| Obsidian import/export | usable |
| Supabase sync and remote read templates | advanced optional |
| policy-based memory automation | usable-alpha |
| semantic search, API/local embedding providers, rerank, benchmark adapters | evolving |
| Profile / Dream / Forgetting agents | guidance-first, not autonomous deletion |

Vault-for-LLM is still pre-1.0. The core local path is intentionally conservative;
advanced integrations are powerful, but should be enabled deliberately.

## Documentation Map

- Agent install runbook: [docs/agent_install.md](docs/agent_install.md)
- CLI reference: [docs/cli_reference.md](docs/cli_reference.md)
- Agent integrations: [docs/agent_integrations.md](docs/agent_integrations.md)
- Memory automation: [docs/automation.md](docs/automation.md)
- Memory governance: [docs/memory_governance.md](docs/memory_governance.md)
- Supabase setup: [docs/supabase_setup.md](docs/supabase_setup.md)
- MCP tool reference: [docs/mcp_tool_reference.md](docs/mcp_tool_reference.md)
- MCP workflow: [docs/mcp_memory_workflow.md](docs/mcp_memory_workflow.md)
- PageIndex / Headroom comparison: [docs/comparisons/pageindex_headroom.md](docs/comparisons/pageindex_headroom.md)
- Vision notes: [docs/vision.md](docs/vision.md)

## Development

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
pytest -q
```

## License

Apache-2.0. See [LICENSE](LICENSE).
