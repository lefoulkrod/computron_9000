"""Tests for the provider registry and get_provider factory."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import LLMConfig
from sdk.providers import _find_proxy_socket, _get_llm_config, get_provider, reset_provider


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
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "ollama"}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider()
        from sdk.providers._ollama import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_caches_singleton(self):
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "ollama"}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider()
            p2 = get_provider()
        assert p1 is p2

    def test_reset_clears_cache(self):
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "ollama"}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            p1 = get_provider()
            reset_provider()
            p2 = get_provider()
        assert p1 is not p2

    def test_unknown_provider_raises(self):
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "unknown"}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                get_provider()

    def test_openai_provider(self):
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "openai"}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_anthropic_provider(self):
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "anthropic"}), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider()
        from sdk.providers._anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)

    def test_proxy_socket_used_when_present(self, tmp_path):
        """When the llm_proxy socket exists, the provider is created with it."""
        sock = tmp_path / "llm_proxy_openai.sock"
        sock.touch()

        with patch("sdk.providers.load_settings", return_value={"llm_provider": "openai"}), \
             patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            provider = get_provider()

        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)
        assert provider._client.base_url.host == "localhost"

    def test_direct_connection_with_base_url(self):
        """When base_url is set in settings, it's passed to from_config."""
        settings = {"llm_provider": "openai", "llm_base_url": "http://lm-studio:1234/v1"}
        with patch("sdk.providers.load_settings", return_value=settings), \
             patch("sdk.providers.load_config", return_value=_fake_config()):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)
        assert "lm-studio" in str(provider._client.base_url)


@pytest.mark.unit
class TestGetLLMConfig:
    """_get_llm_config reads from settings.json."""

    def test_defaults_to_ollama(self):
        """When settings.json has no llm_* keys, defaults to ollama."""
        with patch("sdk.providers.load_settings", return_value={}):
            result = _get_llm_config()
        assert result.provider == "ollama"
        assert result.base_url is None

    def test_provider_from_settings(self):
        """llm_provider in settings.json sets the provider."""
        with patch("sdk.providers.load_settings", return_value={"llm_provider": "anthropic"}):
            result = _get_llm_config()
        assert result.provider == "anthropic"

    def test_base_url_from_settings(self):
        """llm_base_url in settings.json sets the base_url."""
        with patch("sdk.providers.load_settings", return_value={"llm_base_url": "http://lm-studio:1234/v1"}):
            result = _get_llm_config()
        assert result.base_url == "http://lm-studio:1234/v1"

    def test_api_key_in_settings_is_ignored(self):
        """llm_api_key in settings.json is NOT read — keys live in the vault."""
        with patch("sdk.providers.load_settings", return_value={"llm_api_key": "sk-test-123"}):
            result = _get_llm_config()
        assert result.api_key is None

    def test_multiple_settings(self):
        """provider and base_url can be set simultaneously."""
        settings = {"llm_provider": "openai", "llm_base_url": "http://vllm:8000/v1"}
        with patch("sdk.providers.load_settings", return_value=settings):
            result = _get_llm_config()
        assert result.provider == "openai"
        assert result.base_url == "http://vllm:8000/v1"


@pytest.mark.unit
class TestFindProxySocket:
    """_find_proxy_socket locates the llm_proxy broker UDS."""

    def test_returns_path_when_socket_exists(self, tmp_path):
        sock = tmp_path / "llm_proxy_openai.sock"
        sock.touch()
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _find_proxy_socket("openai")
        assert result == sock

    def test_returns_none_when_socket_absent(self, tmp_path):
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _find_proxy_socket("openai")
        assert result is None

    def test_provider_name_in_socket_filename(self, tmp_path):
        (tmp_path / "llm_proxy_openai.sock").touch()
        with patch("sdk.providers.load_config", return_value=_fake_config(str(tmp_path))):
            result = _find_proxy_socket("anthropic")
        assert result is None
