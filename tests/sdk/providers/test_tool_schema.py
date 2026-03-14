"""Tests for callable_to_json_schema conversion."""

from typing import Any

import pytest

from sdk.providers._tool_schema import (
    _parse_arg_descriptions,
    _python_type_to_json_schema,
    callable_to_json_schema,
)


# ── _python_type_to_json_schema ─────────────────────────────────────────


@pytest.mark.unit
class TestPythonTypeToJsonSchema:
    def test_str(self):
        assert _python_type_to_json_schema(str) == {"type": "string"}

    def test_int(self):
        assert _python_type_to_json_schema(int) == {"type": "integer"}

    def test_float(self):
        assert _python_type_to_json_schema(float) == {"type": "number"}

    def test_bool(self):
        assert _python_type_to_json_schema(bool) == {"type": "boolean"}

    def test_bare_list(self):
        assert _python_type_to_json_schema(list) == {"type": "array"}

    def test_bare_dict(self):
        assert _python_type_to_json_schema(dict) == {"type": "object"}

    def test_list_of_str(self):
        assert _python_type_to_json_schema(list[str]) == {
            "type": "array",
            "items": {"type": "string"},
        }

    def test_list_of_int(self):
        assert _python_type_to_json_schema(list[int]) == {
            "type": "array",
            "items": {"type": "integer"},
        }

    def test_dict_str_any(self):
        assert _python_type_to_json_schema(dict[str, Any]) == {"type": "object"}

    def test_optional_str(self):
        assert _python_type_to_json_schema(str | None) == {"type": "string"}

    def test_optional_int(self):
        assert _python_type_to_json_schema(int | None) == {"type": "integer"}

    def test_unannotated(self):
        """Missing annotation defaults to string."""
        import inspect

        assert _python_type_to_json_schema(inspect.Parameter.empty) == {"type": "string"}

    def test_any_type(self):
        assert _python_type_to_json_schema(Any) == {"type": "string"}

    def test_unknown_type_defaults_to_string(self):
        """An unrecognized type falls back to string."""

        class Custom:
            pass

        assert _python_type_to_json_schema(Custom) == {"type": "string"}


# ── _parse_arg_descriptions ─────────────────────────────────────────────


@pytest.mark.unit
class TestParseArgDescriptions:
    def test_none_docstring(self):
        assert _parse_arg_descriptions(None) == {}

    def test_empty_docstring(self):
        assert _parse_arg_descriptions("") == {}

    def test_no_args_section(self):
        assert _parse_arg_descriptions("Just a summary.\n\nSome details.") == {}

    def test_simple_args(self):
        doc = """Do something.

        Args:
            name: The user's name.
            age: The user's age.
        """
        result = _parse_arg_descriptions(doc)
        assert result == {
            "name": "The user's name.",
            "age": "The user's age.",
        }

    def test_args_with_type_annotations(self):
        doc = """Execute a command.

        Args:
            cmd (str): The bash command to execute.
            timeout (float): Max seconds to wait. Default 600.
        """
        result = _parse_arg_descriptions(doc)
        assert result == {
            "cmd": "The bash command to execute.",
            "timeout": "Max seconds to wait. Default 600.",
        }

    def test_multiline_arg_description(self):
        doc = """Process data.

        Args:
            query: The search query to run against the
                database. Supports wildcards.
            limit: Maximum results.
        """
        result = _parse_arg_descriptions(doc)
        assert result["query"] == "The search query to run against the database. Supports wildcards."
        assert result["limit"] == "Maximum results."

    def test_args_section_ends_at_returns(self):
        doc = """Compute.

        Args:
            x: First value.

        Returns:
            The sum.
        """
        result = _parse_arg_descriptions(doc)
        assert result == {"x": "First value."}
        assert "Returns" not in result

    def test_args_section_ends_at_raises(self):
        doc = """Compute.

        Args:
            x: First value.

        Raises:
            ValueError: If x is negative.
        """
        result = _parse_arg_descriptions(doc)
        assert result == {"x": "First value."}

    def test_arguments_keyword(self):
        """The 'Arguments:' header also works."""
        doc = """Do thing.

        Arguments:
            val: Some value.
        """
        result = _parse_arg_descriptions(doc)
        assert result == {"val": "Some value."}

    def test_real_world_run_bash_cmd(self):
        """Matches the actual run_bash_cmd docstring style."""
        doc = """Execute a bash command in the virtual computer container.

    Runs one-shot commands under ``set -euo pipefail``. Package installs
    (pip, npm, apt) are auto-promoted to root. Dev servers, watch mode, and
    other long-running/blocking processes are blocked (exit code 126).

    Args:
        cmd: The bash command to execute.
        timeout: Max seconds to wait. Default 600.

    Returns:
        BashCmdResult: ``stdout``, ``stderr``, and ``exit_code``.
    """
        result = _parse_arg_descriptions(doc)
        assert result == {
            "cmd": "The bash command to execute.",
            "timeout": "Max seconds to wait. Default 600.",
        }


# ── callable_to_json_schema ─────────────────────────────────────────────


@pytest.mark.unit
class TestCallableToJsonSchema:
    def test_simple_function(self):
        def greet(name: str) -> str:
            """Say hello to someone."""
            return f"Hello, {name}!"

        schema = callable_to_json_schema(greet)
        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "greet"
        assert func["description"] == "Say hello to someone."
        params = func["parameters"]
        assert params["type"] == "object"
        assert params["properties"] == {"name": {"type": "string"}}
        assert params["required"] == ["name"]

    def test_multiple_params_with_defaults(self):
        def search(query: str, limit: int = 10, verbose: bool = False) -> list[str]:
            """Search for items."""
            return []

        schema = callable_to_json_schema(search)
        func = schema["function"]
        assert func["name"] == "search"
        params = func["parameters"]
        assert set(params["properties"]) == {"query", "limit", "verbose"}
        assert params["properties"]["query"] == {"type": "string"}
        assert params["properties"]["limit"] == {"type": "integer"}
        assert params["properties"]["verbose"] == {"type": "boolean"}
        # Only query is required (limit and verbose have defaults)
        assert params["required"] == ["query"]

    def test_no_params(self):
        def noop() -> None:
            """Do nothing."""

        schema = callable_to_json_schema(noop)
        params = schema["function"]["parameters"]
        assert params["properties"] == {}
        assert params["required"] == []

    def test_no_docstring(self):
        def mystery(x: int) -> int:
            return x

        schema = callable_to_json_schema(mystery)
        assert schema["function"]["description"] == ""

    def test_multiline_docstring_uses_first_line(self):
        def compute(x: float, y: float) -> float:
            """Compute the result.

            This is a longer description that should not appear.
            """
            return x + y

        schema = callable_to_json_schema(compute)
        assert schema["function"]["description"] == "Compute the result."

    def test_unannotated_params_default_to_string(self):
        def loose(a, b):
            """Loose typing."""

        schema = callable_to_json_schema(loose)
        props = schema["function"]["parameters"]["properties"]
        assert props["a"] == {"type": "string"}
        assert props["b"] == {"type": "string"}
        assert schema["function"]["parameters"]["required"] == ["a", "b"]

    def test_complex_param_types(self):
        def process(
            tags: list[str],
            metadata: dict[str, Any],
            count: int | None = None,
        ) -> str:
            """Process data."""
            return ""

        schema = callable_to_json_schema(process)
        props = schema["function"]["parameters"]["properties"]
        assert props["tags"] == {"type": "array", "items": {"type": "string"}}
        assert props["metadata"] == {"type": "object"}
        assert props["count"] == {"type": "integer"}
        assert schema["function"]["parameters"]["required"] == ["tags", "metadata"]

    def test_google_style_arg_descriptions_added(self):
        """Per-parameter descriptions from Google-style docstrings are included."""
        def run_cmd(cmd: str, timeout: float = 600.0) -> str:
            """Execute a bash command.

            Args:
                cmd: The bash command to execute.
                timeout: Max seconds to wait. Default 600.

            Returns:
                The command output.
            """
            return ""

        schema = callable_to_json_schema(run_cmd)
        props = schema["function"]["parameters"]["properties"]
        assert props["cmd"] == {
            "type": "string",
            "description": "The bash command to execute.",
        }
        assert props["timeout"] == {
            "type": "number",
            "description": "Max seconds to wait. Default 600.",
        }

    def test_no_description_when_docstring_lacks_args_section(self):
        """Parameters have no description key when docstring has no Args section."""
        def simple(x: int) -> int:
            """Just a summary."""
            return x

        schema = callable_to_json_schema(simple)
        assert schema["function"]["parameters"]["properties"]["x"] == {"type": "integer"}
        assert "description" not in schema["function"]["parameters"]["properties"]["x"]
