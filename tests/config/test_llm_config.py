"""Unit tests for llm.host env-driven configuration."""

from __future__ import annotations

import importlib
import os
from typing import Generator

import pytest

import config as config_module
from config import load_config


@pytest.fixture(autouse=True)
def _clear_load_config_cache() -> Generator[None, None, None]:
    """Clear load_config cache before each test to re-evaluate env.

    Yields:
        None: Pytest fixture.
    """
    # Clear the lru_cache on load_config
    load_config.cache_clear()  # type: ignore[attr-defined]
    yield
    load_config.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.unit
def test_llm_host_defaults_to_yaml_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM host should default to YAML value when env var is not set."""
    monkeypatch.delenv("LLM_HOST", raising=False)
    importlib.reload(config_module)
    cfg = load_config()
    assert cfg.llm.host == "http://127.0.0.1:11434"


@pytest.mark.unit
def test_llm_host_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM host should reflect value from LLM_HOST env var."""
    monkeypatch.setenv("LLM_HOST", "llm1")
    importlib.reload(config_module)
    cfg = load_config()
    assert cfg.llm.host == "llm1"


@pytest.mark.unit
def test_llm_host_env_blank_falls_back_to_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """If LLM_HOST exists but is blank, use the YAML llm.host value."""
    monkeypatch.setenv("LLM_HOST", "")
    importlib.reload(config_module)
    cfg = load_config()
    assert cfg.llm.host == "http://127.0.0.1:11434"
