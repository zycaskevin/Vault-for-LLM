# Decision Record: Split MCP Automation Handlers

Date: 2026-06-25
Version: v0.6.124

## Context

`vault/mcp.py` had already been reduced by moving read and memory handlers into dedicated modules, but automation and lifecycle branches still kept domain behavior in the central MCP router.

Keeping those branches in the router made future MCP safety review harder because routing, automation policy calls, dream runs, and cold-store lifecycle calls were interleaved in one large function.

## Decision

Move these MCP handlers into `vault.mcp_automation`:

- `vault_automation_inbox`
- `vault_automation_activity`
- `vault_automation_brief`
- `vault_automation_handoff`
- `vault_cold_store_expired`
- `vault_dream_run`

The public MCP tool names, arguments, and JSON result shapes remain unchanged.

## Safety Notes

This is a mechanical module-boundary split. It does not add any new MCP tool, write permission, auto-promote path, remote sync behavior, or background automation trigger.

Automation, dream, and cold-store behavior keeps the existing dry-run defaults, bounded limits, and lifecycle protections.

## Consequences

`vault/mcp.py` becomes closer to a thin router. Automation and lifecycle behavior can now be tested, reviewed, and extended through a smaller domain-specific module before the v0.7 platform boundary.
