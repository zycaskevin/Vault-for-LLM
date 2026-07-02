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

from vault.mcp_memory import handle_memory_tool_call
from vault.mcp_automation import handle_automation_tool_call
from vault.mcp_task import handle_task_tool_call
from vault.mcp_skill import handle_skill_tool_call
from vault.mcp_sync import handle_sync_tool_call
from vault.mcp_gateway import handle_gateway_tool_call
from vault.mcp_security import (
    check_agent_signature as _check_agent_signature,
    check_mcp_rate_limit as _check_mcp_rate_limit,
    reset_rate_limiter as _reset_rate_limiter,
)
from vault.mcp_search import (
    MCP_SEARCH_MAX_LIMIT,
    MCP_SEARCH_MAX_OFFSET,
    clamp_int as _clamp_int,
    search_field_set as _search_field_set,
    shape_search_results as _shape_search_results,
)
from vault.mcp_tools import (
    TOOLS,
    TOOL_PROFILES,
    active_tools,
    select_tools,
    _set_active_tools,
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


def handle_tool_call(name: str, arguments: dict) -> dict:
    """處理 MCP tool call，回傳結果。"""
    name = _canonical_tool_name(name)
    arguments = arguments or {}
    rate_limited = _check_mcp_rate_limit(name, arguments)
    if rate_limited is not None:
        return {"result": json.dumps(rate_limited, ensure_ascii=False, indent=2)}
    signature_denied = _check_agent_signature(name, arguments)
    if signature_denied is not None:
        return {"result": json.dumps(signature_denied, ensure_ascii=False, indent=2)}
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
                max_sensitivity=arguments.get("max_sensitivity") or "medium",
                include_expired_temporal=bool(arguments.get("include_expired_temporal", True)),
                include_future_temporal=bool(arguments.get("include_future_temporal", True)),
                temporal_as_of=arguments.get("temporal_as_of", ""),
            )
            output = _shape_search_results(results, compact=compact, field_set=field_set)
            db.close()
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        memory_payload = handle_memory_tool_call(name, arguments)
        if memory_payload is not None:
            return memory_payload

        automation_payload = handle_automation_tool_call(name, arguments, db_path=DB_PATH)
        if automation_payload is not None:
            return automation_payload

        task_payload = handle_task_tool_call(name, arguments, db_path=DB_PATH)
        if task_payload is not None:
            return task_payload

        skill_payload = handle_skill_tool_call(name, arguments, db_path=DB_PATH)
        if skill_payload is not None:
            return skill_payload

        sync_payload = handle_sync_tool_call(name, arguments, db_path=DB_PATH)
        if sync_payload is not None:
            return sync_payload

        gateway_payload = handle_gateway_tool_call(name, arguments, db_path=DB_PATH)
        if gateway_payload is not None:
            return gateway_payload

        if name == "vault_obsidian_import":
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
                    prune_missing=bool(arguments.get("prune_missing", False)),
                    conflict_inbox=bool(arguments.get("conflict_inbox", False)),
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

        if name == "vault_obsidian_resolve_conflict":
            from vault.agent_setup import compile_project
            from vault.import_obsidian import resolve_obsidian_conflict

            project_dir = Path(DB_PATH).resolve().parent
            dry_run = bool(arguments.get("dry_run", False))
            resolution_payload = resolve_obsidian_conflict(
                project_dir=project_dir,
                vault_dir=arguments.get("vault_dir", ""),
                source_path=arguments.get("source_path", ""),
                resolution=arguments.get("resolution", ""),
                category=arguments.get("category", "obsidian"),
                tags=arguments.get("tags", "obsidian"),
                layer=arguments.get("layer", "L3"),
                trust=float(arguments.get("trust", 0.5)),
                allow_private=bool(arguments.get("allow_private", False)),
                dry_run=dry_run,
                conflict_inbox=bool(arguments.get("conflict_inbox", True)),
            )
            payload = {
                "project_dir": str(project_dir),
                "vault_dir": arguments.get("vault_dir", ""),
                "resolution": resolution_payload,
                "next_action": {
                    "tool": "vault_obsidian_import",
                    "arguments": {
                        "vault_dir": arguments.get("vault_dir", ""),
                        "dry_run": False,
                        "compile": True,
                        "conflict_inbox": True,
                    },
                    "instruction": "Re-run Obsidian import after resolving conflicts so the manifest and compiled knowledge stay fresh.",
                },
            }
            if bool(arguments.get("compile", False)) and not dry_run:
                payload["compile"] = compile_project(
                    project_dir,
                    allow_private=bool(arguments.get("allow_private", False)),
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
                max_sensitivity=arguments.get("max_sensitivity") or "medium",
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
                max_sensitivity=arguments.get("max_sensitivity") or "medium",
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
                "result": {"tools": active_tools()},
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
