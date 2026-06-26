"""sqlite-vec table helpers for VaultDB."""

from __future__ import annotations

import sqlite3
import struct
import sys
from typing import Any


def parse_embedding_dim(value: str, *, default: int = 384) -> int:
    """Return a safe embedding dimension for sqlite-vec table creation/search."""
    try:
        dim = int(value)
        if dim < 64 or dim > 4096:
            raise ValueError(f"embedding_dim out of range: {dim}")
        return dim
    except (ValueError, TypeError):
        return default


def init_vec_table(conn: sqlite3.Connection, *, embedding_dim: str) -> None:
    """Create the sqlite-vec virtual table without dropping existing vectors."""
    dim = parse_embedding_dim(embedding_dim)
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_vec USING vec0("
            f"  knowledge_id INTEGER PRIMARY KEY, "
            f"  embedding float[{dim}]"
            f")"
        )
        conn.commit()
    except Exception as e:
        if "already exists" in str(e).lower() or "different" in str(e).lower():
            print("[vault-mcp] ⚠️ 向量表初始化異常，正在重建", file=sys.stderr)
            conn.execute("DROP TABLE IF EXISTS knowledge_vec")
            conn.execute(
                f"CREATE VIRTUAL TABLE knowledge_vec USING vec0("
                f"  knowledge_id INTEGER PRIMARY KEY, "
                f"  embedding float[{dim}]"
                f")"
            )
            conn.commit()
        else:
            raise


def add_embedding(conn: sqlite3.Connection, *, vec_available: bool, knowledge_id: int, embedding: list[float]) -> None:
    """Insert or replace one sqlite-vec embedding row."""
    if not vec_available:
        raise RuntimeError("向量功能未啟用")
    emb_bytes = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        "INSERT OR REPLACE INTO knowledge_vec(knowledge_id, embedding) VALUES(?, ?)",
        (knowledge_id, emb_bytes),
    )
    conn.commit()


def search_vector(
    conn: sqlite3.Connection,
    *,
    vec_available: bool,
    embedding_dim: str,
    query_embedding: list[float],
    limit: int = 10,
    min_trust: float = 0.0,
    layer: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Run sqlite-vec search and return matching knowledge rows."""
    if not vec_available:
        raise RuntimeError("向量搜尋功能未啟用")

    if query_embedding is None or not isinstance(query_embedding, (list, tuple)) or len(query_embedding) == 0:
        return []

    expected_dim = parse_embedding_dim(embedding_dim)
    if len(query_embedding) != expected_dim:
        raise ValueError(f"向量維度不匹配：預期 {expected_dim} 維，實際 {len(query_embedding)} 維")

    max_limit = 500
    if limit > max_limit:
        limit = max_limit

    emb_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    vec_search_multiplier = 5
    vec_limit = min(limit * vec_search_multiplier, max_limit)
    vec_rows = conn.execute(
        "SELECT knowledge_id, distance FROM knowledge_vec "
        "WHERE embedding MATCH ? ORDER BY distance ASC LIMIT ?",
        (emb_bytes, vec_limit),
    ).fetchall()

    if not vec_rows:
        return []

    knowledge_ids = [row["knowledge_id"] for row in vec_rows]
    id_to_dist: dict[int, float] = {}
    for row in vec_rows:
        kid = int(row["knowledge_id"])
        dist = row["distance"]
        if isinstance(dist, bytes):
            dist = struct.unpack("f", dist)[0]
        id_to_dist[kid] = float(dist)

    where_conditions = [
        "id IN ({})".format(",".join("?" * len(knowledge_ids))),
        "trust >= ?",
        "COALESCE(status, 'active') != 'archived'",
    ]
    params: list[Any] = list(knowledge_ids)
    params.append(min_trust)

    if layer is not None:
        where_conditions.append("layer = ?")
        params.append(layer)
    if category is not None:
        where_conditions.append("category = ?")
        params.append(category)

    where_clause = " AND ".join(where_conditions)
    rows = conn.execute(f"SELECT * FROM knowledge WHERE {where_clause}", params).fetchall()

    results = []
    for row in rows:
        kid = int(row["id"])
        if kid in id_to_dist:
            item = dict(row)
            item["_distance"] = id_to_dist[kid]
            results.append(item)

    results.sort(key=lambda x: x["_distance"])
    return results
