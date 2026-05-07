"""Tests for the provider registry and get_provider factory."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import LLMConfig
from sdk.providers import _get_llm_config, _proxy_socket_path, get_provider, reset_provider


@pytest.fixture(autouse=True)
def _clean_provider():
    """Ensure provider cache is cleared before and after each test."""
    reset_provider()
    yield
    reset_provider()


def _fake_config(sockets_dir="/tmp/no-such-dir-in-tests"):
    cfg = MagicMock()
    cfg.integrations.sockets_dir = sockets_dir
    return cfg


@pytest.mark.unit
class TestGetProvider:
    def test_returns_ollama_provider(self):
        """Ollama always has a base_url → direct connection."""
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider()
        from sdk.providers._ollama import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_caches_singleton(self):
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider()
            p2 = get_provider()
        assert p1 is p2

    def test_reset_clears_cache(self):
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider()
            reset_provider()
            p2 = get_provider()
        assert p1 is not p2

    def test_unknown_provider_raises(self):
        settings = {"llm_provider": "unknown", "llm_base_url": "http://x"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                get_provider()

    def test_proxy_when_no_base_url(self, tmp_path):
        """No base_url → provider connects through broker socket."""
        settings = {"llm_provider": "openai"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)
        assert provider._client.base_url.host == "localhost"

    def test_proxy_anthropic(self, tmp_path):
        """Anthropic without base_url → broker."""
        settings = {"llm_provider": "anthropic"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider()
        from sdk.providers._anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)

    def test_direct_with_base_url(self):
        """base_url present → direct connection, no broker."""
        settings = {"llm_provider": "openai", "llm_base_url": "http://lm-studio:1234/v1"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)
        assert "lm-studio" in str(provider._client.base_url)

    def test_openai_compat_uses_openai_provider(self, tmp_path):
        """openai_compat maps to the same OpenAIProvider class."""
        settings = {"llm_provider": "openai_compat"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)


@pytest.mark.unit
class TestGetLLMConfig:
    """_get_llm_config builds an LLMConfig from a settings dict."""

    def test_defaults_to_ollama(self):
        """When settings has no llm_* keys, defaults to ollama."""
        result = _get_llm_config({})
        assert result.provider == "ollama"
        assert result.base_url is None

    def test_provider_from_settings(self):
        result = _get_llm_config({"llm_provider": "anthropic"})
        assert result.provider == "anthropic"

    def test_base_url_from_settings(self):
        result = _get_llm_config({"llm_base_url": "http://lm-studio:1234/v1"})
        assert result.base_url == "http://lm-studio:1234/v1"

    def test_api_key_not_read(self):
        """API keys live in the vault, not settings."""
        result = _get_llm_config({"llm_api_key": "sk-test-123"})
        assert result.api_key is None

    def test_multiple_settings(self):
        result = _get_llm_config({"llm_provider": "openai", "llm_base_url": "http://vllm:8000/v1"})
        assert result.provider == "openai"
        assert result.base_url == "http://vllm:8000/v1"


@pytest.mark.unit
class TestProxySocketPath:
    """_proxy_socket_path derives socket path from provider name."""

    def test_openai(self, tmp_path):
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _proxy_socket_path("openai")
        assert result == tmp_path / "llm_openai.sock"

    def test_anthropic(self, tmp_path):
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _proxy_socket_path("anthropic")
        assert result == tmp_path / "llm_anthropic.sock"

    def test_openai_compat(self, tmp_path):
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _proxy_socket_path("openai_compat")
        assert result == tmp_path / "llm_openai_compat.sock"
