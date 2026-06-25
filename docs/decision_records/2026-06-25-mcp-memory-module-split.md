# Decision Record: Split MCP Memory Handlers

Date: 2026-06-25

## Context

`vault/mcp.py` still contained local active-memory writes, candidate-first memory proposals, review/promote/list operations, and session transcript capture. These paths are among the most important MCP safety surfaces because they can create or promote memory. Keeping them inside the main tool dispatcher made review harder and mixed write policy with unrelated read, remote, automation, and server code.

## Decision

Move local memory write/review/capture handlers into `vault.mcp_memory` while keeping compatibility imports in `vault.mcp`.

The moved surface includes:

- `vault_add`
- `vault_memory_propose`
- `vault_memory_promote`
- `vault_memory_review`
- `vault_memory_candidates`
- `vault_capture_session`
- `vault_capture_discover`
- `_format_memory_candidate`
- `_resolve_mcp_transcript_path`

## Expected Impact

- Smaller review surface for MCP memory mutation behavior.
- Clearer separation between tool dispatch, local reads, remote reads, and local memory writes.
- No change to MCP tool names, write-policy checks, privacy gates, candidate-first defaults, session path restrictions, or response payloads.

## Follow-Up

Continue shrinking `vault/mcp.py` around stable boundaries before the 0.7 milestone. Good next candidates are automation/maintenance handlers and MCP tool schema definitions.
