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
    return cfg


def _direct(name, base_url):
    return {"direct_providers": {name: {"base_url": base_url}}}


@pytest.mark.unit
class TestGetProvider:
    def test_returns_direct_ollama_provider(self):
        """Ollama configured as a direct provider → direct connection."""
        with patch("sdk.providers.load_settings", return_value=_direct("ollama", "http://localhost:11434")), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider("ollama")
        from sdk.providers._ollama import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_caches_by_name(self):
        with patch("sdk.providers.load_settings", return_value=_direct("ollama", "http://localhost:11434")), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider("ollama")
            p2 = get_provider("ollama")
        assert p1 is p2

    def test_reset_clears_one(self):
        with patch("sdk.providers.load_settings", return_value=_direct("ollama", "http://localhost:11434")), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider("ollama")
            reset_provider("ollama")
            p2 = get_provider("ollama")
        assert p1 is not p2

    def test_reset_clears_all(self):
        with patch("sdk.providers.load_settings", return_value=_direct("ollama", "http://localhost:11434")), \
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

    def test_direct_with_base_url(self):
        """A direct provider entry connects straight to its base URL."""
        with patch("sdk.providers.load_settings", return_value=_direct("openai", "http://lm-studio:1234/v1")), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider("openai")
        from sdk.providers._openai_responses import OpenAIResponsesProvider
        assert isinstance(provider, OpenAIResponsesProvider)
        assert "lm-studio" in str(provider._client.base_url)

    def test_brokered_via_socket(self, tmp_path):
        """No direct entry but a broker socket exists → connect through it."""
        (tmp_path / "llm_openai.sock").touch()
        with patch("sdk.providers.load_settings", return_value={}), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("openai")
        from sdk.providers._openai_responses import OpenAIResponsesProvider
        assert isinstance(provider, OpenAIResponsesProvider)
        assert provider._client.base_url.host == "localhost"

    def test_brokered_anthropic_via_socket(self, tmp_path):
        (tmp_path / "llm_anthropic.sock").touch()
        with patch("sdk.providers.load_settings", return_value={}), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("anthropic")
        from sdk.providers._anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)

    def test_openai_compat_uses_openai_provider(self, tmp_path):
        """openai_compat maps to the same OpenAIProvider class."""
        (tmp_path / "llm_openai_compat.sock").touch()
        with patch("sdk.providers.load_settings", return_value={}), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("openai_compat")
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_openrouter_uses_openai_provider(self, tmp_path):
        """openrouter maps to OpenAIProvider (OpenAI-compatible API)."""
        (tmp_path / "llm_openrouter.sock").touch()
        with patch("sdk.providers.load_settings", return_value={}), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider("openrouter")
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_not_configured_raises(self):
        """A provider with no direct entry and no broker socket gives a clear error."""
        with patch("sdk.providers.load_settings", return_value={}), \
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
