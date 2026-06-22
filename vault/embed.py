"""
Vault-for-LLM — 嵌入生成模組。

支援三種嵌入來源：
1. ONNX Runtime（本地模型，不需要 PyTorch 2GB+）
2. Ollama（已有 Ollama 的人零額外安裝）
3. sentence-transformers（降級方案，需要 PyTorch）

預設 ONNX 模型：
- 中文：BAAI/bge-small-zh-v1.5 (512d, ~90MB)
- 英文：sentence-transformers/all-MiniLM-L6-v2 (384d, ~40MB)
- 混合：sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384d, ~200MB)
"""

import os
import importlib.util
import time
from pathlib import Path
from typing import Optional

from .log import log

# ── 模型定義 ─────────────────────────────────────────────

MODELS = {
    "zh": {
        "name": "BAAI/bge-small-zh-v1.5",
        "dim": 512,
        "onnx_file": "model.onnx",
        "size_mb": 90,
        "language": "中文",
    },
    "en": {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "onnx_file": "model.onnx",
        "size_mb": 40,
        "language": "英文",
    },
    "mix": {
        "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "dim": 384,
        "onnx_file": "model.onnx",
        "size_mb": 200,
        "language": "中英混合",
    },
}

DEFAULT_MODEL_KEY = "mix"


def _load_auto_tokenizer(auto_tokenizer_cls, model_or_path: str):
    """Load tokenizer with newer mistral-regex fix when supported."""
    try:
        return auto_tokenizer_cls.from_pretrained(
            model_or_path,
            fix_mistral_regex=True,
        )
    except TypeError:
        return auto_tokenizer_cls.from_pretrained(model_or_path)


class EmbeddingProvider:
    """嵌入生成基底類別。"""

    provider_id = "embedding-provider"
    is_semantic = True

    def __init__(self, dim: int = 384):
        self._dim = dim
        self._metrics = {
            "encode_calls": 0,
            "encoded_texts": 0,
            "http_requests": 0,
            "http_retries": 0,
            "http_retry_after_delays": 0,
            "http_failures": 0,
            "last_latency_ms": 0.0,
        }

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        raise NotImplementedError

    @property
    def dim(self) -> int:
        return self._dim

    def _record_encode(self, text_count: int, started_at: float) -> None:
        self._metrics["encode_calls"] += 1
        self._metrics["encoded_texts"] += int(text_count)
        self._metrics["last_latency_ms"] = round((time.perf_counter() - started_at) * 1000, 6)

    def get_metrics(self) -> dict:
        return dict(self._metrics)

    def reset_metrics(self) -> None:
        for key in self._metrics:
            self._metrics[key] = 0.0 if key == "last_latency_ms" else 0


class ONNXEmbeddingProvider(EmbeddingProvider):
    """用 ONNX Runtime 跑嵌入模型。不需要 PyTorch。"""

    is_semantic = True

    def __init__(self, model_key: str = "mix", cache_dir: Optional[str] = None):
        super().__init__(dim=MODELS[model_key]["dim"])
        self.model_key = model_key
        self.model_info = MODELS[model_key]
        self.provider_id = f"onnx:{self.model_info['name']}"
        self._dim = self.model_info["dim"]
        self.cache_dir = Path(cache_dir or os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))) / "vault-mcp" / "models"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = None
        self._tokenizer = None

    def _ensure_model(self):
        """確保 ONNX 模型檔存在，不存在就下載。"""
        model_name = self.model_info["name"]
        model_dir = self.cache_dir / model_name.replace("/", "--")
        onnx_path = model_dir / self.model_info["onnx_file"]

        if onnx_path.exists():
            return onnx_path

        # 下載 + 轉換 ONNX
        log.info(f"下載 {model_name} → ONNX...")
        model_dir.mkdir(parents=True, exist_ok=True)

        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer

            tokenizer = _load_auto_tokenizer(AutoTokenizer, model_name)
            model = ORTModelForFeatureExtraction.from_pretrained(
                model_name, export=True
            )
            model.save_pretrained(model_dir)
            tokenizer.save_pretrained(model_dir)
            log.info(f"✅ 模型已下載到 {model_dir}")
            return model_dir / self.model_info["onnx_file"]
        except Exception as e:
            raise RuntimeError(
                f"下載/轉換 ONNX 模型失敗: {e}\n"
                f"請確認有網路連線，或手動下載模型到 {model_dir}"
            )

    def _load_session(self):
        """延遲載入 ONNX session。"""
        if self._session is not None:
            return

        import onnxruntime as ort
        from transformers import AutoTokenizer

        model_name = self.model_info["name"]
        model_dir = self.cache_dir / model_name.replace("/", "--")
        onnx_path = model_dir / self.model_info["onnx_file"]

        if not onnx_path.exists():
            self._ensure_model()

        # 載入 tokenizer
        self._tokenizer = _load_auto_tokenizer(AutoTokenizer, str(model_dir))

        # 載入 ONNX session
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(str(onnx_path), sess_options)
        log.info(f"✅ ONNX 模型已載入 ({self.model_info['language']})")

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        """生成嵌入向量。"""
        started_at = time.perf_counter()
        self._load_session()

        if isinstance(texts, str):
            texts = [texts]

        # Tokenize
        encoded = self._tokenizer(
            texts, padding=True, truncation=True, max_length=512, return_tensors="np"
        )

        # 推理
        inputs = {
            k: v for k, v in encoded.items()
            if k in ["input_ids", "attention_mask", "token_type_ids"]
            and k in {inp.name for inp in self._session.get_inputs()}
        }
        outputs = self._session.run(None, inputs)

        # Mean Pooling（跟 sentence-transformers 一致）
        import numpy as np
        token_embeddings = outputs[0]  # (batch, seq_len, dim)
        attention_mask = encoded["attention_mask"]

        # 擴展 mask 維度以匹配 embeddings
        mask_expanded = np.expand_dims(attention_mask, -1).astype(float)
        # 對 padding token 做 mask
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        mean_embeddings = sum_embeddings / sum_mask

        # Normalize
        norms = np.linalg.norm(mean_embeddings, axis=1, keepdims=True)
        normalized = mean_embeddings / np.clip(norms, a_min=1e-9, a_max=None)

        result = normalized.tolist()
        self._record_encode(len(texts), started_at)
        return result


class OllamaEmbeddingProvider(EmbeddingProvider):
    """用 Ollama API 做嵌入。適合已有 Ollama 的人。"""

    is_semantic = True

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        dim: int = 768,
        max_retries: int = 1,
        retry_backoff: float = 0.25,
        max_retry_after: float = 5.0,
    ):
        super().__init__(dim=dim)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.provider_id = f"ollama:{self.base_url}:{self.model}"
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = max(0.0, float(retry_backoff))
        self.max_retry_after = max(0.0, float(max_retry_after))

    @property
    def dim(self) -> int:
        # 動態偵測維度（首次呼叫時）
        if self._dim is None:
            test = self.encode("test")
            self._dim = len(test[0])
        return self._dim

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        import urllib.request
        import urllib.error
        import json as _json
        started_at = time.perf_counter()

        if isinstance(texts, str):
            texts = [texts]

        # 優先嘗試 batch API (/api/embed)，失敗降級到單條 (/api/embeddings)
        if len(texts) > 1:
            try:
                payload = _json.dumps({
                    "model": self.model,
                    "input": texts,
                }).encode()

                req = urllib.request.Request(
                    f"{self.base_url}/api/embed",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )

                with self._urlopen_with_retry(req, timeout=max(60, len(texts) * 5)) as resp:
                    data = _json.loads(resp.read())
                    # /api/embed 回傳 {"model":..., "embeddings": [[...], ...]}
                    if "embeddings" in data:
                        results = data["embeddings"]
                        if results and self._dim is None:
                            self._dim = len(results[0])
                        self._record_encode(len(texts), started_at)
                        return results
            except (urllib.error.HTTPError, urllib.error.URLError, KeyError):
                pass  # 降級到單條

        # 單條或 batch 降級
        results = []
        for text in texts:
            payload = _json.dumps({
                "model": self.model,
                "prompt": text,
            }).encode()

            req = urllib.request.Request(
                f"{self.base_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )

            with self._urlopen_with_retry(req, timeout=max(30, len(texts) * 5)) as resp:
                data = _json.loads(resp.read())
                results.append(data["embedding"])

        # 只在首次偵測時設定維度（避免每次 encode 重設）
        if results and self._dim is None:
            self._dim = len(results[0])

        self._record_encode(len(texts), started_at)
        return results

    def _urlopen_with_retry(self, req, timeout: int):
        import urllib.request
        import urllib.error

        attempts = self.max_retries + 1
        last_exc = None
        for attempt in range(attempts):
            self._metrics["http_requests"] += 1
            try:
                return urllib.request.urlopen(req, timeout=timeout)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    self._metrics["http_failures"] += 1
                    raise
                self._metrics["http_retries"] += 1
                delay = self._retry_delay(exc, attempt)
                if delay > 0:
                    time.sleep(delay)
        raise last_exc

    def _retry_delay(self, exc: Exception, attempt: int) -> float:
        retry_after = self._retry_after_seconds(exc)
        if retry_after is not None:
            self._metrics["http_retry_after_delays"] += 1
            return retry_after
        return self.retry_backoff * (2 ** attempt) if self.retry_backoff else 0.0

    def _retry_after_seconds(self, exc: Exception) -> float | None:
        import urllib.error

        if not isinstance(exc, urllib.error.HTTPError):
            return None
        if exc.code not in {429, 503}:
            return None
        headers = getattr(exc, "headers", None)
        value = headers.get("Retry-After") if headers is not None else None
        if value is None:
            return None
        try:
            seconds = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        if seconds <= 0:
            return 0.0
        return min(seconds, self.max_retry_after)


class SentenceTransformerProvider(EmbeddingProvider):
    """降級方案：用sentence-transformers（需要PyTorch）。"""

    is_semantic = True

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        super().__init__(dim=0)
        self.model_name = model_name
        self.provider_id = f"sentence-transformers:{model_name}"
        self._model = None
        self._dim = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        started_at = time.perf_counter()
        self._load()
        if isinstance(texts, str):
            texts = [texts]
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        result = embeddings.tolist()
        self._record_encode(len(texts), started_at)
        return result

    @property
    def dim(self) -> int:
        self._load()
        return self._dim


def create_embedding_provider(
    provider: str = "auto",
    model_key: str = "mix",
    cache_dir: Optional[str] = None,
    ollama_model: str = "nomic-embed-text",
    ollama_url: str = "http://localhost:11434",
) -> EmbeddingProvider:
    """
    工廠函數，建立嵌入 provider。

    provider:
    - "auto": 偵測環境自動選擇（ONNX > Ollama > sentence-transformers）
    - "onnx": ONNX Runtime
    - "ollama": Ollama API
    - "sentence-transformers": PyTorch 降級方案
    - "hash": 確定性哈希嵌入（輕量，無外部依賴，用於測試）
    """
    if provider == "hash":
        from vault.semantic import DeterministicHashEmbeddingProvider
        return DeterministicHashEmbeddingProvider(dim=384)

    if provider == "auto":
        # 1. 嘗試 ONNX
        if importlib.util.find_spec("onnxruntime") is not None:
            return ONNXEmbeddingProvider(model_key=model_key, cache_dir=cache_dir)
        # 2. 嘗試 Ollama
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return OllamaEmbeddingProvider(model=ollama_model, base_url=ollama_url)
        except Exception:
            pass
        # 3. 降級到 sentence-transformers
        if importlib.util.find_spec("sentence_transformers") is not None:
            return SentenceTransformerProvider()
        raise RuntimeError(
            "找不到任何嵌入 provider！請安裝以下之一：\n"
            "  pip install onnxruntime optimum  (推薦，最輕量)\n"
            "  或啟動 Ollama\n"
            "  或 pip install sentence-transformers  (需要 PyTorch 2GB+)\n"
            "  或使用 provider=\"hash\" 進行測試（非語義嵌入）"
        )

    elif provider == "onnx":
        return ONNXEmbeddingProvider(model_key=model_key, cache_dir=cache_dir)

    elif provider == "ollama":
        return OllamaEmbeddingProvider(model=ollama_model, base_url=ollama_url)

    elif provider == "sentence-transformers":
        return SentenceTransformerProvider()

    else:
        raise ValueError(f"未知 provider: {provider}，可選: auto, onnx, ollama, sentence-transformers, hash")
