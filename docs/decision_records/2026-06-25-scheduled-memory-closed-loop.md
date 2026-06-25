# Scheduled Memory Closed Loop

Date: 2026-06-25

## Decision

Vault-for-LLM scheduled memory automation should run a full candidate-first
closed loop:

1. `vault memory pipeline --write-candidates`
2. `vault memory reflection --write-candidates`
3. `vault automation cycle`
4. `vault automation inbox --write-handoff`
5. `vault automation learning-health --write-health`

This turns the automatic, temporal, and reflective memory features into a daily
agent habit instead of separate manual commands.

## Safety Boundary

- The pipeline writes candidate memory only.
- Reflection writes review candidates only.
- `automation cycle` keeps the existing policy and apply controls.
- The generated handoff remains compact and does not expose raw transcript
  contents or raw private memory.
- MCP exposure for pipeline/reflection/temporal status belongs to review,
  maintenance, and explicit tool allowlists; the `core` profile stays small.

## Rationale

Long-running agents need memory to improve without asking the user to inspect
every line. The loop should therefore automate extraction, reflection, ranking,
and handoff, while preserving a small human-review surface for ambiguous,
sensitive, or high-impact changes.
