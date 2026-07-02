"""CLI handlers for multi-host sync safety surfaces."""

from __future__ import annotations

import argparse
import json
import sys

from .cli_context import find_project_dir
from .db import VaultDB
from .multi_host import list_audit_log, list_conflicts, list_revisions, preview_conflict, resolve_conflict


def add_sync_parser(sub: argparse._SubParsersAction) -> None:
    """Register local multi-host sync safety commands."""
    parser = sub.add_parser("sync", help="多主機同步安全狀態：revision、conflict、audit")
    sync_sub = parser.add_subparsers(dest="sync_action", help="Sync 子命令")

    sp = sync_sub.add_parser("revisions", help="列出本機 revision graph 事件")
    sp.add_argument("--limit", "-n", type=_positive_int, default=20)
    _add_output_args(sp)

    sp = sync_sub.add_parser("conflicts", help="列出待處理或已處理的同步衝突")
    sp.add_argument("--status", choices=["open", "resolved", ""], default="open")
    sp.add_argument("--limit", "-n", type=_positive_int, default=20)
    _add_output_args(sp)

    sp = sync_sub.add_parser("audit", help="列出同步/合併 audit log")
    sp.add_argument("--limit", "-n", type=_positive_int, default=20)
    _add_output_args(sp)

    sp = sync_sub.add_parser("preview-conflict", help="預覽同步衝突差異與建議，不修改記憶")
    sp.add_argument("conflict_id", help="conflict id")
    sp.add_argument("--context-lines", type=_positive_int, default=2, help="diff 上下文行數")
    _add_output_args(sp)

    sp = sync_sub.add_parser("resolve-conflict", help="標記同步衝突已被人工處理")
    sp.add_argument("conflict_id", help="conflict id")
    sp.add_argument("--resolution", choices=["keep_local", "accept_remote", "manual"], required=True)
    sp.add_argument("--reason", default="", help="解決原因")
    sp.add_argument("--agent-id", default="", help="處理此衝突的 Agent ID")
    sp.add_argument(
        "--apply-memory-change",
        action="store_true",
        help="允許 accept_remote 實際 promote 遠端候選並歸檔本地舊知識；manual/keep_local 不需要",
    )
    _add_output_args(sp)


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def cmd_sync(args) -> None:
    project_dir = find_project_dir()
    action = getattr(args, "sync_action", "")
    try:
        with VaultDB(project_dir / "vault.db") as db:
            if action == "revisions":
                payload = {
                    "ok": True,
                    "revisions": list_revisions(db, limit=args.limit),
                }
            elif action == "conflicts":
                payload = {
                    "ok": True,
                    "conflicts": list_conflicts(db, status=args.status, limit=args.limit),
                }
            elif action == "audit":
                payload = {
                    "ok": True,
                    "events": list_audit_log(db, limit=args.limit),
                }
            elif action == "preview-conflict":
                payload = preview_conflict(
                    db,
                    args.conflict_id,
                    context_lines=getattr(args, "context_lines", 2),
                )
            elif action == "resolve-conflict":
                payload = {
                    "ok": True,
                    "conflict": resolve_conflict(
                        db,
                        args.conflict_id,
                        resolution=args.resolution,
                        reason=args.reason or "",
                        actor_agent=args.agent_id or "",
                        apply_memory_change=bool(getattr(args, "apply_memory_change", False)),
                        project_dir=project_dir,
                    ),
                }
            else:
                print("用法: vault sync {revisions|conflicts|audit|preview-conflict|resolve-conflict}", file=sys.stderr)
                raise SystemExit(2)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if getattr(args, "json", False) or getattr(args, "pretty", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
        return

    if action == "revisions":
        print(f"sync revisions: {len(payload['revisions'])} item(s)")
        for row in payload["revisions"]:
            print(f"  - {row['id']} {row['operation']} {row['status']} {row['title']}")
    elif action == "conflicts":
        print(f"sync conflicts: {len(payload['conflicts'])} item(s)")
        for row in payload["conflicts"]:
            print(f"  - {row['id']} {row['status']} {row['conflict_type']} {row['reason']}")
    elif action == "audit":
        print(f"sync audit: {len(payload['events'])} event(s)")
        for row in payload["events"]:
            print(f"  - {row['id']} {row['action']} {row['target_type']}:{row['target_id']}")
    elif action == "preview-conflict":
        conflict = payload["conflict"]
        print(f"sync conflict preview: {conflict['id']} ({payload['status']})")
        print(f"  type: {conflict.get('conflict_type', '')}")
        print(f"  reason: {conflict.get('reason', '')}")
        print(f"  local:  #{payload['local'].get('id', '')} {payload['local'].get('title', '')}")
        print(f"  remote: {payload['remote'].get('id', '')} {payload['remote'].get('title', '')}")
        print(f"  suggested: {payload['recommendation'].get('safe_action', '')}")
        print(f"  next: {payload['recommendation'].get('command', '')}")
    elif action == "resolve-conflict":
        row = payload["conflict"]
        print(f"sync conflict resolved: {row['id']} ({row['status']})")
