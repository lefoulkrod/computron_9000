from typing import Any

import pytest


class DummyAsyncClient:
    def __init__(self) -> None:
        self._response: str | None = None

    async def generate(self, model: str, prompt: str, think: bool = False) -> Any:
        class Response:
            def __init__(self, response: str) -> None:
                self.response = response

        return Response(self._response or f"Summary for: {prompt[:20]}...")

    def set_response(self, response: str) -> None:
        self._response = response


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "llm_response,expected",
    [
        ("Summary for: test...", "Summary for: test..."),
        ("<think>   \n</think>Summary for: test...", "Summary for: test..."),
        ("Summary<think>\n\n</think> for: test...", "Summary for: test..."),
        ("<think>\n\n</think>", ""),
        ("foo<think>\n\n</think>bar", "foobar"),
    ],
)
async def test_generate_summary_with_ollama_think_removal(
    monkeypatch, llm_response, expected
):
    """
    Test that generate_summary_with_ollama removes <think>...</think> blocks with whitespace/newlines.
    """
    import utils.generate_summary as mod

    dummy = DummyAsyncClient()
    dummy.set_response(llm_response)
    monkeypatch.setattr(mod, "AsyncClient", lambda: dummy)
    from utils.generate_summary import generate_summary_with_ollama

    result = await generate_summary_with_ollama(prompt="test", think=False)
    assert result == expected
