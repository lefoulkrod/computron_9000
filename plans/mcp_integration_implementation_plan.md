# MCP (Model Context Protocol) Integration Implementation Plan

## Overview

This plan details the implementation of MCP (Model Context Protocol) client support in COMPUTRON_9000. MCP is an open standard by Anthropic that enables AI assistants to securely connect with external data sources and tools through a standardized protocol.

## Background

MCP addresses one of the top user requests (18.8% of Anthropic's 81K users) for task automation. It provides:
- Standardized tool schemas
- Server discovery and connection
- Bi-directional communication
- Security boundaries

## Goals

1. Enable COMPUTRON_9000 to connect to MCP servers
2. Expose MCP tools as native COMPUTRON_9000 tools
3. Support common MCP servers (filesystem, web search, SQLite)
4. Maintain existing tool system architecture

---

## Phase 1: Foundation & Dependencies

### Step 1.1: Add MCP SDK Dependency

**File:** `pyproject.toml`

Add the official MCP SDK to dependencies:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "mcp>=1.0.0",
]
```

**Testing:**
```bash
uv sync
python -c "import mcp; print(mcp.__version__)"
```

### Step 1.2: Create MCP Configuration Schema

**File:** `config/__init__.py`

Add new configuration models:

```python
class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection."""
    
    name: str
    command: str  # Command to start the server (e.g., "npx", "python", "docker")
    args: list[str] = Field(default_factory=list)  # Arguments for the command
    env: dict[str, str] = Field(default_factory=dict)  # Environment variables
    timeout: int = 30  # Connection timeout in seconds
    enabled: bool = True


class MCPConfig(BaseModel):
    """Configuration for MCP client integration."""
    
    enabled: bool = False
    servers: list[MCPServerConfig] = Field(default_factory=list)
    auto_discover: bool = False  # Auto-discover local MCP servers
    tool_prefix: str = "mcp_"  # Prefix for MCP tool names


# Update AppConfig to include MCP:
class AppConfig(BaseModel):
    # ... existing fields ...
    mcp: MCPConfig = Field(default_factory=MCPConfig)
```

**Testing:**
- Verify config loads with empty MCP section
- Verify config validation rejects invalid server configs

---

## Phase 2: Core MCP Client Implementation

### Step 2.1: Create MCP Client Module

**New File:** `tools/mcp/__init__.py`

Package initialization:

```python
"""MCP (Model Context Protocol) client integration for COMPUTRON_9000."""

from .client import MCPClient, MCPConnectionError
from .registry import MCPRegistry, get_mcp_registry
from .tools import convert_mcp_tools, execute_mcp_tool

__all__ = [
    "MCPClient",
    "MCPConnectionError", 
    "MCPRegistry",
    "get_mcp_registry",
    "convert_mcp_tools",
    "execute_mcp_tool",
]
```

### Step 2.2: Implement MCP Client

**New File:** `tools/mcp/client.py`

```python
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
                            "parameters": tool.parameters,
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
```

### Step 2.3: Implement MCP Registry

**New File:** `tools/mcp/registry.py`

```python
"""Registry for managing MCP server connections."""

from __future__ import annotations

import logging
from typing import Any

from config import MCPConfig, load_config

from .client import MCPClient, MCPConnectionError

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
```

---

## Phase 3: Tool Integration

### Step 3.1: Create MCP Tool Adapter

**New File:** `tools/mcp/tools.py`

```python
"""Tool adapter for MCP tools - converts MCP tools to COMPUTRON_9000 format."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, create_model

from sdk.tools._schema import JSONValue

from .registry import get_mcp_registry

logger = logging.getLogger(__name__)


def _mcp_type_to_python(mcp_type: str) -> type:
    """Convert MCP type to Python type."""
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return type_map.get(mcp_type, Any)


def _create_pydantic_model_from_schema(
    name: str, 
    schema: dict[str, Any]
) -> type[BaseModel]:
    """Create a Pydantic model from JSON schema."""
    fields = {}
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    for prop_name, prop_schema in properties.items():
        prop_type = _mcp_type_to_python(prop_schema.get("type", "string"))
        description = prop_schema.get("description", "")
        
        if prop_name in required:
            fields[prop_name] = (prop_type, ...)
        else:
            fields[prop_name] = (prop_type | None, None)
    
    return create_model(name, **fields)


def convert_mcp_tools(
    mcp_tools: list[dict[str, Any]]
) -> list[Callable[..., Any]]:
    """Convert MCP tool definitions to COMPUTRON_9000 callable tools."""
    tools = []
    
    for tool_def in mcp_tools:
        tool_name = tool_def["name"]
        tool_description = tool_def.get("description", "")
        parameters_schema = tool_def.get("parameters", {})
        
        # Create Pydantic model for parameters
        ParamModel = _create_pydantic_model_from_schema(
            f"{tool_name}Params", 
            parameters_schema
        )
        
        # Create the tool function
        def create_tool_function(name: str, description: str, model: type[BaseModel]) -> Callable[..., Any]:
            async def mcp_tool(**kwargs: Any) -> JSONValue:
                """MCP tool wrapper."""
                registry = get_mcp_registry()
                client = registry.get_client_for_tool(name)
                
                if not client:
                    return {"error": f"MCP client for tool '{name}' not found"}
                
                # Strip prefix for actual MCP call
                original_name = registry.strip_prefix(name)
                
                try:
                    result = await client.call_tool(original_name, kwargs)
                    return _normalize_mcp_result(result)
                except Exception as e:
                    logger.exception("MCP tool '%s' failed", name)
                    return {"error": str(e)}
            
            # Set function metadata for tool schema generation
            mcp_tool.__name__ = name
            mcp_tool.__doc__ = description
            mcp_tool.__annotations__ = {**model.__annotations__, "return": JSONValue}
            
            return mcp_tool
        
        tool_func = create_tool_function(tool_name, tool_description, ParamModel)
        tools.append(tool_func)
    
    return tools


def _normalize_mcp_result(result: Any) -> JSONValue:
    """Normalize MCP tool result for COMPUTRON_9000."""
    if isinstance(result, BaseModel):
        return result.model_dump()
    elif isinstance(result, list):
        return [_normalize_mcp_result(item) for item in result]
    elif isinstance(result, dict):
        return {k: _normalize_mcp_result(v) for k, v in result.items()}
    return result


async def execute_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute an MCP tool by name with given arguments."""
    registry = get_mcp_registry()
    client = registry.get_client_for_tool(tool_name)
    
    if not client:
        raise ValueError(f"MCP tool '{tool_name}' not available")
    
    original_name = registry.strip_prefix(tool_name)
    return await client.call_tool(original_name, arguments)
```

### Step 3.2: Update Core Tools

**File:** `sdk/tools/_core.py`

Modify to include MCP tools:

```python
"""Core tools included in every agent's tool set."""

from collections.abc import Callable
from typing import Any


def get_core_tools() -> list[Callable[..., Any]]:
    """Return tools that every agent gets regardless of skill configuration.

    Lazy imports to avoid circular dependencies.
    """
    from sdk.skills._tools import list_available_skills, load_skill
    from sdk.tools._spawn_agent import spawn_agent
    from tools.custom_tools import create_custom_tool, lookup_custom_tools, run_custom_tool
    from tools.mcp import convert_mcp_tools, get_mcp_registry
    from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
    from tools.virtual_computer import describe_image, play_audio, send_file

    core_tools = [
        save_to_scratchpad,
        recall_from_scratchpad,
        load_skill,
        list_available_skills,
        spawn_agent,
        create_custom_tool,
        lookup_custom_tools,
        run_custom_tool,
        send_file,
        play_audio,
        describe_image,
    ]
    
    # Add MCP tools if MCP is enabled
    registry = get_mcp_registry()
    if registry.config.enabled:
        mcp_tools = registry.get_all_tools()
        if mcp_tools:
            converted = convert_mcp_tools(mcp_tools)
            core_tools.extend(converted)
    
    return core_tools
```

### Step 3.3: Add MCP Lifecycle Management

**File:** `main.py`

Add MCP initialization and shutdown:

```python
# Near startup
async def initialize_services():
    """Initialize all services including MCP."""
    from tools.mcp import get_mcp_registry
    
    registry = get_mcp_registry()
    await registry.initialize()


async def shutdown_services():
    """Shutdown all services including MCP."""
    from tools.mcp import get_mcp_registry
    
    registry = get_mcp_registry()
    await registry.shutdown()


# In main() or app lifecycle:
try:
    await initialize_services()
    # ... run server ...
finally:
    await shutdown_services()
```

---

## Phase 4: Configuration & Documentation

### Step 4.1: Update config.yaml Example

Add MCP configuration section to `config.yaml`:

```yaml
# ... existing config ...

mcp:
  enabled: true
  tool_prefix: "mcp_"
  auto_discover: false
  servers:
    # Filesystem MCP server
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/Documents"]
      env: {}
      timeout: 30
      enabled: true
    
    # SQLite MCP server
    - name: sqlite
      command: uvx
      args: ["mcp-server-sqlite", "--db-path", "/home/user/data.db"]
      enabled: false
    
    # Web search MCP server (example)
    - name: web_search
      command: python
      args: ["-m", "mcp_server_web_search"]
      env:
        SEARCH_API_KEY: "${SEARCH_API_KEY}"
      enabled: false
```

### Step 4.2: Create MCP Documentation

**New File:** `docs/mcp_integration.md`

```markdown
# MCP Integration Guide

## Overview

COMPUTRON_9000 supports the Model Context Protocol (MCP), enabling integration with external tool servers.

## Configuration

Enable MCP in `config.yaml`:

```yaml
mcp:
  enabled: true
  tool_prefix: "mcp_"
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"]
```

## Available MCP Servers

### Filesystem
Provides file operations (read, write, list, search).

### SQLite
Database operations with SQL support.

### Web Search
Internet search capabilities.

## Using MCP Tools

MCP tools are prefixed with `mcp_` and available to all agents automatically.

Example: `mcp_read_file`, `mcp_write_file`

## Troubleshooting

- Check MCP server logs
- Verify command availability in PATH
- Ensure proper permissions for file operations
```

---

## Phase 5: Testing

### Step 5.1: Unit Tests

**New File:** `tests/tools/mcp/test_client.py`

```python
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
```

**New File:** `tests/tools/mcp/test_registry.py`

```python
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
```

**New File:** `tests/tools/mcp/test_tools.py`

```python
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
```

### Step 5.2: Integration Tests

**New File:** `tests/tools/mcp/test_integration.py`

```python
"""Integration tests for MCP (requires MCP server)."""

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("MCP_TEST_SERVER"),
        reason="MCP_TEST_SERVER not set"
    ),
]


@pytest.mark.asyncio
async def test_mcp_filesystem_integration() -> None:
    """Test integration with filesystem MCP server."""
    # Test actual MCP server interaction
    pass
```

---

## Phase 6: Example MCP Servers

### Step 6.1: Filesystem MCP Server

Most common use case - file operations:

```yaml
mcp:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
```

Tools exposed:
- `mcp_read_file` - Read file contents
- `mcp_write_file` - Write to files
- `mcp_list_directory` - List directory contents
- `mcp_search_files` - Search for files

### Step 6.2: SQLite MCP Server

```yaml
mcp:
  servers:
    - name: sqlite
      command: uvx
      args: ["mcp-server-sqlite", "--db-path", "/path/to/database.db"]
```

Tools exposed:
- `mcp_query` - Execute SQL queries
- `mcp_execute` - Execute SQL commands

### Step 6.3: Custom Python MCP Server

**New File:** `tools/mcp/servers/README.md`

Instructions for creating custom MCP servers in Python.

---

## Implementation Timeline

| Phase | Duration | Files Modified/Created |
|-------|----------|----------------------|
| Phase 1: Foundation | 0.5 day | `pyproject.toml`, `config/__init__.py` |
| Phase 2: Core Client | 1 day | `tools/mcp/client.py`, `tools/mcp/registry.py` |
| Phase 3: Tool Integration | 1 day | `tools/mcp/tools.py`, `sdk/tools/_core.py`, `main.py` |
| Phase 4: Configuration | 0.5 day | `config.yaml`, `docs/mcp_integration.md` |
| Phase 5: Testing | 1 day | `tests/tools/mcp/*.py` |
| Phase 6: Examples | 0.5 day | `tools/mcp/servers/` |
| **Total** | **~4.5 days** | **~15 files** |

---

## Dependencies

### Required
- `mcp>=1.0.0` - Official MCP Python SDK

### Optional (for MCP servers)
- `npx` (Node.js) - For Node-based MCP servers
- `uvx` - For Python-based MCP servers

---

## Success Criteria

1. ✅ MCP SDK dependency added and imports successfully
2. ✅ Configuration schema supports MCP server definitions
3. ✅ MCP client connects to servers and lists available tools
4. ✅ MCP tools appear in agent tool lists with proper prefix
5. ✅ Agents can invoke MCP tools and receive results
6. ✅ Graceful handling of MCP server connection failures
7. ✅ Unit tests cover core MCP functionality
8. ✅ Documentation explains setup and usage

---

## Future Enhancements

1. **Auto-discovery**: Scan for local MCP servers
2. **Tool filtering**: Whitelist/blacklist specific tools
3. **Caching**: Cache tool schemas to reduce connections
4. **Metrics**: Track MCP tool usage and latency
5. **Multi-server tools**: Combine tools from multiple servers
6. **MCP prompts**: Support MCP prompt templates
7. **MCP resources**: Support MCP resource access
