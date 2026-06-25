# Agent Setup Supabase Module Split

Date: 2026-06-25

## Decision

Move Supabase setup guide rendering, setup-language normalization, and the advanced read-policy SQL template from `vault.agent_setup` into `vault.agent_setup_supabase`.

`vault.agent_setup` re-exports the moved names so existing tests, CLI code, and downstream callers can keep importing the same symbols.

## Context

`vault.agent_setup` has been serving several separate responsibilities: project creation, agent roster files, memory layout manifests, validation packs, startup/update-status templates, sync templates, local smoke scripts, optional dependency installation, and interactive setup.

The Supabase setup section is large because it includes multilingual guide text and a long SQL policy template. Keeping that in the main installer module made reviews noisier, especially after the remote-reader and multi-agent/RLS work.

## Consequences

- Reviewers can inspect Supabase setup and SQL policy generation in one focused module.
- The main setup-agent module remains the orchestration layer instead of the storage/RLS documentation layer.
- Public behavior remains unchanged: generated guide paths, SQL content, mode names, language aliases, and compatibility imports are preserved.
- Future Supabase changes should land in `vault.agent_setup_supabase` unless they affect setup orchestration itself.

## Verification

The release gate should verify:

- `vault setup-agent --features supabase --supabase-setup advanced` still writes `README-supabase-setup.md` and `supabase-read-policy.sql`.
- `from vault.agent_setup import SUPABASE_READ_POLICY_SQL` remains valid.
- `render_supabase_setup_guide(...)` still supports `en`, `zh-Hant`, and `zh-CN`.
- `scripts/module_size_gate.py` reflects the lower `vault/agent_setup.py` size after the split.
