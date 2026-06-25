"""CLI handlers for semantic index workflows."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _find_project_dir() -> Path:
    from vault import cli as cli_module

    return cli_module.find_project_dir()


def _json_print(payload: dict, *, pretty: bool = False) -> None:
    from vault import cli as cli_module

    cli_module._json_print(payload, pretty=pretty)


def _semantic_vectors_exist(db_path: Path) -> bool:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT 1 FROM semantic_vectors LIMIT 1").fetchone()
            return row is not None
    except sqlite3.Error:
        return False


def _semantic_stats_payload(stats, provider) -> dict:
    return {
        "provider_id": provider.provider_id,
        "is_semantic": bool(provider.is_semantic),
        "dimension": int(provider.dim),
        "knowledge_rows": int(stats.knowledge_rows),
        "node_vectors": int(stats.node_vectors),
        "claim_vectors": int(stats.claim_vectors),
        "changed_only": bool(getattr(stats, "changed_only", False)),
        "candidate_rows": int(getattr(stats, "candidate_rows", stats.knowledge_rows)),
        "skipped_rows": int(getattr(stats, "skipped_rows", 0)),
    }


def _persistent_cache_payload(provider) -> dict:
    return {
        "memory_rows": int(getattr(provider, "cache_size", 0)),
        "persistent_hits": int(getattr(provider, "persistent_hits", 0)),
        "persistent_misses": int(getattr(provider, "persistent_misses", 0)),
        "writes": int(getattr(provider, "writes", 0)),
    }


def _close_provider(provider) -> None:
    close = getattr(provider, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _load_unique_qa_queries(qa_file: str | Path) -> list[str]:
    from vault.search_qa import load_search_qa_set

    qa = load_search_qa_set(qa_file)
    seen: set[str] = set()
    queries: list[str] = []
    for case in qa["cases"]:
        query = str(case["query"])
        if query not in seen:
            seen.add(query)
            queries.append(query)
    return queries


def _create_semantic_provider(args, *, cached: bool = False):
    from vault.db import VaultDB
    from vault.embed import create_embedding_provider
    from vault.semantic import (
        CachedEmbeddingProvider,
        DeterministicHashEmbeddingProvider,
        validate_embedding_provider,
    )

    if args.allow_hash:
        provider = DeterministicHashEmbeddingProvider(dim=args.hash_dim)
        return CachedEmbeddingProvider(provider) if cached else provider

    db_path = Path(args.db_path) if args.db_path else _find_project_dir() / "vault.db"
    with VaultDB(db_path) as db:
        provider_name = db.get_config("embedding_provider", "auto")
        model_key = db.get_config("embedding_model", "mix")
    provider = create_embedding_provider(provider=provider_name, model_key=model_key)
    validate_embedding_provider(provider, require_semantic=True, allow_hash=False)
    return CachedEmbeddingProvider(provider) if cached else provider


def _create_persistent_semantic_provider(args, db):
    from vault.semantic import PersistentCachedEmbeddingProvider

    provider = _create_semantic_provider(args, cached=False)
    return PersistentCachedEmbeddingProvider(provider, db)


def cmd_semantic(args):
    """Operator-facing semantic index workflows."""
    from vault.db import VaultDB
    from vault.search_qa import evaluate_search_qa, write_json
    from vault.semantic import embedding_cache_stats, prune_embedding_cache, rebuild_semantic_index
    from vault.semantic_lifecycle import run_semantic_daemon, run_semantic_startup

    action = args.semantic_action
    if action not in {"rebuild", "warm", "smoke", "cache-stats", "cache-prune", "startup", "daemon"}:
        print(
            "error: semantic requires action: rebuild, warm, smoke, cache-stats, cache-prune, startup, or daemon",
            file=sys.stderr,
        )
        raise SystemExit(2)

    db_path = Path(args.db_path) if args.db_path else _find_project_dir() / "vault.db"

    try:
        if action in {"startup", "daemon"}:
            lifecycle_kwargs = {
                "db_path": db_path,
                "qa_file": args.qa_file,
                "allow_hash": args.allow_hash,
                "hash_dim": args.hash_dim,
                "persist_cache": not args.no_persist_cache,
                "rebuild": args.rebuild,
                "smoke": args.smoke,
                "mode": args.mode,
                "limit": args.limit,
                "semantic_vector_kind": args.semantic_vector_kind,
                "older_than_days": args.older_than_days,
                "max_rows": args.max_rows,
                "changed_only": getattr(args, "changed_only", False),
                "semantic_limit": getattr(args, "semantic_limit", None),
            }
            if action == "startup":
                payload = run_semantic_startup(**lifecycle_kwargs)
            else:
                payload = run_semantic_daemon(
                    repeat=args.repeat,
                    interval=args.interval,
                    **lifecycle_kwargs,
                )
            if args.output:
                write_json(args.output, payload)
            _json_print(payload, pretty=args.pretty)
            return

        if action == "cache-stats":
            with VaultDB(db_path) as db:
                stats = embedding_cache_stats(
                    db,
                    provider_id=args.provider_id,
                    dimension=args.dimension,
                )
            _json_print({"action": "cache-stats", **stats}, pretty=args.pretty)
            return

        if action == "cache-prune":
            with VaultDB(db_path) as db:
                deleted = prune_embedding_cache(
                    db,
                    provider_id=args.provider_id,
                    dimension=args.dimension,
                    older_than_days=args.older_than_days,
                    max_rows=args.max_rows,
                )
            _json_print({"action": "cache-prune", "deleted_rows": deleted}, pretty=args.pretty)
            return

        if action == "rebuild":
            if args.persist_cache:
                with VaultDB(db_path) as db:
                    provider = _create_persistent_semantic_provider(args, db)
                    try:
                        stats = rebuild_semantic_index(
                            db,
                            provider,
                            knowledge_id=args.knowledge_id,
                            require_semantic=not args.allow_hash,
                            allow_hash=args.allow_hash,
                            changed_only=getattr(args, "changed_only", False),
                            limit=getattr(args, "limit", None),
                        )
                        payload = {"action": "rebuild", **_semantic_stats_payload(stats, provider)}
                        payload["persistent_cache"] = _persistent_cache_payload(provider)
                    finally:
                        _close_provider(provider)
            else:
                provider = _create_semantic_provider(args, cached=False)
                try:
                    with VaultDB(db_path) as db:
                        stats = rebuild_semantic_index(
                            db,
                            provider,
                            knowledge_id=args.knowledge_id,
                            require_semantic=not args.allow_hash,
                            allow_hash=args.allow_hash,
                            changed_only=getattr(args, "changed_only", False),
                            limit=getattr(args, "limit", None),
                        )
                    payload = {"action": "rebuild", **_semantic_stats_payload(stats, provider)}
                finally:
                    _close_provider(provider)
            _json_print(payload, pretty=args.pretty)
            return

        if action == "warm":
            queries = _load_unique_qa_queries(args.qa_file)
            if args.persist_cache:
                with VaultDB(db_path) as db:
                    provider = _create_persistent_semantic_provider(args, db)
                    try:
                        if queries:
                            provider.encode(queries)
                        payload = {
                            "action": "warm",
                            "provider_id": provider.provider_id,
                            "is_semantic": bool(provider.is_semantic),
                            "dimension": int(provider.dim),
                            "warmed_queries": len(queries),
                            "cache_size": provider.cache_size,
                            "persistent_cache": _persistent_cache_payload(provider),
                        }
                    finally:
                        _close_provider(provider)
            else:
                provider = _create_semantic_provider(args, cached=True)
                try:
                    if queries:
                        provider.encode(queries)
                    payload = {
                        "action": "warm",
                        "provider_id": provider.provider_id,
                        "is_semantic": bool(provider.is_semantic),
                        "dimension": int(provider.dim),
                        "warmed_queries": len(queries),
                        "cache_size": provider.cache_size,
                    }
                finally:
                    _close_provider(provider)
            _json_print(payload, pretty=args.pretty)
            return

        queries = _load_unique_qa_queries(args.qa_file)
        if args.persist_cache:
            with VaultDB(db_path) as db:
                provider = _create_persistent_semantic_provider(args, db)
                try:
                    stats = rebuild_semantic_index(
                        db,
                        provider,
                        knowledge_id=args.knowledge_id,
                        require_semantic=not args.allow_hash,
                        allow_hash=args.allow_hash,
                        changed_only=getattr(args, "changed_only", False),
                        limit=getattr(args, "semantic_limit", None),
                    )
                    if queries:
                        provider.encode(queries)
                    cache_payload = _persistent_cache_payload(provider)
                finally:
                    _close_provider(provider)
        else:
            provider = _create_semantic_provider(args, cached=True)
            try:
                with VaultDB(db_path) as db:
                    stats = rebuild_semantic_index(
                        db,
                        provider,
                        knowledge_id=args.knowledge_id,
                        require_semantic=not args.allow_hash,
                        allow_hash=args.allow_hash,
                        changed_only=getattr(args, "changed_only", False),
                        limit=getattr(args, "semantic_limit", None),
                    )
                if queries:
                    provider.encode(queries)
                cache_payload = None
            finally:
                _close_provider(provider)
        qa_snapshot = evaluate_search_qa(
            db_path=db_path,
            qa_file=args.qa_file,
            mode=args.mode,
            limit=args.limit,
            embed_provider=provider,
            semantic_vector_kind=args.semantic_vector_kind,
            allow_hash=args.allow_hash,
        )
        payload = {
            "action": "smoke",
            "provider_id": provider.provider_id,
            "is_semantic": bool(provider.is_semantic),
            "dimension": int(provider.dim),
            "rebuild": {
                "knowledge_rows": int(stats.knowledge_rows),
                "node_vectors": int(stats.node_vectors),
                "claim_vectors": int(stats.claim_vectors),
            },
            "warmed_queries": len(queries),
            "cache_size": provider.cache_size,
            "qa": {"aggregate": qa_snapshot["aggregate"]},
            "output_written": bool(args.output),
        }
        if getattr(stats, "changed_only", False):
            payload["rebuild"].update(
                {
                    "changed_only": True,
                    "candidate_rows": int(getattr(stats, "candidate_rows", stats.knowledge_rows)),
                    "skipped_rows": int(getattr(stats, "skipped_rows", 0)),
                }
            )
        if cache_payload is not None:
            payload["persistent_cache"] = cache_payload
        if args.output:
            write_json(args.output, payload)
        _json_print(payload, pretty=args.pretty)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

