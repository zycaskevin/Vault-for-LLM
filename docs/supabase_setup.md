# Supabase Setup

Supabase is optional. Vault-for-LLM starts as a local SQLite memory vault and
does not need a hosted database for normal single-machine use.

Add Supabase when the memory needs to cross a machine or runtime boundary:

- different agents run on different computers
- Coze, n8n, or another hosted workflow needs remote reads
- remote agents need to submit reviewable memory candidates back to the local
  vault owner
- a team wants a synced copy of reviewed project memory
- a mobile, home, robot, or other future interface should read the same
  approved memory layer

Skip Supabase when one local `vault.db` is enough.

## Simple Path

For most users, start here.

1. Create or open a Supabase account.
2. Create one Supabase project for this memory workspace.
3. Open **Project Settings -> API**.
4. Copy the Project URL into `SUPABASE_URL`.
5. Copy the `service_role` key into `SUPABASE_SERVICE_ROLE_KEY` only on the
   trusted machine that runs sync jobs.
6. Put those values in the Vault project `.env`, or another reviewed
   environment source.
7. Create the tables from the schema below in the Supabase SQL editor.
8. Run the first sync:

```bash
python -m scripts.sync_to_supabase --db /path/to/project/vault.db --document-map --health
```

For near-realtime freshness on a trusted local machine:

```bash
vault setup-agent \
  --features core,mcp,supabase \
  --supabase-sync realtime \
  --agent-project-dir /path/to/project

/path/to/project/agent-install/supabase-realtime-sync.sh
```

The realtime template watches local `vault.db`, waits for a short quiet period,
then runs the same local-to-Supabase sync. It writes
`reports/supabase-sync-latest.json` so `vault remote status` and Agent
dashboards can tell whether the remote copy is fresh.

This is not bidirectional active-knowledge sync. Supabase remains a reviewed
memory read copy, plus an optional candidate request inbox. Keep
`SUPABASE_SERVICE_ROLE_KEY` only on the trusted sync host, never inside Coze,
browser clients, mobile clients, or public workflow endpoints.

When remote hosts need to contribute memory, use candidate sync instead of
direct active-memory writes:

```bash
vault remote submit-candidate \
  --from-agent hosted-agent \
  --title "Deployment lesson" \
  --content "..." \
  --trust 0.8

vault remote pull-candidates --apply --json
vault sync conflicts --json
vault sync audit --json
```

This creates a local audit trail and can detect simple conflicts before a
reviewed candidate becomes active knowledge. It is the safe bidirectional path:
remote machines can suggest memory, while the trusted local vault remains the
source of truth.

Default sync does not upload full `content_raw`. Add `--include-content` only
when the user intentionally wants full local content copied to Supabase.

Privacy gate failures are expected. Clean the source note and recompile instead
of bypassing the gate.

## Multi-Host Roadmap Boundary

Vault currently supports three separate sharing modes:

| Mode | Status | What it means |
|---|---|---|
| Local shared vault | usable | Agents on the same machine can point to the same `vault.db` and use local governance filters. |
| Supabase read copy | usable | Reviewed local knowledge can be pushed to Supabase for remote read-only access. |
| Remote candidate inbox | usable-alpha | Remote hosts can submit candidate requests; a trusted host pulls them into local review. |

The first multi-host safety surface is local revision/conflict/audit tracking.
`vault sync revisions`, `vault sync conflicts`, and `vault sync audit` show what
remote candidates arrived, what changed locally, and what needs a human or
trusted agent decision.

True multi-master active-knowledge writing is not enabled yet. That future
phase needs a stronger revision graph, conflict resolver, rollback plan, and
audit policy before multiple machines can safely overwrite reviewed knowledge.

## Agent-Guided Setup

When an agent is doing the install, prefer this simple generator:

```bash
vault setup-agent \
  --non-interactive \
  --agent work-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase \
  --install-optional-deps \
  --supabase-setup simple \
  --supabase-sync cron \
  --remote-reader all \
  --validation-pack all \
  --json
```

For Traditional Chinese output:

```bash
vault setup-agent \
  --non-interactive \
  --agent work-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase \
  --language zh-Hant \
  --supabase-setup simple \
  --json
```

Manual interactive installs ask for setup language. Agent and scripted installs
should pass `--language` explicitly or use the default English output.

## Minimal Schema

The minimal schema below uses integer IDs because it mirrors local SQLite sync.
If your Supabase project already uses UUID primary keys, keep your schema and
apply `docs/supabase_read_policy.sql`; the guarded reader RPCs compare IDs as
text and support either integer IDs or UUIDs.

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
  status text default 'active',
  expires_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  last_synced timestamptz
);

create index if not exists vault_knowledge_title_idx on vault_knowledge (title);
create index if not exists vault_knowledge_content_hash_idx on vault_knowledge (content_hash);
create index if not exists vault_knowledge_scope_idx on vault_knowledge (scope);
create index if not exists vault_knowledge_sensitivity_idx on vault_knowledge (sensitivity);

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

## Remote Readers

Use remote readers when Coze, n8n, a shell script, or an agent on another host
needs read-only access to reviewed memory summaries:

```bash
vault setup-agent \
  --non-interactive \
  --agent remote-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase \
  --remote-reader all \
  --validation-pack all \
  --json
```

This writes:

- `README-remote-reader.md`
- `remote-reader.env.example`
- `remote-reader-smoke.sh`
- `n8n-remote-reader.workflow.json`
- `coze-supabase-vault-openapi.json`
- `README-live-validation.md`
- `VALIDATE-n8n.md`
- `VALIDATE-coze.md`

After applying `docs/supabase_read_policy.sql`, verify the remote reader path:

```bash
export SUPABASE_URL=https://YOUR_PROJECT.supabase.co
export SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
vault remote status --json
vault remote smoke --agent-id remote-agent --query "deployment SOP" --json
vault remote doctor --agent-id remote-agent --query "deployment SOP" --json
```

`vault remote status` is an offline safety check. It confirms that the local
SQLite vault remains the source of truth, Supabase is a reviewed read copy plus
candidate request inbox, active memory sync is not real-time bidirectional, and
remote freshness is unknown unless a local sync report exists. `vault remote
smoke` checks the basic search RPC. `vault remote doctor` checks the full
remote-reader path: search, readable-entry RPCs,
Document Map nodes, claims, content access, map, and bounded read. It returns
status checks and next actions without printing raw synced content.

Remote readers must not receive `SUPABASE_SERVICE_ROLE_KEY`.

## Safe Candidate Requests

Phase 1 bidirectional sync is candidate-first. A remote host can propose memory,
but it cannot directly write active knowledge.

Remote or hosted agent:

```bash
export SUPABASE_URL=https://YOUR_PROJECT.supabase.co
export SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
vault remote submit-candidate \
  --from-agent remote-agent \
  --title "Deployment lesson" \
  --content "The deploy workflow should run smoke tests before publishing." \
  --reason "Observed during the remote deploy session" \
  --trust 0.75 \
  --scope shared \
  --sensitivity low \
  --json
```

Trusted local sync host:

```bash
export SUPABASE_URL=https://YOUR_PROJECT.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
vault remote pull-candidates --limit 20 --json
vault remote pull-candidates --limit 20 --apply --json
```

`pull-candidates --apply` writes to local `memory_candidates`, not
`knowledge`. The normal candidate gates decide whether the item is clean enough
to review, and `vault promote <candidate_id> --confirm` is still the step that
turns reviewed memory into active knowledge.

If the local trusted host has explicitly enabled low-risk auto-promotion in
`automation_policy.yaml`, it can merge only this pull's low-risk candidates:

```yaml
auto_promote_low_risk_candidates: true
auto_promote_allowed_sources:
  - remote_write_request
auto_promote_allowed_memory_types:
  - remote_candidate
auto_promote_allowed_scopes:
  - shared
auto_promote_allowed_sensitivities:
  - low
auto_promote_min_trust: 0.8
auto_promote_requires_source_ref: true
```

Then run:

```bash
vault remote pull-candidates --apply --auto-promote-low-risk --json
```

This still runs the local privacy, duplicate, metadata, and quality gates. It
only promotes candidates imported by that pull, and leaves low-trust,
conflicting, sensitive, or weak candidates in the review queue.

The SQL in `docs/supabase_read_policy.sql` creates
`vault_memory_write_requests` and the guarded `vault_submit_memory_request`
RPC. Hosted agents can execute the RPC with anon/authenticated credentials but
cannot read or update the request table directly.

## Advanced RLS

Use advanced RLS only after the simple path is working.

Advanced setup is for users who need any of these:

- multiple agents with different read boundaries
- Coze or n8n read-only access
- sensitivity-based sharing
- private profile summaries mixed with shared project knowledge
- owner-only or allow-list memory reads

Generate the advanced setup pack:

```bash
vault setup-agent \
  --non-interactive \
  --agent profile-agent \
  --scope shared \
  --agent-project-dir ~/Vaults/project-memory \
  --features core,mcp,supabase,memory_agents \
  --supabase-setup advanced \
  --remote-reader all \
  --agent-roster profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation \
  --validation-pack all \
  --json
```

Recommended policy shape:

- sync jobs or backend functions may use the service role
- normal agents use read-only APIs, RPC, Edge Functions, or RLS-backed JWTs
- private raw memory stays local or owner-only
- shared project knowledge is readable by trusted project agents
- medium-sensitivity summaries require `allowed_agents`
- normal agents can propose candidates but should not directly write active
  shared memory

Do not give `SUPABASE_SERVICE_ROLE_KEY` to normal agents, Coze, n8n, browser
clients, or mobile apps. The service role bypasses RLS.

Use metadata for access decisions:

```sql
alter table vault_knowledge add column if not exists owner_agent text default 'unknown';
alter table vault_knowledge add column if not exists scope text default 'project';
alter table vault_knowledge add column if not exists sensitivity text default 'low';
alter table vault_knowledge add column if not exists allowed_agents jsonb default '[]'::jsonb;
alter table vault_knowledge add column if not exists memory_type text default 'knowledge';
alter table vault_knowledge add column if not exists status text default 'active';
alter table vault_knowledge add column if not exists expires_at timestamptz;
```

For a ready-to-paste read-only starting point, use
[`docs/supabase_read_policy.sql`](supabase_read_policy.sql). It creates a
`vault_search_readable` RPC for hosted readers. The RPC applies
`scope` / `sensitivity` / `owner_agent` / `allowed_agents` / `expires_at`
filters and returns safe metadata plus summaries only. It does not return raw
full text.

RLS is row-level. It is not a substitute for separating unsafe columns from safe
fields. Keep raw private conversations and shareable summaries in separate
tables, views, or RPC responses when the boundary matters.

## Layer Guidance

Treat `layer` as memory depth, not access control:

- `L0` is minimal identity and should usually stay private.
- `L1` can include stable work preferences and reviewed project contracts.
- `L2` can include recent state or handoff summaries, preferably with
  `expires_at`.
- `L3` is best for low-sensitivity shared SOPs, architecture notes, fixes, and
  lessons.

For user personality/profile memory, sync only reviewed summaries unless the
user explicitly approves wider sharing. Raw private chats, deep psychological
analysis, persona files, and high-sensitivity notes should stay in a private
vault or owner-only table.

See [memory governance layers](memory_governance.md).
