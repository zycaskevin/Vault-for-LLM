# Agent Installer Low-Risk Auto-Promote Policy

Date: 2026-06-24

## Decision

Expose low-risk candidate auto-promotion in `vault setup-agent` as an explicit
installer option.

## Rationale

The closed loop should not require a user or agent to manually edit YAML after
installation. At the same time, auto-promotion changes active memory and must
not be hidden inside a default schedule. The installer should ask the user and
write the policy only when the user chooses it.

## Behavior

- Non-interactive installs can pass `--automation-auto-promote-low-risk`.
- Interactive installs ask whether to enable low-risk auto-promote when memory
  automation schedules are being generated.
- Setup writes or updates `automation_policy.yaml`.
- If an existing policy file is updated, setup creates a timestamped backup.
- Generated schedule README files show whether low-risk auto-promote is enabled.
- Scheduled jobs still need `--automation-apply` before any promotion can
  happen.

## Safety Boundary

This installer option does not widen the promotion rules. It only writes the
same low-risk policy supported by automation: default source `session_capture`,
default memory type `session_lesson`, default sensitivity `low`, a required
source reference, trust threshold, and all candidate gates passing.

