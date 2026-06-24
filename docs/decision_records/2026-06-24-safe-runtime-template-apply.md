# Decision Record: Safe Runtime Template Apply

Date: 2026-06-24

## Context

`vault setup-agent` generates startup templates for common local Agent runtimes:
Codex, Claude Code, OpenClaw, and Hermes Agent. Users still had to copy those
templates into runtime instruction files by hand.

That manual step is fragile. Different runtimes can drift, users can paste the
same template multiple times, and agents may overwrite existing instructions if
the operation is not explicitly designed to be safe.

## Decision

Add:

```bash
vault agent install-runtime-template --runtime <codex|claude-code|openclaw|hermes> --target <file>
```

The command:

- previews by default;
- writes only with `--apply`;
- wraps the generated template in a stable marked block;
- replaces that block on later runs;
- backs up existing target files before changing them;
- reads templates from `agent-install/` by default, or from `--template-dir`.

## Safety Boundary

- No runtime is auto-upgraded.
- No runtime is restarted.
- Existing files are not changed unless `--apply` is present.
- Existing target files are backed up unless `--no-backup` is explicitly set.
- The command applies only generated startup templates, not raw private memory.

## Consequences

Agent-driven installs can now move from "generate a template" to "safely apply a
template" without relying on a human copy-paste step. This keeps multi-runtime
setup consistent while preserving user control over the final write.
