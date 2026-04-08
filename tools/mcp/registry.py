"""Registry for managing MCP server connections."""

from __future__ import annotations

import logging
from typing import Any

from config import MCPConfig, load_config

from tools.mcp.client import MCPClient, MCPConnectionError

logger = logging.getLogger(__name__)


class MCPRegistry:
    """Registry for managing MCP server connections and tools."""

    def __init__(self, config: MCPConfig | None = None) -> None:
        self.config = config or load_config().mcp
        self._clients: dict[str, MCPClient] = {}
        self._tool_to_server: dict[str, str] = {}  # Maps tool_name -> server_name

    async def initialize(self) -> None:
        """Initialize all enabled MCP connections."""
        if not self.config.enabled:
            logger.debug("MCP integration is disabled")
            return

        for server_config in self.config.servers:
            if not server_config.enabled:
                continue

            try:
                client = MCPClient(server_config)
                await client.connect()
                self._clients[server_config.name] = client

                # Map tools to this server
                prefix = self.config.tool_prefix
                for tool in client.tools:
                    tool_name = f"{prefix}{tool['name']}"
                    self._tool_to_server[tool_name] = server_config.name

            except MCPConnectionError as e:
                logger.warning("Failed to connect to MCP server '%s': %s",
                              server_config.name, e)

    async def shutdown(self) -> None:
        """Close all MCP connections."""
        for name, client in self._clients.items():
            try:
                await client.disconnect()
                logger.debug("Disconnected from MCP server '%s'", name)
            except Exception as e:
                logger.warning("Error disconnecting from '%s': %s", name, e)
        self._clients.clear()
        self._tool_to_server.clear()

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Return all tools from all connected MCP servers."""
        tools = []
        prefix = self.config.tool_prefix

        for server_name, client in self._clients.items():
            for tool in client.tools:
                prefixed_tool = {
                    **tool,
                    "name": f"{prefix}{tool['name']}",
                    "server": server_name,
                }
                tools.append(prefixed_tool)

        return tools

    def get_client_for_tool(self, tool_name: str) -> MCPClient | None:
        """Get the client that provides the given tool."""
        server_name = self._tool_to_server.get(tool_name)
        if server_name:
            return self._clients.get(server_name)
        return None

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool name is an MCP tool."""
        return tool_name.startswith(self.config.tool_prefix)

    def strip_prefix(self, tool_name: str) -> str:
        """Remove MCP prefix from tool name."""
        if tool_name.startswith(self.config.tool_prefix):
            return tool_name[len(self.config.tool_prefix):]
        return tool_name


# Global registry instance
_mcp_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    """Get or create the global MCP registry."""
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = MCPRegistry()
    return _mcp_registry
