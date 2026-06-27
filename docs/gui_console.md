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
| Left | Project status, candidate review queue, recent memory |
| Center | Search results, candidate review, and bounded evidence reader |
| Right | Graph, timeline, governance, and usage metadata for the selected memory |

## API

The local server exposes read-only JSON endpoints:

| Endpoint | Purpose |
|---|---|
| `/api/overview` | Stats, automation brief, review inbox, recent memory |
| `/api/candidates` | Candidate queue without full content |
| `/api/candidate/<id>` | Candidate metadata, gate details, and content for review |
| `POST /api/candidate/<id>/review` | Promote, reject, or block with explicit confirmation |
| `/api/search?q=...` | Local keyword search for memory entries |
| `/api/entry/<id>` | Metadata, Document Map rows, claims, graph summary |
| `/api/read?knowledge_id=1&line_start=1&line_end=40` | Bounded evidence range |

## Safety

- The default host is localhost only.
- Active memory edits, archive, and policy edits remain CLI/MCP operations.
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
- make temporal and governance metadata visible beside each memory
- keep future write-capable flows explicit, audited, and rollback-friendly
