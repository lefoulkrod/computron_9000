"""Tests for MCP registry."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.mcp.registry import MCPRegistry, get_mcp_registry
from config import MCPConfig, MCPServerConfig


@pytest.mark.unit
class TestMCPRegistry:
    """Test MCP registry functionality."""

    def test_registry_initialization(self) -> None:
        config = MCPConfig(enabled=True)
        registry = MCPRegistry(config)
        assert registry.config == config
        assert not registry._clients

    def test_is_mcp_tool(self) -> None:
        config = MCPConfig(enabled=True, tool_prefix="mcp_")
        registry = MCPRegistry(config)

        assert registry.is_mcp_tool("mcp_read_file")
        assert not registry.is_mcp_tool("read_file")

    def test_strip_prefix(self) -> None:
        config = MCPConfig(enabled=True, tool_prefix="mcp_")
        registry = MCPRegistry(config)

        assert registry.strip_prefix("mcp_read_file") == "read_file"
        assert registry.strip_prefix("read_file") == "read_file"

    def test_get_client_for_tool_not_found(self) -> None:
        config = MCPConfig(enabled=True, tool_prefix="mcp_")
        registry = MCPRegistry(config)

        assert registry.get_client_for_tool("mcp_nonexistent") is None

    def test_get_all_tools_empty(self) -> None:
        config = MCPConfig(enabled=True, tool_prefix="mcp_")
        registry = MCPRegistry(config)

        tools = registry.get_all_tools()
        assert tools == []
