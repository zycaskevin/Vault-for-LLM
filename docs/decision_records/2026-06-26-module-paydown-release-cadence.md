# Decision Record: Module Paydown Release Cadence

Date: 2026-06-26

## Context

Vault-for-LLM has been moving quickly through the v0.7 line. Several recent releases shipped real user-facing improvements, but the same cadence should not be used for every internal module split.

Large-module paydown is important, but each split is mostly maintenance work. Publishing a new external version for every split makes the project look noisy and can make users wonder whether every release requires attention.

## Decision

Use multiple focused pull requests for module-size paydown, but do not publish a new package release after every maintenance PR.

Release only when one of these is true:

- A user-facing feature is added or materially changed.
- A security or privacy fix needs external users to upgrade.
- Several maintenance PRs have accumulated into a meaningful stability release.
- Documentation, install behavior, or packaging behavior changes in a way users need to know.

Internal-only refactors should still pass the normal gates, but they can land on `main` without a version bump.

## Working Pattern

For module paydown:

1. Open small PRs with one clear boundary each.
2. Avoid version bumps, PyPI releases, and GitHub Releases unless the PR changes external behavior.
3. Keep compatibility shims when moving public imports.
4. Tighten module-size baselines only after the split passes tests.
5. Record substantial architecture decisions in `docs/decision_records/`.

## Initial Paydown Queue

- `vault/db.py`: schema constants, table initialization, usage lifecycle, and memory feedback logic.
- `vault/agent_setup.py`: setup orchestration vs generated templates.
- `vault/automation.py`: execution flow vs policy/review/cycle helpers.

## Expected Outcome

External users see fewer, more meaningful releases.

Maintainers still get small reviewable PRs, CI protection, and clear module-size progress.
