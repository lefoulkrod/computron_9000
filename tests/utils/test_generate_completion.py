from typing import Any

import pytest


class DummyAsyncClient:
    def __init__(self) -> None:
        self._response: str | None = None
        self._thinking: str | None = None

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        think: bool = False,
        options: Any = None,
        **kwargs,
    ) -> Any:
        class Response:
            def __init__(self, response: str, thinking: str | None) -> None:
                self.response = response
                self.thinking = thinking
        response_val = self._response if self._response is not None else f"Completion for: {prompt[:20]}..."
        return Response(
            response_val,
            self._thinking,
        )

    def set_response(self, response: str, thinking: str | None = None) -> None:
        self._response = response
        self._thinking = thinking

@pytest.mark.unit
@pytest.mark.asyncio

@pytest.mark.parametrize(
    "llm_response,thinking,expected_response,expected_thinking",
    [
        ("Completion for: test...", None, "Completion for: test...", None),
        ("Completion for: test...", "", "Completion for: test...", ""),
        ("Completion for: test...", "Some thinking", "Completion for: test...", "Some thinking"),
        ("", "Some thinking", "", "Some thinking"),
    ],
)
async def test_generate_completion_thinking_property(monkeypatch, llm_response, thinking, expected_response, expected_thinking):
    """
    Test that generate_completion returns response and thinking as separate values.
    """
    import importlib
    mod = importlib.import_module("models.generate_completion")
    from models.generate_completion import generate_completion

    dummy = DummyAsyncClient()
    dummy.set_response(llm_response, thinking)
    monkeypatch.setattr(mod, "AsyncClient", lambda: dummy)

    result, result_thinking = await generate_completion(prompt="test", model="notused", think=False)
    assert result == expected_response
    assert result_thinking == expected_thinking
