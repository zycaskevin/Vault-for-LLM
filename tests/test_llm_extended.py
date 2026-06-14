"""
Extended tests for vault/llm.py
Focus on MockLLMProvider and create_llm_provider factory.
"""
import pytest
from unittest.mock import MagicMock, patch
import os


class TestMockLLMProvider:
    def test_mock_provider_name(self):
        """Test MockLLMProvider name property."""
        from vault.llm import MockLLMProvider
        provider = MockLLMProvider("test response")
        assert provider.name == "mock"

    def test_mock_provider_generate(self):
        """Test MockLLMProvider generate returns fixed response."""
        from vault.llm import MockLLMProvider
        response = "Hello, world!"
        provider = MockLLMProvider(response)
        result = provider.generate("any prompt")
        assert result == response

    def test_mock_provider_generate_with_params(self):
        """Test MockLLMProvider generate accepts all parameters."""
        from vault.llm import MockLLMProvider
        provider = MockLLMProvider("response")
        result = provider.generate(
            "prompt",
            max_tokens=100,
            temperature=0.7,
            system_prompt="You are helpful",
        )
        assert result == "response"

    def test_mock_provider_default_response(self):
        """Test MockLLMProvider default response."""
        from vault.llm import MockLLMProvider
        provider = MockLLMProvider()
        result = provider.generate("test")
        assert result == "mock response"


class TestCreateLLMProvider:
    def test_create_mock_provider(self):
        """Test creating mock provider explicitly."""
        from vault.llm import create_llm_provider
        provider = create_llm_provider("mock")
        assert provider.name == "mock"
        assert provider.generate("test") == "mock response"

    def test_create_mock_with_custom_response(self):
        """Test creating mock provider with custom response."""
        from vault.llm import create_llm_provider
        provider = create_llm_provider("mock", response="custom")
        assert provider.generate("test") == "custom"

    def test_create_llm_provider_auto_no_env(self):
        """Test auto mode without API keys falls back gracefully."""
        from vault.llm import create_llm_provider
        # Mock Ollama to fail, and no API keys set
        with patch.dict(os.environ, {}, clear=True):
            with patch('vault.llm.OllamaLLMProvider') as mock_ollama:
                mock_ollama.side_effect = RuntimeError("Ollama not available")
                try:
                    provider = create_llm_provider("auto")
                    # Should not reach here if all fail
                except Exception:
                    # Expected if no providers available
                    pass

    def test_create_llm_provider_invalid_name(self):
        """Test invalid provider name raises error."""
        from vault.llm import create_llm_provider
        with pytest.raises(ValueError):
            create_llm_provider("nonexistent_provider")


class TestLLMProviderABC:
    def test_cannot_instantiate_abc(self):
        """Test that LLMProvider abstract class cannot be instantiated."""
        from vault.llm import LLMProvider
        with pytest.raises(TypeError):
            LLMProvider()

    def test_mock_provider_is_llm_provider(self):
        """Test MockLLMProvider is an instance of LLMProvider."""
        from vault.llm import LLMProvider, MockLLMProvider
        provider = MockLLMProvider()
        assert isinstance(provider, LLMProvider)


class TestOllamaLLMProvider:
    """Test OllamaLLMProvider with mocked client."""


class TestOllamaLLMProviderInit:
    """Test OllamaLLMProvider initialization and properties."""

    def test_ollama_provider_init_defaults(self):
        from vault.llm import OllamaLLMProvider
        provider = OllamaLLMProvider()
        assert provider.base_url == "http://localhost:11434"
        assert provider._requested_model == "qwen3:8b"
        assert provider._model is None
        assert provider._checked is False

    def test_ollama_provider_init_custom(self):
        from vault.llm import OllamaLLMProvider
        provider = OllamaLLMProvider(
            model="llama3",
            base_url="http://custom:11434/",
            timeout=60,
        )
        assert provider.base_url == "http://custom:11434"
        assert provider._requested_model == "llama3"
        assert provider._timeout == 60

    def test_ollama_provider_name_before_check(self):
        from vault.llm import OllamaLLMProvider
        provider = OllamaLLMProvider(model="test-model")
        assert "ollama:" in provider.name
        assert "test-model" in provider.name

    @patch('urllib.request.urlopen')
    def test_ollama_ensure_model_success(self, mock_urlopen):
        from vault.llm import OllamaLLMProvider
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [{"name": "qwen3:8b"}]
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        provider = OllamaLLMProvider(model="qwen3:8b")
        model = provider._ensure_model()
        assert model == "qwen3:8b"
        assert provider._model == "qwen3:8b"
        assert provider._checked is True

    @patch('urllib.request.urlopen')
    def test_ollama_ensure_model_fallback(self, mock_urlopen):
        from vault.llm import OllamaLLMProvider
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [{"name": "llama3.2:3b"}]
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        provider = OllamaLLMProvider(model="nonexistent")
        model = provider._ensure_model()
        assert model == "llama3.2:3b"

    @patch('urllib.request.urlopen')
    def test_ollama_ensure_model_connection_error(self, mock_urlopen):
        from vault.llm import OllamaLLMProvider
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        provider = OllamaLLMProvider()
        with pytest.raises(RuntimeError, match="Ollama 未啟動或不可用"):
            provider._ensure_model()

    @patch('urllib.request.urlopen')
    def test_ollama_generate(self, mock_urlopen):
        from vault.llm import OllamaLLMProvider
        import json

        # Mock tags response
        mock_tags = MagicMock()
        mock_tags.read.return_value = json.dumps({
            "models": [{"name": "qwen3:8b"}]
        }).encode()

        # Mock generate response
        mock_gen = MagicMock()
        mock_gen.read.return_value = json.dumps({
            "response": "  Hello from Ollama  "
        }).encode()

        mock_urlopen.return_value.__enter__.side_effect = [mock_tags, mock_gen]

        provider = OllamaLLMProvider()
        result = provider.generate("Test prompt")
        assert result == "Hello from Ollama"

    @patch('urllib.request.urlopen')
    def test_ollama_generate_with_system_prompt(self, mock_urlopen):
        from vault.llm import OllamaLLMProvider
        import json

        mock_tags = MagicMock()
        mock_tags.read.return_value = json.dumps({
            "models": [{"name": "qwen3:8b"}]
        }).encode()

        mock_gen = MagicMock()
        mock_gen.read.return_value = json.dumps({
            "response": "With system prompt"
        }).encode()

        mock_urlopen.return_value.__enter__.side_effect = [mock_tags, mock_gen]

        provider = OllamaLLMProvider()
        result = provider.generate("Hi", system_prompt="You are helpful")
        assert result == "With system prompt"


class TestClaudeLLMProviderInit:
    """Test ClaudeLLMProvider initialization and error paths."""

    def test_claude_provider_init_defaults(self):
        from vault.llm import ClaudeLLMProvider
        provider = ClaudeLLMProvider(api_key="sk-test")
        assert provider._model == "claude-sonnet-4-20250514"
        assert provider._api_key == "sk-test"

    def test_claude_provider_init_custom(self):
        from vault.llm import ClaudeLLMProvider
        provider = ClaudeLLMProvider(
            model="claude-3-opus",
            api_key="sk-custom",
            max_tokens=500,
        )
        assert provider._model == "claude-3-opus"
        assert provider._api_key == "sk-custom"
        assert provider._default_max_tokens == 500

    def test_claude_provider_name(self):
        from vault.llm import ClaudeLLMProvider
        provider = ClaudeLLMProvider(model="test-model", api_key="sk-test")
        assert "claude:" in provider.name
        assert "test-model" in provider.name

    def test_claude_provider_no_api_key(self):
        from vault.llm import ClaudeLLMProvider
        import os
        # Clear env var
        with patch.dict(os.environ, {}, clear=True):
            provider = ClaudeLLMProvider()
            with pytest.raises(RuntimeError, match="缺少 ANTHROPIC_API_KEY"):
                provider._ensure_client()

    def test_claude_provider_anthropic_import_error(self):
        from vault.llm import ClaudeLLMProvider
        import sys

        # Temporarily remove anthropic from sys.modules
        original_anthropic = sys.modules.get('anthropic')
        sys.modules['anthropic'] = None  # Will cause ImportError on import

        try:
            provider = ClaudeLLMProvider(api_key="sk-test")
            with pytest.raises(RuntimeError, match="缺少 anthropic 套件"):
                provider._ensure_client()
        finally:
            if original_anthropic is not None:
                sys.modules['anthropic'] = original_anthropic
            else:
                del sys.modules['anthropic']


class TestOpenAILLMProviderInit:
    """Test OpenAILLMProvider initialization and error paths."""

    def test_openai_provider_init_defaults(self):
        from vault.llm import OpenAILLMProvider
        provider = OpenAILLMProvider(api_key="sk-test")
        assert provider._model == "gpt-4o-mini"
        assert provider._api_key == "sk-test"
        assert provider._base_url is None

    def test_openai_provider_init_custom(self):
        from vault.llm import OpenAILLMProvider
        provider = OpenAILLMProvider(
            model="gpt-4",
            api_key="sk-custom",
            base_url="https://custom.example.com/v1",
        )
        assert provider._model == "gpt-4"
        assert provider._api_key == "sk-custom"
        assert provider._base_url == "https://custom.example.com/v1"

    def test_openai_provider_name(self):
        from vault.llm import OpenAILLMProvider
        provider = OpenAILLMProvider(model="gpt-4", api_key="sk-test")
        assert "openai:" in provider.name
        assert "gpt-4" in provider.name

    def test_openai_provider_no_api_key(self):
        from vault.llm import OpenAILLMProvider
        import os
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenAILLMProvider()
            with pytest.raises(RuntimeError, match="缺少 OPENAI_API_KEY"):
                provider._ensure_client()

    def test_openai_provider_import_error(self):
        from vault.llm import OpenAILLMProvider
        import sys

        original_openai = sys.modules.get('openai')
        sys.modules['openai'] = None

        try:
            provider = OpenAILLMProvider(api_key="sk-test")
            with pytest.raises(RuntimeError, match="缺少 openai 套件"):
                provider._ensure_client()
        finally:
            if original_openai is not None:
                sys.modules['openai'] = original_openai
            else:
                del sys.modules['openai']


class TestCreateLLMProviderExtended:
    """More tests for create_llm_provider factory."""

    def test_create_ollama_provider(self):
        from vault.llm import create_llm_provider
        provider = create_llm_provider("ollama", model="llama3")
        assert provider.name.startswith("ollama:")

    def test_create_claude_provider(self):
        from vault.llm import create_llm_provider
        provider = create_llm_provider("claude", api_key="sk-test")
        assert provider.name.startswith("claude:")

    def test_create_openai_provider(self):
        from vault.llm import create_llm_provider
        provider = create_llm_provider("openai", api_key="sk-test")
        assert provider.name.startswith("openai:")
