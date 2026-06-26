"""Quality, freshness, deduplication, and Search QA CLI handlers."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

from .cli_semantic import _create_semantic_provider, _semantic_vectors_exist
from .cli_context import _arg_value, _enforce_cli_privacy, _json_print, find_project_dir
from .cli_search import temporal_search_kwargs


def cmd_config(args):
    """配置管理。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()

    if args.config_action == "set" and len(args.config_args) >= 2:
        key, value = args.config_args[0], args.config_args[1]
        db.set_config(key, value)
        print(f"✅ {key} = {value}")
    elif args.config_action == "get" and len(args.config_args) >= 1:
        key = args.config_args[0]
        value = db.get_config(key)
        print(f"{key} = {value}")
    elif args.config_action == "list":
        rows = db.conn.execute("SELECT key, value FROM config").fetchall()
        for row in rows:
            print(f"  {row['key']} = {row['value']}")
    else:
        print("用法: vault config set <key> <value>")
        print("      vault config get <key>")
        print("      vault config list")

    db.close()


def cmd_converge(args):
    """收斂檢查 — 自問知識是否充足。"""
    from scripts.convergence_check import check_convergence

    db_path = str(find_project_dir() / "vault.db")
    check_convergence(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        min_trust=args.min_trust,
        ollama_model=args.ollama,
        api_url=args.api,
        api_key=args.api_key,
    )


def cmd_cross_validate(args):
    """跨模型不對稱驗證。"""
    from scripts.cross_validate import cross_validate

    db_path = str(find_project_dir() / "vault.db")
    cross_validate(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        min_trust=args.min_trust,
        local_only=args.local_only,
        local_model=args.local_model,
        cloud_model=args.cloud_model,
    )


def cmd_freshness(args):
    """知識新鮮度追蹤與審查排程。"""
    from scripts.freshness_check import check_freshness

    db_path = str(find_project_dir() / "vault.db")
    check_freshness(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        stale_only=args.stale_only,
    )


def cmd_dedup(args):
    """語意去重 — 檢測與合併重複知識。"""
    from scripts.deduplicate_semantic import find_duplicates, merge_duplicates

    db_path = str(find_project_dir() / "vault.db")
    duplicates = find_duplicates(db_path=db_path, threshold=args.threshold)
    if duplicates:
        if args.merge:
            print("\n" + "=" * 50)
            merge_duplicates(db_path=db_path, dry_run=False)
        elif args.dry_run:
            print("\n💡 加 --merge 實際合併")
        else:
            print("\n💡 加 --merge 實際合併，加 --dry-run 預覽計劃")
    else:
        print("✅ 沒有發現重複條目")


def cmd_search_qa(args):
    """Search QA snapshot run / before-after compare."""
    from vault.search_qa import (
        compare_search_qa_snapshots,
        evaluate_search_qa,
        format_search_qa_comparison,
        format_search_qa_snapshot,
        write_json,
    )

    action = args.search_qa_action
    if action == "run":
        db_path = Path(args.db_path) if args.db_path else find_project_dir() / "vault.db"
        embed_provider = None
        needs_provider = args.mode in {"semantic", "hybrid", "vector"} or (
            args.mode == "auto" and (
                getattr(args, "allow_hash", False) or _semantic_vectors_exist(db_path)
            )
        )
        if needs_provider:
            semantic_args = argparse.Namespace(
                db_path=str(db_path),
                allow_hash=getattr(args, "allow_hash", False),
                hash_dim=getattr(args, "hash_dim", 32),
            )
            embed_provider = _create_semantic_provider(
                semantic_args,
                cached=args.mode in {"auto", "semantic", "hybrid"},
            )
        snapshot = evaluate_search_qa(
            db_path=db_path,
            qa_file=args.qa_file,
            mode=args.mode,
            limit=args.limit,
            embed_provider=embed_provider,
            semantic_vector_kind=args.semantic_vector_kind,
            allow_hash=args.allow_hash,
            min_score=args.min_score,
        )
        if args.output:
            write_json(args.output, snapshot)
        print(format_search_qa_snapshot(snapshot))
        return

    if action == "compare":
        comparison = compare_search_qa_snapshots(args.before, args.after)
        if args.output:
            write_json(args.output, comparison)
        print(format_search_qa_comparison(comparison))
        return

    print("error: search-qa requires action: run or compare", file=sys.stderr)
    raise SystemExit(2)
