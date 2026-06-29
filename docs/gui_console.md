# Vault Console

`vault gui` starts a local, read-only browser console for one project vault.

It is the first GUI slice for Vault-for-LLM. It does not replace CLI/MCP. Use it
to inspect the memory loop and handle explicit candidate review decisions.

## Start

```bash
vault gui --project-dir ~/Vaults/my-project
```

The server binds to `127.0.0.1:8765` by default and opens the browser.

For headless validation or remote shells:

```bash
vault gui --project-dir ~/Vaults/my-project --no-open --port 8765
```

## Layout

| Area | Purpose |
|---|---|
| Left | Project status, active Task Ledger items, candidate review queue, filterable document list |
| Center | Search results, task handoff, candidate review, and bounded evidence reader |
| Right | Task details, or Document Map, graph, timeline, governance, and usage metadata for the selected memory |

The document list is the first Obsidian-like navigation slice: it lets a user
filter active memory by text, layer, category, and sensitivity before opening a
bounded read in the center pane.

The Task Ledger panel shows the current working set separately from L0-L3
memory. Selecting a task shows plan, completed work, decisions, blockers, next
actions, evidence refs, recent task events, and compact handoff Markdown. It is
read-only in the GUI; use CLI/MCP to update task state.

The Map tab is the first structured-reading slice. It shows Document Map
sections and visible claims for the selected memory. Clicking a section opens
that exact line range in the bounded evidence reader instead of loading the
whole note.

The Graph tab shows a compact local relationship map for the selected memory.
The center node is the current memory; linked nodes around it can be clicked to
open the related memory without leaving the console.

## API

The local server exposes read-only JSON endpoints:

| Endpoint | Purpose |
|---|---|
| `/api/overview` | Stats, automation brief, review inbox, recent memory |
| `/api/tasks?status=active` | Compact Task Ledger list |
| `/api/task/<id>` | One Task Ledger item with handoff Markdown |
| `/api/candidates` | Candidate queue without full content |
| `/api/candidate/<id>` | Candidate metadata, gate details, and content for review |
| `POST /api/candidate/<id>/review` | Promote, reject, or block with explicit confirmation |
| `/api/documents?q=...&layer=L3&category=...&sensitivity=low` | Filterable active-memory document list without raw content |
| `/api/search?q=...` | Local keyword search for memory entries |
| `/api/entry/<id>` | Metadata, Document Map rows, claims, graph summary |
| `/api/read?knowledge_id=1&line_start=1&line_end=40` | Bounded evidence range |

## Safety

- The default host is localhost only.
- Active memory edits, archive, and policy edits remain CLI/MCP operations.
- Task Ledger updates remain CLI/MCP operations; the GUI displays task state
  but does not mutate it.
- Candidate review actions are `POST`-only and require a confirmation token:
  `<candidate_id>:<action>`.
- Candidate promotion uses the existing `promote_candidate(confirm=True)` flow
  and reruns gates before writing active knowledge.
- Candidate rejection/blocking uses the existing review workflow and records
  feedback for automation learning.
- Private or restricted data should not be exposed by binding the GUI to a
  public network interface.

## Product Direction

The GUI should make the automation loop easier to trust:

- show the smallest human review surface first
- keep bounded evidence more prominent than raw full-document dumps
- let the right-side Map tab guide bounded reads before richer graph views
- keep graph visualization compact and local before adding heavier canvas or
  WebGL views
- make temporal and governance metadata visible beside each memory
- keep future write-capable flows explicit, audited, and rollback-friendly
