# P0/A1 Public String Audit

Generated: 2026-05-17T01:46:18Z
Workspace: `/home/zycas/Vault-for-LLM`
Scope: tracked files only. Product code was not modified.

## Result

FAIL for public-release readiness: the repository has no obvious leaked secrets or user filesystem paths in tracked files, but it still contains public-unsuitable internal/product-specific strings and assumptions that should be remediated before treating the repo as fully neutral public OSS.

Blockers: none for completing this audit. Remediation should be handled in follow-up code/doc cleanup tasks.

## Findings

| Term / pattern | Path(s) | Severity | Recommendation |
|---|---|---:|---|
| `hermes_vault_health`, `Dashboard`, `dashboard health snapshot` | `scripts/sync_to_supabase.py:11`, `scripts/sync_to_supabase.py:38`, `scripts/sync_to_supabase.py:460-494`, `scripts/sync_to_supabase.py:536`; `vault/health.py:4`; `tests/test_vault_health_metrics.py:1,37` | High | Split public Supabase sync from private dashboard-health sync. Make remote health-table names configurable and neutral, or move dashboard-specific integration into a private/optional adapter. Avoid exposing the `hermes_` table name in public defaults/tests. |
| `gr_entities`, `gr_edges`, `gr_entity_knowledge` | `scripts/fix_ek_links.py:2,36,46,99,107,122,127`; `scripts/sync_graph_to_supabase.py:83,98,137,201,255`; `tests/test_e2e.py:273,280,285`; `scripts/auto_backlink.py:37` | High | Replace hard-coded private graph table prefixes with public Vault names or a config/env mapping. If these are legacy/private schema names, document them as migration-only or move scripts out of the public default path. |
| `Hermes`, `Hermes Agent`, `Hermes Hard Hooks` | `raw/20260427-agent-harness-architecture.md:92-103`; `scripts/auto_backlink.py:41-42,112`; `tests/test_e2e.py:47`; `docs/agent_memory_qa_roadmap.md:229` | Medium | Neutralize product-specific examples to `Example Agent` / `Vault Agent`, or mark them explicitly as third-party examples. Public raw/example content should not look like it requires the Hermes product/runtime. |
| `hermes-main`, `~/.hermes/skills/<name>` | `vault/cli.py:823,837,902-903,1376` | Medium | Change the default skill source and local skill path to Vault-neutral values, or make them configurable. `~/.hermes` and `hermes-main` make the public CLI appear coupled to a private agent runtime. |
| `holographic memory`, `delegate_task fallback` sample knowledge | `tests/test_e2e.py:47-48` | Low | Replace test fixture text with product-neutral Vault examples. The current strings are not secrets, but they encode another agent system's terminology into public examples. |
| Personal GitHub owner `zycaskevin` in clone instructions | `README.md:138`; `README.zh-CN.md:138`; `README.zh-Hant.md:138` | Low | If this is the intended canonical public repository owner, this is acceptable. If the release should be organization-neutral, replace with the public org/repo URL or a placeholder like `your-org/Vault-for-LLM`. |
| `raw/20260427-agent-harness-architecture.md` real raw knowledge note | `raw/20260427-agent-harness-architecture.md:1-123` | Medium | Decide whether real raw vault content should ship in the public repo. If kept, label it as a sanitized example. Otherwise replace it with synthetic sample knowledge to avoid shipping operational/personal research notes as defaults. |
| `localhost`, `127.0.0.1`, `http://localhost:11434` defaults | `scripts/convergence_check.py:17`; `scripts/cross_validate.py:47`; `vault/cli.py:408`; `vault/embed.py:176,280,301`; `vault/importer.py:70,469,682`; `vault/llm.py:65` | Allow / Low | These are normal local-first defaults for Ollama/vLLM and are public-suitable. Keep them, but ensure public docs describe them as local optional services, not deployed infrastructure. |
| Environment variable names for API keys | `scripts/convergence_check.py:370-371,380`; `scripts/cross_validate.py:69-87`; `vault/llm.py:171-242`; `vault/cli.py:1183,1441` | Allow / Low | No literal secret values were found. Keep environment-variable based configuration; maintain CI secret scanning and avoid committing `.env` files. |

## Verification commands run

```sh
git status --short
git grep -n -I -E '(/home/|/Users/|C:\\|D:\\|/mnt/[a-z]/|Desktop|Downloads|Documents|zycas|LAPTOP|localhost|127\.0\.0\.1|0\.0\.0\.0)' -- . ':!docs/p0_public_string_audit.md'
git grep -n -I -E '(TODO|FIXME|HACK|XXX|INTERNAL|internal|private|secret|token|password|api[_-]?key|credential|dashboard|Notion|Airtable|Google|OpenAI|Anthropic|Slack|Discord|Telegram|元宝|Yuanbao)' -- . ':!docs/p0_public_string_audit.md'
git grep -n -I -E 'Hermes|hermes|Guardrails|guardrails|Dashboard|dashboard|Holographic|holographic|Supabase|supabase|zycas|zycaskevin|Kevin|\.hermes|hermes_' -- . ':!docs/p0_public_string_audit.md'
git grep -n -I -E '(/home/[[:alnum:]_.-]+|/Users/[[:alnum:]_.-]+|/mnt/[a-z]/|C:\\Users|D:\\|LAPTOP-[A-Za-z0-9]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})' -- . ':!docs/p0_public_string_audit.md'
git grep -n -I -E '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{20,}|password[[:space:]]*=|secret[[:space:]]*=|api[_-]?key[[:space:]]*=)' -- . ':!docs/p0_public_string_audit.md'
git grep -n -I -E 'gr_[A-Za-z0-9_]+' -- . ':!docs/p0_public_string_audit.md'
git grep -n -I -E 'hermes_vault|Hermes|holographic memory|delegate_task|\.hermes|hermes-main' -- tests vault scripts raw templates docs README.md README.zh-CN.md README.zh-Hant.md SCHEMA.md PROGRESS.md AUDIT_REPORT.md
git grep -n -I -E 'dashboard|Dashboard|health snapshot|health sync' -- scripts vault tests docs README.md README.zh-CN.md README.zh-Hant.md SCHEMA.md PROGRESS.md AUDIT_REPORT.md supabase
git status --short
```

## Notes

- The secret-pattern scan returned only parameter names / environment-variable references, not literal credentials.
- The path/person scan returned no local absolute home paths or email addresses. The only personal-looking owner string was the public GitHub clone URL owner `zycaskevin`.
- Supabase itself is documented as optional in public docs; the main remaining risk is hard-coded table/schema naming and dashboard-health coupling.

## A2 remediation notes

- `raw/20260427-agent-harness-architecture.md` was replaced with a synthetic public-safe example note, preserving the harness concept without shipping private operational memory.
- Product-specific example strings in `tests/test_e2e.py`, `tests/test_vault_health_metrics.py`, `scripts/auto_backlink.py`, and `vault/cli.py` were neutralized where they were acting as default/test/example content.
- Supabase dashboard/table-name coupling remains intentionally out of scope for A2 and should be handled by A3.

## A3 remediation notes

- Public Supabase sync now uses Vault-branded default table names for health and graph tables, with `VAULT_SUPABASE_*_TABLE` environment-variable overrides for existing private schemas.
- Optional Supabase scripts now guard the Supabase client import so local SQLite-first usage can import modules without the optional dependency installed.
- Public README files explicitly state that SQLite remains the source of truth and Supabase is only an optional sync/read target.

## A4 remediation notes

- Decision: keep `vault skill` visible, but position it as a product-neutral, experimental local skill registry rather than a hosted or mature marketplace.
- CLI help/output now uses local-registry wording while retaining neutral defaults (`vault-cli`, `VAULT_SKILLS_DIR`, `~/.vault/skills`).
- README variants now describe `vault skill` as local-only/experimental and no longer present it as a skill marketplace headline.
