"""Importable semantic startup and bounded warm-daemon lifecycle hooks.

The functions in this module are safe to call from process supervisors, tests, or
other Python code without going through argparse. Production defaults use the
configured real embedding provider and reject deterministic hash providers unless
``allow_hash=True`` is passed explicitly for tests or local development.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .db import VaultDB
from .embed import create_embedding_provider
from .search_qa import evaluate_search_qa, load_search_qa_set
from .semantic import (
    CachedEmbeddingProvider,
    DeterministicHashEmbeddingProvider,
    PersistentCachedEmbeddingProvider,
    embedding_cache_stats,
    prune_embedding_cache,
    rebuild_semantic_index,
    validate_embedding_provider,
)


def close_provider(provider: Any) -> None:
    """Best-effort close helper for embedding providers.

    Provider cleanup errors are intentionally swallowed so cleanup never masks a
    successful lifecycle run or an earlier, more important exception.
    """
    close = getattr(provider, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def run_semantic_startup(
    *,
    db_path: str | Path = "vault.db",
    qa_file: str | Path | None = None,
    allow_hash: bool = False,
    hash_dim: int = 32,
    persist_cache: bool = True,
    rebuild: bool = False,
    smoke: bool = False,
    mode: str = "keyword",
    limit: int = 10,
    semantic_vector_kind: str = "claim",
    older_than_days: int | None = None,
    max_rows: int | None = None,
    knowledge_id: int | None = None,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Run one semantic startup cycle and return a JSON-serializable summary.

    The safe default does not rebuild vectors unless ``rebuild=True`` is passed.
    Persistent embedding cache is enabled by default for startup; pass
    ``persist_cache=False`` to use only an in-memory cache for this call.
    """
    resolved_db_path = Path(db_path)
    qa_path = Path(qa_file) if qa_file is not None else None
    queries = _load_unique_qa_queries(qa_path) if qa_path is not None else []
    provider_owned = provider is None
    active_provider = provider

    with VaultDB(resolved_db_path) as db:
        cache_before = embedding_cache_stats(db)
        active_provider = active_provider or _create_semantic_provider(
            db,
            allow_hash=allow_hash,
            hash_dim=hash_dim,
        )
        validate_embedding_provider(
            active_provider,
            require_semantic=not allow_hash,
            allow_hash=allow_hash,
        )
        lifecycle_provider = _cache_provider(active_provider, db, persist_cache=persist_cache)
        try:
            provider_payload = _provider_payload(lifecycle_provider)
            payload: dict[str, Any] = {
                "action": "startup",
                "success": True,
                "provider": provider_payload,
                "provider_id": provider_payload["provider_id"],
                "is_semantic": provider_payload["is_semantic"],
                "dimension": provider_payload["dimension"],
                "persist_cache": bool(persist_cache),
                "cache_before": cache_before,
                "rebuild": None,
                "warmed_queries": 0,
                "prune_deleted_rows": 0,
                "smoke": None,
            }

            if rebuild:
                stats = rebuild_semantic_index(
                    db,
                    lifecycle_provider,
                    knowledge_id=knowledge_id,
                    require_semantic=not allow_hash,
                    allow_hash=allow_hash,
                )
                payload["rebuild"] = {
                    "knowledge_rows": int(stats.knowledge_rows),
                    "node_vectors": int(stats.node_vectors),
                    "claim_vectors": int(stats.claim_vectors),
                    "provider_id": stats.provider_id,
                    "dimension": int(stats.dimension),
                }

            if queries:
                lifecycle_provider.encode(queries)
            payload["warmed_queries"] = len(queries)
            payload["provider"] = _provider_payload(lifecycle_provider)

            if older_than_days is not None or max_rows is not None:
                payload["prune_deleted_rows"] = prune_embedding_cache(
                    db,
                    provider_id=None,
                    dimension=None,
                    older_than_days=older_than_days,
                    max_rows=max_rows,
                )

            payload["cache_after"] = embedding_cache_stats(db)
            if persist_cache:
                payload["persistent_cache"] = _persistent_cache_payload(lifecycle_provider)

        finally:
            if provider_owned:
                close_provider(lifecycle_provider)

    if smoke and qa_path is not None:
        snapshot = evaluate_search_qa(
            db_path=resolved_db_path,
            qa_file=qa_path,
            mode=mode,
            limit=limit,
            embed_provider=active_provider,
            semantic_vector_kind=semantic_vector_kind,
            allow_hash=allow_hash,
        )
        payload["smoke"] = {"aggregate": snapshot["aggregate"]}

    return payload


def run_semantic_daemon(
    *,
    repeat: int = 1,
    interval: float = 60.0,
    **startup_kwargs: Any,
) -> dict[str, Any]:
    """Run bounded semantic startup iterations.

    ``repeat=1`` is the default and is CI-safe. ``repeat=0`` runs forever and is
    intended only for explicit supervisor-managed daemon use.
    """
    repeat = int(repeat)
    interval = float(interval)
    if repeat < 0:
        raise ValueError("repeat must be >= 0")
    if interval < 0:
        raise ValueError("interval must be >= 0")

    iterations: list[dict[str, Any]] = []
    index = 0
    while repeat == 0 or index < repeat:
        summary = run_semantic_startup(**startup_kwargs)
        summary["iteration"] = index + 1
        iterations.append(summary)
        index += 1
        if repeat != 0 and index >= repeat:
            break
        if interval > 0:
            time.sleep(interval)

    return {
        "action": "daemon",
        "success": all(bool(item.get("success")) for item in iterations),
        "repeat": repeat,
        "interval": interval,
        "iterations": iterations,
    }


def _create_semantic_provider(
    db: VaultDB,
    *,
    allow_hash: bool,
    hash_dim: int,
) -> Any:
    if allow_hash:
        return DeterministicHashEmbeddingProvider(dim=hash_dim)
    provider_name = db.get_config("embedding_provider", "auto")
    model_key = db.get_config("embedding_model", "mix")
    provider = create_embedding_provider(provider=provider_name, model_key=model_key)
    return validate_embedding_provider(provider, require_semantic=True, allow_hash=False)


def _cache_provider(provider: Any, db: VaultDB, *, persist_cache: bool) -> Any:
    if persist_cache:
        if isinstance(provider, PersistentCachedEmbeddingProvider):
            return provider
        return PersistentCachedEmbeddingProvider(provider, db)
    if isinstance(provider, (CachedEmbeddingProvider, PersistentCachedEmbeddingProvider)):
        return provider
    return CachedEmbeddingProvider(provider)


def _load_unique_qa_queries(qa_file: Path | None) -> list[str]:
    if qa_file is None:
        return []
    qa = load_search_qa_set(qa_file)
    seen: set[str] = set()
    queries: list[str] = []
    for case in qa["cases"]:
        query = str(case["query"])
        if query not in seen:
            seen.add(query)
            queries.append(query)
    return queries


def _provider_payload(provider: Any) -> dict[str, Any]:
    return {
        "provider_id": str(getattr(provider, "provider_id", provider.__class__.__name__)),
        "is_semantic": bool(getattr(provider, "is_semantic", True)),
        "dimension": int(getattr(provider, "dim")),
        "cache_size": int(getattr(provider, "cache_size", 0)),
    }


def _persistent_cache_payload(provider: Any) -> dict[str, int]:
    return {
        "memory_rows": int(getattr(provider, "cache_size", 0)),
        "persistent_hits": int(getattr(provider, "persistent_hits", 0)),
        "persistent_misses": int(getattr(provider, "persistent_misses", 0)),
        "writes": int(getattr(provider, "writes", 0)),
    }
