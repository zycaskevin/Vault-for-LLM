# Decision Record: Discussion Conclusions Must Become Documents

Date: 2026-06-24

## Context

Vault-for-LLM is becoming a multi-agent memory infrastructure project. Product
direction often emerges from long design conversations about agent setup,
shared and private vaults, update status, automation handoffs, Supabase sync,
memory governance, and future platform behavior.

Those conversations are useful only if future agents and maintainers can find
the resulting decisions without rereading chat history.

## Decision

Every substantial product, architecture, automation, security, or
memory-governance discussion must be turned into a repository document before
the next implementation pass begins.

This rule applies even when the next task feels obvious. If the conclusion will
influence future development, it must be written down first.

## Product Principle

Vault should treat design conclusions as memory-worthy project knowledge:
reviewable, searchable, sourceable, and safe to hand off to the next agent.

The repo document is the stable source of truth. Chat history can provide
context, but it is not the implementation contract.

## Required Shape

A discussion record should capture:

- what was decided
- why the decision matters
- the intended user-facing behavior
- the agent-facing behavior
- privacy or safety boundaries
- implementation tasks
- deferred questions

The record must be public-safe. It should avoid private names, raw private
conversation details, secrets, local-only paths, personal agent lore, and
unreviewed sensitive context.

## Current Discussion Outcome

For multi-agent installs, Vault should move toward one shared local runtime per
machine with registered agent adapters. Memory should not become fragmented
across every tool.

The recommended default is hybrid:

- shared project vaults for project knowledge, SOPs, fixes, release process,
  benchmarks, and safety rules
- private agent vaults for identity, private preferences, personal notes, and
  agent-specific working style
- optional Supabase sync for cross-device or remote-agent shared memory
- a local agent registry and update status surface so connected agents can see
  Vault version, update notices, and startup handoff guidance

Future setup flows should make this clear during installation instead of making
users guess whether each agent is using an isolated or shared memory store.

## Follow-up Tasks

- Add a local agent registry for registered tools and agents.
- Add update-status and upgrade-plan commands.
- Let setup-agent default toward hybrid memory layout.
- Add startup guidance so each registered agent checks update status and reads
  the latest automation handoff.
- Consider MCP access for update status and automation handoff.
