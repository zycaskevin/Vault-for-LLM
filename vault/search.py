"""
Vault-for-LLM — 搜尋模組。

關鍵字 + 向量混合搜尋，自動降級。
- 有嵌入→語意搜尋（向量）
- 沒嵌入→純關鍵字（LIKE）
- 兩種都做→混合排序（RRF）
"""

import re
import sqlite3
from typing import Optional

from .db import VaultDB
from .embed import (
    create_embedding_provider,
    EmbeddingProvider,
)
from .semantic import (
    SemanticProviderError,
    provider_dimension,
    provider_id,
    search_semantic_index,
    validate_embedding_provider,
)

DEFAULT_KEYWORD_MIN_SCORE = 0.34


def _normalize_text(value: str) -> str:
    """Normalize text for best-effort claim matching."""
    return re.sub(r"\s+", " ", (value or "").strip().lower())


class VaultSearch:
    """Vault-for-LLM 搜尋引擎。"""

    def __init__(
        self,
        db: VaultDB,
        embed_provider=None,
        embed_provider_name: str = "auto",
        embed_model_key: str = "mix",
        graph=None,
    ):
        self.db = db
        self._embed = embed_provider
        self._embed_provider_name = embed_provider_name
        self._embed_model_key = embed_model_key
        self._graph = graph  # VaultGraph 實例（可選）

    @property
    def has_embeddings(self) -> bool:
        """檢查是否有向量搜尋能力。"""
        return self._embed is not None and self.db._vec_available

    def _get_embed(self) -> Optional[EmbeddingProvider]:
        """延遲初始化嵌入 provider。"""
        if self._embed is not None:
            return self._embed
        try:
            self._embed = create_embedding_provider(
                provider=self._embed_provider_name,
                model_key=self._embed_model_key,
            )
            return self._embed
        except RuntimeError:
            return None

    @staticmethod
    def _is_vector_db_fallback_error(exc: sqlite3.OperationalError) -> bool:
        """Return True for sqlite-vec/vector-table errors safe to keyword-fallback."""
        msg = str(exc).lower()
        return any(
            marker in msg
            for marker in (
                "dimension mismatch",
                "query vector",
                "embedding column",
                "vector table",
                "knowledge_vec",
                "sqlite-vec",
                "vec0",
            )
        )

    @staticmethod
    def _is_fts_fallback_error(exc: Exception) -> bool:
        """Return True when FTS5 keyword search should fall back to LIKE."""
        if isinstance(exc, RuntimeError):
            return "fts5" in str(exc).lower()
        if not isinstance(exc, sqlite3.OperationalError):
            return False
        msg = str(exc).lower()
        return any(
            marker in msg
            for marker in (
                "fts5",
                "knowledge_fts",
                "malformed match",
                "fts5: syntax error",
            )
        )

    # ── 搜尋入口 ──────────────────────────────────────────

    def search(
        self,
        query: str,
        mode: str = "auto",
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        graph_expand: int = 0,
        use_rerank: bool = True,
        compact: bool = False,
        semantic_vector_kind: str = "claim",
        allow_hash: bool = False,
        min_score: float | None = None,
    ) -> list[dict]:
        """
        搜尋知識庫。

        mode:
        - "auto": 有嵌入→混合，沒嵌入→關鍵字
        - "keyword": 純關鍵字
        - "vector": 純向量（legacy sqlite-vec）
        - "semantic": stored semantic_vectors search
        - "hybrid": keyword + stored semantic_vectors when available, with legacy vector fallback

        graph_expand:
        - 0: 不使用圖譜擴展（預設）
        - 1: 擴展 1 跳（直接鄰居）
        - 2: 擴展 2 跳

        use_rerank: 是否使用 reranker 重排序（預設 True）
        """
        if mode == "keyword":
            results = self.search_keyword(query, limit, min_trust, layer, category, min_score=min_score)
        elif mode == "vector":
            results = self.search_vector(query, limit * 2, min_trust, layer, category)
            results = results[:limit]
        elif mode == "semantic":
            results = self.search_semantic(
                query,
                limit,
                min_trust,
                layer,
                category,
                vector_kind=semantic_vector_kind,
                require_semantic=not allow_hash,
                allow_hash=allow_hash,
            )
        elif mode == "hybrid":
            results = self.search_hybrid(
                query,
                limit,
                min_trust,
                layer,
                category,
                semantic_vector_kind=semantic_vector_kind,
                allow_hash=allow_hash,
                min_score=min_score,
            )
        else:
            # auto: safe by default: use stored semantic index only with a real semantic provider.
            if self._semantic_index_available(
                semantic_vector_kind,
                require_semantic=not allow_hash,
                allow_hash=allow_hash,
            ):
                results = self.search_hybrid(
                    query,
                    limit,
                    min_trust,
                    layer,
                    category,
                    semantic_vector_kind=semantic_vector_kind,
                    allow_hash=allow_hash,
                    min_score=min_score,
                )
            else:
                embed = self._get_embed()
                if embed is not None and self.db._vec_available and bool(getattr(embed, "is_semantic", True)):
                    results = self.search_hybrid(query, limit, min_trust, layer, category, min_score=min_score)
                else:
                    results = self.search_keyword(query, limit, min_trust, layer, category, min_score=min_score)

        # 圖譜擴展
        if graph_expand > 0 and self._graph is not None:
            results = self._apply_graph_expand(results, graph_expand, limit)

        # Reranker
        if use_rerank and results:
            results = self._rerank(results)

        # 提取 best_claim
        for r in results:
            if not r.get("best_claim"):
                r["best_claim"] = self._extract_best_claim(r.get("content_aaak", ""))

        # Document Map enrichment（best span / node / citation）
        if results:
            self._enrich_with_document_map(results, query)

        if compact:
            return [self._compact_result(r) for r in results]
        return results

    # ── Document Map enrichment ─────────────────────────────

    def _enrich_with_document_map(self, results: list[dict], query: str = "") -> None:
        """Attach best Document Map span metadata to search results when available.

        This is intentionally best-effort: older/local databases without populated
        map rows keep the previous result shape unchanged.
        """
        if self.db.conn is None:
            return

        query_terms = [term.lower() for term in self._tokenize(query or "")]
        for result in results:
            knowledge_id = result.get("id")
            if not knowledge_id:
                continue
            try:
                span = self._find_document_map_span(
                    int(knowledge_id),
                    result.get("best_claim", ""),
                    query_terms,
                )
            except Exception:
                # Search must not fail because optional map metadata is missing.
                continue
            if not span:
                continue

            line_start = span.get("line_start") or span.get("node_line_start")
            line_end = span.get("line_end") or span.get("node_line_end") or line_start
            if not line_start or not line_end:
                continue

            title = result.get("title", "")
            node = {
                "node_uid": span.get("node_uid", ""),
                "heading": span.get("heading", ""),
                "path": span.get("path", ""),
                "line_start": span.get("node_line_start") or line_start,
                "line_end": span.get("node_line_end") or line_end,
            }

            # Backward-compatible top-level fields plus structured fields.
            result["node_uid"] = node["node_uid"]
            result["path"] = node["path"]
            result["heading"] = node["heading"]
            result["line_start"] = int(line_start)
            result["line_end"] = int(line_end)
            result["best_span"] = f"L{line_start}-L{line_end}"
            result["best_node"] = node
            result["citation"] = f"#{knowledge_id} {title} L{line_start}-L{line_end}"
            result["recommended_next_tool"] = "vault_read_range"
            result["next_action"] = {
                "tool": "vault_map_show",
                "arguments": {"knowledge_id": int(knowledge_id)},
            }
            result["next_actions"] = [
                {
                    "tool": "vault_map_show",
                    "arguments": {"knowledge_id": int(knowledge_id)},
                },
                {
                    "tool": "vault_read_range",
                    "arguments": {
                        "knowledge_id": int(knowledge_id),
                        "node_uid": node["node_uid"],
                        "line_start": int(line_start),
                        "line_end": int(line_end),
                    },
                },
            ]

    @staticmethod
    def _compact_result(result: dict) -> dict:
        """Return an opt-in compact search payload without raw content blobs."""
        fields = (
            "id",
            "title",
            "category",
            "layer",
            "trust",
            "tags",
            "best_claim",
            "best_span",
            "node_uid",
            "path",
            "heading",
            "line_start",
            "line_end",
            "citation",
            "recommended_next_tool",
            "next_action",
            "next_actions",
        )
        compact = {key: result[key] for key in fields if key in result}
        if "_rerank_score" in result:
            compact["rerank_score"] = result["_rerank_score"]
        return compact

    def _find_document_map_span(
        self,
        knowledge_id: int,
        best_claim: str = "",
        query_terms: list[str] | None = None,
    ) -> dict | None:
        """Return the best claim/node span for one knowledge entry, if populated."""
        query_terms = query_terms or []
        best_claim_norm = _normalize_text(best_claim)

        claim_rows = [
            dict(row)
            for row in self.db.conn.execute(
                """SELECT c.node_uid, c.claim, c.line_start, c.line_end,
                          n.heading, n.path,
                          n.line_start AS node_line_start,
                          n.line_end AS node_line_end
                   FROM knowledge_claims c
                   LEFT JOIN knowledge_nodes n
                     ON n.knowledge_id = c.knowledge_id
                    AND n.node_uid = c.node_uid
                   WHERE c.knowledge_id=?
                   ORDER BY c.line_start, c.id""",
                (knowledge_id,),
            ).fetchall()
        ]

        if claim_rows:
            scored_rows: list[tuple[int, dict]] = []
            for row in claim_rows:
                claim_norm = _normalize_text(row.get("claim", ""))
                haystack = " ".join(
                    str(row.get(key) or "").lower()
                    for key in ("claim", "path", "heading")
                )
                score = 0
                if best_claim_norm and claim_norm == best_claim_norm:
                    score += 100
                elif best_claim_norm and (
                    best_claim_norm in claim_norm or claim_norm in best_claim_norm
                ):
                    score += 75
                score += sum(10 for term in query_terms if term and term in haystack)
                scored_rows.append((score, row))

            scored_rows.sort(
                key=lambda item: (
                    item[0],
                    -(item[1].get("line_start") or 0),
                ),
                reverse=True,
            )
            return scored_rows[0][1]

        node = self.db.conn.execute(
            """SELECT node_uid, heading, path,
                      line_start, line_end,
                      line_start AS node_line_start,
                      line_end AS node_line_end
               FROM knowledge_nodes
               WHERE knowledge_id=?
               ORDER BY line_start, level DESC, id
               LIMIT 1""",
            (knowledge_id,),
        ).fetchone()
        return dict(node) if node else None

    # ── Reranker ──────────────────────────────────────────

    @staticmethod
    def _rerank(results: list[dict]) -> list[dict]:
        """
        搜尋結果重排序。
        score = cosine_sim × 0.5 + graph_depth_bonus + trust × 0.15 + freshness × 0.15

        graph_depth_bonus: 0.1 per hop, max 0.2
        freshness: 1.0 - min(days_since_update / 365, 0.5)
        """
        from datetime import datetime, timezone

        def calc_freshness(updated_at: str) -> float:
            if not updated_at:
                return 0.5
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - dt).days
                return 1.0 - min(days / 365, 0.5)
            except Exception:
                return 0.5

        def calc_graph_depth(result: dict) -> float:
            dist = result.get("_graph_distance", 0)
            if dist == 0:
                return 0.2  # 直接匹配，最高加分
            return max(0, 0.2 - (dist - 1) * 0.1)

        for r in results:
            # 基礎語意分數（歸一到 0-1）
            base_sim = r.get("_score", 0.5)
            if isinstance(base_sim, float) and base_sim > 1.0:
                # RRF 分數可能 > 1，歸一化
                base_sim = min(base_sim / 0.05, 1.0)  # RRF 典型最大 ~0.05

            trust = r.get("trust", 0.5)
            freshness = r.get("freshness", None)
            if freshness is None:
                freshness = calc_freshness(r.get("updated_at", ""))
            freshness = max(0.0, min(1.0, freshness))

            graph_bonus = calc_graph_depth(r)

            rerank_score = (
                base_sim * 0.5
                + graph_bonus
                + trust * 0.15
                + freshness * 0.15
            )

            r["_rerank_score"] = round(rerank_score, 4)

        results.sort(key=lambda x: x.get("_rerank_score", 0), reverse=True)
        return results

    # ── 原子主張提取 ──────────────────────────────────────

    @staticmethod
    def _extract_best_claim(content_aaak: str) -> str:
        """
        從 AAAK 壓縮內容提取最相關的原子主張。
        如果有 CLAIMS 段，取第一條；否則取 content_raw 前 100 字。
        """
        if not content_aaak:
            return ""

        # 嘗試提取 CLAIMS 段
        if "CLAIMS:" in content_aaak:
            lines = content_aaak.split("\n")
            claims = []
            in_claims = False
            for line in lines:
                if line.strip() == "CLAIMS:":
                    in_claims = True
                    continue
                if in_claims and line.strip().startswith("- ["):
                    claims.append(line.strip())
                elif in_claims and not line.strip().startswith("-"):
                    break

            if claims:
                # 取第一條作為 best_claim
                first = claims[0]
                # 格式: "- [C1] 描述 (L12)"
                import re
                match = re.match(r"- \[\w+\]\s*(.+?)(?:\s*\(L\d+\))?$", first)
                if match:
                    return match.group(1).strip()
                return first.lstrip("- []C0123456789 ").strip()

        # 沒有 CLAIMS 段， fallback
        return ""

    # ── 關鍵字搜尋 ──────────────────────────────────────────

    def search_keyword(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        min_score: float | None = None,
    ) -> list[dict]:
        """Keyword search with optional FTS5/BM25 and LIKE fallback."""
        terms = self._tokenize(query)
        if not terms:
            return []
        score_floor = DEFAULT_KEYWORD_MIN_SCORE if min_score is None else max(0.0, float(min_score))

        try:
            results = self.db.search_fts_keyword(
                terms,
                limit=limit,
                min_trust=min_trust,
                layer=layer,
                category=category,
            )
        except Exception as exc:
            if not self._is_fts_fallback_error(exc):
                raise
            results = []

        if results:
            for d in results:
                text = f"{d.get('title', '')} {d.get('content_raw', '')} {d.get('tags', '')}".lower()
                matched = sum(1 for t in terms if t.lower() in text)
                bm25_score = float(d.pop("_bm25", 0.0) or 0.0)
                d["_score"] = matched / len(terms)
                d["_bm25"] = bm25_score
                d["_mode"] = "keyword_fts"
            return [d for d in results if d.get("_score", 0.0) >= score_floor]

        return self._search_keyword_like(query, terms, limit, min_trust, layer, category, min_score=score_floor)

    def _search_keyword_like(
        self,
        query: str,
        terms: list[str],
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        min_score: float = DEFAULT_KEYWORD_MIN_SCORE,
    ) -> list[dict]:
        """LIKE keyword fallback used when FTS5 is unavailable or yields no hits."""
        # 建構 WHERE 條件
        conditions = []
        params: list = [min_trust]

        for term in terms:
            conditions.append(
                "(title LIKE ? OR content_raw LIKE ? OR content_aaak LIKE ? "
                "OR tags LIKE ? OR category LIKE ?)"
            )
            pattern = f"%{term}%"
            params.extend([pattern] * 5)

        where = f"trust >= ? AND ({' OR '.join(conditions)})" if len(terms) > 1 else f"trust >= ? AND {conditions[0]}"

        if layer:
            where += " AND layer=?"
            params.append(layer)
        if category:
            where += " AND category=?"
            params.append(category)

        sql = f"SELECT * FROM knowledge WHERE {where} ORDER BY trust DESC LIMIT ?"
        params.append(limit)

        rows = self.db.conn.execute(sql, params).fetchall()

        # 關鍵字評分：匹配詞數越多分越高
        results = []
        for row in rows:
            d = dict(row)
            text = f"{d.get('title', '')} {d.get('content_raw', '')} {d.get('tags', '')}".lower()
            matched = sum(1 for t in terms if t.lower() in text)
            d["_score"] = matched / len(terms)
            d["_mode"] = "keyword"
            if d["_score"] >= min_score:
                results.append(d)

        results.sort(key=lambda x: x["_score"], reverse=True)
        return results

    # ── 向量搜尋 ──────────────────────────────────────────

    def search_vector(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """純向量語意搜尋。"""
        embed = self._get_embed()
        if embed is None or not self.db._vec_available:
            # 降級到關鍵字
            return self.search_keyword(query, limit, min_trust, layer, category)

        try:
            query_vec = embed.encode(query)[0]
        except Exception as e:
            print(f"[vault-mcp] ⚠️ 嵌入失敗，降級到關鍵字: {e}")
            return self.search_keyword(query, limit, min_trust, layer, category)

        try:
            results = self.db.search_vector(query_vec, limit=limit * 2, min_trust=min_trust)
        except sqlite3.OperationalError as e:
            if self._is_vector_db_fallback_error(e):
                print(f"[vault-mcp] ⚠️ 向量搜尋失敗，降級到關鍵字: {e}")
                return self.search_keyword(query, limit, min_trust, layer, category)
            raise

        # 後過濾
        if layer:
            results = [r for r in results if r.get("layer") == layer]
        if category:
            results = [r for r in results if r.get("category") == category]

        for r in results:
            # sqlite-vec cosine distance: 0=相同, 1=正交, 2=相反
            # 轉成 0~1 的相似度分數：score = 1 - distance/2
            dist = r.get("_distance", 1.0) or 0.0
            r["_score"] = max(0.0, 1.0 - dist / 2)
            r["_mode"] = "vector"

        return results[:limit]

    # ── Stored semantic index search ─────────────────────────

    def _semantic_provider(self, *, require_semantic: bool, allow_hash: bool):
        provider = self._get_embed()
        if provider is None:
            return None
        return validate_embedding_provider(
            provider,
            require_semantic=require_semantic,
            allow_hash=allow_hash,
        )

    def _semantic_index_available(
        self,
        vector_kind: str = "claim",
        *,
        require_semantic: bool = True,
        allow_hash: bool = False,
    ) -> bool:
        """Return True when the active provider has stored vectors for this DB."""
        try:
            provider = self._semantic_provider(
                require_semantic=require_semantic,
                allow_hash=allow_hash,
            )
            if provider is None:
                return False
            row = self.db.conn.execute(
                """SELECT 1 FROM semantic_vectors
                   WHERE provider_id=? AND dimension=? AND vector_kind=?
                   LIMIT 1""",
                (provider_id(provider), provider_dimension(provider), vector_kind),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        *,
        vector_kind: str = "claim",
        require_semantic: bool = True,
        allow_hash: bool = False,
    ) -> list[dict]:
        """Search stored semantic_vectors and return normal search result shape.

        Missing providers or missing semantic-index tables are treated as an empty
        explicit semantic result. Provider safety violations intentionally raise.
        """
        provider = self._semantic_provider(
            require_semantic=require_semantic,
            allow_hash=allow_hash,
        )
        if provider is None:
            return []

        try:
            rows = search_semantic_index(
                self.db,
                query,
                provider=provider,
                vector_kind=vector_kind,
                limit=limit * 4,
                require_semantic=require_semantic,
                allow_hash=allow_hash,
            )
        except SemanticProviderError:
            raise
        except (AttributeError, TypeError, RuntimeError):
            return []
        except sqlite3.OperationalError as exc:
            if "semantic_vectors" in str(exc).lower():
                return []
            raise

        results: list[dict] = []
        seen: set[int] = set()
        for row in rows:
            kid = int(row.get("knowledge_id") or row.get("id"))
            if kid in seen:
                continue
            knowledge = self.db.get_knowledge(kid)
            if not knowledge:
                continue
            item = dict(knowledge)
            if item.get("trust", 0.0) < min_trust:
                continue
            if layer and item.get("layer") != layer:
                continue
            if category and item.get("category") != category:
                continue

            item["_score"] = float(row.get("_score", 0.0) or 0.0)
            item["_mode"] = "semantic_hash" if not bool(getattr(provider, "is_semantic", True)) else "semantic"
            item["semantic_vector_kind"] = row.get("vector_kind", vector_kind)
            item["semantic_item_uid"] = row.get("item_uid")
            item["semantic_source_text"] = row.get("source_text")
            if row.get("line_start") and row.get("line_end"):
                item["line_start"] = int(row["line_start"])
                item["line_end"] = int(row["line_end"])
                item["best_span"] = f"L{item['line_start']}-L{item['line_end']}"
            for key in ("node_uid", "heading", "path", "citation"):
                if row.get(key):
                    item[key] = row[key]
            if row.get("source_text"):
                item["best_claim"] = row["source_text"]
            results.append(item)
            seen.add(kid)
            if len(results) >= limit:
                break
        return results

    # ── 混合搜尋（RRF） ────────────────────────────────────

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        *,
        semantic_vector_kind: str = "claim",
        allow_hash: bool = False,
        min_score: float | None = None,
    ) -> list[dict]:
        """
        Hybrid search with Reciprocal Rank Fusion (RRF).

        Prefer the stored semantic index when a safe provider/index is available;
        otherwise preserve the legacy sqlite-vec vector fallback.
        """
        k = 60  # RRF constant

        kw_results = self.search_keyword(
            query,
            limit=limit * 2,
            min_trust=min_trust,
            layer=layer,
            category=category,
            min_score=min_score,
        )

        try:
            semantic_results = self.search_semantic(
                query,
                limit=limit * 2,
                min_trust=min_trust,
                layer=layer,
                category=category,
                vector_kind=semantic_vector_kind,
                require_semantic=not allow_hash,
                allow_hash=allow_hash,
            )
        except SemanticProviderError:
            semantic_results = []

        if semantic_results:
            second_results = semantic_results
            hybrid_mode = (
                "hybrid_semantic_hash"
                if any(item.get("_mode") == "semantic_hash" for item in semantic_results)
                else "hybrid_semantic"
            )
        elif self._get_embed() is not None and self.db._vec_available:
            second_results = self.search_vector(
                query,
                limit=limit * 2,
                min_trust=min_trust,
                layer=layer,
                category=category,
            )
            hybrid_mode = "hybrid"
        else:
            second_results = []
            hybrid_mode = "keyword"

        scores: dict[int, float] = {}
        all_items: dict[int, dict] = {}

        for rank, item in enumerate(kw_results):
            kid = item["id"]
            scores[kid] = scores.get(kid, 0) + 1.0 / (k + rank + 1)
            all_items[kid] = item

        for rank, item in enumerate(second_results):
            kid = item["id"]
            scores[kid] = scores.get(kid, 0) + 1.0 / (k + rank + 1)
            if kid not in all_items:
                all_items[kid] = item
            else:
                # Merge: semantic/vector span metadata wins, but keep the fused mode clear.
                all_items[kid].update(
                    {
                        key: value
                        for key, value in item.items()
                        if key.startswith("semantic_")
                        or key in {"best_span", "line_start", "line_end", "citation", "node_uid", "path", "heading"}
                    }
                )
                all_items[kid]["_mode"] = hybrid_mode

        sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for kid, score in sorted_ids[:limit]:
            item = all_items[kid]
            item["_score"] = score
            if second_results and item.get("_mode", "").split("_", 1)[0] in {"keyword", "semantic", "vector"}:
                item["_mode"] = hybrid_mode
            else:
                item["_mode"] = item.get("_mode", hybrid_mode)
            results.append(item)

        return results

    # ── 圖譜擴展 ──────────────────────────────────────────────

    def _apply_graph_expand(
        self, results: list[dict], expand_depth: int, limit: int
    ) -> list[dict]:
        """
        對搜尋結果應用圖譜擴展。
        沿著圖譜邊找相鄰知識，合併到搜尋結果中。
        """
        if not results or self._graph is None:
            return results

        # 已有的結果 ID 集合
        seen_ids = {r["id"] for r in results}
        expanded = list(results)

        # 對每個搜尋結果，找圖譜鄰居
        for r in results:
            neighbors = self.db.get_neighbors(r["id"], max_depth=expand_depth)
            for n in neighbors:
                if n["id"] not in seen_ids:
                    seen_ids.add(n["id"])
                    k = self.db.get_knowledge(n["id"])
                    if k:
                        d = dict(k)
                        # 圖譜擴展的分數衰減：距離越遠分數越低
                        base_score = r.get("_score", 0.5)
                        d["_score"] = base_score * (0.7 ** n["distance"])
                        d["_mode"] = "graph_expand"
                        d["_graph_distance"] = n["distance"]
                        d["_relation"] = n["relation"]
                        expanded.append(d)

        # 重新排序：原搜尋結果優先，圖譜擴展次之
        expanded.sort(key=lambda x: (
            -x.get("_score", 0),
            x.get("_graph_distance", 0),
        ))

        return expanded[:limit]

    # ── 工具 ──────────────────────────────────────────────

    @staticmethod
    def _tokenize(query: str) -> list[str]:
        """
        簡單分詞：英文按空格，中文按字元。
        過濾掉太短的詞。
        """
        # 英文單詞
        english = re.findall(r"[a-zA-Z]{2,}", query)
        # 中文詞（2-4字元的連續中文字）
        chinese = re.findall(r"[\u4e00-\u9fff]{2,4}", query)
        # 如果中文只有單字，也拆開
        if not chinese:
            chars = re.findall(r"[\u4e00-\u9fff]", query)
            chinese = [c for c in chars if len(c) == 1]

        terms = english + chinese
        # 去重，保留順序
        seen = set()
        unique = []
        for t in terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        return unique if unique else [query]
