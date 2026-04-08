"""Tests for MCP tool conversion."""

import pytest
from tools.mcp.tools import (
    _mcp_type_to_python,
    _create_pydantic_model_from_schema,
    _normalize_mcp_result,
)


@pytest.mark.unit
class TestMCPToolConversion:
    """Test MCP tool conversion utilities."""

    def test_mcp_type_to_python(self) -> None:
        assert _mcp_type_to_python("string") == str
        assert _mcp_type_to_python("integer") == int
        assert _mcp_type_to_python("number") == float
        assert _mcp_type_to_python("boolean") == bool
        assert _mcp_type_to_python("array") == list
        assert _mcp_type_to_python("object") == dict
        # Unknown type returns Any
        from typing import Any
        assert _mcp_type_to_python("unknown") is Any

    def test_create_pydantic_model(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path"],
        }

        Model = _create_pydantic_model_from_schema("TestParams", schema)
        assert "path" in Model.model_fields
        assert "content" in Model.model_fields

    def test_normalize_mcp_result(self) -> None:
        # Test with simple values
        assert _normalize_mcp_result("string") == "string"
        assert _normalize_mcp_result(123) == 123
        assert _normalize_mcp_result(True) == True

        # Test with lists
        result = [1, 2, 3]
        assert _normalize_mcp_result(result) == [1, 2, 3]

        # Test with dicts
        result = {"key": "value"}
        assert _normalize_mcp_result(result) == {"key": "value"}
