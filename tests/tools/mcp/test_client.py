"""Tests for MCP client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.mcp.client import MCPClient, MCPConnectionError
from config import MCPServerConfig


@pytest.mark.unit
class TestMCPClient:
    """Test MCP client functionality."""

    @pytest.fixture
    def config(self) -> MCPServerConfig:
        return MCPServerConfig(
            name="test_server",
            command="echo",
            args=["test"],
        )

    @pytest.mark.asyncio
    async def test_client_initialization(self, config: MCPServerConfig) -> None:
        client = MCPClient(config)
        assert client.config == config
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_connection_error(self, config: MCPServerConfig) -> None:
        config.command = "nonexistent_command"
        client = MCPClient(config)

        with pytest.raises(MCPConnectionError):
            await client.connect()
