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
from .access_policy import ReadPolicy, filter_readable_memories, normalize_read_policy
from .temporal import filter_temporal_rows
from .search_graph import apply_graph_expand
from .embed import (
    create_embedding_provider,
    EmbeddingProvider,
)
from .search_rerank import (
    CrossEncoderReranker,
    LightweightReranker,
    _is_active_memory,
    calc_freshness,
    calc_graph_depth,
    calc_usage_boost,
)
from .search_cache import SearchCacheMixin
from .search_query import SearchQueryMixin
from .search_results import SearchResultMixin
from .search_semantic_methods import SearchSemanticMixin
from .search_utils import (
    DEFAULT_KEYWORD_MIN_SCORE,
    MAX_GRAPH_EXPAND_DEPTH,
    MAX_LIMIT,
    _normalize_text,
    normalize_search_limit,
)
from .semantic import SemanticProviderError, provider_dimension, provider_id


class VaultSearch(SearchQueryMixin, SearchCacheMixin, SearchResultMixin, SearchSemanticMixin):
    """Vault-for-LLM 搜尋引擎。"""

    def __init__(
        self,
        db: VaultDB,
        embed_provider=None,
        embed_provider_name: str = "auto",
        embed_model_key: str = "mix",
        graph=None,
        # 混合搜尋權重
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
        # 查詢擴展
        enable_query_expansion: bool = True,
        query_expansion_count: int = 5,
        # 查詢擴展分數衰減（不同擴展類型有不同衰減率）
        # 同義詞替換衰減最小，因為語義最接近
        query_expansion_synonym_decay: float = 0.95,
        # 問句變換衰減中等
        query_expansion_question_decay: float = 0.85,
        # 縮寫/全稱擴展衰減稍大
        query_expansion_abbr_decay: float = 0.90,
        # 關鍵詞提取衰減最大
        query_expansion_keyword_decay: float = 0.75,
        # 可選能力開關（分級掛載）
        enable_vector_search: bool = True,  # 是否允許使用向量檢索
        enable_cross_encoder: bool = True,  # 是否允許使用 cross-encoder rerank
        enable_llm_enhancement: bool = False,  # 是否允許 LLM 驅動的進階功能
        # Rerank 設定
        enable_rerank: bool = True,
        rerank_strategy: str = "auto",  # auto, lightweight, cross_encoder, none
        cross_encoder_model: str = "all-MiniLM-L6-v2",
        # LLM 查詢改寫
        enable_llm_query_rewrite: bool = False,
        llm_query_rewrite_strategy: str = "auto",  # auto, synonym, decompose, keywords
    ):
        self.db = db
        self._embed = embed_provider
        self._embed_provider_name = embed_provider_name
        self._embed_model_key = embed_model_key
        self._graph = graph  # VaultGraph 實例（可選）
        # 混合搜尋權重
        self._keyword_weight = keyword_weight
        self._vector_weight = vector_weight
        # 查詢擴展
        self._enable_query_expansion = enable_query_expansion
        self._query_expansion_count = query_expansion_count
        # 查詢擴展分數衰減參數
        self._query_expansion_synonym_decay = query_expansion_synonym_decay
        self._query_expansion_question_decay = query_expansion_question_decay
        self._query_expansion_abbr_decay = query_expansion_abbr_decay
        self._query_expansion_keyword_decay = query_expansion_keyword_decay
        # 分級能力開關
        self._enable_vector_search = enable_vector_search
        self._enable_cross_encoder = enable_cross_encoder
        self._enable_llm_enhancement = enable_llm_enhancement
        # Rerank 設定
        self._enable_rerank = enable_rerank
        self._rerank_strategy = rerank_strategy
        self._cross_encoder_model = cross_encoder_model
        # LLM 查詢改寫設定
        self._enable_llm_query_rewrite = enable_llm_query_rewrite
        self._llm_query_rewrite_strategy = llm_query_rewrite_strategy
        # 安全模式：捕獲異常並返回空結果，避免洩露內部錯誤信息
        self._safe_mode = False
        # 快取設定
        self._enable_cache = False  # 預設關閉，需要時手動開啟
        self._cache_size = 128
        self._cache_ttl = 60  # 快取有效期（秒）
        self._max_cache_memory_mb = 32  # 快取最大內存使用量（MB）
        self._current_cache_memory = 0  # 當前快取內存使用量（字節）
        # 快取存儲：{cache_key: (timestamp, results, size_bytes)}
        self._cache = {}
        # 快取命中統計
        self._cache_hits = 0
        self._cache_misses = 0
        # 快取已偵測的能力狀態
        self._cached_embed_available = None
        self._cached_rerank_available = None
        self._cached_cross_encoder_available = None
        self._cached_llm_available = None
        # 延遲初始化的 reranker
        self._reranker = None
        self._cross_encoder_reranker = None

        # 參數驗證（P2: Issue N3）
        self._validate_params()

    def _validate_params(self) -> None:
        """
        驗證主要配置參數的有效性。

        確保權重、數量、比例等參數在合理範圍內。
        """
        # 權重參數：必須 >= 0
        if self._keyword_weight < 0:
            raise ValueError(f"keyword_weight 必須 >= 0，當前值: {self._keyword_weight}")
        if self._vector_weight < 0:
            raise ValueError(f"vector_weight 必須 >= 0，當前值: {self._vector_weight}")

        # 數量參數：必須 >= 0 且有上限
        MAX_QUERY_EXPANSIONS = 20
        if self._query_expansion_count < 0:
            raise ValueError(f"query_expansion_count 必須 >= 0，當前值: {self._query_expansion_count}")
        if self._query_expansion_count > MAX_QUERY_EXPANSIONS:
            raise ValueError(
                f"query_expansion_count 不能超過 {MAX_QUERY_EXPANSIONS}，"
                f"當前值: {self._query_expansion_count}"
            )

        # 比例參數：必須在 0-1 範圍
        decay_params = [
            ("query_expansion_synonym_decay", self._query_expansion_synonym_decay),
            ("query_expansion_question_decay", self._query_expansion_question_decay),
            ("query_expansion_abbr_decay", self._query_expansion_abbr_decay),
            ("query_expansion_keyword_decay", self._query_expansion_keyword_decay),
        ]
        for name, value in decay_params:
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{name} 必須在 0-1 範圍內，當前值: {value}")

        # 驗證 rerank_strategy
        valid_strategies = {"auto", "lightweight", "cross_encoder", "none"}
        if self._rerank_strategy not in valid_strategies:
            raise ValueError(
                f"rerank_strategy 必須是 {valid_strategies} 之一，當前值: {self._rerank_strategy}"
            )

        # 驗證 llm_query_rewrite_strategy
        valid_rewrite_strategies = {"auto", "synonym", "decompose", "keywords"}
        if self._llm_query_rewrite_strategy not in valid_rewrite_strategies:
            raise ValueError(
                f"llm_query_rewrite_strategy 必須是 {valid_rewrite_strategies} 之一，"
                f"當前值: {self._llm_query_rewrite_strategy}"
            )

        # 驗證 cross_encoder_model 格式（防範路徑遍歷風險）
        import re
        if not re.match(r'^[a-zA-Z0-9_\-/]+$', self._cross_encoder_model):
            raise ValueError(
                f"cross_encoder_model 格式無效，僅允許字母、數字、下劃線、連字符和斜線，"
                f"當前值: {self._cross_encoder_model}"
            )

    @property
    def has_embeddings(self) -> bool:
        """檢查是否有向量搜尋能力（含開關檢查）。"""
        if not self._enable_vector_search:
            return False
        # 保持向後兼容：僅檢查已設置的 embed_provider，不觸發自動創建
        return self._embed is not None and bool(getattr(self.db, '_vec_available', False))

    @property
    def has_reranker(self) -> bool:
        """檢查是否有 rerank 能力（含開關檢查）。"""
        if not self._enable_rerank:
            return False
        if self._cached_rerank_available is not None:
            return self._cached_rerank_available
        reranker = self._get_reranker()
        available = reranker is not None and reranker.available
        self._cached_rerank_available = available
        return available

    @property
    def has_cross_encoder(self) -> bool:
        """檢查是否有 cross-encoder 重排序能力。"""
        if not self._enable_cross_encoder or not self._enable_rerank:
            return False
        if self._cached_cross_encoder_available is not None:
            return self._cached_cross_encoder_available
        # 嘗試初始化 CrossEncoderReranker 來偵測可用性
        try:
            reranker = CrossEncoderReranker(model_name=self._cross_encoder_model)
            available = reranker.available
        except Exception:
            available = False
        self._cached_cross_encoder_available = available
        return available

    @property
    def has_llm(self) -> bool:
        """檢查是否有 LLM 能力（用於查詢改寫等進階功能）。"""
        if not self._enable_llm_enhancement:
            return False
        if self._cached_llm_available is not None:
            return self._cached_llm_available
        try:
            from .llm import create_llm_provider
            llm = create_llm_provider()
            available = llm is not None
        except Exception:
            available = False
        self._cached_llm_available = available
        return available

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

    def _get_reranker(self):
        """
        延遲初始化 reranker。

        根據策略返回對應的 reranker：
        - auto: 優先使用 cross-encoder（若可用），否則使用 lightweight
        - cross_encoder: 僅使用 cross-encoder
        - lightweight: 僅使用 lightweight
        - none: 不使用 reranker
        """
        if not self._enable_rerank or self._rerank_strategy == "none":
            return None

        # 嘗試獲取 cross-encoder reranker
        if self._rerank_strategy in ("auto", "cross_encoder") and self._enable_cross_encoder:
            ce_reranker = self._get_cross_encoder_reranker()
            if ce_reranker is not None and ce_reranker.available:
                return ce_reranker
            # 如果是強制 cross_encoder 策略但不可用，返回 None
            if self._rerank_strategy == "cross_encoder":
                return None

        # fallback 到 lightweight
        if self._reranker is not None:
            return self._reranker if self._reranker.available else None
        try:
            self._reranker = LightweightReranker()
            return self._reranker if self._reranker and self._reranker.available else None
        except Exception:
            return None

    def _get_cross_encoder_reranker(self) -> Optional[CrossEncoderReranker]:
        """延遲初始化 cross-encoder reranker。"""
        if not self._enable_cross_encoder or not self._enable_rerank:
            return None
        if self._cross_encoder_reranker is not None:
            return self._cross_encoder_reranker if self._cross_encoder_reranker.available else None
        try:
            self._cross_encoder_reranker = CrossEncoderReranker(
                model_name=self._cross_encoder_model,
            )
            return self._cross_encoder_reranker if self._cross_encoder_reranker.available else None
        except Exception:
            return None

    # 同義詞詞典（用於查詢擴展）- 同時支援繁簡體

    # 繁簡中文常見轉換映射（用於問句模式匹配）


    # ── 快取管理 ──────────────────────────────────────────


    def info(self) -> dict:
        """
        取得目前可用的搜尋能力摘要。

        Returns:
            dict: 包含各層級能力狀態與配置的字典
                  同時提供中文與英文鍵名，保持向後兼容
        """
        basic_layer = {
            "關鍵詞搜尋": True,
            "keyword_search": True,
            "輕量級重排序": self._enable_rerank,
            "lightweight_rerank": self._enable_rerank,
            "查詢擴展": self._enable_query_expansion,
            "query_expansion": self._enable_query_expansion,
            "文件地圖支援": self._graph is not None,
            "document_map_support": self._graph is not None,
        }

        advanced_layer = {
            "向量檢索": self.has_embeddings,
            "vector_search": self.has_embeddings,
            "混合搜尋": self.has_embeddings,
            "hybrid_search": self.has_embeddings,
            "語義索引": self.has_embeddings,
            "semantic_index": self.has_embeddings,
        }

        premium_layer = {
            "Cross-Encoder 重排序": self.has_cross_encoder,
            "cross_encoder_rerank": self.has_cross_encoder,
            "Cross-Encoder 模型": self._cross_encoder_model if self.has_cross_encoder else None,
            "cross_encoder_model": self._cross_encoder_model if self.has_cross_encoder else None,
        }

        flagship_layer = {
            "LLM 查詢改寫": self.has_llm and self._enable_llm_query_rewrite,
            "llm_query_rewrite": self.has_llm and self._enable_llm_query_rewrite,
            "LLM 改寫策略": self._llm_query_rewrite_strategy,
            "llm_rewrite_strategy": self._llm_query_rewrite_strategy,
        }

        config_layer = {
            "預設模式": "hybrid" if self.has_embeddings else "keyword",
            "default_mode": "hybrid" if self.has_embeddings else "keyword",
            "關鍵詞權重": self._keyword_weight,
            "keyword_weight": self._keyword_weight,
            "向量權重": self._vector_weight,
            "vector_weight": self._vector_weight,
            "Rerank 策略": self._rerank_strategy,
            "rerank_strategy": self._rerank_strategy,
            "Rerank 開關": self._enable_rerank,
            "rerank_enabled": self._enable_rerank,
            "查詢擴展數量": self._query_expansion_count,
            "query_expansion_count": self._query_expansion_count,
            "查詢擴展開關": self._enable_query_expansion,
            "query_expansion_enabled": self._enable_query_expansion,
            "向量搜尋開關": self._enable_vector_search,
            "vector_search_enabled": self._enable_vector_search,
            "Cross-Encoder 開關": self._enable_cross_encoder,
            "cross_encoder_enabled": self._enable_cross_encoder,
            "LLM 增強開關": self._enable_llm_enhancement,
            "llm_enhancement_enabled": self._enable_llm_enhancement,
            "LLM 查詢改寫開關": self._enable_llm_query_rewrite,
            "llm_query_rewrite_enabled": self._enable_llm_query_rewrite,
            "嵌入提供者": self._embed_provider_name,
            "embedding_provider": self._embed_provider_name,
            "嵌入模型": self._embed_model_key,
            "embedding_model": self._embed_model_key,
        }

        caps = {
            "基礎層": basic_layer,
            "basic": basic_layer,
            "進階層": advanced_layer,
            "advanced": advanced_layer,
            "高階層": premium_layer,
            "premium": premium_layer,
            "旗艦層": flagship_layer,
            "flagship": flagship_layer,
            "配置": config_layer,
            "config": config_layer,
        }
        return caps

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
            msg = str(exc).lower()
            return "fts5" in msg or "全文搜尋" in msg
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
        offset: int = 0,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        graph_expand: int = 0,
        use_rerank: bool = True,
        compact: bool = False,
        semantic_vector_kind: str = "claim",
        allow_hash: bool = False,
        min_score: float | None = None,
        use_query_expansion: bool = True,
        use_llm_rewrite: bool = False,
        normalize_scores: bool = False,
        include_snippet: bool = False,
        highlight_snippet: bool = False,
        fields: Optional[list[str]] = None,
        agent_id: str = "",
        include_private: bool = False,
        max_sensitivity: str = "",
        include_expired_temporal: bool = True,
        include_future_temporal: bool = True,
        temporal_as_of: str = "",
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
        use_query_expansion: 是否使用查詢擴展（預設 True）
        use_llm_rewrite: 是否使用 LLM 查詢改寫（預設 False）
        min_score: 最小分數閾值，僅返回分數 >= min_score 的結果。
                   注意：不同模式的分數含義不同——
                   - keyword 模式：匹配詞比例（0-1）
                   - vector 模式：轉換後的餘弦相似度（0-1）
                   - hybrid 模式：RRF 融合分數（範圍較大）
                   設置時請考慮不同模式的分數分佈差異。
                   若開啟 normalize_scores，則所有模式分數統一為 0-1 範圍。
        normalize_scores: 是否將結果分數標準化到 0-1 範圍（預設 False）
                          開啟後，不同模式的分數具有可比性，min_score 可使用統一閾值。
        include_snippet: 是否生成搜尋結果片段（預設 False）
                         開啟後每個結果會包含 _snippet 欄位，顯示與查詢最相關的上下文。
        highlight_snippet: 是否在片段中高亮匹配的關鍵詞（預設 False）
                           使用 <em> 標籤包裹匹配詞，需與 include_snippet 同時開啟。
        offset: 分頁偏移量（預設 0），跳過前 offset 條結果。
                與 limit 配合使用實現分頁，offset 最大為 9999。
        fields: 指定返回的欄位列表（預設 None 返回全部欄位）。
                常用欄位：id, title, category, layer, trust, _score, _snippet,
                         content_raw, content_aaak, tags, source, summary。
                指定後僅返回列表中的欄位，減少數據傳輸量。
                內部欄位（_score, _snippet 等）需顯式包含。
        """
        # 安全模式：捕獲異常返回空結果，避免洩露內部錯誤信息
        if self._safe_mode:
            try:
                return self._do_search(
                    query, mode, limit, offset, min_trust, layer, category,
                    graph_expand, use_rerank, compact, semantic_vector_kind,
                    allow_hash, min_score, use_query_expansion, use_llm_rewrite,
                    normalize_scores, include_snippet, highlight_snippet, fields,
                    agent_id, include_private, max_sensitivity,
                    include_expired_temporal, include_future_temporal, temporal_as_of,
                )
            except (ValueError, TypeError):
                raise  # 參數驗證錯誤仍然拋出
            except Exception:
                return []

        return self._do_search(
            query, mode, limit, offset, min_trust, layer, category,
            graph_expand, use_rerank, compact, semantic_vector_kind,
            allow_hash, min_score, use_query_expansion, use_llm_rewrite,
            normalize_scores, include_snippet, highlight_snippet, fields,
            agent_id, include_private, max_sensitivity,
            include_expired_temporal, include_future_temporal, temporal_as_of,
        )

    def _do_search(
        self,
        query: str,
        mode: str = "auto",
        limit: int = 10,
        offset: int = 0,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        graph_expand: int = 0,
        use_rerank: bool = True,
        compact: bool = False,
        semantic_vector_kind: str = "claim",
        allow_hash: bool = False,
        min_score: float | None = None,
        use_query_expansion: bool = True,
        use_llm_rewrite: bool = False,
        normalize_scores: bool = False,
        include_snippet: bool = False,
        highlight_snippet: bool = False,
        fields: Optional[list[str]] = None,
        agent_id: str = "",
        include_private: bool = False,
        max_sensitivity: str = "",
        include_expired_temporal: bool = True,
        include_future_temporal: bool = True,
        temporal_as_of: str = "",
    ) -> list[dict]:
        """內部搜尋實現。"""
        read_policy = normalize_read_policy(
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        )
        # 驗證 mode 參數
        valid_modes = {"auto", "basic", "keyword", "vector", "semantic", "hybrid"}
        if mode not in valid_modes:
            raise ValueError(
                f"無效的搜尋模式: {mode!r}. 有效模式: {sorted(valid_modes)}"
            )
        # 向後相容：basic 是 auto 的別名
        if mode == "basic":
            mode = "auto"

        # ── 安全防線：空查詢 / None 檢查 ──
        if query is None or not isinstance(query, str) or not query.strip():
            return []

        # 計算快取鍵（無論是否啟用快取都計算，方便後續使用）
        cache_key = None
        if self._enable_cache:
            cache_key = self._get_cache_key(
                query=query,
                mode=mode,
                limit=limit,
                offset=offset,
                min_trust=min_trust,
                layer=layer,
                category=category,
                graph_expand=graph_expand,
                use_rerank=use_rerank,
                compact=compact,
                min_score=min_score,
                use_query_expansion=use_query_expansion,
                use_llm_rewrite=use_llm_rewrite,
                normalize_scores=normalize_scores,
                include_snippet=include_snippet,
                highlight_snippet=highlight_snippet,
                fields=",".join(sorted(fields)) if fields else "",
                semantic_vector_kind=semantic_vector_kind,
                allow_hash=allow_hash,
                agent_id=read_policy.agent_id,
                include_private=read_policy.include_private,
                max_sensitivity=read_policy.max_sensitivity,
                include_expired_temporal=include_expired_temporal,
                include_future_temporal=include_future_temporal,
                temporal_as_of=temporal_as_of,
                embed_provider=self._embed_cache_identity(),
                rerank_strategy=self._rerank_strategy,
            )
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self._record_result_usage(cached)
                return cached

        # ── 安全防線：min_score 範圍驗證 ──
        if min_score is not None:
            if not isinstance(min_score, (int, float)):
                min_score = None
            elif min_score < 0:
                min_score = 0.0

        # ── 安全防線：查詢長度限制 ──
        MAX_QUERY_LENGTH = 1000
        if len(query) > MAX_QUERY_LENGTH:
            query = query[:MAX_QUERY_LENGTH]

        # ── 安全防線：limit 邊界保護 ──
        limit = normalize_search_limit(limit)
        if limit <= 0:
            return []

        # ── 安全防線：offset 邊界驗證 ──
        # 降低 MAX_OFFSET 從 9999 → 2000，配合 MAX_SEARCH_WINDOW 防止深分頁 DoS
        MAX_OFFSET = 2000
        if not isinstance(offset, int) or offset < 0:
            offset = 0
        if offset > MAX_OFFSET:
            offset = MAX_OFFSET

        # 為分頁預留偏移量：搜尋階段多取 offset 筆，最後再切片
        # 安全限制：搜尋窗口上限 = MAX_OFFSET + MAX_LIMIT，防止深分頁導致性能問題
        MAX_SEARCH_WINDOW = MAX_OFFSET + MAX_LIMIT
        _page_limit = limit
        if offset > 0:
            search_limit = limit + offset
            if search_limit > MAX_SEARCH_WINDOW:
                # 超出搜尋窗口，調整實際可返回的數量
                search_limit = MAX_SEARCH_WINDOW
                _page_limit = max(0, MAX_SEARCH_WINDOW - offset)
            limit = min(search_limit, MAX_LIMIT + MAX_OFFSET)

        # ── 安全防線：圖譜擴展深度上限 ──
        if graph_expand > MAX_GRAPH_EXPAND_DEPTH:
            graph_expand = MAX_GRAPH_EXPAND_DEPTH
        if graph_expand < 0:
            graph_expand = 0

        # LLM 查詢改寫：在查詢擴展之前進行
        if use_llm_rewrite and self._enable_llm_query_rewrite and self.has_llm:
            query = self._rewrite_query_with_llm(query)

        # 查詢擴展：生成多種說法的查詢，提升召回率
        if use_query_expansion and self._enable_query_expansion:
            queries = self._expand_query(query)
        else:
            queries = [(query, 1.0)]

        # 執行搜尋
        all_results = []
        for q_text, q_weight in queries:
            if mode == "keyword":
                results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)
            elif mode == "vector":
                if self.has_embeddings:
                    results = self.search_vector(q_text, limit * 2, min_trust, layer, category)
                    if not results:
                        results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)
                    else:
                        results = results[:limit]
                else:
                    results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)
            elif mode == "semantic":
                # semantic mode: use stored semantic_vectors table
                # Only try semantic search if a provider is available.
                # Wrap in try/except to gracefully fall back to keyword if the
                # provider fails (e.g., missing dependencies for lazy-loaded providers).
                # SemanticProviderError is intentionally re-raised as it signals
                # a configuration error (using hash provider with require_semantic=True).
                try:
                    if self._embed is not None:
                        results = self.search_semantic(
                            q_text,
                            limit,
                            min_trust,
                            layer,
                            category,
                            vector_kind=semantic_vector_kind,
                            require_semantic=not allow_hash,
                            allow_hash=allow_hash,
                        )
                    else:
                        # No embed provider configured — fall back to keyword
                        results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)
                except SemanticProviderError:
                    raise
                except Exception:
                    # Provider failed (missing dependencies, etc.) — fall back to keyword
                    results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)
            elif mode == "hybrid":
                # hybrid mode combines keyword + second source (semantic or vector)
                # search_hybrid handles fallbacks internally, so try it if any second source might be available
                has_second_source = (
                    self.has_embeddings
                    or self._semantic_index_available(
                        semantic_vector_kind,
                        require_semantic=not allow_hash,
                        allow_hash=allow_hash,
                    )
                )
                if has_second_source:
                    results = self.search_hybrid(
                        q_text,
                        limit,
                        min_trust,
                        layer,
                        category,
                        semantic_vector_kind=semantic_vector_kind,
                        allow_hash=allow_hash,
                        min_score=min_score,
                    )
                else:
                    results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)
            else:
                # auto: choose the best available search strategy
                # Priority: hybrid (with semantic) > hybrid (with vector) > keyword
                if self._semantic_index_available(
                    semantic_vector_kind,
                    require_semantic=not allow_hash,
                    allow_hash=allow_hash,
                ):
                    # Has semantic index — use hybrid search for best results
                    results = self.search_hybrid(
                        q_text,
                        limit,
                        min_trust,
                        layer,
                        category,
                        semantic_vector_kind=semantic_vector_kind,
                        allow_hash=allow_hash,
                        min_score=min_score,
                    )
                elif self.has_embeddings:
                    # Has vector search — use hybrid with vector
                    results = self.search_hybrid(
                        q_text,
                        limit,
                        min_trust,
                        layer,
                        category,
                        semantic_vector_kind=semantic_vector_kind,
                        allow_hash=allow_hash,
                        min_score=min_score,
                    )
                else:
                    # Only keyword search available
                    results = self.search_keyword(q_text, limit, min_trust, layer, category, min_score=min_score)

            # 根據擴展查詢的權重衰減分數
            if q_weight < 1.0:
                for r in results:
                    r["_score"] = r.get("_score", 0) * q_weight
                    r["_expanded_query"] = q_text

            all_results.extend(results)

        # 多查詢結果合併去重
        if len(queries) > 1:
            merged: dict[int, dict] = {}
            for r in all_results:
                kid = r["id"]
                if kid not in merged or r.get("_score", 0) > merged[kid].get("_score", 0):
                    merged[kid] = r
            results = sorted(merged.values(), key=lambda x: x.get("_score", 0), reverse=True)
            results = results[:limit]
        else:
            results = all_results

        # 圖譜擴展
        if graph_expand > 0 and self._graph is not None:
            results = apply_graph_expand(
                self.db,
                results,
                expand_depth=graph_expand,
                limit=limit,
                min_trust=min_trust,
                layer=layer,
                category=category,
                read_policy=read_policy,
            )

        results = [r for r in results if _is_active_memory(r)]
        results = filter_readable_memories(results, read_policy)
        results = filter_temporal_rows(
            results,
            include_expired=include_expired_temporal,
            include_future=include_future_temporal,
            as_of=temporal_as_of,
        )

        # Reranker
        if use_rerank and results:
            results = self._rerank_with_strategy(results, query=query)

        # 提取 best_claim
        for r in results:
            if not r.get("best_claim"):
                r["best_claim"] = self._extract_best_claim(r.get("content_aaak", ""))

        # Document Map enrichment（best span / node / citation）
        if results:
            self._enrich_with_document_map(results, query)

        # 分數標準化（0-1 範圍）
        if normalize_scores and results:
            scores = [r.get("_score", 0.0) for r in results]
            max_score = max(scores)
            min_score_val = min(scores)
            score_range = max_score - min_score_val
            if score_range > 0:
                for r in results:
                    original = r.get("_score", 0.0)
                    r["_original_score"] = original
                    r["_score"] = round((original - min_score_val) / score_range, 4)
            else:
                # 所有分數相同，全部設為 1.0
                for r in results:
                    r["_original_score"] = r.get("_score", 0.0)
                    r["_score"] = 1.0

        # 生成搜尋結果片段
        if include_snippet and results and query:
            for r in results:
                # 優先使用 content_aaak，其次使用 content_raw
                content = r.get("content_aaak", "") or r.get("content_raw", "")
                if content:
                    r["_snippet"] = self._generate_snippet(
                        content, query, highlight=highlight_snippet
                    )
                else:
                    r["_snippet"] = ""

        # ── 分頁切片 ──
        if offset > 0 and results:
            results = results[offset:offset + _page_limit]

        # ── 存入快取 ──
        if cache_key is not None:
            self._set_to_cache(cache_key, results)

        self._record_result_usage(results)

        if compact:
            return [self._compact_result(r) for r in results]

        # 欄位過濾（僅在非 compact 模式下生效）
        if fields and results:
            field_set = set(fields)
            results = [{k: v for k, v in r.items() if k in field_set} for r in results]

        return results

    def _record_result_usage(self, results: list[dict]) -> None:
        """Best-effort usage telemetry; search must not fail because of it."""
        if not results or self.db.conn is None:
            return
        try:
            knowledge_ids = [int(r["id"]) for r in results if r.get("id")]
            self.db.record_knowledge_access(knowledge_ids)
        except Exception:
            return

    # ── Document Map enrichment ─────────────────────────────


    # ── Reranker ──────────────────────────────────────────


    # ── 原子主張提取 ──────────────────────────────────────


    # ── 關鍵字搜尋 ──────────────────────────────────────────

    def search_keyword(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        min_score: float | None = None,
        use_bm25_score: bool = False,
    ) -> list[dict]:
        """
        Keyword search with optional FTS5/BM25 and LIKE fallback.

        Args:
            use_bm25_score: 若為 True，使用 BM25 分數作為基礎分數（經過正規化），
                           這會比簡單的匹配率更準確。預設 False 以保持向後兼容。
        """
        limit = normalize_search_limit(limit)
        if limit <= 0:
            return []
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

                # 根據 use_bm25_score 參數選擇分數計算方式（P1: Issue 17）
                if use_bm25_score and bm25_score > 0:
                    # 使用 BM25 分數，經過正規化使其範圍在 0-1
                    # BM25 分數通常在 0-30 左右，正規化到 0-1
                    d["_score"] = min(1.0, bm25_score / 15.0)
                else:
                    # 使用簡單的匹配率（預設行為，保持向後兼容）
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
        # 空查詢直接返回空結果
        if not terms:
            return []

        # 轉義 LIKE 特殊字符，防止通配符注入
        def _escape_like_pattern(term: str) -> str:
            return term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

        # 建構 WHERE 條件
        conditions = []
        params: list = [min_trust]

        for term in terms:
            conditions.append(
                "(title LIKE ? ESCAPE '\\' OR content_raw LIKE ? ESCAPE '\\' "
                "OR content_aaak LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' "
                "OR category LIKE ? ESCAPE '\\')"
            )
            escaped = _escape_like_pattern(term)
            pattern = f"%{escaped}%"
            params.extend([pattern] * 5)

        where = f"trust >= ? AND ({' OR '.join(conditions)})" if len(terms) > 1 else f"trust >= ? AND {conditions[0]}"
        where += " AND COALESCE(status, 'active') != 'archived'"

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


    # ── Stored semantic index search ─────────────────────────


    # ── 混合搜尋（RRF） ────────────────────────────────────


    # ── Compatibility wrappers ──────────────────────────────────────────


    # ── 工具 ──────────────────────────────────────────────
