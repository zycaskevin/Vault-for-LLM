# Agent-First Usage

Vault-for-LLM has many commands because agents, scheduled jobs, and maintenance
workflows need precise tools. Humans should not have to memorize that surface.

Use this rule:

> Humans choose intent. Agents choose commands.

Use `vault guide --intent <intent>` when you want an even smaller map:

```bash
vault guide --intent install
vault guide --intent daily
vault guide --intent skills
```

## Human Surface

Most people only need these entrypoints:

| Intent | Command |
|---|---|
| Install or connect an agent | `vault setup-agent` |
| See the small command map | `vault guide` |
| Browse locally | `vault gui` |
| Search memory | `vault search "query"` |
| Propose something worth remembering | `vault remember "Title" --content "..." --reason "..."` |
| Continue a long task | `vault task start/update/handoff` |
| Check local health | `vault doctor` / `vault security doctor` |

Everything else can be treated as an implementation detail unless you are
debugging, maintaining, or writing an integration.

## Agent Surface

Agents should prefer MCP profiles over raw CLI breadth.

| Profile | Use |
|---|---|
| `core` | Daily recall: status, activity, brief, handoff, search, bounded read, propose memory |
| `review` | Candidate review, transcript capture, Task Ledger, Skill read/sync inspection, Dream reports |
| `maintenance` | Explicit operator-led writes, cold-store lifecycle, Obsidian import, convergence, freshness |
| `full` | Trusted local operators and backwards compatibility |

Start daily agents with:

```bash
vault-mcp --project-dir ~/Vaults/project-memory --tool-profile core
```

Escalate to `review` or `maintenance` only for the session that needs it.

## Why The CLI Is Still Large

The wider CLI is for:

- setup agents generating startup packs,
- scheduled automation and n8n templates,
- Supabase remote-reader validation,
- Obsidian/OKF import and export,
- search QA and benchmark reproducibility,
- database backup/restore and migration,
- local troubleshooting.

Keeping those commands available helps agents work precisely. Hiding them from
the human quickstart keeps the product usable.

## Recommended Flow

1. Ask an agent to install Vault with `vault setup-agent`.
2. Use `vault guide` when you want a compact map.
3. Use `vault guide --intent skills` when you only need Skill upgrade review.
4. Let daily agents use `core` MCP.
5. Let review agents use `review` MCP only when they need candidate or task
   review.
6. Reserve `maintenance` for scheduled jobs or explicit operator-led cleanup.

## Non-Goals

- Do not put every command in the README quickstart.
- Do not expose every MCP tool in `core`.
- Do not ask users to choose low-level flags when `setup-agent` can generate a
  stable configuration.
- Do not silently promote memory, install skills, or apply maintenance actions
  just because a command exists.
