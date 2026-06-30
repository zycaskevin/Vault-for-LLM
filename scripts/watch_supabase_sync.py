#!/usr/bin/env python3
"""Near-realtime local-to-Supabase sync watcher.

This is intentionally one-way: local SQLite remains the source of truth and
Supabase remains a shared read copy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts._utils import find_db_path, load_dotenv_cascade


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_report_path(db_path: Path) -> Path:
    return db_path.parent / "reports" / "supabase-sync-latest.json"


def _build_sync_command(args: argparse.Namespace, db_path: Path) -> list[str]:
    command = [
        str(args.python_executable or sys.executable),
        "-m",
        "scripts.sync_to_supabase",
        "--db",
        str(db_path),
    ]
    if args.include_content:
        command.append("--include-content")
    if args.document_map:
        command.append("--document-map")
    if args.health:
        command.append("--health")
    return command


def _path_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def _db_signature(db_path: Path) -> dict[str, int]:
    paths = [db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")]
    return {str(path): _path_mtime_ns(path) for path in paths}


def _write_report(
    path: Path,
    *,
    status: str,
    command: list[str],
    returncode: int | None = None,
    error: str = "",
    dry_run: bool = False,
    trigger: str = "watch",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "mode": "near_realtime_push",
        "direction": "local_to_supabase",
        "bidirectional": False,
        "realtime": True,
        "last_synced_at": _utc_now() if status in {"ok", "dry_run"} else "",
        "completed_at": _utc_now(),
        "trigger": trigger,
        "dry_run": dry_run,
        "command": command,
        "returncode": returncode,
        "error": error,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_sync(args: argparse.Namespace, db_path: Path, *, trigger: str) -> int:
    command = _build_sync_command(args, db_path)
    report_path = Path(args.report).expanduser() if args.report else _default_report_path(db_path)
    if args.dry_run:
        print("Dry run: would run", " ".join(command))
        _write_report(report_path, status="dry_run", command=command, dry_run=True, trigger=trigger)
        return 0

    load_dotenv_cascade(str(db_path.parent / ".env"))
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    status = "ok" if completed.returncode == 0 else "failed"
    _write_report(
        report_path,
        status=status,
        command=command,
        returncode=completed.returncode,
        error=completed.stderr[-2000:] if completed.returncode else "",
        trigger=trigger,
    )
    return int(completed.returncode)


def watch(args: argparse.Namespace) -> int:
    db_path = Path(args.db or find_db_path()).expanduser().resolve()
    if not db_path.exists():
        print(f"vault.db not found: {db_path}", file=sys.stderr)
        return 2

    if args.once:
        return _run_sync(args, db_path, trigger="once")

    interval = max(1.0, float(args.interval_seconds))
    debounce = max(0.0, float(args.debounce_seconds))
    max_runs = max(0, int(args.max_runs or 0))
    run_count = 0
    last_signature = _db_signature(db_path)
    pending_since: float | None = time.monotonic() if args.sync_on_start else None
    trigger = "startup" if args.sync_on_start else "watch"

    print(f"Watching {db_path} for local-to-Supabase sync changes.")
    while True:
        now = time.monotonic()
        signature = _db_signature(db_path)
        if signature != last_signature:
            last_signature = signature
            pending_since = now
            trigger = "db_changed"

        if pending_since is not None and now - pending_since >= debounce:
            rc = _run_sync(args, db_path, trigger=trigger)
            run_count += 1
            pending_since = None
            trigger = "watch"
            if rc != 0 and args.stop_on_error:
                return rc
            if max_runs and run_count >= max_runs:
                return 0

        time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch local vault.db and push near-realtime Supabase sync.")
    parser.add_argument("--db", default="", help="vault.db path; defaults to Vault discovery")
    parser.add_argument("--interval-seconds", type=float, default=5.0, help="poll interval seconds")
    parser.add_argument("--debounce-seconds", type=float, default=10.0, help="wait for quiet period before sync")
    parser.add_argument("--sync-on-start", action="store_true", help="run one sync shortly after startup")
    parser.add_argument("--once", action="store_true", help="run one sync and exit")
    parser.add_argument("--max-runs", type=int, default=0, help="exit after N sync runs; 0 means forever")
    parser.add_argument("--stop-on-error", action="store_true", help="exit if sync command fails")
    parser.add_argument("--dry-run", action="store_true", help="do not contact Supabase; write a dry-run report")
    parser.add_argument("--report", default="", help="sync report path; defaults to reports/supabase-sync-latest.json")
    parser.add_argument("--python-executable", default="", help="Python executable used to run scripts.sync_to_supabase")
    parser.add_argument("--include-content", action="store_true", help="sync reviewed raw content too")
    parser.add_argument("--document-map", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--health", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return watch(args)


if __name__ == "__main__":
    raise SystemExit(main())
