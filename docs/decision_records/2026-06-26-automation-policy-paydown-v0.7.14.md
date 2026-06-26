# Decision Record: Automation Policy Paydown for v0.7.14

Date: 2026-06-26

## Context

The automation subsystem has become one of Vault-for-LLM's central product surfaces: cycle runs, review summaries, feedback learning, fleet health, handoff receipts, and scheduled memory maintenance all depend on it.

That growth made `vault/automation.py` carry both workflow orchestration and policy parsing/defaults. The module remained functional, but the mixed responsibility made reviews slower and made future automation changes more likely to touch unrelated code.

## Decision

Move automation policy constants, default policy generation, YAML policy loading, policy file writing, mode normalization, and typed policy value parsing into `vault/automation_policy.py`.

Keep the existing public import surface from `vault.automation`:

- `DEFAULT_MODE`
- `POLICY_FILE`
- `default_policy`
- `load_policy`
- `write_policy`

This preserves compatibility for existing callers such as `vault.agent_setup` and external integrations.

## Impact

- `vault/automation.py` now focuses more narrowly on automation planning and execution.
- The policy module is small enough to review independently.
- Future policy changes can be tested and reasoned about without scanning the full automation workflow implementation.

## Compatibility

No CLI, MCP, database, or policy-file behavior changes are intended.

Existing code that imports policy helpers from `vault.automation` should continue to work.

## Follow-Up

Continue module-size paydown on the next highest-risk surfaces:

- `vault/db.py`: schema/migration and usage/lifecycle operations are still broad.
- `vault/agent_setup.py`: generated artifact templates and installer orchestration can be separated further.
- `vault/automation.py`: review/cycle execution can keep shrinking behind focused helpers.
