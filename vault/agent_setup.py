"""Agent-friendly setup wizard and sync template helpers."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vault import __version__
from vault.agent_registry import register_agent
from vault.db import VaultDB
from vault.import_obsidian import sync_obsidian_vault


DEFAULT_FEATURES = ["core", "mcp"]
VALID_FEATURES = {
    "core",
    "mcp",
    "obsidian_import",
    "semantic",
    "supabase",
    "headroom",
    "memory_agents",
    "dev",
}
VALID_SYNC_TARGETS = {"none", "cron", "launchagent", "n8n", "all"}
VALID_REMOTE_READER_TARGETS = {"none", "shell", "n8n", "coze", "all"}
VALID_VALIDATION_PACK_TARGETS = {"none", "remote", "n8n", "coze", "all"}
VALID_AGENT_ROLES = {"work", "profile", "care", "dream", "remote", "automation", "observer"}
VALID_SUPABASE_SETUP_MODES = {"none", "simple", "advanced"}
VALID_SETUP_LANGUAGES = {"en", "zh-Hant", "zh-CN"}
VALID_AUTOMATION_MODES = {"conservative", "balanced", "autonomous"}
VALID_AUTOMATION_COMMANDS = {"run", "cycle"}
VALID_MEMORY_LAYOUTS = {"shared", "private", "hybrid"}
PYPI_EXTRA_FEATURES = {"mcp", "semantic", "supabase", "dev"}
VALID_EMBEDDING_MODELS = {"zh", "en", "mix"}
DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES = 24 * 60
DEFAULT_AUTOMATION_INTERVAL_MINUTES = 24 * 60
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
revoke all on table public.vault_knowledge from anon, authenticated;
revoke all on table public.vault_knowledge_nodes from anon, authenticated;
revoke all on table public.vault_knowledge_claims from anon, authenticated;
revoke all on function public.vault_is_readable(text, text, text, jsonb, text, timestamptz, text, boolean, text) from public;
revoke all on function public.vault_search_readable(text, text, boolean, text, integer) from public;
revoke all on function public.vault_get_readable(text, text, boolean, text) from public;
revoke all on function public.vault_nodes_readable(text, text, boolean, text) from public;
revoke all on function public.vault_claims_readable(text, text, boolean, text) from public;
revoke all on function public.vault_content_readable(text, text, boolean, text) from public;
grant execute on function public.vault_search_readable(text, text, boolean, text, integer) to anon, authenticated;
grant execute on function public.vault_get_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_nodes_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_claims_readable(text, text, boolean, text) to anon, authenticated;
grant execute on function public.vault_content_readable(text, text, boolean, text) to anon, authenticated;
"""


def default_project_dir(scope: str, *, agent: str = "generic") -> Path:
    home = Path.home()
    if scope == "shared":
        return home / "Vaults" / "project-memory"
    if scope == "domain":
        return home / "Vaults" / "domain-memory"
    if scope == "temporary":
        import tempfile

        return Path(tempfile.mkdtemp(prefix="vault-agent-setup-"))
    if agent == "openclaw":
        return home / ".openclaw" / "workspace" / "vault-project"
    return home / ".vault-for-llm" / "agent-private"


def default_agent_private_dir(agent: str = "generic") -> Path:
    root = os.environ.get("VAULT_AGENT_PRIVATE_ROOT", "").strip()
    base = Path(root).expanduser() if root else Path.home() / "Vaults" / "agents"
    return base / _safe_slug(agent, default="generic") / "private-memory"


def normalize_features(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        features = list(DEFAULT_FEATURES)
    elif isinstance(raw, str):
        features = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        features = [str(part).strip() for part in raw if str(part).strip()]

    if "core" not in features:
        features.insert(0, "core")

    normalized: list[str] = []
    for feature in features:
        if feature not in VALID_FEATURES:
            allowed = ", ".join(sorted(VALID_FEATURES))
            raise ValueError(f"unknown optional feature '{feature}' (expected one of: {allowed})")
        if feature not in normalized:
            normalized.append(feature)
    return normalized


def ensure_project(project_dir: str | Path) -> Path:
    project_path = Path(project_dir).expanduser().resolve()
    project_path.mkdir(parents=True, exist_ok=True)
    for dirname in ["raw", "compiled", "L0-identity", "L1-core-facts", "L2-context", "L3-knowledge"]:
        (project_path / dirname).mkdir(parents=True, exist_ok=True)

    with VaultDB(str(project_path / "vault.db")) as db:
        db.set_config("embedding_provider", db.get_config("embedding_provider", "auto"))
        db.set_config("embedding_model", db.get_config("embedding_model", "mix"))
        db.set_config("embedding_dim", db.get_config("embedding_dim", "384"))

    gitignore = project_path / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    for line in ["# Vault-for-LLM", "*.db", "__pycache__/", ".cache/"]:
        if line not in lines:
            lines.append(line)
    gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project_path


def compile_project(project_dir: str | Path, *, allow_private: bool = False) -> dict[str, Any]:
    from vault.compiler import VaultCompiler

    project_path = Path(project_dir).expanduser().resolve()
    db = VaultDB(str(project_path / "vault.db"))
    db.connect()
    try:
        compiler = VaultCompiler(project_path, db=db, embed_provider=None, allow_private=allow_private)
        with contextlib.redirect_stdout(io.StringIO()):
            return compiler.compile(dry_run=False)
    finally:
        db.close()


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def obsidian_sync_command(
    *,
    project_dir: str | Path,
    obsidian_vault: str | Path,
    vault_executable: str = "vault",
) -> list[str]:
    return [
        vault_executable,
        "import",
        "obsidian",
        "--vault",
        str(Path(obsidian_vault).expanduser()),
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--compile",
        "--no-embed",
    ]


def render_cron_template(*, command: list[str], interval_minutes: int = 15) -> str:
    interval = max(1, int(interval_minutes))
    return "\n".join(
        [
            "# Vault-for-LLM Obsidian sync",
            f"*/{interval} * * * * {shell_join(command)} >> $HOME/.vault-for-llm/obsidian-sync.log 2>&1",
            "",
        ]
    )


def render_daily_cron_template(*, command: list[str], hour: int = 3, minute: int = 0) -> str:
    safe_hour = max(0, min(23, int(hour)))
    safe_minute = max(0, min(59, int(minute)))
    return "\n".join(
        [
            "# Vault-for-LLM daily sync",
            f"{safe_minute} {safe_hour} * * * {shell_join(command)} >> $HOME/.vault-for-llm/supabase-sync.log 2>&1",
            "",
        ]
    )


def render_launchagent_plist(
    *,
    command: list[str],
    label: str = "com.zycaskevin.vault-for-llm.obsidian-sync",
    interval_minutes: int = 15,
    log_basename: str = "obsidian-sync",
) -> str:
    interval_seconds = max(60, int(interval_minutes) * 60)
    program = command[0]
    args = command[1:]
    arg_lines = "\n".join(f"    <string>{_xml_escape(arg)}</string>" for arg in args)
    safe_log_basename = str(log_basename or "vault-sync").strip().replace("/", "-")
    stdout_path = Path.home() / ".vault-for-llm" / f"{safe_log_basename}.log"
    stderr_path = Path.home() / ".vault-for-llm" / f"{safe_log_basename}.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_xml_escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_xml_escape(program)}</string>
{arg_lines}
  </array>
  <key>StartInterval</key>
  <integer>{interval_seconds}</integer>
  <key>StandardOutPath</key>
  <string>{_xml_escape(str(stdout_path))}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(str(stderr_path))}</string>
</dict>
</plist>
"""


def _xml_escape(value: object) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def render_n8n_workflow(*, command: list[str], interval_minutes: int = 15) -> str:
    workflow = {
        "name": "Vault-for-LLM Obsidian Sync",
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": max(1, int(interval_minutes))}]
                    }
                },
                "id": "schedule",
                "name": "Every interval",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {"command": shell_join(command)},
                "id": "vault-obsidian-sync",
                "name": "Vault Obsidian Sync",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [260, 0],
            },
        ],
        "connections": {
            "Every interval": {"main": [[{"node": "Vault Obsidian Sync", "type": "main", "index": 0}]]}
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def render_n8n_automation_workflow(*, command: list[str], interval_minutes: int = DEFAULT_AUTOMATION_INTERVAL_MINUTES) -> str:
    workflow = {
        "name": "Vault-for-LLM Memory Automation",
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": max(1, int(interval_minutes))}]
                    }
                },
                "id": "schedule",
                "name": "Every interval",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {"command": shell_join(command)},
                "id": "vault-memory-automation",
                "name": "Vault Memory Automation",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [280, 0],
            },
        ],
        "connections": {
            "Every interval": {"main": [[{"node": "Vault Memory Automation", "type": "main", "index": 0}]]}
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def render_n8n_remote_reader_workflow(
    *,
    agent_id: str,
    query: str = "deployment SOP",
    vault_executable: str = "vault",
) -> str:
    command = [
        vault_executable,
        "remote",
        "search",
        query,
        "--agent-id",
        agent_id,
        "--json",
    ]
    workflow = {
        "name": "Vault-for-LLM Remote Reader",
        "nodes": [
            {
                "parameters": {},
                "id": "manual-trigger",
                "name": "Manual trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
            },
            {
                "parameters": {"command": shell_join(command)},
                "id": "vault-remote-search",
                "name": "Vault Remote Search",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [260, 0],
            },
        ],
        "connections": {
            "Manual trigger": {"main": [[{"node": "Vault Remote Search", "type": "main", "index": 0}]]}
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def render_coze_supabase_openapi_template(*, agent_id: str) -> str:
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Vault-for-LLM Supabase Remote Reader",
            "version": __version__,
            "description": "Read safe Vault-for-LLM memory summaries through the Supabase vault_search_readable RPC.",
        },
        "servers": [
            {
                "url": "https://YOUR_PROJECT.supabase.co/rest/v1",
                "description": "Replace with your Supabase Project URL plus /rest/v1.",
            }
        ],
        "paths": {
            "/rpc/vault_search_readable": {
                "post": {
                    "operationId": "vaultRemoteSearch",
                    "summary": "Search reviewed Vault-for-LLM remote memory summaries",
                    "description": "Use an anon/authenticated key. Do not expose SUPABASE_SERVICE_ROLE_KEY to Coze or browser clients.",
                    "security": [{"SupabaseApiKey": []}, {"SupabaseBearer": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "p_agent_id": {"type": "string", "default": agent_id},
                                        "p_query": {"type": "string", "default": "deployment SOP"},
                                        "p_include_private": {"type": "boolean", "default": False},
                                        "p_max_sensitivity": {
                                            "type": "string",
                                            "enum": ["low", "medium", "high", "restricted"],
                                            "default": "medium",
                                        },
                                        "p_limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                                    },
                                    "required": ["p_agent_id", "p_query"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Safe metadata and summary rows. This RPC intentionally does not return content_raw.",
                            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}},
                        }
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "SupabaseApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "apikey",
                    "description": "Use SUPABASE_ANON_KEY or an authenticated user token.",
                },
                "SupabaseBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Use the same anon/authenticated token as a Bearer token.",
                },
            }
        },
    }
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def supabase_sync_command(
    *,
    project_dir: str | Path,
    python_executable: str | Path | None = None,
    document_map: bool = True,
    health: bool = True,
    include_content: bool = False,
) -> list[str]:
    command = [
        str(python_executable or sys.executable),
        "-m",
        "scripts.sync_to_supabase",
        "--db",
        str(Path(project_dir).expanduser() / "vault.db"),
    ]
    if include_content:
        command.append("--include-content")
    if document_map:
        command.append("--document-map")
    if health:
        command.append("--health")
    return command


def write_supabase_sync_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    targets: str | list[str] = "all",
    interval_minutes: int = DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES,
    python_executable: str | Path | None = None,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_sync_targets(targets)
    command = supabase_sync_command(
        project_dir=project_dir,
        python_executable=python_executable,
    )

    written: dict[str, str] = {}
    if "cron" in selected:
        path = out / "supabase-sync.cron"
        path.write_text(render_daily_cron_template(command=command), encoding="utf-8")
        written["cron"] = str(path)
    if "launchagent" in selected:
        path = out / "com.zycaskevin.vault-for-llm.supabase-sync.plist"
        path.write_text(
            render_launchagent_plist(
                command=command,
                label="com.zycaskevin.vault-for-llm.supabase-sync",
                interval_minutes=interval_minutes,
                log_basename="supabase-sync",
            ),
            encoding="utf-8",
        )
        written["launchagent"] = str(path)
    if "n8n" in selected:
        path = out / "n8n-supabase-sync.workflow.json"
        path.write_text(render_n8n_workflow(command=command, interval_minutes=interval_minutes), encoding="utf-8")
        written["n8n"] = str(path)

    readme = out / "README-supabase-sync.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Supabase Sync Templates",
                "",
                "Generated command:",
                "",
                f"```bash\n{shell_join(command)}\n```",
                "",
                "Review `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` before enabling any scheduled job.",
                "The local SQLite database remains the source of truth.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def _normalize_automation_mode(mode: str | None) -> str:
    value = str(mode or "balanced").strip().lower()
    if value not in VALID_AUTOMATION_MODES:
        allowed = ", ".join(sorted(VALID_AUTOMATION_MODES))
        raise ValueError(f"unknown automation mode '{mode}' (expected one of: {allowed})")
    return value


def _normalize_automation_command(command: str | None) -> str:
    value = str(command or "cycle").strip().lower()
    if value not in VALID_AUTOMATION_COMMANDS:
        allowed = ", ".join(sorted(VALID_AUTOMATION_COMMANDS))
        raise ValueError(f"unknown automation command '{command}' (expected one of: {allowed})")
    return value


def automation_schedule_command(
    *,
    project_dir: str | Path,
    mode: str = "balanced",
    apply: bool = False,
    command: str = "cycle",
    vault_executable: str = "vault",
    write_workspace: bool = False,
    inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
) -> list[str]:
    normalized_command = _normalize_automation_command(command)
    command_args = [
        vault_executable,
        "automation",
        normalized_command,
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--mode",
        _normalize_automation_mode(mode),
        "--pretty",
    ]
    if apply:
        command_args.append("--apply")
    if normalized_command == "cycle" and write_workspace:
        command_args.append("--write-workspace")
        command_args.extend(["--inbox-limit", str(max(1, min(int(inbox_limit or 5), 50)))])
        if include_transcripts:
            command_args.extend(
                [
                    "--include-transcripts",
                    "--transcript-limit",
                    str(max(1, min(int(transcript_limit or 5), 20))),
                ]
            )
    return command_args


def automation_inbox_handoff_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
    limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
) -> list[str]:
    command = [
        vault_executable,
        "automation",
        "inbox",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--limit",
        str(max(1, min(int(limit or 5), 50))),
        "--write-handoff",
        "--pretty",
    ]
    if include_transcripts:
        command.extend(
            [
                "--include-transcripts",
                "--transcript-limit",
                str(max(1, min(int(transcript_limit or 5), 20))),
            ]
        )
    return command


def automation_schedule_with_inbox_command(
    *,
    project_dir: str | Path,
    mode: str = "balanced",
    apply: bool = False,
    command: str = "cycle",
    vault_executable: str = "vault",
    write_workspace: bool = False,
    inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
) -> list[str]:
    primary = automation_schedule_command(
        project_dir=project_dir,
        mode=mode,
        apply=apply,
        command=command,
        vault_executable=vault_executable,
        write_workspace=write_workspace,
        inbox_limit=inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    inbox = automation_inbox_handoff_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    return ["sh", "-lc", f"{shell_join(primary)} && {shell_join(inbox)}"]


def write_automation_schedule_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    targets: str | list[str] = "all",
    interval_minutes: int = DEFAULT_AUTOMATION_INTERVAL_MINUTES,
    mode: str = "balanced",
    apply: bool = False,
    command: str = "cycle",
    vault_executable: str = "vault",
    write_workspace: bool = False,
    workspace_inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_sync_targets(targets)
    normalized_mode = _normalize_automation_mode(mode)
    normalized_command = _normalize_automation_command(command)
    command_args = automation_schedule_command(
        project_dir=project_dir,
        mode=normalized_mode,
        apply=apply,
        command=normalized_command,
        vault_executable=vault_executable,
        write_workspace=write_workspace,
        inbox_limit=workspace_inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    scheduled_args = automation_schedule_with_inbox_command(
        project_dir=project_dir,
        mode=normalized_mode,
        apply=apply,
        command=normalized_command,
        vault_executable=vault_executable,
        write_workspace=write_workspace,
        inbox_limit=workspace_inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    inbox_args = automation_inbox_handoff_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    handoff_args = [
        vault_executable,
        "automation",
        "handoff",
        "--project-dir",
        str(Path(project_dir).expanduser()),
    ]

    written: dict[str, str] = {}
    if "cron" in selected:
        path = out / "memory-automation.cron"
        interval = max(1, int(interval_minutes))
        schedule = f"*/{interval} * * * *" if interval < 60 else "0 3 * * *"
        path.write_text(
            "\n".join(
                [
                    "# Vault-for-LLM memory automation",
                    f"{schedule} {shell_join(scheduled_args)} >> $HOME/.vault-for-llm/memory-automation.log 2>&1",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["cron"] = str(path)
    if "launchagent" in selected:
        path = out / "com.zycaskevin.vault-for-llm.memory-automation.plist"
        path.write_text(
            render_launchagent_plist(
                command=scheduled_args,
                label="com.zycaskevin.vault-for-llm.memory-automation",
                interval_minutes=interval_minutes,
                log_basename="memory-automation",
            ),
            encoding="utf-8",
        )
        written["launchagent"] = str(path)
    if "n8n" in selected:
        path = out / "n8n-memory-automation.workflow.json"
        path.write_text(
            render_n8n_automation_workflow(command=scheduled_args, interval_minutes=interval_minutes),
            encoding="utf-8",
        )
        written["n8n"] = str(path)

    readme = out / "README-memory-automation.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Memory Automation Schedule",
                "",
                "Generated command:",
                "",
                f"```bash\n{shell_join(command_args)}\n```",
                "",
                "Scheduled templates run this command and then write an inbox handoff:",
                "",
                f"```bash\n{shell_join(inbox_args)}\n```",
                "",
                "Next agent startup handoff:",
                "",
                f"```bash\n{shell_join(handoff_args)}\n```",
                "",
                "Run this at the start of the next agent session. It is read-only and prefers",
                "`reports/automation/cycle-latest.md` before falling back to JSON handoffs.",
                "",
                "Recommended first step:",
                "",
                "```bash",
                f"vault automation plan --project-dir {shlex.quote(str(Path(project_dir).expanduser()))} --mode {normalized_mode} --write-policy --pretty",
                "```",
                "",
                "Safety defaults:",
                "",
                f"- scheduled command: `vault automation {normalized_command}`",
                f"- mode: `{normalized_mode}`",
                f"- apply reversible archival: `{str(bool(apply)).lower()}`",
                "- `cycle` first writes a bounded learning policy from reviewed candidate outcomes, then runs automation",
                "- automation never hard-deletes memory",
                "- expired memories with usage are protected and sent to human review",
                "- scheduled runs write `reports/automation/inbox-latest.json` as the next-agent handoff",
                f"- scheduled cycle workspace: `{str(bool(write_workspace and normalized_command == 'cycle')).lower()}`",
                "- cycle workspace path: `reports/automation/cycle-latest.json` when enabled",
                "- cycle workspace Markdown: `reports/automation/cycle-latest.md` when enabled",
                "- next agent startup command: `vault automation handoff`",
                f"- uncaptured transcript hints in scheduled handoff: `{str(bool(include_transcripts)).lower()}`",
                "- transcript discovery is metadata-only and does not read transcript contents",
                "",
                "Review `automation_policy.yaml` before enabling a scheduled job.",
                "Keep the Python virtualenv and project directory in stable paths, not `/tmp`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def _normalize_remote_reader_targets(raw: str | list[str] | None) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    else:
        parts = [str(part).strip().lower() for part in raw if str(part).strip()]
    if not parts or "none" in parts:
        return set()
    unknown = [part for part in parts if part not in VALID_REMOTE_READER_TARGETS]
    if unknown:
        allowed = ", ".join(sorted(VALID_REMOTE_READER_TARGETS))
        raise ValueError(f"unknown remote reader template target '{unknown[0]}' (expected one of: {allowed})")
    if "all" in parts:
        return {"shell", "n8n", "coze"}
    return set(parts)


def write_remote_reader_templates(
    *,
    output_dir: str | Path,
    agent: str,
    targets: str | list[str] = "all",
    query: str = "deployment SOP",
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_remote_reader_targets(targets)
    if not selected:
        return {}

    safe_agent = str(agent or "generic")
    safe_query = str(query or "deployment SOP")
    written: dict[str, str] = {}

    if "shell" in selected:
        path = out / "remote-reader-smoke.sh"
        path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    ": \"${SUPABASE_URL:?Set SUPABASE_URL first}\"",
                    ": \"${SUPABASE_ANON_KEY:?Set SUPABASE_ANON_KEY first}\"",
                    shell_join(
                        [
                            vault_executable,
                            "remote",
                            "smoke",
                            "--agent-id",
                            safe_agent,
                            "--query",
                            safe_query,
                            "--json",
                        ]
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["shell"] = str(path)

    if "n8n" in selected:
        path = out / "n8n-remote-reader.workflow.json"
        path.write_text(
            render_n8n_remote_reader_workflow(
                agent_id=safe_agent,
                query=safe_query,
                vault_executable=vault_executable,
            ),
            encoding="utf-8",
        )
        written["n8n"] = str(path)

    if "coze" in selected:
        path = out / "coze-supabase-vault-openapi.json"
        path.write_text(render_coze_supabase_openapi_template(agent_id=safe_agent), encoding="utf-8")
        written["coze"] = str(path)

    env_path = out / "remote-reader.env.example"
    env_path.write_text(
        "\n".join(
            [
                "# Vault-for-LLM remote reader credentials",
                "# Use an anon/authenticated key. Do not put SUPABASE_SERVICE_ROLE_KEY in hosted agents.",
                "SUPABASE_URL=https://YOUR_PROJECT.supabase.co",
                "SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY",
                f"VAULT_AGENT_ID={safe_agent}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["env_example"] = str(env_path)

    readme = out / "README-remote-reader.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Remote Reader Templates",
                "",
                "Use these templates after Supabase sync and `docs/supabase_read_policy.sql` are applied.",
                "",
                "Remote readers are for safe summaries and metadata. They should not receive the service role key.",
                "",
                "## Required credentials",
                "",
                "- `SUPABASE_URL`: Supabase Project URL",
                "- `SUPABASE_ANON_KEY`: anon/authenticated key for read-only RPC access",
                f"- Agent ID: `{safe_agent}`",
                "",
                "## Smoke test",
                "",
                f"```bash\nvault remote smoke --agent-id {shlex.quote(safe_agent)} --query {shlex.quote(safe_query)} --json\n```",
                "",
                "Expected result: `ok=true` and a `vault_search_readable` payload. If `ok=false`, follow the `next_action` message.",
                "",
                "## Reader flow",
                "",
                "```text",
                "vault remote search -> vault remote map -> vault remote read",
                "```",
                "",
                "Coze should call the Supabase RPC directly through the OpenAPI template. n8n can either run the CLI template or call the same RPC through HTTP nodes.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def _safe_slug(value: object, default: str = "agent") -> str:
    text = str(value or default).strip().lower()
    cleaned = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            cleaned.append(char)
        elif char in {" ", ".", "/"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-_")
    return slug or default


def _role_defaults(role: str) -> dict[str, Any]:
    normalized = str(role or "work").strip().lower()
    if normalized == "profile":
        return {"scope": "private", "max_sensitivity": "high", "tool_profile": "review", "can_write_candidates": True}
    if normalized == "care":
        return {"scope": "private", "max_sensitivity": "medium", "tool_profile": "core", "can_write_candidates": True}
    if normalized == "dream":
        return {"scope": "private", "max_sensitivity": "medium", "tool_profile": "maintenance", "can_write_candidates": True}
    if normalized == "remote":
        return {"scope": "shared", "max_sensitivity": "medium", "tool_profile": "remote", "can_write_candidates": False}
    if normalized == "automation":
        return {"scope": "shared", "max_sensitivity": "low", "tool_profile": "core", "can_write_candidates": False}
    if normalized == "observer":
        return {"scope": "shared", "max_sensitivity": "low", "tool_profile": "core", "can_write_candidates": False}
    return {"scope": "shared", "max_sensitivity": "medium", "tool_profile": "core", "can_write_candidates": True}


def normalize_agent_roster(raw: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if raw is None:
        return []
    entries: list[dict[str, Any]] = []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        for part in parts:
            fields = [field.strip() for field in part.split(":")]
            agent = fields[0] if fields else ""
            role = fields[1] if len(fields) > 1 and fields[1] else "work"
            scope = fields[2] if len(fields) > 2 and fields[2] else None
            max_sensitivity = fields[3] if len(fields) > 3 and fields[3] else None
            entries.append(
                {
                    "agent_id": agent,
                    "role": role,
                    **({"scope": scope} if scope else {}),
                    **({"max_sensitivity": max_sensitivity} if max_sensitivity else {}),
                }
            )
    else:
        entries = [dict(item) for item in raw]

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        agent_id = _safe_slug(item.get("agent_id") or item.get("agent") or item.get("name"), default="")
        if not agent_id:
            raise ValueError("agent roster entries require an agent id")
        if agent_id in seen:
            continue
        seen.add(agent_id)
        role = str(item.get("role") or "work").strip().lower()
        if role not in VALID_AGENT_ROLES:
            allowed = ", ".join(sorted(VALID_AGENT_ROLES))
            raise ValueError(f"unknown agent role '{role}' (expected one of: {allowed})")
        defaults = _role_defaults(role)
        scope = str(item.get("scope") or defaults["scope"]).strip().lower()
        if scope not in {"private", "project", "shared", "public"}:
            raise ValueError("agent roster scope must be private, project, shared, or public")
        max_sensitivity = str(item.get("max_sensitivity") or defaults["max_sensitivity"]).strip().lower()
        if max_sensitivity not in {"low", "medium", "high", "restricted"}:
            raise ValueError("agent roster max_sensitivity must be low, medium, high, or restricted")
        normalized.append(
            {
                "agent_id": agent_id,
                "role": role,
                "scope": scope,
                "max_sensitivity": max_sensitivity,
                "tool_profile": str(item.get("tool_profile") or defaults["tool_profile"]),
                "can_write_candidates": bool(item.get("can_write_candidates", defaults["can_write_candidates"])),
                "private_memory": bool(item.get("private_memory", role in {"profile", "care", "dream"})),
                "remote_reader": bool(item.get("remote_reader", role in {"remote", "automation", "observer"})),
            }
        )
    return normalized


def render_agent_access_matrix(roster: list[dict[str, Any]]) -> str:
    lines = [
        "# Vault-for-LLM Agent Access Matrix",
        "",
        "Use this file as the reviewed roster for multi-agent memory sharing.",
        "",
        "| Agent | Role | Scope | Max sensitivity | Tool profile | Candidate write | Private memory | Remote reader |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in roster:
        lines.append(
            "| {agent_id} | {role} | {scope} | {max_sensitivity} | {tool_profile} | {can_write_candidates} | {private_memory} | {remote_reader} |".format(
                **item
            )
        )
    lines.extend(
        [
            "",
            "Rules:",
            "",
            "- Persona files, raw private chats, and high-sensitivity profile notes stay in each agent's private memory.",
            "- Shared project memory should be reviewed, source-backed, and usually `sensitivity: low` or `medium`.",
            "- Care/profile agents may publish reviewed L2 summaries, not raw private conversations.",
            "- Remote readers use `SUPABASE_ANON_KEY` or a scoped authenticated token, never the service role key.",
            "",
        ]
    )
    return "\n".join(lines)


def write_agent_roster_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    roster: str | list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = normalize_agent_roster(roster)
    if not normalized:
        return {}
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    env_dir = out / "agent-env"
    env_dir.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser()

    roster_path = out / "agent-roster.json"
    roster_path.write_text(json.dumps({"agents": normalized}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    matrix_path = out / "AGENT_ACCESS_MATRIX.md"
    matrix_path.write_text(render_agent_access_matrix(normalized), encoding="utf-8")

    command_lines = ["#!/usr/bin/env sh", "set -eu", ""]
    env_paths: dict[str, str] = {}
    for item in normalized:
        agent_id = item["agent_id"]
        env_path = env_dir / f"{agent_id}.env.example"
        env_path.write_text(
            "\n".join(
                [
                    f"VAULT_AGENT_ID={agent_id}",
                    f"VAULT_AGENT_ROLE={item['role']}",
                    f"VAULT_SCOPE={item['scope']}",
                    f"VAULT_MAX_SENSITIVITY={item['max_sensitivity']}",
                    f"VAULT_TOOL_PROFILE={item['tool_profile']}",
                    f"VAULT_PROJECT_DIR={project_path}",
                    "SUPABASE_URL=https://YOUR_PROJECT.supabase.co",
                    "SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        env_paths[agent_id] = str(env_path)
        command_lines.append(
            shell_join(
                [
                    "vault",
                    "setup-agent",
                    "--non-interactive",
                    "--agent",
                    agent_id,
                    "--scope",
                    "private" if item["private_memory"] else "shared",
                    "--agent-project-dir",
                    str(project_path),
                    "--features",
                    "core,mcp",
                    "--tool-profile",
                    item["tool_profile"],
                    "--json",
                ]
            )
        )

    commands_path = out / "agent-setup-commands.sh"
    commands_path.write_text("\n".join(command_lines) + "\n", encoding="utf-8")

    readme_path = out / "README-agent-roster.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Multi-Agent Roster",
                "",
                "Generated files:",
                "",
                "- `agent-roster.json`: machine-readable roster.",
                "- `AGENT_ACCESS_MATRIX.md`: human-reviewed sharing policy.",
                "- `agent-env/*.env.example`: per-agent environment examples.",
                "- `agent-setup-commands.sh`: local setup commands for each agent.",
                "",
                "Review the matrix before using these settings in production. This generator does not grant access by itself; it writes policy files and setup helpers.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "count": len(normalized),
        "roster": str(roster_path),
        "matrix": str(matrix_path),
        "commands": str(commands_path),
        "readme": str(readme_path),
        "env": env_paths,
    }


def write_memory_layout_manifest(
    *,
    output_dir: str | Path,
    agent: str,
    memory_layout: str,
    shared_project_dir: str | Path,
    private_project_dir: str | Path | None = None,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    safe_agent = _safe_slug(agent, default="generic")
    shared_path = Path(shared_project_dir).expanduser().resolve()
    private_path = Path(private_project_dir).expanduser().resolve() if private_project_dir else None
    payload: dict[str, Any] = {
        "version": 1,
        "agent": safe_agent,
        "memory_layout": memory_layout,
        "shared_project_dir": str(shared_path),
        "shared_db_path": str(shared_path / "vault.db"),
        "private_project_dir": str(private_path) if private_path else "",
        "private_db_path": str(private_path / "vault.db") if private_path else "",
        "rules": {
            "shared": "Reviewed project knowledge, SOPs, fixes, release process, benchmark evidence, and safety rules.",
            "private": "Agent identity, private preferences, personal notes, and agent-specific working style. Local-only by default.",
        },
        "startup_commands": [
            "vault update-status",
            f"vault automation handoff --project-dir {shared_path}",
        ],
    }
    manifest_path = out / "hybrid-vault-layout.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme_path = out / "README-hybrid-vault-layout.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Hybrid Vault Layout",
                "",
                "This setup separates shared project memory from private Agent memory.",
                "",
                f"- Agent: `{safe_agent}`",
                f"- Layout: `{memory_layout}`",
                f"- Shared project vault: `{shared_path}`",
                f"- Private Agent vault: `{private_path or ''}`",
                "",
                "Shared project memory is for reviewed project knowledge, SOPs, fixes, release process, benchmark evidence, and safety rules.",
                "Private Agent memory is local-only by default and is for identity, private preferences, personal notes, and agent-specific working style.",
                "",
                "Startup:",
                "",
                "```bash",
                "vault update-status",
                f"vault automation handoff --project-dir {shlex.quote(str(shared_path))}",
                "```",
                "",
                "This manifest is a coordination file. It is not an authorization policy and does not sync private memory.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {"manifest": str(manifest_path), "readme": str(readme_path)}


def write_mcp_startup_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    tool_profile: str,
    agent: str,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser().resolve()
    safe_agent = _safe_slug(agent, default="generic")
    payload = {
        "version": 1,
        "agent": safe_agent,
        "project_dir": str(project_path),
        "db_path": str(project_path / "vault.db"),
        "mcp_server": {
            "command": "vault-mcp",
            "args": [
                "--project-dir",
                str(project_path),
                "--tool-profile",
                tool_profile,
            ],
            "tool_profile": tool_profile,
        },
        "startup_sequence": [
            {
                "tool": "vault_update_status",
                "arguments": {
                    "read_status": True,
                    "agent_id": safe_agent,
                },
                "fallback_arguments": {
                    "latest_version": "",
                    "check_pypi": False,
                    "write_status": False,
                    "agent_id": safe_agent,
                },
                "purpose": "Read installed version, local Agent registry, shared/private vault paths, and startup commands.",
            },
            {
                "tool": "vault_automation_handoff",
                "arguments": {
                    "source": "auto",
                    "handoff_path": "",
                },
                "purpose": "Read the latest compact handoff when one exists.",
            },
            {
                "tool": "vault_search",
                "arguments": {
                    "query": "<user task or handoff keyword>",
                    "limit": 5,
                    "compact": True,
                },
                "purpose": "Search only when the handoff or task needs more context.",
            },
            {
                "tool": "vault_read_range",
                "arguments": {
                    "knowledge_id": "<id from search>",
                    "line_start": 1,
                    "line_end": 20,
                },
                "purpose": "Read bounded evidence before citing Vault memory.",
            },
            {
                "tool": "vault_memory_propose",
                "arguments": {
                    "title": "<short durable lesson>",
                    "content": "<reviewable memory>",
                    "reason": "<why this is worth remembering>",
                },
                "purpose": "Propose new durable memory as a candidate, not active knowledge.",
            },
        ],
        "safety": {
            "local_stdio_only": True,
            "check_pypi_default": False,
            "handoff_read_only": True,
            "auto_promote_memory": False,
            "read_raw_transcripts_by_default": False,
            "read_existing_update_status_first": True,
        },
    }
    json_path = out / "mcp-startup.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme_path = out / "README-mcp-startup.md"
    readme_path.write_text(
        "\n".join(
            [
                "# MCP Startup Guide",
                "",
                "Use this guide when an MCP-capable Agent connects to this Vault project.",
                "",
                "Server:",
                "",
                "```bash",
                f"vault-mcp --project-dir {shlex.quote(str(project_path))} --tool-profile {shlex.quote(tool_profile)}",
                "```",
                "",
                "Startup sequence:",
                "",
                f"1. `vault_update_status` with `read_status=true` and `agent_id={safe_agent}`",
                "2. `vault_automation_handoff`",
                "3. `vault_search` only when more context is needed",
                "4. `vault_read_range` before citing memory",
                "5. `vault_memory_propose` for new durable lessons",
                "",
                "Default safety:",
                "",
                "- first read the existing machine status file; if it is missing, call `vault_update_status` without `read_status`",
                "- keep `check_pypi=false` unless the user asks for a live update check",
                "- handoff reads are read-only and stay under `reports/automation`",
                "- do not read raw transcript contents by default",
                "- do not auto-promote memory",
                "- tool profiles reduce schema size but are not an authorization boundary",
                "",
                f"Machine-readable startup file: `{json_path.name}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json": str(json_path), "readme": str(readme_path)}


def write_update_status_templates(
    *,
    output_dir: str | Path,
    agent: str = "generic",
    vault_executable: str = "vault",
    interval_minutes: int = 60,
) -> dict[str, str]:
    from vault.agent_registry import update_status_path

    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    safe_agent = _safe_slug(agent, default="generic")
    status_path = update_status_path()
    write_command = [vault_executable, "update-status", "--write-status", "--json"]
    read_command = [vault_executable, "update-status", "--read-status", "--agent", safe_agent, "--json"]
    focus_command = [vault_executable, "update-status", "--agent", safe_agent, "--json"]
    contract = {
        "version": 1,
        "agent": safe_agent,
        "status_path": str(status_path),
        "read_command": shell_join(read_command),
        "write_command": shell_join(write_command),
        "focus_command": shell_join(focus_command),
        "mcp_read": {
            "tool": "vault_update_status",
            "arguments": {"read_status": True, "agent_id": safe_agent},
        },
        "mcp_fallback": {
            "tool": "vault_update_status",
            "arguments": {"latest_version": "", "check_pypi": False, "write_status": False, "agent_id": safe_agent},
        },
        "mcp_write": {
            "tool": "vault_update_status",
            "arguments": {"write_status": True, "check_pypi": False},
        },
        "safety": {
            "metadata_only": True,
            "check_pypi_default": False,
            "auto_upgrade": False,
            "shared_machine_status": True,
        },
    }
    contract_path = out / "update-status-contract.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    cron_path = out / "update-status.cron"
    cron_path.write_text(
        "\n".join(
            [
                "# Vault-for-LLM local Agent update status",
                f"*/{max(1, int(interval_minutes))} * * * * {shell_join(write_command)} >> $HOME/.vault-for-llm/update-status.log 2>&1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    launchagent_path = out / "update-status.launchagent.plist"
    launchagent_path.write_text(
        render_launchagent_plist(
            command=write_command,
            label="com.zycaskevin.vault-for-llm.update-status",
            interval_minutes=interval_minutes,
            log_basename="update-status",
        ),
        encoding="utf-8",
    )

    refresh_script_path = out / "refresh-update-status.sh"
    refresh_script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                "",
                f"VAULT=${{VAULT:-{shlex.quote(vault_executable)}}}",
                "",
                "\"$VAULT\" update-status --write-status --json >/dev/null",
                f"\"$VAULT\" update-status --doctor --max-status-age-minutes {max(1, int(interval_minutes))} --json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    refresh_script_path.chmod(0o755)

    rollout_path = out / "README-agent-update-rollout.md"
    rollout_path.write_text(
        "\n".join(
            [
                "# Agent Update Rollout",
                "",
                "Use this when one local runtime upgrades Vault-for-LLM and the other runtimes need to notice.",
                "",
                "After an upgrade or reinstall, refresh the shared machine notice:",
                "",
                "```bash",
                f"sh {shlex.quote(str(refresh_script_path))}",
                "```",
                "",
                "Manual equivalent:",
                "",
                "```bash",
                shell_join(write_command),
                f"{vault_executable} update-status --doctor --max-status-age-minutes {max(1, int(interval_minutes))}",
                "```",
                "",
                "What the doctor checks:",
                "",
                "- `update-status.json` exists",
                "- the notice is fresh enough for this install pack",
                "- every registered Agent appears in `agent_update_notices`",
                "- no registered Agent is behind the current runtime or latest known version",
                "",
                "Agents should still read with their own runtime id:",
                "",
                "```bash",
                shell_join(read_command),
                "```",
                "",
                "This is not an auto-upgrader. It is a shared local notice and a health check.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    readme_path = out / "README-update-status.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Agent Update Status",
                "",
                "This install pack lets multiple local Agent runtimes share one Vault-for-LLM update notice.",
                "",
                "Shared status file:",
                "",
                f"- `{status_path}`",
                "",
                "Read existing status without recomputing:",
                "",
                "```bash",
                shell_join(read_command),
                "```",
                "",
                "Write fresh local status without contacting PyPI:",
                "",
                "```bash",
                shell_join(write_command),
                "```",
                "",
                "MCP startup:",
                "",
                f"1. call `vault_update_status` with `read_status=true` and `agent_id={safe_agent}`",
                "2. if the result has `missing=true`, call `vault_update_status` with `check_pypi=false`",
                "3. only set `check_pypi=true` when the user asks for a live online version check",
                "",
                "Safety:",
                "",
                "- this is metadata only: versions, registered Agents, vault paths, and handoff commands",
                "- it is not an auto-upgrader",
                "- one updated runtime can write the status; other runtimes can read it",
                "- each runtime should pass its own `agent_id` to get `current_agent_notice` and `startup_checklist`",
                "- install or upgrade each Agent environment explicitly",
                "",
                f"Cron example: `{cron_path.name}`",
                f"LaunchAgent example: `{launchagent_path.name}`",
                f"Refresh script: `{refresh_script_path.name}`",
                f"Rollout guide: `{rollout_path.name}`",
                f"Machine-readable contract: `{contract_path.name}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "contract": str(contract_path),
        "readme": str(readme_path),
        "cron": str(cron_path),
        "launchagent": str(launchagent_path),
        "refresh_script": str(refresh_script_path),
        "rollout_readme": str(rollout_path),
    }


def write_agent_adapter_startup_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    tool_profile: str,
    agent: str,
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser().resolve()
    safe_agent = _safe_slug(agent, default="generic")
    read_status_command = [
        vault_executable,
        "update-status",
        "--read-status",
        "--agent",
        safe_agent,
        "--json",
    ]
    fallback_status_command = [
        vault_executable,
        "update-status",
        "--agent",
        safe_agent,
        "--json",
    ]
    handoff_command = [
        vault_executable,
        "automation",
        "handoff",
        "--project-dir",
        str(project_path),
    ]
    mcp_command = [
        "vault-mcp",
        "--project-dir",
        str(project_path),
        "--tool-profile",
        tool_profile,
    ]
    startup_sequence = [
        {
            "name": "read_update_status",
            "cli": shell_join(read_status_command),
            "mcp": {
                "tool": "vault_update_status",
                "arguments": {"read_status": True, "agent_id": safe_agent},
            },
            "fallback": {
                "cli": shell_join(fallback_status_command),
                "mcp": {
                    "tool": "vault_update_status",
                    "arguments": {
                        "latest_version": "",
                        "check_pypi": False,
                        "write_status": False,
                        "agent_id": safe_agent,
                    },
                },
            },
        },
        {
            "name": "read_automation_handoff",
            "cli": shell_join(handoff_command),
            "mcp": {
                "tool": "vault_automation_handoff",
                "arguments": {"source": "auto", "handoff_path": ""},
            },
        },
        {
            "name": "search_when_needed",
            "mcp": {
                "tool": "vault_search",
                "arguments": {"query": "<task keyword>", "limit": 5, "compact": True},
            },
        },
        {
            "name": "read_bounded_evidence",
            "mcp": {
                "tool": "vault_read_range",
                "arguments": {"knowledge_id": "<id>", "line_start": 1, "line_end": 40},
            },
        },
        {
            "name": "propose_durable_memory",
            "mcp": {
                "tool": "vault_memory_propose",
                "arguments": {
                    "title": "<durable lesson>",
                    "content": "<reviewable memory>",
                    "reason": "<why this should be remembered>",
                },
            },
        },
    ]
    adapters = {
        "codex": {
            "file": "codex-startup.md",
            "where_to_put": "project AGENTS.md or Codex project instructions",
            "note": "Use before touching code so Codex sees update status and handoff context first.",
        },
        "claude_code": {
            "file": "claude-code-startup.md",
            "where_to_put": "project CLAUDE.md or Claude Code project memory",
            "note": "Keep Vault startup short: status, handoff, then bounded searches.",
        },
        "openclaw": {
            "file": "openclaw-startup.md",
            "where_to_put": "OpenClaw workspace bootstrap or skill instructions",
            "note": "If a compact latest-context.md exists, read it before deeper Vault searches.",
        },
        "hermes": {
            "file": "hermes-startup.md",
            "where_to_put": "Hermes profile AGENTS.md, MEMORY.md, or runtime bootstrap",
            "note": "Point each profile at the same shared project vault but keep profile identity private.",
        },
    }
    contract = {
        "version": 1,
        "agent": safe_agent,
        "project_dir": str(project_path),
        "db_path": str(project_path / "vault.db"),
        "tool_profile": tool_profile,
        "mcp_server": {
            "command": "vault-mcp",
            "args": [
                "--project-dir",
                str(project_path),
                "--tool-profile",
                tool_profile,
            ],
        },
        "commands": {
            "read_update_status": shell_join(read_status_command),
            "fallback_update_status": shell_join(fallback_status_command),
            "handoff": shell_join(handoff_command),
            "mcp_server": shell_join(mcp_command),
        },
        "startup_sequence": startup_sequence,
        "adapters": adapters,
        "safety": {
            "auto_upgrade": False,
            "check_pypi_default": False,
            "read_raw_transcripts_by_default": False,
            "auto_promote_memory": False,
            "candidate_first_memory": True,
            "bounded_reads_before_citation": True,
            "tool_profile_is_not_auth": True,
        },
    }
    contract_path = out / "adapter-startup-contract.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def adapter_markdown(title: str, *, target: str, note: str, openclaw: bool = False) -> str:
        lines = [
            f"# {title}",
            "",
            f"Target location: {target}.",
            "",
            note,
            "",
            "Startup order:",
            "",
            f"1. Read update status: `{shell_join(read_status_command)}`.",
            f"2. If status is missing, run bounded fallback: `{shell_join(fallback_status_command)}`.",
            f"3. Read the compact automation handoff: `{shell_join(handoff_command)}`.",
            "4. Search only when the task needs more context.",
            "5. Use bounded reads before citing memory.",
            "6. Propose durable lessons as candidates; do not auto-promote them.",
            "",
            "MCP server:",
            "",
            "```bash",
            shell_join(mcp_command),
            "```",
            "",
            "First MCP calls:",
            "",
            f"- `vault_update_status` with `read_status=true`, `agent_id={safe_agent}`.",
            "- `vault_automation_handoff` with `source=auto`.",
            "- `vault_search` and `vault_read_range` only when needed.",
            "- `vault_memory_propose` for new durable lessons.",
            "",
            "Safety rules:",
            "",
            "- Do not auto-upgrade another Agent runtime.",
            "- Do not read raw transcript contents by default.",
            "- Do not auto-promote memory.",
            "- Treat tool profiles as schema-size filters, not permissions.",
            "",
        ]
        if openclaw:
            lines.extend(
                [
                    "OpenClaw note:",
                    "",
                    "- If `latest-context.md` exists in the workspace, read that compact context first.",
                    "- Use Vault search only when the compact context is not enough.",
                    "",
                ]
            )
        lines.extend(
            [
                f"Machine-readable contract: `{contract_path.name}`",
                "",
            ]
        )
        return "\n".join(lines)

    files: dict[str, str] = {"contract": str(contract_path)}
    for adapter_id, adapter in adapters.items():
        filename = adapter["file"]
        path = out / filename
        path.write_text(
            adapter_markdown(
                {
                    "codex": "Codex Startup Template",
                    "claude_code": "Claude Code Startup Template",
                    "openclaw": "OpenClaw Startup Template",
                    "hermes": "Hermes Agent Startup Template",
                }[adapter_id],
                target=adapter["where_to_put"],
                note=adapter["note"],
                openclaw=adapter_id == "openclaw",
            ),
            encoding="utf-8",
        )
        files[adapter_id] = str(path)

    readme_path = out / "README-agent-adapters.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Agent Adapter Startup Templates",
                "",
                "Use these templates when one machine has multiple Agent runtimes connected to the same Vault project.",
                "",
                "The shared rule is simple: update-status -> automation handoff -> search/read/propose.",
                "",
                "Generated files:",
                "",
                "- `codex-startup.md`",
                "- `claude-code-startup.md`",
                "- `openclaw-startup.md`",
                "- `hermes-startup.md`",
                "- `adapter-startup-contract.json`",
                "",
                "What each Agent should do at startup:",
                "",
                f"1. Read the shared update notice with `{shell_join(read_status_command)}`.",
                f"2. If no notice exists, run `{shell_join(fallback_status_command)}` without a live PyPI check.",
                f"3. Read `{shell_join(handoff_command)}` for the latest compact memory automation handoff.",
                "4. Search only when the task or handoff needs more detail.",
                "5. Read bounded evidence before citing memory.",
                "6. Propose new durable memory as candidates.",
                "",
                "Safety boundary:",
                "",
                "- no auto-upgrade",
                "- no raw transcript reads by default",
                "- no automatic memory promotion",
                "- one shared project vault can coexist with private per-Agent identity/profile memory",
                "- tool profiles reduce token/schema size but are not an authorization boundary",
                "",
                f"MCP server command: `{shell_join(mcp_command)}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    files["readme"] = str(readme_path)
    return files


def _normalize_validation_pack_targets(raw: str | list[str] | None) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    else:
        parts = [str(part).strip().lower() for part in raw if str(part).strip()]
    if not parts or "none" in parts:
        return set()
    unknown = [part for part in parts if part not in VALID_VALIDATION_PACK_TARGETS]
    if unknown:
        allowed = ", ".join(sorted(VALID_VALIDATION_PACK_TARGETS))
        raise ValueError(f"unknown validation pack target '{unknown[0]}' (expected one of: {allowed})")
    if "all" in parts:
        return {"remote", "n8n", "coze"}
    return set(parts)


def write_live_validation_pack(
    *,
    output_dir: str | Path,
    agent: str,
    targets: str | list[str] = "all",
    query: str = "deployment SOP",
) -> dict[str, str]:
    selected = _normalize_validation_pack_targets(targets)
    if not selected:
        return {}
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    safe_agent = _safe_slug(agent, default="generic")
    safe_query = str(query or "deployment SOP")
    written: dict[str, str] = {}

    if "remote" in selected:
        path = out / "validate-remote-reader.sh"
        path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    ": \"${SUPABASE_URL:?Set SUPABASE_URL first}\"",
                    ": \"${SUPABASE_ANON_KEY:?Set SUPABASE_ANON_KEY first}\"",
                    shell_join(["vault", "remote", "smoke", "--agent-id", safe_agent, "--query", safe_query, "--json"]),
                    shell_join(["vault", "remote", "search", safe_query, "--agent-id", safe_agent, "--json"]),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["remote"] = str(path)

    if "n8n" in selected:
        path = out / "VALIDATE-n8n.md"
        path.write_text(
            "\n".join(
                [
                    "# Validate n8n Remote Reader",
                    "",
                    "1. Import `n8n-remote-reader.workflow.json` from the same `agent-install/` directory.",
                    "2. Ensure the n8n host can run the `vault` CLI.",
                    "3. Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the n8n process environment.",
                    "4. Run the manual trigger and confirm the command output contains `vault_search_readable` results.",
                    "5. Do not place `SUPABASE_SERVICE_ROLE_KEY` in n8n unless n8n is the trusted sync host.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["n8n"] = str(path)

    if "coze" in selected:
        path = out / "VALIDATE-coze.md"
        path.write_text(
            "\n".join(
                [
                    "# Validate Coze Remote Reader",
                    "",
                    "1. Import `coze-supabase-vault-openapi.json` as the Coze connector schema.",
                    "2. Replace `https://YOUR_PROJECT.supabase.co/rest/v1` with your Supabase REST endpoint.",
                    "3. Configure the Supabase anon key as both the `apikey` header and the bearer value for the authorization header.",
                    "4. Call `vaultRemoteSearch` with `p_agent_id`, `p_query`, `p_include_private=false`, `p_max_sensitivity=medium`, and `p_limit=5`.",
                    "5. Confirm responses contain safe summaries and do not expose `content_raw`.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["coze"] = str(path)

    readme = out / "README-live-validation.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Live Validation Pack",
                "",
                "Use this after the local setup, Supabase schema, read policy, and first sync are complete.",
                "",
                "Validation order:",
                "",
                "1. Run `validate-remote-reader.sh` on a trusted machine.",
                "2. Import and run the n8n workflow if n8n is part of the deployment.",
                    "3. Import and call the Coze OpenAPI connector if Coze or another hosted agent is part of the deployment.",
                "",
                "Passing local tests does not prove remote credentials or hosted platform settings. This pack verifies the external deployment without exposing service-role credentials to hosted agents.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def render_memory_agents_guide(
    *,
    project_dir: str | Path,
    agent: str,
    language: str = "en",
) -> str:
    project_path = Path(project_dir).expanduser()
    safe_language = _normalize_setup_language(language)
    if safe_language == "zh-Hant":
        lines = [
            "# Vault-for-LLM 記憶 Agent 設定",
            "",
            "這份文件給 Profile / Dream / Forgetting agent 使用。",
            "",
            "預設政策：",
            "",
            "- Profile agent 預設只產生候選記憶，不直接寫入 active memory。",
            "- Dream agent 預設只產生 report，不直接刪除或 promote。",
            "- Forgetting agent 預設只建議 archive、expire、merge 或降權，不自動刪除。",
            "- 原始私密對話不同步到 shared vault 或 Supabase，除非使用者明確同意。",
            "- 共享人格側寫只允許 reviewed summary，不共享 raw private interaction。",
            "",
            "建議生命週期：",
            "",
            "```text",
            "capture -> candidate -> review -> active -> dream -> consolidate -> archive/expire",
            "```",
            "",
            "建議 metadata：",
            "",
            "```yaml",
            "scope: private | project | shared | public",
            "sensitivity: low | medium | high | restricted",
            f"owner_agent: {agent}",
            "allowed_agents: []",
            "status: candidate | reviewed | active | archived",
            "memory_type: user_profile | care_summary | dream_report | forgetting_suggestion",
            "expires_at: null",
            "```",
            "",
            "建議執行方式：",
            "",
            f"- Project vault: `{project_path}`",
            "- Profile agent：整理 L0/L1/L2 側寫候選，等待使用者或 trusted agent review。",
            "- Dream agent：定期執行 `vault dream`，輸出整理報告。",
            "- Forgetting agent：根據 dream report 產生 archive/expire 建議，不直接刪除。",
        ]
    elif safe_language == "zh-CN":
        lines = [
            "# Vault-for-LLM 记忆 Agent 设置",
            "",
            "这份文件给 Profile / Dream / Forgetting agent 使用。",
            "",
            "默认政策：",
            "",
            "- Profile agent 默认只产生候选记忆，不直接写入 active memory。",
            "- Dream agent 默认只产生 report，不直接删除或 promote。",
            "- Forgetting agent 默认只建议 archive、expire、merge 或降权，不自动删除。",
            "- 原始私密对话不同步到 shared vault 或 Supabase，除非用户明确同意。",
            "- 共享人格侧写只允许 reviewed summary，不共享 raw private interaction。",
            "",
            "建议生命周期：",
            "",
            "```text",
            "capture -> candidate -> review -> active -> dream -> consolidate -> archive/expire",
            "```",
            "",
            "建议 metadata：",
            "",
            "```yaml",
            "scope: private | project | shared | public",
            "sensitivity: low | medium | high | restricted",
            f"owner_agent: {agent}",
            "allowed_agents: []",
            "status: candidate | reviewed | active | archived",
            "memory_type: user_profile | care_summary | dream_report | forgetting_suggestion",
            "expires_at: null",
            "```",
            "",
            "建议执行方式：",
            "",
            f"- Project vault: `{project_path}`",
            "- Profile agent：整理 L0/L1/L2 侧写候选，等待用户或 trusted agent review。",
            "- Dream agent：定期执行 `vault dream`，输出整理报告。",
            "- Forgetting agent：根据 dream report 产生 archive/expire 建议，不直接删除。",
        ]
    else:
        lines = [
            "# Vault-for-LLM Memory Agents",
            "",
            "Use this guide for Profile / Dream / Forgetting agents.",
            "",
            "Default policy:",
            "",
            "- Profile agents produce candidate memories; they do not write active memory directly.",
            "- Dream agents produce reports; they do not delete or promote memory directly.",
            "- Forgetting agents suggest archive, expiry, merge, or downgrade actions; they do not auto-delete.",
            "- Raw private conversations do not sync to shared vaults or Supabase unless the user explicitly approves.",
            "- Shared user profiles should be reviewed summaries, not raw private interactions.",
            "",
            "Recommended lifecycle:",
            "",
            "```text",
            "capture -> candidate -> review -> active -> dream -> consolidate -> archive/expire",
            "```",
            "",
            "Recommended metadata:",
            "",
            "```yaml",
            "scope: private | project | shared | public",
            "sensitivity: low | medium | high | restricted",
            f"owner_agent: {agent}",
            "allowed_agents: []",
            "status: candidate | reviewed | active | archived",
            "memory_type: user_profile | care_summary | dream_report | forgetting_suggestion",
            "expires_at: null",
            "```",
            "",
            "Recommended operation:",
            "",
            f"- Project vault: `{project_path}`",
            "- Profile agent: propose L0/L1/L2 profile candidates for user or trusted-agent review.",
            "- Dream agent: run `vault dream` on a schedule and write review reports.",
            "- Forgetting agent: convert dream findings into archive/expiry suggestions, not direct deletion.",
        ]
    return "\n".join(lines) + "\n"


def write_memory_agents_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    agent: str,
    language: str = "en",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "README-memory-agents.md"
    path.write_text(
        render_memory_agents_guide(
            project_dir=project_dir,
            agent=agent,
            language=language,
        ),
        encoding="utf-8",
    )
    return {"guide": str(path), "mode": "report_only_candidate_only"}


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


def write_sync_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    obsidian_vault: str | Path,
    targets: str | list[str] = "all",
    interval_minutes: int = 15,
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_sync_targets(targets)
    command = obsidian_sync_command(
        project_dir=project_dir,
        obsidian_vault=obsidian_vault,
        vault_executable=vault_executable,
    )

    written: dict[str, str] = {}
    if "cron" in selected:
        path = out / "obsidian-sync.cron"
        path.write_text(render_cron_template(command=command, interval_minutes=interval_minutes), encoding="utf-8")
        written["cron"] = str(path)
    if "launchagent" in selected:
        path = out / "com.zycaskevin.vault-for-llm.obsidian-sync.plist"
        path.write_text(
            render_launchagent_plist(command=command, interval_minutes=interval_minutes),
            encoding="utf-8",
        )
        written["launchagent"] = str(path)
    if "n8n" in selected:
        path = out / "n8n-obsidian-sync.workflow.json"
        path.write_text(render_n8n_workflow(command=command, interval_minutes=interval_minutes), encoding="utf-8")
        written["n8n"] = str(path)

    readme = out / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Obsidian Sync Templates",
                "",
                "Generated command:",
                "",
                f"```bash\n{shell_join(command)}\n```",
                "",
                "Review paths before enabling any scheduled job.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def render_local_smoke_script(*, project_dir: str | Path, vault_executable: str = "vault") -> str:
    project = shlex.quote(str(Path(project_dir).expanduser()))
    return "\n".join(
        [
            "#!/usr/bin/env sh",
            "set -eu",
            f"PROJECT_DIR={project}",
            f"VAULT=${{VAULT:-{shlex.quote(vault_executable)}}}",
            "PYTHON=${PYTHON:-python3}",
            "SMOKE_ID=\"$(date +%Y%m%d%H%M%S)-$$\"",
            "TITLE=\"Vault local smoke ${SMOKE_ID}\"",
            "CANDIDATE_TITLE=\"Vault local smoke candidate ${SMOKE_ID}\"",
            "CONTENT=\"Vault-for-LLM local smoke ${SMOKE_ID}: add/search-json/remember/candidates works.\"",
            "",
            "$VAULT add \"$TITLE\" \\",
            "  --project-dir \"$PROJECT_DIR\" \\",
            "  --content \"$CONTENT\" \\",
            "  --category setup \\",
            "  --tags smoke,setup \\",
            "  --trust 0.9 \\",
            "  --source setup-agent >/dev/null",
            "",
            "SEARCH_JSON=\"$($VAULT search \"$TITLE\" --project-dir \"$PROJECT_DIR\" --keyword-only --limit 5 --json)\"",
            "export SEARCH_JSON TITLE",
            "$PYTHON - <<'PY'",
            "import json, os",
            "payload = json.loads(os.environ['SEARCH_JSON'])",
            "title = os.environ['TITLE']",
            "if payload.get('count', 0) < 1:",
            "    raise SystemExit(f'search returned no results: {payload!r}')",
            "if not any(item.get('title') == title for item in payload.get('results', [])):",
            "    raise SystemExit(f'search did not return smoke title: {payload!r}')",
            "PY",
            "",
            "$VAULT remember \"$CANDIDATE_TITLE\" \\",
            "  --project-dir \"$PROJECT_DIR\" \\",
            "  --content \"Candidate-only smoke memory created during agent setup validation.\" \\",
            "  --reason \"Verify candidate memory workflow after agent installation.\" \\",
            "  --mode candidate \\",
            "  --category setup \\",
            "  --tags smoke,setup \\",
            "  --source setup-agent \\",
            "  --source-ref \"local-smoke:${SMOKE_ID}\" >/dev/null",
            "",
            "CANDIDATES_JSON=\"$($VAULT candidates --project-dir \"$PROJECT_DIR\" --pretty)\"",
            "export CANDIDATES_JSON CANDIDATE_TITLE",
            "$PYTHON - <<'PY'",
            "import json, os",
            "payload = json.loads(os.environ['CANDIDATES_JSON'])",
            "title = os.environ['CANDIDATE_TITLE']",
            "if payload.get('count', 0) < 1:",
            "    raise SystemExit(f'candidate list is empty: {payload!r}')",
            "if not any(item.get('title') == title for item in payload.get('candidates', [])):",
            "    raise SystemExit(f'candidate list did not include smoke candidate: {payload!r}')",
            "PY",
            "",
            "export PROJECT_DIR",
            "$PYTHON - <<'PY'",
            "import json, os",
            "from vault.mcp import _set_project_dir, handle_tool_call, select_tools",
            "_set_project_dir(os.environ['PROJECT_DIR'])",
            "core = [tool['name'] for tool in select_tools('core')]",
            "required = {'vault_update_status', 'vault_automation_handoff'}",
            "missing = sorted(required - set(core))",
            "if missing:",
            "    raise SystemExit(f'MCP core profile missing startup tools: {missing}')",
            "status = json.loads(handle_tool_call('vault_update_status', {})['result'])",
            "if 'installed_version' not in status or 'startup_commands' not in status:",
            "    raise SystemExit(f'invalid update status payload: {status!r}')",
            "handoff = json.loads(handle_tool_call('vault_automation_handoff', {})['result'])",
            "if handoff.get('action') != 'handoff' or not handoff.get('safety', {}).get('read_only'):",
            "    raise SystemExit(f'invalid handoff payload: {handoff!r}')",
            "PY",
            "",
            "echo \"local_smoke=ok\"",
            "",
        ]
    )


def write_local_smoke_template(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    script_path = out / "local-smoke.sh"
    script_path.write_text(
        render_local_smoke_script(project_dir=project_dir, vault_executable=vault_executable),
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    return {"script": str(script_path)}


def _normalize_sync_targets(targets: str | list[str]) -> set[str]:
    if isinstance(targets, str):
        selected = {part.strip() for part in targets.split(",") if part.strip()}
    else:
        selected = {str(part).strip() for part in targets if str(part).strip()}
    if not selected or "none" in selected:
        return set()
    if "all" in selected:
        return {"cron", "launchagent", "n8n"}
    unknown = selected - VALID_SYNC_TARGETS
    if unknown:
        raise ValueError(f"unknown sync target(s): {', '.join(sorted(unknown))}")
    return selected


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


def _normalize_memory_layout(layout: str | None) -> str:
    value = str(layout or "hybrid").strip().lower()
    if value not in VALID_MEMORY_LAYOUTS:
        allowed = ", ".join(sorted(VALID_MEMORY_LAYOUTS))
        raise ValueError(f"unknown memory layout '{layout}' (expected one of: {allowed})")
    return value


@dataclass
class AgentSetupConfig:
    project_dir: Path
    scope: str = "private"
    agent: str = "generic"
    memory_layout: str = "hybrid"
    agent_private_dir: Path | None = None
    features: list[str] = field(default_factory=lambda: list(DEFAULT_FEATURES))
    language: str = "en"
    tool_profile: str = "core"
    install_optional_deps: bool = False
    install_embedding_model: str | None = None
    obsidian_vault: Path | None = None
    import_obsidian: bool = False
    obsidian_dry_run_first: bool = True
    sync_targets: str | list[str] = "none"
    sync_interval_minutes: int = 15
    supabase_sync_targets: str | list[str] = "none"
    supabase_sync_interval_minutes: int = DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES
    supabase_setup_mode: str = "simple"
    remote_reader_targets: str | list[str] = "none"
    remote_reader_query: str = "deployment SOP"
    agent_roster: str | list[dict[str, Any]] | None = None
    validation_pack_targets: str | list[str] = "none"
    automation_schedule_targets: str | list[str] = "none"
    automation_interval_minutes: int = DEFAULT_AUTOMATION_INTERVAL_MINUTES
    automation_mode: str = "balanced"
    automation_command: str = "cycle"
    automation_apply: bool = False
    automation_write_workspace: bool = False
    automation_workspace_inbox_limit: int = 5
    automation_include_transcripts: bool = False
    automation_transcript_limit: int = 5
    template_dir: Path | None = None
    allow_private: bool = False
    stable_venv_path: Path | None = None


def run_agent_setup(config: AgentSetupConfig) -> dict[str, Any]:
    project_path = ensure_project(config.project_dir)
    features = normalize_features(config.features)
    language = _normalize_setup_language(config.language)
    memory_layout = _normalize_memory_layout(config.memory_layout)
    private_project_path: Path | None = None
    if memory_layout in {"hybrid", "private"}:
        private_project_path = ensure_project(config.agent_private_dir or default_agent_private_dir(config.agent))
    optional_dependency_install = None
    if config.install_optional_deps:
        optional_dependency_install = install_optional_dependencies(features)
    embedding_model_install = None
    if config.install_embedding_model:
        if "semantic" not in features:
            raise ValueError("install_embedding_model requires the semantic feature")
        embedding_model_install = install_embedding_model(
            config.install_embedding_model,
            project_dir=project_path,
        )
    feature_next_steps = optional_feature_next_steps(
        features,
        project_dir=project_path,
        installed_deps=bool(config.install_optional_deps),
        installed_embedding_model=config.install_embedding_model,
    )
    environment_warnings = python_environment_warnings()
    result: dict[str, Any] = {
        "version": __version__,
        "project_dir": str(project_path),
        "scope": config.scope,
        "agent": config.agent,
        "memory_layout": memory_layout,
        "agent_private_dir": str(private_project_path) if private_project_path else "",
        "features": features,
        "language": language,
        "tool_profile": config.tool_profile,
        "optional_dependency_install": optional_dependency_install,
        "embedding_model_install": embedding_model_install,
        "environment_warnings": environment_warnings,
        "db_path": str(project_path / "vault.db"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "obsidian": None,
        "sync_templates": {},
        "supabase_setup": {},
        "supabase_sync_templates": {},
        "remote_reader_templates": {},
        "agent_roster": {},
        "live_validation_pack": {},
        "memory_agents": {},
        "automation_schedule_templates": {},
        "local_smoke": {},
        "stable_venv": {},
        "memory_layout_files": {},
        "mcp_startup": {},
        "update_status_templates": {},
        "agent_adapter_startup": {},
        "agent_registry": {},
        "next_steps": [
            f"vault search \"test query\" --project-dir {shlex.quote(str(project_path))} --limit 5 --json",
            f"vault-mcp --project-dir {shlex.quote(str(project_path))} --tool-profile {shlex.quote(config.tool_profile)}",
        ]
        + feature_next_steps,
    }
    result["agent_registry"] = register_agent(
        agent=config.agent,
        project_dir=project_path,
        scope=config.scope,
        features=features,
        tool_profile=config.tool_profile,
        source="setup-agent",
        memory_layout=memory_layout,
        private_project_dir=private_project_path,
    )
    result["next_steps"].insert(0, "Check local agent registry and update status: vault update-status")
    template_dir = config.template_dir or (project_path / "agent-install")
    result["memory_layout_files"] = write_memory_layout_manifest(
        output_dir=template_dir,
        agent=config.agent,
        memory_layout=memory_layout,
        shared_project_dir=project_path,
        private_project_dir=private_project_path,
    )
    result["next_steps"].append(f"Review memory layout manifest: {result['memory_layout_files']['manifest']}")
    result["mcp_startup"] = write_mcp_startup_guide(
        output_dir=template_dir,
        project_dir=project_path,
        tool_profile=config.tool_profile,
        agent=config.agent,
    )
    result["next_steps"].append(f"Review MCP startup guide: {result['mcp_startup']['readme']}")
    result["update_status_templates"] = write_update_status_templates(
        output_dir=template_dir,
        agent=config.agent,
    )
    result["next_steps"].append(f"Review Agent update status guide: {result['update_status_templates']['readme']}")
    result["next_steps"].append(f"Run update rollout health check: {result['update_status_templates']['refresh_script']}")
    result["agent_adapter_startup"] = write_agent_adapter_startup_templates(
        output_dir=template_dir,
        project_dir=project_path,
        tool_profile=config.tool_profile,
        agent=config.agent,
    )
    result["next_steps"].append(f"Review Agent adapter startup guide: {result['agent_adapter_startup']['readme']}")
    result["local_smoke"] = write_local_smoke_template(
        output_dir=template_dir,
        project_dir=project_path,
    )
    result["next_steps"].insert(0, f"Run local smoke test: {result['local_smoke']['script']}")
    if environment_warnings:
        result["next_steps"].append(
            "Move temporary Python virtualenvs to a stable path such as ~/.hermes/venvs/vault-for-llm/ before relying on scheduled jobs."
        )

    if "memory_agents" in features:
        result["memory_agents"] = write_memory_agents_guide(
            output_dir=template_dir,
            project_dir=project_path,
            agent=config.agent,
            language=language,
        )
        result["next_steps"].append(
            f"Review memory agents guide: {result['memory_agents']['guide']}"
        )

    if config.stable_venv_path:
        result["stable_venv"] = write_stable_venv_template(
            output_dir=template_dir,
            project_dir=project_path,
            venv_path=config.stable_venv_path,
            agent=config.agent,
            scope=config.scope,
            features=features,
            tool_profile=config.tool_profile,
            install_embedding_model=config.install_embedding_model,
        )
        result["next_steps"].append(
            f"Run stable venv bootstrap: sh {shlex.quote(result['stable_venv']['script'])}"
        )

    if config.obsidian_vault:
        obsidian_payload: dict[str, Any] = {"vault": str(config.obsidian_vault)}
        if config.obsidian_dry_run_first:
            obsidian_payload["dry_run"] = sync_obsidian_vault(
                project_dir=project_path,
                vault_dir=config.obsidian_vault,
                dry_run=True,
                allow_private=config.allow_private,
            )
        if config.import_obsidian:
            obsidian_payload["import"] = sync_obsidian_vault(
                project_dir=project_path,
                vault_dir=config.obsidian_vault,
                dry_run=False,
                allow_private=config.allow_private,
            )
            obsidian_payload["compile"] = compile_project(project_path, allow_private=config.allow_private)
        result["obsidian"] = obsidian_payload

        targets = _normalize_sync_targets(config.sync_targets)
        if targets:
            result["sync_templates"] = write_sync_templates(
                output_dir=template_dir,
                project_dir=project_path,
                obsidian_vault=config.obsidian_vault,
                targets=sorted(targets),
                interval_minutes=config.sync_interval_minutes,
            )

    if "supabase" in features:
        result["supabase_setup"] = write_supabase_setup_guide(
            output_dir=template_dir,
            project_dir=project_path,
            agent=config.agent,
            mode=config.supabase_setup_mode,
            language=language,
        )
        if result["supabase_setup"]:
            result["next_steps"].append(
                f"Review Supabase setup guide: {result['supabase_setup']['guide']}"
            )

    supabase_targets = _normalize_sync_targets(config.supabase_sync_targets)
    if "supabase" in features and supabase_targets:
        result["supabase_sync_templates"] = write_supabase_sync_templates(
            output_dir=template_dir,
            project_dir=project_path,
            targets=sorted(supabase_targets),
            interval_minutes=config.supabase_sync_interval_minutes,
        )

    remote_reader_targets = _normalize_remote_reader_targets(config.remote_reader_targets)
    if "supabase" in features and remote_reader_targets:
        result["remote_reader_templates"] = write_remote_reader_templates(
            output_dir=template_dir,
            agent=config.agent,
            targets=sorted(remote_reader_targets),
            query=config.remote_reader_query,
        )
        if result["remote_reader_templates"]:
            result["next_steps"].append(
                f"Run remote reader smoke test: {result['remote_reader_templates'].get('shell') or 'vault remote smoke'}"
            )

    if config.agent_roster:
        result["agent_roster"] = write_agent_roster_templates(
            output_dir=template_dir,
            project_dir=project_path,
            roster=config.agent_roster,
        )
        if result["agent_roster"]:
            result["next_steps"].append(f"Review agent access matrix: {result['agent_roster']['matrix']}")

    validation_targets = _normalize_validation_pack_targets(config.validation_pack_targets)
    if validation_targets:
        result["live_validation_pack"] = write_live_validation_pack(
            output_dir=template_dir,
            agent=config.agent,
            targets=sorted(validation_targets),
            query=config.remote_reader_query,
        )
        if result["live_validation_pack"]:
            result["next_steps"].append(f"Run live validation checklist: {result['live_validation_pack']['readme']}")

    automation_targets = _normalize_sync_targets(config.automation_schedule_targets)
    if automation_targets:
        result["automation_schedule_templates"] = write_automation_schedule_templates(
            output_dir=template_dir,
            project_dir=project_path,
            targets=sorted(automation_targets),
            interval_minutes=config.automation_interval_minutes,
            mode=config.automation_mode,
            command=config.automation_command,
            apply=config.automation_apply,
            write_workspace=config.automation_write_workspace,
            workspace_inbox_limit=config.automation_workspace_inbox_limit,
            include_transcripts=config.automation_include_transcripts,
            transcript_limit=config.automation_transcript_limit,
        )
        result["next_steps"].append(
            f"Review memory automation schedule: {result['automation_schedule_templates']['readme']}"
        )
        result["next_steps"].append(
            f"Next agent startup handoff: vault automation handoff --project-dir {project_path}"
        )

    return result


def default_stable_venv_path() -> Path:
    return Path("~/.hermes/venvs/vault-for-llm").expanduser()


def _pypi_install_target_for_features(features: list[str]) -> str:
    selected = normalize_features(features)
    extras = [feature for feature in ["mcp", "semantic", "supabase", "dev"] if feature in selected]
    if extras:
        return f"vault-for-llm[{','.join(extras)}]=={__version__}"
    return f"vault-for-llm=={__version__}"


def render_stable_venv_script(
    *,
    venv_path: str | Path,
    project_dir: str | Path,
    agent: str,
    scope: str,
    features: list[str],
    tool_profile: str,
    install_embedding_model: str | None = None,
) -> str:
    selected = normalize_features(features)
    install_target = _pypi_install_target_for_features(selected)
    project_path = Path(project_dir).expanduser()
    venv = Path(venv_path).expanduser()
    setup_command = [
        '"$VENV/bin/vault"',
        "setup-agent",
        "--non-interactive",
        "--agent",
        agent,
        "--scope",
        scope,
        "--agent-project-dir",
        str(project_path),
        "--features",
        ",".join(selected),
        "--tool-profile",
        tool_profile,
        "--json",
    ]
    if install_embedding_model:
        setup_command.extend(["--install-embedding-model", install_embedding_model])

    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        "",
        f"VENV={shlex.quote(str(venv))}",
        f"PROJECT_DIR={shlex.quote(str(project_path))}",
        "",
        "mkdir -p \"$(dirname \"$VENV\")\"",
        "python3 -m venv \"$VENV\"",
        "\"$VENV/bin/python\" -m pip install --upgrade pip",
        f"\"$VENV/bin/python\" -m pip install {shlex.quote(install_target)}",
    ]
    if "headroom" in selected:
        lines.append("\"$VENV/bin/python\" -m pip install headroom-ai")
    lines.extend(
        [
            "\"$VENV/bin/vault\" --version",
            "mkdir -p \"$PROJECT_DIR\"",
            " ".join(shlex.quote(part) if "$" not in part else part for part in setup_command),
            "",
        ]
    )
    return "\n".join(lines)


def render_stable_venv_readme(*, venv_path: str | Path, script_path: str | Path) -> str:
    return "\n".join(
        [
            "# Stable Python Virtualenv",
            "",
            "This template creates a long-lived Python virtualenv for Vault-for-LLM.",
            "Use it for scheduled jobs, MCP commands, Supabase sync, and agent runtimes.",
            "",
            f"Recommended venv path: `{Path(venv_path).expanduser()}`",
            "",
            "Run:",
            "",
            "```bash",
            f"sh {shlex.quote(str(script_path))}",
            "```",
            "",
            "After it succeeds, point scheduled jobs and agent MCP commands at the",
            "`vault` and `vault-mcp` executables inside that venv instead of a",
            "temporary `/tmp/...` virtualenv.",
            "",
        ]
    )


def write_stable_venv_template(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    venv_path: str | Path,
    agent: str,
    scope: str,
    features: list[str],
    tool_profile: str,
    install_embedding_model: str | None = None,
) -> dict[str, Any]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    script_path = out / "setup-stable-venv.sh"
    script_path.write_text(
        render_stable_venv_script(
            venv_path=venv_path,
            project_dir=project_dir,
            agent=agent,
            scope=scope,
            features=features,
            tool_profile=tool_profile,
            install_embedding_model=install_embedding_model,
        ),
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    readme_path = out / "README-stable-venv.md"
    readme_path.write_text(
        render_stable_venv_readme(venv_path=venv_path, script_path=script_path),
        encoding="utf-8",
    )
    return {
        "venv_path": str(Path(venv_path).expanduser()),
        "script": str(script_path),
        "readme": str(readme_path),
    }


def install_optional_dependencies(features: list[str]) -> dict[str, Any]:
    selected = normalize_features(features)
    commands: list[list[str]] = []
    extras = [feature for feature in ["mcp", "semantic", "supabase", "dev"] if feature in selected]
    if extras:
        commands.append(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                f"vault-for-llm[{','.join(extras)}]=={__version__}",
            ]
        )
    if "headroom" in selected:
        commands.append([sys.executable, "-m", "pip", "install", "headroom-ai"])

    results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        item = {
            "command": shell_join(command),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
        results.append(item)
        if completed.returncode != 0:
            raise RuntimeError(
                "optional dependency install failed: "
                f"{shell_join(command)}\n{completed.stderr[-2000:]}"
            )

    return {
        "installed": bool(commands),
        "features": selected,
        "commands": [shell_join(command) for command in commands],
        "results": results,
    }


def python_environment_warnings() -> list[str]:
    """Warn agents when Vault was installed into a disposable temp environment."""
    prefixes = {
        str(Path(tempfile.gettempdir()).resolve()),
        "/tmp",
        "/private/tmp",
        "/var/tmp",
        "/private/var/tmp",
    }
    candidates = {
        "sys_prefix": str(Path(sys.prefix).expanduser()),
        "sys_executable": str(Path(sys.executable).expanduser()),
    }
    warnings: list[str] = []
    for label, raw_path in candidates.items():
        path = str(Path(raw_path).resolve())
        if any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes):
            warnings.append(
                f"{label} is under a temporary directory ({raw_path}); use a stable venv such as ~/.hermes/venvs/vault-for-llm/ for long-lived agent installs."
            )
    return warnings


def install_embedding_model(model_key: str, *, project_dir: str | Path) -> dict[str, Any]:
    model = str(model_key).strip().lower()
    if model not in VALID_EMBEDDING_MODELS:
        allowed = ", ".join(sorted(VALID_EMBEDDING_MODELS))
        raise ValueError(f"unknown embedding model '{model_key}' (expected one of: {allowed})")

    command = [
        sys.executable,
        "-m",
        "vault.cli",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "install-embedding",
        "--model",
        model,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    result = {
        "model": model,
        "command": shell_join(command),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    if completed.returncode != 0:
        raise RuntimeError(
            "embedding model install failed: "
            f"{shell_join(command)}\n{completed.stderr[-2000:]}"
        )
    return result


def optional_feature_next_steps(
    features: list[str],
    *,
    project_dir: str | Path,
    installed_deps: bool = False,
    installed_embedding_model: str | None = None,
) -> list[str]:
    project_path = Path(project_dir).expanduser()
    steps: list[str] = []
    if "semantic" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[semantic]"')
        if not installed_embedding_model:
            steps.append("vault install-embedding --model mix")
        steps.append(
            f"vault semantic rebuild --project-dir {shlex.quote(str(project_path))} --persist-cache --pretty"
        )
    if "supabase" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[supabase]"')
        steps.append(
            "Use Supabase only for cross-host/team/shared-memory sync; skip it when local vault.db is enough."
        )
        steps.append("configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before running sync scripts")
        steps.append("use SUPABASE_ANON_KEY, not the service role key, for remote reader agents")
    if "headroom" in features:
        if not installed_deps:
            steps.append("python -m pip install headroom-ai")
        steps.extend(
            [
                "Use Headroom after Vault retrieval when logs, tool output, or retrieved context are too large.",
                "Keep Vault citations tied to original vault_read_range output, not compressed summaries.",
            ]
        )
    if "memory_agents" in features:
        steps.extend(
            [
                "Keep Profile/Dream/Forgetting agents report-only or candidate-only by default.",
                "Use reviewed summaries for shared profile memory; keep raw private interactions local.",
                "Use Progressive Memory Disclosure: boot summary -> active context -> topic map -> bounded read -> raw/archive only when justified.",
            ]
        )
    if "dev" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[dev]"')
    return steps


def interactive_setup(argv_config: dict[str, Any]) -> AgentSetupConfig:
    agent = str(argv_config.get("agent") or _ask("Agent/runtime", "generic"))
    scope = str(argv_config.get("scope") or _ask("Vault scope (shared/private/domain/temporary)", "private"))
    memory_layout = str(
        argv_config.get("memory_layout")
        or _ask("Memory layout (hybrid/shared/private)", "hybrid")
    )
    project_dir = argv_config.get("project_dir")
    if not project_dir:
        project_dir = _ask("Vault project directory", str(default_project_dir(scope, agent=agent)))
    agent_private_dir = argv_config.get("agent_private_dir")
    if not agent_private_dir and _normalize_memory_layout(memory_layout) in {"hybrid", "private"}:
        agent_private_dir = _ask("Agent private vault directory", str(default_agent_private_dir(agent)))
    language = argv_config.get("language")
    if language is None:
        language = _ask("Setup language / 安裝語言 (en/zh-Hant/zh-CN)", "en")

    features_raw = argv_config.get("features")
    if features_raw:
        features = normalize_features(features_raw)
    else:
        features = _ask_interactive_features()

    install_optional_deps = bool(argv_config.get("install_optional_deps", False))
    if not install_optional_deps and _features_need_dependency_install(features):
        install_optional_deps = _ask_yes_no("Install selected optional Python dependencies now?", True)

    install_embedding_choice = argv_config.get("install_embedding_model")
    if install_embedding_choice is None and install_optional_deps and "semantic" in features:
        if _ask_yes_no("Download and configure a local ONNX embedding model now?", True):
            install_embedding_choice = _ask("Embedding model (zh/en/mix)", "mix")

    obsidian_vault = argv_config.get("obsidian_vault")
    if obsidian_vault is None:
        obsidian_vault = _ask("Existing Obsidian vault path (blank to skip)", "")

    import_obsidian = bool(argv_config.get("import_obsidian", False))
    sync_targets = argv_config.get("sync_targets", "none")
    if obsidian_vault:
        if "import_obsidian" not in argv_config:
            import_obsidian = _ask_yes_no("Run first Obsidian import after dry-run?", False)
        if not argv_config.get("sync_targets"):
            sync_targets = _ask("Automatic sync templates (none/cron/launchagent/n8n/all)", "none")

    supabase_sync_targets = argv_config.get("supabase_sync_targets", "none")
    supabase_setup_mode = argv_config.get("supabase_setup_mode")
    if "supabase" in features and supabase_setup_mode is None:
        supabase_setup_mode = _ask("Supabase setup guide (simple/advanced/none)", "simple")
    if "supabase" in features and not argv_config.get("supabase_sync_targets"):
        supabase_sync_targets = _ask("Daily Supabase sync templates (none/cron/launchagent/n8n/all)", "none")
    remote_reader_targets = argv_config.get("remote_reader_targets", "none")
    if "supabase" in features and not argv_config.get("remote_reader_targets"):
        remote_reader_targets = _ask("Remote reader templates for n8n/Coze/shell (none/shell/n8n/coze/all)", "none")
    remote_reader_query = str(argv_config.get("remote_reader_query") or "deployment SOP")
    agent_roster = argv_config.get("agent_roster")
    if agent_roster is None and _ask_yes_no("Generate multi-agent roster/access-matrix templates?", False):
        agent_roster = _ask("Agent roster (example: profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation)", "")
    validation_pack_targets = argv_config.get("validation_pack_targets", "none")
    if "supabase" in features and not argv_config.get("validation_pack_targets"):
        validation_pack_targets = _ask("Live validation pack for remote/n8n/coze (none/remote/n8n/coze/all)", "none")

    automation_schedule_targets = argv_config.get("automation_schedule_targets", "none")
    if not argv_config.get("automation_schedule_targets"):
        automation_schedule_targets = _ask("Memory automation schedule templates (none/cron/launchagent/n8n/all)", "none")
    automation_mode = argv_config.get("automation_mode") or "balanced"
    if automation_schedule_targets and automation_schedule_targets != "none" and not argv_config.get("automation_mode"):
        automation_mode = _ask("Memory automation mode (conservative/balanced/autonomous)", "balanced")
    automation_command = argv_config.get("automation_command") or "cycle"
    if automation_schedule_targets and automation_schedule_targets != "none" and not argv_config.get("automation_command"):
        automation_command = _ask("Memory automation command (cycle/run)", "cycle")
    automation_apply = bool(argv_config.get("automation_apply", False))
    if automation_schedule_targets and automation_schedule_targets != "none" and "automation_apply" not in argv_config:
        automation_apply = _ask_yes_no("Allow scheduled automation to apply reversible archival?", False)
    automation_write_workspace = bool(argv_config.get("automation_write_workspace", False))
    if (
        automation_schedule_targets
        and automation_schedule_targets != "none"
        and str(automation_command or "cycle") == "cycle"
        and "automation_write_workspace" not in argv_config
    ):
        automation_write_workspace = _ask_yes_no(
            "Write scheduled cycle workspace handoff (cycle-latest.json)?",
            False,
        )
    automation_workspace_inbox_limit = int(argv_config.get("automation_workspace_inbox_limit") or 5)
    automation_include_transcripts = bool(argv_config.get("automation_include_transcripts", False))
    if (
        automation_schedule_targets
        and automation_schedule_targets != "none"
        and "automation_include_transcripts" not in argv_config
    ):
        automation_include_transcripts = _ask_yes_no(
            "Include metadata-only uncaptured transcript hints in scheduled inbox handoff?",
            False,
        )
    automation_transcript_limit = int(argv_config.get("automation_transcript_limit") or 5)

    stable_venv_path = argv_config.get("stable_venv_path")
    if not stable_venv_path and argv_config.get("write_stable_venv_script"):
        stable_venv_path = str(default_stable_venv_path())
    if stable_venv_path is None and python_environment_warnings():
        if _ask_yes_no("Current Python environment looks temporary. Generate a stable venv bootstrap script?", True):
            stable_venv_path = _ask("Stable venv path", str(default_stable_venv_path()))

    return AgentSetupConfig(
        project_dir=Path(project_dir),
        scope=scope,
        agent=agent,
        memory_layout=memory_layout,
        agent_private_dir=Path(agent_private_dir).expanduser() if agent_private_dir else None,
        features=features,
        language=_normalize_setup_language(str(language)),
        tool_profile=str(argv_config.get("tool_profile") or "core"),
        install_optional_deps=install_optional_deps,
        install_embedding_model=install_embedding_choice,
        obsidian_vault=Path(obsidian_vault).expanduser() if obsidian_vault else None,
        import_obsidian=import_obsidian,
        sync_targets=sync_targets,
        sync_interval_minutes=int(argv_config.get("sync_interval_minutes") or 15),
        supabase_sync_targets=supabase_sync_targets,
        supabase_sync_interval_minutes=int(
            argv_config.get("supabase_sync_interval_minutes")
            or DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES
        ),
        supabase_setup_mode=str(supabase_setup_mode or "simple"),
        remote_reader_targets=remote_reader_targets,
        remote_reader_query=remote_reader_query,
        agent_roster=agent_roster or None,
        validation_pack_targets=validation_pack_targets,
        automation_schedule_targets=automation_schedule_targets,
        automation_interval_minutes=int(
            argv_config.get("automation_interval_minutes")
            or DEFAULT_AUTOMATION_INTERVAL_MINUTES
        ),
        automation_mode=_normalize_automation_mode(str(automation_mode)),
        automation_command=_normalize_automation_command(str(automation_command)),
        automation_apply=automation_apply,
        automation_write_workspace=automation_write_workspace,
        automation_workspace_inbox_limit=automation_workspace_inbox_limit,
        automation_include_transcripts=automation_include_transcripts,
        automation_transcript_limit=automation_transcript_limit,
        template_dir=Path(argv_config["template_dir"]) if argv_config.get("template_dir") else None,
        allow_private=bool(argv_config.get("allow_private", False)),
        stable_venv_path=Path(stable_venv_path).expanduser() if stable_venv_path else None,
    )


def _ask(prompt: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def _ask_interactive_features() -> list[str]:
    features = ["core"]
    if _ask_yes_no("Configure local stdio MCP tools for this agent?", True):
        features.append("mcp")
    if _ask_yes_no("Enable optional semantic search and embedding workflow?", False):
        features.append("semantic")
    if _ask_yes_no("Enable optional Supabase sync/read dependencies?", False):
        features.append("supabase")
    if _ask_yes_no(
        "Enable optional Headroom context compression for long logs/tool output?",
        False,
    ):
        features.append("headroom")
    if _ask_yes_no("Enable Profile/Dream/Forgetting memory-agent guidance?", False):
        features.append("memory_agents")
    if _ask_yes_no("Install developer/benchmark dependencies?", False):
        features.append("dev")
    return features


def _features_need_dependency_install(features: list[str]) -> bool:
    selected = set(normalize_features(features))
    # The recommended first install already uses vault-for-llm[mcp]. Do not ask
    # users to install "optional" dependencies again when MCP is the only extra.
    extras_that_need_confirmation = PYPI_EXTRA_FEATURES - {"mcp"}
    return bool((selected & extras_that_need_confirmation) or "headroom" in selected)


def _ask_yes_no(prompt: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{default_text}]: ").strip().lower()
    except EOFError:
        answer = ""
    if not answer:
        return default
    return answer in {"y", "yes", "true", "1"}
