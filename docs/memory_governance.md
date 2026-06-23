# Memory Governance Layers

Vault-for-LLM uses `L0` through `L3` as memory depth and usage layers. Do not
use those layers as access-control rules by themselves.

The recommended model is:

| Layer | Meaning | Typical sharing |
|---|---|---|
| `L0` | Minimal identity for the user, agent, project, or workspace. | Private by default. Share only small reviewed summaries. |
| `L1` | Stable core facts, contracts, preferences, and working rules. | Share with trusted work agents after review. |
| `L2` | Recent context, current decisions, incidents, handoff notes, and short-term state. | Share reviewed summaries, usually with freshness or expiry metadata. |
| `L3` | Deep searchable knowledge, SOPs, architecture notes, fixes, and lessons. | Best default layer for low-sensitivity shared project knowledge. |

Use side metadata to decide who may read, write, sync, or export a memory:

```yaml
layer: L2
scope: shared
sensitivity: medium
owner_agent: profile-agent
allowed_agents: ["profile-agent", "work-agent", "product-agent"]
status: reviewed
memory_type: care_summary
expires_at: 2026-07-01
```

## Progressive Memory Disclosure

Memory should be revealed in layers. A daily agent should start from the
smallest safe context, then request deeper evidence only when needed:

```text
L0 boot summary
  -> active context
  -> topic map
  -> search candidates
  -> bounded read
  -> raw source / archive
```

Each step should respect `scope`, `sensitivity`, `owner_agent`,
`allowed_agents`, and task context. Compression can reduce selected context
after retrieval, but it should not replace permission checks or source reads.

## Read-Side Filters

Local SQLite remains inspectable by the operator, but agent-facing reads can
apply a governance policy:

```bash
vault search "deployment notes" --agent-id work-agent --max-sensitivity medium
```

MCP tools accept the same policy fields:

```json
{
  "query": "deployment notes",
  "agent_id": "work-agent",
  "include_private": false,
  "max_sensitivity": "medium"
}
```

Without an explicit policy, legacy local reads remain unchanged. With a policy:

- `private` memory requires `include_private=true` and the agent must be the
  `owner_agent` or listed in `allowed_agents`.
- `restricted` memory requires the agent to be the `owner_agent` or listed in
  `allowed_agents`.
- `max_sensitivity` is a hard cap; for example `medium` excludes `high` and
  `restricted` entries.

## User Profile Guidance

Do not put a whole user personality profile into `L0`. `L0` is loaded often, so
it should stay small and safe.

Split user profile memory like this:

| Profile content | Recommended layer | Recommended metadata |
|---|---|---|
| Minimal identity, roles, and long-term mission. | `L0` | `scope: private`, or a reviewed shared summary. |
| Stable working preferences, language, collaboration style, and durable boundaries. | `L1` | `scope: project` or `shared`, `sensitivity: medium`. |
| Recent emotional/workload state and current care instructions. | `L2` | `scope: shared`, `sensitivity: medium`, `expires_at` required. |
| Deep personality analysis, psychological inference, raw private interaction history. | `L3` or a separate private table/vault. | `scope: private`, `sensitivity: high`, narrow `allowed_agents`. |

For example, a companion agent may keep private raw conversations locally, then
publish only a reviewed weekly summary:

```yaml
---
layer: L2
memory_type: care_summary
scope: shared
sensitivity: medium
owner_agent: care-agent
allowed_agents: ["profile-agent", "work-agent", "product-agent"]
status: reviewed
expires_at: 2026-07-01
---

the user seems under heavier workload this week. Prefer concise reassurance before
task pressure, and avoid repeated follow-up questions unless the task is urgent.
```

The raw conversation that produced this summary should remain private.

## Dedicated Memory Agents

Advanced users can assign one or two agents to maintain memory quality:

| Agent role | Responsibility | Should not do |
|---|---|---|
| Profile agent | Maintains stable user profile, communication preferences, care summaries, and agent-specific boundaries. | Do not expose raw private chats or turn sensitive observations into shared active memory without review. |
| Dream / forgetting agent | Runs dream reports, marks stale entries, finds duplicates, proposes promotion/archive actions, and suggests expiry for low-value context. | Do not delete or promote shared memory without explicit policy or user approval. |

This keeps the vault useful as it grows. It also makes the data model more
portable for future embodied agents, long-running assistants, or world-model
workflows: user context, project state, source-grounded knowledge, and safe
forgetting can live in the same inspectable governance layer.

## Usage And Forgetting Signals

Vault records lightweight read-side signals on active memories:

- `access_count`: how often a memory appears in retrieval results.
- `citation_count`: reserved for workflows that explicitly mark a memory as
  cited or used as evidence.
- `last_accessed_at`: the most recent retrieval timestamp.

These counters are not a surveillance log. They are coarse maintenance signals
for ranking, dream reports, and archive review.

Short-lived memories should carry `expires_at`. Operators or maintenance agents
can preview and apply TTL archival:

```bash
vault usage stats
vault usage archive-expired
vault usage archive-expired --apply
```

Archival changes `status` to `archived`; it does not delete the row. This keeps
old memories reviewable while keeping normal retrieval focused on active memory.

## Multi-Agent Sharing

For Hermes Agent, OpenClaw, Codex, Claude Code, n8n, Coze, or other runtimes:

- Share the same project memory only when they use the same stable `vault.db` or
  the same reviewed Supabase sync view.
- Keep each agent's persona, private profile notes, and raw private
  conversations in that agent's private vault or local profile files.
- Let trusted work agents share `L1` and `L3` project knowledge after review.
- Let care or companion agents publish short `L2` summaries instead of raw
  private chats.
- Treat `status: candidate` as not active memory; use `vault candidates` to
  review the queue, then promote before shared use.

Recommended product setup:

```bash
vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase,memory_agents \
  --supabase-setup advanced \
  --supabase-sync cron \
  --remote-reader all \
  --agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation \
  --validation-pack all \
  --json
```

This keeps local SQLite as the source of truth, creates Supabase guidance for a
reviewed remote read layer, generates shell/n8n/Coze reader templates, writes a
multi-agent access matrix, and includes live validation checklists without
exposing raw private conversations.

## Supabase and RLS

Supabase RLS can enforce shared-memory boundaries, but RLS should use columns
such as `scope`, `sensitivity`, `owner_agent`, `allowed_agents`, and `status`.
Do not overload `layer` as a permission level.

Keep `SUPABASE_SERVICE_ROLE_KEY` on trusted sync machines only. Normal agents,
Coze, n8n, or browser clients should use read-only APIs, Edge Functions, RPCs,
or RLS-backed JWTs.

## Obsidian Sync

Obsidian import/export can carry governance metadata in frontmatter. Adding
metadata fields is backward-compatible:

```yaml
---
layer: L3
scope: shared
sensitivity: low
owner_agent: work-agent
status: active
memory_type: procedure
---
```

Changing or renaming `L0` through `L3` is not recommended. It would require
updates to compiler inference, CLI/MCP schemas, graph styling, Obsidian
round-trips, Supabase mapping, tests, and documentation.

## Graph Impact

The graph should keep using `L0` through `L3` for structural depth. It can add
badges, filters, or colors for `scope`, `sensitivity`, and `owner_agent` without
changing the layer model.
