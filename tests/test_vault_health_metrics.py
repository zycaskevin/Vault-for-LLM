"""Sprint 4C tests: Document Map health metrics and optional remote health sync."""

from __future__ import annotations

import subprocess
import sys
import hashlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.health import collect_vault_health_metrics
from vault.docmap import build_document_map_for_entry
from scripts import sync_to_supabase


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTableQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload = None
        self.filters = []

    def _assert_health_does_not_reference_id(self, fields):
        if self.table_name != sync_to_supabase.VAULT_HEALTH_TABLE:
            return
        for field in fields:
            if field == "id":
                raise AssertionError("remote health fake schema has no id column")

    def select(self, *args, **kwargs):
        self.operation = "select"
        selected_fields = []
        for arg in args:
            selected_fields.extend(part.strip() for part in str(arg).split(","))
        self._assert_health_does_not_reference_id(selected_fields)
        return self

    def limit(self, *args, **kwargs):
        return self

    def eq(self, field, value):
        self._assert_health_does_not_reference_id([field])
        self.filters.append((field, value))
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = dict(payload)
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = dict(payload)
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table_name, [])
        matches = [
            row for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]

        if self.operation == "select":
            return _FakeResponse([dict(row) for row in matches])

        if self.operation == "insert":
            original_payload = dict(self.payload)
            payload = dict(self.payload)
            if self.table_name != sync_to_supabase.VAULT_HEALTH_TABLE:
                payload.setdefault("id", self.client.next_id)
                self.client.next_id += 1
            rows.append(payload)
            self.client.operations.append(("insert", self.table_name, original_payload))
            return _FakeResponse([dict(payload)])

        if self.operation == "update":
            for row in matches:
                row.update(self.payload)
                self.client.operations.append(("update", self.table_name, dict(self.payload), dict(self.filters)))
            return _FakeResponse([dict(row) for row in matches])

        raise AssertionError(f"unknown operation: {self.operation}")


class _FakeSupabaseClient:
    def __init__(self):
        self.next_id = 5000
        self.operations = []
        self.tables = {sync_to_supabase.VAULT_HEALTH_TABLE: []}

    def table(self, table_name: str):
        if table_name not in self.tables:
            raise RuntimeError(f"missing table: {table_name}")
        return _FakeTableQuery(self, table_name)


def _add_entry(db: VaultDB, title: str, raw: str, aaak: str = "") -> int:
    return db.add_knowledge(
        title=title,
        content_raw=raw,
        content_aaak=aaak,
        category="technique",
        source=f"raw/{title.lower().replace(' ', '-')}.md",
        trust=0.9,
    )


def _build_metrics_fixture(tmp_path: Path) -> Path:
    db_path = tmp_path / "vault.db"
    db = VaultDB(db_path).connect()
    try:
        both_id = _add_entry(
            db,
            "Alpha Health Both",
            "# Alpha Root\n"
            "- Alpha health claim is traceable.\n"
            "## Alpha Detail\n"
            "- More alpha detail.",
            "TITLE:Alpha Health Both\n"
            "CLAIMS:\n"
            "- [C1] Alpha health claim is traceable. (L2)",
        )
        build_document_map_for_entry(db.conn, both_id)

        nodes_only_id = _add_entry(
            db,
            "Beta Nodes Only",
            "# Beta Root\n"
            "- Beta has a section node but no AAAK claims.",
        )
        build_document_map_for_entry(db.conn, nodes_only_id)

        _add_entry(
            db,
            "Gamma No Map",
            "# Gamma Root\n"
            "- Gamma has not been built into the Document Map yet.",
        )

        oversize_id = _add_entry(
            db,
            "Delta Oversize",
            "\n".join(f"Delta line {i}" for i in range(1, 82)),
        )
        build_document_map_for_entry(db.conn, oversize_id)
    finally:
        db.close()
    return db_path


def test_collect_vault_health_metrics_empty_db_zero_denominators(tmp_path):
    db_path = tmp_path / "vault.db"
    db = VaultDB(db_path).connect()
    db.close()

    metrics = collect_vault_health_metrics(str(db_path), sample_limit=20)

    assert metrics.total_entries == 0
    assert metrics.entries_with_nodes == 0
    assert metrics.entries_with_claims == 0
    assert metrics.entries_without_nodes == 0
    assert metrics.entries_without_claims == 0
    assert metrics.sampled_search_results == 0
    assert metrics.search_results_with_best_span == 0
    assert metrics.map_coverage == 0.0
    assert metrics.claim_coverage == 0.0
    assert metrics.citation_coverage == 0.0
    assert metrics.read_range_over_limit_violations == 0


def test_collect_vault_health_metrics_counts_map_claim_citation_and_boundary_gaps(tmp_path):
    db_path = _build_metrics_fixture(tmp_path)

    metrics = collect_vault_health_metrics(str(db_path), sample_limit=20)

    assert metrics.total_entries == 4
    assert metrics.entries_with_nodes == 3
    assert metrics.entries_with_claims == 1
    assert metrics.entries_without_nodes == 1
    assert metrics.entries_without_claims == 3
    assert metrics.sampled_search_results == 4
    assert metrics.search_results_with_best_span == 3
    assert metrics.map_coverage == pytest.approx(0.75)
    assert metrics.claim_coverage == pytest.approx(0.25)
    assert metrics.citation_coverage == pytest.approx(0.75)
    assert metrics.read_range_over_limit_violations == 1


def test_collect_vault_health_metrics_sample_limit_zero_has_zero_citation_coverage(tmp_path):
    db_path = _build_metrics_fixture(tmp_path)

    metrics = collect_vault_health_metrics(str(db_path), sample_limit=0)

    assert metrics.total_entries == 4
    assert metrics.sampled_search_results == 0
    assert metrics.search_results_with_best_span == 0
    assert metrics.map_coverage == pytest.approx(0.75)
    assert metrics.claim_coverage == pytest.approx(0.25)
    assert metrics.citation_coverage == 0.0


def test_collect_vault_health_metrics_read_range_boundary_is_strictly_over_80(tmp_path):
    db_path = tmp_path / "vault.db"
    db = VaultDB(db_path).connect()
    try:
        eighty_id = _add_entry(
            db,
            "Eighty Line Boundary",
            "\n".join(f"Eighty line {i}" for i in range(1, 81)),
        )
        build_document_map_for_entry(db.conn, eighty_id)
        eighty_one_id = _add_entry(
            db,
            "Eighty One Line Boundary",
            "\n".join(f"Eighty-one line {i}" for i in range(1, 82)),
        )
        build_document_map_for_entry(db.conn, eighty_one_id)
    finally:
        db.close()

    metrics = collect_vault_health_metrics(str(db_path), sample_limit=0)

    assert metrics.total_entries == 2
    assert metrics.entries_with_nodes == 2
    assert metrics.read_range_over_limit_violations == 1


def test_sync_vault_health_maps_payload_and_upserts_without_network(tmp_path, monkeypatch):
    db_path = _build_metrics_fixture(tmp_path)
    fake = _FakeSupabaseClient()

    def fail_if_real_client_requested():
        raise AssertionError("sync_vault_health should use injected fake client")

    monkeypatch.setattr(sync_to_supabase, "_get_sb_client", fail_if_real_client_requested)

    result = sync_to_supabase.sync_vault_health(
        str(db_path),
        sample_limit=20,
        sb_client=fake,
        check_date="2026-05-09",
    )

    assert result["action"] == "inserted"
    assert result["payload"] == {
        "check_date": "2026-05-09",
        "total_knowledge": 4,
        "convergence_rate": pytest.approx(75.0),
        "avg_freshness": pytest.approx(75.0),
        "contradiction_count": 1,
        "gap_count": 4,
    }
    assert fake.tables[sync_to_supabase.VAULT_HEALTH_TABLE][0]["check_date"] == "2026-05-09"
    assert "id" not in fake.tables[sync_to_supabase.VAULT_HEALTH_TABLE][0]

    db = VaultDB(db_path).connect()
    try:
        _add_entry(db, "Epsilon No Map", "# Epsilon\n- New unmapped entry.")
    finally:
        db.close()

    second = sync_to_supabase.sync_vault_health(
        str(db_path),
        sample_limit=20,
        sb_client=fake,
        check_date="2026-05-09",
    )

    assert second["action"] == "updated"
    assert len(fake.tables[sync_to_supabase.VAULT_HEALTH_TABLE]) == 1
    stored = fake.tables[sync_to_supabase.VAULT_HEALTH_TABLE][0]
    assert stored["total_knowledge"] == 5
    assert stored["gap_count"] == 6
    update_ops = [op for op in fake.operations if op[0] == "update"]
    assert update_ops
    assert update_ops[-1][3] == {"check_date": "2026-05-09"}
    assert "id" not in update_ops[-1][3]


def test_sync_cli_help_exposes_health_flags():
    result = subprocess.run(
        [sys.executable, "scripts/sync_to_supabase.py", "--help"],
        cwd=Path(__file__).parent.parent,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--health" in result.stdout
    assert "--vault-health" in result.stdout
    assert "--health-sample-limit" in result.stdout
    assert "--include-content" in result.stdout


def test_knowledge_sync_payload_excludes_content_by_default():
    row = (
        1, "Title", "L3", "general", "tag", 0.8,
        "raw body", "aaak body", "abc123", "local", "summary",
        "shared", "medium", "profile-agent", '["work-agent"]', "care_summary", "",
        "", "",
    )

    payload = sync_to_supabase._knowledge_sync_payload(row)

    assert payload["content_raw"] == ""
    assert payload["content_aaak"] == ""
    assert payload["summary"] == "summary"
    assert payload["content_hash"] == "abc123"
    assert payload["scope"] == "shared"
    assert payload["sensitivity"] == "medium"
    assert payload["owner_agent"] == "profile-agent"
    assert payload["allowed_agents"] == ["work-agent"]
    assert payload["memory_type"] == "care_summary"


def test_knowledge_sync_payload_generates_hash_when_missing():
    row = (
        1, "Title", "L3", "general", "tag", 0.8,
        "raw body", "aaak body", None, "local", "summary",
        "project", "low", "", "[]", "knowledge", "",
        "", "",
    )

    payload = sync_to_supabase._knowledge_sync_payload(row)

    assert payload["content_hash"]
    assert len(payload["content_hash"]) == 64
    assert payload["content_raw"] == ""


def test_knowledge_sync_payload_regenerates_blank_hashes():
    row = (
        1, "Title", "L3", "general", "tag", 0.8,
        "raw body", "aaak body", "   ", "local", "summary",
        "project", "low", "", "[]", "knowledge", "",
        "", "",
    )

    payload = sync_to_supabase._knowledge_sync_payload(row)

    assert payload["content_hash"] == hashlib.sha256(
        "raw body\naaak body\nsummary\nTitle".encode("utf-8")
    ).hexdigest()
    assert payload["content_hash"].strip()


def test_knowledge_sync_payload_include_content_blocks_privacy_fail():
    blocked_secret_text = "pass" + "word = supersecret123"
    row = (
        1, "Title", "L3", "general", "tag", 0.8,
        blocked_secret_text, "aaak body", "abc123", "local", "summary",
        "project", "low", "", "[]", "knowledge", "",
        "", "",
    )

    payload = sync_to_supabase._knowledge_sync_payload(row, include_content=True)

    assert payload["content_raw"] == ""
    assert payload["content_aaak"] == ""


def test_skill_sync_payload_include_content_when_safe():
    row = (
        1, "skill", "1.0.0", "agent", "general", "search", "",
        0.9, "# Skill\nSafe body.", "hash", "desc", "", "",
    )

    payload = sync_to_supabase._skill_sync_payload(row, include_content=True)

    assert payload["content_raw"] == "# Skill\nSafe body."


def test_skill_sync_payload_generates_hash_when_missing():
    row = (
        1, "skill", "1.0.0", "agent", "general", "search", "",
        0.9, "# Skill\nSafe body.", None, "desc", "", "",
    )

    payload = sync_to_supabase._skill_sync_payload(row)

    assert payload["content_hash"]
    assert len(payload["content_hash"]) == 64


def test_supabase_public_defaults_and_optional_imports_are_neutral(monkeypatch):
    import importlib

    env_vars = [
        "VAULT_SUPABASE_HEALTH_TABLE",
        "VAULT_SUPABASE_KNOWLEDGE_TABLE",
        "VAULT_SUPABASE_GRAPH_ENTITIES_TABLE",
        "VAULT_SUPABASE_GRAPH_EDGES_TABLE",
        "VAULT_SUPABASE_GRAPH_ENTITY_KNOWLEDGE_TABLE",
    ]
    for env_var in env_vars:
        monkeypatch.delenv(env_var, raising=False)

    sync_module = importlib.reload(sync_to_supabase)
    from scripts import fix_ek_links, sync_graph_to_supabase

    graph_module = importlib.reload(sync_graph_to_supabase)
    fix_module = importlib.reload(fix_ek_links)

    assert sync_module.VAULT_HEALTH_TABLE == "vault_health_metrics"
    assert graph_module.GRAPH_ENTITIES_TABLE == "vault_graph_entities"
    assert graph_module.GRAPH_EDGES_TABLE == "vault_graph_edges"
    assert graph_module.GRAPH_ENTITY_KNOWLEDGE_TABLE == "vault_graph_entity_knowledge"
    assert fix_module.GRAPH_ENTITIES_TABLE == "vault_graph_entities"
    assert fix_module.GRAPH_ENTITY_KNOWLEDGE_TABLE == "vault_graph_entity_knowledge"
