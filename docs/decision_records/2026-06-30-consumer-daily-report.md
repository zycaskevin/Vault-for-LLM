# Consumer Daily Report Boundary

Date: 2026-06-30

## Decision

Vault should support a non-technical user path where the human does not learn
the CLI. Agents operate the memory system through setup artifacts, MCP profiles,
and automation schedules. The human reviews a short daily report and only makes
the few decisions that need human judgment.

## Product Boundary

- CLI and MCP remain agent/operator surfaces.
- `vault daily-report` is the primary human daily surface.
- The GUI should show the same daily report before deeper memory details.
- Consumer setup should generate plain-language daily-report guidance.
- Consumer schedules must stay report-first unless the user explicitly enables
  apply/autopromote policies.

## Safety

The daily report is read-only. It must not promote candidates, archive memory,
delete memory, change access policy, or reveal raw candidate content. It may
write JSON/Markdown report artifacts under `reports/daily/`.

## Rationale

General agent users should feel that Vault is a memory vault maintained by their
agent, not a database they have to administer. The 95/5 model is:

- 95%: agents search, organize, propose candidates, rank review work, and keep
  reports fresh.
- 5%: humans confirm important memory decisions such as keep/private/share/do
  not remember/defer.

## Follow-Up

- Add richer GUI review actions for daily-report cards.
- Let scheduled consumer mode write `daily-report-latest.md` directly.
- Add install-copy in generated runtime templates that tells agents to show the
  daily report first.
