"""CLI tests for Vault Document Map commands."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.cli import main


RAW_CONTENT = "\n".join(
    [
        "# Title",
        "intro",
        "## Tool-gated Reading",
        "detail line",
        "## Other Section",
        "other detail",
    ]
)

AAAK_CONTENT = "\n".join(
    [
        "TITLE: Example",
        "CLAIMS:",
        "- [C1] Tool-gated reading keeps agents from reading whole documents. (L3-L4)",
    ]
)


def _create_project_with_entry(
    tmp_path,
    monkeypatch,
    *,
    title="Example",
    content_raw=RAW_CONTENT,
    content_aaak=AAAK_CONTENT,
):
    monkeypatch.chdir(tmp_path)
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        knowledge_id = db.add_knowledge(
            title,
            content_raw,
            content_aaak=content_aaak,
            layer="L3",
            category="technique",
        )
    finally:
        db.close()
    return knowledge_id


def _run_cli(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["vault", *args])
    main()


def test_map_build_one_entry_creates_nodes_and_claims(tmp_path, monkeypatch, capsys):
    knowledge_id = _create_project_with_entry(tmp_path, monkeypatch)

    _run_cli(monkeypatch, "map", "build", str(knowledge_id))

    out = capsys.readouterr().out.lower()
    assert "built" in out
    assert "nodes" in out
    assert "claims" in out

    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        node_count = db.conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_nodes WHERE knowledge_id=?",
            (knowledge_id,),
        ).fetchone()["c"]
        claim_count = db.conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_claims WHERE knowledge_id=?",
            (knowledge_id,),
        ).fetchone()["c"]
    finally:
        db.close()

    assert node_count == 3
    assert claim_count == 1


def test_map_build_without_id_creates_nodes_and_claims_for_all_entries(tmp_path, monkeypatch, capsys):
    first_id = _create_project_with_entry(tmp_path, monkeypatch, title="First Entry")
    second_id = _create_project_with_entry(tmp_path, monkeypatch, title="Second Entry")

    _run_cli(monkeypatch, "map", "build")

    out = capsys.readouterr().out.lower()
    assert "built 2 entries" in out

    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        for knowledge_id in (first_id, second_id):
            node_count = db.conn.execute(
                "SELECT COUNT(*) AS c FROM knowledge_nodes WHERE knowledge_id=?",
                (knowledge_id,),
            ).fetchone()["c"]
            claim_count = db.conn.execute(
                "SELECT COUNT(*) AS c FROM knowledge_claims WHERE knowledge_id=?",
                (knowledge_id,),
            ).fetchone()["c"]
            assert node_count == 3
            assert claim_count == 1
    finally:
        db.close()


def test_map_build_missing_id_prints_friendly_message(tmp_path, monkeypatch, capsys):
    _create_project_with_entry(tmp_path, monkeypatch)

    _run_cli(monkeypatch, "map", "build", "999")

    out = capsys.readouterr().out
    assert "Knowledge id not found: 999" in out


def test_map_show_prints_title_structure_paths_and_line_ranges(tmp_path, monkeypatch, capsys):
    knowledge_id = _create_project_with_entry(tmp_path, monkeypatch)
    _run_cli(monkeypatch, "map", "build", str(knowledge_id))
    capsys.readouterr()

    _run_cli(monkeypatch, "map", "show", str(knowledge_id))

    out = capsys.readouterr().out
    assert f"#{knowledge_id} Example" in out
    assert "Title" in out
    assert "Title/Tool-gated Reading" in out
    assert "Title/Other Section" in out
    assert "L1-L6" in out
    assert "L3-L4" in out


def test_map_build_deduplicates_repeated_claims_in_same_node(tmp_path, monkeypatch):
    duplicate_aaak = "\n".join(
        [
            "TITLE: Duplicate Example",
            "CLAIMS:",
            "- [C1] Repeated claim should be stored only once. (L3)",
            "- [C2] Repeated claim should be stored only once. (L4)",
        ]
    )
    knowledge_id = _create_project_with_entry(
        tmp_path,
        monkeypatch,
        title="Duplicate Example",
        content_aaak=duplicate_aaak,
    )

    _run_cli(monkeypatch, "map", "build", str(knowledge_id))

    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        claim_count = db.conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_claims WHERE knowledge_id=?",
            (knowledge_id,),
        ).fetchone()["c"]
    finally:
        db.close()

    assert claim_count == 1


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("map", "show", "1"), "vault.db"),
        (("map", "read", "1", "--lines", "1-1"), "vault.db"),
        (("map", "query", "anything"), "vault.db"),
    ],
)
def test_map_read_only_commands_do_not_create_missing_database(
    tmp_path, monkeypatch, capsys, args, expected
):
    monkeypatch.chdir(tmp_path)

    _run_cli(monkeypatch, *args)

    out = capsys.readouterr().out
    assert expected in out
    assert "not found" in out.lower()
    assert not (tmp_path / "vault.db").exists()


@pytest.mark.parametrize(
    "args",
    [
        ("map", "show", "1"),
        ("map", "read", "1", "--lines", "1-1"),
        ("map", "query", "tool-gated"),
    ],
)
def test_map_read_only_commands_do_not_use_vaultdb_connect(
    tmp_path, monkeypatch, capsys, args
):
    knowledge_id = _create_project_with_entry(tmp_path, monkeypatch)
    _run_cli(monkeypatch, "map", "build", str(knowledge_id))
    capsys.readouterr()

    def fail_connect(self):  # pragma: no cover - failure path asserted by test
        raise AssertionError("read-only map commands must not initialize DB")

    monkeypatch.setattr(VaultDB, "connect", fail_connect)

    _run_cli(monkeypatch, *args)

    out = capsys.readouterr().out
    assert "read-only map commands must not initialize DB" not in out


def test_map_show_without_nodes_suggests_build(tmp_path, monkeypatch, capsys):
    knowledge_id = _create_project_with_entry(tmp_path, monkeypatch)

    _run_cli(monkeypatch, "map", "show", str(knowledge_id))

    out = capsys.readouterr().out
    assert "No document map nodes" in out
    assert f"vault map build {knowledge_id}" in out


def test_map_read_prints_clamped_range_with_citation(tmp_path, monkeypatch, capsys):
    knowledge_id = _create_project_with_entry(tmp_path, monkeypatch)

    _run_cli(monkeypatch, "map", "read", str(knowledge_id), "--lines", "2-99")

    out = capsys.readouterr().out
    assert "#" + str(knowledge_id) + " Example L2-L6" in out
    assert "2|intro" in out
    assert "3|## Tool-gated Reading" in out
    assert "6|other detail" in out
    assert "99|" not in out


def test_map_query_finds_claim_and_prints_location(tmp_path, monkeypatch, capsys):
    knowledge_id = _create_project_with_entry(tmp_path, monkeypatch)
    _run_cli(monkeypatch, "map", "build", str(knowledge_id))
    capsys.readouterr()

    _run_cli(monkeypatch, "map", "query", "tool-gated reading")

    out = capsys.readouterr().out
    assert f"#{knowledge_id} Example" in out
    assert "Tool-gated reading keeps agents from reading whole documents." in out
    assert "L3-L4" in out
    assert "Title/Tool-gated Reading" in out


def test_map_query_matches_title_and_path_without_claim_text(tmp_path, monkeypatch, capsys):
    raw_content = "\n".join(
        [
            "# Root",
            "intro",
            "## Path Only Marker",
            "neutral detail",
        ]
    )
    aaak_content = "\n".join(
        [
            "TITLE: Unique Query Title",
            "CLAIMS:",
            "- [C1] A neutral note. (L4)",
        ]
    )
    knowledge_id = _create_project_with_entry(
        tmp_path,
        monkeypatch,
        title="Unique Query Title",
        content_raw=raw_content,
        content_aaak=aaak_content,
    )
    _run_cli(monkeypatch, "map", "build", str(knowledge_id))
    capsys.readouterr()

    _run_cli(monkeypatch, "map", "query", "Unique Query Title")
    title_out = capsys.readouterr().out
    assert f"#{knowledge_id} Unique Query Title" in title_out
    assert "A neutral note." in title_out

    _run_cli(monkeypatch, "map", "query", "Path Only Marker")
    path_out = capsys.readouterr().out
    assert "Root/Path Only Marker" in path_out
    assert "A neutral note." in path_out


def test_map_query_limit_must_be_positive(tmp_path, monkeypatch, capsys):
    _create_project_with_entry(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        _run_cli(monkeypatch, "map", "query", "anything", "--limit", "0")

    assert excinfo.value.code == 2
    assert "positive" in capsys.readouterr().err.lower()


def test_map_query_limit_one_constrains_result_count(tmp_path, monkeypatch, capsys):
    first_id = _create_project_with_entry(tmp_path, monkeypatch, title="First Match")
    _create_project_with_entry(tmp_path, monkeypatch, title="Second Match")
    _run_cli(monkeypatch, "map", "build")
    capsys.readouterr()

    _run_cli(monkeypatch, "map", "query", "Tool-gated reading", "--limit", "1")

    out = capsys.readouterr().out
    result_headers = [line for line in out.splitlines() if line.startswith("#")]
    assert result_headers == [
        f"#{first_id} First Match L3-L4 Title/Tool-gated Reading [tool-gated-reading-3]"
    ]
