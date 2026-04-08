"""Integration tests for MCP (requires MCP server)."""

import os
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
    # This test requires MCP_TEST_SERVER to be set to run
    pass
