"""Graph expansion helpers for VaultSearch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .access_policy import ReadPolicy, can_read_memory

if TYPE_CHECKING:
    from .db import VaultDB


def apply_graph_expand(
    db: "VaultDB",
    results: list[dict],
    *,
    expand_depth: int,
    limit: int,
    min_trust: float = 0.0,
    layer: Optional[str] = None,
    category: Optional[str] = None,
    read_policy: ReadPolicy | None = None,
) -> list[dict]:
    """Expand search results through graph neighbors while honoring ACL filters."""
    if not results:
        return results

    seen_ids = {row["id"] for row in results}
    expanded = list(results)
    for row in results:
        if len(expanded) >= limit:
            break
        neighbors = db.get_neighbors(
            row["id"],
            max_depth=expand_depth,
            min_trust=min_trust,
            layer=layer,
            category=category,
        )
        for neighbor in neighbors:
            if len(expanded) >= limit:
                break
            neighbor_id = neighbor["id"]
            if neighbor_id in seen_ids:
                continue
            knowledge = db.get_knowledge(neighbor_id)
            if not _can_include_neighbor(
                knowledge,
                min_trust=min_trust,
                layer=layer,
                category=category,
                read_policy=read_policy,
            ):
                continue
            seen_ids.add(neighbor_id)
            item = dict(knowledge)
            item["_score"] = row.get("_score", 0.5) * (0.7 ** neighbor["distance"])
            item["_mode"] = "graph_expand"
            item["_graph_distance"] = neighbor["distance"]
            item["_relation"] = neighbor["relation"]
            expanded.append(item)

    expanded.sort(key=lambda item: (-item.get("_score", 0), item.get("_graph_distance", 0)))
    return expanded[:limit]


def _can_include_neighbor(
    knowledge: dict | None,
    *,
    min_trust: float,
    layer: Optional[str],
    category: Optional[str],
    read_policy: ReadPolicy | None,
) -> bool:
    if not knowledge:
        return False
    if knowledge.get("trust", 0) < min_trust:
        return False
    if layer and knowledge.get("layer") != layer:
        return False
    if category and knowledge.get("category") != category:
        return False
    if read_policy is not None and not can_read_memory(knowledge, read_policy):
        return False
    return True
