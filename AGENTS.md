# Agent Instructions For Vault-for-LLM

This repository is designed to be installed, configured, and modified by agent
runtimes as well as by humans. If you are an agent working in this repo, treat
this file and `agent_manifest.json` as the operational source of truth.

If you can run shell commands for the user, do not stop at telling them how to
install Vault-for-LLM manually. Ask the required scope/feature questions, run the
install/configuration steps yourself, and finish with a smoke test.

## Common Install Architecture

Hermes Agent, Codex, OpenCode, Claude Code, OpenClaw, n8n, and other
MCP-capable or shell-capable agents should use the same basic shape:

```text
choose projectDir -> choose optional features -> install vault -> configure CLI or stdio MCP -> verify search/read/propose
```

Only add runtime-specific adapters when the host needs custom tool registration
or UI metadata. The stable cross-agent contract is `projectDir`, the `vault`
CLI, `vault-mcp`, and candidate-first memory writes.

For MCP-capable agents, prefer the smallest tool profile that fits the job:

```bash
vault-mcp --project-dir /path/to/project --tool-profile core
```

`core` exposes only `vault_search`, `vault_read_range`, `vault_memory_propose`,
and `vault_stats`. Use `review`, `remote`, `maintenance`, or `full` only when
those extra tools are needed.

## Second Decision: Optional Features

After choosing database scope, ask which optional capabilities the user wants.
Do not install heavyweight or cloud-connected extras silently.

Recommended prompts:

| Feature | Default | Ask when | Install command |
|---|---|---|---|
| `core` | yes | Always. Local SQLite, Markdown, keyword search. | `python -m pip install vault-for-llm` |
| `mcp` | yes for MCP-capable agents | The runtime supports local stdio MCP. | `python -m pip install "vault-for-llm[mcp]"` |
| `obsidian_import` | no | User has an existing Obsidian vault to import and search through Vault. | built into core CLI |
| `semantic` | no | User wants embedding-backed semantic/hybrid retrieval. | `python -m pip install "vault-for-llm[semantic]"` |
| `supabase` | no | User wants optional remote sync/read paths. | `python -m pip install "vault-for-llm[supabase]"` |
| `dev` | no | You are modifying the repo, running benchmarks, or validating a PR. | `python -m pip install -e ".[dev]"` |

After database scope and optional feature prompts, ask whether the user has an
existing Obsidian vault. If yes, ask for the vault path, run a dry-run first,
then perform the first import only after confirmation:

```bash
vault import obsidian --vault /path/to/ObsidianVault --project-dir /path/to/project --dry-run
vault import obsidian --vault /path/to/ObsidianVault --project-dir /path/to/project --compile
```

After the first import, ask whether to schedule automatic sync with cron,
LaunchAgent, n8n, or the host agent by re-running the same `--compile` command.

For semantic installs, configure a real provider and rebuild vectors:

```bash
vault install-embedding --model mix
vault semantic rebuild --project-dir /path/to/project --persist-cache --pretty
```

For Ollama-backed embeddings, use:

```bash
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
```

For Supabase sync, remind the user that SQLite remains the source of truth and
full-content sync requires explicit approval:

```bash
python scripts/sync_to_supabase.py --document-map
```

## First Decision: Database Scope

Before installing or connecting Vault-for-LLM for a user, decide where the
Vault project directory should live.

```text
one project directory = one vault.db
```

Use one shared project directory when trusted agents should collaborate on the
same governed project memory. Use separate project directories when an agent,
customer, domain, test, or benchmark must stay isolated.

Recommended choices:

| Scope | Use when | Example |
|---|---|---|
| `shared` | Hermes, OpenClaw, Codex, Claude Code, or n8n should share confirmed project knowledge. | `~/Vaults/my-project` |
| `private` | One agent is experimenting or should not affect official memory. | `~/.openclaw/workspace/vault-project` |
| `domain` | Customer or business data boundaries must stay separate. | `~/Vaults/clinic-customer-service` |
| `temporary` | Demos, tests, and benchmarks. | `/tmp/vault-benchmark-*` |

If the user has not specified a scope, ask whether they want a shared project
vault or an isolated agent-private vault. For non-interactive installs, default
to `private`.

## Safe Agent Workflow

For retrieval:

```text
search -> bounded read -> answer with sources
```

For new memory:

```text
propose candidate -> review -> promote only when approved
```

In shared vaults, prefer `vault_memory_propose` or `vault remember` over direct
active writes. Do not let every runtime write unreviewed facts into the same
active memory database.

## Common Commands

Local source checkout:

```bash
python -m pip install -e .
vault init --project-dir /path/to/project
vault compile --project-dir /path/to/project --no-embed
vault search "release checklist" --project-dir /path/to/project --limit 5
vault-mcp --project-dir /path/to/project --tool-profile core
```

Existing Obsidian vault source:

```bash
vault import obsidian --vault /path/to/ObsidianVault --project-dir /path/to/project --dry-run
vault import obsidian --vault /path/to/ObsidianVault --project-dir /path/to/project --compile
```

Ask before connecting Obsidian. Use `--dry-run` first, then schedule the same
`--compile` command with cron, LaunchAgent, n8n, or the host agent if the user
wants automatic sync. The importer skips `00-Vault-Knowledge/` so Vault export
notes do not loop back into source memory.

OpenClaw install:

```bash
bash integrations/openclaw/install.sh --scope private --non-interactive
bash integrations/openclaw/install.sh --scope shared --project-dir ~/Vaults/my-project --non-interactive
```

## Validation Before PRs

Run the narrow checks that match your change, and prefer the full test suite
when behavior changed:

```bash
python scripts/readme_command_smoke.py
python scripts/check_release_parity.py
bash integrations/openclaw/verify.sh
python -m pytest -q
```

For OpenClaw installer changes, also smoke-test `--scope private`,
`--scope shared --project-dir <tmp>`, and missing option values.

## Safety Rules

- Do not commit runtime vault databases, benchmark output, report artifacts, or
  local secrets.
- Do not expose `vault-mcp` directly to the public internet; it is a local stdio
  server, not an authenticated network service.
- Do not claim benchmark percentages as universal product scores. Keep them tied
  to the dataset, probe type, and retrieval mode that produced them.
- Do not change package name, CLI entry points, or license text without updating
  README variants, release parity checks, and integration docs.
