# MCP Remote Module Split

Date: 2026-06-25

## Context

The MCP router contains both local project-memory tools and remote Supabase reader tools. The remote path is security-sensitive because it enforces read policy, bounded source reads, and remote doctor checks for cross-host agents.

After adding the module-size gate, `vault/mcp.py` was still a large review surface. The next safe split was the remote reader path because it has a clear concern boundary.

## Decision

Move Supabase remote MCP reader helpers into `vault.mcp_remote`.

The main `vault.mcp` module still exposes compatibility imports and wrappers for:

- `vault_remote_map_show`
- `vault_remote_read_range`
- `_vault_remote_search_payload`
- `_vault_remote_doctor_payload`
- `_vault_remote_map_show_payload`
- `_vault_remote_read_range_payload`
- existing remote helper imports used by tests and downstream callers

## Consequences

The public MCP tool names and payloads remain unchanged. Existing monkeypatch-based tests that patch `vault.mcp._get_supabase_client` continue to work.

The module-size baseline for `vault/mcp.py` is lowered after the split, so the file cannot silently grow back to its old size.

## Follow-Ups

- Split automation MCP helpers into a focused module.
- Split memory-candidate MCP helpers into a focused module.
- Continue preserving public MCP tool names while moving implementation details behind smaller modules.
