---
slug: vault-for-llm
version: "1.0.0"
display_name: Vault-for-LLM Project Memory
displayName: Vault-for-LLM Project Memory
name: vault-for-llm
description: >
  Connect OpenClaw to Vault-for-LLM as a local-first governed project memory
  layer. Search first, then bounded-read cited source ranges; propose new
  memories as candidates instead of writing directly into active memory.
metadata:
  openclaw:
    category: "memory"
    requires:
      bins: ["python3"]
tags:
  - memory
  - vault-for-llm
  - project-knowledge
  - mcp
  - local-first
---

# Vault-for-LLM Project Memory

Use this skill when OpenClaw needs durable project knowledge from Vault-for-LLM.

Vault is not an always-on chat memory dump. Treat it as governed project memory:
confirmed decisions, source-of-truth notes, pitfalls, SOPs, repo docs, and
reviewed handoff knowledge.

## Agent Rules

1. Search before answering project-memory questions.
2. Do not treat search preview text as final evidence.
3. If a result has `id`, `node_uid`, or `line_start`/`line_end`, use bounded
   read before citing it.
4. Cite the source title and line range returned by Vault when making claims.
5. Use candidate-first memory:
   - For new observations, use `vault_memory_propose`.
   - Do not promote candidates unless a human operator explicitly asks.
   - Do not use direct `vault_add` for autonomous memories.
6. Keep secrets out of memory. If content may include tokens, API keys, private
   credentials, or customer data, ask before storing.

## Commands

```bash
vault-openclaw init
vault-openclaw search "deployment checklist" --limit 5
vault-openclaw read-range 12 --line-start 20 --line-end 55
vault-openclaw mcp-config
```

## Database Scope

OpenClaw shares memory with other agents only when they use the same Vault
project directory. If OpenClaw should join a shared project memory, configure the
plugin `projectDir` to the same path used by Hermes, Codex, Claude Code, or n8n.
Use a separate `projectDir` for isolated experiments.

## Recommended Loop

```text
vault_search -> vault_read_range -> answer with source
```

For new memory:

```text
vault_memory_propose -> human review -> vault_memory_promote only after approval
```
