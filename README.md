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
Install Vault-for-LLM for this project. Use vault-for-llm[mcp]==0.6.121.
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
pip install "vault-for-llm[mcp]==0.6.121"

vault setup-agent
```

`setup-agent` registers the Agent in the local registry at
`~/.vault-for-llm/agent-registry.json` and writes an `agent-install/` pack with:

- MCP startup instructions
- update-status and rollout doctor templates
- Codex, Claude Code, OpenClaw, and Hermes Agent startup templates
- a runtime update playbook for multi-runtime machines
- a hybrid shared/private vault layout manifest

Check whether that generated startup pack is current:

```bash
vault agent startup-doctor --template-dir ./agent-install
```

Each runtime can read its own focused startup view:

```bash
vault update-status --read-status --agent codex
```

If you want Vault to safely paste one generated runtime template into a target
file, preview first and then apply:

```bash
vault agent install-runtime-template --runtime codex --target ./AGENTS.md
vault agent install-runtime-template --runtime codex --target ./AGENTS.md --apply
```

The apply command is dry-run by default and creates a backup before changing an
existing file. Full install details live in [`docs/agent_install.md`](docs/agent_install.md).

For non-interactive agent installs:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --memory-layout hybrid \
  --features core,mcp,supabase,headroom \
  --write-stable-venv-script \
  --supabase-setup simple \
  --remote-reader shell \
  --automation-schedule cron \
  --automation-write-workspace \
  --automation-include-transcripts \
  --automation-auto-promote-low-risk \
  --json
```

This can generate `agent-install/setup-stable-venv.sh`, so scheduled jobs and
MCP commands do not depend on a disposable `/tmp` virtualenv.

### Manual Quickstart

```bash
pip install "vault-for-llm[mcp]==0.6.121"

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

Agents can also turn a completed session transcript into reviewable candidates:

```bash
vault capture discover --project-dir ~/Vaults/my-project --pretty
vault capture session codex-session.jsonl --project-dir ~/Vaults/my-project --pretty
vault capture session codex-session.jsonl --project-dir ~/Vaults/my-project --write-candidates
```

Discovery lists likely transcript files without reading their contents. Session
capture previews by default. `--write-candidates` writes candidate memories
only; it does not promote active knowledge.

For MCP-capable runtimes:

```bash
vault-mcp --project-dir ~/Vaults/my-project --tool-profile core
```

Recommended core tools:

- `vault_search`
- `vault_read_range`
- `vault_memory_propose`
- `vault_stats`
- `vault_update_status`
- `vault_automation_handoff`

Reviewer or maintenance agents can use `vault_capture_discover` and
`vault_capture_session` from the MCP `review` profile to run the same
session-capture flow. Capture previews by default; `write_candidates=true` is
required before anything enters the candidate queue.

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

MCP writes use the same governance boundary. Low-sensitivity `project` writes
remain compatible, but `shared`/`public`, `private`, `high`, and `restricted`
writes require a calling `agent_id` plus the matching explicit capability flag
such as `allow_shared`, `allow_private`, `allow_high_sensitivity`, or
`allow_restricted`. This keeps a shared vault from becoming a free-for-all when
several runtimes connect to the same memory.

Searches record lightweight usage counters (`access_count`, `citation_count`,
`last_accessed_at`). The default lightweight reranker uses these signals as a
small, saturated boost, so frequently useful memories can rise slightly without
overriding source relevance, trust, freshness, or access policy.
`vault automation brief` also turns usage into an explainable
`importance_score` with visible components for access, citation, recency, trust,
freshness, TTL pressure, and protection hints. The score is for ranking and
review guidance only; it never bypasses governance or promotes memory by itself.

Short-lived memories with `expires_at` can be moved to `status: archived`
instead of deleted:

```bash
vault usage stats
vault usage archive-expired --apply
vault usage cold-store-expired --apply
```

`archive-expired` is for expired memories with no protected usage signal.
`cold-store-expired` is for expired memories that are still retrieved or cited:
it writes a compact summary, moves the row out of normal recall with
`status: archived`, keeps the original content for audit/restore, and skips
private, high/restricted, and L0/L1 memory.
Policy automation can run the same cold-store path during `vault automation run`
or `vault automation cycle` when `cold_store_used_expired` and `--apply` are
enabled.
Cold-store previews and automation ledgers use the same `importance_score` to
sort expired-but-used memories, so review starts with the memories most likely
to deserve refresh, summary, or protected cold storage.
`vault automation inbox` and `vault automation brief` turn those report-level
signals into a compact review digest, so the human review surface stays short:
review protected TTL decisions, expired-but-used memory, cold-store summaries,
and promotion previews before opening raw candidate content.
`vault automation review-summary` is even smaller: it turns the brief, inbox,
and latest report into a few approval cards for the 5% of memory decisions a
person should actually inspect.
`vault automation review-feedback` closes that tiny loop: record whether a card
was accepted, rejected, or deferred, then let `automation eval` turn those
outcomes into bounded ranking hints for future review cards.
`vault automation learning-health` gives that loop a dashboard-safe status:
whether learning is still cold, healthy, worth watching, or needs review.
When `vault automation eval --write-learning-policy` has enough reviewed
feedback, inbox/brief also use that bounded learning policy to sort review
items. The multiplier is visible and capped; it is not an authorization policy.

Design notes: [docs/memory_governance.md](docs/memory_governance.md).

Policy-based automation lets agents handle routine maintenance while humans
keep ownership of the rules:

```bash
vault automation plan --write-policy
vault automation run
vault automation run --apply
vault automation cycle --apply
vault automation cycle --apply --include-transcripts --capture-transcripts --write-workspace
vault automation inbox --limit 5
vault automation inbox --include-transcripts --write-handoff
```

`vault capture discover` and `vault capture session` are the ingestion side of
that loop. Discovery finds likely transcript files without reading their
contents. Capture scans the chosen transcript for reusable decisions, pitfalls,
workflows, and source-of-truth signals, then routes them through the normal
candidate gates. Automation and Dream can later rank and clean those
candidates, but promotion remains explicit. MCP review agents can call
`vault_capture_discover` and `vault_capture_session` for the same preview-first
flow without adding those heavier tools to the everyday `core` profile.
`vault automation inbox --include-transcripts` can include the same
metadata-only discovery hints in `reports/automation/inbox-latest.json`, so the
next scheduled agent can see uncaptured transcript exports without reading
their contents first.
When you explicitly add `--capture-transcripts --apply`, the cycle can turn
those discovered transcript files into gated review candidates. It still does
not promote active memory, and the generated handoffs omit raw transcript and
candidate content.

Balanced automation can pre-fill the memory candidate queue with Dream and
Forgetting suggestions when `--apply` is used, but it still does not promote
candidates by default or hard-delete memory. Use `conservative` mode when
scheduled jobs should only write reports.

If you want the first real closed loop from candidate to formal memory, enable
it deliberately during agent install:

```bash
vault setup-agent \
  --automation-schedule cron \
  --automation-apply \
  --automation-auto-promote-low-risk
```

That installer option writes `automation_policy.yaml` for you. The policy is
equivalent to:

```yaml
auto_promote_low_risk_candidates: true
auto_promote_allowed_sources: [session_capture]
auto_promote_allowed_memory_types: [session_lesson]
auto_promote_allowed_sensitivities: [low]
auto_promote_min_trust: 0.65
auto_promote_max_per_run: 3
auto_promote_requires_source_ref: true
```

With that policy, `vault automation cycle --apply` can promote only low-risk
session lessons that pass privacy, duplicate, metadata, and quality gates and
include a source reference. Without `--apply`, Vault only previews what would be
promoted. Private, high-sensitivity, duplicate, weak, or sourceless candidates
stay in the review queue.

`vault automation eval` reads promoted/rejected/blocked candidate outcomes and
shows which suggestion sources are earning trust over time. The signal guides
future curation priority; it does not override review, privacy, or access
policy.

Rejected and blocked candidates can be recorded directly:

```bash
vault candidate-review mem_123 --outcome rejected --reason "Too vague to keep."
```

This is useful for agents because "do not keep this" becomes structured
feedback instead of disappearing into chat history.

For scheduled agents, `vault automation eval --write-learning-policy` also
writes `reports/automation/learning_policy.json`. That file contains bounded
priority hints, such as preferring a suggestion source that is often promoted
or downgrading one that is often rejected. The bounds are deliberately small
and never authorize auto-promotion, deletion, or privacy bypass.

Dream and scheduled automation can read that policy on the next run. They use
it to annotate and sort candidate suggestions, so reviewers see better-ranked
cleanup work first while the formal promote/reject decision remains explicit.
When Dream finds duplicate groups, it can also write a
`consolidation_suggestion` candidate that asks for a reviewed merge/archive
decision without changing active knowledge by itself.
`vault automation cycle` runs that feedback-to-curation loop in one command:
evaluate reviewed outcomes, write the bounded learning policy, then run safe
automation so Dream can consume the latest hints.
Add `--write-workspace` to write `reports/automation/cycle-latest.json`, a
compact next-agent workbench with candidate review, optional transcript paths,
and the latest curation-policy summary. It also writes
`reports/automation/cycle-latest.md`, a readable handoff with the same safe
summary, priority brief, suggested next tasks, an agent start prompt, and no
raw candidate or transcript content.
The next agent can read the latest compact handoff with:

```bash
vault automation handoff
```

MCP-capable agents can read the same compact handoff with
`vault_automation_handoff` in the `core` profile.

When `reports/automation/fleet-health-latest.md` or `.json` exists, the handoff
also includes that shared multi-Agent health panel. The CLI prints fleet health
first, then the selected cycle/inbox handoff; MCP keeps the main handoff in
`content` and exposes the shared panel through `fleet_health_content`.

`vault automation inbox` is the short review surface for that loop. It does not
mutate memory. It ranks privacy-blocked, sensitive, duplicate, weak-quality, and
automation-generated candidates, hides raw content by default, and shows only the
smallest useful queue for a human or trusted agent to review.
Scheduled automation templates write the same view to
`reports/automation/inbox-latest.json` after each successful run.
`vault automation activity` is the shortest audit surface for the same loop: it
shows recent auto-promote previews, promotions, and skipped reasons without raw
candidate content. MCP-capable agents can call `vault_automation_activity` from
the `core` profile.

`vault automation brief` is the shortest daily intelligence view. It combines
learning hints from promote/reject feedback, explainable memory importance,
forgetting pressure, shared agent health, and the 5% human-review queue. Use it
before opening full reports:

```bash
vault automation brief --pretty
vault automation review-summary --write-summary
vault automation review-feedback --kind memory_importance --card-id 12 \
  --decision accept --reason "Correctly protected an expired but cited memory" \
  --write-learning-policy
vault automation learning-health --write-health
vault automation fleet-health --write-health
```

MCP-capable agents can call `vault_automation_brief` from the `core` profile.
For multi-Agent installs, `vault automation fleet-health` combines local Agent
registry metadata, learning-health status, and update-distribution health into
`reports/automation/fleet-health-latest.json` plus `.md`. It is read-only and
does not read private memory, raw candidate content, or raw feedback reasons.
`vault automation handoff` automatically surfaces this panel before the
individual cycle/inbox handoff when the file exists.

Agent installers can generate cron, LaunchAgent, or n8n templates with
`vault setup-agent --automation-schedule cron|launchagent|n8n|all`. Scheduled
templates default to `vault automation cycle`, so long-running agents can learn
from reviewed outcomes before the next maintenance pass. The schedule is still
report-first unless the user explicitly opts into `--automation-apply`; pass
`--automation-command run` for a simpler maintenance-only schedule.
Generated schedules also write `reports/automation/learning-health-latest.json`
and `.md` after each run, giving humans and all connected agents the same short
view of whether the learning loop is healthy, watching repeated rejects, or
still in cold start.
Add `--automation-write-workspace` when generated schedules should write
`reports/automation/cycle-latest.json` and `reports/automation/cycle-latest.md`
after the cycle, so the next agent starts from the daily memory workbench
instead of full reports.
Generated schedule README files include `vault automation handoff --project-dir ...`
as the read-only startup command for the next agent.
Add `--automation-include-transcripts` only when the scheduled handoff should
also list uncaptured transcript exports. That list is metadata-only and keeps
transcript contents out of the generated handoff.
Add `--automation-auto-promote-low-risk` only when the user wants setup-agent to
write the low-risk auto-promote policy. Pair it with `--automation-apply` when
the scheduled cycle should actually promote eligible candidates; without
`--apply`, scheduled jobs preview only.

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
Remote readers should pass the search result `id` directly into map/read; it
may be an integer or a Supabase UUID.

```bash
pip install "vault-for-llm[supabase]==0.6.121"
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
