"""Vault Document Map health metrics collector.

SQLite remains the source of truth.  These metrics are intentionally compact and
pure enough for unit tests; optional Supabase sync maps them into a neutral
remote health table without introducing new local requirements.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .db import VaultDB
from .search import VaultSearch

DEFAULT_SAMPLE_LIMIT = 20
# Keep this aligned with vault_mcp._vault_read_range_payload default.
DEFAULT_MAX_READ_RANGE_LINES = 80


@dataclass(frozen=True)
class VaultHealthMetrics:
    """Daily health snapshot for the Document Map integration."""

    total_entries: int
    entries_with_nodes: int
    entries_with_claims: int
    entries_without_nodes: int
    entries_without_claims: int
    sampled_search_results: int
    search_results_with_best_span: int
    map_coverage: float
    claim_coverage: float
    citation_coverage: float
    read_range_over_limit_violations: int

    def to_dict(self) -> dict:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float:
    """Return a stable 0.0 ratio for empty denominators."""
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _has_usable_best_span(result: dict) -> bool:
    """Best-effort check matching the enriched local search result contract."""
    best_node = result.get("best_node") or {}
    next_actions = result.get("next_actions") or []
    has_read_action = any(
        action.get("tool") == "vault_read_range"
        for action in next_actions
        if isinstance(action, dict)
    )
    return bool(
        result.get("best_span")
        and best_node
        and result.get("line_start")
        and result.get("line_end")
        and (
            result.get("recommended_next_tool") == "vault_read_range"
            or result.get("next_action")
            or has_read_action
        )
    )


def collect_vault_health_metrics(
    db_path: str,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    max_read_range_lines: int = DEFAULT_MAX_READ_RANGE_LINES,
) -> VaultHealthMetrics:
    """Collect Document Map health metrics from the local SQLite database.

    Coverage denominator behavior is explicit:
    - total_entries == 0 => map_coverage and claim_coverage are 0.0
    - sampled_search_results == 0 => citation_coverage is 0.0

    citation_coverage samples deterministic local keyword searches by knowledge
    title and counts results that were enriched with a best span / node / next
    action by VaultSearch.
    """
    db = VaultDB(db_path).connect()
    try:
        return collect_vault_health_metrics_from_db(
            db,
            sample_limit=sample_limit,
            max_read_range_lines=max_read_range_lines,
        )
    finally:
        db.close()


def collect_vault_health_metrics_from_db(
    db: VaultDB,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    max_read_range_lines: int = DEFAULT_MAX_READ_RANGE_LINES,
) -> VaultHealthMetrics:
    """Collect metrics from an already-open VaultDB instance."""
    if db.conn is None:
        raise ValueError("VaultDB must be connected before collecting health metrics")

    try:
        sample_limit = int(sample_limit)
    except (TypeError, ValueError):
        sample_limit = DEFAULT_SAMPLE_LIMIT
    sample_limit = max(0, sample_limit)

    try:
        max_read_range_lines = int(max_read_range_lines)
    except (TypeError, ValueError):
        max_read_range_lines = DEFAULT_MAX_READ_RANGE_LINES
    if max_read_range_lines <= 0:
        max_read_range_lines = DEFAULT_MAX_READ_RANGE_LINES

    conn = db.conn
    total_entries = conn.execute("SELECT COUNT(*) AS c FROM knowledge").fetchone()["c"]
    entries_with_nodes = conn.execute(
        """SELECT COUNT(DISTINCT k.id) AS c
           FROM knowledge k
           JOIN knowledge_nodes n ON n.knowledge_id = k.id"""
    ).fetchone()["c"]
    entries_with_claims = conn.execute(
        """SELECT COUNT(DISTINCT k.id) AS c
           FROM knowledge k
           JOIN knowledge_claims c ON c.knowledge_id = k.id"""
    ).fetchone()["c"]

    entries_without_nodes = total_entries - entries_with_nodes
    entries_without_claims = total_entries - entries_with_claims

    sampled_search_results = 0
    search_results_with_best_span = 0
    if sample_limit > 0 and total_entries > 0:
        search = VaultSearch(db, embed_provider=None, embed_provider_name="none")
        sample_rows = conn.execute(
            "SELECT id, title FROM knowledge ORDER BY id LIMIT ?", (sample_limit,)
        ).fetchall()
        for row in sample_rows:
            query = (row["title"] or str(row["id"])).strip()
            results = search.search(
                query,
                mode="keyword",
                limit=1,
                use_rerank=False,
            )
            sampled_search_results += len(results)
            search_results_with_best_span += sum(
                1 for result in results if _has_usable_best_span(result)
            )

    read_range_over_limit_violations = conn.execute(
        """SELECT COUNT(*) AS c
           FROM knowledge_nodes
           WHERE (line_end - line_start + 1) > ?""",
        (max_read_range_lines,),
    ).fetchone()["c"]

    return VaultHealthMetrics(
        total_entries=total_entries,
        entries_with_nodes=entries_with_nodes,
        entries_with_claims=entries_with_claims,
        entries_without_nodes=entries_without_nodes,
        entries_without_claims=entries_without_claims,
        sampled_search_results=sampled_search_results,
        search_results_with_best_span=search_results_with_best_span,
        map_coverage=_ratio(entries_with_nodes, total_entries),
        claim_coverage=_ratio(entries_with_claims, total_entries),
        citation_coverage=_ratio(search_results_with_best_span, sampled_search_results),
        read_range_over_limit_violations=read_range_over_limit_violations,
    )
