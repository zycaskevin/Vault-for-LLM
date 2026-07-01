# Vault Console

`vault gui` starts a local browser memory control center for one project vault.

It does not replace CLI/MCP. Agents should still operate the toolbox. Humans use
the GUI to see the daily memory report first, then inspect review cards,
bounded evidence, tasks, and document maps when needed.

## Start

```bash
vault gui --project-dir ~/Vaults/my-project
```

The server binds to `127.0.0.1:8765` by default and opens the browser.
It generates an ephemeral access token by default and opens the browser with
that token in the URL. Set `VAULT_GUI_TOKEN` to reuse a stable local token.
The top-right language selector supports Traditional Chinese, Simplified
Chinese, and English. The selected language is stored in the browser and is
also sent to the daily-report API.

For headless validation or remote shells:

```bash
vault gui --project-dir ~/Vaults/my-project --no-open --port 8765
```

For localhost-only test sessions, the token can be disabled explicitly:

```bash
vault gui --project-dir ~/Vaults/my-project --no-auth --no-open
```

`--no-auth` is rejected for non-localhost binds.

## Layout

| Area | Purpose |
|---|---|
| Left | Daily report, project status, multi-Agent sync health, active Task Ledger items, candidate review queue, filterable document list |
| Center | Memory Control Center by default, then search results, task handoff, candidate review, and bounded evidence reader |
| Right | Task details, or Document Map, graph, timeline, governance, and usage metadata for the selected memory |

The first screen is intentionally not a raw database browser. It starts with the
same read-only daily report as `vault daily-report`, shows only the decisions
that truly need human attention, and reminds the user that Vault will not
silently promote, archive, or delete memory.

Daily report cards are not decision buttons. Each card should explain what the
human is deciding and then open the detailed candidate/evidence view. The actual
actions stay separated there, such as keep, reject, or block.

For non-technical users, keep the GUI in their preferred language and let the
Agent handle CLI details. The human-facing surface should be the daily report,
review cards, and bounded evidence, not the full command set.

The document list is the first Obsidian-like navigation slice: it lets a user
filter active memory by text, layer, category, and sensitivity before opening a
bounded read in the center pane.

The Task Ledger panel shows the current working set separately from L0-L3
memory. Selecting a task shows plan, completed work, decisions, blockers, next
actions, evidence refs, recent task events, and compact handoff Markdown. It is
read-only in the GUI; use CLI/MCP to update task state.

The Multi-Agent Dashboard includes a read-only Sync Health card. It shows open
conflict count, revision count, and audit event count for remote candidate sync.
It does not show raw candidate content or private memory. Use CLI/MCP to resolve
conflicts after reviewing the relevant candidate and source evidence.

The Map tab is the first structured-reading slice. It shows Document Map
sections and visible claims for the selected memory. Clicking a section opens
that exact line range in the bounded evidence reader instead of loading the
whole note.

The Graph tab shows a compact local relationship map for the selected memory.
The center node is the current memory; linked nodes around it can be clicked to
open the related memory without leaving the console.

## API

Most local server endpoints are read-only. The only GUI write path is the
explicit candidate review endpoint, which is separated as a `POST` action:

| Endpoint | Purpose |
|---|---|
| `/api/overview` | Stats, automation brief, review inbox, recent memory |
| `/api/agent-dashboard` | Connected Agents, recent sync artifacts, review cards, and Sync Health |
| `/api/sync-status` | Read-only local revision/conflict/audit summary for multi-host candidate sync |
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
- The GUI requires a token by default. API calls can pass the token in the
  `token` query parameter, `X-Vault-Gui-Token` header, or the local
  `vault_gui_token` cookie set after opening the tokenized URL.
- Active memory edits, archive, and policy edits remain CLI/MCP operations.
- Task Ledger updates remain CLI/MCP operations; the GUI displays task state
  but does not mutate it.
- Candidate review actions are `POST`-only and require a confirmation token:
  `<candidate_id>:<action>`.
- Candidate promotion uses the existing `promote_candidate(confirm=True)` flow
  and reruns gates before writing active knowledge.
- Candidate rejection/blocking uses the existing review workflow and records
  feedback for automation learning.
- Sync conflict review is shown as a side-by-side local memory vs remote
  candidate decision. `keep_local`, `accept_remote`, and `manual` are separate
  buttons; accepting remote promotes the candidate and archives the old local
  row instead of silently overwriting it.
- Private or restricted data should not be exposed by binding the GUI to a
  public network interface. If a broader bind is needed, keep token auth enabled
  and put the GUI behind a trusted local tunnel or reverse proxy.

## Product Direction

The GUI should make the automation loop easier to trust:

- show the smallest human review surface first
- keep bounded evidence more prominent than raw full-document dumps
- let the right-side Map tab guide bounded reads before richer graph views
- keep graph visualization compact and local before adding heavier canvas or
  WebGL views
- make temporal and governance metadata visible beside each memory
- keep future write-capable flows explicit, audited, and rollback-friendly
