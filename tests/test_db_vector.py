import sqlite3

import pytest

from vault.db_vector import add_embedding, parse_embedding_dim, search_vector


def test_parse_embedding_dim_uses_safe_default_for_invalid_values():
    assert parse_embedding_dim("384") == 384
    assert parse_embedding_dim("63") == 384
    assert parse_embedding_dim("4097") == 384
    assert parse_embedding_dim("not-a-number") == 384


def test_vector_helpers_fail_closed_when_vec_is_unavailable():
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(RuntimeError, match="向量功能未啟用"):
            add_embedding(conn, vec_available=False, knowledge_id=1, embedding=[0.0] * 384)

        with pytest.raises(RuntimeError, match="向量搜尋功能未啟用"):
            search_vector(
                conn,
                vec_available=False,
                embedding_dim="384",
                query_embedding=[0.0] * 384,
            )
    finally:
        conn.close()
