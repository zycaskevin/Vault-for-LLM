"""Document Map schema tests for GuardrailsDB."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guardrails_lite.guardrails_db import GuardrailsDB


EXPECTED_SCHEMA_VERSION = "5"


KNOWLEDGE_NODES_COLUMNS = {
    "id": {"type": "INTEGER", "pk": 1},
    "knowledge_id": {"type": "INTEGER", "notnull": 1},
    "node_uid": {"type": "TEXT", "notnull": 1},
    "parent_uid": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "level": {"type": "INTEGER", "notnull": 1, "dflt_value": "0"},
    "heading": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "path": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "summary": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "line_start": {"type": "INTEGER", "notnull": 1},
    "line_end": {"type": "INTEGER", "notnull": 1},
    "token_estimate": {"type": "INTEGER", "notnull": 1, "dflt_value": "0"},
    "content_hash": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "created_at": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "updated_at": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
}


KNOWLEDGE_CLAIMS_COLUMNS = {
    "id": {"type": "INTEGER", "pk": 1},
    "knowledge_id": {"type": "INTEGER", "notnull": 1},
    "node_uid": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "claim_uid": {"type": "TEXT", "notnull": 1},
    "claim": {"type": "TEXT", "notnull": 1},
    "claim_type": {"type": "TEXT", "notnull": 1, "dflt_value": "'claim'"},
    "line_start": {"type": "INTEGER", "notnull": 1, "dflt_value": "0"},
    "line_end": {"type": "INTEGER", "notnull": 1, "dflt_value": "0"},
    "confidence": {"type": "REAL", "notnull": 1, "dflt_value": "0.7"},
    "source": {"type": "TEXT", "notnull": 1, "dflt_value": "'aaak'"},
    "content_hash": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "created_at": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
    "updated_at": {"type": "TEXT", "notnull": 1, "dflt_value": "''"},
}


def _columns(db: GuardrailsDB, table: str) -> dict[str, dict]:
    return {row["name"]: dict(row) for row in db.conn.execute(f"PRAGMA table_info({table})")}


def _index_columns(db: GuardrailsDB, index_name: str) -> list[str]:
    return [row["name"] for row in db.conn.execute(f"PRAGMA index_info({index_name})")]


def _indexes(db: GuardrailsDB, table: str) -> dict[str, dict]:
    indexes = {}
    for row in db.conn.execute(f"PRAGMA index_list({table})"):
        index = dict(row)
        index["columns"] = _index_columns(db, index["name"])
        indexes[index["name"]] = index
    return indexes


def _foreign_keys(db: GuardrailsDB, table: str) -> list[dict]:
    return [dict(row) for row in db.conn.execute(f"PRAGMA foreign_key_list({table})")]


def _assert_columns(table_columns: dict[str, dict], expected: dict[str, dict]) -> None:
    assert set(expected).issubset(table_columns.keys())
    for column_name, expected_attrs in expected.items():
        actual = table_columns[column_name]
        for attr, expected_value in expected_attrs.items():
            assert actual[attr] == expected_value, f"{column_name}.{attr}"


def _assert_foreign_key_to_knowledge(db: GuardrailsDB, table: str) -> None:
    foreign_keys = _foreign_keys(db, table)
    assert any(
        fk["from"] == "knowledge_id" and fk["table"] == "knowledge" and fk["to"] == "id"
        for fk in foreign_keys
    )


def _assert_index(db: GuardrailsDB, table: str, index_name: str, columns: list[str]) -> None:
    indexes = _indexes(db, table)
    assert index_name in indexes
    assert indexes[index_name]["columns"] == columns
    assert indexes[index_name]["unique"] == 0


def _assert_unique_index(db: GuardrailsDB, table: str, columns: list[str]) -> None:
    indexes = _indexes(db, table)
    assert any(index["unique"] == 1 and index["columns"] == columns for index in indexes.values())


def _parse_sections(content: str):
    from guardrails_lite.guardrails_map import parse_markdown_sections

    return parse_markdown_sections(content)


def _parse_claims(content_aaak: str):
    from guardrails_lite.guardrails_map import parse_aaak_claims

    return parse_aaak_claims(content_aaak)


def _hash_slice(content: str, line_start: int, line_end: int) -> str:
    lines = content.splitlines()
    section_text = "\n".join(lines[line_start - 1 : line_end])
    return hashlib.sha256(section_text.encode()).hexdigest()


def _nodes_as_dicts(content: str) -> list[dict]:
    return [node.__dict__ for node in _parse_sections(content)]


def _claims_as_dicts(content_aaak: str) -> list[dict]:
    return [claim.__dict__ for claim in _parse_claims(content_aaak)]


def test_document_map_tables_are_created_for_new_db(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        tables = {
            row["name"]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
                ("knowledge_nodes", "knowledge_claims"),
            )
        }
        assert tables == {"knowledge_nodes", "knowledge_claims"}
    finally:
        db.close()


def test_document_map_columns_and_constraints(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        _assert_columns(_columns(db, "knowledge_nodes"), KNOWLEDGE_NODES_COLUMNS)
        _assert_columns(_columns(db, "knowledge_claims"), KNOWLEDGE_CLAIMS_COLUMNS)
        _assert_foreign_key_to_knowledge(db, "knowledge_nodes")
        _assert_foreign_key_to_knowledge(db, "knowledge_claims")
    finally:
        db.close()


def test_document_map_indexes_exist(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        _assert_index(db, "knowledge_nodes", "idx_knowledge_nodes_knowledge_id", ["knowledge_id"])
        _assert_index(db, "knowledge_nodes", "idx_knowledge_nodes_node_uid", ["node_uid"])
        _assert_index(db, "knowledge_nodes", "idx_knowledge_nodes_path", ["path"])
        _assert_unique_index(db, "knowledge_nodes", ["knowledge_id", "node_uid"])

        _assert_index(db, "knowledge_claims", "idx_knowledge_claims_knowledge_id", ["knowledge_id"])
        _assert_index(db, "knowledge_claims", "idx_knowledge_claims_node_uid", ["node_uid"])
        _assert_index(db, "knowledge_claims", "idx_knowledge_claims_claim_type", ["claim_type"])
        _assert_unique_index(db, "knowledge_claims", ["knowledge_id", "claim_uid"])
    finally:
        db.close()


def test_document_map_schema_init_is_idempotent(tmp_path):
    db_path = tmp_path / "guardrails.db"

    GuardrailsDB(db_path).connect().close()
    GuardrailsDB(db_path).connect().close()

    db = GuardrailsDB(db_path).connect()
    try:
        assert "knowledge_nodes" in {row["name"] for row in db.conn.execute("PRAGMA table_list")}
        assert "knowledge_claims" in {row["name"] for row in db.conn.execute("PRAGMA table_list")}
        assert db.get_config("schema_version", "0") == EXPECTED_SCHEMA_VERSION
    finally:
        db.close()


def test_document_map_migrates_existing_partial_tables_idempotently(tmp_path):
    import sqlite3

    db_path = tmp_path / "guardrails.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                layer TEXT NOT NULL DEFAULT 'L3',
                category TEXT NOT NULL DEFAULT 'general',
                tags TEXT NOT NULL DEFAULT '',
                trust REAL NOT NULL DEFAULT 0.5,
                content_raw TEXT NOT NULL DEFAULT '',
                content_aaak TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE knowledge_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id INTEGER NOT NULL,
                node_uid TEXT NOT NULL,
                heading TEXT NOT NULL DEFAULT '',
                level INTEGER NOT NULL DEFAULT 0,
                parent_uid TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                content_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id),
                UNIQUE(knowledge_id, node_uid)
            );
            CREATE TABLE knowledge_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id INTEGER NOT NULL,
                node_uid TEXT NOT NULL DEFAULT '',
                claim TEXT NOT NULL,
                claim_type TEXT NOT NULL DEFAULT 'claim',
                line_start INTEGER NOT NULL DEFAULT 0,
                line_end INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'aaak',
                content_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id),
                UNIQUE(knowledge_id, node_uid, claim)
            );
            INSERT INTO knowledge (title, content_raw) VALUES ('Doc', '# Title\nBody');
            INSERT INTO knowledge_nodes
                (knowledge_id, node_uid, heading, level, parent_uid, path,
                 line_start, line_end, content_hash, created_at, updated_at)
                VALUES (1, 'title-1', 'Title', 1, '', 'Title', 1, 2, 'h', '', '');
            INSERT INTO knowledge_claims
                (knowledge_id, node_uid, claim, claim_type, line_start, line_end,
                 source, content_hash, created_at, updated_at)
                VALUES
                (1, 'title-1', 'First claim.', 'claim', 2, 2, 'aaak', '', '', ''),
                (1, 'title-1', 'Second claim.', 'claim', 2, 2, 'aaak', '', '', '');
            """
        )
        conn.commit()
    finally:
        conn.close()

    GuardrailsDB(db_path).connect().close()
    GuardrailsDB(db_path).connect().close()

    db = GuardrailsDB(db_path).connect()
    try:
        _assert_columns(_columns(db, "knowledge_nodes"), KNOWLEDGE_NODES_COLUMNS)
        _assert_columns(_columns(db, "knowledge_claims"), KNOWLEDGE_CLAIMS_COLUMNS)
        _assert_unique_index(db, "knowledge_claims", ["knowledge_id", "claim_uid"])
        migrated_node = db.conn.execute(
            "SELECT summary, token_estimate FROM knowledge_nodes WHERE knowledge_id=1"
        ).fetchone()
        assert dict(migrated_node) == {"summary": "", "token_estimate": 0}
        claim_rows = [
            dict(row)
            for row in db.conn.execute(
                """SELECT claim_uid, confidence FROM knowledge_claims
                   WHERE knowledge_id=1 ORDER BY claim"""
            )
        ]
        assert len({row["claim_uid"] for row in claim_rows}) == 2
        assert all(row["claim_uid"] for row in claim_rows)
        assert all(row["confidence"] == 0.7 for row in claim_rows)
        assert db.get_config("schema_version", "0") == EXPECTED_SCHEMA_VERSION
    finally:
        db.close()


def test_parse_markdown_sections_returns_root_node_when_no_headings():
    content = "plain text\nstill root"

    nodes = _nodes_as_dicts(content)

    assert nodes == [
        {
            "node_uid": "root-1",
            "heading": "root",
            "level": 0,
            "parent_uid": "",
            "path": "root",
            "line_start": 1,
            "line_end": 2,
            "content_hash": _hash_slice(content, 1, 2),
        }
    ]


def test_parse_markdown_sections_tracks_h1_h2_h3_nesting_and_line_ranges():
    content = "\n".join(
        [
            "# Title",
            "Intro text",
            "## API",
            "API intro",
            "### Auth",
            "Auth details",
            "## Usage",
            "Usage details",
            "# Appendix",
            "Appendix text",
        ]
    )

    nodes = _nodes_as_dicts(content)

    assert nodes == [
        {
            "node_uid": "title-1",
            "heading": "Title",
            "level": 1,
            "parent_uid": "",
            "path": "Title",
            "line_start": 1,
            "line_end": 8,
            "content_hash": _hash_slice(content, 1, 8),
        },
        {
            "node_uid": "api-3",
            "heading": "API",
            "level": 2,
            "parent_uid": "title-1",
            "path": "Title/API",
            "line_start": 3,
            "line_end": 6,
            "content_hash": _hash_slice(content, 3, 6),
        },
        {
            "node_uid": "auth-5",
            "heading": "Auth",
            "level": 3,
            "parent_uid": "api-3",
            "path": "Title/API/Auth",
            "line_start": 5,
            "line_end": 6,
            "content_hash": _hash_slice(content, 5, 6),
        },
        {
            "node_uid": "usage-7",
            "heading": "Usage",
            "level": 2,
            "parent_uid": "title-1",
            "path": "Title/Usage",
            "line_start": 7,
            "line_end": 8,
            "content_hash": _hash_slice(content, 7, 8),
        },
        {
            "node_uid": "appendix-9",
            "heading": "Appendix",
            "level": 1,
            "parent_uid": "",
            "path": "Appendix",
            "line_start": 9,
            "line_end": 10,
            "content_hash": _hash_slice(content, 9, 10),
        },
    ]


def test_parse_markdown_sections_duplicate_headings_get_line_number_uids():
    content = "# Intro\nfirst\n# Intro\nsecond"

    nodes = _nodes_as_dicts(content)

    assert [node["node_uid"] for node in nodes] == ["intro-1", "intro-3"]
    assert [node["path"] for node in nodes] == ["Intro", "Intro"]


def test_parse_markdown_sections_non_h1_first_heading_has_no_parent_but_valid_path():
    content = "## API\nbody\n### Auth\ndetails"

    nodes = _nodes_as_dicts(content)

    assert nodes[0]["node_uid"] == "api-1"
    assert nodes[0]["parent_uid"] == ""
    assert nodes[0]["path"] == "API"
    assert nodes[0]["line_end"] == 4
    assert nodes[1]["node_uid"] == "auth-3"
    assert nodes[1]["parent_uid"] == "api-1"
    assert nodes[1]["path"] == "API/Auth"


def test_parse_markdown_sections_cjk_heading_slug_does_not_become_empty():
    content = "# 章節標題\n內容"

    nodes = _nodes_as_dicts(content)

    assert nodes[0]["node_uid"] == "章節標題-1"
    assert nodes[0]["heading"] == "章節標題"
    assert nodes[0]["path"] == "章節標題"


def test_parse_markdown_sections_counts_frontmatter_and_leading_lines():
    content = "---\ntitle: Doc\n---\n\n# Title ###\nbody"

    nodes = _nodes_as_dicts(content)

    assert nodes == [
        {
            "node_uid": "title-5",
            "heading": "Title",
            "level": 1,
            "parent_uid": "",
            "path": "Title",
            "line_start": 5,
            "line_end": 6,
            "content_hash": _hash_slice(content, 5, 6),
        }
    ]


def test_parse_aaak_claims_empty_or_missing_claims_returns_empty():
    assert _claims_as_dicts("") == []
    assert _claims_as_dicts("TITLE:Doc\n- [C1] Not in claims section (L1)") == []


def test_parse_aaak_claims_parses_single_and_range_spans():
    aaak = "\n".join(
        [
            "TITLE:Doc",
            "CLAIMS:",
            "- [C1] Single line claim. (L12)",
            "- [C2] Range claim. (L12-L14)",
            "- [C3] Generator range claim. (L20-22)",
        ]
    )

    claims = _claims_as_dicts(aaak)

    assert [claim["claim_id"] for claim in claims] == ["C1", "C2", "C3"]
    assert [claim["claim"] for claim in claims] == [
        "Single line claim.",
        "Range claim.",
        "Generator range claim.",
    ]
    assert [(claim["line_start"], claim["line_end"]) for claim in claims] == [
        (12, 12),
        (12, 14),
        (20, 22),
    ]
    assert all(claim["source"] == "aaak" for claim in claims)
    assert claims[0]["content_hash"] == hashlib.sha256("Single line claim.".encode()).hexdigest()


def test_parse_aaak_claims_preserves_parentheses_inside_claim_text():
    aaak = "TITLE:Doc\nCLAIMS:\n- [C1] Keep foo(bar) and (important) text. (L7)"

    claims = _claims_as_dicts(aaak)

    assert claims[0]["claim"] == "Keep foo(bar) and (important) text."
    assert claims[0]["line_start"] == 7
    assert claims[0]["line_end"] == 7


def test_parse_aaak_claims_skips_malformed_and_truncated_lines():
    aaak = "\n".join(
        [
            "TITLE:Doc",
            "CLAIMS:",
            "- [C1] Good claim. (L1)",
            "- [C2] Truncated span. (L",
            "- [C3] Truncated text /ven",
            "- Non-claim AAAK bullet follows",
            "- [C4] Later valid claim. (L3-L5)",
        ]
    )

    claims = _claims_as_dicts(aaak)

    assert [claim["claim_id"] for claim in claims] == ["C1", "C4"]
    assert [claim["claim"] for claim in claims] == ["Good claim.", "Later valid claim."]


def test_assign_claim_node_uid_prefers_deepest_narrowest_node():
    from guardrails_lite.guardrails_map import assign_claim_node_uid

    nodes = _parse_sections(
        "\n".join(
            [
                "# Title",
                "Intro",
                "## API",
                "API intro",
                "### Auth",
                "Auth details",
                "## Usage",
                "Usage details",
            ]
        )
    )

    assert assign_claim_node_uid(nodes, 6) == "auth-5"
    assert assign_claim_node_uid(nodes, 8) == "usage-7"
    assert assign_claim_node_uid(nodes, 99) == ""


def test_build_document_map_for_entry_backfills_nodes_and_claims_idempotently(tmp_path):
    from guardrails_lite.guardrails_map import build_document_map_for_entry

    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        raw = "\n".join(
            [
                "# Title",
                "Intro",
                "## API",
                "API intro",
                "### Auth",
                "Auth details",
            ]
        )
        aaak = "\n".join(
            [
                "TITLE:Doc",
                "CLAIMS:",
                "- [C1] Top claim. (L2)",
                "- [C2] Auth claim. (L6)",
                "- [C3] Orphan claim. (L99)",
            ]
        )
        knowledge_id = db.add_knowledge("Doc", raw, content_aaak=aaak)
        db.conn.execute(
            """INSERT INTO knowledge_nodes
               (knowledge_id, node_uid, heading, level, parent_uid, path,
                summary, line_start, line_end, token_estimate,
                content_hash, created_at, updated_at)
               VALUES (?, 'stale', 'stale', 1, '', 'stale', '', 1, 1, 0, '', '', '')""",
            (knowledge_id,),
        )
        db.conn.execute(
            """INSERT INTO knowledge_claims
               (knowledge_id, node_uid, claim_uid, claim, claim_type, line_start,
                line_end, confidence, source, content_hash, created_at, updated_at)
               VALUES (?, 'stale', 'stale-1', 'stale claim', 'claim', 1, 1, 0.7, 'aaak', '', '', '')""",
            (knowledge_id,),
        )
        db.conn.commit()

        first = build_document_map_for_entry(db.conn, knowledge_id)
        second = build_document_map_for_entry(db.conn, knowledge_id)

        assert first == {"nodes": 3, "claims": 3}
        assert second == {"nodes": 3, "claims": 3}
        assert db.conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_nodes WHERE knowledge_id=?", (knowledge_id,)
        ).fetchone()["c"] == 3
        assert db.conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_claims WHERE knowledge_id=?", (knowledge_id,)
        ).fetchone()["c"] == 3

        node_rows = [
            dict(row)
            for row in db.conn.execute(
                """SELECT node_uid, summary, token_estimate
                   FROM knowledge_nodes
                   WHERE knowledge_id=?
                   ORDER BY line_start""",
                (knowledge_id,),
            )
        ]
        assert node_rows == [
            {"node_uid": "title-1", "summary": "Intro", "token_estimate": 6},
            {"node_uid": "api-3", "summary": "API intro", "token_estimate": 4},
            {"node_uid": "auth-5", "summary": "Auth details", "token_estimate": 2},
        ]

        claim_rows = [
            dict(row)
            for row in db.conn.execute(
                """SELECT node_uid, claim_uid, claim, line_start, line_end,
                          confidence, source, claim_type
                   FROM knowledge_claims
                   WHERE knowledge_id=?
                   ORDER BY claim""",
                (knowledge_id,),
            )
        ]
        assert claim_rows == [
            {
                "node_uid": "auth-5",
                "claim_uid": "c-6-df793572a45fb7d8",
                "claim": "Auth claim.",
                "line_start": 6,
                "line_end": 6,
                "confidence": 0.7,
                "source": "aaak",
                "claim_type": "claim",
            },
            {
                "node_uid": "",
                "claim_uid": "c-99-e34b3f72eea6229f",
                "claim": "Orphan claim.",
                "line_start": 99,
                "line_end": 99,
                "confidence": 0.7,
                "source": "aaak",
                "claim_type": "claim",
            },
            {
                "node_uid": "title-1",
                "claim_uid": "c-2-b3d946311d9f923e",
                "claim": "Top claim.",
                "line_start": 2,
                "line_end": 2,
                "confidence": 0.7,
                "source": "aaak",
                "claim_type": "claim",
            },
        ]
    finally:
        db.close()


def test_build_document_map_for_entry_raises_for_missing_knowledge_id(tmp_path):
    from guardrails_lite.guardrails_map import build_document_map_for_entry

    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        try:
            build_document_map_for_entry(db.conn, 999)
        except ValueError as exc:
            assert "Knowledge id not found" in str(exc)
        else:
            raise AssertionError("expected ValueError")
    finally:
        db.close()
