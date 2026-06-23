-- Vault-for-LLM advanced Supabase read policy
-- Paste this into the Supabase SQL editor after creating the minimal tables.
-- Keep SUPABASE_SERVICE_ROLE_KEY only on trusted sync hosts. Hosted agents
-- should call vault_search_readable with anon/authenticated credentials.

alter table public.vault_knowledge add column if not exists scope text default 'project';
alter table public.vault_knowledge add column if not exists sensitivity text default 'low';
alter table public.vault_knowledge add column if not exists owner_agent text default '';
alter table public.vault_knowledge add column if not exists allowed_agents jsonb default '[]'::jsonb;
alter table public.vault_knowledge add column if not exists memory_type text default 'knowledge';
alter table public.vault_knowledge add column if not exists status text default 'active';
alter table public.vault_knowledge add column if not exists expires_at timestamptz;

create index if not exists vault_knowledge_scope_idx on public.vault_knowledge (scope);
create index if not exists vault_knowledge_sensitivity_idx on public.vault_knowledge (sensitivity);
create index if not exists vault_knowledge_owner_agent_idx on public.vault_knowledge (owner_agent);

create or replace function public.vault_sensitivity_rank(value text)
returns integer
language sql
immutable
as $$
  select case coalesce(lower(value), 'low')
    when 'low' then 0
    when 'medium' then 1
    when 'high' then 2
    when 'restricted' then 3
    else 0
  end
$$;

create or replace function public.vault_is_readable(
  p_scope text,
  p_sensitivity text,
  p_owner_agent text,
  p_allowed_agents jsonb,
  p_status text,
  p_expires_at timestamptz,
  p_agent_id text default '',
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns boolean
language sql
stable
as $$
  select coalesce(p_status, 'active') in ('active', 'reviewed')
    and (p_expires_at is null or p_expires_at > now())
    and public.vault_sensitivity_rank(p_sensitivity)
      <= public.vault_sensitivity_rank(p_max_sensitivity)
    and (
      coalesce(p_scope, 'project') <> 'private'
      or (
        p_include_private
        and coalesce(p_agent_id, '') <> ''
        and (
          coalesce(p_owner_agent, '') = p_agent_id
          or coalesce(p_allowed_agents, '[]'::jsonb) ? p_agent_id
        )
      )
    )
    and (
      coalesce(p_sensitivity, 'low') <> 'restricted'
      or (
        coalesce(p_agent_id, '') <> ''
        and (
          coalesce(p_owner_agent, '') = p_agent_id
          or coalesce(p_allowed_agents, '[]'::jsonb) ? p_agent_id
        )
      )
    )
$$;

create or replace function public.vault_search_readable(
  p_agent_id text default '',
  p_query text default '',
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium',
  p_limit integer default 20
)
returns table (
  id bigint,
  title text,
  layer smallint,
  category text,
  tags jsonb,
  trust real,
  summary text,
  source text,
  scope text,
  sensitivity text,
  owner_agent text,
  allowed_agents jsonb,
  memory_type text,
  expires_at timestamptz,
  updated_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select
    k.id,
    k.title,
    k.layer,
    k.category,
    k.tags,
    k.trust,
    k.summary,
    k.source,
    coalesce(k.scope, 'project') as scope,
    coalesce(k.sensitivity, 'low') as sensitivity,
    coalesce(k.owner_agent, '') as owner_agent,
    coalesce(k.allowed_agents, '[]'::jsonb) as allowed_agents,
    coalesce(k.memory_type, 'knowledge') as memory_type,
    k.expires_at,
    k.updated_at
  from public.vault_knowledge k
  where public.vault_is_readable(
      k.scope,
      k.sensitivity,
      k.owner_agent,
      k.allowed_agents,
      k.status,
      k.expires_at,
      p_agent_id,
      p_include_private,
      p_max_sensitivity
    )
    and (
      coalesce(p_query, '') = ''
      or k.title ilike '%' || p_query || '%'
      or k.summary ilike '%' || p_query || '%'
      or k.source ilike '%' || p_query || '%'
    )
  order by k.updated_at desc nulls last, k.id desc
  limit greatest(1, least(coalesce(p_limit, 20), 100));
$$;

create or replace function public.vault_get_readable(
  p_agent_id text default '',
  p_knowledge_id bigint default 0,
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  id bigint,
  title text,
  scope text,
  sensitivity text,
  owner_agent text,
  allowed_agents jsonb,
  memory_type text,
  expires_at timestamptz,
  updated_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select
    k.id,
    k.title,
    coalesce(k.scope, 'project') as scope,
    coalesce(k.sensitivity, 'low') as sensitivity,
    coalesce(k.owner_agent, '') as owner_agent,
    coalesce(k.allowed_agents, '[]'::jsonb) as allowed_agents,
    coalesce(k.memory_type, 'knowledge') as memory_type,
    k.expires_at,
    k.updated_at
  from public.vault_knowledge k
  where k.id = p_knowledge_id
    and public.vault_is_readable(
      k.scope,
      k.sensitivity,
      k.owner_agent,
      k.allowed_agents,
      k.status,
      k.expires_at,
      p_agent_id,
      p_include_private,
      p_max_sensitivity
    )
  limit 1;
$$;

create or replace function public.vault_nodes_readable(
  p_agent_id text default '',
  p_knowledge_id bigint default 0,
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  knowledge_id bigint,
  node_uid text,
  parent_uid text,
  level integer,
  heading text,
  path text,
  summary text,
  line_start integer,
  line_end integer,
  token_estimate integer,
  content_hash text,
  knowledge_title text,
  knowledge_source text,
  knowledge_content_hash text
)
language sql
stable
security definer
set search_path = public
as $$
  select
    n.knowledge_id,
    n.node_uid,
    n.parent_uid,
    n.level,
    n.heading,
    n.path,
    n.summary,
    n.line_start,
    n.line_end,
    n.token_estimate,
    n.content_hash,
    n.knowledge_title,
    n.knowledge_source,
    n.knowledge_content_hash
  from public.vault_knowledge_nodes n
  join public.vault_knowledge k on k.id = n.knowledge_id
  where n.knowledge_id = p_knowledge_id
    and public.vault_is_readable(
      k.scope,
      k.sensitivity,
      k.owner_agent,
      k.allowed_agents,
      k.status,
      k.expires_at,
      p_agent_id,
      p_include_private,
      p_max_sensitivity
    )
  order by n.line_start, n.level, n.id;
$$;

create or replace function public.vault_claims_readable(
  p_agent_id text default '',
  p_knowledge_id bigint default 0,
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  knowledge_id bigint,
  node_uid text,
  claim_uid text,
  claim text,
  claim_type text,
  line_start integer,
  line_end integer,
  confidence real,
  source text,
  content_hash text,
  knowledge_title text,
  knowledge_source text,
  knowledge_content_hash text
)
language sql
stable
security definer
set search_path = public
as $$
  select
    c.knowledge_id,
    c.node_uid,
    c.claim_uid,
    c.claim,
    c.claim_type,
    c.line_start,
    c.line_end,
    c.confidence,
    c.source,
    c.content_hash,
    c.knowledge_title,
    c.knowledge_source,
    c.knowledge_content_hash
  from public.vault_knowledge_claims c
  join public.vault_knowledge k on k.id = c.knowledge_id
  where c.knowledge_id = p_knowledge_id
    and public.vault_is_readable(
      k.scope,
      k.sensitivity,
      k.owner_agent,
      k.allowed_agents,
      k.status,
      k.expires_at,
      p_agent_id,
      p_include_private,
      p_max_sensitivity
    )
  order by c.line_start, c.line_end, c.claim_uid;
$$;

create or replace function public.vault_content_readable(
  p_agent_id text default '',
  p_knowledge_id bigint default 0,
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  title text,
  content_raw text,
  content_hash text
)
language sql
stable
security definer
set search_path = public
as $$
  select
    k.title,
    k.content_raw,
    k.content_hash
  from public.vault_knowledge k
  where k.id = p_knowledge_id
    and public.vault_is_readable(
      k.scope,
      k.sensitivity,
      k.owner_agent,
      k.allowed_agents,
      k.status,
      k.expires_at,
      p_agent_id,
      p_include_private,
      p_max_sensitivity
    )
  limit 1;
$$;

alter table public.vault_knowledge enable row level security;
alter table public.vault_knowledge_nodes enable row level security;
alter table public.vault_knowledge_claims enable row level security;
revoke all on table public.vault_knowledge from anon, authenticated;
revoke all on table public.vault_knowledge_nodes from anon, authenticated;
revoke all on table public.vault_knowledge_claims from anon, authenticated;
revoke all on function public.vault_is_readable(text, text, text, jsonb, text, timestamptz, text, boolean, text) from public;
revoke all on function public.vault_search_readable(text, text, boolean, text, integer) from public;
revoke all on function public.vault_get_readable(text, bigint, boolean, text) from public;
revoke all on function public.vault_nodes_readable(text, bigint, boolean, text) from public;
revoke all on function public.vault_claims_readable(text, bigint, boolean, text) from public;
revoke all on function public.vault_content_readable(text, bigint, boolean, text) from public;
grant execute on function public.vault_search_readable(text, text, boolean, text, integer) to anon, authenticated;
grant execute on function public.vault_get_readable(text, bigint, boolean, text) to anon, authenticated;
grant execute on function public.vault_nodes_readable(text, bigint, boolean, text) to anon, authenticated;
grant execute on function public.vault_claims_readable(text, bigint, boolean, text) to anon, authenticated;
grant execute on function public.vault_content_readable(text, bigint, boolean, text) to anon, authenticated;
