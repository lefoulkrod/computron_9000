import logging
from unittest.mock import MagicMock

import pytest
from google.genai import types
from google.adk.models.llm_request import LlmRequest
from agents.adk.callbacks import log_llm_request_callback
from google.adk.agents.callback_context import CallbackContext

class DummyPart(types.Part):
    def __init__(self, text=None, function_call=None, function_response=None, thought=None):
        super().__init__()
        self.text = text
        self.function_call = function_call
        self.function_response = function_response
        self.thought = thought

class DummyContent(types.Content):
    def __init__(self, parts=None, role=None):
        super().__init__()
        self.parts = parts or []
        self.role = role

def test_log_llm_request_callback_logs_parts(caplog):
    """
    Test that log_llm_request_callback logs all parts in all contents.
    """
    caplog.set_level(logging.DEBUG)
    ctx = MagicMock()
    ctx.agent_name = "test_agent"
    part1 = DummyPart(text="hello", function_call=None, function_response=None, thought=None)
    part2 = DummyPart(text=None, function_call="call", function_response="resp", thought=True)
    content = DummyContent(parts=[part1, part2], role="user")
    req = LlmRequest(model="foo", contents=[content])
    log_llm_request_callback(ctx, req)
    assert "Request To LLM" in caplog.text
    assert "[text]: hello" in caplog.text
    assert "[function_call]: call" in caplog.text
    assert "[function_response]: resp" in caplog.text
    assert "[thought]: True" in caplog.text

def test_log_llm_request_callback_no_parts(caplog):
    """
    Test that log_llm_request_callback logs when there are no content parts.
    """
    caplog.set_level(logging.DEBUG)
    ctx = MagicMock()
    ctx.agent_name = "test_agent"
    req = LlmRequest(model="foo", contents=[])
    log_llm_request_callback(ctx, req)
    assert "No Content Parts" in caplog.text
