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
from typing import Any, Protocol

from .db import VaultDB
from .docmap import build_document_map_for_entry


@dataclass(frozen=True)
class SemanticIndexStats:
    """Summary of one semantic-index rebuild."""

    knowledge_rows: int
    node_vectors: int
    claim_vectors: int
    provider_id: str
    dimension: int


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
        provider_id=provider.provider_id,
        dimension=provider.dim,
    )


def search_semantic_index(
    db: VaultDB,
    query: str,
    provider: SemanticEmbeddingProvider | None = None,
    vector_kind: str = "claim",
    limit: int = 10,
    *,
    require_semantic: bool = False,
    allow_hash: bool = True,
) -> list[dict[str, Any]]:
    """Search stored deterministic semantic vectors and preserve citation metadata."""
    provider = validate_embedding_provider(
        provider or DeterministicHashEmbeddingProvider(),
        require_semantic=require_semantic,
        allow_hash=allow_hash,
    )
    query_vec = provider.encode(query)[0]
    rows = db.conn.execute(
        """SELECT sv.*, k.title, k.category, k.layer, k.trust,
                  n.heading, n.path
             FROM semantic_vectors sv
             JOIN knowledge k ON k.id = sv.knowledge_id
             LEFT JOIN knowledge_nodes n
               ON n.knowledge_id = sv.knowledge_id
              AND n.node_uid = sv.item_uid
            WHERE sv.provider_id=? AND sv.dimension=? AND sv.vector_kind=?""",
        (provider.provider_id, provider.dim, vector_kind),
    ).fetchall()

    results: list[dict[str, Any]] = []
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
        results.append(item)

    results.sort(key=lambda item: item["_score"], reverse=True)
    return results[:limit]


def semantic_index_counts(db: VaultDB) -> dict[str, int]:
    """Return simple semantic index row counts by vector kind."""
    rows = db.conn.execute(
        "SELECT vector_kind, count(*) AS count FROM semantic_vectors GROUP BY vector_kind"
    ).fetchall()
    return {row["vector_kind"]: int(row["count"]) for row in rows}


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
