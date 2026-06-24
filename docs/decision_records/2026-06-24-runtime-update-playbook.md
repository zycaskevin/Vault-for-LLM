# Decision Record: Runtime Update Playbook

Date: 2026-06-24

## Context

Vault-for-LLM supports several local Agent runtimes on one machine. Codex,
Claude Code, OpenClaw, Hermes Agent, and other runtimes may each have their own
Python environment, but they should not silently fragment project memory into
separate unmanaged databases.

Earlier releases added the local Agent registry, update-status notices, rollout
doctor checks, and MCP doctor mode. The remaining gap is operational: generated
installer artifacts should tell each runtime exactly what to do at startup and
after one runtime upgrades Vault.

## Decision

`vault setup-agent` writes a runtime update playbook:

- `agent-install/README-runtime-update-playbook.md`
- `agent-install/runtime-update-playbook.json`

The playbook is included with the existing adapter startup pack and describes:

1. startup status read;
2. no-network fallback status;
3. MCP doctor mode for stale or unclear rollout state;
4. automation handoff before deeper memory search;
5. post-upgrade shared notice refresh;
6. no automatic runtime upgrade or restart.

## Safety Boundary

- The playbook is not an auto-upgrader.
- The playbook does not restart another runtime.
- The playbook does not read raw transcripts by default.
- The default stays one shared project vault plus optional private per-Agent
  memory.
- Live PyPI checks remain opt-in.

## Consequences

Multi-runtime installs get one copyable, generated operating rule. Humans can
paste runtime-specific startup templates into each agent, while agents can read
the JSON playbook when they need a machine-readable version of the same rule.
