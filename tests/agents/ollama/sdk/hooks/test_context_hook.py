"""Tests for ContextHook."""

from __future__ import annotations

from typing import Any

import pytest

from agents.ollama.sdk.hooks import ContextHook


class _FakeHistory:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


@pytest.mark.unit
def test_records_and_returns():
    class FakeCtxManager:
        recorded = None

        def record_response(self, response: Any) -> None:
            self.recorded = response

    mgr = FakeCtxManager()
    hook = ContextHook(mgr)
    sentinel = object()
    result = hook.after_model(sentinel, _FakeHistory(), 1, "TEST")
    assert result is sentinel
    assert mgr.recorded is sentinel
