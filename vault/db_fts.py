"""FTS5 keyword index helpers for VaultDB."""

from __future__ import annotations

import sqlite3


def init_fts_table(conn: sqlite3.Connection) -> bool:
    """Create and backfill the optional FTS5 keyword index."""
    try:
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                title,
                content_raw,
                content_aaak,
                tags,
                category,
                tokenize='unicode61'
            )"""
        )
        rebuild_fts_index_if_empty(conn, fts_available=True)
        return True
    except sqlite3.OperationalError:
        return False


def rebuild_fts_index_if_empty(conn: sqlite3.Connection, *, fts_available: bool) -> None:
    """Backfill FTS rows for existing databases without rebuilding every connect."""
    if not fts_available:
        return
    row = conn.execute("SELECT count(*) AS count FROM knowledge_fts").fetchone()
    if row and int(row["count"]) > 0:
        return
    conn.execute(
        """INSERT INTO knowledge_fts(rowid, title, content_raw, content_aaak, tags, category)
           SELECT id, title, content_raw, content_aaak, tags, category FROM knowledge"""
    )


def sync_fts_row(conn: sqlite3.Connection, knowledge_id: int, *, fts_available: bool) -> None:
    """Synchronize one knowledge row into the optional FTS5 index."""
    if not fts_available:
        return
    row = conn.execute(
        "SELECT id, title, content_raw, content_aaak, tags, category FROM knowledge WHERE id=?",
        (knowledge_id,),
    ).fetchone()
    if not row:
        return
    conn.execute("DELETE FROM knowledge_fts WHERE rowid=?", (knowledge_id,))
    conn.execute(
        """INSERT INTO knowledge_fts(rowid, title, content_raw, content_aaak, tags, category)
           VALUES(?,?,?,?,?,?)""",
        (
            row["id"],
            row["title"],
            row["content_raw"],
            row["content_aaak"],
            row["tags"],
            row["category"],
        ),
    )


def delete_fts_row(conn: sqlite3.Connection, knowledge_id: int, *, fts_available: bool) -> None:
    """Remove one knowledge row from the optional FTS5 index."""
    if fts_available:
        conn.execute("DELETE FROM knowledge_fts WHERE rowid=?", (knowledge_id,))


def quote_fts_token(token: str) -> str:
    """Quote a FTS5 token as a literal and clamp very long inputs."""
    if len(token) > 100:
        token = token[:100]
    return '"' + token.replace('"', '""') + '"'


def search_fts_keyword(
    conn: sqlite3.Connection,
    *,
    fts_available: bool,
    terms: list[str],
    limit: int = 10,
    min_trust: float = 0.0,
    layer: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Keyword search using optional FTS5 + BM25. Raises if unavailable/bad query."""
    if not fts_available:
        raise RuntimeError("全文搜尋功能未啟用")

    max_fts_terms = 50
    filtered_terms = [term for term in terms if term]
    if len(filtered_terms) > max_fts_terms:
        filtered_terms = filtered_terms[:max_fts_terms]
    match_query = " OR ".join(quote_fts_token(term) for term in filtered_terms)
    if not match_query:
        return []

    filters = ["k.trust >= ?"]
    params: list = [match_query, min_trust]
    if layer:
        filters.append("k.layer=?")
        params.append(layer)
    if category:
        filters.append("k.category=?")
        params.append(category)
    where = " AND ".join(filters)
    params.append(limit)

    rows = conn.execute(
        f"""SELECT k.*, bm25(knowledge_fts) AS _bm25
            FROM knowledge_fts
            JOIN knowledge k ON k.id = knowledge_fts.rowid
           WHERE knowledge_fts MATCH ? AND {where}
             AND COALESCE(k.status, 'active') != 'archived'
           ORDER BY _bm25 ASC, k.trust DESC
           LIMIT ?""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]
