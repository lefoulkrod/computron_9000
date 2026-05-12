"""Tests for the provider registry and get_provider factory."""

from unittest.mock import MagicMock, patch

import pytest

from sdk.providers import _proxy_socket_path, get_provider, reset_provider


@pytest.fixture(autouse=True)
def _clean_provider():
    """Ensure provider cache is cleared before and after each test."""
    reset_provider()
    yield
    reset_provider()


def _fake_config(sockets_dir="/tmp/no-such-dir-in-tests"):
    cfg = MagicMock()
    cfg.integrations.sockets_dir = sockets_dir
    cfg.llm.host = "http://localhost:11434"
    return cfg


@pytest.mark.unit
class TestGetProvider:
    def test_returns_ollama_provider(self):
        """Ollama always has a base_url → direct connection."""
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider("ollama")
        from sdk.providers._ollama import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_caches_by_name(self):
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider("ollama")
            p2 = get_provider("ollama")
        assert p1 is p2

    def test_reset_clears_one(self):
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider("ollama")
            reset_provider("ollama")
            p2 = get_provider("ollama")
        assert p1 is not p2

    def test_reset_clears_all(self):
        settings = {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider("ollama")
            reset_provider()
            p2 = get_provider("ollama")
        assert p1 is not p2

    def test_unknown_provider_raises(self):
        with patch("sdk.providers.load_settings", return_value={}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                get_provider("unknown")

    def test_proxy_when_no_base_url(self, tmp_path):
        """No base_url → provider connects through broker socket."""
        (tmp_path / "llm_openai.sock").touch()
        settings = {"llm_provider": "ollama"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("openai")
        from sdk.providers._openai_responses import OpenAIResponsesProvider
        assert isinstance(provider, OpenAIResponsesProvider)
        assert provider._client.base_url.host == "localhost"

    def test_proxy_anthropic(self, tmp_path):
        """Anthropic without base_url → broker."""
        (tmp_path / "llm_anthropic.sock").touch()
        settings = {"llm_provider": "ollama"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("anthropic")
        from sdk.providers._anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)

    def test_direct_with_base_url(self):
        """base_url present for the active provider → direct connection, no broker."""
        settings = {"llm_provider": "openai", "llm_base_url": "http://lm-studio:1234/v1"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider("openai")
        from sdk.providers._openai_responses import OpenAIResponsesProvider
        assert isinstance(provider, OpenAIResponsesProvider)
        assert "lm-studio" in str(provider._client.base_url)

    def test_openai_compat_uses_openai_provider(self, tmp_path):
        """openai_compat maps to the same OpenAIProvider class."""
        (tmp_path / "llm_openai_compat.sock").touch()
        settings = {"llm_provider": "ollama"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("openai_compat")
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_openrouter_uses_openai_provider(self, tmp_path):
        """openrouter maps to OpenAIProvider (OpenAI-compatible API)."""
        (tmp_path / "llm_openrouter.sock").touch()
        settings = {"llm_provider": "ollama"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("openrouter")
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_missing_broker_socket_raises(self):
        """Cloud provider with no base_url and no broker socket gives a clear error."""
        settings = {"llm_provider": "ollama"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            with pytest.raises(ValueError, match="not configured"):
                get_provider("anthropic")


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

    def test_openrouter(self, tmp_path):
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _proxy_socket_path("openrouter")
        assert result == tmp_path / "llm_openrouter.sock"
