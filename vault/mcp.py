#!/usr/bin/env python3
"""Vault-for-LLM MCP server with public ``vault_*`` tool names."""

import argparse
import json
import sys
import os
from pathlib import Path

try:
    from . import __version__
except Exception:  # pragma: no cover - direct script fallback
    __version__ = "0.1.0"

# 確保模組路徑
VAULT_DIR = str(Path(__file__).parent.parent)
if VAULT_DIR not in sys.path:
    sys.path.insert(0, VAULT_DIR)

from vault.mcp_memory import (
    _format_memory_candidate,
    _resolve_mcp_transcript_path,
    handle_memory_tool_call,
)
from vault.mcp_security import (
    check_mcp_rate_limit as _check_mcp_rate_limit,
    reset_rate_limiter as _reset_rate_limiter,
)
from vault.mcp_read import (
    _compact_node,
    _error,
    _format_citation,
    _line_hash,
    _next_action_for_error,
    _open_readonly_db,
    _preferred_read_node,
    _read_range_action,
    _vault_map_show_payload,
    _vault_read_range_payload,
    vault_map_show,
    vault_read_range,
)
from vault import mcp_remote as _mcp_remote
from vault.mcp_remote import (
    REMOTE_CLAIM_TABLE,
    REMOTE_KNOWLEDGE_TABLE,
    REMOTE_NODE_TABLE,
    _content_hash_for_text,
    _get_supabase_client,
    _remote_claim_content,
    _remote_error,
    _remote_next_action_for_error,
    _remote_node_payload,
    _remote_read_range_action,
    _sort_remote_claims,
    _sort_remote_nodes,
    _supabase_rows,
)

DB_PATH = os.path.join(
    os.environ.get("VAULT_PATH") or VAULT_DIR,
    "vault.db",
)
MCP_SEARCH_MAX_LIMIT = 50
MCP_SEARCH_MAX_OFFSET = 1000
MCP_ALLOWED_SEARCH_FIELDS = {
    "id",
    "title",
    "category",
    "layer",
    "trust",
    "tags",
    "best_claim",
    "best_span",
    "best_node",
    "node_uid",
    "path",
    "heading",
    "line_start",
    "line_end",
    "citation",
    "recommended_next_tool",
    "next_action",
    "next_actions",
    "rerank_score",
    "_score",
    "_original_score",
    "_snippet",
    "content_preview",
}
MCP_MEMORY_CANDIDATE_MAX_LIMIT = 100


def _set_project_dir(project_dir: str | os.PathLike[str]) -> None:
    """Point the MCP server at a project's local SQLite vault."""
    global DB_PATH
    project_path = Path(project_dir).expanduser().absolute()
    DB_PATH = str(project_path / "vault.db")


def _canonical_tool_name(name: str) -> str:
    """Return the public Vault MCP tool name unchanged."""
    return name


def _get_db():
    """取得資料庫連線。"""
    from vault.db import VaultDB
    db = VaultDB(DB_PATH)
    db.connect()
    return db


def _get_search():
    """取得搜尋引擎。"""
    from vault.db import VaultDB
    from vault.search import VaultSearch
    from vault.embed import create_embedding_provider

    db = VaultDB(DB_PATH)
    db.connect()

    embed = None
    try:
        provider_name = db.get_config("embedding_provider", "auto")
        model_key = db.get_config("embedding_model", "mix")
        if provider_name != "none":
            embed = create_embedding_provider(provider=provider_name, model_key=model_key)
    except Exception:
        pass

    return db, VaultSearch(db, embed_provider=embed)


def _clamp_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _search_field_set(fields) -> set[str] | None:
    if not isinstance(fields, list):
        return None
    return {str(field) for field in fields if str(field) in MCP_ALLOWED_SEARCH_FIELDS}


# ── Remote MCP wrappers ───────────────────────────────

def _vault_remote_search_payload(*args, **kwargs) -> dict:
    if kwargs.get("sb_client") is None:
        kwargs["sb_client"] = _get_supabase_client()
    return _mcp_remote._vault_remote_search_payload(*args, **kwargs)


def _vault_remote_doctor_payload(*args, **kwargs) -> dict:
    if kwargs.get("sb_client") is None:
        kwargs["sb_client"] = _get_supabase_client()
    return _mcp_remote._vault_remote_doctor_payload(*args, **kwargs)


def _vault_remote_map_show_payload(*args, **kwargs) -> dict:
    if kwargs.get("sb_client") is None:
        kwargs["sb_client"] = _get_supabase_client()
    return _mcp_remote._vault_remote_map_show_payload(*args, **kwargs)


def _vault_remote_read_range_payload(*args, **kwargs) -> dict:
    if kwargs.get("sb_client") is None:
        kwargs["sb_client"] = _get_supabase_client()
    return _mcp_remote._vault_remote_read_range_payload(*args, **kwargs)


def vault_remote_map_show(
    knowledge_id: int | str,
    compact: bool = False,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    """Return a synced Supabase Document Map structure (read-only target)."""
    return _vault_remote_map_show_payload(
        knowledge_id,
        compact=compact,
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )


def vault_remote_read_range(
    knowledge_id: int | str,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    """Return a bounded remote source/claim range with a fixed citation."""
    return _vault_remote_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=line_start,
        line_end=line_end,
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )


# ── MCP Server Implementation ──────────────────────────

TOOLS = [
    {
        "name": "vault_search",
        "description": "搜尋 Vault 百科知識庫。支援關鍵字、向量、混合搜尋。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋查詢（中英文皆可）"
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "keyword", "vector", "semantic", "hybrid"],
                    "description": "搜尋模式（預設 auto）",
                    "default": "auto"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆（預設 10）",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MCP_SEARCH_MAX_LIMIT
                },
                "offset": {
                    "type": "integer",
                    "description": "跳過前 N 筆（分頁用，預設 0）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": MCP_SEARCH_MAX_OFFSET
                },
                "normalize_scores": {
                    "type": "boolean",
                    "description": "是否對分數進行標準化（預設 false）",
                    "default": False
                },
                "include_snippet": {
                    "type": "boolean",
                    "description": "是否在結果中包含內容片段（預設 false）",
                    "default": False
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定回傳欄位（如 ['id', 'title', 'best_claim']），預設全欄位"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡 payload（MCP 預設 true；設為 false 可取得含 content_preview 的完整輸出）",
                    "default": True
                },
                "agent_id": {
                    "type": "string",
                    "description": "可選 Agent 身份；提供後套用 scope/sensitivity/allowed_agents 讀取過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "搭配 agent_id 使用；允許讀取 owner/allow-list 授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high", "restricted"],
                    "description": "可選最高敏感度；例如 medium 會排除 high/restricted",
                    "default": ""
                },
            },
            "required": ["query"]
        }
    },
    {
        "name": "vault_add",
        "description": "Direct low-level add to active Vault knowledge. Prefer vault_memory_propose for autonomous agents and unreviewed memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "知識標題"
                },
                "content": {
                    "type": "string",
                    "description": "知識內容（Markdown 格式）"
                },
                "category": {
                    "type": "string",
                    "description": "分類（error/technique/architecture/concept/decision/general）",
                    "default": "general"
                },
                "tags": {
                    "type": "string",
                    "description": "標籤（逗號分隔，如 'sqlite,踩坑,擴展'）",
                    "default": ""
                },
                "trust": {
                    "type": "number",
                    "description": "信任分數（0.0-1.0，session 提取建議 0.4，手動驗證 0.8+）",
                    "default": 0.5
                },
                "layer": {
                    "type": "string",
                    "description": "知識層級（L0-L3）",
                    "default": "L3"
                },
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "memory_type": {"type": "string", "default": "knowledge"},
                "expires_at": {"type": "string", "default": ""},
                "agent_id": {"type": "string", "description": "Calling agent identity for write-side governance.", "default": ""},
                "allow_shared": {"type": "boolean", "description": "Required for shared/public writes.", "default": False},
                "allow_private": {"type": "boolean", "description": "Required for private writes.", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "description": "Required for high-sensitivity writes.", "default": False},
                "allow_restricted": {"type": "boolean", "description": "Required for restricted writes.", "default": False},
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "vault_memory_propose",
        "description": "Propose a possible memory through deterministic gates. Candidate-first; use this instead of vault_add for autonomous agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "source": {"type": "string", "default": "mcp"},
                "source_ref": {"type": "string", "default": ""},
                "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
                "category": {"type": "string", "default": "general"},
                "tags": {"type": "string", "default": ""},
                "trust": {"type": "number", "default": 0.5},
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "memory_type": {"type": "string", "default": "knowledge"},
                "expires_at": {"type": "string", "default": ""},
                "agent_id": {"type": "string", "description": "Calling agent identity for write-side governance.", "default": ""},
                "allow_shared": {"type": "boolean", "description": "Required for shared/public candidates.", "default": False},
                "allow_private": {"type": "boolean", "description": "Required for private candidates.", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "description": "Required for high-sensitivity candidates.", "default": False},
                "allow_restricted": {"type": "boolean", "description": "Required for restricted candidates.", "default": False},
                "reason": {"type": "string", "description": "Why this is worth remembering"},
                "mode": {"type": "string", "enum": ["candidate", "promote_if_safe"], "default": "candidate"},
            },
            "required": ["title", "content", "reason"]
        }
    },
    {
        "name": "vault_memory_promote",
        "description": "Promote a reviewed memory candidate into raw/ plus active SQLite knowledge. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "confirm": {"type": "boolean", "default": True},
                "compile": {"type": "boolean", "default": True},
                "build_map": {"type": "boolean", "default": True},
                "agent_id": {"type": "string", "description": "Calling agent identity for write-side governance.", "default": ""},
                "allow_shared": {"type": "boolean", "description": "Required when the candidate writes shared/public memory.", "default": False},
                "allow_private": {"type": "boolean", "description": "Required when the candidate writes private memory.", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "description": "Required when the candidate writes high-sensitivity memory.", "default": False},
                "allow_restricted": {"type": "boolean", "description": "Required when the candidate writes restricted memory.", "default": False},
            },
            "required": ["candidate_id", "confirm"]
        }
    },
    {
        "name": "vault_memory_review",
        "description": "Record a rejected or blocked candidate review outcome so automation can learn without promoting memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["rejected", "blocked"]},
                "reason": {"type": "string", "description": "Why the candidate was rejected or blocked"},
                "score": {"type": "number", "description": "Optional 0..1 feedback score"},
            },
            "required": ["candidate_id", "outcome", "reason"]
        }
    },
    {
        "name": "vault_memory_candidates",
        "description": "List memory candidates for review. Defaults to pending candidates and omits full raw content unless requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Candidate status filter, for example candidate/promoted/rejected.",
                    "default": "candidate",
                },
                "all": {
                    "type": "boolean",
                    "description": "List all statuses instead of filtering by status.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidates to return.",
                    "default": 50,
                    "minimum": 1,
                    "maximum": MCP_MEMORY_CANDIDATE_MAX_LIMIT,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include full candidate content. Defaults false to keep MCP payloads small.",
                    "default": False,
                },
                "include_gates": {
                    "type": "boolean",
                    "description": "Include the full gate payload for review.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_capture_session",
        "description": "Preview or write reviewable memory candidates from an agent session transcript. Dry-run by default; never promotes active memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "transcript_path": {
                    "type": "string",
                    "description": "Transcript path. Relative paths resolve under the current Vault project; absolute paths require allow_absolute_path=true.",
                },
                "format": {
                    "type": "string",
                    "enum": ["auto", "jsonl", "markdown", "text"],
                    "default": "auto",
                },
                "source_system": {
                    "type": "string",
                    "description": "Source system, for example codex/hermes/openclaw/claude-code.",
                    "default": "auto",
                },
                "agent_id": {"type": "string", "default": ""},
                "write_candidates": {
                    "type": "boolean",
                    "description": "Write gated candidates into memory_candidates. Defaults false for preview-only capture.",
                    "default": False,
                },
                "max_candidates": {
                    "type": "integer",
                    "description": "Maximum extracted candidates.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum deterministic capture score.",
                    "default": 0.55,
                },
                "scope": {
                    "type": "string",
                    "enum": ["private", "project", "shared", "public"],
                    "default": "project",
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "default": "low",
                },
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include redacted full candidate content. Defaults false.",
                    "default": False,
                },
                "allow_absolute_path": {
                    "type": "boolean",
                    "description": "Allow reading a transcript outside the current project directory.",
                    "default": False,
                },
            },
            "required": ["transcript_path"],
        }
    },
    {
        "name": "vault_capture_discover",
        "description": "Discover likely session transcript files without reading transcript contents. Use before vault_capture_session when the transcript path is unknown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional search directories. Relative paths resolve under the current Vault project.",
                    "default": [],
                },
                "source_system": {
                    "type": "string",
                    "description": "Preferred source system, for example codex/hermes/openclaw/claude-code.",
                    "default": "auto",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum transcript candidates to return.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory depth to scan.",
                    "default": 3,
                    "minimum": 0,
                    "maximum": 8,
                },
                "max_file_mb": {
                    "type": "number",
                    "description": "Skip transcript-like files larger than this size.",
                    "default": 5.0,
                },
                "allow_absolute_paths": {
                    "type": "boolean",
                    "description": "Allow search directories outside the current project.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_automation_inbox",
        "description": "Read the compact automation review inbox. Read-only by default; returns the shortest candidate/report queue without raw content unless requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum inbox items to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 50,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include redacted candidate content. Defaults false.",
                    "default": False,
                },
                "write_handoff": {
                    "type": "boolean",
                    "description": "Write reports/automation/inbox-latest.json for scheduled handoff.",
                    "default": False,
                },
                "include_transcripts": {
                    "type": "boolean",
                    "description": "Include metadata-only transcript discovery hints. Defaults false.",
                    "default": False,
                },
                "transcript_limit": {
                    "type": "integer",
                    "description": "Maximum transcript discovery hints to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
        }
    },
    {
        "name": "vault_automation_activity",
        "description": "Read compact closed-loop automation activity from recent reports. Read-only; returns promoted/skipped reasons without raw candidate content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum recent reports to scan.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "event_limit": {
                    "type": "integer",
                    "description": "Maximum activity events to return.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        }
    },
    {
        "name": "vault_automation_brief",
        "description": "Read a compact automation intelligence brief: learning hints, memory weights, forgetting pressure, shared agent health, and the 5% human-review queue. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum learning rules, usage weights, and forgetting preview rows to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "review_limit": {
                    "type": "integer",
                    "description": "Maximum human-review items to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "min_events": {
                    "type": "integer",
                    "description": "Minimum feedback events before a group is considered learnable.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        }
    },
    {
        "name": "vault_automation_handoff",
        "description": "Read the latest compact startup handoff for this project. Read-only; does not inspect raw transcripts or mutate memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["auto", "cycle", "inbox"],
                    "description": "Which handoff to read. auto prefers cycle-latest.md and attaches fleet-health when present.",
                    "default": "auto",
                },
                "handoff_path": {
                    "type": "string",
                    "description": "Optional custom reports/automation/*.md or *.json handoff path.",
                    "default": "",
                },
            },
        }
    },
    {
        "name": "vault_cold_store_expired",
        "description": "Preview or apply summarize-then-cold-store for expired-but-used memories. Defaults to dry-run; skips private, high/restricted, and L0/L1 memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum expired memories to inspect.",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "min_usage": {
                    "type": "integer",
                    "description": "Minimum access_count + citation_count required before cold-store.",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "summary_max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to keep in the cold-store summary.",
                    "default": 360,
                    "minimum": 80,
                    "maximum": 2000,
                },
                "apply": {
                    "type": "boolean",
                    "description": "Actually write summary and archive eligible rows. Defaults false.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_obsidian_import",
        "description": "Import an existing Obsidian vault into raw/obsidian/. Run dry_run first; compile only after user confirmation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault_dir": {"type": "string", "description": "Obsidian vault directory"},
                "dry_run": {"type": "boolean", "default": True},
                "compile": {"type": "boolean", "default": False},
                "category": {"type": "string", "default": "obsidian"},
                "tags": {"type": "string", "default": "obsidian"},
                "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
                "trust": {"type": "number", "default": 0.5},
                "allow_private": {"type": "boolean", "default": False},
            },
            "required": ["vault_dir"]
        }
    },
    {
        "name": "vault_dream_run",
        "description": "Run deterministic dream curation. Defaults to report-only and never deletes knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["report", "apply_safe"], "default": "report"},
                "checks": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["freshness", "dedup", "convergence", "metadata", "orphans"]},
                    "default": ["freshness", "dedup", "convergence", "metadata", "orphans"],
                },
                "limit": {"type": "integer", "default": 50},
                "write_report": {"type": "boolean", "default": True},
                "write_candidates": {
                    "type": "boolean",
                    "default": False,
                    "description": "Write Dream suggestions into the memory candidate queue. Never promotes automatically.",
                },
                "backup": {"type": "boolean", "default": True},
            }
        }
    },
    {
        "name": "vault_stats",
        "description": "取得 Vault 百科統計資訊。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "vault_update_status",
        "description": "Show local Vault version, update hint, Agent registry, shared/private vaults, and startup handoff commands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "latest_version": {
                    "type": "string",
                    "description": "Optional known latest version. Avoids network checks when provided.",
                    "default": "",
                },
                "check_pypi": {
                    "type": "boolean",
                    "description": "Contact PyPI to resolve the latest version. Defaults false for bounded startup.",
                    "default": False,
                },
                "read_status": {
                    "type": "boolean",
                    "description": "Read existing ~/.vault-for-llm/update-status.json without recomputing. Defaults false.",
                    "default": False,
                },
                "doctor": {
                    "type": "boolean",
                    "description": "Check shared update-status health without adding a separate MCP tool. Defaults false.",
                    "default": False,
                },
                "max_status_age_minutes": {
                    "type": "integer",
                    "description": "Freshness threshold for doctor mode. Defaults 1440 minutes.",
                    "default": 1440,
                    "minimum": 0,
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional Agent/runtime id for a focused startup checklist.",
                    "default": "",
                },
                "write_status": {
                    "type": "boolean",
                    "description": "Write ~/.vault-for-llm/update-status.json. Defaults false.",
                    "default": False,
                },
            }
        }
    },
    {
        "name": "vault_converge",
        "description": "執行收斂檢查 — 判斷哪些知識條目內容不夠完整。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "最多檢查幾條（0=全部）",
                    "default": 5
                },
                "min_trust": {
                    "type": "number",
                    "description": "只檢查 trust 低於此值（預設 1.0 = 檢查所有未收斂的）",
                    "default": 1.0
                },
            }
        }
    },
    {
        "name": "vault_freshness",
        "description": "檢查知識條目的新鮮度 — 哪些條目過期了。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_only": {
                    "type": "boolean",
                    "description": "只顯示過期條目",
                    "default": True
                },
            }
        }
    },
    {
        "name": "vault_map_show",
        "description": "讀取指定知識的 Document Map 結構（章節、路徑、行號）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
                },
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high", "restricted"],
                    "default": ""
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_read_range",
        "description": "讀取指定知識的受限行號範圍；成功回傳固定 citation，預設最多 80 行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
                "node_uid": {
                    "type": "string",
                    "description": "Document Map node_uid；若省略行號，使用此 node 的行號範圍",
                    "default": ""
                },
                "line_start": {
                    "type": "integer",
                    "description": "起始行號（含）",
                    "default": 0
                },
                "line_end": {
                    "type": "integer",
                    "description": "結束行號（含）",
                    "default": 0
                },
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high", "restricted"],
                    "default": ""
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_search",
        "description": "透過 Supabase read-only RPC 搜尋可讀遠端記憶；預設只回傳安全 metadata 與摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋字串；空字串會回傳最新可讀記憶",
                    "default": ""
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆，最高 50",
                    "default": 10
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡欄位（預設 true）",
                    "default": True
                },
            },
        }
    },
    {
        "name": "vault_remote_map_show",
        "description": "從 Supabase 同步目標讀取 Document Map 結構（唯讀；SQLite 仍是 source of truth）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "oneOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Remote knowledge ID；可為本地同步的正整數 ID，或 Supabase UUID"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_read_range",
        "description": "從 Supabase 同步目標讀取受限行號範圍；成功回傳固定 citation，預設最多 80 行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "oneOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Remote knowledge ID；可為本地同步的正整數 ID，或 Supabase UUID"
                },
                "node_uid": {
                    "type": "string",
                    "description": "Remote Document Map node_uid；若省略行號，使用此 node 的行號範圍",
                    "default": ""
                },
                "line_start": {
                    "type": "integer",
                    "description": "起始行號（含）",
                    "default": 0
                },
                "line_end": {
                    "type": "integer",
                    "description": "結束行號（含）",
                    "default": 0
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
]

TOOL_PROFILES = {
    "core": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
    ],
    "review": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        "vault_dream_run",
    ],
    "remote": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_remote_search",
        "vault_remote_map_show",
        "vault_remote_read_range",
    ],
    "maintenance": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        "vault_cold_store_expired",
        "vault_obsidian_import",
        "vault_dream_run",
        "vault_converge",
        "vault_freshness",
    ],
    "full": [tool["name"] for tool in TOOLS],
}

_ACTIVE_TOOLS = TOOLS


def _tool_names_from_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    names = [name.strip() for name in value.split(",") if name.strip()]
    return names or None


def _tools_for_names(names: list[str]) -> list[dict]:
    by_name = {tool["name"]: tool for tool in TOOLS}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise ValueError(f"Unknown MCP tool(s): {', '.join(unknown)}")
    return [by_name[name] for name in names]


def select_tools(tool_profile: str = "full", tools: str | None = None) -> list[dict]:
    """Return the MCP tool schemas visible to the client."""
    custom_names = _tool_names_from_csv(tools)
    if custom_names:
        return _tools_for_names(custom_names)
    if tool_profile not in TOOL_PROFILES:
        allowed = ", ".join(sorted(TOOL_PROFILES))
        raise ValueError(f"Unknown MCP tool profile '{tool_profile}' (expected {allowed})")
    return _tools_for_names(TOOL_PROFILES[tool_profile])


def _set_active_tools(tool_profile: str = "full", tools: str | None = None) -> None:
    global _ACTIVE_TOOLS
    _ACTIVE_TOOLS = select_tools(tool_profile, tools)


def handle_tool_call(name: str, arguments: dict) -> dict:
    """處理 MCP tool call，回傳結果。"""
    name = _canonical_tool_name(name)
    arguments = arguments or {}
    rate_limited = _check_mcp_rate_limit(name, arguments)
    if rate_limited is not None:
        return {"result": json.dumps(rate_limited, ensure_ascii=False, indent=2)}
    try:
        if name == "vault_search":
            compact = bool(arguments.get("compact", True))
            field_set = _search_field_set(arguments.get("fields"))
            limit = _clamp_int(
                arguments.get("limit", 10),
                default=10,
                minimum=1,
                maximum=MCP_SEARCH_MAX_LIMIT,
            )
            offset = _clamp_int(
                arguments.get("offset", 0),
                default=0,
                minimum=0,
                maximum=MCP_SEARCH_MAX_OFFSET,
            )
            db, search = _get_search()
            results = search.search(
                query=arguments.get("query", ""),
                mode=arguments.get("mode", "auto"),
                limit=limit,
                offset=offset,
                normalize_scores=arguments.get("normalize_scores", False),
                include_snippet=arguments.get("include_snippet", False),
                fields=None,
                min_trust=0.0,
                compact=False,
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", ""),
            )
            # 簡化輸出
            output = []
            for r in results:
                if compact:
                    item = {
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "best_claim": r.get("best_claim", ""),
                        "best_span": r.get("best_span"),
                        "node_uid": r.get("node_uid"),
                        "path": r.get("path"),
                        "heading": r.get("heading"),
                        "line_start": r.get("line_start"),
                        "line_end": r.get("line_end"),
                        "citation": r.get("citation"),
                        "recommended_next_tool": r.get("recommended_next_tool"),
                        "next_action": r.get("next_action"),
                        "next_actions": r.get("next_actions"),
                        "rerank_score": r.get("rerank_score", r.get("_rerank_score")),
                        "_score": r.get("_score"),
                        "_original_score": r.get("_original_score"),
                        "_snippet": r.get("_snippet"),
                    }
                    item = {k: v for k, v in item.items() if v is not None}
                    if field_set is not None:
                        item = {k: v for k, v in item.items() if k in field_set}
                    output.append(item)
                    continue
                item = {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "category": r.get("category"),
                    "layer": r.get("layer"),
                    "trust": r.get("trust"),
                    "tags": r.get("tags"),
                    "best_claim": r.get("best_claim", ""),
                    "best_span": r.get("best_span"),
                    "best_node": r.get("best_node"),
                    "node_uid": r.get("node_uid"),
                    "path": r.get("path"),
                    "heading": r.get("heading"),
                    "line_start": r.get("line_start"),
                    "line_end": r.get("line_end"),
                    "citation": r.get("citation"),
                    "recommended_next_tool": r.get("recommended_next_tool"),
                    "next_action": r.get("next_action"),
                    "next_actions": r.get("next_actions"),
                    "rerank_score": r.get("_rerank_score"),
                    "_score": r.get("_score"),
                    "_original_score": r.get("_original_score"),
                    "_snippet": r.get("_snippet"),
                }
                # 截斷 content_raw
                raw = r.get("content_raw", "")
                if raw and len(raw) > 200:
                    item["content_preview"] = raw[:200] + "..."
                else:
                    item["content_preview"] = raw
                if field_set is not None:
                    item = {k: v for k, v in item.items() if k in field_set}
                output.append(item)
            db.close()
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        memory_payload = handle_memory_tool_call(name, arguments)
        if memory_payload is not None:
            return memory_payload

        if name == "vault_automation_inbox":
            from vault.automation import automation_inbox

            limit = _clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=50)
            payload = automation_inbox(
                Path(DB_PATH).resolve().parent,
                limit=limit,
                include_content=bool(arguments.get("include_content", False)),
                include_transcripts=bool(arguments.get("include_transcripts", False)),
                transcript_limit=_clamp_int(
                    arguments.get("transcript_limit", 5),
                    default=5,
                    minimum=1,
                    maximum=20,
                ),
                write_handoff=bool(arguments.get("write_handoff", False)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_automation_activity":
            from vault.automation import automation_activity

            payload = automation_activity(
                Path(DB_PATH).resolve().parent,
                limit=_clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=20),
                event_limit=_clamp_int(
                    arguments.get("event_limit", 20),
                    default=20,
                    minimum=1,
                    maximum=100,
                ),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_automation_brief":
            from vault.automation import automation_brief

            payload = automation_brief(
                Path(DB_PATH).resolve().parent,
                limit=_clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=20),
                review_limit=_clamp_int(arguments.get("review_limit", 5), default=5, minimum=1, maximum=20),
                min_events=_clamp_int(arguments.get("min_events", 5), default=5, minimum=1, maximum=100),
                write_brief=False,
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_automation_handoff":
            from vault.automation import automation_handoff

            payload = automation_handoff(
                Path(DB_PATH).resolve().parent,
                source=str(arguments.get("source") or "auto"),
                handoff_path=str(arguments.get("handoff_path") or ""),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_cold_store_expired":
            from vault.db import VaultDB

            with VaultDB(DB_PATH) as db:
                payload = db.cold_store_expired_knowledge(
                    limit=_clamp_int(arguments.get("limit", 100), default=100, minimum=1, maximum=1000),
                    dry_run=not bool(arguments.get("apply", False)),
                    min_usage=_clamp_int(arguments.get("min_usage", 1), default=1, minimum=1, maximum=1000),
                    summary_max_chars=_clamp_int(
                        arguments.get("summary_max_chars", 360),
                        default=360,
                        minimum=80,
                        maximum=2000,
                    ),
                )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_obsidian_import":
            from vault.agent_setup import compile_project
            from vault.import_obsidian import sync_obsidian_vault

            project_dir = Path(DB_PATH).resolve().parent
            dry_run = bool(arguments.get("dry_run", True))
            payload = {
                "project_dir": str(project_dir),
                "vault_dir": arguments.get("vault_dir", ""),
                "dry_run": dry_run,
                "import": sync_obsidian_vault(
                    project_dir=project_dir,
                    vault_dir=arguments.get("vault_dir", ""),
                    category=arguments.get("category", "obsidian"),
                    tags=arguments.get("tags", "obsidian"),
                    layer=arguments.get("layer", "L3"),
                    trust=float(arguments.get("trust", 0.5)),
                    dry_run=dry_run,
                    allow_private=bool(arguments.get("allow_private", False)),
                ),
            }
            if bool(arguments.get("compile", False)) and not dry_run:
                payload["compile"] = compile_project(
                    project_dir,
                    allow_private=bool(arguments.get("allow_private", False)),
                )
            else:
                payload["next_action"] = {
                    "tool": "vault_obsidian_import",
                    "arguments": {
                        "vault_dir": arguments.get("vault_dir", ""),
                        "dry_run": False,
                        "compile": True,
                    },
                    "instruction": "Run only after the user confirms the dry-run result.",
                }
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_dream_run":
            from vault.dream import run_dream

            payload = run_dream(
                Path(DB_PATH).resolve().parent,
                mode=arguments.get("mode", "report"),
                checks=arguments.get("checks"),
                limit=arguments.get("limit", 50),
                write_report=bool(arguments.get("write_report", True)),
                write_candidates=bool(arguments.get("write_candidates", False)),
                backup=bool(arguments.get("backup", True)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_stats":
            db = _get_db()
            stats = db.stats()
            db.close()
            return {"result": json.dumps(stats, ensure_ascii=False, indent=2)}

        elif name == "vault_update_status":
            from vault.agent_registry import (
                build_update_distribution_health,
                build_update_status,
                focus_update_status_for_agent,
                read_update_status,
                write_update_status,
            )

            if bool(arguments.get("read_status", False)) and bool(arguments.get("write_status", False)):
                payload = {
                    "ok": False,
                    "error": "read_status cannot be combined with write_status",
                }
                return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}
            agent_id = str(arguments.get("agent_id") or "")
            if bool(arguments.get("doctor", False)):
                payload = build_update_distribution_health(
                    max_age_minutes=_clamp_int(
                        arguments.get("max_status_age_minutes"),
                        default=24 * 60,
                        minimum=0,
                        maximum=7 * 24 * 60,
                    )
                )
                if agent_id:
                    payload = focus_update_status_for_agent(payload, agent_id)
            elif bool(arguments.get("read_status", False)):
                payload = read_update_status(agent_id=agent_id)
            else:
                payload = build_update_status(
                    latest_version=str(arguments.get("latest_version") or ""),
                    check_pypi=bool(arguments.get("check_pypi", False)),
                )
            if (
                bool(arguments.get("write_status", False))
                and not bool(arguments.get("read_status", False))
                and not bool(arguments.get("doctor", False))
            ):
                payload["status_path"] = str(write_update_status(payload))
            if agent_id and not bool(arguments.get("read_status", False)) and not bool(arguments.get("doctor", False)):
                payload = focus_update_status_for_agent(payload, agent_id)
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_converge":
            # 使用關鍵詞 fallback，不依賴 LLM
            from scripts.convergence_check import check_convergence
            results = check_convergence(
                db_path=DB_PATH,
                apply=False,  # MCP 只讀取，不自動更新
                limit=arguments.get("limit", 5),
                min_trust=arguments.get("min_trust", 1.0),
            )
            if results is None:
                return {"result": json.dumps({"message": "沒有待檢查的條目"}, ensure_ascii=False)}
            output = [{
                "id": r["id"],
                "title": r["title"],
                "avg_score": r["avg_score"],
                "status": r["status"],
            } for r in results]
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "vault_freshness":
            from scripts.freshness_check import check_freshness
            results = check_freshness(
                db_path=DB_PATH,
                apply=False,  # MCP 只讀取
                stale_only=arguments.get("stale_only", True),
            )
            if results is None:
                return {"result": json.dumps({"message": "百科是空的"}, ensure_ascii=False)}
            output = [{
                "id": r["id"],
                "title": r["title"],
                "freshness": r["new_freshness"],
                "category": r["category"],
            } for r in results[:20]]  # 最多回傳 20 條
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "vault_map_show":
            payload = _vault_map_show_payload(
                arguments.get("knowledge_id", 0),
                compact=bool(arguments.get("compact", False)),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", ""),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_read_range":
            payload = _vault_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", ""),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_search":
            payload = _vault_remote_search_payload(
                query=arguments.get("query", ""),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", "medium"),
                limit=arguments.get("limit", 10),
                compact=bool(arguments.get("compact", True)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_map_show":
            payload = _vault_remote_map_show_payload(
                arguments.get("knowledge_id", 0),
                compact=bool(arguments.get("compact", False)),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", "medium"),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_read_range":
            payload = _vault_remote_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", "medium"),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        else:
            return {
                "error": f"Unknown tool: {name}",
                "failure_mode": "unknown_tool",
                "next_action": {"tool": "tools/list", "arguments": {}},
            }

    except Exception as e:
        return {
            "error": f"Error: {str(e)}",
            "failure_mode": "tool_execution_failed",
            "next_action": {"tool": name, "arguments": arguments or {}},
        }


# ── stdio MCP Server ──────────────────────────────────

def run_stdio():
    """作為 stdio MCP server 運行。"""
    # 讀取 MCP 協議訊息
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Initialize
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "vault-mcp",
                        "version": __version__,
                    },
                },
            }
            print(json.dumps(response), flush=True)

        # List tools
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": _ACTIVE_TOOLS},
            }
            print(json.dumps(response), flush=True)

        # Call tool
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = handle_tool_call(tool_name, arguments)

            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result.get("result", result.get("error", ""))}
                    ]
                },
            }
            print(json.dumps(response), flush=True)

        # Notifications (no response needed)
        elif method == "notifications/initialized":
            pass

        else:
            if msg_id is not None:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                print(json.dumps(response), flush=True)


# ── Direct CLI (for testing) ──────────────────────────

def main(argv: list[str] | None = None):
    """Entry point for the vault-mcp command."""
    parser = argparse.ArgumentParser(
        prog="vault-mcp",
        description="Vault-for-LLM MCP server",
    )
    parser.add_argument(
        "--project-dir",
        help="Project directory containing vault.db (defaults to VAULT_PATH or package root)",
    )
    parser.add_argument(
        "--tool-profile",
        choices=sorted(TOOL_PROFILES),
        default=os.environ.get("VAULT_MCP_TOOL_PROFILE", "full"),
        help=(
            "MCP tool visibility profile. Use 'core' to reduce agent tool-schema tokens. "
            "Default: full for backward compatibility."
        ),
    )
    parser.add_argument(
        "--tools",
        default=os.environ.get("VAULT_MCP_TOOLS"),
        help="Comma-separated explicit MCP tool allowlist; overrides --tool-profile.",
    )
    parser.add_argument(
        "--cli",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.project_dir:
        _set_project_dir(args.project_dir)

    try:
        _set_active_tools(args.tool_profile, args.tools)
    except ValueError as exc:
        parser.error(str(exc))

    if args.cli is not None:
        cli_args = args.cli
        tool_name = cli_args[0] if cli_args else "stats"
        tool_args = {}

        if tool_name == "search" and len(cli_args) > 1:
            tool_args = {"query": cli_args[1], "mode": "auto", "limit": 5}
        elif tool_name == "add" and len(cli_args) > 2:
            tool_args = {"title": cli_args[1], "content": cli_args[2]}
        elif tool_name == "stats":
            tool_args = {}
        elif tool_name == "converge":
            tool_args = {"limit": 5}
        elif tool_name == "freshness":
            tool_args = {"stale_only": True}

        result = handle_tool_call(f"vault_{tool_name}", tool_args)
        print(result.get("result", result.get("error", "")))
    else:
        run_stdio()


if __name__ == "__main__":
    main()
