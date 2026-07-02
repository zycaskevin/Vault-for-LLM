# Vision: User-Owned Memory for Agent Families

Vault-for-LLM is the memory core.

Hermes Agent, OpenClaw, Claude Code, Codex, n8n, robots, car assistants, smart
home agents, and future embodied systems are the hands.

Models are the compute tools.

The long-term goal is not to build one more chatbot memory plugin. The goal is
to let a user own a lifelong memory layer that different agents and devices can
use without forcing that user to surrender privacy, review, portability, or the
right to forget.

## The Future We Are Building For

Each person may eventually have an agent family:

- work agents that code, write, plan, and operate tools
- companion agents that understand communication style and care context
- home agents that know household rules and daily preferences
- car agents that continue a conversation while moving between places
- robots and embodied agents that act in the physical world
- cloud or workflow agents that operate services such as n8n, Coze, or internal APIs

Those agents can have different personalities, capabilities, and permissions.
They should not all see the same memory. But they should be able to share the
same reviewed continuity when the user allows it.

The question is not whether long-term agent memory will exist. It is who owns
it.

Vault-for-LLM takes the position that the memory should belong to the user.

## Brain, Hands, Compute

```text
Vault-for-LLM       = brain / memory core
Agent runtimes      = hands / action layers
Models              = compute tools
Obsidian + graph    = human-readable memory garden and review surface
Supabase or sync    = optional cross-host bridge, not the owner
```

In this model, an agent runtime can be replaced without erasing the user's
memory. A model can be swapped without losing project history, profile
preferences, source records, or long-term context. A cloud sync layer can help
devices share memory, but it should not become the user's only source of truth.

## Core Principles

- **User-owned**: the user controls where memory lives and who may read it.
- **Local-first**: local SQLite remains the default source of truth.
- **Agent-neutral**: Hermes, OpenClaw, Claude Code, Codex, n8n, and future agents
  should connect through shared CLI/MCP contracts instead of proprietary memory
  silos.
- **Reviewable**: important memories pass through candidate review before
  becoming active shared knowledge.
- **Permissioned**: agents receive views of memory based on scope, sensitivity,
  owner, allowed agents, device, and context.
- **Forgettable**: forgetting should be a governed lifecycle, not accidental
  deletion and not permanent platform memory.
- **Portable**: Markdown, Obsidian, SQLite, backup/restore, and sync exports keep
  memory inspectable and movable.
- **Composable**: memory should grow into skills, procedures, graph links,
  summaries, and new ideas over time.
- **Progressively disclosed**: agents should see the smallest useful memory view
  first, then open deeper context only when the task, permission, and evidence
  require it.

## Progressive Memory Disclosure

Vault-for-LLM should behave like a guided memory vault, not an open warehouse.
An agent should not receive the user's full memory just because it can connect
to a database.

The retrieval path should unfold in layers:

```text
boot memory
  -> active context summary
  -> topic / graph map
  -> search candidates
  -> bounded evidence ranges
  -> raw source or archive only when justified
```

This mirrors progressive disclosure in skill systems: read the small operating
contract first, then open references, scripts, or raw sources only when the work
requires them.

The goal is to keep context small, reduce leakage, and make memory feel more
human: first a clue, then a related topic, then a specific source, then the
original memory if the user or task truly needs it.

Compression systems such as Headroom can help after Vault has already narrowed
the context. They should not replace permission filtering, retrieval, bounded
reads, or source-grounded citations.

## Memory Lifecycle

```text
capture
  -> candidate
  -> review
  -> active memory
  -> retrieval / bounded read
  -> dream report
  -> consolidate
  -> archive / expire / cold storage
  -> recall when needed
```

The purpose is not to remember everything forever. The purpose is to keep memory
useful:

- repeated events can become one stable pattern
- stale context can be downgraded
- low-value notes can move out of daily recall
- private raw interactions can stay private
- source-grounded knowledge can remain traceable
- old memories can be recovered when the user asks

## Agent Family Memory

Different agents should use different memory views:

| Agent type | Typical memory view |
|---|---|
| Work/coding agent | project decisions, SOPs, fixes, repo context, user work preferences |
| Companion agent | private relationship context, care summaries, communication boundaries |
| Product/strategy agent | goals, roadmap, decisions, market notes, user values |
| Home agent | household rules, device preferences, routine context |
| Car agent | active threads, schedule, destination context, low-sensitivity preferences |
| Robot/embodied agent | place context, action permissions, physical-world constraints |
| Cloud workflow agent | only the reviewed data needed for its task |

The memory core should support shared continuity without flattening every agent
into the same identity. Personality, facts, user profile, permissions, and
source records should remain separable.

## Dedicated Memory Agents

A mature Vault may include specialized memory-maintenance agents:

- **Profile agent**: maintains stable user profile, preferences, collaboration
  style, care summaries, and agent-specific boundaries.
- **Dream agent**: periodically reviews memory clusters, finds stale or repeated
  entries, discovers new themes, and produces report-first suggestions.
- **Forgetting agent**: proposes expiry, archive, downgrade, or merge actions so
  memory stays efficient without becoming unrecoverable.
- **Graph agent**: finds useful links between project knowledge, user patterns,
  Obsidian notes, and emerging ideas.

These agents should default to report-only or candidate-only behavior. They
should not silently publish private profile memory, delete active memory, or
promote shared knowledge without user-approved policy.

## Obsidian and Graph as the Human Review Layer

Vault should be useful to agents, but memory must remain visible to humans.

Obsidian can act as:

- a memory garden
- a review surface
- a graph view
- a place to edit or correct summaries
- a way to see what agents think they know

Vault's built-in GUI should stay focused on the memory control plane:

- connected agents and their permissions
- sync health for Obsidian, Supabase, and Gateway
- conflicts and daily review queues
- automation health and safe actions
- security settings such as local GUI auth and agent identity checks

Vault provides:

- structured compile/import/export
- search and bounded reads
- metadata and trust layers
- candidate memory review
- graph/document-map records
- backup/restore and sync paths

Together, they let memory become interactive instead of hidden.

The practical split is simple: Obsidian is where humans write, link, and browse
knowledge; Vault is where agents retrieve, govern, audit, and share memory.
Obsidian folders can map to `scope` and `sensitivity`, and Obsidian wikilinks
can become Vault graph edges. Generated Vault notes should live in a clearly
generated folder such as `00-Vault-Knowledge/` so agent output does not silently
overwrite user-authored notes.

## Sync Without Surrender

Cross-device memory will need sync. Supabase or another remote layer can help a
car, robot, phone, home agent, cloud workflow, and work agent share reviewed
state.

But sync is a bridge, not the owner.

The local vault should remain usable without cloud infrastructure. Remote
systems should receive only the view they need:

- shared project knowledge
- reviewed profile summaries
- low-sensitivity active threads
- device-appropriate context
- never raw private memory by default

## What We Will Not Build

- A black-box memory system the user cannot inspect.
- A platform-owned memory silo that breaks when the user changes agents.
- Silent writes of private interaction history into shared memory.
- Silent deletion disguised as forgetting.
- One giant memory bucket where every agent sees everything.
- A system that treats cloud sync as required for basic use.

## Roadmap Direction

Near-term work should make the existing pieces more coherent:

1. Keep L0-L3 stable as memory depth layers.
2. Add governance metadata such as `scope`, `sensitivity`, `owner_agent`,
   `allowed_agents`, `status`, `memory_type`, and `expires_at`.
3. Make setup-agent ask about profile memory privacy and optional memory agents.
4. Improve dream reports so they propose merge, archive, expiry, and graph-link
   actions instead of only reporting stale or duplicate entries.
5. Let Obsidian carry governance frontmatter and review notes.
6. Use Supabase/RLS only as an optional cross-host bridge for reviewed memory.
7. Keep MCP tool profiles small so daily agents use memory without carrying too
   many tools.

The north star:

> Vault-for-LLM is a user-owned lifelong memory layer for agent families. It is
> the brain that keeps continuity; agents are the hands that act; models are the
> compute tools that reason over reviewed memory.

The product strategy for turning this vision into an open-source core,
self-host team layer, optional cloud, and enterprise governance platform lives
in [docs/strategy/](strategy/). Use those documents before making large
roadmap, pricing, cloud, or enterprise-scope decisions.

If this approach works, Vault-for-LLM can become a practical reference design
for future user-owned memory vaults: databases that do not merely store facts,
but help users review, connect, compress, forget, recover, and carry their
continuity across tools and embodied systems.
