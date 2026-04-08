"""MCP client for connecting to MCP servers."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """Raised when connection to MCP server fails."""
    pass


class MCPClient:
    """Client for connecting to an MCP server and invoking tools."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._session: ClientSession | None = None
        self._tools: list[dict[str, Any]] = []

    async def connect(self) -> None:
        """Connect to the MCP server."""
        try:
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env if self.config.env else None,
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    # Cache available tools
                    tools_response = await session.list_tools()
                    self._tools = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        }
                        for tool in tools_response.tools
                    ]
                    logger.info(
                        "Connected to MCP server '%s' with %d tools",
                        self.config.name,
                        len(self._tools)
                    )
        except Exception as e:
            raise MCPConnectionError(
                f"Failed to connect to MCP server '{self.config.name}': {e}"
            ) from e

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._session:
            await self._session.close()
            self._session = None
            self._tools = []

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._session is not None

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Return list of available tools from this server."""
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        if not self._session:
            raise MCPConnectionError("Not connected to MCP server")

        result = await self._session.call_tool(tool_name, arguments)
        return result

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()
