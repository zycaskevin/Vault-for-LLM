# Agent Access Presets

## Context

Vault-for-LLM is meant to serve many agent runtimes on the same machine or
through the same shared memory layer: Codex, Claude Code, OpenClaw, Hermes
Agent, n8n, Coze, and future MCP-capable tools.

The raw configuration surface is too large for normal users. They should not
need to understand `scope`, `sensitivity`, `tool_profile`, private vault layout,
shared write permissions, and remote-reader boundaries before an agent can use
Vault safely.

## Decision

Add named Agent Access Presets as the user-facing and agent-facing setup layer.

Initial presets:

- `personal-agent`: private/profile memory, candidate-first writes, no promote.
- `work-agent`: shared project memory, candidate-first writes, no promote.
- `review-agent`: shared review/read surface, no writes.
- `automation-agent`: low-sensitivity maintenance and report jobs.
- `remote-readonly-agent`: Supabase/remote readers with no writes.
- `admin-agent`: trusted local maintenance, explicit promote allowed.

`vault setup-agent --agent-preset ...` can apply default scope, MCP tool
profile, and memory layout when the user or calling agent does not provide
them. Generated multi-agent roster files now include:

- `AGENT_ACCESS_MATRIX.md`
- `AGENT_ACCESS_PRESETS.md`
- per-agent env examples with the selected preset
- setup commands that preserve the preset

Advanced installers can override individual preset fields, including maximum
sensitivity, candidate writes, promotion, shared/private writes, private-memory
marker, and remote-reader marker. Overridden presets are marked with
`customized: true`, keep the `base_preset`, and list the changed fields in
`overrides`.

## Boundaries

Presets are defaults and documentation, not cryptographic identity.
Manual overrides are still defaults and documentation, not cryptographic
identity.

They do not replace:

- MCP HMAC signatures for local identity hardening,
- Supabase RLS/RPC policies for remote reads,
- service-role key separation,
- review/promotion gates,
- OS-level file permissions.

Hosted or browser-based agents should use `remote-readonly-agent` and never get
the Supabase service-role key.

Personal/profile agents can keep private memory locally, but should share only
reviewed summaries into project memory.

## Consequences

Normal users can choose a plain-language role instead of a matrix of flags.
Agents can generate safer installation artifacts without guessing how each
runtime should read, write, or share memory.

Future GUI setup panels and Supabase sync-status views should display these
presets as the primary control surface.
