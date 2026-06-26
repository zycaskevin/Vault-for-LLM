# 2026-06-26 Agent Setup Runtime Module Split

## Status

Accepted.

## Context

The v0.7 stabilization queue includes large-module paydown before the next
external release. `vault/agent_setup_startup.py` had grown to cover two related
but separate responsibilities:

- generating MCP startup, update-status, and runtime adapter install files
- installing generated runtime templates and checking startup-contract health

Keeping both in one module made future setup-agent changes harder to review and
made the startup-doctor code look like part of the template renderer.

## Decision

Move runtime-template installation and startup-contract doctor helpers into
`vault/agent_setup_runtime.py`.

`vault/agent_setup_startup.py` remains responsible for generating setup files.
`vault/agent_setup_runtime.py` owns:

- runtime template filename and marker helpers
- dry-run/apply installation of generated runtime startup templates
- startup-contract doctor checks for generated JSON, runtime templates, and
  README files

`vault.agent_setup` continues to re-export the public helper functions used by
CLI flows, so command behavior and import paths used by the CLI stay stable.

## Consequences

- Setup-agent startup generation and runtime validation now have clearer module
  ownership.
- The module-size gate has more useful headroom for future setup-agent changes.
- No release is needed for this refactor by itself; it is part of the v0.7
  stabilization batch.
- Future runtime-specific startup checks should go into
  `vault/agent_setup_runtime.py`, not the template renderer.
