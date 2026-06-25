# Decision Record: Split Automation CLI Helpers

Date: 2026-06-25

## Context

`vault/cli.py` is one of the largest modules in the package. After the
automation report helpers moved to `vault.automation_reports`, the next
low-risk boundary was the automation CLI surface:

- `vault automation ...` command dispatch
- human-readable automation output rendering
- automation subcommand parser registration

This code is large, but it is mostly command routing and presentation, not core
automation lifecycle logic.

## Decision

Move automation CLI command handling and parser registration into
`vault.cli_automation`.

Keep `vault.cli.cmd_automation(args)` as a wrapper that delegates to the new
module. The wrapper passes the existing project-dir resolver and JSON printer
into `vault.cli_automation`, avoiding a reverse import from the new module back
into `vault.cli`.

## Consequences

- `vault/cli.py` drops from 4413 lines to 3571 lines.
- `vault/cli_automation.py` is 869 lines and stays below the default 1200-line
  new-module threshold.
- The public automation command surface stays stable.
- Automation CLI tests continue to exercise the same command names and output
  paths while the implementation is easier to review.

## Follow-Ups

- Continue splitting `vault/cli.py` by command family, especially large but
  mostly-presentational surfaces.
- Keep compatibility wrappers when tests or downstream users import existing
  command functions.
- Lower module-size baselines after each split.
