import pytest

from vault.db import VaultDB
from vault.db_fts import quote_fts_token, search_fts_keyword


def test_quote_fts_token_escapes_quotes_and_clamps_length():
    token = 'alpha"beta' + ("x" * 120)

    quoted = quote_fts_token(token)

    assert quoted.startswith('"alpha""beta')
    assert quoted.endswith('"')
    assert len(quoted[1:-1].replace('""', '"')) == 100


def test_fts_helper_raises_when_unavailable(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        with pytest.raises(RuntimeError, match="全文搜尋功能未啟用"):
            search_fts_keyword(db.conn, fts_available=False, terms=["anything"])
    finally:
        db.close()


def test_fts_helper_filters_empty_terms_and_respects_limit(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        first_id = db.add_knowledge(title="Alpha Beta", content_raw="alpha beta", trust=0.9)
        db.add_knowledge(title="Alpha Gamma", content_raw="alpha gamma", trust=0.8)

        rows = db.search_fts_keyword(["", "alpha"], limit=1)
        assert [row["id"] for row in rows] == [first_id]
        assert db.search_fts_keyword([""]) == []
    finally:
        db.close()
