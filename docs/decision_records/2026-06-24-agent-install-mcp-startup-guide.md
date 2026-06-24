# Decision Record: Agent Installer MCP Startup Guide

Date: 2026-06-24

## Decision

`vault setup-agent` should generate MCP startup instructions alongside CLI
startup instructions.

The installer writes:

- `agent-install/mcp-startup.json` for agents and wrappers.
- `agent-install/README-mcp-startup.md` for people and agent prompts.

The startup order is:

1. Call `vault_update_status`.
2. Call `vault_automation_handoff`.
3. Search with `vault_search` only when more context is needed.
4. Read bounded evidence with `vault_read_range`.
5. Propose new durable memory with `vault_memory_propose`.

## Rationale

Many users run several local runtimes on the same machine. Some prefer CLI
commands, while MCP-capable agents should not have to infer startup behavior
from README prose. Generated installer artifacts make the runtime contract
visible, repeatable, and easy for Hermes Agent, Codex, Claude Code, OpenClaw,
and other MCP-capable systems to follow.

## Safety Boundary

- The guide does not start a network service.
- The guide keeps `check_pypi=false` by default.
- The guide keeps handoff reads under `reports/automation`.
- The guide does not grant permission to read raw transcripts or auto-promote
  memory.
- Tool profiles are convenience filters, not authorization boundaries.

## Non-goals

- This does not replace Supabase RLS/RPC for remote access control.
- This does not force every agent to use MCP.
- This does not change the shared/private vault layout policy.
