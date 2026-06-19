"""Deterministic semantic-index plumbing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import vault.semantic as semantic_module
from vault.db import VaultDB
from vault.search import VaultSearch
from vault.semantic import (
    CachedEmbeddingProvider,
    DeterministicHashEmbeddingProvider,
    SemanticProviderError,
    rebuild_semantic_index,
    rebuild_semantic_vec_index,
    search_semantic_index,
    search_semantic_index_vec,
    semantic_vec_index_is_fresh,
    semantic_index_counts,
    validate_embedding_provider,
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


def test_provider_guard_fails_closed_for_hash_when_semantic_required():
    provider = DeterministicHashEmbeddingProvider(dim=8)

    assert validate_embedding_provider(provider, allow_hash=True) is provider
    with pytest.raises(SemanticProviderError, match="not a semantic embedding provider"):
        validate_embedding_provider(provider, require_semantic=True)
    with pytest.raises(SemanticProviderError, match="hash/test provider"):
        validate_embedding_provider(provider, allow_hash=False)


class CountingEmbeddingProvider:
    def __init__(self, provider_id: str = "counting", dim: int = 4):
        self.provider_id = provider_id
        self.is_semantic = True
        self._dim = dim
        self.calls: list[list[str]] = []

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        text_list = [texts] if isinstance(texts, str) else list(texts)
        self.calls.append(text_list)
        return [[float(len(text) % 7)] * self._dim for text in text_list]


def test_cached_embedding_provider_reuses_repeated_texts_and_keeps_provider_boundary():
    first_raw = CountingEmbeddingProvider(provider_id="provider-a")
    first = CachedEmbeddingProvider(first_raw)

    assert first.encode("same") == first.encode("same")
    assert first_raw.calls == [["same"]]
    assert first.cache_size == 1

    first.encode(["same", "new"])
    assert first_raw.calls == [["same"], ["new"]]
    assert first.cache_size == 2

    second_raw = CountingEmbeddingProvider(provider_id="provider-b")
    second = CachedEmbeddingProvider(second_raw)
    second.encode("same")

    assert second_raw.calls == [["same"]]
    assert second.cache_size == 1


def test_search_semantic_index_uses_cache_wrapper_for_repeated_queries(tmp_path: Path):
    db = VaultDB(tmp_path / "vault.db").connect()
    raw_provider = CountingEmbeddingProvider(provider_id="counting-semantic", dim=4)
    cached = CachedEmbeddingProvider(raw_provider)
    try:
        db.add_knowledge(
            "Semantic Index Guide",
            RAW_V1,
            content_aaak=AAAK_V1,
            category="search",
            tags="semantic,index,claim",
            trust=0.9,
        )
        rebuild_semantic_index(db, cached, require_semantic=True)
        raw_provider.calls.clear()

        search_semantic_index(db, "repeat query", provider=cached, require_semantic=True)
        search_semantic_index(db, "repeat query", provider=cached, require_semantic=True)

        assert raw_provider.calls == [["repeat query"]]
    finally:
        db.close()


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


def test_semantic_index_search_marks_truncated_scan(tmp_path: Path, monkeypatch):
    db = VaultDB(tmp_path / "vault.db").connect()
    provider = DeterministicHashEmbeddingProvider(dim=8)
    monkeypatch.setattr(semantic_module, "SEMANTIC_MAX_SCAN_ROWS", 2)
    try:
        for idx in range(3):
            db.add_knowledge(
                f"Doc {idx}",
                f"# Doc {idx}\n\nClaim number {idx} is searchable.",
                content_aaak=f"TITLE: Doc {idx}\nCLAIMS:\n- [C1] Claim number {idx} is searchable. (L2)",
                category="search",
                trust=0.9,
            )
        rebuild_semantic_index(db, provider)

        results = search_semantic_index(
            db,
            "searchable claim",
            provider=provider,
            vector_kind="claim",
            limit=2,
        )

        assert results
        assert all(result["_semantic_scanned_rows"] == 2 for result in results)
        assert all(result["_semantic_truncated"] is True for result in results)
    finally:
        db.close()


def test_sqlite_vec_semantic_index_finds_rows_beyond_scan_cap(tmp_path: Path, monkeypatch):
    db = VaultDB(tmp_path / "vault.db").connect()
    provider = DeterministicHashEmbeddingProvider(dim=8)
    if not getattr(db, "_vec_available", False):
        db.close()
        pytest.skip("sqlite-vec extension is not available")
    monkeypatch.setattr(semantic_module, "SEMANTIC_MAX_SCAN_ROWS", 2)
    try:
        for idx in range(5):
            text = "needle sqlite vec target" if idx == 4 else f"filler claim {idx}"
            db.add_knowledge(
                f"Doc {idx}",
                f"# Doc {idx}\n\n{text}",
                content_aaak=f"TITLE: Doc {idx}\nCLAIMS:\n- [C1] {text} (L2)",
                category="search",
                trust=0.9,
            )
        rebuild_semantic_index(db, provider)
        stats = rebuild_semantic_vec_index(db, provider, vector_kind="claim")

        scan_results = search_semantic_index(
            db,
            "needle sqlite vec target",
            provider=provider,
            vector_kind="claim",
            limit=2,
        )
        vec_results = search_semantic_index_vec(
            db,
            "needle sqlite vec target",
            provider=provider,
            vector_kind="claim",
            limit=2,
        )

        assert stats.indexed_vectors == 5
        assert all(result["knowledge_id"] != 5 for result in scan_results)
        assert vec_results[0]["knowledge_id"] == 5
        assert vec_results[0]["_mode"] == "semantic_vec"
        assert vec_results[0]["_semantic_index_backend"] == "sqlite_vec"
        assert vec_results[0]["_semantic_vec_rank"] == 1
    finally:
        db.close()


def test_rebuild_semantic_index_refreshes_sqlite_vec_shadow_index(tmp_path: Path):
    db = VaultDB(tmp_path / "vault.db").connect()
    provider = DeterministicHashEmbeddingProvider(dim=8)
    if not getattr(db, "_vec_available", False):
        db.close()
        pytest.skip("sqlite-vec extension is not available")
    try:
        db.add_knowledge(
            "Semantic Vec Lifecycle",
            "# Semantic Vec Lifecycle\n\nNeedle lifecycle claim.",
            content_aaak="TITLE: Semantic Vec Lifecycle\nCLAIMS:\n- [C1] Needle lifecycle claim. (L2)",
            category="search",
            trust=0.9,
        )

        rebuild_semantic_index(db, provider)

        assert semantic_vec_index_is_fresh(db, provider, "claim") is True
        vec_results = search_semantic_index_vec(
            db,
            "Needle lifecycle claim",
            provider=provider,
            vector_kind="claim",
            limit=1,
        )
        assert vec_results
        assert vec_results[0]["_semantic_index_backend"] == "sqlite_vec"
    finally:
        db.close()


class BagOfWordsSemanticProvider:
    provider_id = "test-bow-semantic-v1"
    is_semantic = True

    def __init__(self):
        self._dim = 4

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        text_list = [texts] if isinstance(texts, str) else list(texts)
        return [self._encode_one(text) for text in text_list]

    def _encode_one(self, text: str) -> list[float]:
        tokens = set(text.lower().replace("-", " ").replace(".", " ").split())
        vehicle = {"automobile", "car", "vehicle", "garage", "maintenance"}
        cooking = {"cooking", "recipe", "kitchen", "bread"}
        vectors = [
            float(bool(tokens & vehicle)),
            float(bool(tokens & cooking)),
            float("wrench" in tokens),
            1.0,
        ]
        norm = sum(value * value for value in vectors) ** 0.5 or 1.0
        return [value / norm for value in vectors]


class FilterWindowSemanticProvider:
    provider_id = "test-filter-window-semantic-v1"
    is_semantic = True
    dim = 2

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        text_list = [texts] if isinstance(texts, str) else list(texts)
        out = []
        for text in text_list:
            lowered = text.lower()
            if "query" in lowered:
                out.append([1.0, 0.0])
            elif "target" in lowered:
                out.append([0.8, 0.2])
            else:
                out.append([0.999, 0.001])
        return out


def _build_main_search_semantic_db(tmp_path: Path, provider) -> VaultDB:
    db = VaultDB(tmp_path / "vault.db").connect()
    db.add_knowledge(
        "Workshop Notes",
        "# Workshop Notes\nGarage maintenance uses a wrench for calibration.",
        content_aaak="TITLE: Workshop Notes\nCLAIMS:\n- [C1] Garage maintenance uses a wrench for calibration. (L2)",
        category="ops",
        tags="tools",
        trust=0.91,
    )
    db.add_knowledge(
        "Sourdough Notes",
        "# Sourdough Notes\nKitchen recipe timing controls bread flavor.",
        content_aaak="TITLE: Sourdough Notes\nCLAIMS:\n- [C1] Kitchen recipe timing controls bread flavor. (L2)",
        category="food",
        tags="recipe",
        trust=0.88,
    )
    rebuild_semantic_index(db, provider, require_semantic=bool(provider.is_semantic), allow_hash=True)
    return db


def test_vault_search_semantic_uses_stored_index_for_non_keyword_match(tmp_path: Path):
    provider = BagOfWordsSemanticProvider()
    db = _build_main_search_semantic_db(tmp_path, provider)
    try:
        search = VaultSearch(db, embed_provider=provider)
        assert search.search("automobile", mode="keyword", limit=5, use_rerank=False) == []

        results = search.search("automobile", mode="semantic", limit=2, use_rerank=False)

        assert [result["title"] for result in results][:1] == ["Workshop Notes"]
        assert results[0]["_mode"] in {"semantic", "semantic_vec"}
        assert results[0]["semantic_vector_kind"] == "claim"
        assert results[0]["best_span"] == "L2-L2"
        assert results[0]["citation"] == "#1 Workshop Notes L2-L2"
        assert "content_raw" in results[0]
    finally:
        db.close()


def test_vault_search_semantic_uses_sqlite_vec_backend_when_unfiltered(tmp_path: Path):
    provider = BagOfWordsSemanticProvider()
    db = _build_main_search_semantic_db(tmp_path, provider)
    if not getattr(db, "_vec_available", False):
        db.close()
        pytest.skip("sqlite-vec extension is not available")
    search = VaultSearch(db, embed_provider=provider)
    try:
        results = search.search_semantic("automobile garage", limit=1)

        assert results
        assert results[0]["title"] == "Workshop Notes"
        assert results[0]["_mode"] == "semantic_vec"
        assert results[0]["_semantic_index_backend"] == "sqlite_vec"
    finally:
        db.close()


def test_vault_search_semantic_filter_falls_back_to_scan_for_recall(tmp_path: Path):
    db = VaultDB(tmp_path / "vault.db").connect()
    provider = FilterWindowSemanticProvider()
    if not getattr(db, "_vec_available", False):
        db.close()
        pytest.skip("sqlite-vec extension is not available")
    try:
        for idx in range(150):
            text = f"near filler {idx}"
            db.add_knowledge(
                f"Low Trust {idx}",
                text,
                content_aaak=f"TITLE: Low Trust {idx}\nCLAIMS:\n- [C1] {text} (L1)",
                category="search",
                trust=0.1,
            )
        db.add_knowledge(
            "High Trust Target",
            "target answer",
            content_aaak="TITLE: High Trust Target\nCLAIMS:\n- [C1] target answer (L1)",
            category="search",
            trust=0.9,
        )
        rebuild_semantic_index(db, provider, require_semantic=True)

        search = VaultSearch(db, embed_provider=provider)
        results = search.search_semantic("query text", limit=1, min_trust=0.8)

        assert results
        assert results[0]["title"] == "High Trust Target"
        assert results[0]["_mode"] == "semantic"
        assert "_semantic_index_backend" not in results[0]
    finally:
        db.close()


def test_semantic_search_cache_key_includes_vector_kind(tmp_path: Path):
    provider = BagOfWordsSemanticProvider()
    db = _build_main_search_semantic_db(tmp_path, provider)
    search = VaultSearch(db, embed_provider=provider)
    search.set_cache_config(enabled=True)
    try:
        claim_results = search.search(
            "garage maintenance",
            mode="semantic",
            semantic_vector_kind="claim",
            use_rerank=False,
        )
        node_results = search.search(
            "garage maintenance",
            mode="semantic",
            semantic_vector_kind="node",
            use_rerank=False,
        )

        assert claim_results
        assert node_results
        assert claim_results[0]["semantic_vector_kind"] == "claim"
        assert node_results[0]["semantic_vector_kind"] == "node"
    finally:
        db.close()


def test_vault_search_hybrid_combines_keyword_and_stored_semantic_modes(tmp_path: Path):
    provider = BagOfWordsSemanticProvider()
    db = _build_main_search_semantic_db(tmp_path, provider)
    try:
        search = VaultSearch(db, embed_provider=provider)

        results = search.search("automobile recipe", mode="hybrid", limit=5, use_rerank=False)
        titles = {result["title"] for result in results}

        assert {"Workshop Notes", "Sourdough Notes"}.issubset(titles)
        assert all(result["_mode"] == "hybrid_semantic" for result in results)
    finally:
        db.close()


def test_vault_search_semantic_rejects_hash_provider_by_default(tmp_path: Path):
    provider = DeterministicHashEmbeddingProvider(dim=8)
    db = _build_main_search_semantic_db(tmp_path, provider)
    try:
        search = VaultSearch(db, embed_provider=provider)

        with pytest.raises(SemanticProviderError, match="not a semantic embedding provider"):
            search.search("garage", mode="semantic", use_rerank=False)

        hybrid = search.search("garage", mode="hybrid", use_rerank=False)
        assert hybrid
        assert hybrid[0]["title"] == "Workshop Notes"
        assert "semantic" not in hybrid[0]["_mode"]

        allowed = search.search("garage", mode="semantic", allow_hash=True, use_rerank=False)
        assert allowed
        assert allowed[0]["_mode"] in {"semantic_hash", "semantic_vec_hash"}
    finally:
        db.close()
