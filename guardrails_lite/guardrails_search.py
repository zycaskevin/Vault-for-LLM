"""
Guardrails Lite — 搜尋模組。

關鍵字 + 向量混合搜尋，自動降級。
- 有嵌入→語意搜尋（向量）
- 沒嵌入→純關鍵字（LIKE）
- 兩種都做→混合排序（RRF）
"""

import re
from typing import Optional

from .guardrails_db import GuardrailsDB
from .guardrails_embed import (
    create_embedding_provider,
    EmbeddingProvider,
    MODELS,
    DEFAULT_MODEL_KEY,
)


class GuardrailsSearch:
    """Guardrails Lite 搜尋引擎。"""

    def __init__(
        self,
        db: GuardrailsDB,
        embed_provider=None,
        embed_provider_name: str = "auto",
        embed_model_key: str = "mix",
        graph=None,
    ):
        self.db = db
        self._embed = embed_provider
        self._embed_provider_name = embed_provider_name
        self._embed_model_key = embed_model_key
        self._graph = graph  # GuardrailsGraph 實例（可選）

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
    ) -> list[dict]:
        """
        搜尋知識庫。

        mode:
        - "auto": 有嵌入→混合，沒嵌入→關鍵字
        - "keyword": 純關鍵字
        - "vector": 純向量
        - "hybrid": 混合（RRF 融合）

        graph_expand:
        - 0: 不使用圖譜擴展（預設）
        - 1: 擴展 1 跳（直接鄰居）
        - 2: 擴展 2 跳

        use_rerank: 是否使用 reranker 重排序（預設 True）
        """
        if mode == "keyword":
            results = self.search_keyword(query, limit, min_trust, layer, category)
        elif mode == "vector":
            results = self.search_vector(query, limit * 2, min_trust, layer, category)
            results = results[:limit]
        elif mode == "hybrid":
            results = self.search_hybrid(query, limit, min_trust, layer, category)
        else:
            # auto: 智慧降級
            embed = self._get_embed()
            if embed is not None and self.db._vec_available:
                results = self.search_hybrid(query, limit, min_trust, layer, category)
            else:
                results = self.search_keyword(query, limit, min_trust, layer, category)

        # 圖譜擴展
        if graph_expand > 0 and self._graph is not None:
            results = self._apply_graph_expand(results, graph_expand, limit)

        # Reranker
        if use_rerank and results:
            results = self._rerank(results)

        # 提取 best_claim
        for r in results:
            r["best_claim"] = self._extract_best_claim(r.get("content_aaak", ""))

        return results

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
    ) -> list[dict]:
        """純關鍵字搜尋，自動拆詞 + LIKE 匹配。"""
        # 拆詞：中文按字元，英文按空格
        terms = self._tokenize(query)
        if not terms:
            return []

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
            print(f"[guardrails-lite] ⚠️ 嵌入失敗，降級到關鍵字: {e}")
            return self.search_keyword(query, limit, min_trust, layer, category)

        results = self.db.search_vector(query_vec, limit=limit * 2, min_trust=min_trust)

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

    # ── 混合搜尋（RRF） ────────────────────────────────────

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        混合搜尋：Reciprocal Rank Fusion（RRF）。
        向量跟關鍵字各自的排名做倒數加權融合。
        """
        k = 60  # RRF 常數

        # 取兩組結果
        kw_results = self.search_keyword(query, limit=limit * 2, min_trust=min_trust,
                                          layer=layer, category=category)
        vec_results = self.search_vector(query, limit=limit * 2, min_trust=min_trust,
                                          layer=layer, category=category)

        # RRF 融合
        scores: dict[int, float] = {}
        all_items: dict[int, dict] = {}

        for rank, item in enumerate(kw_results):
            kid = item["id"]
            scores[kid] = scores.get(kid, 0) + 1.0 / (k + rank + 1)
            all_items[kid] = item

        for rank, item in enumerate(vec_results):
            kid = item["id"]
            scores[kid] = scores.get(kid, 0) + 1.0 / (k + rank + 1)
            if kid not in all_items:
                all_items[kid] = item
            else:
                # 合併：向量的 metadata 優先
                all_items[kid]["_mode"] = "hybrid"

        # 排序
        sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for kid, score in sorted_ids[:limit]:
            item = all_items[kid]
            item["_score"] = score
            item["_mode"] = item.get("_mode", "hybrid")
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