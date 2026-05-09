"""Sprint 4A tests: compile hook and Supabase Document Map sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guardrails_lite.guardrails_compile import GuardrailsCompiler
from guardrails_lite.guardrails_db import GuardrailsDB
from guardrails_lite.guardrails_map import build_document_map_for_entry
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

    def select(self, *args, **kwargs):
        self.operation = "select"
        return self

    def limit(self, *args, **kwargs):
        return self

    def eq(self, field, value):
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
            payload.setdefault("id", self.client.next_id)
            self.client.next_id += 1
            rows.append(payload)
            self.client.operations.append(("insert", self.table_name, original_payload))
            return _FakeResponse([payload])

        if self.operation == "update":
            for row in matches:
                row.update(self.payload)
                self.client.operations.append(("update", self.table_name, dict(self.payload), dict(self.filters)))
            return _FakeResponse([dict(row) for row in matches])

        raise AssertionError(f"unknown operation: {self.operation}")


class _FakeSupabaseClient:
    def __init__(self):
        self.next_id = 1000
        self.operations = []
        self.tables = {
            sync_to_supabase.DOCUMENT_MAP_NODE_TABLE: [],
            sync_to_supabase.DOCUMENT_MAP_CLAIM_TABLE: [],
        }

    def table(self, table_name: str):
        if table_name not in self.tables:
            raise RuntimeError(f"missing table: {table_name}")
        return _FakeTableQuery(self, table_name)


def _write_raw(project_dir: Path, body: str) -> Path:
    raw_dir = project_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    raw_file = raw_dir / "entry.md"
    raw_file.write_text(
        "---\n"
        "title: Sprint 4A Compile Hook\n"
        "category: technique\n"
        "layer: L3\n"
        "tags: [document-map, compile]\n"
        "trust: 0.8\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return raw_file


def _count(db: GuardrailsDB, table: str) -> int:
    return db.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def test_compile_refreshes_document_map_for_new_and_updated_entries_but_not_dry_run_or_skipped(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        _write_raw(
            tmp_path,
            "# Overview\n"
            "- First compile hook claim should be captured for map refresh.\n"
            "## Details\n"
            "- Second compile hook claim should also remain traceable.",
        )
        compiler = GuardrailsCompiler(tmp_path, db=db, embed_provider=None)

        dry_stats = compiler.compile(dry_run=True)
        assert dry_stats["new"] == 1
        assert _count(db, "knowledge") == 0
        assert _count(db, "knowledge_nodes") == 0

        stats = compiler.compile()
        assert stats["new"] == 1
        knowledge_id = db.conn.execute("SELECT id FROM knowledge").fetchone()["id"]
        assert _count(db, "knowledge_nodes") >= 2
        assert _count(db, "knowledge_claims") >= 1

        node_count_after_new = _count(db, "knowledge_nodes")
        skipped_stats = compiler.compile()
        assert skipped_stats["skipped"] == 1
        assert _count(db, "knowledge_nodes") == node_count_after_new

        _write_raw(
            tmp_path,
            "# Overview\n"
            "- Updated compile hook claim should refresh document map rows.\n"
            "## Details\n"
            "- Existing detail remains traceable.\n"
            "### Extra\n"
            "- Extra section appears only after update.",
        )
        update_stats = compiler.compile()
        assert update_stats["updated"] == 1
        assert db.conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_nodes WHERE knowledge_id=? AND heading='Extra'",
            (knowledge_id,),
        ).fetchone()["c"] == 1
    finally:
        db.close()


def test_sync_document_map_upserts_nodes_and_claims_without_network(tmp_path, monkeypatch):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        knowledge_id = db.add_knowledge(
            title="Remote Map Resolver Entry",
            content_raw=(
                "# Root\n"
                "- Claim one should be available for remote navigation.\n"
                "## Child\n"
                "- Claim two should be available for remote read_range."
            ),
            content_aaak=(
                "TITLE:Remote Map Resolver Entry\n"
                "CLAIMS:\n"
                "- [C1] Claim one should be available for remote navigation. (L2)\n"
                "- [C2] Claim two should be available for remote read_range. (L4)"
            ),
            category="technique",
            source="raw/remote-map.md",
        )
        build_document_map_for_entry(db.conn, knowledge_id)
    finally:
        db.close()

    fake = _FakeSupabaseClient()
    first_node = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        existing_node = first_node.conn.execute(
            "SELECT knowledge_id, node_uid FROM knowledge_nodes ORDER BY line_start LIMIT 1"
        ).fetchone()
        fake.tables[sync_to_supabase.DOCUMENT_MAP_NODE_TABLE].append(
            {"id": 10, "knowledge_id": existing_node["knowledge_id"], "node_uid": existing_node["node_uid"]}
        )
    finally:
        first_node.close()

    monkeypatch.setattr(sync_to_supabase, "_get_sb_client", lambda: fake)

    stats = sync_to_supabase.sync_document_map(str(tmp_path / "guardrails.db"))

    assert stats["nodes_updated"] == 1
    assert stats["nodes_inserted"] >= 1
    assert stats["claims_inserted"] == 2
    assert stats["claims_failed"] == 0

    node_payloads = [op[2] for op in fake.operations if op[0] in {"insert", "update"} and op[1] == sync_to_supabase.DOCUMENT_MAP_NODE_TABLE]
    claim_payloads = [op[2] for op in fake.operations if op[0] == "insert" and op[1] == sync_to_supabase.DOCUMENT_MAP_CLAIM_TABLE]
    expected_node_keys = set(sync_to_supabase.DOCUMENT_MAP_NODE_COLUMNS + sync_to_supabase.DOCUMENT_MAP_CONTEXT_COLUMNS)
    expected_claim_keys = set(sync_to_supabase.DOCUMENT_MAP_CLAIM_COLUMNS + sync_to_supabase.DOCUMENT_MAP_CONTEXT_COLUMNS)

    assert node_payloads
    assert claim_payloads
    assert set(node_payloads[0]) == expected_node_keys
    assert set(claim_payloads[0]) == expected_claim_keys
    assert node_payloads[0]["knowledge_title"] == "Remote Map Resolver Entry"
    assert claim_payloads[0]["knowledge_source"] == "raw/remote-map.md"


def test_document_map_sync_columns_match_sqlite_schema(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        node_columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(knowledge_nodes)")}
        claim_columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(knowledge_claims)")}
        knowledge_columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(knowledge)")}
    finally:
        db.close()

    assert set(sync_to_supabase.DOCUMENT_MAP_NODE_COLUMNS) == node_columns - {"id"}
    assert set(sync_to_supabase.DOCUMENT_MAP_CLAIM_COLUMNS) == claim_columns - {"id"}
    assert {"title", "source", "content_hash"}.issubset(knowledge_columns)
    assert sync_to_supabase.DOCUMENT_MAP_CONTEXT_COLUMNS == [
        "knowledge_title",
        "knowledge_source",
        "knowledge_content_hash",
    ]


def test_sync_cli_help_exposes_document_map_flag():
    result = subprocess.run(
        [sys.executable, "scripts/sync_to_supabase.py", "--help"],
        cwd=Path(__file__).parent.parent,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--document-map" in result.stdout
