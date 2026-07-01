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
    json_output = _arg_value(args, "json", False) is True or _arg_value(args, "pretty", False) is True
    pretty_output = _arg_value(args, "pretty", False) is True

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
                    if json_output:
                        _json_print(
                            {
                                "ok": False,
                                "status": "error",
                                "error": "knowledge_not_found",
                                "message": str(exc),
                                "knowledge_id": knowledge_id,
                            },
                            pretty=pretty_output,
                        )
                        return
                    print(str(exc))
                    return
                total_nodes += result["nodes"]
                total_claims += result["claims"]

            payload = {
                "ok": True,
                "status": "ok",
                "action": "build",
                "knowledge_ids": knowledge_ids,
                "entry_count": len(knowledge_ids),
                "nodes": total_nodes,
                "claims": total_claims,
            }
            if json_output:
                _json_print(payload, pretty=pretty_output)
                return
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
                    if json_output:
                        _json_print(
                            {
                                "ok": False,
                                "status": "not_found",
                                "error": "knowledge_not_found",
                                "knowledge_id": args.knowledge_id,
                            },
                            pretty=pretty_output,
                        )
                        return
                    print(f"Knowledge id not found: {args.knowledge_id}")
                    return

                rows = conn.execute(
                    """SELECT node_uid, level, path, line_start, line_end
                       FROM knowledge_nodes
                       WHERE knowledge_id=?
                       ORDER BY line_start, level, id""",
                    (args.knowledge_id,),
                ).fetchall()

                payload = {
                    "ok": True,
                    "status": "ok",
                    "action": "show",
                    "knowledge_id": args.knowledge_id,
                    "title": entry["title"],
                    "node_count": len(rows),
                    "nodes": [dict(row) for row in rows],
                    "next_action": (
                        f"vault map build {args.knowledge_id}"
                        if not rows
                        else "Use vault map read <knowledge_id> --lines START-END for bounded reads."
                    ),
                }
                if json_output:
                    _json_print(payload, pretty=pretty_output)
                    return
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
                    if json_output:
                        _json_print(
                            {
                                "ok": False,
                                "status": "not_found",
                                "error": "knowledge_not_found",
                                "knowledge_id": args.knowledge_id,
                            },
                            pretty=pretty_output,
                        )
                        return
                    print(f"Knowledge id not found: {args.knowledge_id}")
                    return

                lines = (entry["content_raw"] or "").splitlines()
                total_lines = len(lines)
                if total_lines == 0:
                    if json_output:
                        _json_print(
                            {
                                "ok": True,
                                "status": "empty",
                                "action": "read",
                                "knowledge_id": args.knowledge_id,
                                "title": entry["title"],
                                "line_start": 0,
                                "line_end": 0,
                                "total_lines": 0,
                                "lines": [],
                            },
                            pretty=pretty_output,
                        )
                        return
                    print(f"#{args.knowledge_id} {entry['title']} L0-L0")
                    return

                clamped_start = min(max(1, start_line), total_lines)
                clamped_end = min(max(clamped_start, end_line), total_lines)

                payload = {
                    "ok": True,
                    "status": "ok",
                    "action": "read",
                    "knowledge_id": args.knowledge_id,
                    "title": entry["title"],
                    "line_start": clamped_start,
                    "line_end": clamped_end,
                    "total_lines": total_lines,
                    "lines": [
                        {"line_number": line_number, "text": lines[line_number - 1]}
                        for line_number in range(clamped_start, clamped_end + 1)
                    ],
                }
                if json_output:
                    _json_print(payload, pretty=pretty_output)
                    return
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

                payload = {
                    "ok": True,
                    "status": "ok",
                    "action": "query",
                    "query": args.query,
                    "count": len(rows),
                    "results": [dict(row) for row in rows],
                }
                if json_output:
                    _json_print(payload, pretty=pretty_output)
                    return
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
    if args.remote_action == "status":
        from vault.remote_status import build_remote_status

        project_dir = find_project_dir()
        payload = build_remote_status(
            project_dir,
            agent_id=args.agent_id or "",
            max_sync_age_minutes=args.max_sync_age_minutes,
        )
        if args.json or args.pretty:
            print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
            return
        _print_remote_status(payload)
        return

    if args.remote_action in {"submit-candidate", "pull-candidates"}:
        from vault.remote_candidates import (
            pull_remote_candidate_requests,
            submit_remote_candidate_request,
        )

        project_dir = find_project_dir()
        action = args.remote_action
        if action == "submit-candidate":
            payload = submit_remote_candidate_request(
                title=args.title,
                content=args.content,
                reason=args.reason or "",
                from_agent=args.from_agent or "",
                category=args.category or "general",
                tags=args.tags or "",
                trust=args.trust,
                scope=args.scope or "project",
                sensitivity=args.sensitivity or "low",
                owner_agent=args.owner_agent or "",
                allowed_agents=args.allowed_agents or "",
                memory_type=args.memory_type or "remote_candidate",
                source_ref=args.source_ref or "",
                idempotency_key=args.idempotency_key or "",
            )
        else:
            if args.auto_promote_low_risk and not args.apply:
                payload = {
                    "ok": False,
                    "error": "apply_required",
                    "message": "--auto-promote-low-risk requires --apply because it can write active knowledge.",
                }
                if args.json or args.pretty:
                    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
                    return
                print(f"error: {payload['error']}: {payload['message']}", file=sys.stderr)
                raise SystemExit(2)
            payload = pull_remote_candidate_requests(
                project_dir,
                agent_id=args.agent_id or "",
                limit=args.limit,
                apply=bool(args.apply),
                auto_promote_low_risk=bool(args.auto_promote_low_risk),
            )

        if args.json or args.pretty:
            print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
            return
        if payload.get("error"):
            print(f"error: {payload['error']}: {payload.get('message', '')}", file=sys.stderr)
            raise SystemExit(2)
        if action == "submit-candidate":
            print(f"remote candidate submitted: {payload.get('id', '')} ({payload.get('status', 'submitted')})")
        else:
            mode = "applied" if payload.get("apply") else "preview"
            print(
                f"remote candidate pull: {mode}, "
                f"{payload.get('count', 0)} request(s), "
                f"imported={payload.get('imported_count', 0)}, "
                f"skipped={payload.get('skipped_count', 0)}"
            )
            auto_promote = payload.get("auto_promote") or {}
            if auto_promote.get("enabled"):
                print(
                    "  auto-promote: "
                    f"{auto_promote.get('status', 'not_run')}, "
                    f"promoted={auto_promote.get('promoted_count', 0)}, "
                    f"eligible={auto_promote.get('would_promote_count', 0)}"
                )
            for item in payload.get("requests", []):
                print(f"  - {item.get('id', '')} {item.get('title', '')} [{item.get('status', '')}]")
        return

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
        print("用法: vault remote {search|map|read|smoke|doctor|submit-candidate|pull-candidates}")
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


def _print_remote_status(payload: dict) -> None:
    """Print a human-friendly local remote-sharing status."""
    local = payload.get("local", {})
    supabase = payload.get("supabase", {})
    remote_reader = payload.get("remote_reader", {})
    sync = payload.get("sync", {})
    access = payload.get("agent_access", {})

    print("Vault remote status")
    print(f"- Project: {payload.get('project_dir', '')}")
    print("- Source of truth: local vault.db")
    print("- Remote model: Supabase reviewed read copy plus candidate request inbox; active memory is not multi-master sync")
    print(f"- Local DB: {'ok' if local.get('db_exists') else 'missing'} ({local.get('knowledge_count', 0)} knowledge item(s))")
    print(
        "- Supabase env: "
        f"url={'yes' if supabase.get('url_configured') else 'no'}, "
        f"reader-key={'yes' if supabase.get('anon_key_configured') else 'no'}, "
        f"service-role={'present' if supabase.get('service_role_key_present') else 'absent'}"
    )
    reader_targets = [key for key, enabled in (remote_reader.get("targets") or {}).items() if enabled]
    sync_targets = [
        key
        for key, enabled in ((sync.get("templates") or {}).get("targets") or {}).items()
        if enabled
    ]
    print(f"- Remote reader templates: {', '.join(reader_targets) if reader_targets else 'none'}")
    print(f"- Sync templates: {', '.join(sync_targets) if sync_targets else 'none'}")
    report = (sync.get("last_report") or {})
    if report.get("exists"):
        age = report.get("age_minutes")
        age_text = f"{age} minutes old" if age is not None else "age unknown"
        print(f"- Last sync report: {report.get('path')} ({age_text})")
    else:
        print("- Last sync report: not found")
    print(
        "- Agent access: "
        f"{access.get('agent_count', 0)} roster agent(s), "
        f"remote readers={len(access.get('remote_readers') or [])}, "
        f"shared writers={len(access.get('shared_writers') or [])}"
    )
    warnings = payload.get("warnings") or []
    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"- [{item.get('severity', 'info')}] {item.get('message', '')}")
    actions = payload.get("next_actions") or []
    if actions:
        print("\nNext actions:")
        for item in actions:
            print(f"- {item}")


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
