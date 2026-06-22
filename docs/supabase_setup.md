# Supabase Setup

Supabase is optional. Vault-for-LLM works locally with SQLite first.

Use Supabase only when you need one of these:

- agents run on different machines
- Coze, n8n, or a hosted workflow needs remote memory reads
- a team wants a synced copy of reviewed project memory

Skip Supabase when one local `vault.db` is enough.

## Simple Sync

1. Create or open a Supabase account.
2. Create one Supabase project for this memory workspace.
3. Open Project Settings -> API.
4. Copy the Project URL into `SUPABASE_URL`.
5. Copy the `service_role` key into `SUPABASE_SERVICE_ROLE_KEY` only on the trusted machine that runs sync jobs.
6. Put those values in the Vault project `.env`, or another reviewed environment source.
7. Create the tables below in the Supabase SQL editor.
8. Run the first sync:

```bash
python -m scripts.sync_to_supabase --db /path/to/project/vault.db --document-map --health
```

Default sync does not upload full `content_raw`. Add `--include-content` only when you intentionally want full local content copied to Supabase.

Privacy gate failures are intentional. Clean the source notes and recompile instead of bypassing the gate.

## Minimal Schema

```sql
create table if not exists vault_knowledge (
  id bigint generated always as identity primary key,
  title text not null,
  layer smallint default 3,
  category text default 'general',
  tags jsonb default '[]'::jsonb,
  trust real default 0.5,
  content_raw text default '',
  content_aaak text default '',
  content_hash text not null,
  summary text default '',
  source text default 'local',
  scope text default 'project',
  sensitivity text default 'low',
  owner_agent text default '',
  allowed_agents jsonb default '[]'::jsonb,
  memory_type text default 'knowledge',
  expires_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  last_synced timestamptz
);

create index if not exists vault_knowledge_title_idx on vault_knowledge (title);
create index if not exists vault_knowledge_content_hash_idx on vault_knowledge (content_hash);

create table if not exists vault_skills (
  id bigint generated always as identity primary key,
  name text not null unique,
  version text default '1.0.0',
  agent_source text default '',
  category text default 'general',
  capabilities jsonb default '[]'::jsonb,
  dependencies jsonb default '[]'::jsonb,
  trust real default 0.5,
  content_raw text default '',
  content_hash text not null,
  description text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  last_synced timestamptz
);

create table if not exists vault_knowledge_nodes (
  id bigint generated always as identity primary key,
  knowledge_id bigint not null,
  node_uid text not null,
  parent_uid text,
  level integer default 0,
  heading text default '',
  path text default '',
  summary text default '',
  line_start integer,
  line_end integer,
  token_estimate integer default 0,
  content_hash text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  knowledge_title text default '',
  knowledge_source text default '',
  knowledge_content_hash text default '',
  unique (knowledge_id, node_uid)
);

create table if not exists vault_knowledge_claims (
  id bigint generated always as identity primary key,
  knowledge_id bigint not null,
  node_uid text not null,
  claim_uid text not null,
  claim text not null,
  claim_type text default '',
  line_start integer,
  line_end integer,
  confidence real default 0,
  source text default '',
  content_hash text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  knowledge_title text default '',
  knowledge_source text default '',
  knowledge_content_hash text default '',
  unique (knowledge_id, claim_uid)
);

create table if not exists vault_health_metrics (
  check_date date primary key,
  total_knowledge integer default 0,
  convergence_rate real default 0,
  avg_freshness real default 0,
  contradiction_count integer default 0,
  gap_count integer default 0,
  created_at timestamptz default now()
);
```

## Agent-Friendly Setup

For a simple guided setup:

```bash
vault setup-agent \
  --non-interactive \
  --agent nancy \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,supabase \
  --install-optional-deps \
  --supabase-setup simple \
  --supabase-sync cron \
  --remote-reader all \
  --json
```

For Traditional Chinese output:

```bash
vault setup-agent \
  --non-interactive \
  --agent nancy \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,supabase \
  --language zh-Hant \
  --supabase-setup simple \
  --json
```

Manual interactive installs ask for the setup language. Agent/non-interactive installs should pass `--language` or use the default English output.

`--remote-reader shell|n8n|coze|all` generates a reader package under
`agent-install/` after Supabase is selected. Use it when Coze, n8n, or an agent
on another host needs read-only access to reviewed memory summaries.

After applying `docs/supabase_read_policy.sql`, verify the remote reader path:

```bash
export SUPABASE_URL=https://YOUR_PROJECT.supabase.co
export SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
vault remote smoke --agent-id coco --query "deployment SOP" --json
```

## Advanced RLS

Do not give `SUPABASE_SERVICE_ROLE_KEY` to normal agents, Coze, n8n, or browser clients. The service role bypasses RLS.

Recommended shape:

- sync jobs or backend functions may use the service role
- normal agents use read-only APIs, RPC, Edge Functions, or RLS-backed JWTs
- private raw memory stays local or owner-only
- shared project knowledge can be readable by trusted project agents
- medium-sensitivity summaries require an allow-list such as `allowed_agents`
- normal agents can propose candidates but should not directly write active shared memory

Possible extra columns for a shared-memory table or view:

```sql
alter table vault_knowledge add column if not exists owner_agent text default 'unknown';
alter table vault_knowledge add column if not exists scope text default 'project';
alter table vault_knowledge add column if not exists sensitivity text default 'low';
alter table vault_knowledge add column if not exists allowed_agents jsonb default '[]'::jsonb;
alter table vault_knowledge add column if not exists memory_type text default 'knowledge';
alter table vault_knowledge add column if not exists status text default 'active';
alter table vault_knowledge add column if not exists expires_at timestamptz;
```

Keep raw private conversations and shareable summaries in separate tables, views, or RPC responses. RLS is row-level, not a substitute for separating unsafe columns from safe fields.

For a ready-to-paste read-only starting point, use
[`docs/supabase_read_policy.sql`](supabase_read_policy.sql). It creates a
`vault_search_readable` RPC for hosted readers. The RPC applies
`scope` / `sensitivity` / `owner_agent` / `allowed_agents` / `expires_at`
filters and returns safe metadata plus summaries only. It does not return raw
full text; keep authoritative citations on local `vault_read_range` unless you
intentionally design a separate reviewed content API.

`vault setup-agent --supabase-setup advanced` also writes the same SQL to
`agent-install/supabase-read-policy.sql` beside the generated setup guide.

Treat `layer` as memory depth, not access control:

- `L0` is minimal identity and should usually stay private.
- `L1` can include stable work preferences and reviewed project contracts.
- `L2` can include recent state or handoff summaries, preferably with `expires_at`.
- `L3` is best for low-sensitivity shared SOPs, architecture notes, fixes, and lessons.

For user personality/profile memory, sync only reviewed summaries unless the
user explicitly approves wider sharing. Raw private chats, deep psychological
analysis, persona files, and high-sensitivity notes should stay in a private
vault or owner-only table. See [memory governance layers](memory_governance.md).
