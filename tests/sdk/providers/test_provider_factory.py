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


@pytest.fixture(autouse=True)
def _no_settings_override():
    """Isolate tests from any settings.json on the developer's machine."""
    with patch("sdk.providers.load_settings", return_value={}):
        yield


def _fake_config(provider: str = "ollama", sockets_dir: str = "/tmp/no-such-dir-in-tests"):
    cfg = MagicMock()
    cfg.llm.provider = provider
    cfg.llm.host = "http://localhost:11434"
    cfg.llm.api_key = None
    cfg.llm.base_url = None
    cfg.integrations.sockets_dir = sockets_dir
    return cfg


def _real_llm_config(**kwargs) -> LLMConfig:
    """Return a real LLMConfig for tests that exercise model_copy."""
    return LLMConfig(provider="ollama", **kwargs)


@pytest.mark.unit
class TestGetProvider:
    def test_returns_ollama_provider(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("ollama")):
            provider = get_provider()
        from sdk.providers._ollama import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_caches_singleton(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("ollama")):
            p1 = get_provider()
            p2 = get_provider()
        assert p1 is p2

    def test_reset_clears_cache(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("ollama")):
            p1 = get_provider()
            reset_provider()
            p2 = get_provider()
        assert p1 is not p2

    def test_unknown_provider_raises(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("unknown")):
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                get_provider()

    def test_openai_provider(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("openai")):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_anthropic_provider(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("anthropic")):
            provider = get_provider()
        from sdk.providers._anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)

    def test_proxy_socket_used_when_present(self, tmp_path):
        """When the llm_proxy socket exists, the provider is created with it."""
        # Create a fake socket file so _find_proxy_socket returns a path.
        sock = tmp_path / "llm_proxy_openai.sock"
        sock.touch()

        with patch("sdk.providers.load_config", return_value=_fake_config("openai", str(tmp_path))):
            provider = get_provider()

        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)
        # Client was built with the proxy base URL, not the real cloud URL.
        assert provider._client.base_url.host == "localhost"

    def test_direct_connection_when_no_proxy_socket(self):
        """When no llm_proxy socket exists, from_config() is used (direct connection)."""
        cfg = _fake_config("openai")
        cfg.llm.base_url = "http://lm-studio:1234/v1"
        with patch("sdk.providers.load_config", return_value=cfg):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)
        # No proxy involved — base_url comes from config.
        assert "lm-studio" in str(provider._client.base_url)


@pytest.mark.unit
class TestGetLLMConfig:
    """_get_llm_config merges config.yaml defaults with settings.json overrides."""

    def _app_cfg(self, llm: LLMConfig) -> MagicMock:
        cfg = MagicMock()
        cfg.llm = llm
        return cfg

    def test_no_overrides_returns_base(self):
        """When settings.json has no llm_* keys, the base config is returned as-is."""
        base = _real_llm_config(host="http://localhost:11434")
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={}):
            result = _get_llm_config()
        assert result.provider == "ollama"
        assert result.host == "http://localhost:11434"

    def test_provider_override(self):
        """llm_provider in settings.json overrides the base provider."""
        base = _real_llm_config()
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={"llm_provider": "anthropic"}):
            result = _get_llm_config()
        assert result.provider == "anthropic"

    def test_api_key_in_settings_is_ignored(self):
        """llm_api_key in settings.json is NOT read — keys live in the vault now."""
        base = _real_llm_config()
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={"llm_api_key": "sk-test-123"}):
            result = _get_llm_config()
        # api_key should remain None (not overridden from settings)
        assert result.api_key is None

    def test_base_url_override(self):
        """llm_base_url in settings.json overrides the base base_url."""
        base = _real_llm_config()
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={"llm_base_url": "http://lm-studio:1234/v1"}):
            result = _get_llm_config()
        assert result.base_url == "http://lm-studio:1234/v1"

    def test_host_not_overridden_by_settings(self):
        """host is Ollama-specific; settings.json cannot override it."""
        base = _real_llm_config(host="http://localhost:11434")
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={"llm_base_url": "http://other:1234"}):
            result = _get_llm_config()
        # host comes from config.yaml, not settings.json
        assert result.host == "http://localhost:11434"

    def test_multiple_overrides_applied(self):
        """provider and base_url overrides can be applied simultaneously."""
        base = _real_llm_config()
        overrides = {
            "llm_provider": "openai",
            "llm_base_url": "http://vllm:8000/v1",
        }
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value=overrides):
            result = _get_llm_config()
        assert result.provider == "openai"
        assert result.base_url == "http://vllm:8000/v1"


@pytest.mark.unit
class TestFindProxySocket:
    """_find_proxy_socket locates the llm_proxy broker UDS."""

    def test_returns_path_when_socket_exists(self, tmp_path):
        """Returns the socket path when the broker socket file is present."""
        sock = tmp_path / "llm_proxy_openai.sock"
        sock.touch()
        with patch("sdk.providers.load_config", return_value=_fake_config("openai", str(tmp_path))):
            result = _find_proxy_socket("openai")
        assert result == sock

    def test_returns_none_when_socket_absent(self, tmp_path):
        """Returns None when no socket file is present (broker not running)."""
        with patch("sdk.providers.load_config", return_value=_fake_config("openai", str(tmp_path))):
            result = _find_proxy_socket("openai")
        assert result is None

    def test_provider_name_in_socket_filename(self, tmp_path):
        """Socket filename includes the provider name for discrimination."""
        # Create openai socket but ask for anthropic — should return None.
        (tmp_path / "llm_proxy_openai.sock").touch()
        with patch("sdk.providers.load_config", return_value=_fake_config("anthropic", str(tmp_path))):
            result = _find_proxy_socket("anthropic")
        assert result is None
