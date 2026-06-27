"""Vector, semantic-index, hybrid, and graph-expand search helpers."""

from __future__ import annotations

import sqlite3
from typing import Optional

from .access_policy import ReadPolicy
from .search_graph import apply_graph_expand
from .search_rerank import _is_active_memory
from .search_utils import normalize_search_limit
from .semantic import (
    SemanticProviderError,
    provider_dimension,
    provider_id,
    search_semantic_index,
    search_semantic_index_vec,
    semantic_vec_index_is_fresh,
    validate_embedding_provider,
)


class SearchSemanticMixin:
        def search_vector(
            self,
            query: str,
            limit: int = 10,
            min_trust: float = 0.0,
            layer: Optional[str] = None,
            category: Optional[str] = None,
            min_score: float | None = None,
        ) -> list[dict]:
            """
            純向量語意搜尋。

            min_score: 最小相似度分數（0-1），僅返回相似度 >= min_score 的結果。
                      向量模式的分數為餘弦相似度轉換為 0-1 範圍，
                      與 keyword 模式的匹配率分數含義不同，使用時請注意。

            注意：當向量搜尋不可用時返回空列表（不降級到關鍵字），
            調用者需自行處理降級邏輯。
            """
            # 空查詢防護
            if not query or not isinstance(query, str) or not query.strip():
                return []
            limit = normalize_search_limit(limit)
            if limit <= 0:
                return []
            embed = self._get_embed()
            if embed is None or not self.db._vec_available:
                return []

            try:
                query_vec = embed.encode(query)[0]
            except Exception:
                return []

            # 驗證向量維度與資料庫配置是否匹配
            try:
                expected_dim = int(self.db._get_config("embedding_dim", "384"))
            except (ValueError, TypeError):
                expected_dim = 384
            if len(query_vec) != expected_dim:
                return []

            try:
                results = self.db.search_vector(
                    query_vec, limit=limit * 2, min_trust=min_trust,
                    layer=layer, category=category
                )
            except sqlite3.OperationalError as e:
                if self._is_vector_db_fallback_error(e):
                    return []
                raise
            except ValueError:
                # 維度不匹配等引數錯誤
                return []

            # 後過濾（雙重保險）
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

            # min_score 過濾
            if min_score is not None:
                results = [r for r in results if r.get("_score", 0.0) >= min_score]

            return results[:limit]

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

        def _semantic_index_has_provider_rows(
            self,
            provider,
            vector_kind: str = "claim",
        ) -> bool:
            """Return True only when stored semantic vectors exist for provider."""
            try:
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
            # 空查詢防護
            if not query or not isinstance(query, str) or not query.strip():
                return []
            limit = normalize_search_limit(limit)
            if limit <= 0:
                return []
            provider = self._semantic_provider(
                require_semantic=require_semantic,
                allow_hash=allow_hash,
            )
            if provider is None:
                return []
            if not self._semantic_index_has_provider_rows(provider, vector_kind):
                return []

            try:
                use_vec_backend = (
                    min_trust <= 0.0
                    and layer is None
                    and category is None
                    and semantic_vec_index_is_fresh(self.db, provider, vector_kind)
                )
                search_fn = search_semantic_index_vec if use_vec_backend else search_semantic_index
                rows = search_fn(
                    self.db,
                    query,
                    provider=provider,
                    vector_kind=vector_kind,
                    limit=limit * 4,
                    min_trust=min_trust,
                    layer=layer,
                    category=category,
                    require_semantic=require_semantic,
                    allow_hash=allow_hash,
                )
            except SemanticProviderError:
                raise
            except Exception:
                return []

            results: list[dict] = []
            seen: set[int] = set()
            for row in rows:
                kid = int(row.get("knowledge_id") or row.get("id"))
                if kid in seen:
                    continue
                knowledge = self.db.get_knowledge(kid)
                if not knowledge:
                    continue
                if not _is_active_memory(knowledge):
                    continue
                item = dict(knowledge)
                if item.get("trust", 0.0) < min_trust:
                    continue
                if layer and item.get("layer") != layer:
                    continue
                if category and item.get("category") != category:
                    continue

                item["_score"] = float(row.get("_score", 0.0) or 0.0)
                if row.get("_mode") == "semantic_vec":
                    item["_mode"] = (
                        "semantic_vec_hash"
                        if not bool(getattr(provider, "is_semantic", True))
                        else "semantic_vec"
                    )
                else:
                    item["_mode"] = (
                        "semantic_hash"
                        if not bool(getattr(provider, "is_semantic", True))
                        else "semantic"
                    )
                item["semantic_vector_kind"] = row.get("vector_kind", vector_kind)
                item["semantic_item_uid"] = row.get("item_uid")
                item["semantic_source_text"] = row.get("source_text")
                item["_semantic_scanned_rows"] = int(row.get("_semantic_scanned_rows", 0) or 0)
                item["_semantic_truncated"] = bool(row.get("_semantic_truncated", False))
                if row.get("_semantic_index_backend"):
                    item["_semantic_index_backend"] = row["_semantic_index_backend"]
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
            use_dynamic_weight: bool = True,
            keyword_weight: Optional[float] = None,
            vector_weight: Optional[float] = None,
        ) -> list[dict]:
            """
            Hybrid search with Reciprocal Rank Fusion (RRF).

            Prefer the stored semantic index when a safe provider/index is available;
            otherwise preserve the legacy sqlite-vec vector fallback.

            支援動態權重調整：根據查詢匹配質量自動調整 keyword/vector 權重。
            支援交叉驗證加分：同時出現在關鍵詞和向量結果中的文檔獲得額外加分。
            """
            # 空查詢防護
            if not query or not isinstance(query, str) or not query.strip():
                return []
            limit = normalize_search_limit(limit)
            if limit <= 0:
                return []
            k = 60  # RRF constant
            kw_w = keyword_weight if keyword_weight is not None else self._keyword_weight
            vec_w = vector_weight if vector_weight is not None else self._vector_weight

            kw_results = self.search_keyword(
                query,
                limit=limit * 2,
                min_trust=min_trust,
                layer=layer,
                category=category,
                min_score=min_score,
            )

            semantic_results = []
            if self._semantic_index_available(
                semantic_vector_kind,
                require_semantic=not allow_hash,
                allow_hash=allow_hash,
            ):
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
                    raise
                except Exception:
                    semantic_results = []

            if semantic_results:
                second_results = semantic_results
                hybrid_mode = (
                    "hybrid_semantic_hash"
                    if any(
                        item.get("_mode") in {"semantic_hash", "semantic_vec_hash"}
                        for item in semantic_results
                    )
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
                hybrid_mode = "hybrid" if second_results else "keyword"
            else:
                second_results = []
                hybrid_mode = "keyword"

            # 動態權重調整（P1: Issue 8/N2 — 同時考慮關鍵詞和向量質量）
            if use_dynamic_weight and kw_results and second_results:
                # 計算關鍵詞匹配質量：最高分（0~1）
                kw_max_score = max(r.get('_score', 0) for r in kw_results) if kw_results else 0
                # 關鍵詞質量因子：BM25 分數 > 0.8 為高質量，< 0.3 為低質量
                kw_quality = min(1.0, kw_max_score / 0.8) if kw_max_score > 0 else 0.0

                # 計算向量/語義匹配質量：最高分（0~1，1.0=完全匹配）
                vec_max_score = max(r.get('_score', 0) for r in second_results) if second_results else 0
                # 向量質量因子：相似度 > 0.7 為高質量，< 0.3 為低質量
                vec_quality = min(1.0, vec_max_score / 0.7) if vec_max_score > 0 else 0.0

                # 計算相對質量差異，用於動態調整權重
                # 質量差異越大，權重調整幅度越大
                quality_diff = kw_quality - vec_quality
                avg_quality = (kw_quality + vec_quality) / 2.0
                quality_ratio = kw_quality / max(vec_quality, 0.01)  # 避免除以零

                max_boost = 1.5  # 最大權重倍數
                max_reduce = 0.7  # 最小權重倍數

                # 同時考慮關鍵詞和向量結果的質量（改進：
                # 1. 當兩者質量都很高時，平衡兩者權重，避免某一方過度主導
                # 2. 當其中一方質量明顯較低時，顯著提高另一方權重
                # 3. 當兩者質量都很低時，稍微偏向向量（模糊匹配更有優勢）

                if kw_quality >= 0.8 and vec_quality >= 0.8:
                    # 兩者質量都很高 → 平衡權重，避免某一方過度主導
                    # 使用默認權重，稍微調整以平衡兩者
                    if abs(quality_diff) > 0.1:
                        # 輕微調整，幅度不超過 10%
                        if quality_diff > 0:
                            kw_boost = 1.05
                            vec_boost = 0.95
                        else:
                            kw_boost = 0.95
                            vec_boost = 1.05
                    else:
                        kw_boost = 1.0
                        vec_boost = 1.0
                elif kw_quality >= 0.5 and vec_quality < 0.3:
                    # 關鍵詞質量中等以上，向量質量很低 → 大幅提高關鍵詞權重
                    kw_boost = max_boost
                    vec_boost = max_reduce
                elif vec_quality >= 0.5 and kw_quality < 0.3:
                    # 向量質量中等以上，關鍵詞質量很低 → 大幅提高向量權重
                    kw_boost = max_reduce
                    vec_boost = max_boost
                elif abs(quality_diff) > 0.2:
                    # 有顯著質量差異，根據質量差動態調整
                    if quality_diff > 0:
                        # 關鍵詞質量更高
                        adjustment = quality_diff * (max_boost - 1.0) / 0.8
                        kw_boost = 1.0 + adjustment
                        vec_boost = max_reduce + (1.0 - quality_diff) * (1.0 - max_reduce) / 0.8
                    else:
                        # 向量質量更高
                        adjustment = abs(quality_diff) * (max_boost - 1.0) / 0.8
                        kw_boost = max_reduce + (1.0 + quality_diff) * (1.0 - max_reduce) / 0.8
                        vec_boost = 1.0 + adjustment
                else:
                    # 質量相近，根據整體質量微調
                    if avg_quality > 0.6:
                        # 整體質量高，稍微偏關鍵詞（精確匹配更可靠）
                        kw_boost = 1.1
                        vec_boost = 0.9
                    elif avg_quality < 0.3:
                        # 整體質量低，稍微偏向量（模糊匹配更有優勢）
                        kw_boost = 0.9
                        vec_boost = 1.1
                    else:
                        kw_boost = 1.0
                        vec_boost = 1.0

                kw_w *= kw_boost
                vec_w *= vec_boost

            # RRF 融合（以 kid 去重，同一筆知識只出現一次）
            scores: dict[int, float] = {}
            all_items: dict[int, dict] = {}
            hit_sources: dict[int, set] = {}  # 追蹤每筆知識來自哪些搜尋模式
            kw_rank_map: dict[int, int] = {}  # 關鍵詞結果的排名映射
            vec_rank_map: dict[int, int] = {}  # 向量結果的排名映射

            for rank, item in enumerate(kw_results):
                kid = item["id"]
                kw_rank_map[kid] = rank
                scores[kid] = scores.get(kid, 0) + kw_w * (1.0 / (k + rank + 1))
                all_items[kid] = item
                hit_sources.setdefault(kid, set()).add("keyword")

            for rank, item in enumerate(second_results):
                kid = item["id"]
                vec_rank_map[kid] = rank
                scores[kid] = scores.get(kid, 0) + vec_w * (1.0 / (k + rank + 1))
                if kid not in all_items:
                    all_items[kid] = item
                    hit_sources.setdefault(kid, set()).add("vector")
                else:
                    # 同時命中 keyword 和 vector → 標記為 hybrid，給予交叉驗證加分
                    hit_sources.setdefault(kid, set()).add("vector")
                    # 交叉驗證獎勵（P2: Issue 9 — 根據排名倒數和計算加分幅度）
                    # 排名越靠前，加分越多；雙方都在前 10 名以內時加分最多
                    kw_rank = kw_rank_map.get(kid, len(kw_results))
                    vec_rank = vec_rank_map.get(kid, len(second_results))
                    # 使用倒數排名加權：排名越靠前，倒數值越大
                    reciprocal_rank_sum = (1.0 / (kw_rank + 1)) + (1.0 / (vec_rank + 1))
                    # 最大倒數和為 2.0（雙方都是第 1 名）
                    # 加分範圍：5% ~ 25%，根據排名倒數和動態調整
                    max_bonus = 0.25  # 最大 25% 加分
                    min_bonus = 0.05  # 最小 5% 加分
                    cross_val_bonus = min_bonus + (reciprocal_rank_sum / 2.0) * (max_bonus - min_bonus)
                    scores[kid] *= (1.0 + cross_val_bonus)
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

            # 根據命中來源更新 _mode
            for kid in all_items:
                sources = hit_sources.get(kid, set())
                if len(sources) > 1:
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

        def _apply_graph_expand(
            self,
            results: list[dict],
            expand_depth: int,
            limit: int,
            min_trust: float = 0.0,
            layer: Optional[str] = None,
            category: Optional[str] = None,
            read_policy: ReadPolicy | None = None,
        ) -> list[dict]:
            """Backward-compatible wrapper around ``vault.search_graph``."""
            if not results or self._graph is None or expand_depth <= 0:
                return results
            return apply_graph_expand(
                self.db,
                results,
                expand_depth=expand_depth,
                limit=limit,
                min_trust=min_trust,
                layer=layer,
                category=category,
                read_policy=read_policy,
            )
