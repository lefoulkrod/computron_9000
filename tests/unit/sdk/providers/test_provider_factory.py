"""Tests for the provider registry and get_provider factory."""

from unittest.mock import MagicMock, patch

import pytest

from sdk.providers import get_provider, reset_provider


@pytest.fixture(autouse=True)
def _clean_provider():
    """Ensure provider cache is cleared before and after each test."""
    reset_provider()
    yield
    reset_provider()


def _fake_config(provider: str = "ollama"):
    cfg = MagicMock()
    cfg.llm.provider = provider
    cfg.llm.host = "http://localhost:11434"
    cfg.llm.api_key = None
    cfg.llm.base_url = None
    return cfg


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

    def test_openai_stub(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("openai")):
            provider = get_provider()
        from sdk.providers._openai import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)

    def test_anthropic_stub(self):
        with patch("sdk.providers.load_config", return_value=_fake_config("anthropic")):
            provider = get_provider()
        from sdk.providers._anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)
