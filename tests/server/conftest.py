"""Pytest configuration for server tests.

Provides the aiohttp_client fixture for testing aiohttp applications.
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


@pytest.fixture
async def aiohttp_client():
    """Fixture factory that returns a test client for aiohttp apps.
    
    Usage:
        async def test_something(aiohttp_client, app):
            client = await aiohttp_client(app)
            resp = await client.get('/')
            ...
    """
    clients: list[TestClient] = []
    
    async def _create_client(app: web.Application) -> TestClient:
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        clients.append(client)
        return client
    
    yield _create_client
    
    # Cleanup: close all clients
    for client in clients:
        await client.close()
