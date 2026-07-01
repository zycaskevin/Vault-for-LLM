"""Memory, automation, db, setup-agent, and update-status CLI handlers."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

from .cli_context import _arg_value, _enforce_cli_privacy, _json_flags, _json_print, find_project_dir
from .cli_search import temporal_search_kwargs

def cmd_remember(args):
    """Create a memory candidate or promote it immediately if gates allow."""
    from vault.db import VaultDB
    from vault.memory import propose_memory

    project_dir = find_project_dir()
    content = _arg_value(args, "content", None)
    file_arg = _arg_value(args, "file", None)
    if file_arg:
        content = Path(file_arg).read_text(encoding="utf-8")
    elif content is None:
        content = sys.stdin.read()
    if content == "":
        print("error: content is empty; pass non-empty --content, --file, or stdin input", file=sys.stderr)
        raise SystemExit(2)
    try:
        with VaultDB(project_dir / "vault.db") as db:
            payload = propose_memory(
                db,
                title=args.title,
                content=content,
                reason=args.reason,
                mode=_arg_value(args, "mode", "candidate"),
                layer=_arg_value(args, "layer", "L3"),
                category=_arg_value(args, "category", "general"),
                tags=_arg_value(args, "tags", ""),
                trust=_arg_value(args, "trust", 0.5),
                source=_arg_value(args, "source", "cli"),
                source_ref=_arg_value(args, "source_ref", ""),
                scope=_arg_value(args, "scope", "project"),
                sensitivity=_arg_value(args, "sensitivity", "low"),
                owner_agent=_arg_value(args, "owner_agent", ""),
                allowed_agents=_arg_value(args, "allowed_agents", ""),
                memory_type=_arg_value(args, "memory_type", "knowledge"),
                expires_at=_arg_value(args, "expires_at", ""),
                valid_from=_arg_value(args, "valid_from", ""),
                valid_until=_arg_value(args, "valid_until", ""),
                supersedes_id=_arg_value(args, "supersedes_id", None),
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    payload.setdefault("ok", True)
    _json_print(payload, pretty=args.pretty)


def cmd_promote(args):
    """Promote a memory candidate into raw/ plus active SQLite knowledge."""
    from vault.db import VaultDB
    from vault.memory import promote_candidate

    project_dir = find_project_dir()
    try:
        with VaultDB(project_dir / "vault.db") as db:
            payload = promote_candidate(
                db,
                args.candidate_id,
                confirm=args.confirm,
                project_dir=project_dir,
                compile=not args.no_compile,
                build_map=not args.no_build_map,
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def cmd_candidate_review(args):
    """Record a rejected/blocked review outcome for a memory candidate."""
    from vault.db import VaultDB
    from vault.memory import review_candidate

    project_dir = find_project_dir()
    try:
        with VaultDB(project_dir / "vault.db") as db:
            payload = review_candidate(
                db,
                args.candidate_id,
                outcome=args.outcome,
                reason=args.reason,
                score=args.score,
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def _format_memory_candidate(row: dict, *, include_content: bool = False, include_gates: bool = False) -> dict:
    item = {
        "id": row.get("id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "layer": row.get("layer"),
        "category": row.get("category"),
        "tags": row.get("tags"),
        "trust": row.get("trust"),
        "scope": row.get("scope"),
        "sensitivity": row.get("sensitivity"),
        "owner_agent": row.get("owner_agent"),
        "allowed_agents": row.get("allowed_agents"),
        "memory_type": row.get("memory_type"),
        "expires_at": row.get("expires_at"),
        "valid_from": row.get("valid_from"),
        "valid_until": row.get("valid_until"),
        "supersedes_id": row.get("supersedes_id"),
        "source": row.get("source"),
        "source_ref": row.get("source_ref"),
        "reason": row.get("reason"),
        "privacy_status": row.get("privacy_status"),
        "duplicate_status": row.get("duplicate_status"),
        "quality_status": row.get("quality_status"),
        "promoted_knowledge_id": row.get("promoted_knowledge_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    content = row.get("content") or ""
    item["content_length"] = len(content)
    if include_content:
        item["content"] = content
    elif content:
        item["content_preview"] = " ".join(content.split())[:180]
    if include_gates:
        raw_gates = row.get("gate_payload_json") or "{}"
        try:
            item["gates"] = json.loads(raw_gates)
        except json.JSONDecodeError:
            item["gates"] = {"raw": raw_gates}
    return item


def cmd_candidates(args):
    """List memory candidates without reading the SQLite database by hand."""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    status = None if args.all else args.status
    try:
        with VaultDB(project_dir / "vault.db") as db:
            rows = db.list_memory_candidates(status=status, limit=args.limit)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    payload = {
        "ok": True,
        "count": len(rows),
        "status": status or "all",
        "candidates": [
            _format_memory_candidate(
                row,
                include_content=args.include_content,
                include_gates=args.include_gates,
            )
            for row in rows
        ],
    }
    _json_print(payload, pretty=args.pretty)


def cmd_capture(args):
    """Capture agent/session artifacts into reviewable memory candidates."""
    if args.capture_action == "discover":
        from vault.session_capture import discover_session_transcripts

        project_dir = find_project_dir()
        try:
            payload = discover_session_transcripts(
                project_dir,
                search_dirs=args.search_dir or None,
                source_system=args.source_system,
                limit=args.limit,
                max_depth=args.max_depth,
                max_file_mb=args.max_file_mb,
                allow_absolute_paths=bool(args.allow_absolute_paths),
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        _json_print(payload, pretty=args.pretty)
        return

    if args.capture_action != "session":
        print("用法: vault capture session <transcript> 或 vault capture discover", file=sys.stderr)
        raise SystemExit(2)
    from vault.db import VaultDB
    from vault.session_capture import capture_session_candidates

    project_dir = find_project_dir()
    try:
        with VaultDB(project_dir / "vault.db") as db:
            payload = capture_session_candidates(
                db,
                args.transcript,
                input_format=args.format,
                source_system=args.source_system,
                agent_id=args.agent_id,
                write_candidates=bool(args.write_candidates),
                max_candidates=args.max_candidates,
                min_score=args.min_score,
                scope=args.scope,
                sensitivity=args.sensitivity,
                owner_agent=args.owner_agent,
                allowed_agents=args.allowed_agents,
                include_content=bool(args.include_content),
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def _print_task_summary(task: dict) -> None:
    title = task.get("title") or task.get("id")
    print(f"Task: {title}")
    print(f"  id: {task.get('id')}")
    print(f"  status: {task.get('status')}")
    print(f"  priority: {task.get('priority') or 'P2'}")
    if task.get("due_at"):
        print(f"  due_at: {task.get('due_at')}")
    print(f"  goal: {task.get('goal')}")
    if task.get("next_actions"):
        print("  next_actions:")
        for item in task.get("next_actions", []):
            print(f"    - {item}")
    if task.get("continuation_note"):
        print(f"  continuation_note: {task.get('continuation_note')}")


def cmd_task(args):
    """Task Ledger runtime working-set workflows."""
    from vault.db import VaultDB
    from vault.task_ledger import (
        claim_task_handoff,
        complete_task,
        create_task_handoff,
        get_task,
        list_task_handoffs,
        list_tasks,
        start_task,
        task_handoff,
        update_task,
    )

    action = getattr(args, "task_action", "")
    if action not in {
        "start",
        "update",
        "status",
        "resume",
        "handoff",
        "send-handoff",
        "inbox",
        "claim-handoff",
        "complete",
    }:
        print(
            "error: task requires action: start, update, status, resume, handoff, send-handoff, inbox, claim-handoff, or complete",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        with VaultDB(find_project_dir() / "vault.db") as db:
            if action == "start":
                payload = start_task(
                    db,
                    args.goal,
                    task_id=args.task_id,
                    title=args.title,
                    current_plan=args.plan,
                    next_actions=args.next_action,
                    evidence_refs=args.evidence_ref,
                    continuation_note=args.continuation_note,
                    priority=args.priority,
                    due_at=args.due_at,
                    scope=args.scope,
                    sensitivity=args.sensitivity,
                    owner_agent=args.owner_agent,
                    allowed_agents=args.allowed_agents,
                    source=args.source,
                )
            elif action == "update":
                payload = update_task(
                    db,
                    args.task_id,
                    current_plan=args.plan,
                    completed=args.done,
                    hard_decisions=args.decision,
                    blockers=args.blocker,
                    open_questions=args.question,
                    next_actions=args.next_action,
                    evidence_refs=args.evidence_ref,
                    continuation_note=args.continuation_note,
                    priority=args.priority,
                    due_at=args.due_at,
                    status=args.status,
                    agent_id=args.agent_id,
                    source_ref=args.source_ref,
                )
            elif action in {"status", "resume"}:
                if args.task_id:
                    task = get_task(db, args.task_id, include_events=bool(args.include_events))
                    if not task:
                        raise KeyError(f"task not found: {args.task_id}")
                    payload = {"ok": True, "action": action, "task": task}
                else:
                    payload = {
                        "ok": True,
                        "action": "list",
                        "status": args.status,
                        "tasks": list_tasks(db, status=args.status, limit=args.limit),
                    }
            elif action == "handoff":
                payload = task_handoff(db, args.task_id)
            elif action == "send-handoff":
                payload = create_task_handoff(
                    db,
                    args.task_id,
                    handoff_id=args.handoff_id,
                    from_agent=args.from_agent,
                    to_agent=args.to_agent,
                    message=args.message,
                    source_ref=args.source_ref,
                )
            elif action == "inbox":
                payload = {
                    "ok": True,
                    "action": "inbox",
                    "agent_id": args.agent_id,
                    "status": args.status,
                    "handoffs": list_task_handoffs(
                        db,
                        agent_id=args.agent_id,
                        status=args.status,
                        limit=args.limit,
                    ),
                }
            elif action == "claim-handoff":
                payload = claim_task_handoff(
                    db,
                    args.handoff_id,
                    agent_id=args.agent_id,
                    note=args.note,
                )
            else:
                payload = complete_task(
                    db,
                    args.task_id,
                    summary=args.summary,
                    next_actions=args.next_action,
                    agent_id=args.agent_id,
                )
    except (KeyError, ValueError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    json_output, pretty_output = _json_flags(args)
    if json_output:
        _json_print(payload, pretty=pretty_output)
        return

    if action == "handoff":
        print(payload["markdown"], end="")
    elif action == "send-handoff":
        handoff = payload["handoff"]
        print(f"Handoff sent: {handoff.get('id')}")
        print(f"  task_id: {handoff.get('task_id')}")
        print(f"  from_agent: {handoff.get('from_agent')}")
        print(f"  to_agent: {handoff.get('to_agent')}")
    elif action == "inbox":
        handoffs = payload.get("handoffs", [])
        print(f"Handoff inbox ({payload.get('status')}): {len(handoffs)}")
        for handoff in handoffs:
            print(
                f"  {handoff.get('id')} [{handoff.get('status')}]"
                f" task={handoff.get('task_id')} from={handoff.get('from_agent')} to={handoff.get('to_agent')}"
            )
    elif action == "claim-handoff":
        handoff = payload["handoff"]
        print(f"Handoff claimed: {handoff.get('id')}")
        print(f"  claimed_by: {handoff.get('claimed_by')}")
        print(f"  task_id: {handoff.get('task_id')}")
    elif payload.get("task"):
        _print_task_summary(payload["task"])
    else:
        tasks = payload.get("tasks", [])
        print(f"Tasks ({payload.get('status') or 'all'}): {len(tasks)}")
        for task in tasks:
            due = f" due={task.get('due_at')}" if task.get("due_at") else ""
            print(
                f"  {task.get('id')} [{task.get('status')}/{task.get('priority') or 'P2'}]"
                f"{due} {task.get('title') or task.get('goal')}"
            )


def cmd_dream(args):
    """Run a deterministic report-first dream curation pass."""
    from vault.dream import run_dream

    project_dir = find_project_dir()
    try:
        payload = run_dream(
            project_dir,
            mode=args.mode,
            checks=args.checks,
            limit=args.limit,
            write_report=args.write_report,
            write_candidates=bool(getattr(args, "write_candidates", False)),
            backup=not args.no_backup,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def cmd_usage(args):
    """Memory usage telemetry and TTL archive workflows."""
    from vault.db import VaultDB

    action = getattr(args, "usage_action", "")
    if action not in {"stats", "archive-expired", "cold-store-expired"}:
        print("error: usage requires action: stats, archive-expired, or cold-store-expired", file=sys.stderr)
        raise SystemExit(2)

    try:
        with VaultDB(find_project_dir() / "vault.db") as db:
            if action == "stats":
                payload = {
                    "action": "stats",
                    **db.usage_stats(limit=args.limit),
                }
            elif action == "archive-expired":
                payload = db.archive_expired_knowledge(
                    limit=args.limit,
                    dry_run=not args.apply,
                )
            else:
                payload = db.cold_store_expired_knowledge(
                    limit=args.limit,
                    dry_run=not args.apply,
                    min_usage=getattr(args, "min_usage", 1),
                    summary_max_chars=getattr(args, "summary_max_chars", 360),
                )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.json or args.pretty:
        _json_print(payload, pretty=args.pretty)
        return

    if action == "stats":
        print("📈 Memory usage\n")
        print(f"  知識筆數:       {payload.get('knowledge_count', 0)}")
        print(f"  已到期未歸檔:   {payload.get('expired_active_count', 0)}")
        print(f"  檢索命中次數:   {payload.get('total_accesses', 0)}")
        print(f"  引用次數:       {payload.get('total_citations', 0)}")
        status_counts = payload.get("status_counts", {})
        if status_counts:
            print("  狀態:")
            for status, count in sorted(status_counts.items()):
                print(f"    - {status}: {count}")
        top_used = payload.get("top_used", [])
        if top_used:
            print("\n  Top used:")
            for row in top_used:
                print(
                    f"    #{row.get('id')} {row.get('title')} "
                    f"(access={row.get('access_count', 0)}, citations={row.get('citation_count', 0)})"
                )
        return

    verb = "would archive" if payload.get("dry_run") else "archived"
    if action == "archive-expired":
        print(f"🗄️  TTL archive {verb}: {payload.get('eligible_count', 0)} eligible")
        if payload.get("dry_run"):
            print("   Add --apply to archive these memories.")
        for row in payload.get("items", [])[: args.limit]:
            print(f"  #{row.get('id')} {row.get('title')} expires_at={row.get('expires_at')}")
        return

    verb = "would cold-store" if payload.get("dry_run") else "cold-stored"
    print(f"🧊 TTL cold-store {verb}: {payload.get('eligible_count', 0)} eligible")
    print(
        f"   skipped_low_usage={payload.get('skipped_low_usage_count', 0)} "
        f"skipped_protected={payload.get('skipped_protected_count', 0)}"
    )
    if payload.get("dry_run"):
        print("   Add --apply to summarize and archive these memories.")
    for row in payload.get("items", [])[: args.limit]:
        print(
            f"  #{row.get('id')} {row.get('title')} "
            f"usage={row.get('usage_count', 0)} layer={row.get('layer')}->{row.get('target_layer')}"
        )


def cmd_automation(args):
    """Policy-based memory automation workflows."""
    from vault.cli_automation import cmd_automation as _cmd_automation

    return _cmd_automation(
        args,
        find_project_dir=find_project_dir,
        json_print=_json_print,
    )


def cmd_db(args):
    """SQLite schema migration/status/backup workflows."""
    from vault.db import VaultDB
    from vault.db_backup import BackupError, backup_database, restore_database, verify_backup

    action = args.db_action
    if action not in {"status", "migrate", "backup", "verify-backup", "restore"}:
        print(
            "error: db requires action: status, migrate, backup, verify-backup, or restore",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        if action == "verify-backup":
            payload = verify_backup(args.backup_path)
            _json_print(payload, pretty=args.pretty)
            return

        db_path = Path(args.db_path) if args.db_path else find_project_dir() / "vault.db"
        if action == "backup":
            payload = backup_database(db_path, args.output, verify=args.verify)
        elif action == "restore":
            payload = restore_database(args.backup_path, db_path, force=args.force)
        else:
            with VaultDB(db_path) as db:
                payload = db.schema_status() if action == "status" else db.migrate()
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    _json_print(payload, pretty=args.pretty)

def cmd_export(args):
    """One-way export commands for human-readable knowledge browsing."""
    if args.export_target not in {"obsidian", "okf"}:
        print("error: export requires target: obsidian or okf", file=sys.stderr)
        raise SystemExit(2)
    json_output, pretty_output = _json_flags(args)
    if args.export_target == "okf":
        from vault.okf import export_okf_bundle

        try:
            result = export_okf_bundle(
                project_dir=find_project_dir(),
                bundle_dir=args.bundle,
                category=args.category,
                tag=args.tag,
                layer=args.layer,
                limit=args.limit,
                min_trust=args.min_trust,
                include_private=args.include_private,
                include_restricted=args.include_restricted,
                dry_run=args.dry_run,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        if json_output:
            _json_print(result, pretty=pretty_output)
            return
        print(
            "OKF export: "
            f"matched={result['matched']} written={result['written']} "
            f"dry_run={result['dry_run']} bundle={result['bundle_dir']}"
        )
        for path in [*result["reserved_paths"], *result["paths"]][:12]:
            print(f"  {path}")
        total_paths = len(result["reserved_paths"]) + len(result["paths"])
        if total_paths > 12:
            print(f"  ... {total_paths - 12} more")
        return

    from vault.export_obsidian import export_obsidian_vault
    try:
        result = export_obsidian_vault(
            project_dir=find_project_dir(),
            vault_dir=args.vault,
            category=args.category,
            tag=args.tag,
            layer=args.layer,
            limit=args.limit,
            min_trust=args.min_trust,
            source=args.source,
            dry_run=args.dry_run,
            include_review_inbox=getattr(args, "include_review_inbox", False),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if json_output:
        _json_print({"ok": True, "status": "ok", **result}, pretty=pretty_output)
        return
    print(
        "Obsidian export: "
        f"matched={result['matched']} written={result['written']} "
        f"dry_run={result['dry_run']} vault={result['vault_dir']}"
    )
    for path in result["paths"][:10]:
        print(f"  {path}")
    if len(result["paths"]) > 10:
        print(f"  ... {len(result['paths']) - 10} more")
def cmd_setup_agent(args):
    """Interactive/non-interactive agent setup wizard."""
    from vault.agent_access import agent_access_preset
    from vault.agent_setup import (
        AgentSetupConfig,
        default_stable_venv_path,
        default_project_dir,
        interactive_setup,
        normalize_features,
        run_agent_setup,
    )

    def _agent_access_overrides_from_args() -> dict[str, object]:
        overrides: dict[str, object] = {}
        if args.scope in {"private", "shared"}:
            overrides["scope"] = args.scope
        if args.tool_profile:
            overrides["tool_profile"] = args.tool_profile
        if args.memory_layout:
            overrides["memory_layout"] = args.memory_layout
        if getattr(args, "max_sensitivity", None):
            overrides["max_sensitivity"] = args.max_sensitivity
        for attr in [
            "can_write_candidates",
            "can_promote",
            "can_write_shared",
            "can_write_private",
            "private_memory",
            "agent_remote_reader",
        ]:
            value = getattr(args, attr, None)
            if value is not None:
                key = "remote_reader" if attr == "agent_remote_reader" else attr
                overrides[key] = bool(value)
        return overrides

    if getattr(args, "non_interactive", False):
        preset = agent_access_preset(args.agent_preset)
        scope = args.scope or preset.get("setup_scope") or "private"
        project_dir = Path(args.agent_project_dir or default_project_dir(scope, agent=args.agent))
        config = AgentSetupConfig(
            project_dir=project_dir,
            scope=scope,
            agent=args.agent,
            agent_preset=args.agent_preset or "",
            audience=args.audience,
            memory_layout=args.memory_layout or preset.get("memory_layout") or "hybrid",
            agent_private_dir=Path(args.agent_private_dir).expanduser() if args.agent_private_dir else None,
            features=normalize_features(args.features),
            language=args.language,
            tool_profile=args.tool_profile or preset.get("tool_profile") or "core",
            install_optional_deps=bool(args.install_optional_deps),
            install_embedding_model=args.install_embedding_model,
            obsidian_vault=Path(args.obsidian_vault).expanduser() if args.obsidian_vault else None,
            import_obsidian=bool(args.import_obsidian),
            obsidian_rules_path=Path(args.obsidian_rules).expanduser() if args.obsidian_rules else None,
            obsidian_write_default_rules=bool(args.obsidian_write_default_rules),
            obsidian_review_inbox=bool(args.obsidian_review_inbox),
            sync_targets=args.obsidian_sync,
            sync_interval_minutes=args.sync_interval_minutes,
            supabase_sync_targets=args.supabase_sync,
            supabase_setup_mode=args.supabase_setup or "simple",
            supabase_sync_interval_minutes=args.supabase_sync_interval_minutes,
            remote_reader_targets=args.remote_reader,
            remote_reader_query=args.remote_reader_query,
            agent_roster=args.agent_roster,
            validation_pack_targets=args.validation_pack,
            automation_schedule_targets=args.automation_schedule,
            automation_interval_minutes=args.automation_interval_minutes,
            automation_mode=args.automation_mode,
            automation_command=args.automation_command,
            automation_apply=bool(args.automation_apply),
            automation_write_workspace=bool(args.automation_write_workspace),
            automation_workspace_inbox_limit=args.automation_workspace_inbox_limit,
            automation_include_transcripts=bool(args.automation_include_transcripts),
            automation_transcript_limit=args.automation_transcript_limit,
            automation_capture_transcripts=bool(args.automation_capture_transcripts),
            automation_capture_transcript_limit=args.automation_capture_transcript_limit,
            automation_auto_promote_low_risk=bool(args.automation_auto_promote_low_risk),
            daily_report_time=args.daily_report_time,
            template_dir=Path(args.template_dir).expanduser() if args.template_dir else None,
            allow_private=bool(args.allow_private),
            stable_venv_path=(
                Path(args.stable_venv).expanduser()
                if args.stable_venv
                else (default_stable_venv_path() if args.write_stable_venv_script else None)
            ),
            agent_access_overrides=_agent_access_overrides_from_args(),
        )
    else:
        setup_values = {
            "agent": args.agent,
            "agent_preset": args.agent_preset,
            "scope": args.scope,
            "audience": args.audience,
            "project_dir": args.agent_project_dir,
            "memory_layout": args.memory_layout,
            "agent_private_dir": args.agent_private_dir,
            "features": args.features,
            "language": args.language,
            "tool_profile": args.tool_profile,
            "max_sensitivity": args.max_sensitivity,
            "install_optional_deps": args.install_optional_deps,
            "install_embedding_model": args.install_embedding_model,
            "obsidian_vault": args.obsidian_vault,
            "obsidian_rules_path": args.obsidian_rules,
            "supabase_setup_mode": args.supabase_setup,
            "remote_reader_query": args.remote_reader_query,
            "agent_roster": args.agent_roster,
            "sync_interval_minutes": args.sync_interval_minutes,
            "supabase_sync_interval_minutes": args.supabase_sync_interval_minutes,
            "automation_interval_minutes": args.automation_interval_minutes,
            "automation_workspace_inbox_limit": args.automation_workspace_inbox_limit,
            "automation_transcript_limit": args.automation_transcript_limit,
            "automation_capture_transcript_limit": args.automation_capture_transcript_limit,
            "daily_report_time": args.daily_report_time,
            "template_dir": args.template_dir,
            "allow_private": args.allow_private,
            "stable_venv_path": args.stable_venv,
            "write_stable_venv_script": args.write_stable_venv_script,
        }
        setup_values["agent_access_overrides"] = _agent_access_overrides_from_args()
        if args.import_obsidian:
            setup_values["import_obsidian"] = True
        if args.obsidian_write_default_rules:
            setup_values["obsidian_write_default_rules"] = True
        if args.obsidian_review_inbox:
            setup_values["obsidian_review_inbox"] = True
        if args.obsidian_sync != "none":
            setup_values["sync_targets"] = args.obsidian_sync
        if args.supabase_sync != "none":
            setup_values["supabase_sync_targets"] = args.supabase_sync
        if args.remote_reader != "none":
            setup_values["remote_reader_targets"] = args.remote_reader
        if args.validation_pack != "none":
            setup_values["validation_pack_targets"] = args.validation_pack
        if args.automation_schedule != "none":
            setup_values["automation_schedule_targets"] = args.automation_schedule
        if args.automation_mode != "balanced":
            setup_values["automation_mode"] = args.automation_mode
        if args.automation_command != "cycle":
            setup_values["automation_command"] = args.automation_command
        if args.automation_apply:
            setup_values["automation_apply"] = True
        if args.automation_write_workspace:
            setup_values["automation_write_workspace"] = True
        if args.automation_include_transcripts:
            setup_values["automation_include_transcripts"] = True
        if args.automation_capture_transcripts:
            setup_values["automation_capture_transcripts"] = True
        if args.automation_auto_promote_low_risk:
            setup_values["automation_auto_promote_low_risk"] = True
        config = interactive_setup(setup_values)

    payload = run_agent_setup(config)
    payload.setdefault("ok", True)
    payload.setdefault("status", "ok")
    if args.pretty or args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if payload.get("audience") == "consumer":
        _print_consumer_setup_summary(payload)
        return

    print("Agent setup complete")
    print(f"  project_dir: {payload['project_dir']}")
    print(f"  db_path: {payload['db_path']}")
    print(f"  features: {', '.join(payload['features'])}")
    print(f"  memory_layout: {payload['memory_layout']}")
    if payload.get("agent_private_dir"):
        print(f"  agent_private_dir: {payload['agent_private_dir']}")
    print(f"  language: {payload['language']}")
    if payload.get("obsidian"):
        obsidian = payload["obsidian"]
        dry = obsidian.get("dry_run") or {}
        imported = obsidian.get("import") or {}
        print(f"  obsidian_vault: {obsidian.get('vault')}")
        if dry:
            print(
                "  obsidian_dry_run: "
                f"scanned={dry.get('scanned')} added={dry.get('added')} updated={dry.get('updated')}"
            )
        if imported:
            print(
                "  obsidian_import: "
                f"added={imported.get('added')} updated={imported.get('updated')} skipped={imported.get('skipped')}"
            )
        if obsidian.get("folder_rules"):
            print(f"  obsidian_folder_rules: {obsidian['folder_rules'].get('path')}")
        if obsidian.get("review_inbox"):
            print(f"  obsidian_review_inbox: {obsidian['review_inbox'].get('target_dir')}")
    if payload.get("sync_templates"):
        print("  sync_templates:")
        for name, path in payload["sync_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("supabase_setup"):
        print("  supabase_setup:")
        for name, path in payload["supabase_setup"].items():
            print(f"    {name}: {path}")
    if payload.get("supabase_sync_templates"):
        print("  supabase_sync_templates:")
        for name, path in payload["supabase_sync_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("remote_reader_templates"):
        print("  remote_reader_templates:")
        for name, path in payload["remote_reader_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("agent_roster"):
        print("  agent_roster:")
        for name, path in payload["agent_roster"].items():
            if name == "env":
                continue
            print(f"    {name}: {path}")
    if payload.get("live_validation_pack"):
        print("  live_validation_pack:")
        for name, path in payload["live_validation_pack"].items():
            print(f"    {name}: {path}")
    if payload.get("automation_schedule_templates"):
        print("  automation_schedule_templates:")
        for name, path in payload["automation_schedule_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("automation_policy"):
        print(f"  automation_policy: {payload['automation_policy'].get('path')}")
    if payload.get("memory_agents"):
        print("  memory_agents:")
        for name, path in payload["memory_agents"].items():
            print(f"    {name}: {path}")
    if payload.get("stable_venv"):
        print("  stable_venv:")
        for name, path in payload["stable_venv"].items():
            print(f"    {name}: {path}")
    if payload.get("memory_layout_files"):
        print("  memory_layout_files:")
        for name, path in payload["memory_layout_files"].items():
            print(f"    {name}: {path}")
    if payload.get("agent_access"):
        print("  agent_access:")
        for name, path in payload["agent_access"].items():
            print(f"    {name}: {path}")
    if payload.get("update_status_templates"):
        print("  update_status_templates:")
        for name, path in payload["update_status_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("agent_adapter_startup"):
        print("  agent_adapter_startup:")
        for name, path in payload["agent_adapter_startup"].items():
            print(f"    {name}: {path}")
    if payload.get("security_hardening"):
        print("  security_hardening:")
        for name, path in payload["security_hardening"].items():
            print(f"    {name}: {path}")
    if payload.get("human_next_steps"):
        print("For the user:")
        for step in payload["human_next_steps"]:
            print(f"  {step}")
    print("Next steps:")
    for step in payload["next_steps"]:
        print(f"  {step}")


def _print_consumer_setup_summary(payload: dict) -> None:
    print("Vault consumer setup complete")
    print(f"  project_dir: {payload['project_dir']}")
    print(f"  db_path: {payload['db_path']}")
    print(f"  language: {payload.get('language', 'en')}")
    if payload.get("consumer_daily_report"):
        print(f"  daily_report_guide: {payload['consumer_daily_report'].get('guide')}")
    if payload.get("automation_schedule_templates"):
        templates = payload["automation_schedule_templates"]
        if templates.get("cron"):
            print(f"  daily_schedule: {templates['cron']}")
        elif templates.get("launchagent"):
            print(f"  daily_schedule: {templates['launchagent']}")
        elif templates.get("n8n"):
            print(f"  daily_schedule: {templates['n8n']}")
    if payload.get("security_hardening"):
        print(f"  safety_guide: {payload['security_hardening'].get('readme')}")

    print("For you:")
    for step in payload.get("human_next_steps") or []:
        print(f"  {step}")

    agent_steps: list[str] = []
    if payload.get("local_smoke", {}).get("script"):
        agent_steps.append(f"Run the smoke check: {payload['local_smoke']['script']}")
    if payload.get("automation_schedule_templates", {}).get("readme"):
        agent_steps.append(f"Review and enable the daily schedule: {payload['automation_schedule_templates']['readme']}")
    if payload.get("security_hardening", {}).get("readme"):
        agent_steps.append(f"Apply local safety defaults: {payload['security_hardening']['readme']}")
    if payload.get("consumer_daily_report", {}).get("guide"):
        agent_steps.append(f"Use the consumer guide when explaining Vault to the user: {payload['consumer_daily_report']['guide']}")

    print("For your agent:")
    for step in agent_steps[:5]:
        print(f"  {step}")
    print("  Full maintenance details are available with --json.")


def cmd_agent(args):
    """Local agent registry commands."""
    from vault.agent_registry import (
        build_update_distribution_health,
        build_update_status,
        focus_update_status_for_agent,
        list_agents,
        read_update_status,
        register_agent,
    )

    action = getattr(args, "agent_action", None)
    if action == "register":
        project_dir = Path(args.agent_project_dir or find_project_dir()).expanduser()
        features = [item.strip() for item in str(args.features or "").split(",") if item.strip()]
        skills = [item.strip() for item in str(getattr(args, "skills", "") or "").split(",") if item.strip()]
        payload = register_agent(
            agent=args.agent,
            project_dir=project_dir,
            scope=args.scope,
            features=features,
            tool_profile=args.tool_profile,
            source=args.source,
            memory_layout=args.memory_layout,
            private_project_dir=Path(args.agent_private_dir).expanduser() if args.agent_private_dir else None,
            skills=skills,
        )
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        agent = payload["agent"]
        print("Agent registered")
        print(f"  agent: {agent['agent_id']}")
        print(f"  project_dir: {agent['project_dir']}")
        if agent.get("private_project_dir"):
            print(f"  private_project_dir: {agent['private_project_dir']}")
        print(f"  memory_layout: {agent['memory_layout']}")
        print(f"  scope: {agent['scope']}")
        if agent.get("skills"):
            print(f"  skills: {', '.join(agent['skills'])}")
        print(f"  registry: {payload['registry_path']}")
        return

    if action == "list":
        payload = list_agents()
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        print(f"Registered agents: {payload['agent_count']}")
        print(f"Registry: {payload['registry_path']}")
        for item in payload["agents"]:
            print(
                "  {agent_id} [{scope}] project={project_dir} version={vault_version}".format(
                    **item
                )
            )
        return

    if action == "status":
        if args.read_status and args.write_status:
            raise SystemExit("--read-status cannot be combined with --write-status")
        if getattr(args, "doctor", False):
            payload = build_update_distribution_health(max_age_minutes=args.max_status_age_minutes)
            if args.json or args.pretty:
                _json_print(payload, pretty=args.pretty)
                return
            _print_update_distribution_health(payload)
            return
        if args.read_status:
            payload = read_update_status(agent_id=args.agent or "")
        else:
            payload = build_update_status(
                latest_version=args.latest_version,
                check_pypi=bool(args.check_pypi),
            )
        if args.write_status and not args.read_status:
            from vault.agent_registry import write_update_status

            payload["status_path"] = str(write_update_status(payload))
        if args.agent and not args.read_status:
            payload = focus_update_status_for_agent(payload, args.agent)
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        _print_update_status(payload)
        return

    if action == "doctor":
        payload = build_update_distribution_health(max_age_minutes=args.max_status_age_minutes)
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        _print_update_distribution_health(payload)
        return

    if action == "install-runtime-template":
        from vault.agent_setup import install_runtime_template

        template_dir = Path(args.template_dir).expanduser() if args.template_dir else (find_project_dir() / "agent-install")
        try:
            payload = install_runtime_template(
                runtime=args.runtime,
                template_dir=template_dir,
                target_path=Path(args.target).expanduser(),
                apply=bool(args.apply),
                backup=not bool(args.no_backup),
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        print("Runtime template apply preview" if not payload["apply"] else "Runtime template applied")
        print(f"  runtime: {payload['runtime']}")
        print(f"  source: {payload['source']}")
        print(f"  target: {payload['target']}")
        print(f"  action: {payload['action']}")
        print(f"  changed: {payload['changed']}")
        if payload.get("backup"):
            print(f"  backup: {payload['backup']}")
        print(f"  next: {payload['next_step']}")
        return

    if action == "startup-doctor":
        from vault.agent_setup import startup_contract_doctor

        template_dir = Path(args.template_dir).expanduser() if args.template_dir else (find_project_dir() / "agent-install")
        payload = startup_contract_doctor(template_dir)
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        print("Agent startup contract doctor")
        print(f"  status: {payload['status']}")
        print(f"  template_dir: {payload['template_dir']}")
        summary = payload.get("summary", {})
        print(
            "  checks: pass={pass_count} warn={warn_count} fail={fail_count}".format(
                pass_count=summary.get("pass", 0),
                warn_count=summary.get("warn", 0),
                fail_count=summary.get("fail", 0),
            )
        )
        for check in payload.get("checks", []):
            if check.get("status") != "pass":
                print(f"  - {check.get('status')}: {check.get('name')} ({check.get('detail')})")
        print(f"  next: {payload.get('next_action')}")
        return

    raise SystemExit("agent subcommand required: register, list, status, doctor, startup-doctor, or install-runtime-template")


def cmd_update_status(args):
    """Show local Vault runtime update and agent registry status."""
    from vault.agent_registry import (
        build_update_distribution_health,
        build_update_status,
        focus_update_status_for_agent,
        read_update_status,
        write_update_status,
    )

    if args.read_status and args.write_status:
        raise SystemExit("--read-status cannot be combined with --write-status")
    if getattr(args, "doctor", False):
        payload = build_update_distribution_health(max_age_minutes=args.max_status_age_minutes)
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
            return
        _print_update_distribution_health(payload)
        return
    if args.read_status:
        payload = read_update_status(agent_id=args.agent or "")
    else:
        payload = build_update_status(
            latest_version=args.latest_version,
            check_pypi=bool(args.check_pypi),
        )
    if args.write_status and not args.read_status:
        payload["status_path"] = str(write_update_status(payload))
    if args.agent and not args.read_status:
        payload = focus_update_status_for_agent(payload, args.agent)
    if args.json or args.pretty:
        _json_print(payload, pretty=args.pretty)
        return
    _print_update_status(payload)


def _print_update_distribution_health(payload: dict) -> None:
    print("Vault Agent update distribution")
    print(f"  ok: {payload.get('ok', False)}")
    print(f"  registry: {payload.get('registry_path', '')}")
    print(f"  status_path: {payload.get('status_path', '')}")
    print(f"  status_exists: {payload.get('status_exists', False)}")
    print(f"  status_installed_version: {payload.get('status_installed_version', '')}")
    print(f"  status_current_runtime_mismatch: {payload.get('status_current_runtime_mismatch', False)}")
    print(f"  status_stale: {payload.get('status_stale', True)}")
    print(f"  status_age_seconds: {payload.get('status_age_seconds')}")
    print(f"  agents: {payload.get('agent_count', 0)}")
    attention = payload.get("agents_needing_attention") or []
    if attention:
        print("Agents needing attention:")
        for agent in attention:
            print(f"  {agent}")
    missing = payload.get("agents_missing_from_status") or []
    if missing:
        print("Agents missing from status:")
        for agent in missing:
            print(f"  {agent}")
    print("Recommended actions:")
    for action in payload.get("recommended_actions", []):
        print(f"  {action}")


def _print_update_status(payload: dict) -> None:
    if payload.get("missing"):
        print("Vault update status")
        print(f"  status_path: {payload.get('status_path', '')}")
        print(f"  missing: {payload.get('missing')}")
        if payload.get("startup_agent_id"):
            print(f"  startup_agent: {payload['startup_agent_id']}")
        if payload.get("message"):
            print(f"  message: {payload['message']}")
        if payload.get("startup_checklist"):
            print("Startup checklist:")
            for step in payload["startup_checklist"]:
                print(f"  {step}")
        return
    print("Vault update status")
    print(f"  installed_version: {payload['installed_version']}")
    print(f"  latest_version: {payload['latest_version']}")
    print(f"  update_available: {payload['update_available']}")
    if payload.get("latest_version_error"):
        print(f"  latest_version_error: {payload['latest_version_error']}")
    if payload.get("startup_agent_id"):
        print(f"  startup_agent: {payload['startup_agent_id']}")
        print(f"  startup_agent_registered: {payload.get('startup_agent_registered', False)}")
        print(f"  current_agent_needs_attention: {payload.get('current_agent_needs_attention', False)}")
        action = payload.get("current_agent_recommended_action")
        if action:
            print(f"  current_agent_recommended_action: {action}")
    print(f"  registry: {payload['registry_path']}")
    print(f"  agents: {payload['agent_count']}")
    for agent in payload.get("agents", []):
        print(
            "    {agent_id}: layout={memory_layout} scope={scope} project={project_dir}".format(
                **agent
            )
        )
        if agent.get("private_project_dir"):
            print(f"      private: {agent['private_project_dir']}")
    notices = payload.get("agent_update_notices", [])
    if notices:
        print("Agent update notices:")
        for notice in notices:
            marker = "!" if notice.get("needs_attention") else "-"
            print(
                "  {marker} {agent_id}: {status} "
                "(registered={registered_version}, latest={latest_known_version})".format(
                    marker=marker,
                    **notice,
                )
            )
            if notice.get("needs_attention"):
                print(f"      {notice['recommended_action']}")
    print("Startup commands:")
    for command in payload.get("startup_commands", []):
        print(f"  {command}")
    print("Next steps:")
    for step in payload.get("next_steps", []):
        print(f"  {step}")
    if payload.get("startup_checklist"):
        print("Startup checklist:")
        for step in payload["startup_checklist"]:
            print(f"  {step}")
