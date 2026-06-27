# Vault Console

`vault gui` starts a local, read-only browser console for one project vault.

It is the first GUI slice for Vault-for-LLM. It does not replace CLI/MCP, and it
does not mutate memory yet. Use it to inspect the memory loop before deciding
which review action should be taken through CLI or MCP.

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
| Left | Project status, review queue, recent memory |
| Center | Search results and bounded evidence reader |
| Right | Graph, timeline, governance, and usage metadata for the selected memory |

## API

The local server exposes read-only JSON endpoints:

| Endpoint | Purpose |
|---|---|
| `/api/overview` | Stats, automation brief, review inbox, recent memory |
| `/api/search?q=...` | Local keyword search for memory entries |
| `/api/entry/<id>` | Metadata, Document Map rows, claims, graph summary |
| `/api/read?knowledge_id=1&line_start=1&line_end=40` | Bounded evidence range |

## Safety

- The default host is localhost only.
- The first GUI slice is read-only.
- Promotion, rejection, archive, and policy edits remain CLI/MCP operations.
- Private or restricted data should not be exposed by binding the GUI to a
  public network interface.

## Product Direction

The GUI should make the automation loop easier to trust:

- show the smallest human review surface first
- keep bounded evidence more prominent than raw full-document dumps
- make temporal and governance metadata visible beside each memory
- prepare a future write-capable review flow with explicit confirmation,
  audit, and rollback
