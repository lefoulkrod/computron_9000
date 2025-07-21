from typing import Any

import pytest

class DummyAsyncClient:
    def __init__(self) -> None:
        self._response: str | None = None

    async def generate(self, model: str, prompt: str, system: str | None = None, think: bool = False, options: Any = None, **kwargs) -> Any:
        class Response:
            def __init__(self, response: str) -> None:
                self.response = response
        return Response(self._response or f"Completion for: {prompt[:20]}...")

    def set_response(self, response: str) -> None:
        self._response = response

@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "llm_response,expected",
    [
        ("Completion for: test...", "Completion for: test..."),
        ("<think>   \n</think>Completion for: test...", "Completion for: test..."),
        ("Completion<think>\n\n</think> for: test...", "Completion for: test..."),
        ("<think>\n\n</think>", ""),
        ("foo<think>\n\n</think>bar", "foobar"),
    ],
)
async def test_generate_completion_think_removal(monkeypatch, llm_response, expected):
    """
    Test that generate_completion removes <think>...</think> blocks with whitespace/newlines.
    """
    import importlib
    mod = importlib.import_module("utils.generate_completion")
    from utils.generate_completion import generate_completion

    dummy = DummyAsyncClient()
    dummy.set_response(llm_response)
    monkeypatch.setattr(mod, "AsyncClient", lambda: dummy)

    result = await generate_completion(prompt="test", think=False)
    assert result == expected
