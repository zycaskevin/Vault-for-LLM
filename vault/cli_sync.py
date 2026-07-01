"""CLI handlers for multi-host sync safety surfaces."""

from __future__ import annotations

import json
import sys

from .cli_context import find_project_dir
from .db import VaultDB
from .multi_host import list_audit_log, list_conflicts, list_revisions, resolve_conflict


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
            elif action == "resolve-conflict":
                payload = {
                    "ok": True,
                    "conflict": resolve_conflict(
                        db,
                        args.conflict_id,
                        resolution=args.resolution,
                        reason=args.reason or "",
                        actor_agent=args.agent_id or "",
                    ),
                }
            else:
                print("用法: vault sync {revisions|conflicts|audit|resolve-conflict}", file=sys.stderr)
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
    elif action == "resolve-conflict":
        row = payload["conflict"]
        print(f"sync conflict resolved: {row['id']} ({row['status']})")
