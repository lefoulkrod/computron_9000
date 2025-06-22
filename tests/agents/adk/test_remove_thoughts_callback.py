import pytest
from unittest.mock import MagicMock

from agents.adk.callbacks.remove_thoughts_callback import remove_thoughts_callback
from google.adk.models.llm_request import LlmRequest
from google.genai.types import Content, Part
from google.adk.agents.callback_context import CallbackContext

class DummyCallbackContext(MagicMock):
    pass

def make_llm_request_with_parts(parts):
    content = Content(parts=parts)
    return LlmRequest(contents=[content])

def test_remove_thoughts_callback_removes_think_parts():
    """
    Test that remove_thoughts_callback removes parts starting with '<think>' and keeps others.
    """
    parts = [
        Part(text="<think>internal reasoning"),
        Part(text="Hello world"),
        Part(text="<think>another thought"),
        Part(text="Final output")
    ]
    llm_request = make_llm_request_with_parts(parts)
    callback_context = DummyCallbackContext()

    remove_thoughts_callback(callback_context, llm_request)
    remaining_texts = [p.text for p in (llm_request.contents[0].parts or [])]
    assert remaining_texts == ["Hello world", "Final output"]

def test_remove_thoughts_callback_handles_no_parts():
    """
    Test that remove_thoughts_callback handles contents with no parts gracefully.
    """
    llm_request = make_llm_request_with_parts([])
    callback_context = DummyCallbackContext()
    remove_thoughts_callback(callback_context, llm_request)
    assert (llm_request.contents[0].parts or []) == []

def test_remove_thoughts_callback_handles_no_text():
    """
    Test that remove_thoughts_callback ignores parts without text attribute.
    """
    class NoTextPart(Part):
        def __init__(self):
            super().__init__()
    parts = [NoTextPart(), Part(text="<think>should remove"), Part(text="Keep me")]
    llm_request = make_llm_request_with_parts(parts)
    callback_context = DummyCallbackContext()
    remove_thoughts_callback(callback_context, llm_request)
    filtered = [p for p in (llm_request.contents[0].parts or []) if getattr(p, 'text', None)]
    assert len(filtered) == 1
    assert filtered[0].text == "Keep me"
