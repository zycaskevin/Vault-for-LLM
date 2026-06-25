# Decision Record: Split Local MCP Read Helpers

Date: 2026-06-25

## Context

`vault/mcp.py` contains tool schemas, dispatch logic, local tools, remote tool wrappers, and read-range helpers. The file is a high-value review surface because MCP tools are the boundary most agents use. Keeping local Document Map and bounded-read logic inside the same file makes it harder to audit read-policy behavior separately from tool dispatch.

## Decision

Move local Document Map and bounded-read helpers into `vault.mcp_read` while keeping compatibility imports in `vault.mcp`.

The moved surface includes:

- `vault_map_show`
- `vault_read_range`
- `_vault_map_show_payload`
- `_vault_read_range_payload`
- `_open_readonly_db`
- `_line_hash`
- `_format_citation`
- `_next_action_for_error`
- `_error`
- `_compact_node`
- `_preferred_read_node`
- `_read_range_action`

## Expected Impact

- Smaller review surface for local MCP read behavior.
- Easier audit boundary between local read helpers and remote Supabase wrappers.
- No change to MCP tool names, payload shapes, citations, range limits, access policy checks, or error guidance.

## Follow-Up

Continue splitting MCP by stable responsibility boundaries. Good next candidates are write/review tool dispatch helpers and automation MCP handlers, as long as public tool names and import compatibility remain intact.
