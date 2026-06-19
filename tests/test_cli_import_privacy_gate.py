"""Privacy gate regressions for direct CLI add/import ingestion."""

from __future__ import annotations

from argparse import Namespace

import pytest


def _secret_text() -> str:
    return "Do not ingest api_key=" + "A" * 24


def test_cmd_add_blocks_secret_like_content_before_db_write(tmp_path, monkeypatch):
    from vault.cli import cmd_add, cmd_init
    from vault.db import VaultDB

    monkeypatch.chdir(tmp_path)
    cmd_init(Namespace(project_dir="."))

    args = Namespace(
        title="Blocked secret",
        content=_secret_text(),
        file=None,
        layer="L3",
        category="general",
        tags="",
        trust=0.5,
        allow_private=False,
    )
    with pytest.raises(SystemExit) as exc:
        cmd_add(args)

    assert exc.value.code == 2
    with VaultDB(tmp_path / "vault.db") as db:
        row = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()
        assert row["count"] == 0


def test_import_document_blocks_secret_like_content_by_default(tmp_path):
    from vault.db import VaultDB
    from vault.importer import import_document

    source = tmp_path / "secret.md"
    source.write_text(_secret_text(), encoding="utf-8")
    with VaultDB(tmp_path / "vault.db") as db:
        with pytest.raises(ValueError, match="privacy gate blocked import"):
            import_document(source, db, strategy="sliding")

        row = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()
        assert row["count"] == 0


def test_import_document_allow_private_keeps_explicit_local_escape_hatch(tmp_path):
    from vault.db import VaultDB
    from vault.importer import import_document

    source = tmp_path / "secret.md"
    source.write_text(_secret_text(), encoding="utf-8")
    with VaultDB(tmp_path / "vault.db") as db:
        ids = import_document(source, db, strategy="sliding", allow_private=True)

        assert ids
        row = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()
        assert row["count"] == len(ids)
