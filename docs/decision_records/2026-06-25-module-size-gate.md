# Module Size Gate

Date: 2026-06-25

## Context

Vault-for-LLM has grown quickly. Large modules such as automation, CLI, agent setup, MCP, search, and database code are still functional, but their size makes reviews slower and makes security-sensitive changes harder to reason about.

The project needs a guardrail that improves maintainability without blocking the current codebase.

## Decision

Add a baseline-based module-size gate.

- New `vault/*.py` modules use a default maximum line count.
- Existing modules that already exceed the default are recorded in `scripts/module_size_baseline.json`.
- A baselined oversized module may stay at or below its recorded size.
- A baselined oversized module may not grow unless the baseline is intentionally updated with review context.
- CI runs `python scripts/module_size_gate.py`.

## Consequences

This does not force an immediate large refactor. It prevents further silent growth while allowing the team to split large modules incrementally.

When a feature needs to touch a large module, the preferred path is to extract a focused helper module with its own tests. If growth is truly unavoidable, the baseline update should be explicit and documented.

## Follow-Ups

- Continue reducing `vault/mcp.py` after the security helper split.
- Identify focused extraction points in `vault/automation.py`, `vault/cli.py`, and `vault/agent_setup.py`.
- Consider adding a report mode for trend tracking after several releases.
