# Decision Record: Task Ledger Is a Working Set, Not a Memory Layer

Date: 2026-06-29

## Context

Vault-for-LLM uses `L0` through `L3` to describe long-lived memory depth:
identity, stable facts, recent context, and deep project knowledge. As agents
take on longer tasks, a different problem appears: the agent needs to know what
the current task is doing right now without rereading the whole conversation,
reconstructing the plan from search results, or turning every temporary step
into long-term memory.

Long-running tasks also cross physical model sessions. A new session or a
different agent should be able to continue the same logical task from a small,
auditable working set rather than from compressed chat history.

## Decision

Add a separate Task Ledger / Working Set concept. Do not add `L4`, and do not
store task ledgers as ordinary `L2` knowledge by default.

`L0` through `L3` remain memory depth layers:

- `L0`: identity and minimal framing
- `L1`: stable facts, contracts, preferences, and rules
- `L2`: reviewed recent context and short-term background
- `L3`: detailed searchable project knowledge, SOPs, decisions, and lessons

Task Ledger is a task-runtime state layer:

- current goal
- current plan
- completed work
- hard decisions
- blockers
- open questions
- next actions
- evidence references
- continuation note

## Product Principle

Vault is the governed long-term memory. Task Ledger is the current workbench.

The workbench may contain temporary steps, failed attempts, partial plans, and
handoff notes. Those entries should not become active long-term knowledge just
because they helped one task continue.

When a task phase ends, Vault should extract only reusable lessons into memory
candidates. Promotion to `L0` through `L3` still goes through the normal gates.

## Why This Is Not L2

`L2` is reviewed recent background that can help future tasks. A Task Ledger is
the active state of one task. It can be updated frequently and may include
temporary details that are useful only while that task is open.

Use this rule of thumb:

| Question | Recommended destination |
|---|---|
| Does the next task also need this context? | `L2` or `L3` candidate |
| Is it only needed to resume the current task? | Task Ledger |
| Is it a stable user or project rule? | `L1` candidate |
| Is it a technical decision, SOP, fix, or reusable lesson? | `L3` candidate |
| Is it a failed attempt or temporary implementation note? | Task event/history, not active knowledge |

## Expected Flow

```text
Task starts
  -> Task Ledger stores goal, plan, and evidence refs
  -> Agents update task events while working
  -> Handoff/resume reads the working set first
  -> Task phase ends
  -> Reusable lessons are proposed as Vault candidates
  -> Gates decide whether they enter L0-L3
```

## Agent-Facing Behavior

Agents should start task continuation from the Task Ledger, then use Vault
search and bounded reads only when they need durable knowledge or source
evidence.

Default continuation context should stay small:

```yaml
task_id: example-task
goal: Finish the current implementation safely.
status: active
current_plan:
  - Inspect failing tests.
  - Patch the narrow cause.
  - Re-run targeted tests.
hard_decisions:
  - Do not promote raw transcripts into active memory.
blockers: []
next_actions:
  - Run the focused test file.
evidence_refs:
  - file: tests/test_example.py
continuation_note: Start from the focused failure, not from a broad repo scan.
```

This is intentionally smaller than a conversation transcript or full Vault
memory dump.

## Privacy And Safety Boundaries

- Task Ledger can reference private or sensitive evidence, but it should not
  copy raw secrets or private conversation content into shared task state.
- Task Ledger entries should carry the same governance metadata style as Vault
  memory where needed: `scope`, `sensitivity`, `owner_agent`, and
  `allowed_agents`.
- Shared task ledgers should default to low-sensitivity project work state.
- Private agent working notes can exist, but they should not be synced into
  shared task state unless summarized and reviewed.
- A task completion step may propose memory candidates, but it should not
  auto-promote raw task events into active memory.

## Implementation Shape

The minimum implementation should avoid changing the meaning of `knowledge.layer`.

Suggested tables or file-backed equivalents:

- `task_ledger`: task identity, goal, status, current working set,
  continuation note, owner/scope metadata
- `task_events`: append-only task updates such as decisions, blockers,
  completed steps, and handoff notes
- `task_evidence_refs`: references to files, knowledge ids, document-map nodes,
  reports, issues, PRs, or external artifacts

Suggested CLI:

```bash
vault task start "Repair memory benchmark"
vault task update <task_id> --decision "Do not promote raw transcripts"
vault task handoff <task_id>
vault task resume <task_id>
vault task complete <task_id>
```

Implemented MCP tools:

- `vault_task_start`
- `vault_task_status`
- `vault_task_update`
- `vault_task_handoff`
- `vault_task_complete`

Task tools belong to review/maintenance/full profiles, not the core profile.
They are useful for long-running agent work, but they are not needed for every
startup and should not increase the default MCP schema surface.

## Relationship To GUI

The GUI should eventually show Task Ledger separately from memory documents:

- active task card
- plan / done / blockers / next actions
- evidence refs
- continuation note
- extracted memory candidates, if any

Do not place task events inside the normal document list unless they have been
converted into reviewed Vault candidates.

## Deferred Questions

- Should task ledgers live inside `vault.db` by default, or start as a
  file-backed `.vault/tasks/` ledger for easier inspection?
- Should task ids be user-readable slugs, UUIDs, or both?
- How long should completed task ledgers remain in the active task index?
- Which task fields should be synced to Supabase for cross-device handoff?
- Should a task completion command automatically create draft memory
  candidates, or require an explicit `vault task extract-candidates` command?
