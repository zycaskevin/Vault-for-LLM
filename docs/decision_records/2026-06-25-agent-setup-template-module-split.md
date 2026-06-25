# Decision Record: Split Agent Setup Template Helpers

Date: 2026-06-25

## Context

`vault/agent_setup.py` remained one of the largest modules in the package after
the MCP, automation report, and automation CLI splits. A large part of the file
was template rendering and command construction for setup artifacts:

- Obsidian sync cron, LaunchAgent, and n8n templates
- Supabase sync templates
- remote-reader shell, n8n, and Coze templates
- memory automation schedule templates
- shared shell/plist/n8n rendering helpers

These helpers are important, but they are mostly deterministic file rendering.
Keeping them inside the main setup wizard made review harder than necessary.

## Decision

Move schedule, sync, and remote-reader template helpers into
`vault.agent_setup_templates`.

Keep compatibility imports in `vault.agent_setup` so existing tests, scripts,
and downstream callers can continue importing the helper names from the original
module.

## Consequences

- `vault/agent_setup.py` drops from 4266 lines to 3408 lines.
- `vault/agent_setup_templates.py` is 899 lines and stays below the default
  1200-line new-module threshold.
- `vault setup-agent` behavior and generated artifact paths stay unchanged.
- Future setup work can review wizard flow separately from template rendering.

## Follow-Ups

- Continue splitting `vault/agent_setup.py` by stable boundaries, especially
  startup/update-status templates and optional dependency bootstrap helpers.
- Keep each split behavior-preserving and backed by packaged install smoke.
- Lower module-size baselines after each successful split.
