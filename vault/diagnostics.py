"""Small diagnostics helpers shared by CLI and DB stats."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection


def semantic_vector_stats(conn: Connection) -> tuple[int, dict[str, int]]:
    """Return total and per-kind JSON semantic vector counts."""
    counts: dict[str, int] = {}
    try:
        rows = conn.execute(
            "SELECT vector_kind, COUNT(*) AS count FROM semantic_vectors GROUP BY vector_kind"
        ).fetchall()
    except Exception:
        return 0, counts
    total = 0
    for row in rows:
        kind = str(row["vector_kind"] or "unknown")
        count = int(row["count"] or 0)
        counts[kind] = count
        total += count
    return total, counts


def embedding_stats(conn: Connection, *, vec_available: bool) -> dict[str, object]:
    """Return a compact embedding-count summary across legacy and semantic stores."""
    legacy_count = 0
    if vec_available:
        try:
            legacy_count = conn.execute("SELECT COUNT(*) FROM knowledge_vec").fetchone()[0]
        except Exception:
            legacy_count = 0
    semantic_count, semantic_counts = semantic_vector_stats(conn)
    total = legacy_count or semantic_count
    source = "legacy_sqlite_vec" if legacy_count else "semantic_vectors"
    return {
        "embedding_count": total,
        "embedding_count_source": source if total else "none",
        "legacy_embedding_count": legacy_count,
        "semantic_vector_count": semantic_count,
        "semantic_vector_counts": semantic_counts,
    }


def stats_summary_lines(stats: dict[str, object]) -> list[str]:
    """Format the fixed top section of ``vault stats`` output."""
    lines = [
        f"  知識筆數:   {stats['knowledge_count']}",
        f"  嵌入筆數:   {stats['embedding_count']} ({stats.get('embedding_count_source', 'unknown')})",
        f"  legacy sqlite-vec: {stats.get('legacy_embedding_count', 0)}",
        f"  semantic_vectors: {stats.get('semantic_vector_count', 0)}",
        f"  圖譜邊數:   {stats.get('edge_count', 0)}",
        f"  圖譜實體:   {stats.get('entity_count', 0)}",
        f"  活躍記憶:   {stats.get('active_count', 0)}",
        f"  歸檔記憶:   {stats.get('archived_count', 0)}",
        f"  已到期未歸檔: {stats.get('expired_active_count', 0)}",
        f"  檢索命中次數: {stats.get('total_accesses', 0)}",
        f"  引用次數:   {stats.get('total_citations', 0)}",
        f"  向量搜尋:   {'✅' if stats['vec_available'] else '❌'}",
    ]
    if not stats["vec_available"] and stats.get("vec_load_error"):
        lines.append(f"  向量降級原因: {stats['vec_load_error']}")
    lines.extend([f"  DB 大小:    {stats['db_size_mb']} MB", f"  DB 路徑:    {stats['db_path']}"])
    return lines


def sqlite_vec_runtime_status(project_dir: str | Path) -> str:
    """Return a human-readable sqlite-vec runtime status for a project DB."""
    from vault.db import VaultDB

    db = None
    try:
        db = VaultDB(str(Path(project_dir) / "vault.db")).connect()
        stats = db.stats()
        if stats.get("vec_available"):
            return "✅ extension loaded for this DB"
        detail = stats.get("vec_load_error") or "extension unavailable"
        return f"⚠️ {detail}; keyword search and semantic_vectors JSON fallback still work"
    except Exception as exc:
        return f"⚠️ runtime check failed: {exc}"
    finally:
        if db is not None:
            db.close()
