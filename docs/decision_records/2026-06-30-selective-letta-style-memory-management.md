# Decision Record: Selective Letta-Style Memory Management

Date: 2026-06-30

## Context

Vault-for-LLM has grown from a local project memory vault into a broader
agent-facing memory platform: candidate-first writes, Task Ledger, automation
cycle, temporal facts, reflection, GUI, MCP profiles, and multi-agent registry.

Letta/MemGPT points toward a valuable experience: agents can manage memory
autonomously, consolidate old context, and keep long-lived state without a
developer manually calling `add()` at every turn.

The risk is architectural drift. Letta is a full stateful agent runtime. Vault
should not force users to move their agents into one runtime or accept black-box
memory writes. Vault's product value is local-first, inspectable, reversible,
agent-agnostic memory governance.

## Decision

Vault will learn from Letta-style memory management, but it will not become a
full agent runtime.

The core remains a small, inspectable memory engine:

- Markdown and SQLite remain the durable source surfaces.
- Candidate-first memory remains the default for autonomous ingestion.
- CLI and MCP remain the integration contracts.
- Automation remains policy-driven, report-first, and reversible by default.
- Task Ledger remains task-runtime state, not a new L0-L3 memory layer.

Autonomous memory behavior is added as optional layers around the core:

1. **Automatic memory pipeline**
   - Discover and parse session artifacts.
   - Extract candidate memories.
   - Run deterministic privacy, duplicate, metadata, quality, and governance
     gates.
   - Write candidates or reports; do not silently promote by default.

2. **Lifecycle management**
   - Track usage, freshness, temporal validity, and importance.
   - Archive, summarize, or cold-store old memories before deleting anything.
   - Keep original content recoverable for audit and rollback.

3. **Reflection / dreaming**
   - Periodically cluster, summarize, deduplicate, and surface higher-level
     insights.
   - Feed suggestions back into the candidate queue or review reports.
   - Keep long-term learning explainable and bounded.

## Current Implementation Direction

This decision is reflected in the current v0.7 line:

- MCP tool profiles keep daily agents on `core`; review/maintenance tools are
  opt-in.
- Local MCP reads default to `max_sensitivity=medium` instead of anonymous
  all-sensitivity reads.
- GUI access is token-protected by default.
- Task Ledger supports `priority` and `due_at` for task continuity without
  promoting todo state into active memory.
- Skill Registry gains version history and upgrade planning, but agents do not
  silently overwrite runtime skills.

## Consequences

Good consequences:

- Vault remains usable by Codex, Claude Code, Hermes, OpenClaw, n8n, Coze, and
  other runtimes without requiring a single agent OS.
- Users can choose manual, semi-automatic, or scheduled autonomous memory modes.
- Memory changes remain auditable and recoverable.
- MCP token cost stays bounded for daily use.

Tradeoffs:

- Vault will not feel as magically autonomous as a full Letta-style runtime out
  of the box.
- Some automation requires setup choices, policies, and review workflows.
- Strong identity/auth for local agents remains an operator choice unless a
  future deployment mode can enforce it without breaking common local MCP
  clients.

## Non-Goals

- Do not create a hidden background memory writer that bypasses candidates.
- Do not make Task Ledger an `L4` or merge it into `L2`.
- Do not make Skill upgrade plans automatically overwrite agent skill files.
- Do not require PostgreSQL, a service daemon, or one hosted runtime for normal
  local use.

## Follow-Ups

- Keep improving automatic memory extraction quality.
- Add more visible, compact human-review reports for the 5% of decisions that
  need user approval.
- Make Skill version status visible in fleet health once enough agents declare
  their skill usage.
- Consider stronger local agent identity defaults when common MCP clients can
  interoperate cleanly with HMAC or another lightweight authentication scheme.
