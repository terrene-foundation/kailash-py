"""Fixtures for MCP server E2E tests."""

import asyncio
import socket
import time
from typing import Any, Dict

import pytest
import pytest_asyncio
from aiohttp import web
from kailash.mcp_server.auth import AuthManager
from kailash.mcp_server.protocol import get_protocol_manager
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.transports import WebSocketServerTransport
from kailash.middleware.gateway.event_store import EventStore

# from tests.utils.mcp_utils import create_test_mcp_server


@pytest.fixture
def unused_tcp_port():
    """Find an unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest_asyncio.fixture
async def mcp_server_e2e(unused_tcp_port):
    """Create and start MCP server for E2E testing."""
    # Create server components with mock connections for now
    # TODO: Set up real PostgreSQL connection for E2E tests
    event_store = None  # EventStore(postgres_conn)
    auth_manager = (
        None  # AuthManager(secret_key="test_secret_e2e", db_pool=postgres_conn)
    )

    # Create server
    server = MCPServer(
        "test_server_e2e",
        event_store=event_store,
        auth_provider=auth_manager,
        enable_subscriptions=True,
    )

    # Add test data
    protocol_mgr = get_protocol_manager()
    protocol_mgr.roots._roots = []  # Clear any existing
    protocol_mgr.roots.add_root("file:///workspace", "Workspace", "Main workspace")
    protocol_mgr.roots.add_root("file:///home", "Home", "User home directory")

    # Add test resources
    @server.resource("file:///{path}")
    async def file_resource(path: str) -> str:
        """Access files by path."""
        return f"Content of file: {path}"

    @server.resource("config:///{section}")
    async def config_resource(section: str) -> Dict[str, Any]:
        """Access configuration."""
        configs = {
            "database": {"host": "localhost", "port": 5432},
            "api": {"timeout": 30},
        }
        return configs.get(section, {})

    # Add test prompts
    @server.prompt("analyze")
    async def analyze_prompt(data: str) -> str:
        """Analyze data prompt."""
        return f"Please analyze: {data}"

    @server.prompt("debug")
    async def debug_prompt(code: str) -> str:
        """Debug code prompt."""
        return f"Debug this code: {code}"

    # Create web app
    app = web.Application()

    # Store client connections for sampling support
    client_connections = {}

    # Create a mock transport for sampling support
    class MockTransport:
        """Mock transport that supports sending messages to clients."""

        def __init__(self):
            self.clients = client_connections

        async def send_message(self, message, client_id=None):
            """Send message to specific client."""
            if client_id and client_id in self.clients:
                # Send the message immediately
                ws = self.clients[client_id]
                try:
                    await ws.send_json(message)
                    return True
                except Exception as e:
                    return False
            return False

        def has_send_message(self):
            """Check if transport supports sending messages."""
            return True

    # Set mock transport on server
    server._transport = MockTransport()

    # Add WebSocket handler
    async def websocket_handler(request):
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Handle connection
        client_id = f"client_{time.time()}"

        # Store connection for sampling support
        client_connections[client_id] = ws

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    # Parse and handle message
                    data = msg.json()
                    response = await server._handle_websocket_message(data, client_id)

                    if response:
                        await ws.send_json(response)

                elif msg.type == web.WSMsgType.ERROR:
                    print(f"WebSocket error: {ws.exception()}")

        except Exception as e:
            print(f"WebSocket handler error: {e}")
        finally:
            # Cleanup
            if client_id in server.client_info:
                del server.client_info[client_id]
            if client_id in client_connections:
                del client_connections[client_id]

        return ws

    app.router.add_get("/ws", websocket_handler)

    # Start server
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "localhost", unused_tcp_port)
    await site.start()

    # Wait for server to be ready
    await asyncio.sleep(0.1)

    yield {"server": server, "app": app, "runner": runner, "port": unused_tcp_port}

    # Cleanup
    await runner.cleanup()
