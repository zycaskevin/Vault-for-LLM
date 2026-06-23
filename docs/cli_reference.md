# CLI Reference

This page lists the broader Vault-for-LLM CLI surface. Most agents should start
with the daily loop in the README and only use these commands when needed.

## Daily Workflow

| Command | Purpose |
|---|---|
| `vault init` | Initialize a project vault |
| `vault setup-agent` / `vault install-agent` | Run the agent installer wizard and optional Obsidian sync template generator |
| `vault remember "Title" --content "..." --reason "..."` | Propose candidate memory for review |
| `vault capture session codex-session.jsonl --pretty` | Preview candidate memories extracted from an agent session transcript |
| `vault capture session codex-session.jsonl --write-candidates` | Write extracted session lessons into the candidate queue, not active knowledge |
| `vault candidates` | List pending candidate memories without dumping full raw content |
| `vault promote <candidate_id> --confirm` | Promote reviewed candidate memory |
| `vault compile` | Compile `raw/` into SQLite and generated artifacts |
| `vault search "query"` | Search the vault |
| `vault map read <id> --lines 10-30` | Read a bounded source range for citation |
| `vault remote smoke --agent-id remote-agent --query "deployment SOP" --json` | Verify Supabase remote reader credentials and the `vault_search_readable` RPC |
| `vault remote doctor --agent-id remote-agent --query "deployment SOP" --json` | Diagnose the full Supabase remote reader path: search, readable-entry RPCs, Document Map, claims, content, map, and bounded read |
| `vault remote search "query" --agent-id remote-agent --json` | Search the Supabase read-only memory view through `vault_search_readable` |
| `vault remote map <id> --compact --json` | Inspect remote synced Document Map rows |
| `vault remote read <id> --node-uid <node> --json` | Read remote bounded evidence from synced content/claims |
| `vault remove <id> --confirm` | Remove a knowledge entry after reviewing its ID |

## Knowledge Ingestion

| Command | Purpose |
|---|---|
| `vault add "Title" --content "..."` | Add one active knowledge entry directly |
| `vault add "Title" --file note.md` | Add an entry from a Markdown file |
| `vault import long-doc.md` | Import and chunk a long document |
| `vault import obsidian --vault /path/to/ObsidianVault --dry-run` | Preview importing existing Obsidian notes into `raw/obsidian/` |
| `vault import obsidian --vault /path/to/ObsidianVault --compile` | Import changed Obsidian notes and compile them into `vault.db` |
| `vault export obsidian --vault /path/to/ObsidianVault --dry-run` | Export read-only Markdown notes for Obsidian browsing |

Prefer `vault remember` over `vault add` for autonomous agents or unreviewed
memory.

`vault import obsidian` skips `.obsidian/`, `.trash/`, `.git/`, and
`00-Vault-Knowledge/` by default. The generated raw notes include
`obsidian_source_path` and `obsidian_source_hash`, so repeated imports update
changed notes without duplicating unchanged ones.

## Agent Setup

| Command | Purpose |
|---|---|
| `vault setup-agent` | Ask for scope, setup language, optional features, Obsidian import, sync templates, and generate `agent-install/local-smoke.sh` |
| `vault setup-agent --non-interactive --agent codex --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,obsidian_import` | Agent-friendly scripted install |
| `vault setup-agent --non-interactive --agent codex --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,semantic,supabase,headroom --language en --install-optional-deps --install-embedding-model mix --supabase-setup simple --json` | Install selected optional dependencies and configure a local semantic model |
| `vault setup-agent --non-interactive --agent profile-agent --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,memory_agents --language zh-Hant --json` | Generate Profile / Dream / Forgetting agent guidance with report-only and candidate-only defaults |
| `vault setup-agent --non-interactive --agent profile-agent --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,supabase --language zh-Hant --install-optional-deps --supabase-setup simple --supabase-sync cron --remote-reader all --json` | Generate guided Supabase setup, daily sync templates, and shell/n8n/Coze remote reader templates |
| `vault setup-agent --non-interactive --agent profile-agent --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,supabase,memory_agents --agent-roster profile-agent:profile,work-agent:work,remote-agent:remote,n8n:automation --validation-pack all --json` | Generate a multi-agent access matrix plus live Supabase/n8n/Coze validation checklists |
| `vault setup-agent --non-interactive --agent codex --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,supabase --write-stable-venv-script --json` | Generate `agent-install/setup-stable-venv.sh` for reboot-safe scheduled jobs and MCP commands |
| `vault setup-agent --non-interactive --agent automation-agent --scope shared --agent-project-dir ~/Vaults/my-project --features core,mcp,memory_agents --automation-schedule all --automation-mode balanced --json` | Generate cron, LaunchAgent, and n8n templates for report-first memory automation |
| `vault setup-agent --obsidian-vault ~/Documents/ObsidianVault --import-obsidian --obsidian-sync all` | Run first Obsidian import and write cron, LaunchAgent, and n8n templates |

`vault install-agent` is an alias for `vault setup-agent`.
Interactive setup asks before installing optional dependencies. Non-interactive
agents must pass `--install-optional-deps`; semantic model download is opt-in
with `--install-embedding-model zh|en|mix`.
Use `--write-stable-venv-script` for the default long-lived venv path, or
`--stable-venv PATH` when the user chooses a custom stable virtualenv.
Memory-agent guidance is opt-in with `--features memory_agents`; it writes
`README-memory-agents.md` and does not install a model or auto-promote memory.
Supabase sync templates are opt-in with `--supabase-sync cron|launchagent|n8n|all`
and use `python -m scripts.sync_to_supabase --db <project>/vault.db`.
Supabase remote reader templates are opt-in with
`--remote-reader shell|n8n|coze|all`; validate credentials with
`vault remote smoke --agent-id <agent> --json`.
Multi-agent roster templates are opt-in with `--agent-roster`; each entry uses
`agent_id:role[:scope[:max_sensitivity]]`, for example
`profile-agent:profile,work-agent:work,remote-agent:remote,n8n:automation`. Live external validation
files are opt-in with `--validation-pack remote|n8n|coze|all`.
Memory automation schedule files are opt-in with
`--automation-schedule cron|launchagent|n8n|all`; generated jobs default to
`vault automation cycle` and stay report-first unless `--automation-apply` is
explicitly set. Use `--automation-command run` for maintenance-only schedules.
Manual interactive setup asks for `en`, `zh-Hant`, or `zh-CN`; non-interactive
agent installs can pass `--language`. Supabase setup guide generation is opt-in
with `--supabase-setup none|simple|advanced`; keep `simple` as the default path
unless the user asks for RLS or multi-agent permissions.
For MCP remote readers, use `vault-mcp --tool-profile remote` and the sequence
`vault_remote_search` -> `vault_remote_map_show` -> `vault_remote_read_range`
after applying `docs/supabase_read_policy.sql` in Supabase.
Remote IDs can be local integers or Supabase UUIDs; pass the ID returned by
search directly into map/read.
Use `vault remote doctor --agent-id <agent> --json` when search works but
map/read fails, or after applying remote-reader SQL. It returns safe status
checks, counts, and next actions without dumping raw synced content.
For per-tool MCP examples, see `docs/mcp_tool_reference.md`.

## Search And Navigation

| Command | Purpose |
|---|---|
| `vault search "query"` | Search the vault; use `--min-score` to tune weak-match suppression |
| `vault search "query" --json` | Return machine-readable search results for agents, scripts, and automation smoke tests |
| `vault search "query" --graph-expand 2` | Search with graph expansion |
| `vault map build` | Build/backfill Document Map rows |
| `vault map show <id>` | Show a knowledge entry's section map |
| `vault map read <id> --lines 10-30` | Read a bounded source range |
| `vault list` | List knowledge entries |
| `vault remove <id> --confirm` / `vault delete <id> --confirm` | Delete a knowledge entry by ID |
| `vault stats` | Show vault statistics |
| `vault usage stats` / `vault usage archive-expired --apply` | Inspect retrieval usage and archive expired memories without deleting them |

## Quality And Curation

| Command | Purpose |
|---|---|
| `vault lint` | Run quality checks |
| `vault dream` | Produce report-first memory curation summaries |
| `vault candidates --include-gates` | Review candidate-memory queue and gate details before promotion |
| `vault candidate-review <id> --outcome rejected --reason "..."` | Record rejected/blocked candidate feedback without promoting memory |
| `vault capture session <transcript> --write-candidates` | Capture decisions, pitfalls, workflows, and source-of-truth lines from JSONL/Markdown/text transcripts as gated candidates |
| `vault automation plan --write-policy` | Create a policy-based maintenance plan and starter `automation_policy.yaml` |
| `vault automation run` / `vault automation run --apply` | Run report-first memory automation; reports include a dry-run diff and action ledger, and `--apply` only performs policy-allowed reversible actions |
| `vault automation cycle --apply` | Run one safe feedback-to-curation loop: evaluate reviewed candidate outcomes, write `learning_policy.json`, then run policy-based automation so Dream can consume the latest hints |
| `vault automation inbox --limit 5` | Show the shortest read-only review queue across candidates and the latest automation report |
| `vault automation report` / `vault automation eval --write-learning-policy` / `vault automation doctor` | Review automation reports, evaluate candidate-outcome feedback into bounded curation hints, and check scheduled-job readiness |
| `vault freshness` | Experimental freshness/review scheduling |
| `vault usage archive-expired` | Preview TTL-based archive actions; add `--apply` to mark eligible memories archived |
| `vault dedup` | Detect or merge duplicate entries |
| `vault converge` | Experimental convergence/self-questioning check |
| `vault cross-validate` | Experimental cross-model validation |
| `vault search-qa run` / `vault search-qa compare` | Run Search QA snapshots, hard-negative checks, and before/after comparisons |

## Storage And Maintenance

| Command | Purpose |
|---|---|
| `vault doctor` | Check local environment and optional dependencies |
| `vault db status` / `vault db migrate` | Inspect or update local SQLite schema |
| `vault db backup` / `vault db verify-backup` / `vault db restore` | Create, verify, and restore local SQLite backups |
| `vault graph build` / `vault graph show` | Build or inspect the inferred knowledge graph |

## Optional Semantic Workflow

| Command | Purpose |
|---|---|
| `vault install-embedding` | Install a local embedding model |
| `vault config set embedding.provider ollama` | Configure an embedding provider; also supports `openai`, `cohere`, and `voyage` when the matching API key environment variable is set |
| `vault semantic rebuild` | Rebuild semantic vector rows after configuring a real embedding provider |
| `vault semantic rebuild --changed-only --persist-cache` | Refresh only missing or stale semantic vector rows |
| `vault semantic warm` | Precompute QA query embeddings without writing vector rows |
| `vault semantic smoke` | Rebuild, warm, and run a Search QA smoke snapshot |
| `vault semantic cache-stats` / `vault semantic cache-prune` | Inspect or prune the durable embedding cache |
| `vault semantic startup` / `vault semantic daemon` | Run startup or bounded daemon lifecycle hooks |

## Experimental Local Skills

| Command | Purpose |
|---|---|
| `vault skill search "query"` | Search local experimental skill registry entries |

Run `vault <command> --help` for command-specific options.
