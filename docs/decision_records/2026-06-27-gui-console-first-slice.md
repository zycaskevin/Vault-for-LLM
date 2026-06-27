# GUI Console First Slice

Date: 2026-06-27

## Decision

Vault-for-LLM should start its GUI as a local read-only console, not as a full
note editor or hosted dashboard.

The first slice is:

- left navigation: overview, search, review queue
- center evidence reader: search results and bounded source ranges
- right intelligence panel: graph, timeline, governance, and usage metadata

This follows the useful shape of document tools such as Obsidian without copying
their product goal. Vault is an agent memory governance layer, so the right
panel must answer whether a memory is usable, current, cited, and permitted,
not only whether it links to another note.

## Rationale

The GUI should make the existing automation loop easier to trust:

- humans should see the smallest review queue first
- agents should keep using CLI/MCP for writes and automation
- bounded reads and citations should stay more prominent than raw full-document
  dumps
- local-first users should not need Node, a database server, or a hosted UI

## Scope

First implementation:

- `vault gui` starts a localhost-only HTTP server using Python stdlib
- no new runtime dependency
- read-only JSON endpoints for overview, search, entry metadata, bounded read,
  and graph summary
- a single static HTML/CSS/JS shell served by the local process

Out of scope for the first slice:

- promote/reject/archive buttons that mutate memory
- authentication beyond localhost binding
- packaged Electron or desktop app shell
- remote Supabase browser

## Safety

The first GUI should not expose private data over the network by default. It
binds to `127.0.0.1` unless the operator explicitly chooses a different host.

Mutation workflows stay in CLI/MCP until the GUI has explicit confirmation,
audit, and rollback affordances.
