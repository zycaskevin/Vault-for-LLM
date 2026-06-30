# Skill Upgrades And Agent-First CLI Surface

Date: 2026-06-30

## Decision

Keep the full CLI available for agents, scheduled jobs, and maintainers, but do
not make humans learn that whole surface.

The product entrypoint remains:

```bash
vault guide
```

`vault guide --intent ...` narrows the map by user intent. For Skill operations,
the human-facing path is an advisory upgrade plan, not direct runtime mutation:

```bash
vault guide --intent skills
vault skill upgrade-plan --installed-file installed-skills.json
```

## Why

Vault has grown into a broad local Agent knowledge platform. Removing commands
would make automation and reproducibility worse, but showing every command to a
human makes the product feel noisy.

The stable rule is:

> Humans choose intent. Agents choose commands.

## Skill Upgrade Boundary

The local Skill registry can store versions, content hashes, and sync state. An
upgrade plan may report:

- `not_installed`
- `current`
- `upgrade_available`
- `drift`
- `local_newer`

These states are advisory. They do not install, overwrite, or delete runtime
Skill files. Runtime Skill changes still require an explicit user/operator
sync step outside the registry.

## Consequences

- Humans get a smaller guided surface.
- Agents still get precise tools through MCP profiles and generated setup
  artifacts.
- Skill upgrade checks can detect content drift when installed manifests include
  `content_hash`, not only version numbers.
- Future GUI work can call the same upgrade-plan payload to show a reviewable
  Skill update panel.
