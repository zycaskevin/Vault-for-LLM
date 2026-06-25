"""Small shared CLI parser helpers."""

from __future__ import annotations

import argparse


def add_governance_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", choices=["private", "project", "shared", "public"], default="project", help="記憶範圍：private/project/shared/public")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high", "restricted"], default="low", help="敏感度：low/medium/high/restricted")
    parser.add_argument("--owner-agent", default="", help="擁有者 Agent，例如 profile-agent、work-agent、codex")
    parser.add_argument("--allowed-agents", default="", help="可讀 Agent 清單；可用 JSON array 或逗號分隔")
    parser.add_argument("--memory-type", default="knowledge", help="記憶類型，例如 knowledge/profile/dream/care_summary/decision")
    parser.add_argument("--expires-at", default="", help="可選過期時間，ISO-8601 字串")
    parser.add_argument("--valid-from", default="", help="事實有效開始時間，ISO-8601；不同於 expires-at")
    parser.add_argument("--valid-until", default="", help="事實有效結束時間，ISO-8601；用於保留過去事實")
    parser.add_argument("--supersedes-id", type=int, default=None, help="此記憶取代的舊 knowledge id")
