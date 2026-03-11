"""Test WebSocket server directly without full Nexus."""

import asyncio
import json
import logging
import os
import sys

import pytest

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from nexus.mcp_websocket_server import MCPWebSocketServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_websocket_server():
    """Test WebSocket server directly."""
    print("Starting test...")

    # Create mock MCP server
    class MockMCPServer:
        def __init__(self):
            self._tools = {"echo": lambda message="Hello": {"echo": message}}
            self._resources = {
                "system://info": lambda uri: {
                    "uri": uri,
                    "mimeType": "application/json",
                    "content": json.dumps({"test": "data"}),
                }
            }

    mock_server = MockMCPServer()

    # Create WebSocket server
    ws_server = MCPWebSocketServer(mock_server, host="127.0.0.1", port=3903)

    # Start server
    logger.info("Starting WebSocket server on port 3903...")
    await ws_server.start()

    # Give it time to start
    await asyncio.sleep(1)

    logger.info("WebSocket server should be running now")

    # Keep running for a bit
    await asyncio.sleep(5)

    # Stop server
    await ws_server.stop()
    logger.info("WebSocket server stopped")


if __name__ == "__main__":
    asyncio.run(test_websocket_server())
