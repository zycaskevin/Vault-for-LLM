-- Guardrails Document Map Sprint 4B remote read target schema.
-- Local SQLite remains the source of truth; these Supabase tables are sync/read targets only.
-- Apply manually in Supabase SQL editor/CLI before running scripts/sync_to_supabase.py --document-map.

create extension if not exists pgcrypto;

create table if not exists public.guardrails_knowledge_nodes (
    id uuid primary key default gen_random_uuid(),
    knowledge_id bigint not null,
    node_uid text not null,
    parent_uid text,
    level integer not null,
    heading text not null default '',
    path text not null default '',
    summary text,
    line_start integer not null,
    line_end integer not null,
    token_estimate integer,
    content_hash text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    knowledge_title text,
    knowledge_source text,
    knowledge_content_hash text,
    constraint guardrails_knowledge_nodes_natural_key unique (knowledge_id, node_uid),
    constraint guardrails_knowledge_nodes_line_bounds check (line_start > 0 and line_end >= line_start)
);

comment on table public.guardrails_knowledge_nodes is
    'Guardrails Document Map nodes synced from local SQLite. SQLite remains source of truth; Supabase is read/sync target only.';
comment on column public.guardrails_knowledge_nodes.knowledge_id is
    'Local SQLite knowledge.id copied for remote navigation; not authoritative in Supabase.';

create index if not exists idx_guardrails_knowledge_nodes_knowledge_id
    on public.guardrails_knowledge_nodes (knowledge_id);
create index if not exists idx_guardrails_knowledge_nodes_knowledge_line
    on public.guardrails_knowledge_nodes (knowledge_id, line_start, line_end);
create index if not exists idx_guardrails_knowledge_nodes_content_hash
    on public.guardrails_knowledge_nodes (knowledge_content_hash);

alter table public.guardrails_knowledge_nodes enable row level security;

drop policy if exists agents_rw on public.guardrails_knowledge_nodes;
create policy agents_rw on public.guardrails_knowledge_nodes
    for all
    using (true)
    with check (true);

create table if not exists public.guardrails_knowledge_claims (
    id uuid primary key default gen_random_uuid(),
    knowledge_id bigint not null,
    node_uid text,
    claim_uid text not null,
    claim text not null default '',
    claim_type text,
    line_start integer not null,
    line_end integer not null,
    confidence double precision,
    source text,
    content_hash text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    knowledge_title text,
    knowledge_source text,
    knowledge_content_hash text,
    constraint guardrails_knowledge_claims_natural_key unique (knowledge_id, claim_uid),
    constraint guardrails_knowledge_claims_line_bounds check (line_start > 0 and line_end >= line_start)
);

comment on table public.guardrails_knowledge_claims is
    'Guardrails Document Map claims synced from local SQLite. SQLite remains source of truth; Supabase is read/sync target only.';
comment on column public.guardrails_knowledge_claims.knowledge_id is
    'Local SQLite knowledge.id copied for remote navigation; not authoritative in Supabase.';

create index if not exists idx_guardrails_knowledge_claims_knowledge_id
    on public.guardrails_knowledge_claims (knowledge_id);
create index if not exists idx_guardrails_knowledge_claims_node_uid
    on public.guardrails_knowledge_claims (knowledge_id, node_uid);
create index if not exists idx_guardrails_knowledge_claims_knowledge_line
    on public.guardrails_knowledge_claims (knowledge_id, line_start, line_end);
create index if not exists idx_guardrails_knowledge_claims_content_hash
    on public.guardrails_knowledge_claims (knowledge_content_hash);

alter table public.guardrails_knowledge_claims enable row level security;

drop policy if exists agents_rw on public.guardrails_knowledge_claims;
create policy agents_rw on public.guardrails_knowledge_claims
    for all
    using (true)
    with check (true);
