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

## Task Ledger Versus L2

Do not treat Task Ledger as `L2`, and do not create an `L4` layer for task
state. `L0` through `L3` describe long-lived memory depth. Task Ledger describes
the active working set for one task.

`L2` is reviewed recent background that may help future tasks. Task Ledger is
the current state of one task: current goal, plan, completed work, hard
decisions, blockers, open questions, next actions, evidence references, and a
continuation note.

Use this distinction:

| Content | Destination |
|---|---|
| "This project is moving toward multi-agent memory governance." | `L2` candidate |
| "The active PR already merged the graph panel; next action is Task Ledger design." | Task Ledger |
| "Future architecture discussions must become decision records." | `L1` or `L3` candidate |
| "A failed implementation attempt during this task." | Task event/history, not active knowledge |

Task Ledger can reference Vault memories, files, reports, issues, PRs, or
Document Map nodes. It should not copy raw private content into shared task
state. When a task phase ends, extract only reusable lessons into Vault
candidates; promotion into `L0` through `L3` still requires the normal gates.

Directed handoffs are part of Task Ledger, not a new memory layer. They let one
agent address a compact task snapshot to another agent and let the receiver
claim it. The handoff packet should contain task state, a sender note, and
shared evidence references. It must not copy another agent's private identity,
style notes, or raw private conversation memory into the shared task inbox.

Recommended task-runtime shape:

```yaml
task_id: example-task
goal: Finish the current implementation safely.
status: active
current_plan:
  - Inspect the focused failure.
  - Patch the narrow cause.
  - Re-run targeted tests.
hard_decisions:
  - Do not promote raw transcripts into active memory.
blockers: []
next_actions:
  - Run the focused test file.
evidence_refs:
  - file: tests/test_example.py
continuation_note: Resume from the focused failure, not from a broad repo scan.
```

See
`docs/decision_records/2026-06-29-task-ledger-working-set-boundary.md` for the
full decision record.

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

## Multi-Host Candidate Sync

For multiple machines, treat remote writes as suggestions first. A hosted or
remote agent should submit a candidate request, not overwrite reviewed active
knowledge:

```bash
vault remote submit-candidate --from-agent remote-agent --title "..." --content "..."
```

A trusted local sync host then pulls those requests into the normal candidate
queue:

```bash
vault remote pull-candidates --apply
vault sync conflicts
vault sync audit
```

This keeps the same safety boundary as local agent work:

- remote agents can contribute reusable lessons;
- local gates still scan privacy, duplication, metadata, and quality;
- low-risk auto-merge is policy-gated and optional;
- conflicts are visible before they become active memory;
- audit events show what arrived, what was promoted, and who marked a conflict
  resolved.

Do not use Supabase service-role keys in hosted agents, mobile clients, browser
clients, or public workflow endpoints. Those clients should use the guarded RPC
for candidate submission or read-only memory access.

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

These counters are not a surveillance log and they are not access-control
rules. They are coarse maintenance signals for ranking, dream reports, and
archive review. The lightweight reranker applies them as a small saturated
boost, so a repeatedly useful memory may move up when relevance is otherwise
similar, but it should not beat a better source just because it is popular.

Short-lived memories should carry `expires_at`. Operators or maintenance agents
can preview and apply TTL archival:

```bash
vault usage stats
vault usage archive-expired
vault usage archive-expired --apply
```

Archival changes `status` to `archived`; it does not delete the row. This keeps
old memories reviewable while keeping normal retrieval focused on active memory.

Temporal fact windows are a separate idea from TTL. Use `valid_from`,
`valid_until`, and `supersedes_id` when a fact changes over time:

```yaml
valid_from: 2026-06-25
valid_until:
supersedes_id: 42
```

In this model, `valid_until` means "this fact is no longer current." It should
stay searchable as history and evidence. `expires_at` means "this memory can
leave daily recall after this date." Agents should use `vault memory temporal
status` and `vault memory temporal list --state past` when they need to explain
what changed, not only what is true now.

Search results mark temporal rows with `temporal_state`. Default search keeps
past and future facts visible for audit, but agents that need only currently
valid facts should pass `--exclude-expired` or MCP
`include_expired_temporal=false`.

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
