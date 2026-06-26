"""Graph and entity helpers for VaultDB."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3


def add_edge(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    relation: str = "related_to",
    weight: float = 1.0,
    auto_inferred: bool = False,
) -> int:
    """Add an edge and return its id. Existing same-direction edges are reused."""
    existing = conn.execute(
        "SELECT id FROM edges WHERE source_id=? AND target_id=? AND relation=?",
        (source_id, target_id, relation),
    ).fetchone()
    if existing:
        return existing[0]

    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO edges(source_id, target_id, relation, weight, auto_inferred, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (source_id, target_id, relation, weight, int(auto_inferred), now),
    )
    conn.commit()
    return cursor.lastrowid


def delete_edge(conn: sqlite3.Connection, edge_id: int) -> bool:
    conn.execute("DELETE FROM edges WHERE id=?", (edge_id,))
    conn.commit()
    return conn.total_changes > 0


def get_edges(
    conn: sqlite3.Connection,
    node_id: int | None = None,
    relation: str | None = None,
    direction: str = "both",
) -> list[dict]:
    """Return graph edges, optionally filtered by node, relation, and direction."""
    conditions = []
    params: list = []

    if node_id is not None:
        if direction in ("outgoing", "both"):
            conditions.append("source_id=?")
            params.append(node_id)
        if direction in ("incoming", "both"):
            conditions.append("target_id=?")
            params.append(node_id)
        if direction == "both":
            where = f"({' OR '.join(conditions)})"
        else:
            where = conditions[0] if conditions else "1=1"
    else:
        where = "1=1"

    if relation:
        where += " AND relation=?"
        params.append(relation)

    rows = conn.execute(f"SELECT * FROM edges WHERE {where} ORDER BY weight DESC", params).fetchall()
    return [dict(row) for row in rows]


def get_neighbors(
    conn: sqlite3.Connection,
    node_id: int,
    max_depth: int = 2,
    min_weight: float = 0.0,
    min_trust: float = 0.0,
    layer: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Traverse graph neighbors with bounded depth and optional knowledge filters."""
    if node_id is None or not isinstance(node_id, (int, float)):
        return []
    node_id = int(node_id)

    max_depth_limit = 10
    max_neighbors = 200
    max_visited = 500
    if max_depth > max_depth_limit:
        max_depth = max_depth_limit
    if max_depth < 0:
        max_depth = 0

    if min_weight < 0:
        min_weight = 0.0
    if min_trust < 0:
        min_trust = 0.0
    if min_trust > 1:
        min_trust = 1.0

    need_perm_check = min_trust > 0.0 or layer is not None or category is not None
    visited = {node_id}
    frontier = {node_id}
    all_neighbors: dict[int, dict] = {}

    for depth in range(1, max_depth + 1):
        next_frontier = set()
        layer_neighbors: dict[int, dict] = {}

        for nid in frontier:
            if len(visited) >= max_visited:
                break
            rows = conn.execute(
                "SELECT source_id, target_id, relation, weight FROM edges "
                "WHERE (source_id=? OR target_id=?) AND weight >= ?",
                (nid, nid, min_weight),
            ).fetchall()
            for row in rows:
                if len(visited) >= max_visited:
                    break
                neighbor = row["target_id"] if row["source_id"] == nid else row["source_id"]
                if neighbor not in visited and neighbor not in layer_neighbors:
                    layer_neighbors[neighbor] = {
                        "id": neighbor,
                        "distance": depth,
                        "relation": row["relation"],
                        "weight": row["weight"],
                    }

        if need_perm_check and layer_neighbors:
            neighbor_ids = list(layer_neighbors.keys())
            placeholders = ",".join("?" * len(neighbor_ids))
            where_conditions = [f"id IN ({placeholders})", "trust >= ?"]
            params: list = neighbor_ids + [min_trust]

            if layer is not None:
                where_conditions.append("layer = ?")
                params.append(layer)
            if category is not None:
                where_conditions.append("category = ?")
                params.append(category)

            where_clause = " AND ".join(where_conditions)
            sql = f"SELECT id, trust, layer, category FROM knowledge WHERE {where_clause}"
            valid_rows = conn.execute(sql, params).fetchall()
            valid_ids = {row["id"] for row in valid_rows}

            for nid in valid_ids:
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.add(nid)
                    all_neighbors[nid] = layer_neighbors[nid]
        else:
            for nid, info in layer_neighbors.items():
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.add(nid)
                    all_neighbors[nid] = info

        if len(visited) >= max_visited:
            break
        frontier = next_frontier
        if not frontier:
            break

    return list(all_neighbors.values())[:max_neighbors]


def add_entity(conn: sqlite3.Connection, name: str, entity_type: str = "concept") -> int:
    """Add an entity and return its id. Existing names are reused."""
    existing = conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()
    if existing:
        return existing[0]
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO entities(name, entity_type, created_at) VALUES(?,?,?)",
        (name, entity_type, now),
    )
    conn.commit()
    return cursor.lastrowid


def link_entity_knowledge(conn: sqlite3.Connection, entity_id: int, knowledge_id: int) -> None:
    """Link an entity to a knowledge row if the link does not already exist."""
    existing = conn.execute(
        "SELECT id FROM entity_knowledge WHERE entity_id=? AND knowledge_id=?",
        (entity_id, knowledge_id),
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO entity_knowledge(entity_id, knowledge_id) VALUES(?,?)",
            (entity_id, knowledge_id),
        )
        conn.commit()


def get_entities_for_knowledge(conn: sqlite3.Connection, knowledge_id: int) -> list[dict]:
    """Return all entities linked to a knowledge row."""
    rows = conn.execute(
        "SELECT e.* FROM entities e "
        "JOIN entity_knowledge ek ON e.id = ek.entity_id "
        "WHERE ek.knowledge_id=?",
        (knowledge_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_knowledge_for_entity(conn: sqlite3.Connection, entity_name: str) -> list[int]:
    """Return all knowledge ids linked to an entity name."""
    rows = conn.execute(
        "SELECT ek.knowledge_id FROM entities e "
        "JOIN entity_knowledge ek ON e.id = ek.entity_id "
        "WHERE e.name=?",
        (entity_name,),
    ).fetchall()
    return [row[0] for row in rows]
