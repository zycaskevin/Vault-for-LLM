# Consumer Product Hardening Before Release

## Decision

Before the next public release, Vault should treat non-technical Agent users as
the default consumer path:

- the human opens the GUI or reads `vault daily-report`,
- the Agent handles CLI, MCP, setup files, and automation,
- setup asks only a small number of human questions in consumer mode,
- local GUI and MCP safety guidance is generated during setup.

## Consumer Setup Questions

Consumer mode should avoid a full engineering questionnaire. The visible choices
are:

1. language: Traditional Chinese, Simplified Chinese, or English,
2. independent or shared memory vault,
3. optional connections: Obsidian, Supabase, both, or none,
4. daily report time.

Everything else remains available through flags or builder mode.

## Consumer Output

Consumer setup output should be split by audience:

- the default terminal output is for the human and should stay short,
- Agent maintenance details go under a separate "For your agent" section,
- full setup payloads remain available with `--json`,
- builder mode can still print the detailed maintenance checklist.

This keeps "agent-driven install" from turning back into an engineering
questionnaire after setup succeeds.

## Safety Boundary

Consumer mode stays report-first:

- scheduled jobs can write daily reports and automation handoffs,
- scheduled jobs do not enable `--apply` by default,
- HMAC is strongly guided through generated env examples but not forced on
  existing MCP clients,
- GUI token auth remains enabled by default.

## Consequences

- GUI should feel like a memory control center before it feels like a database
  browser.
- GUI and daily reports should keep the selected human language so people do
  not need to read English command output to trust the system.
- `setup-agent --audience consumer` becomes the recommended public onboarding
  command.
- Builder mode remains the place for detailed optional dependency, Supabase,
  roster, and automation policy choices.
