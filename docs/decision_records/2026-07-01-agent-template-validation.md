# Agent Template Validation

Date: 2026-07-01

## Decision

Generated Agent install packs must be machine-checkable before release. The
same `vault agent startup-doctor` command that checks the startup handoff
contract also validates the shortest safe setup contracts for Codex, Claude
Code, Hermes, OpenClaw, Coze, and n8n.

## Why

Vault-for-LLM is meant to be installed and maintained by agents for normal
users. That means generated templates cannot rely on humans reading every file
after each release. The install pack should fail loudly when a runtime template
or remote-reader setup drifts away from the current safety boundary.

## Validation Scope

`startup-doctor` validates:

- local stdio MCP clients for Codex, Claude Code, Hermes, and OpenClaw;
- hosted or workflow reader templates for Coze and n8n;
- HMAC recommendation and candidate-first MCP memory guidance;
- Gateway health/serve commands and safe adapter defaults;
- remote-reader safety, including explicit opt-in for bidirectional Supabase
  sync.

## Non-Goals

This does not execute every runtime. It checks the generated contracts and
configuration shape from the install pack. Runtime-specific end-to-end smoke
tests still belong in release validation.
