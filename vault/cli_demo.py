"""CLI helpers for runnable Vault demos."""

from __future__ import annotations

import argparse
from typing import Any, Callable

from .demo_agent_governance import run_agent_governance_demo


def add_demo_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("demo", help="可重跑的產品定位與整合示範")
    demo_sub = parser.add_subparsers(dest="demo_action")

    p = demo_sub.add_parser(
        "agent-governance",
        help="展示 Codex + Claude Code + Hermes 共用 Vault 的記憶治理生命週期",
    )
    p.add_argument("--agent-set", default="codex,claude-code,hermes", help="三個 agent_id，CSV")
    p.add_argument("--keep-project", action="store_true", help="標記保留臨時 demo 專案，方便後續檢查")
    p.add_argument("--json", action="store_true", help="輸出 JSON")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")


def cmd_demo(
    args: Any,
    *,
    project_dir_override: Any = None,
    json_print: Callable[[dict, bool], None],
) -> None:
    action = getattr(args, "demo_action", "")
    if action != "agent-governance":
        print("用法: vault demo agent-governance [--project-dir DIR] [--json|--pretty]")
        return

    payload = run_agent_governance_demo(
        project_dir=project_dir_override,
        agent_set=getattr(args, "agent_set", "codex,claude-code,hermes"),
        keep_project=bool(getattr(args, "keep_project", False)),
    )
    if getattr(args, "json", False) or getattr(args, "pretty", False):
        json_print(payload, getattr(args, "pretty", False))
        return

    print("Vault agent-governance demo")
    print(f"  project: {payload['project_dir']}")
    print(f"  candidate: {payload['candidate_id']}")
    print(f"  promoted knowledge: {payload['promoted_knowledge_id']}")
    print(f"  citation: {payload['read_range_citation']}")
    print(f"  rollback backup: {payload['rollback']['backup_path']}")
    print(f"  report: {payload['artifacts']['report_md']}")
    print("  lifecycle: " + " -> ".join(payload["lifecycle"]))
