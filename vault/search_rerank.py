"""Search reranking and ranking-signal helpers."""

from __future__ import annotations

import math
import re
import threading
from typing import List, Optional


def calc_freshness(updated_at: str) -> float:
    """
    計算文件新鮮度分數（0~1）。

    根據更新時間計算，越新分數越高。
    無法解析時返回 0.5。
    """
    from datetime import datetime, timezone

    if not updated_at:
        return 0.5
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        return 1.0 - min(days / 365, 0.5)
    except Exception:
        return 0.5


def calc_usage_boost(result: dict) -> float:
    """Return a small saturated boost from coarse memory usage signals."""
    from datetime import datetime, timezone

    try:
        access_count = max(0, int(result.get("access_count") or 0))
    except (TypeError, ValueError):
        access_count = 0
    try:
        citation_count = max(0, int(result.get("citation_count") or 0))
    except (TypeError, ValueError):
        citation_count = 0

    access_boost = min(0.08, math.log1p(access_count) * 0.018)
    citation_boost = min(0.07, math.log1p(citation_count) * 0.028)

    recency_boost = 0.0
    last_accessed_at = str(result.get("last_accessed_at") or "").strip()
    if last_accessed_at:
        try:
            dt = datetime.fromisoformat(last_accessed_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days)
            recency_boost = max(0.0, 1.0 - min(days / 30, 1.0)) * 0.03
        except Exception:
            recency_boost = 0.0

    return round(min(0.18, access_boost + citation_boost + recency_boost), 6)


def calc_graph_depth(result: dict) -> float:
    """
    計算圖譜深度加成（0~0.2）。

    直接匹配（距離 0）返回 0.2，
    距離越遠加成越少，最少為 0。
    """
    dist = result.get("_graph_distance", 0)
    if dist == 0:
        return 0.2  # 直接匹配，最高加分
    return max(0, 0.2 - (dist - 1) * 0.1)


def _is_active_memory(row: dict) -> bool:
    """Return True when a memory should participate in normal retrieval."""
    return str(row.get("status") or "active").lower() != "archived"


class LightweightReranker:
    """
    輕量級重排序器，無需額外模型。

    在原始檢索分數基礎上，結合多種信號進行精排序：
    - 標題匹配加權（標題中出現查詢詞大幅加分）
    - 多詞匹配獎勵（匹配的詞越多，排名越靠前）
    - 詞頻加權（BM25 風格的詞頻飽和）
    - 位置權重（關鍵詞出現在開頭加分）
    - 向量相似度補充
    - 新鮮度與圖譜深度加成
    """

    def __init__(self):
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: Optional[int] = None,
        text_field: str = "content_raw",
        title_field: str = "title",
    ) -> List[dict]:
        """
        對文檔列表進行輕量重排序。

        Args:
            query: 查詢文本
            documents: 文檔列表
            top_k: 返回前 k 個
            text_field: 文本字段名
            title_field: 標題字段名
        """
        if not documents:
            return documents

        if top_k is None:
            top_k = len(documents)

        # 提取查詢詞（使用與搜尋模塊一致的分詞策略）
        query_terms = self._extract_terms(query)
        if not query_terms:
            return documents[:top_k]

        # 先對原始分數做歸一化
        scores = [d.get("_score", 0.0) for d in documents]
        max_score = max(scores) if scores else 1.0
        min_score = min(scores) if scores else 0.0
        score_range = max_score - min_score if max_score > min_score else 1.0

        scored_docs = []
        for doc in documents:
            title = (doc.get(title_field) or "").lower()
            content = (doc.get(text_field) or "").lower()
            base_score = doc.get("_score", 0.5)

            # 歸一化原始分數到 0~1
            norm_base = (base_score - min_score) / score_range if score_range > 0 else 0.5

            # 計算各種 rerank 特徵
            boost = 0.0  # 正向加成
            penalty = 0.0  # 負向懲罰

            # 1. 標題匹配加成（非常重要）
            title_hit_count = 0
            for term in query_terms:
                if term in title:
                    title_hit_count += 1
            title_match_ratio = title_hit_count / len(query_terms) if query_terms else 0
            boost += title_match_ratio * 2.0  # 最高 +2.0

            # 2. 完全匹配查詢的開頭部分（非常強的信號）
            query_lower = query.lower()
            if title.startswith(query_lower):
                boost += 3.0
            elif query_lower in title:
                boost += 1.5

            # 3. 多詞匹配獎勵
            content_hit_count = 0
            for term in query_terms:
                if term in content:
                    content_hit_count += 1
            content_match_ratio = content_hit_count / len(query_terms) if query_terms else 0

            # 如果同時有多個詞匹配，加成更大
            if content_hit_count >= 2:
                boost += content_match_ratio * 0.5

            # 4. 詞頻加權（BM25 風格，防止高頻詞主導）
            tf_total = 0.0
            for term in query_terms:
                tf = content.count(term) + title.count(term) * 3
                if tf > 0:
                    saturated = (tf * 2.0) / (tf + 1.0)  # BM25 k1=1 風格
                    tf_total += saturated
            tf_score = tf_total / len(query_terms) if query_terms else 0
            boost += tf_score * 0.3

            # 5. 位置加成：第一個關鍵詞出現在內容開頭
            first_pos = float('inf')
            for term in query_terms:
                pos = content.find(term)
                if pos >= 0 and pos < first_pos:
                    first_pos = pos
            if first_pos < float('inf') and len(content) > 0:
                pos_score = 1.0 - (first_pos / min(len(content), 500))
                boost += max(0, pos_score) * 0.3

            # 6. 向量相似度加成（如果有）
            if "_distance" in doc:
                dist = doc["_distance"]
                vec_sim = max(0.0, 1.0 - dist / 2.0)
                boost += vec_sim * 0.5

            # 7. 對只有單詞匹配的文檔稍微降權（避免噪聲）
            total_hits = title_hit_count + content_hit_count
            if total_hits == 1 and len(query_terms) > 2:
                penalty += 0.2

            # 8. 新鮮度加成（來自原有邏輯）
            freshness = doc.get("freshness", None)
            if freshness is None:
                freshness = calc_freshness(doc.get("updated_at", ""))
            freshness = max(0.0, min(1.0, freshness))
            boost += freshness * 0.15

            # 9. 信任度加成（來自原有邏輯）
            trust = doc.get("trust", 0.5)
            boost += trust * 0.15

            # 10. 圖譜深度加成（來自原有邏輯）
            graph_bonus = calc_graph_depth(doc)
            boost += graph_bonus

            # 11. 使用訊號加成：小幅、飽和，只作 tie-break / stability signal
            boost += calc_usage_boost(doc)

            # 組合最終分數：原始分數 + 加成 - 懲罰
            # 原始分數有較高的基礎權重，rerank 主要做微調
            final_score = norm_base * 2.0 + boost - penalty

            doc_copy = dict(doc)
            doc_copy["_original_score"] = base_score  # 保存 rerank 前的原始分數
            doc_copy["_rerank_score"] = round(final_score, 4)
            doc_copy["_score"] = final_score
            # 保持 _mode 不變，向後兼容；rerank 狀態透過 _rerank_score 存在與否判斷
            scored_docs.append(doc_copy)

        # 排序
        scored_docs.sort(key=lambda x: x["_rerank_score"], reverse=True)
        return scored_docs[:top_k]

    @staticmethod
    def _extract_terms(query: str) -> list[str]:
        """提取查詢中的關鍵詞（與搜尋模塊一致的分詞策略）。"""
        # 按原始順序提取所有 token（英文單詞 + 中文連續片段）
        tokens = []

        # 匹配英文單詞（2+ 字母）
        for m in re.finditer(r'[a-zA-Z]{2,}', query):
            tokens.append((m.start(), m.group()))

        # 匹配中文連續片段，做滑動窗口切分
        for m in re.finditer(r'[\u4e00-\u9fff]+', query):
            seg = m.group()
            seg_start = m.start()
            if len(seg) <= 2:
                tokens.append((seg_start, seg))
            else:
                # 保留原詞 + 雙字滑動窗口
                tokens.append((seg_start, seg))  # 原詞
                for i in range(len(seg) - 1):
                    tokens.append((seg_start + i, seg[i:i+2]))

        # 如果沒有提取到任何 token
        if not tokens:
            chars = re.findall(r'[\u4e00-\u9fff]', query)
            if chars:
                return [c.lower() for c in chars]
            return [query.lower()]

        # 按在原文中的位置排序，保持詞序
        tokens.sort(key=lambda x: x[0])

        # 去重，保留順序，轉小寫
        seen = set()
        unique = []
        for _, t in tokens:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                unique.append(t_lower)
        return unique if unique else [query.lower()]


class CrossEncoderReranker:
    """
    Cross-Encoder 重排序器，使用深度學習模型進行精確的相關性評分。

    自動偵測可用的後端：
    - sentence-transformers（優先，支援多種 Cross-Encoder 模型）
    - onnxruntime（輕量級，使用預轉換的 ONNX 模型）

    模型快取：只在第一次呼叫時載入，後續重複使用。

    執行緒安全：類別層級的快取操作已通過 threading.Lock 保護，
    支援多執行緒環境下的安全存取。
    """

    # 類別層級的模型快取，避免多個實例重複載入
    _cached_model = None
    _cached_model_name = None
    _cached_tokenizer = None
    _backend = None  # "sentence_transformers" or "onnxruntime"
    _init_complete = False  # 初始化完成標誌，用於雙重檢查鎖定的安全判斷
    # 快取鎖，保護快取的並發存取
    _cache_lock = threading.Lock()

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._available = False
        self._model = None
        self._tokenizer = None
        self._try_init()

    @staticmethod
    def clear_cache() -> None:
        """
        手動清除 Cross-Encoder 模型快取。

        釋放快取的模型和分詞器，下次建立實例時會重新載入。
        執行緒安全。
        """
        with CrossEncoderReranker._cache_lock:
            CrossEncoderReranker._init_complete = False  # 最先重置
            CrossEncoderReranker._cached_model = None
            CrossEncoderReranker._cached_model_name = None
            CrossEncoderReranker._cached_tokenizer = None
            CrossEncoderReranker._backend = None

    def _try_init(self) -> None:
        """嘗試初始化 Cross-Encoder 模型。"""
        # 優先使用 sentence-transformers
        try:
            from sentence_transformers import CrossEncoder as STCrossEncoder

            # 先在鎖外檢查（雙重檢查鎖定模式）
            # 使用 _init_complete 標誌確保所有快取變數都已完全設定
            if (CrossEncoderReranker._init_complete and
                CrossEncoderReranker._cached_model_name == self._model_name and
                CrossEncoderReranker._backend == "sentence_transformers"):
                self._model = CrossEncoderReranker._cached_model
                self._available = True
                return

            with CrossEncoderReranker._cache_lock:
                # 獲得鎖後再次檢查（雙重檢查鎖定）
                if (CrossEncoderReranker._init_complete and
                    CrossEncoderReranker._cached_model_name == self._model_name and
                    CrossEncoderReranker._backend == "sentence_transformers"):
                    self._model = CrossEncoderReranker._cached_model
                    self._available = True
                    return

                self._model = STCrossEncoder(self._model_name)
                self._available = True
                CrossEncoderReranker._cached_model = self._model
                CrossEncoderReranker._cached_model_name = self._model_name
                CrossEncoderReranker._backend = "sentence_transformers"
                CrossEncoderReranker._init_complete = True  # 最後設定，表示初始化完成
                return
        except (ImportError, Exception):
            pass

        # 備用：使用 onnxruntime + 手動 tokenizer
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            # 先在鎖外檢查（雙重檢查鎖定模式）
            # 使用 _init_complete 標誌確保所有快取變數都已完全設定
            if (CrossEncoderReranker._init_complete and
                CrossEncoderReranker._cached_model_name == self._model_name and
                CrossEncoderReranker._backend == "onnxruntime"):
                self._model = CrossEncoderReranker._cached_model
                self._tokenizer = CrossEncoderReranker._cached_tokenizer
                self._available = True
                return

            with CrossEncoderReranker._cache_lock:
                # 獲得鎖後再次檢查（雙重檢查鎖定）
                if (CrossEncoderReranker._init_complete and
                    CrossEncoderReranker._cached_model_name == self._model_name and
                    CrossEncoderReranker._backend == "onnxruntime"):
                    self._model = CrossEncoderReranker._cached_model
                    self._tokenizer = CrossEncoderReranker._cached_tokenizer
                    self._available = True
                    return

                # 這裡使用簡化的 ONNX 模型載入邏輯
                # 實際佈署時可指定本地模型路徑
                import os
                model_path = os.environ.get("VAULT_CROSS_ENCODER_PATH", "")
                if model_path and os.path.exists(model_path):
                    self._model = ort.InferenceSession(model_path)
                    # 嘗試載入 tokenizer
                    tokenizer_path = os.path.join(os.path.dirname(model_path), "tokenizer.json")
                    if os.path.exists(tokenizer_path):
                        self._tokenizer = Tokenizer.from_file(tokenizer_path)
                    self._available = True
                    CrossEncoderReranker._cached_model = self._model
                    CrossEncoderReranker._cached_tokenizer = self._tokenizer
                    CrossEncoderReranker._cached_model_name = self._model_name
                    CrossEncoderReranker._backend = "onnxruntime"
                    CrossEncoderReranker._init_complete = True  # 最後設定，表示初始化完成
                    return
        except (ImportError, Exception):
            pass

        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: Optional[int] = None,
        text_field: str = "content_raw",
        title_field: str = "title",
    ) -> List[dict]:
        """
        使用 Cross-Encoder 模型對文檔進行重排序。

        Args:
            query: 查詢文本
            documents: 文檔列表
            top_k: 返回前 k 個
            text_field: 文本字段名
            title_field: 標題字段名
        """
        if not documents or not self._available:
            return documents

        if top_k is None:
            top_k = len(documents)

        # 準備配對
        pairs = []
        for doc in documents:
            title = doc.get(title_field, "") or ""
            content = doc.get(text_field, "") or ""
            # 組合標題和內容作為文檔文本
            doc_text = f"{title}\n{content}" if title else content
            # 截斷避免超過模型最大長度
            if len(doc_text) > 512:
                doc_text = doc_text[:512]
            pairs.append([query, doc_text])

        # 計算分數
        scores = self._predict(pairs)

        # 將分數附加到文檔上
        scored_docs = []
        for i, doc in enumerate(documents):
            doc_copy = dict(doc)
            score = float(scores[i]) if i < len(scores) else 0.0
            doc_copy["_original_score"] = doc.get("_score", 0.0)  # 保存 rerank 前的原始分數
            doc_copy["_cross_encoder_score"] = round(score, 4)
            doc_copy["_rerank_score"] = round(score, 4)
            doc_copy["_score"] = score  # 更新最終分數
            scored_docs.append(doc_copy)

        # 排序
        scored_docs.sort(key=lambda x: x["_cross_encoder_score"], reverse=True)
        return scored_docs[:top_k]

    def _predict(self, pairs: List[List[str]]) -> List[float]:
        """執行模型預測，返回分數列表。"""
        if CrossEncoderReranker._backend == "sentence_transformers":
            return self._model.predict(pairs).tolist()

        elif CrossEncoderReranker._backend == "onnxruntime":
            # ONNX 推理邏輯
            all_scores = []
            for pair in pairs:
                # 使用 tokenizer 進行編碼
                if self._tokenizer is not None:
                    encoding = self._tokenizer.encode(pair[0], pair[1])
                    input_ids = encoding.ids
                    attention_mask = [1] * len(input_ids)
                else:
                    # 簡單的字符級 fallback（極限情況）
                    input_ids = [ord(c) % 30522 for c in " ".join(pair)[:512]]
                    attention_mask = [1] * len(input_ids)

                # 確保為 batch 格式
                input_ids = [input_ids]
                attention_mask = [attention_mask]

                # 推理
                outputs = self._model.run(
                    None,
                    {
                        "input_ids": input_ids,
                        "attention_mask": attention_mask,
                    },
                )
                # 取 logits 的第一個值作為相關性分數
                logits = outputs[0]
                if logits.ndim == 2 and logits.shape[1] > 1:
                    # 多分類，取第二個類別的機率（相關）
                    import math
                    score = 1.0 / (1.0 + math.exp(-logits[0][1]))
                else:
                    score = float(logits[0][0]) if logits.ndim == 2 else float(logits[0])
                all_scores.append(score)
            return all_scores

        return [0.0] * len(pairs)
