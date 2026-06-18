"""Deterministic semantic-index plumbing for public-safe tests and base installs.

This module intentionally does not require a real embedding service. It provides a
stable hash provider so node/claim indexing can be tested before production
semantic providers are wired in later PRs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import struct
from typing import Any, Protocol

from .db import VaultDB

SEMANTIC_MAX_SCAN_ROWS = 10000
from .docmap import build_document_map_for_entry


@dataclass(frozen=True)
class SemanticIndexStats:
    """Summary of one semantic-index rebuild."""

    knowledge_rows: int
    node_vectors: int
    claim_vectors: int
    provider_id: str
    dimension: int


@dataclass(frozen=True)
class SemanticVecIndexStats:
    """Summary of one sqlite-vec semantic shadow-index rebuild."""

    indexed_vectors: int
    provider_id: str
    vector_kind: str
    dimension: int
    table_name: str


class SemanticEmbeddingProvider(Protocol):
    """Minimal provider interface used by semantic-index plumbing."""

    @property
    def provider_id(self) -> str: ...

    @property
    def is_semantic(self) -> bool: ...

    @property
    def dim(self) -> int: ...

    def encode(self, texts: str | list[str]) -> list[list[float]]: ...


class SemanticProviderError(RuntimeError):
    """Raised when a provider violates semantic-index safety gates."""


def provider_id(provider: SemanticEmbeddingProvider) -> str:
    return str(getattr(provider, "provider_id", provider.__class__.__name__))


def provider_dimension(provider: SemanticEmbeddingProvider) -> int:
    return int(provider.dim)


def provider_is_semantic(provider: SemanticEmbeddingProvider) -> bool:
    return bool(getattr(provider, "is_semantic", True))


def validate_embedding_provider(
    provider: SemanticEmbeddingProvider,
    *,
    require_semantic: bool = False,
    allow_hash: bool = True,
) -> SemanticEmbeddingProvider:
    """Validate provider semantics before indexing or search.

    Hash/test providers are allowed by default for local tests. Production-style
    callers should set `require_semantic=True` or `allow_hash=False` to fail
    closed instead of silently accepting deterministic hash vectors.
    """
    is_semantic = provider_is_semantic(provider)
    pid = provider_id(provider)
    if require_semantic and not is_semantic:
        raise SemanticProviderError(
            f"Provider {pid!r} is not a semantic embedding provider; "
            "configure a real provider or disable require_semantic."
        )
    if not allow_hash and not is_semantic:
        raise SemanticProviderError(
            f"Provider {pid!r} is a hash/test provider; pass allow_hash=True only for tests."
        )
    return provider


class CachedEmbeddingProvider:
    """In-memory cache wrapper keyed by provider id, dimension, and text hash."""

    cache_version = "v1"

    def __init__(self, provider: SemanticEmbeddingProvider):
        self.provider = provider
        self._cache: dict[tuple[str, int, str, str], list[float]] = {}

    @property
    def provider_id(self) -> str:
        return provider_id(self.provider)

    @property
    def is_semantic(self) -> bool:
        return provider_is_semantic(self.provider)

    @property
    def dim(self) -> int:
        return provider_dimension(self.provider)

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        text_list = [texts] if isinstance(texts, str) else list(texts)
        results: list[list[float] | None] = []
        missing_texts: list[str] = []
        missing_indexes: list[int] = []

        for index, text in enumerate(text_list):
            key = self._cache_key(text)
            if key in self._cache:
                results.append(self._cache[key])
            else:
                results.append(None)
                missing_texts.append(text)
                missing_indexes.append(index)

        if missing_texts:
            encoded = self.provider.encode(missing_texts)
            for index, text, vector in zip(missing_indexes, missing_texts, encoded, strict=True):
                key = self._cache_key(text)
                self._cache[key] = vector
                results[index] = vector

        return [vector for vector in results if vector is not None]

    def _cache_key(self, text: str) -> tuple[str, int, str, str]:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return (self.provider_id, self.dim, self.cache_version, digest)

    @property
    def cache_size(self) -> int:
        return len(self._cache)


def embedding_text_hash(text: str) -> str:
    """Return the stable public-safe hash used for embedding cache keys."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cached_embedding(
    db: VaultDB,
    provider_id: str,
    dimension: int,
    text: str,
) -> list[float] | None:
    """Read one embedding from the durable cache and update usage counters."""
    text_hash = embedding_text_hash(text)
    row = db.conn.execute(
        """SELECT id, vector FROM embedding_cache
           WHERE provider_id=? AND dimension=? AND text_hash=?""",
        (provider_id, dimension, text_hash),
    ).fetchone()
    if row is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    db.conn.execute(
        """UPDATE embedding_cache
              SET last_used_at=?, hit_count=hit_count+1
            WHERE id=?""",
        (now, row["id"]),
    )
    db.conn.commit()
    return [float(value) for value in json.loads(row["vector"])]


def set_cached_embedding(
    db: VaultDB,
    provider_id: str,
    dimension: int,
    text: str,
    vector: list[float],
) -> None:
    """Write or refresh one embedding in the durable cache."""
    now = datetime.now(timezone.utc).isoformat()
    db.conn.execute(
        """INSERT INTO embedding_cache
           (provider_id, text_hash, dimension, vector, text, created_at, last_used_at, hit_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0)
           ON CONFLICT(provider_id, dimension, text_hash) DO UPDATE SET
             vector=excluded.vector,
             text=excluded.text,
             last_used_at=excluded.last_used_at""",
        (provider_id, embedding_text_hash(text), dimension, json.dumps(vector), text, now, now),
    )
    db.conn.commit()


def embedding_cache_stats(
    db: VaultDB,
    *,
    provider_id: str | None = None,
    dimension: int | None = None,
) -> dict[str, Any]:
    """Return aggregate durable embedding-cache statistics."""
    where: list[str] = []
    params: list[Any] = []
    if provider_id is not None:
        where.append("provider_id=?")
        params.append(provider_id)
    if dimension is not None:
        where.append("dimension=?")
        params.append(dimension)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    row = db.conn.execute(
        f"""SELECT count(*) AS total_rows,
                  coalesce(sum(hit_count), 0) AS total_hits,
                  min(last_used_at) AS oldest_last_used,
                  max(last_used_at) AS newest_last_used
             FROM embedding_cache {where_sql}""",
        params,
    ).fetchone()
    payload: dict[str, Any] = {
        "total_rows": int(row["total_rows"]),
        "total_hits": int(row["total_hits"]),
        "oldest_last_used": row["oldest_last_used"],
        "newest_last_used": row["newest_last_used"],
    }
    if provider_id is not None:
        payload["provider_id"] = provider_id
    if dimension is not None:
        payload["dimension"] = int(dimension)
    return payload


def prune_embedding_cache(
    db: VaultDB,
    *,
    provider_id: str | None = None,
    dimension: int | None = None,
    older_than_days: int | None = None,
    max_rows: int | None = None,
) -> int:
    """Delete durable cache rows by filters and/or keep only newest max_rows."""
    deleted = 0
    where: list[str] = []
    params: list[Any] = []
    if provider_id is not None:
        where.append("provider_id=?")
        params.append(provider_id)
    if dimension is not None:
        where.append("dimension=?")
        params.append(dimension)
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
        where.append("last_used_at<?")
        params.append(cutoff_iso)
    if older_than_days is not None:
        result = db.conn.execute(
            f"DELETE FROM embedding_cache WHERE {' AND '.join(where)}",
            params,
        )
        deleted += int(result.rowcount if result.rowcount != -1 else 0)

    if max_rows is not None:
        keep_where: list[str] = []
        keep_params: list[Any] = []
        if provider_id is not None:
            keep_where.append("provider_id=?")
            keep_params.append(provider_id)
        if dimension is not None:
            keep_where.append("dimension=?")
            keep_params.append(dimension)
        keep_sql = f"WHERE {' AND '.join(keep_where)}" if keep_where else ""
        result = db.conn.execute(
            f"""DELETE FROM embedding_cache
                 WHERE id IN (
                     SELECT ec.id FROM embedding_cache AS ec
                     {keep_sql}
                     ORDER BY ec.last_used_at DESC, ec.id DESC
                     LIMIT -1 OFFSET ?
                 )""",
            [*keep_params, max_rows],
        )
        deleted += int(result.rowcount if result.rowcount != -1 else 0)
    db.conn.commit()
    return deleted


class PersistentCachedEmbeddingProvider:
    """Embedding provider with small in-memory cache backed by VaultDB."""

    cache_version = "v1"

    def __init__(self, provider: SemanticEmbeddingProvider, db: VaultDB):
        self.provider = provider
        self.db = db
        self._cache: dict[tuple[str, int, str, str], list[float]] = {}
        self.persistent_hits = 0
        self.persistent_misses = 0
        self.writes = 0

    @property
    def provider_id(self) -> str:
        return provider_id(self.provider)

    @property
    def is_semantic(self) -> bool:
        return provider_is_semantic(self.provider)

    @property
    def dim(self) -> int:
        return provider_dimension(self.provider)

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        text_list = [texts] if isinstance(texts, str) else list(texts)
        results: list[list[float] | None] = [None] * len(text_list)
        unique_misses: dict[str, list[int]] = {}

        for index, text in enumerate(text_list):
            key = self._cache_key(text)
            if key in self._cache:
                results[index] = self._cache[key]
                continue
            vector = get_cached_embedding(self.db, self.provider_id, self.dim, text)
            if vector is not None:
                self.persistent_hits += 1
                self._cache[key] = vector
                results[index] = vector
                continue
            self.persistent_misses += 1
            unique_misses.setdefault(text, []).append(index)

        if unique_misses:
            miss_texts = list(unique_misses)
            encoded = self.provider.encode(miss_texts)
            for text, vector in zip(miss_texts, encoded, strict=True):
                key = self._cache_key(text)
                self._cache[key] = vector
                set_cached_embedding(self.db, self.provider_id, self.dim, text, vector)
                self.writes += 1
                for index in unique_misses[text]:
                    results[index] = vector

        return [vector for vector in results if vector is not None]

    def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if callable(close):
            close()

    def _cache_key(self, text: str) -> tuple[str, int, str, str]:
        return (self.provider_id, self.dim, self.cache_version, embedding_text_hash(text))


class DeterministicHashEmbeddingProvider:
    """Small deterministic embedding provider for tests and public demos.

    The vectors are useful for plumbing tests only. `is_semantic=False` makes the
    boundary explicit so later production gates can reject this provider when true
    semantic embeddings are required.
    """

    provider_id = "hash-deterministic-v1"
    is_semantic = False

    def __init__(self, dim: int = 32):
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        if isinstance(texts, str):
            texts = [texts]
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self._dim:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) == self._dim:
                    break
            counter += 1
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [round(value / norm, 8) for value in values]


def rebuild_semantic_index(
    db: VaultDB,
    provider: SemanticEmbeddingProvider | None = None,
    knowledge_id: int | None = None,
    *,
    require_semantic: bool = False,
    allow_hash: bool = True,
) -> SemanticIndexStats:
    """Rebuild deterministic node/claim vectors for one row or the whole DB."""
    provider = validate_embedding_provider(
        provider or DeterministicHashEmbeddingProvider(),
        require_semantic=require_semantic,
        allow_hash=allow_hash,
    )
    rows = _knowledge_rows(db, knowledge_id)
    now = datetime.now(timezone.utc).isoformat()
    node_count = 0
    claim_count = 0

    for row in rows:
        kid = int(row["id"])
        build_document_map_for_entry(db.conn, kid)
        _delete_vectors_for_knowledge(db, kid, provider)

        node_items = _node_items(db, kid)
        claim_items = _claim_items(db, kid)
        _insert_vectors(db, node_items, "node", provider, now)
        _insert_vectors(db, claim_items, "claim", provider, now)
        node_count += len(node_items)
        claim_count += len(claim_items)

    db.conn.commit()
    return SemanticIndexStats(
        knowledge_rows=len(rows),
        node_vectors=node_count,
        claim_vectors=claim_count,
        provider_id=provider_id(provider),
        dimension=provider_dimension(provider),
    )


def search_semantic_index(
    db: VaultDB,
    query: str,
    provider: SemanticEmbeddingProvider | None = None,
    vector_kind: str = "claim",
    limit: int = 10,
    *,
    min_trust: float = 0.0,
    layer: str | None = None,
    category: str | None = None,
    require_semantic: bool = False,
    allow_hash: bool = True,
) -> list[dict[str, Any]]:
    """Search stored deterministic semantic vectors and preserve citation metadata.

    使用分批次 + Top-K 堆疊優化，避免一次性加載全部向量導致內存峰值過高。
    """
    provider = validate_embedding_provider(
        provider or DeterministicHashEmbeddingProvider(),
        require_semantic=require_semantic,
        allow_hash=allow_hash,
    )
    query_vec = provider.encode(query)[0]

    # 安全上限：單次查詢最多處理有限向量，防止 DoS；結果會標示是否截斷。
    effective_limit = min(limit, SEMANTIC_MAX_SCAN_ROWS)

    import heapq

    # 建構 SQL 過濾條件（SQL 層權限過濾，避免側信道洩露）
    where_conditions = [
        "sv.provider_id=?",
        "sv.dimension=?",
        "sv.vector_kind=?",
    ]
    params: list[Any] = [provider.provider_id, provider.dim, vector_kind]

    if min_trust > 0.0:
        where_conditions.append("k.trust >= ?")
        params.append(min_trust)
    if layer is not None:
        where_conditions.append("k.layer = ?")
        params.append(layer)
    if category is not None:
        where_conditions.append("k.category = ?")
        params.append(category)

    where_clause = " AND ".join(where_conditions)

    # 使用最小堆維護 Top-K 結果，避免全量排序
    top_results: list[tuple[float, int, dict[str, Any]]] = []
    count = 0
    offset = 0
    batch_size = 500

    while True:
        remaining = SEMANTIC_MAX_SCAN_ROWS - count
        if remaining <= 0:
            break
        rows = db.conn.execute(
            f"""SELECT sv.*, k.title, k.category, k.layer, k.trust,
                      n.heading, n.path
                 FROM semantic_vectors sv
                 JOIN knowledge k ON k.id = sv.knowledge_id
                 LEFT JOIN knowledge_nodes n
                   ON n.knowledge_id = sv.knowledge_id
                  AND n.node_uid = sv.item_uid
                WHERE {where_clause}
                ORDER BY sv.id
                LIMIT ? OFFSET ?""",
            params + [min(batch_size, remaining), offset],
        ).fetchall()

        if not rows:
            break

        for row in rows:
            vector = json.loads(row["vector"])
            score = _dot(query_vec, vector)
            item = dict(row)
            item["_score"] = round(score, 8)
            item["_mode"] = "semantic_hash"
            if item.get("line_start") and item.get("line_end"):
                item["citation"] = (
                    f"#{item['knowledge_id']} {item['title']} "
                    f"L{item['line_start']}-L{item['line_end']}"
                )

            if len(top_results) < effective_limit:
                heapq.heappush(top_results, (score, count, item))
            elif score > top_results[0][0]:
                heapq.heapreplace(top_results, (score, count, item))
            count += 1

        if count >= SEMANTIC_MAX_SCAN_ROWS:
            break
        offset += batch_size

    # 按分數降序排列
    results = [item for _, _, item in sorted(top_results, key=lambda x: x[0], reverse=True)]
    truncated = count >= SEMANTIC_MAX_SCAN_ROWS
    for item in results:
        item["_semantic_scanned_rows"] = count
        item["_semantic_truncated"] = truncated
    return results


def rebuild_semantic_vec_index(
    db: VaultDB,
    provider: SemanticEmbeddingProvider | None = None,
    vector_kind: str = "claim",
    *,
    require_semantic: bool = False,
    allow_hash: bool = True,
) -> SemanticVecIndexStats:
    """Build a sqlite-vec shadow index from stored semantic_vectors rows.

    `semantic_vectors` remains the source of truth. This vec0 table is a
    rebuildable acceleration layer scoped by provider, vector kind, and
    dimension so KNN queries do not need unsupported metadata filters.
    """
    provider = validate_embedding_provider(
        provider or DeterministicHashEmbeddingProvider(),
        require_semantic=require_semantic,
        allow_hash=allow_hash,
    )
    table_name = _semantic_vec_table_name(provider.provider_id, vector_kind, provider.dim)
    _ensure_semantic_vec_table(db, table_name, provider.dim)
    db.conn.execute(f'DELETE FROM "{table_name}"')

    rows = db.conn.execute(
        """SELECT id, vector
             FROM semantic_vectors
            WHERE provider_id=? AND dimension=? AND vector_kind=?
            ORDER BY id""",
        (provider.provider_id, provider.dim, vector_kind),
    ).fetchall()
    db.conn.executemany(
        f"""INSERT INTO "{table_name}"(rowid, embedding, semantic_vector_id)
            VALUES (?, ?, ?)""",
        [
            (
                int(row["id"]),
                _serialize_float32(json.loads(row["vector"]), provider.dim),
                int(row["id"]),
            )
            for row in rows
        ],
    )
    db.conn.commit()
    return SemanticVecIndexStats(
        indexed_vectors=len(rows),
        provider_id=provider.provider_id,
        vector_kind=vector_kind,
        dimension=provider.dim,
        table_name=table_name,
    )


def search_semantic_index_vec(
    db: VaultDB,
    query: str,
    provider: SemanticEmbeddingProvider | None = None,
    vector_kind: str = "claim",
    limit: int = 10,
    *,
    min_trust: float = 0.0,
    layer: str | None = None,
    category: str | None = None,
    require_semantic: bool = False,
    allow_hash: bool = True,
    candidate_limit: int | None = None,
) -> list[dict[str, Any]]:
    """Search the sqlite-vec semantic shadow index and preserve citation metadata."""
    provider = validate_embedding_provider(
        provider or DeterministicHashEmbeddingProvider(),
        require_semantic=require_semantic,
        allow_hash=allow_hash,
    )
    table_name = _semantic_vec_table_name(provider.provider_id, vector_kind, provider.dim)
    if not _semantic_vec_table_exists(db, table_name):
        return []

    query_vec = provider.encode(query)[0]
    effective_limit = max(0, min(limit, SEMANTIC_MAX_SCAN_ROWS))
    if effective_limit == 0:
        return []
    k = candidate_limit or min(max(effective_limit * 20, 100), SEMANTIC_MAX_SCAN_ROWS)

    candidate_rows = db.conn.execute(
        f"""SELECT semantic_vector_id, distance
              FROM "{table_name}"
             WHERE embedding MATCH ? AND k = ?
             ORDER BY distance ASC""",
        (_serialize_float32(query_vec, provider.dim), k),
    ).fetchall()
    if not candidate_rows:
        return []

    rank_by_id = {
        int(row["semantic_vector_id"]): (rank, float(row["distance"]))
        for rank, row in enumerate(candidate_rows)
    }
    placeholders = ",".join("?" for _ in rank_by_id)
    where_conditions = [
        f"sv.id IN ({placeholders})",
        "sv.provider_id=?",
        "sv.dimension=?",
        "sv.vector_kind=?",
    ]
    params: list[Any] = list(rank_by_id) + [provider.provider_id, provider.dim, vector_kind]
    if min_trust > 0.0:
        where_conditions.append("k.trust >= ?")
        params.append(min_trust)
    if layer is not None:
        where_conditions.append("k.layer = ?")
        params.append(layer)
    if category is not None:
        where_conditions.append("k.category = ?")
        params.append(category)

    rows = db.conn.execute(
        f"""SELECT sv.*, k.title, k.category, k.layer, k.trust,
                  n.heading, n.path
             FROM semantic_vectors sv
             JOIN knowledge k ON k.id = sv.knowledge_id
             LEFT JOIN knowledge_nodes n
               ON n.knowledge_id = sv.knowledge_id
              AND n.node_uid = sv.item_uid
            WHERE {" AND ".join(where_conditions)}""",
        params,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        candidate_rank, distance = rank_by_id[int(row["id"])]
        item["_score"] = round(1.0 / (1.0 + distance), 8)
        item["_semantic_distance"] = round(distance, 8)
        item["_semantic_vec_rank"] = candidate_rank + 1
        item["_mode"] = "semantic_vec"
        if item.get("line_start") and item.get("line_end"):
            item["citation"] = (
                f"#{item['knowledge_id']} {item['title']} "
                f"L{item['line_start']}-L{item['line_end']}"
            )
        results.append(item)

    results.sort(key=lambda item: int(item["_semantic_vec_rank"]))
    results = results[:effective_limit]
    for item in results:
        item["_semantic_scanned_rows"] = len(candidate_rows)
        item["_semantic_truncated"] = len(candidate_rows) >= SEMANTIC_MAX_SCAN_ROWS
        item["_semantic_index_backend"] = "sqlite_vec"
    return results


def semantic_index_counts(db: VaultDB) -> dict[str, int]:
    """Return simple semantic index row counts by vector kind."""
    rows = db.conn.execute(
        "SELECT vector_kind, count(*) AS count FROM semantic_vectors GROUP BY vector_kind"
    ).fetchall()
    return {row["vector_kind"]: int(row["count"]) for row in rows}


def _semantic_vec_table_name(provider_id_value: str, vector_kind: str, dimension: int) -> str:
    digest = hashlib.sha256(f"{provider_id_value}\0{vector_kind}".encode()).hexdigest()[:16]
    dim = int(dimension)
    if dim <= 0:
        raise ValueError("semantic vector dimension must be positive")
    return f"semantic_vec_{digest}_d{dim}"


def _ensure_semantic_vec_table(db: VaultDB, table_name: str, dimension: int) -> None:
    if not getattr(db, "_vec_available", False):
        raise RuntimeError("sqlite-vec is not available for semantic vector indexing")
    if not table_name.startswith("semantic_vec_"):
        raise ValueError("invalid semantic vec table name")
    dim = int(dimension)
    if dim <= 0:
        raise ValueError("semantic vector dimension must be positive")
    db.conn.execute(
        f"""CREATE VIRTUAL TABLE IF NOT EXISTS "{table_name}"
            USING vec0(
                embedding float[{dim}],
                +semantic_vector_id integer
            )"""
    )


def _semantic_vec_table_exists(db: VaultDB, table_name: str) -> bool:
    if not getattr(db, "_vec_available", False):
        return False
    row = db.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _serialize_float32(vector: list[float], dimension: int) -> bytes:
    if len(vector) != dimension:
        raise ValueError(
            f"semantic vector dimension mismatch: expected {dimension}, got {len(vector)}"
        )
    return struct.pack(f"{dimension}f", *vector)


def _knowledge_rows(db: VaultDB, knowledge_id: int | None) -> list[Any]:
    if knowledge_id is not None:
        rows = db.conn.execute("SELECT id FROM knowledge WHERE id=?", (knowledge_id,)).fetchall()
    else:
        rows = db.conn.execute("SELECT id FROM knowledge ORDER BY id").fetchall()
    return list(rows)


def _delete_vectors_for_knowledge(
    db: VaultDB,
    knowledge_id: int,
    provider: SemanticEmbeddingProvider,
) -> None:
    db.conn.execute(
        """DELETE FROM semantic_vectors
           WHERE knowledge_id=? AND provider_id=? AND dimension=?""",
        (knowledge_id, provider.provider_id, provider.dim),
    )


def _node_items(db: VaultDB, knowledge_id: int) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT node_uid, heading, path, summary, content_hash, line_start, line_end
             FROM knowledge_nodes
            WHERE knowledge_id=?
            ORDER BY line_start, id""",
        (knowledge_id,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        source_text = "\n".join(
            value
            for value in (row["path"], row["heading"], row["summary"])
            if value
        )
        items.append(
            {
                "knowledge_id": knowledge_id,
                "item_uid": row["node_uid"],
                "source_text": source_text,
                "content_hash": row["content_hash"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
            }
        )
    return items


def _claim_items(db: VaultDB, knowledge_id: int) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT claim_uid, claim, content_hash, line_start, line_end
             FROM knowledge_claims
            WHERE knowledge_id=?
            ORDER BY line_start, id""",
        (knowledge_id,),
    ).fetchall()
    return [
        {
            "knowledge_id": knowledge_id,
            "item_uid": row["claim_uid"],
            "source_text": row["claim"],
            "content_hash": row["content_hash"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
        }
        for row in rows
    ]


def _insert_vectors(
    db: VaultDB,
    items: list[dict[str, Any]],
    vector_kind: str,
    provider: SemanticEmbeddingProvider,
    now: str,
) -> None:
    if not items:
        return
    vectors = provider.encode([item["source_text"] for item in items])
    db.conn.executemany(
        """INSERT OR REPLACE INTO semantic_vectors
           (knowledge_id, vector_kind, item_uid, provider_id, dimension, vector,
            source_text, content_hash, line_start, line_end, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                item["knowledge_id"],
                vector_kind,
                item["item_uid"],
                provider.provider_id,
                provider.dim,
                json.dumps(vector),
                item["source_text"],
                item["content_hash"],
                item["line_start"],
                item["line_end"],
                now,
                now,
            )
            for item, vector in zip(items, vectors, strict=True)
        ],
    )


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
