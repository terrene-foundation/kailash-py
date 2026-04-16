"""Basic test to verify WebSocket MCP server starts correctly."""

import asyncio
import json
import logging
import socket
import threading
import time
from contextlib import closing

import pytest
import websockets
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket MCP server requires the fastmcp package; the official
# mcp.server.FastMCP fallback does not bind a WebSocket transport and
# fails at MCPServer.run() with a TaskGroup error. Skip instead of
# running a test that cannot succeed in the current environment.
pytest.importorskip(
    "fastmcp",
    reason="fastmcp is required for MCP-over-WebSocket integration tests.",
)


def _find_free_port(start: int = 8000) -> int:
    for port in range(start, start + 200):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port starting from {start}")


@pytest.mark.asyncio
async def test_basic_websocket_server():
    """Test basic WebSocket server functionality."""
    # Create Nexus app on dynamic ports (hardcoded 8902/3902 collided when
    # the test ran after another integration test left port 8902 bound).
    # MCP server/channel wiring in core.py:760-767 requires HTTP transport.
    api_port = _find_free_port(8900)
    mcp_port = _find_free_port(api_port + 100)
    app = Nexus(
        api_port=api_port,
        mcp_port=mcp_port,
        enable_auth=False,
        enable_monitoring=False,
        enable_http_transport=True,
    )

    # Register a simple workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "echo",
        {"code": "result = {'echo': parameters.get('message', 'Hello')}"},
    )
    app.register("echo", workflow.build())

    # Start server in thread
    server_thread = threading.Thread(target=app.start, daemon=True)
    server_thread.start()

    # Wait for server to start
    logger.info("Waiting for server to start...")
    await asyncio.sleep(3)

    # Check server status
    logger.info(f"App running: {app._running}")
    logger.info(f"Has MCP server: {hasattr(app, '_mcp_server')}")
    logger.info(f"Has WS server: {hasattr(app, '_ws_server')}")
    logger.info(
        f"MCP thread alive: {hasattr(app, '_mcp_thread') and app._mcp_thread.is_alive() if hasattr(app, '_mcp_thread') else 'No thread'}"
    )

    # Try to connect to the MCP port (not the API port)
    uri = f"ws://localhost:{mcp_port}"
    logger.info(f"Attempting to connect to {uri}")

    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected successfully!")

            # Send a test message
            test_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
            await websocket.send(json.dumps(test_msg))
            logger.info("Sent initialize message")

            # Receive response
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            logger.info(f"Received response: {response}")

            data = json.loads(response)
            assert "result" in data or "error" in data

    except Exception as e:
        logger.error(f"WebSocket connection failed: {e}")
        # Check if MCP server is running
        logger.info(f"App running: {app._running}")
        logger.info(f"Has MCP server: {hasattr(app, '_mcp_server')}")
        logger.info(f"Has WS server: {hasattr(app, '_ws_server')}")
        raise
    finally:
        # Stop the app
        app.stop()


if __name__ == "__main__":
    asyncio.run(test_basic_websocket_server())
