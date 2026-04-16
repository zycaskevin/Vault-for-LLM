"""
Vault for LLM — 嵌入生成模組。

支援三種嵌入來源：
1. ONNX Runtime（本地模型，不需要 PyTorch 2GB+）
2. Ollama（已有 Ollama 的人零額外安裝）
3. sentence-transformers（降級方案，需要 PyTorch）

預設 ONNX 模型：
- 中文：BAAI/bge-small-zh-v1.5 (512d, ~90MB)
- 英文：sentence-transformers/all-MiniLM-L6-v2 (384d, ~40MB)
- 混合：sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384d, ~200MB)
"""

import json
import os
from pathlib import Path
from typing import Optional

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


class EmbeddingProvider:
    """嵌入生成基底類別。"""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        raise NotImplementedError

    def dim(self) -> int:
        return self.dim


class ONNXEmbeddingProvider(EmbeddingProvider):
    """用 ONNX Runtime 跑嵌入模型。不需要 PyTorch。"""

    def __init__(self, model_key: str = "mix", cache_dir: Optional[str] = None):
        self.model_key = model_key
        self.model_info = MODELS[model_key]
        self.dim = self.model_info["dim"]
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.cache/guardrails-lite/models"))
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
        print(f"[guardrails-lite] 下載 {model_name} → ONNX...")
        model_dir.mkdir(parents=True, exist_ok=True)

        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = ORTModelForFeatureExtraction.from_pretrained(
                model_name, export=True
            )
            model.save_pretrained(model_dir)
            tokenizer.save_pretrained(model_dir)
            print(f"[guardrails-lite] ✅ 模型已下載到 {model_dir}")
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
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir))

        # 載入 ONNX session
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(str(onnx_path), sess_options)
        print(f"[guardrails-lite] ✅ ONNX 模型已載入 ({self.model_info['language']})")

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        """生成嵌入向量。"""
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

        return normalized.tolist()


class OllamaEmbeddingProvider(EmbeddingProvider):
    """用 Ollama API 做嵌入。適合已有 Ollama 的人。"""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        dim: int = 768,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dim = dim

    def dim(self) -> int:
        # 動態偵測維度（首次呼叫時）
        if self._dim is None:
            test = self.encode("test")
            self._dim = len(test[0])
        return self._dim

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        import urllib.request
        import json as _json

        if isinstance(texts, str):
            texts = [texts]

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

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read())
                results.append(data["embedding"])

        # 更新實際維度
        if results:
            self._dim = len(results[0])

        return results


class SentenceTransformerProvider(EmbeddingProvider):
    """降級方案：用sentence-transformers（需要PyTorch）。"""

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
        self._dim = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: str | list[str]) -> list[list[float]]:
        self._load()
        if isinstance(texts, str):
            texts = [texts]
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

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
    """
    if provider == "auto":
        # 1. 嘗試 ONNX
        try:
            import onnxruntime
            return ONNXEmbeddingProvider(model_key=model_key, cache_dir=cache_dir)
        except ImportError:
            pass
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
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformerProvider()
        except ImportError:
            raise RuntimeError(
                "找不到任何嵌入 provider！請安裝以下之一：\n"
                "  pip install onnxruntime optimum  (推薦，最輕量)\n"
                "  或啟動 Ollama\n"
                "  或 pip install sentence-transformers  (需要 PyTorch 2GB+)"
            )

    elif provider == "onnx":
        return ONNXEmbeddingProvider(model_key=model_key, cache_dir=cache_dir)

    elif provider == "ollama":
        return OllamaEmbeddingProvider(model=ollama_model, base_url=ollama_url)

    elif provider == "sentence-transformers":
        return SentenceTransformerProvider()

    else:
        raise ValueError(f"未知 provider: {provider}，可選: auto, onnx, ollama, sentence-transformers")