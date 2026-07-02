"""Supabase setup guide and read-policy templates for agent setup."""

from __future__ import annotations

from pathlib import Path

VALID_SUPABASE_SETUP_MODES = {"none", "simple", "advanced"}
VALID_SETUP_LANGUAGES = {"en", "zh-Hant", "zh-CN"}
SUPABASE_SETUP_DOC_URL = "https://github.com/zycaskevin/Vault-for-LLM/blob/main/docs/supabase_setup.md"

SUPABASE_READ_POLICY_SQL = """-- Vault-for-LLM advanced Supabase read policy
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
  hmac_algorithm text not null default '',
  payload_hash text not null default '',
  hmac_signature text not null default '',
  local_candidate_id text not null default '',
  error text not null default ''
);

create index if not exists vault_memory_write_requests_status_idx
  on public.vault_memory_write_requests (status, created_at);
create index if not exists vault_memory_write_requests_from_agent_idx
  on public.vault_memory_write_requests (from_agent, created_at);
create index if not exists vault_memory_write_requests_payload_hash_idx
  on public.vault_memory_write_requests (payload_hash)
  where payload_hash <> '';
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
drop function if exists public.vault_submit_memory_request(text, text, text, text, text, jsonb, real, text, text, text, jsonb, text, text, text, text, text, text);

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
  p_idempotency_key text default '',
  p_hmac_algorithm text default '',
  p_payload_hash text default '',
  p_hmac_signature text default ''
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
    source_ref,
    hmac_algorithm,
    payload_hash,
    hmac_signature
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
    left(coalesce(p_source_ref, ''), 500),
    left(coalesce(p_hmac_algorithm, ''), 40),
    left(coalesce(p_payload_hash, ''), 128),
    left(coalesce(p_hmac_signature, ''), 256)
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
"""


def render_supabase_setup_guide(
    *,
    mode: str,
    project_dir: str | Path,
    agent: str,
    language: str = "en",
) -> str:
    safe_mode = _normalize_supabase_setup_mode(mode)
    safe_language = _normalize_setup_language(language)
    project_path = Path(project_dir).expanduser()
    if safe_language == "zh-Hant":
        lines = _render_supabase_setup_guide_zh_hant(
            mode=safe_mode,
            project_path=project_path,
            agent=agent,
        )
    elif safe_language == "zh-CN":
        lines = _render_supabase_setup_guide_zh_cn(
            mode=safe_mode,
            project_path=project_path,
            agent=agent,
        )
    else:
        lines = _render_supabase_setup_guide_en(
            mode=safe_mode,
            project_path=project_path,
            agent=agent,
        )
    return "\n".join(lines)


def _render_supabase_setup_guide_en(*, mode: str, project_path: Path, agent: str) -> list[str]:
    lines = [
        "# Vault-for-LLM Supabase Setup",
        "",
        "Supabase is optional. Keep using local `vault.db` when one machine is enough.",
        "",
        "Use Supabase when:",
        "",
        "- agents run on different machines",
        "- Coze, n8n, or a hosted workflow needs remote memory reads",
        "- a team wants a synced copy of reviewed project memory",
        "",
        "Skip Supabase when:",
        "",
        "- all agents run on one trusted machine",
        "- local SQLite search is enough",
        "- you are storing private raw conversations that should stay local",
        "",
        "## Simple Sync Setup",
        "",
        "1. Create or open a Supabase account and create one project for this memory workspace.",
        "2. In Supabase, open Project Settings -> API.",
        "3. Copy the Project URL into `SUPABASE_URL`.",
        "4. Copy the `service_role` key into `SUPABASE_SERVICE_ROLE_KEY` only on the trusted machine that runs sync jobs.",
        f"5. Put those values in `{project_path / '.env'}` or another reviewed environment source.",
        f"6. Create the Vault tables using the schema from `{SUPABASE_SETUP_DOC_URL}`.",
        "7. Run the first sync:",
        "",
        f"```bash\npython -m scripts.sync_to_supabase --db {project_path / 'vault.db'} --document-map --health\n```",
        "",
        "8. Verify that the sync finished without HTTP 400 errors and that row counts changed in Supabase.",
        "",
        "Default sync does not upload full `content_raw`. Add `--include-content` only when you intentionally want full local content copied to Supabase.",
        "",
        "Privacy gate failures are intentional. Clean the source notes and recompile instead of bypassing the gate.",
        "",
        "## Agent Rules",
        "",
        f"- Agent name: `{agent}`",
        "- Local `vault.db` remains the source of truth.",
        "- Scheduled sync may use `SUPABASE_SERVICE_ROLE_KEY`.",
        "- Normal agents, Coze, and n8n should not receive the service role key.",
        "- For hosted readers, prefer a read-only API, RPC, Edge Function, or RLS-backed token.",
        "- For remote candidate writes, set `VAULT_SYNC_HMAC_SECRET` on trusted submitters and the trusted pull host to verify payload integrity.",
    ]
    if mode == "advanced":
        lines.extend(
            [
                "",
                "## Advanced Multi-Agent / RLS Notes",
                "",
                "Use RLS for shared Supabase reads and writes, not for each agent's private raw memory.",
                "",
                "Suggested columns for a shared-memory table or view:",
                "",
                "- `owner_agent`: `profile-agent`, `care-agent`, `work-agent`, `product-agent`, `codex`, `remote-agent`, ...",
                "- `scope`: `private`, `project`, `shared`, `public`",
                "- `sensitivity`: `low`, `medium`, `high`, `restricted`",
                "- `allowed_agents`: text array or JSON array of agent IDs",
                "- `status`: `candidate`, `reviewed`, `active`, `archived`",
                "- `expires_at`: optional TTL for short-lived care/status summaries",
                "",
                "Recommended policy shape:",
                "",
                "- private raw memory stays local or owner-only",
                "- project knowledge is readable by trusted project agents",
                "- medium-sensitivity summaries require `allowed_agents` membership",
                "- normal agents can propose candidates but cannot directly write active shared memory",
                "- service role is reserved for reviewed sync jobs or backend functions",
                "- HMAC verification is separate from Supabase auth; use `VAULT_SYNC_HMAC_SECRET` for candidate payload integrity",
                "",
                "This installer also writes `supabase-read-policy.sql` in advanced mode. Paste it into the Supabase SQL editor after the minimal schema to create a read-only RPC named `vault_search_readable`.",
                "",
                "`vault_search_readable` returns safe metadata and summaries only. It does not return raw full text; use local Vault reads for authoritative citations unless you intentionally design a separate reviewed full-content API.",
                "",
                "Do not put raw private conversations and shareable summaries in the same unrestricted row. Use separate tables, views, or RPC responses that return only safe fields.",
            ]
        )
    lines.append("")
    return lines


def _render_supabase_setup_guide_zh_hant(*, mode: str, project_path: Path, agent: str) -> list[str]:
    lines = [
        "# Vault-for-LLM Supabase 設定",
        "",
        "Supabase 是可選功能。只有一台電腦使用時，繼續使用本地 `vault.db` 就好。",
        "",
        "適合使用 Supabase 的情境：",
        "",
        "- Agent 跑在不同電腦上",
        "- Coze、n8n 或 hosted workflow 需要遠端讀取記憶",
        "- 團隊需要同步已審核的專案記憶",
        "",
        "適合跳過 Supabase 的情境：",
        "",
        "- 所有 Agent 都在同一台可信任電腦上",
        "- 本地 SQLite 搜尋已經夠用",
        "- 你正在保存不該上雲端的私人原始對話",
        "",
        "## 簡單同步設定",
        "",
        "1. 建立或登入 Supabase 帳號，為這個記憶工作區建立一個 project。",
        "2. 在 Supabase 打開 Project Settings -> API。",
        "3. 把 Project URL 複製到 `SUPABASE_URL`。",
        "4. 只在負責同步的可信任主機上，把 `service_role` key 放進 `SUPABASE_SERVICE_ROLE_KEY`。",
        f"5. 把這些值放在 `{project_path / '.env'}`，或另一個你審核過的環境設定來源。",
        f"6. 使用 `{SUPABASE_SETUP_DOC_URL}` 裡的 schema 建立 Vault tables。",
        "7. 跑第一次同步：",
        "",
        f"```bash\npython -m scripts.sync_to_supabase --db {project_path / 'vault.db'} --document-map --health\n```",
        "",
        "8. 確認同步沒有 HTTP 400 錯誤，並在 Supabase 看到 row count 有變化。",
        "",
        "預設同步不會上傳完整 `content_raw`。只有你明確想把全文複製到 Supabase 時，才加 `--include-content`。",
        "",
        "privacy gate 擋住是刻意設計。請清理來源筆記後重新 compile，不要硬繞過。",
        "",
        "## Agent 規則",
        "",
        f"- Agent 名稱：`{agent}`",
        "- 本地 `vault.db` 仍然是 source of truth。",
        "- 排程同步可以使用 `SUPABASE_SERVICE_ROLE_KEY`。",
        "- 一般 Agent、Coze、n8n 不應該拿到 service role key。",
        "- hosted reader 建議透過 read-only API、RPC、Edge Function，或 RLS-backed token。",
        "- 遠端候選寫入建議在可信任提交端與可信任拉取主機設定 `VAULT_SYNC_HMAC_SECRET`，用來驗證同步包沒有被竄改。",
    ]
    if mode == "advanced":
        lines.extend(
            [
                "",
                "## 進階 Multi-Agent / RLS 備註",
                "",
                "RLS 適合管理 Supabase 上共享資料的讀寫權限，不適合取代每個 Agent 的私有原始記憶。",
                "",
                "shared-memory table 或 view 可考慮這些欄位：",
                "",
                "- `owner_agent`：`profile-agent`、`care-agent`、`work-agent`、`product-agent`、`codex`、`remote-agent` 等",
                "- `scope`：`private`、`project`、`shared`、`public`",
                "- `sensitivity`：`low`、`medium`、`high`、`restricted`",
                "- `allowed_agents`：可讀 Agent 的 text array 或 JSON array",
                "- `status`：`candidate`、`reviewed`、`active`、`archived`",
                "- `expires_at`：短期照護摘要或狀態摘要的可選 TTL",
                "",
                "建議權限形狀：",
                "",
                "- 私人原始記憶留在本地，或 owner-only",
                "- 專案知識可給可信任的專案 Agent 讀取",
                "- medium sensitivity 摘要需要檢查 `allowed_agents`",
                "- 一般 Agent 只能 propose candidate，不直接寫 active shared memory",
                "- service role 只給審核過的同步工作或後端函式",
                "- HMAC 驗證和 Supabase auth 分開；候選同步包完整性使用 `VAULT_SYNC_HMAC_SECRET`",
                "",
                "advanced 模式也會產生 `supabase-read-policy.sql`。建立 minimal schema 後，把它貼到 Supabase SQL editor，可建立名為 `vault_search_readable` 的 read-only RPC。",
                "",
                "`vault_search_readable` 只回傳安全 metadata 與摘要，不回傳原始全文。正式引用仍建議回到本地 Vault 的 bounded read，除非你另外設計審核過的全文 API。",
                "",
                "不要把私人原始對話和可共享摘要放在同一個無限制 row。請用不同 tables、views 或 RPC，只回傳安全欄位。",
            ]
        )
    lines.append("")
    return lines


def _render_supabase_setup_guide_zh_cn(*, mode: str, project_path: Path, agent: str) -> list[str]:
    text = _render_supabase_setup_guide_zh_hant(
        mode=mode,
        project_path=project_path,
        agent=agent,
    )
    replacements = {
        "設定": "设置",
        "選": "选",
        "繼續": "继续",
        "電腦": "电脑",
        "遠端": "远端",
        "記憶": "记忆",
        "團隊": "团队",
        "同步": "同步",
        "審核": "审核",
        "專案": "项目",
        "適合": "适合",
        "情境": "场景",
        "登入": "登录",
        "建立": "创建",
        "複製": "复制",
        "負責": "负责",
        "主機": "主机",
        "裡": "里",
        "確認": "确认",
        "預設": "默认",
        "會": "会",
        "完整": "完整",
        "明確": "明确",
        "時": "时",
        "擋住": "挡住",
        "設計": "设计",
        "來源": "来源",
        "筆記": "笔记",
        "規則": "规则",
        "名稱": "名称",
        "仍然": "仍然",
        "應該": "应该",
        "透過": "通过",
        "進階": "进阶",
        "備註": "备注",
        "權限": "权限",
        "原始": "原始",
        "欄位": "字段",
        "狀態": "状态",
        "短期": "短期",
        "照護": "照护",
        "摘要": "摘要",
        "建議": "建议",
        "可信任": "可信任",
        "讀取": "读取",
        "檢查": "检查",
        "只給": "只给",
        "後端": "后端",
        "函式": "函数",
        "對話": "对话",
        "無限制": "无限制",
        "不同": "不同",
        "回傳": "返回",
        "安全欄位": "安全字段",
    }
    simplified: list[str] = []
    for line in text:
        for old, new in replacements.items():
            line = line.replace(old, new)
        simplified.append(line)
    return simplified


def write_supabase_setup_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    agent: str,
    mode: str = "simple",
    language: str = "en",
) -> dict[str, str]:
    safe_mode = _normalize_supabase_setup_mode(mode)
    if safe_mode == "none":
        return {}
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "README-supabase-setup.md"
    path.write_text(
        render_supabase_setup_guide(
            mode=safe_mode,
            project_dir=project_dir,
            agent=agent,
            language=language,
        ),
        encoding="utf-8",
    )
    written = {"mode": safe_mode, "guide": str(path)}
    if safe_mode == "advanced":
        sql_path = out / "supabase-read-policy.sql"
        sql_path.write_text(SUPABASE_READ_POLICY_SQL, encoding="utf-8")
        written["read_policy_sql"] = str(sql_path)
    return written



def _normalize_supabase_setup_mode(mode: str | None) -> str:
    value = str(mode or "simple").strip().lower()
    if value not in VALID_SUPABASE_SETUP_MODES:
        allowed = ", ".join(sorted(VALID_SUPABASE_SETUP_MODES))
        raise ValueError(f"unknown Supabase setup mode '{mode}' (expected one of: {allowed})")
    return value


def _normalize_setup_language(language: str | None) -> str:
    value = str(language or "en").strip()
    aliases = {
        "zh": "zh-Hant",
        "zh-tw": "zh-Hant",
        "zh_hant": "zh-Hant",
        "zh-hant": "zh-Hant",
        "tc": "zh-Hant",
        "traditional": "zh-Hant",
        "zh-cn": "zh-CN",
        "zh_hans": "zh-CN",
        "zh-hans": "zh-CN",
        "sc": "zh-CN",
        "simplified": "zh-CN",
        "en-us": "en",
        "english": "en",
    }
    value = aliases.get(value.lower(), value)
    if value not in VALID_SETUP_LANGUAGES:
        allowed = ", ".join(sorted(VALID_SETUP_LANGUAGES))
        raise ValueError(f"unknown setup language '{language}' (expected one of: {allowed})")
    return value
