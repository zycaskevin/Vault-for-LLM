"""CLI group for automatic memory pipeline, temporal facts, and reflection."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable


def cmd_memory(
    args: argparse.Namespace,
    *,
    find_project_dir: Callable[[], Any],
    json_print: Callable[..., None],
) -> None:
    action = getattr(args, "memory_action", "")
    project_dir = find_project_dir()
    try:
        if action == "pipeline":
            from .memory_pipeline import run_memory_pipeline

            payload = run_memory_pipeline(
                project_dir,
                search_dirs=args.search_dir or None,
                source_system=args.source_system,
                agent_id=args.agent_id,
                write_candidates=args.write_candidates,
                run_cycle=args.cycle,
                apply=args.apply,
                transcript_limit=args.transcript_limit,
                max_candidates_per_transcript=args.max_candidates_per_transcript,
                min_score=args.min_score,
                scope=args.scope,
                sensitivity=args.sensitivity,
                include_content=args.include_content,
            )
        elif action == "temporal":
            from .db import VaultDB
            from .temporal import list_temporal_memories, temporal_summary

            with VaultDB(project_dir / "vault.db") as db:
                payload = (
                    temporal_summary(db, as_of=args.as_of)
                    if args.temporal_action == "status"
                    else list_temporal_memories(db, state=args.state, as_of=args.as_of, limit=args.limit)
                )
        elif action == "reflection":
            from .reflection import run_reflection

            payload = run_reflection(
                project_dir,
                checks=args.checks,
                limit=args.limit,
                write_candidates=args.write_candidates,
                apply=args.apply,
                write_report=not args.no_report,
            )
        else:
            print("error: memory requires action: pipeline, temporal, or reflection", file=sys.stderr)
            raise SystemExit(2)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    json_print(payload, pretty=args.pretty)


def add_memory_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("memory", help="自動記憶流水線、時序事實與反思整理")
    memory_sub = parser.add_subparsers(dest="memory_action")

    p = memory_sub.add_parser("pipeline", help="自動 discover/capture 對話記憶候選")
    p.add_argument("--search-dir", action="append", default=[], help="搜尋 transcript 的目錄，可重複")
    p.add_argument("--source-system", default="auto", help="來源系統，例如 codex/hermes/openclaw")
    p.add_argument("--agent-id", default="", help="產生候選的 agent id")
    p.add_argument("--write-candidates", action="store_true", help="寫入候選記憶；預設只 preview")
    p.add_argument("--cycle", action="store_true", help="capture 後接 automation cycle")
    p.add_argument("--apply", action="store_true", help="允許 cycle 套用 policy 允許的可逆操作")
    p.add_argument("--transcript-limit", type=int, default=3)
    p.add_argument("--max-candidates-per-transcript", type=int, default=8)
    p.add_argument("--min-score", type=float, default=0.55)
    p.add_argument("--scope", choices=["private", "project", "shared", "public"], default="project")
    p.add_argument("--sensitivity", choices=["low", "medium", "high", "restricted"], default="low")
    p.add_argument("--include-content", action="store_true", help="輸出候選完整內容；預設只 preview")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = memory_sub.add_parser("temporal", help="檢視事實有效性窗口")
    temporal_sub = p.add_subparsers(dest="temporal_action")
    sp = temporal_sub.add_parser("status", help="統計 current/past/future/timeless 記憶")
    sp.add_argument("--as-of", default="", help="以指定 ISO-8601 時間判斷")
    sp.add_argument("--pretty", action="store_true")
    sp = temporal_sub.add_parser("list", help="列出特定 temporal state 的記憶")
    sp.add_argument("--state", choices=["current", "past", "future", "timeless", "all"], default="current")
    sp.add_argument("--as-of", default="", help="以指定 ISO-8601 時間判斷")
    sp.add_argument("--limit", "-n", type=int, default=50)
    sp.add_argument("--pretty", action="store_true")

    p = memory_sub.add_parser("reflection", help="跑 Dream + lifecycle 的記憶反思")
    p.add_argument("--checks", default="freshness,dedup,convergence,metadata,orphans")
    p.add_argument("--limit", "-n", type=int, default=50)
    p.add_argument("--write-candidates", action="store_true", help="把反思建議寫入候選佇列")
    p.add_argument("--apply", action="store_true", help="允許 lifecycle 套用 policy 允許的可逆操作")
    p.add_argument("--no-report", action="store_true", help="不寫 reports/")
    p.add_argument("--pretty", action="store_true")
