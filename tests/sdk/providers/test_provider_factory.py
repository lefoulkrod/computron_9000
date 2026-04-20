"""Tests for the provider registry and get_provider factory."""

from unittest.mock import MagicMock, patch

import pytest

from config import LLMConfig
from sdk.providers import _get_llm_config, get_provider, reset_provider


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


def _fake_config(provider: str = "ollama"):
    cfg = MagicMock()
    cfg.llm.provider = provider
    cfg.llm.host = "http://localhost:11434"
    cfg.llm.api_key = None
    cfg.llm.base_url = None
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

    def test_api_key_override(self):
        """llm_api_key in settings.json overrides the base api_key."""
        base = _real_llm_config()
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={"llm_api_key": "sk-test-123"}):
            result = _get_llm_config()
        assert result.api_key == "sk-test-123"

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

    def test_multiple_overrides_all_applied(self):
        """All three llm_* settings can be overridden simultaneously."""
        base = _real_llm_config()
        overrides = {
            "llm_provider": "openai",
            "llm_base_url": "http://vllm:8000/v1",
            "llm_api_key": "my-key",
        }
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value=overrides):
            result = _get_llm_config()
        assert result.provider == "openai"
        assert result.base_url == "http://vllm:8000/v1"
        assert result.api_key == "my-key"

    def test_empty_string_llm_api_key_not_applied(self):
        """Empty string for llm_api_key is falsy and does not override base."""
        base = _real_llm_config(api_key="yaml-key")
        with patch("sdk.providers.load_config", return_value=self._app_cfg(base)), \
             patch("sdk.providers.load_settings", return_value={"llm_api_key": ""}):
            result = _get_llm_config()
        # Empty string is falsy — base api_key should be preserved
        assert result.api_key == "yaml-key"
