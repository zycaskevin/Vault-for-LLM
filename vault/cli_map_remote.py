"""Document Map and remote-reader CLI handlers."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

from .cli_context import _arg_value, _enforce_cli_privacy, _json_print, find_project_dir
from .cli_search import temporal_search_kwargs


def cmd_map(args):
    """Document Map 操作：build / show / read / query。"""
    from vault.db import VaultDB
    from vault.docmap import build_document_map_for_entry

    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"
    action = args.map_action

    if action == "build":
        db = VaultDB(str(db_path))
        db.connect()
        try:
            if args.knowledge_id is not None:
                knowledge_ids = [args.knowledge_id]
            else:
                knowledge_ids = [
                    row["id"]
                    for row in db.conn.execute("SELECT id FROM knowledge ORDER BY id").fetchall()
                ]

            total_nodes = 0
            total_claims = 0
            for knowledge_id in knowledge_ids:
                try:
                    result = build_document_map_for_entry(db.conn, knowledge_id)
                except ValueError as exc:
                    print(str(exc))
                    return
                total_nodes += result["nodes"]
                total_claims += result["claims"]

            print(
                f"built {len(knowledge_ids)} entries: "
                f"nodes={total_nodes} claims={total_claims}"
            )
        finally:
            db.close()
        return

    if action in {"show", "read", "query"}:
        conn = _connect_map_readonly(db_path)
        if conn is None:
            return
        try:
            if action == "show":
                entry = _get_map_entry(conn, args.knowledge_id)
                if not entry:
                    print(f"Knowledge id not found: {args.knowledge_id}")
                    return

                rows = conn.execute(
                    """SELECT node_uid, level, path, line_start, line_end
                       FROM knowledge_nodes
                       WHERE knowledge_id=?
                       ORDER BY line_start, level, id""",
                    (args.knowledge_id,),
                ).fetchall()

                print(f"#{args.knowledge_id} {entry['title']}")
                if not rows:
                    print(
                        "No document map nodes found. "
                        f"Run: vault map build {args.knowledge_id}"
                    )
                    return

                for row in rows:
                    level = max(0, int(row["level"] or 0) - 1)
                    indent = "  " * level
                    print(
                        f"{indent}- {row['path']} [{row['node_uid']}] "
                        f"L{row['line_start']}-L{row['line_end']}"
                    )

            elif action == "read":
                try:
                    start_line, end_line = _parse_map_line_range(args.lines)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    raise SystemExit(2)

                entry = _get_map_entry(conn, args.knowledge_id)
                if not entry:
                    print(f"Knowledge id not found: {args.knowledge_id}")
                    return

                lines = (entry["content_raw"] or "").splitlines()
                total_lines = len(lines)
                if total_lines == 0:
                    print(f"#{args.knowledge_id} {entry['title']} L0-L0")
                    return

                clamped_start = min(max(1, start_line), total_lines)
                clamped_end = min(max(clamped_start, end_line), total_lines)

                print(f"#{args.knowledge_id} {entry['title']} L{clamped_start}-L{clamped_end}")
                for line_number in range(clamped_start, clamped_end + 1):
                    print(f"{line_number}|{lines[line_number - 1]}")

            elif action == "query":
                pattern = f"%{args.query}%"
                rows = conn.execute(
                    """SELECT c.knowledge_id, k.title, c.claim, c.node_uid,
                              c.line_start, c.line_end, COALESCE(n.path, '') AS path
                       FROM knowledge_claims c
                       JOIN knowledge k ON k.id = c.knowledge_id
                       LEFT JOIN knowledge_nodes n
                         ON n.knowledge_id = c.knowledge_id
                        AND n.node_uid = c.node_uid
                       WHERE c.claim LIKE ? OR k.title LIKE ? OR COALESCE(n.path, '') LIKE ?
                       ORDER BY c.knowledge_id, c.line_start, c.id
                       LIMIT ?""",
                    (pattern, pattern, pattern, args.limit),
                ).fetchall()

                if not rows:
                    print("No matching document map claims")
                    return

                for row in rows:
                    path = f" {row['path']}" if row["path"] else ""
                    node_uid = f" [{row['node_uid']}]" if row["node_uid"] else ""
                    print(
                        f"#{row['knowledge_id']} {row['title']} "
                        f"L{row['line_start']}-L{row['line_end']}{path}{node_uid}"
                    )
                    print(f"  {row['claim']}")
        finally:
            conn.close()
        return

    print("用法: vault map {build|show|read|query}")


def cmd_remote(args):
    """Supabase remote read workflow: search / map / read."""
    from vault.mcp import (
        _vault_remote_doctor_payload,
        _vault_remote_map_show_payload,
        _vault_remote_read_range_payload,
        _vault_remote_search_payload,
    )

    action = args.remote_action
    if action == "search":
        payload = _vault_remote_search_payload(
            query=args.query or "",
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
            limit=args.limit,
            compact=bool(args.compact),
        )
    elif action == "map":
        payload = _vault_remote_map_show_payload(
            args.knowledge_id,
            compact=bool(args.compact),
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
        )
    elif action == "read":
        line_start = 0
        line_end = 0
        if args.lines:
            try:
                line_start, line_end = _parse_map_line_range(args.lines)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                raise SystemExit(2)
        payload = _vault_remote_read_range_payload(
            args.knowledge_id,
            node_uid=args.node_uid or "",
            line_start=line_start,
            line_end=line_end,
            max_lines=args.max_lines,
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
        )
    elif action == "smoke":
        search_payload = _vault_remote_search_payload(
            query=args.query or "",
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
            limit=args.limit,
            compact=True,
        )
        payload = {
            "ok": not bool(search_payload.get("error")),
            "check": "vault_search_readable",
            "agent_id": args.agent_id or "",
            "query": args.query or "",
            "search": search_payload,
        }
        if not payload["ok"]:
            payload["next_action"] = search_payload.get("next_action") or {
                "message": "Set SUPABASE_URL and SUPABASE_ANON_KEY, apply docs/supabase_read_policy.sql, then retry."
            }
    elif action == "doctor":
        payload = _vault_remote_doctor_payload(
            query=args.query or "",
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
            limit=args.limit,
        )
    else:
        print("用法: vault remote {search|map|read|smoke|doctor}")
        return

    if args.json or args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    if payload.get("error"):
        print(f"error: {payload['error']}: {payload.get('message', '')}", file=sys.stderr)
        if payload.get("next_action"):
            print(json.dumps({"next_action": payload["next_action"]}, ensure_ascii=False))
        raise SystemExit(2)

    if action == "search":
        print(f"remote search: {payload.get('count', 0)} result(s)")
        for item in payload.get("results", []):
            print(f"  #{item.get('id')} {item.get('title', '')}")
            summary = item.get("summary")
            if summary:
                print(f"    {summary}")
            next_action = item.get("next_action")
            if next_action:
                print(f"    next: {next_action.get('tool')} {json.dumps(next_action.get('arguments', {}), ensure_ascii=False)}")
        return

    if action == "smoke":
        if payload.get("ok"):
            count = payload.get("search", {}).get("count", 0)
            print(f"remote smoke: ok ({count} readable result(s))")
            return
        error = payload.get("search", {}).get("error", "unknown")
        message = payload.get("search", {}).get("message", "")
        print(f"remote smoke: failed ({error}) {message}", file=sys.stderr)
        raise SystemExit(2)

    if action == "doctor":
        if payload.get("ok"):
            print("remote doctor: ok")
        else:
            print(f"remote doctor: failed ({payload.get('failure_mode')})", file=sys.stderr)
        for name, result in (payload.get("checks") or {}).items():
            print(f"  - {name}: {result}")
        if payload.get("next_action"):
            print(f"next: {payload['next_action']}")
        if not payload.get("ok"):
            raise SystemExit(2)
        return

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _connect_map_readonly(db_path: Path) -> sqlite3.Connection | None:
    """Open vault.db in SQLite read-only mode for map navigation commands."""
    if not db_path.exists():
        print(f"vault.db not found at {db_path}. Run vault init/compile first.")
        return None

    try:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        print(f"Unable to open vault.db read-only at {db_path}: {exc}")
        return None
    conn.row_factory = sqlite3.Row
    return conn


def _get_map_entry(conn: sqlite3.Connection, knowledge_id: int) -> sqlite3.Row | None:
    """Fetch a knowledge row through a raw SQLite connection."""
    return conn.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()


def _positive_int(value: str) -> int:
    """Argparse type requiring a positive integer."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parse_map_line_range(value: str) -> tuple[int, int]:
    """Parse an inclusive START-END line range for `vault map read`."""
    if not value or "-" not in value:
        raise ValueError("--lines must be START-END")
    start_raw, end_raw = value.split("-", 1)
    try:
        start_line = int(start_raw)
        end_line = int(end_raw)
    except ValueError as exc:
        raise ValueError("--lines must be START-END") from exc
    if start_line < 1 or end_line < 1 or end_line < start_line:
        raise ValueError("--lines must be a positive START-END range")
    return start_line, end_line
