"""Tests for tool call argument truncation."""

import types

import pytest

from sdk.tools import truncate_tool_call_args
from tools._truncation import TRUNCATE_ATTR, truncate_args


@pytest.mark.unit
class TestTruncateArgsDecorator:
    """Tests for the @truncate_args decorator."""

    def test_sets_attribute_on_function(self):
        @truncate_args(content=0, cmd=500)
        def my_tool(content: str, cmd: str) -> str:
            return content

        assert getattr(my_tool, TRUNCATE_ATTR) == {"content": 0, "cmd": 500}

    def test_preserves_function_name(self):
        @truncate_args(content=0)
        def my_tool(content: str) -> str:
            return content

        assert my_tool.__name__ == "my_tool"

    def test_function_still_callable(self):
        @truncate_args(content=0)
        def my_tool(content: str) -> str:
            return f"got: {content}"

        assert my_tool(content="hello") == "got: hello"

    def test_async_function_preserves_attribute(self):
        @truncate_args(code=500)
        async def my_async_tool(code: str) -> str:
            return code

        assert getattr(my_async_tool, TRUNCATE_ATTR) == {"code": 500}

    def test_async_function_remains_coroutine(self):
        """Decorated async functions must stay async so iscoroutinefunction works."""
        import inspect

        @truncate_args(cmd=500)
        async def my_async_tool(cmd: str) -> str:
            return cmd

        assert inspect.iscoroutinefunction(my_async_tool)


def _make_tool_call(name: str, arguments: dict) -> types.SimpleNamespace:
    """Build a fake tool call object matching ollama's structure."""
    return types.SimpleNamespace(
        function=types.SimpleNamespace(name=name, arguments=arguments),
    )


@pytest.mark.unit
class TestTruncateToolCallArgs:
    """Tests for truncate_tool_call_args helper."""

    def test_no_truncation_when_no_decorated_tools(self):
        def plain_tool(content: str) -> str:
            return content

        tc = _make_tool_call("plain_tool", {"content": "x" * 10000})
        result = truncate_tool_call_args([tc], [plain_tool])

        assert result[0].function.arguments["content"] == "x" * 10000

    def test_truncates_with_threshold_zero(self):
        @truncate_args(content=0)
        def write_file(path: str, content: str) -> str:
            return "ok"

        tc = _make_tool_call("write_file", {"path": "app.py", "content": "z" * 5000})
        result = truncate_tool_call_args([tc], [write_file])

        assert result[0].function.arguments["path"] == "app.py"
        assert "5,000 chars omitted from history" in result[0].function.arguments["content"]
        assert "z" not in result[0].function.arguments["content"]

    def test_truncates_with_char_threshold(self):
        @truncate_args(cmd=100)
        def run_bash(cmd: str) -> str:
            return "ok"

        long_cmd = "echo " + "a" * 500
        tc = _make_tool_call("run_bash", {"cmd": long_cmd})
        result = truncate_tool_call_args([tc], [run_bash])

        truncated = result[0].function.arguments["cmd"]
        assert truncated.startswith("echo ")
        assert "truncated" in truncated
        assert "505 chars total" in truncated

    def test_leaves_short_args_alone(self):
        @truncate_args(cmd=500)
        def run_bash(cmd: str) -> str:
            return "ok"

        tc = _make_tool_call("run_bash", {"cmd": "ls -la"})
        result = truncate_tool_call_args([tc], [run_bash])

        assert result[0].function.arguments["cmd"] == "ls -la"

    def test_does_not_mutate_original(self):
        @truncate_args(content=0)
        def write_file(path: str, content: str) -> str:
            return "ok"

        original_content = "x" * 5000
        tc = _make_tool_call("write_file", {"path": "a.py", "content": original_content})
        truncate_tool_call_args([tc], [write_file])

        # Original tool call should be unchanged.
        assert tc.function.arguments["content"] == original_content

    def test_mixed_tools_only_truncates_decorated(self):
        @truncate_args(content=0)
        def write_file(path: str, content: str) -> str:
            return "ok"

        def read_file(path: str) -> str:
            return "data"

        tc_write = _make_tool_call("write_file", {"path": "a.py", "content": "x" * 5000})
        tc_read = _make_tool_call("read_file", {"path": "b.py"})
        result = truncate_tool_call_args([tc_write, tc_read], [write_file, read_file])

        assert "CONTEXT SAVED" in result[0].function.arguments["content"]
        assert result[1].function.arguments["path"] == "b.py"

    def test_tool_call_without_function_passes_through(self):
        tc = types.SimpleNamespace()  # no function attribute
        result = truncate_tool_call_args([tc], [])
        assert result[0] is tc

    def test_non_string_args_not_truncated(self):
        @truncate_args(count=0)
        def my_tool(count: int) -> str:
            return "ok"

        tc = _make_tool_call("my_tool", {"count": 999})
        result = truncate_tool_call_args([tc], [my_tool])

        assert result[0].function.arguments["count"] == 999
