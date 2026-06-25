# Decision Record: Split Agent Setup Startup Helpers

Date: 2026-06-25

## Context

After schedule, sync, and remote-reader template helpers moved to
`vault.agent_setup_templates`, `vault/agent_setup.py` still mixed the setup
wizard with another large deterministic template surface:

- MCP startup guide generation
- update-status contract, cron, LaunchAgent, and rollout templates
- multi-runtime adapter startup templates
- runtime template marker-based install helper
- startup contract doctor

These helpers are tightly related to startup artifacts, but loosely coupled to
the interactive setup flow.

## Decision

Move startup, update-status, runtime adapter, runtime template install, and
startup doctor helpers into `vault.agent_setup_startup`.

Keep compatibility imports in `vault.agent_setup` so existing CLI handlers,
tests, scripts, and downstream imports can keep using the original module path.

## Consequences

- `vault/agent_setup.py` drops from 3408 lines to 2373 lines.
- `vault/agent_setup_startup.py` is 1071 lines and stays below the default
  1200-line new-module threshold.
- Startup artifact behavior remains unchanged.
- Future setup work can review interactive setup flow, schedule templates, and
  startup contracts separately.

## Follow-Ups

- Continue splitting `vault/agent_setup.py` around optional dependency
  bootstrap helpers and Supabase setup guide rendering.
- Keep compatibility imports for public or CLI-used helper functions.
- Keep packaged install smoke in every release closeout, because setup-agent
  correctness matters most when installed from PyPI.
