"""Deterministic semantic-index plumbing tests."""

from __future__ import annotations

import json
from pathlib import Path

from vault.db import VaultDB
from vault.semantic import (
    DeterministicHashEmbeddingProvider,
    rebuild_semantic_index,
    search_semantic_index,
    semantic_index_counts,
)


RAW_V1 = "\n".join(
    [
        "# Semantic Index Guide",
        "Intro",
        "## Claim Search",
        "Claim-level vectors preserve line ranges for citations.",
    ]
)
AAAK_V1 = "\n".join(
    [
        "TITLE: Semantic Index Guide",
        "CLAIMS:",
        "- [C1] Claim-level vectors preserve line ranges for citations. (L4)",
    ]
)

RAW_V2 = "\n".join(
    [
        "# Semantic Index Guide",
        "Intro",
        "## Node Search",
        "Node vectors should replace stale claim vectors after rebuild.",
    ]
)
AAAK_V2 = "\n".join(
    [
        "TITLE: Semantic Index Guide",
        "CLAIMS:",
        "- [C1] Node vectors replace stale semantic rows after rebuild. (L4)",
        "- [C2] Deterministic hash embeddings are public-safe test doubles. (L4)",
    ]
)


def test_deterministic_hash_provider_is_stable_and_non_semantic():
    provider = DeterministicHashEmbeddingProvider(dim=8)

    first = provider.encode("same text")[0]
    second = provider.encode("same text")[0]

    assert first == second
    assert len(first) == 8
    assert provider.provider_id == "hash-deterministic-v1"
    assert provider.is_semantic is False


def test_rebuild_semantic_index_creates_node_and_claim_vectors(tmp_path: Path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        knowledge_id = db.add_knowledge(
            "Semantic Index Guide",
            RAW_V1,
            content_aaak=AAAK_V1,
            category="search",
            tags="semantic,index,claim",
            trust=0.9,
        )

        stats = rebuild_semantic_index(db, DeterministicHashEmbeddingProvider(dim=8))
        counts = semantic_index_counts(db)

        assert stats.knowledge_rows == 1
        assert stats.node_vectors == 2
        assert stats.claim_vectors == 1
        assert counts == {"claim": 1, "node": 2}

        rows = db.conn.execute(
            "SELECT vector_kind, item_uid, vector, line_start, line_end FROM semantic_vectors ORDER BY vector_kind, item_uid"
        ).fetchall()
        assert {row["vector_kind"] for row in rows} == {"node", "claim"}
        assert all(len(json.loads(row["vector"])) == 8 for row in rows)
        assert any(row["line_start"] == 4 and row["line_end"] == 4 for row in rows)
        assert db.get_knowledge(knowledge_id)["title"] == "Semantic Index Guide"
    finally:
        db.close()


def test_rebuild_semantic_index_removes_stale_vectors_after_update(tmp_path: Path):
    db = VaultDB(tmp_path / "vault.db").connect()
    provider = DeterministicHashEmbeddingProvider(dim=8)
    try:
        knowledge_id = db.add_knowledge(
            "Semantic Index Guide",
            RAW_V1,
            content_aaak=AAAK_V1,
            category="search",
            tags="semantic,index,claim",
            trust=0.9,
        )
        rebuild_semantic_index(db, provider, knowledge_id=knowledge_id)

        db.update_knowledge(knowledge_id, content_raw=RAW_V2, content_aaak=AAAK_V2)
        stats = rebuild_semantic_index(db, provider, knowledge_id=knowledge_id)

        assert stats.node_vectors == 2
        assert stats.claim_vectors == 2
        rows = db.conn.execute(
            "SELECT source_text FROM semantic_vectors WHERE vector_kind='claim' ORDER BY source_text"
        ).fetchall()
        source_texts = [row["source_text"] for row in rows]
        assert source_texts == [
            "Deterministic hash embeddings are public-safe test doubles.",
            "Node vectors replace stale semantic rows after rebuild.",
        ]
        assert all("Claim-level vectors preserve" not in text for text in source_texts)
    finally:
        db.close()


def test_semantic_index_search_preserves_citation_metadata(tmp_path: Path):
    db = VaultDB(tmp_path / "vault.db").connect()
    provider = DeterministicHashEmbeddingProvider(dim=8)
    try:
        db.add_knowledge(
            "Semantic Index Guide",
            RAW_V1,
            content_aaak=AAAK_V1,
            category="search",
            tags="semantic,index,claim",
            trust=0.9,
        )
        rebuild_semantic_index(db, provider)

        results = search_semantic_index(
            db,
            "claim vectors citation metadata",
            provider=provider,
            vector_kind="claim",
            limit=1,
        )

        assert len(results) == 1
        assert results[0]["title"] == "Semantic Index Guide"
        assert results[0]["vector_kind"] == "claim"
        assert results[0]["line_start"] == 4
        assert results[0]["line_end"] == 4
        assert results[0]["citation"] == "#1 Semantic Index Guide L4-L4"
        assert results[0]["_mode"] == "semantic_hash"
    finally:
        db.close()
