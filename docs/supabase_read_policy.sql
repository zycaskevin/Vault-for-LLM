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

create table if not exists public.vault_memory_write_requests (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  status text not null default 'submitted',
  idempotency_key text not null default '',
  from_agent text not null default '',
  title text not null,
  content text not null,
  reason text not null default '',
  category text not null default 'general',
  tags jsonb not null default '[]'::jsonb,
  trust real not null default 0.5,
  scope text not null default 'project',
  sensitivity text not null default 'low',
  owner_agent text not null default '',
  allowed_agents jsonb not null default '[]'::jsonb,
  memory_type text not null default 'remote_candidate',
  source_ref text not null default '',
  local_candidate_id text not null default '',
  error text not null default ''
);

create index if not exists vault_memory_write_requests_status_idx
  on public.vault_memory_write_requests (status, created_at);
create index if not exists vault_memory_write_requests_from_agent_idx
  on public.vault_memory_write_requests (from_agent, created_at);
create unique index if not exists vault_memory_write_requests_idempotency_idx
  on public.vault_memory_write_requests (idempotency_key)
  where idempotency_key <> '';

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

drop function if exists public.vault_search_readable(text, text, boolean, text, integer);
drop function if exists public.vault_get_readable(text, bigint, boolean, text);
drop function if exists public.vault_nodes_readable(text, bigint, boolean, text);
drop function if exists public.vault_claims_readable(text, bigint, boolean, text);
drop function if exists public.vault_content_readable(text, bigint, boolean, text);
drop function if exists public.vault_get_readable(text, text, boolean, text);
drop function if exists public.vault_nodes_readable(text, text, boolean, text);
drop function if exists public.vault_claims_readable(text, text, boolean, text);
drop function if exists public.vault_content_readable(text, text, boolean, text);
drop function if exists public.vault_submit_memory_request(text, text, text, text, text, jsonb, text, text, text, jsonb, text, text, text);
drop function if exists public.vault_submit_memory_request(text, text, text, text, text, jsonb, real, text, text, text, jsonb, text, text, text);

create or replace function public.vault_submit_memory_request(
  p_title text,
  p_content text,
  p_reason text default '',
  p_from_agent text default '',
  p_category text default 'general',
  p_tags jsonb default '[]'::jsonb,
  p_trust real default 0.5,
  p_scope text default 'project',
  p_sensitivity text default 'low',
  p_owner_agent text default '',
  p_allowed_agents jsonb default '[]'::jsonb,
  p_memory_type text default 'remote_candidate',
  p_source_ref text default '',
  p_idempotency_key text default ''
)
returns table (
  id text,
  status text,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
  v_status text;
  v_created_at timestamptz;
  v_scope text := lower(coalesce(p_scope, 'project'));
  v_sensitivity text := lower(coalesce(p_sensitivity, 'low'));
  v_tags jsonb := case when jsonb_typeof(coalesce(p_tags, '[]'::jsonb)) = 'array' then coalesce(p_tags, '[]'::jsonb) else '[]'::jsonb end;
  v_allowed_agents jsonb := case when jsonb_typeof(coalesce(p_allowed_agents, '[]'::jsonb)) = 'array' then coalesce(p_allowed_agents, '[]'::jsonb) else '[]'::jsonb end;
  v_idempotency_key text := left(coalesce(p_idempotency_key, ''), 120);
  v_trust real := greatest(0.0, least(coalesce(p_trust, 0.5), 1.0));
begin
  if length(trim(coalesce(p_title, ''))) = 0 or length(trim(coalesce(p_content, ''))) = 0 then
    raise exception 'title and content are required';
  end if;

  if v_scope not in ('project', 'shared', 'public') then
    v_scope := 'project';
  end if;
  if v_sensitivity not in ('low', 'medium') then
    v_sensitivity := 'low';
  end if;

  if v_idempotency_key <> '' then
    select r.id, r.status, r.created_at
      into v_id, v_status, v_created_at
      from public.vault_memory_write_requests r
      where r.idempotency_key = v_idempotency_key
      limit 1;
    if v_id is not null then
      return query select v_id::text, v_status, v_created_at;
      return;
    end if;
  end if;

  insert into public.vault_memory_write_requests (
    idempotency_key,
    from_agent,
    title,
    content,
    reason,
    category,
    tags,
    trust,
    scope,
    sensitivity,
    owner_agent,
    allowed_agents,
    memory_type,
    source_ref
  )
  values (
    v_idempotency_key,
    left(coalesce(p_from_agent, ''), 80),
    left(trim(p_title), 240),
    left(trim(p_content), 20000),
    left(coalesce(p_reason, ''), 1000),
    left(coalesce(nullif(trim(p_category), ''), 'general'), 80),
    v_tags,
    v_trust,
    v_scope,
    v_sensitivity,
    left(coalesce(p_owner_agent, ''), 80),
    v_allowed_agents,
    left(coalesce(nullif(trim(p_memory_type), ''), 'remote_candidate'), 80),
    left(coalesce(p_source_ref, ''), 500)
  )
  returning vault_memory_write_requests.id, vault_memory_write_requests.status, vault_memory_write_requests.created_at
    into v_id, v_status, v_created_at;

  return query select v_id::text, v_status, v_created_at;
end;
$$;

create or replace function public.vault_search_readable(
  p_agent_id text default '',
  p_query text default '',
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium',
  p_limit integer default 20
)
returns table (
  id text,
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
    k.id::text,
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
  p_knowledge_id text default '',
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  id text,
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
    k.id::text,
    k.title,
    coalesce(k.scope, 'project') as scope,
    coalesce(k.sensitivity, 'low') as sensitivity,
    coalesce(k.owner_agent, '') as owner_agent,
    coalesce(k.allowed_agents, '[]'::jsonb) as allowed_agents,
    coalesce(k.memory_type, 'knowledge') as memory_type,
    k.expires_at,
    k.updated_at
  from public.vault_knowledge k
  where k.id::text = p_knowledge_id
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
  p_knowledge_id text default '',
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  knowledge_id text,
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
    n.knowledge_id::text,
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
  where n.knowledge_id::text = p_knowledge_id
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
  p_knowledge_id text default '',
  p_include_private boolean default false,
  p_max_sensitivity text default 'medium'
)
returns table (
  knowledge_id text,
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
    c.knowledge_id::text,
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
  where c.knowledge_id::text = p_knowledge_id
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
  p_knowledge_id text default '',
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
  where k.id::text = p_knowledge_id
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
alter table public.vault_memory_write_requests enable row level security;
revoke all on table public.vault_knowledge from anon, authenticated;
revoke all on table public.vault_knowledge_nodes from anon, authenticated;
revoke all on table public.vault_knowledge_claims from anon, authenticated;
revoke all on table public.vault_memory_write_requests from anon, authenticated;
revoke all on function public.vault_is_readable(text, text, text, jsonb, text, timestamptz, text, boolean, text) from public;
revoke all on function public.vault_search_readable(text, text, boolean, text, integer) from public;
revoke all on function public.vault_get_readable(text, text, boolean, text) from public;
revoke all on function public.vault_nodes_readable(text, text, boolean, text) from public;
revoke all on function public.vault_claims_readable(text, text, boolean, text) from public;
revoke all on function public.vault_content_readable(text, text, boolean, text) from public;
revoke all on function public.vault_submit_memory_request(text, text, text, text, text, jsonb, real, text, text, text, jsonb, text, text, text) from public;
grant execute on function public.vault_search_readable(text, text, boolean, text, integer) to anon, authenticated;
grant execute on function public.vault_get_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_nodes_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_claims_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_content_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_submit_memory_request(text, text, text, text, text, jsonb, real, text, text, text, jsonb, text, text, text) to anon, authenticated;
