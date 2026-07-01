# Directed Agent Handoff Inbox

## Context

Multiple local agents can share one project vault while keeping their own private
memory. They still need a safe way to pass active work from one runtime to
another: Codex may finish a code slice, Hermes may continue review, and OpenClaw
or Claude Code may later resume the same task.

Agent runtimes can already write their own handoff prose, but free-form handoffs
are hard to discover, audit, or claim. Storing them as L2 memory would also blur
the boundary between durable project context and temporary task state.

## Decision

Vault keeps handoff packets inside Task Ledger as a directed inbox:

- `vault task send-handoff` creates a packet addressed from one agent to another.
- `vault task inbox` lists packets for a receiving agent.
- `vault task claim-handoff` records which agent accepted the handoff.
- MCP exposes the same workflow through `vault_task_send_handoff`,
  `vault_task_handoff_inbox`, and `vault_task_claim_handoff`.

The packet contains a task snapshot, sender note, and shared evidence references.
It does not promote content into L0-L3 memory, and it must not copy another
agent's private identity, style notes, or raw private conversation memory into
the shared task inbox.

## Consequences

- Agents can keep their own handoff style while Vault provides the shared
  receipt, status, and audit trail.
- Receivers can claim work without reading the sender's private vault.
- Task Ledger remains task-runtime state; reusable lessons still go through the
  normal candidate-first memory gates before entering L0-L3.
- GUI and automation can later surface the same `task_handoffs` table without
  inventing a second handoff model.
