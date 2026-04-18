"""
Guardrails Lite — LLM Provider 統一介面（策略模式）。

讓 proposition_chunk、contextualize_chunks 等功能可以使用任何 LLM backend，
不強制依賴 Ollama。

支援：
- OllamaLLMProvider：本地 Ollama，免費，需要跑 server
- ClaudeLLMProvider：Anthropic Claude API，最強推理（可選依賴）
- OpenAILLMProvider：OpenAI GPT API（可選依賴）
- MockLLMProvider：測試用，不需 API

使用方式：
  from .guardrails_llm import create_llm_provider
  llm = create_llm_provider("auto")
  result = llm.generate("請總結以下文本...")
"""

import json
import urllib.request
import os
from abc import ABC, abstractmethod
from typing import Optional

from .guardrails_log import log


class LLMProvider(ABC):
    """LLM 呼叫基底類別。"""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> str:
        """生成文字回應。回傳純文字字串。

        system_prompt: 可選系統提示（設定角色/風格/限制）。
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名稱（用於 logging）。"""
        ...


class OllamaLLMProvider(LLMProvider):
    """
    用 Ollama /api/generate 做 LLM 推理。

    特點：
    - 自動偵測可用模型（fallback chain）
    - 只檢查 /api/tags 一次（初始化時），不每次呼叫都查
    - 找不到 Ollama 時 raise RuntimeError
    """

    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self._requested_model = model
        self._timeout = timeout
        self._model: Optional[str] = None
        self._checked = False

    def _ensure_model(self) -> str:
        """偵測可用模型。失敗時不快取，允許下次重試。"""
        if self._checked and self._model is not None:
            return self._model

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                models = json.loads(resp.read()).get("models", [])
                model_names = [m["name"] for m in models]

            # Fallback chain：使用者指定 → 通用小模型
            available = None
            for preferred in [
                self._requested_model,
                "qwen3:8b", "qwen2.5:0.5b",
                "llama3.2:3b", "gemma3:4b", "mistral:7b",
            ]:
                for name in model_names:
                    if preferred in name or name.startswith(preferred.split(":")[0]):
                        available = name
                        break
                if available:
                    break

            if not available and model_names:
                available = model_names[0]

            if available:
                self._model = available
                self._checked = True
                log.info(f"✅ 使用模型: {available}")
                return available
            else:
                raise RuntimeError("Ollama 沒有可用模型")

        except (urllib.error.URLError, ConnectionError, OSError) as e:
            raise RuntimeError(f"Ollama 未啟動或不可用: {e}")

    @property
    def name(self) -> str:
        return f"ollama:{self._model or self._requested_model}"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> str:
        model = self._ensure_model()

        payload_dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        # Ollama 支援 system prompt
        if system_prompt:
            payload_dict["system"] = system_prompt

        payload = json.dumps(payload_dict).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            result = json.loads(resp.read())

        return result.get("response", "").strip()


class ClaudeLLMProvider(LLMProvider):
    """
    用 Anthropic Claude API 做 LLM 推理。

    可選依賴：pip install anthropic
    需要 ANTHROPIC_API_KEY 環境變數。
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        max_tokens: int = 300,
    ):
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._default_max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        if not self._api_key:
            raise RuntimeError(
                "缺少 ANTHROPIC_API_KEY。請設定環境變數或傳入 api_key 參數。"
            )
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        except ImportError:
            raise RuntimeError(
                "缺少 anthropic 套件。請執行：pip install anthropic"
            )

    @property
    def name(self) -> str:
        return f"claude:{self._model}"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> str:
        self._ensure_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._default_max_tokens,
            temperature=temperature,
            messages=messages,
        )
        return message.content[0].text.strip()


class OpenAILLMProvider(LLMProvider):
    """
    用 OpenAI GPT API 做 LLM 推理。

    可選依賴：pip install openai
    需要 OPENAI_API_KEY 環境變數。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        if not self._api_key:
            raise RuntimeError(
                "缺少 OPENAI_API_KEY。請設定環境變數或傳入 api_key 參數。"
            )
        try:
            from openai import OpenAI
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        except ImportError:
            raise RuntimeError(
                "缺少 openai 套件。請執行：pip install openai"
            )

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> str:
        self._ensure_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
        return response.choices[0].message.content.strip()


class MockLLMProvider(LLMProvider):
    """測試用：回傳固定回應，不需任何 API。"""

    def __init__(self, response: str = "mock response"):
        self._response = response

    @property
    def name(self) -> str:
        return "mock"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> str:
        return self._response


def create_llm_provider(
    provider: str = "auto",
    model: Optional[str] = None,
    **kwargs,
) -> LLMProvider:
    """
    工廠函數，建立 LLM provider。

    provider:
    - "auto": 偵測環境自動選擇（Ollama > Claude > OpenAI > 報錯）
    - "ollama": Ollama 本地
    - "claude": Anthropic Claude API
    - "openai": OpenAI GPT API
    - "mock": 測試用
    """
    if provider == "auto":
        # 1. 嘗試 Ollama
        try:
            p = OllamaLLMProvider(model=model or "qwen3:8b", **kwargs)
            p._ensure_model()  # 驗證可用
            return p
        except RuntimeError:
            pass

        # 2. 嘗試 Claude
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                return ClaudeLLMProvider(model=model or "claude-sonnet-4-20250514", **kwargs)
            except Exception:
                pass

        # 3. 嘗試 OpenAI
        if os.environ.get("OPENAI_API_KEY"):
            try:
                return OpenAILLMProvider(model=model or "gpt-4o-mini", **kwargs)
            except Exception:
                pass

        raise RuntimeError(
            "找不到任何可用的 LLM provider！請安裝以下之一：\n"
            "  1. 啟動 Ollama（免費，本地）\n"
            "  2. 設定 ANTHROPIC_API_KEY + pip install anthropic\n"
            "  3. 設定 OPENAI_API_KEY + pip install openai"
        )

    elif provider == "ollama":
        return OllamaLLMProvider(model=model or "qwen3:8b", **kwargs)

    elif provider == "claude":
        return ClaudeLLMProvider(model=model or "claude-sonnet-4-20250514", **kwargs)

    elif provider == "openai":
        return OpenAILLMProvider(model=model or "gpt-4o-mini", **kwargs)

    elif provider == "mock":
        return MockLLMProvider(**kwargs)

    else:
        raise ValueError(
            f"未知 LLM provider: {provider}，可選: auto, ollama, claude, openai, mock"
        )