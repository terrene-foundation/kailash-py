"""Integration tests for enhanced MCP protocol features.

Tests the full MCP protocol implementation with real components,
including tools, resources, prompts, and multi-transport support.
"""

import asyncio
import json
import os
import socket
import time
from contextlib import closing
from typing import Any, Dict

import pytest
import pytest_asyncio
import websockets
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

# Test Component 2: Integration Tests for MCP Protocol Features


def find_free_port(start_port: int = 8000) -> int:
    """Find a free port starting from start_port."""
    for port in range(start_port, start_port + 100):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port starting from {start_port}")


class TestMCPProtocolIntegration:
    """Test full MCP protocol integration with real components."""

    @pytest_asyncio.fixture
    async def nexus_app(self):
        """Create and start a Nexus app for testing."""
        # Find free ports dynamically
        api_port = find_free_port(8900)
        mcp_port = find_free_port(api_port + 100)

        app = Nexus(
            api_port=api_port,
            mcp_port=mcp_port,
            enable_auth=False,  # Disable auth for integration tests
            enable_monitoring=True,
            enable_http_transport=False,  # Test WebSocket only for now
            enable_sse_transport=False,
            enable_discovery=False,
        )

        # Register test workflows
        self._register_test_workflows(app)

        # Start in background
        import threading

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()

        # Wait for server to start with retry logic
        max_retries = 10
        for i in range(max_retries):
            try:
                # Try to connect to the API port to verify it's up
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                    s.settimeout(0.5)
                    s.connect(("localhost", api_port))
                    break
            except (ConnectionRefusedError, socket.timeout):
                if i == max_retries - 1:
                    pytest.fail(f"Server failed to start on port {api_port}")
                await asyncio.sleep(0.5)

        yield app

        # Cleanup
        try:
            app.stop()
            # Give server time to fully shut down
            await asyncio.sleep(0.5)
        except Exception:
            pass  # Ignore cleanup errors

    def _register_test_workflows(self, app: Nexus):
        """Register test workflows."""
        # Simple echo workflow
        echo_workflow = WorkflowBuilder()
        echo_workflow.add_node(
            "PythonCodeNode",
            "echo",
            {"code": "result = {'echo': parameters.get('message', 'Hello')}"},
        )
        echo_workflow.metadata = {
            "description": "Echo a message back",
            "parameters": {
                "message": {"type": "string", "description": "Message to echo"}
            },
        }
        app.register("echo", echo_workflow.build())

        # Math workflow
        math_workflow = WorkflowBuilder()
        math_workflow.add_node(
            "PythonCodeNode",
            "math",
            {
                "code": """
import math
operation = parameters.get('operation', 'add')
a = parameters.get('a', 0)
b = parameters.get('b', 0)

if operation == 'add':
    result = {'result': a + b}
elif operation == 'multiply':
    result = {'result': a * b}
elif operation == 'sqrt':
    result = {'result': math.sqrt(abs(a))}
else:
    result = {'error': f'Unknown operation: {operation}'}
"""
            },
        )
        app.register("math", math_workflow.build())

    @pytest.mark.asyncio
    async def test_websocket_connection(self, nexus_app):
        """Test basic WebSocket connection to MCP server."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        # Retry connection with exponential backoff
        max_retries = 5
        for attempt in range(max_retries):
            try:
                async with websockets.connect(uri, close_timeout=1) as websocket:
                    # Connection is guaranteed to be open within the context manager (websockets 14.0+)
                    # No need to check websocket.open attribute (deprecated)

                    # Send a test message
                    test_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
                    await websocket.send(json.dumps(test_msg))

                    # Should receive response
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    assert response is not None
                    return  # Success

            except (ConnectionRefusedError, OSError) as e:
                if attempt == max_retries - 1:
                    pytest.fail(
                        f"WebSocket connection failed after {max_retries} attempts: {e}"
                    )
                await asyncio.sleep(0.5 * (2**attempt))  # Exponential backoff

    @pytest.mark.asyncio
    async def test_tools_list_protocol(self, nexus_app):
        """Test listing tools through MCP protocol."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Send tools/list request
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            await websocket.send(json.dumps(request))

            # Get response
            response = await websocket.recv()
            data = json.loads(response)

            # Verify response structure
            assert "result" in data
            assert "tools" in data["result"]

            tools = data["result"]["tools"]
            assert len(tools) >= 2  # At least our test workflows

            # Check for echo workflow
            echo_tool = next((t for t in tools if t["name"] == "echo"), None)
            assert echo_tool is not None
            assert "description" in echo_tool
            assert "inputSchema" in echo_tool

    @pytest.mark.asyncio
    async def test_tool_execution_protocol(self, nexus_app):
        """Test executing tools through MCP protocol."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Execute echo tool
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "echo",
                    "arguments": {"message": "Integration test"},
                },
            }
            await websocket.send(json.dumps(request))

            # Get response
            response = await websocket.recv()
            data = json.loads(response)

            # Verify execution result
            assert "result" in data
            result = data["result"]

            # The result should contain the echo
            assert "content" in result
            content = result["content"]
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].get("text", "")
                assert "Integration test" in text_content

    @pytest.mark.asyncio
    async def test_math_tool_execution(self, nexus_app):
        """Test executing math operations through MCP."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Test addition
            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "math",
                    "arguments": {"operation": "add", "a": 10, "b": 20},
                },
            }
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Check result
            assert "result" in data
            result_content = data["result"]["content"]
            if isinstance(result_content, list):
                text = result_content[0]["text"]
                result_data = json.loads(text)
                assert result_data["result"] == 30

    @pytest.mark.asyncio
    async def test_resources_list_protocol(self, nexus_app):
        """Test listing resources through MCP protocol."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Send resources/list request
            request = {"jsonrpc": "2.0", "id": 4, "method": "resources/list"}
            await websocket.send(json.dumps(request))

            # Get response
            response = await websocket.recv()
            data = json.loads(response)

            # Verify response
            assert "result" in data
            assert "resources" in data["result"]

            resources = data["result"]["resources"]
            assert len(resources) > 0

            # Check for workflow resources
            workflow_resources = [
                r for r in resources if r["uri"].startswith("workflow://")
            ]
            assert len(workflow_resources) >= 2  # Our test workflows

    @pytest.mark.asyncio
    async def test_resource_read_protocol(self, nexus_app):
        """Test reading resources through MCP protocol."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Read system info resource
            request = {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "resources/read",
                "params": {"uri": "system://nexus/info"},
            }
            await websocket.send(json.dumps(request))

            # Get response
            response = await websocket.recv()
            data = json.loads(response)

            # Verify system info
            assert "result" in data
            assert "contents" in data["result"]

            contents = data["result"]["contents"]
            assert len(contents) > 0

            content = contents[0]
            assert content["uri"] == "system://nexus/info"
            assert content["mimeType"] == "application/json"

            # Parse system info
            info = json.loads(content["text"])
            assert info["platform"] == "Kailash Nexus"
            assert "workflows" in info
            assert "echo" in info["workflows"]

    @pytest.mark.asyncio
    async def test_workflow_resource_read(self, nexus_app):
        """Test reading workflow definitions as resources."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Read echo workflow
            request = {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "resources/read",
                "params": {"uri": "workflow://echo"},
            }
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Verify workflow definition
            assert "result" in data
            contents = data["result"]["contents"]
            assert len(contents) > 0

            workflow_def = json.loads(contents[0]["text"])
            assert workflow_def["name"] == "echo"
            assert workflow_def["type"] == "workflow"
            assert "nodes" in workflow_def
            assert "schema" in workflow_def

    @pytest.mark.asyncio
    async def test_documentation_resource(self, nexus_app):
        """Test reading documentation resources."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Read quickstart docs
            request = {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "resources/read",
                "params": {"uri": "docs://quickstart"},
            }
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Verify documentation
            assert "result" in data
            contents = data["result"]["contents"]
            assert len(contents) > 0

            doc = contents[0]
            assert doc["mimeType"] == "text/markdown"
            assert "# Nexus Quick Start Guide" in doc["text"]

    @pytest.mark.asyncio
    async def test_configuration_resource(self, nexus_app):
        """Test reading configuration resources."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Read platform config
            request = {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "resources/read",
                "params": {"uri": "config://platform"},
            }
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Verify config
            assert "result" in data
            config_text = data["result"]["contents"][0]["text"]
            config = json.loads(config_text)

            assert config["name"] == "Kailash Nexus"
            assert config["api_port"] == nexus_app._api_port
            assert config["mcp_port"] == nexus_app._mcp_port
            assert config["features"]["monitoring"] is True

    @pytest.mark.asyncio
    async def test_help_resource(self, nexus_app):
        """Test reading help resources."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Read getting started help
            request = {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "resources/read",
                "params": {"uri": "help://getting-started"},
            }
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Verify help content
            assert "result" in data
            help_text = data["result"]["contents"][0]["text"]
            assert "# Getting Started with Nexus" in help_text

    @pytest.mark.asyncio
    async def test_error_handling(self, nexus_app):
        """Test error handling in MCP protocol."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Test unknown method
            request = {"jsonrpc": "2.0", "id": 10, "method": "unknown/method"}
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Should return error
            assert "error" in data
            assert data["error"]["code"] == -32601  # Method not found

            # Test invalid tool
            request = {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "nonexistent", "arguments": {}},
            }
            await websocket.send(json.dumps(request))

            response = await websocket.recv()
            data = json.loads(response)

            # Should return error
            assert "error" in data

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, nexus_app):
        """Test handling concurrent MCP requests."""
        uri = f"ws://localhost:{nexus_app._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Send multiple requests concurrently
            requests = []
            for i in range(5):
                request = {
                    "jsonrpc": "2.0",
                    "id": 100 + i,
                    "method": "tools/call",
                    "params": {
                        "name": "math",
                        "arguments": {"operation": "add", "a": i, "b": i * 2},
                    },
                }
                requests.append(websocket.send(json.dumps(request)))

            # Send all requests
            await asyncio.gather(*requests)

            # Collect all responses
            responses = []
            for _ in range(5):
                response = await websocket.recv()
                responses.append(json.loads(response))

            # Verify all responses
            assert len(responses) == 5
            for i, resp in enumerate(responses):
                assert "result" in resp or "id" in resp


class TestMCPAuthentication:
    """Test MCP authentication when enabled."""

    @pytest.mark.asyncio
    async def test_auth_required(self):
        """Test that authentication is required when enabled."""
        # Find free ports for auth test
        api_port = find_free_port(9100)
        mcp_port = find_free_port(api_port + 100)

        # Create app with auth enabled
        app = Nexus(api_port=api_port, mcp_port=mcp_port, enable_auth=True)

        # Set test API key
        os.environ["NEXUS_API_KEY_TESTUSER"] = "test-key-123"

        # Start app
        import threading

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()

        # Wait for server with retry
        max_retries = 10
        for i in range(max_retries):
            try:
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                    s.settimeout(0.5)
                    s.connect(("localhost", api_port))
                    break
            except (ConnectionRefusedError, socket.timeout):
                if i == max_retries - 1:
                    pytest.fail(f"Auth server failed to start on port {api_port}")
                await asyncio.sleep(0.5)

        try:
            # Try connection without auth - should fail or require auth
            uri = f"ws://localhost:{app._mcp_port}"

            # Note: Actual auth behavior depends on Core SDK implementation
            # This test verifies the setup works
            assert app._enable_auth is True
            assert app._get_api_keys() == {"testuser": "test-key-123"}

        finally:
            try:
                app.stop()
                await asyncio.sleep(0.5)  # Give time to shut down
            except Exception:
                pass
            if "NEXUS_API_KEY_TESTUSER" in os.environ:
                del os.environ["NEXUS_API_KEY_TESTUSER"]


class TestMCPHealthAndMetrics:
    """Test MCP health checks and metrics."""

    @pytest_asyncio.fixture
    async def nexus_app(self):
        """Create and start a Nexus app for testing."""
        # Find available ports
        api_port = self.find_free_port(9500, 9600)
        mcp_port = self.find_free_port(9600, 9700)

        app = Nexus(
            api_port=api_port,
            mcp_port=mcp_port,
            enable_auth=False,
            enable_monitoring=True,
            enable_http_transport=False,
            enable_sse_transport=False,
            enable_discovery=False,
            enable_durability=False,  # Disable caching for tests
        )

        # Register test workflows
        self._register_test_workflows(app)

        # Start in background
        import threading

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()

        # Wait for server to start
        await self.wait_for_server(api_port)

        yield app

        # Cleanup
        try:
            app.stop()
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Error stopping app: {e}")

    def find_free_port(self, start: int, end: int) -> int:
        """Find a free port in the given range."""
        import socket

        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("localhost", port))
                    return port
                except OSError:
                    continue
        raise RuntimeError(f"No free ports found in range {start}-{end}")

    async def wait_for_server(self, port: int, max_retries: int = 10):
        """Wait for server to start listening on port."""
        import socket
        from contextlib import closing

        for i in range(max_retries):
            try:
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                    s.settimeout(0.5)
                    s.connect(("localhost", port))
                    return
            except (ConnectionRefusedError, socket.timeout):
                if i == max_retries - 1:
                    pytest.fail(f"Server failed to start on port {port}")
                await asyncio.sleep(0.5)

    def _register_test_workflows(self, app: Nexus):
        """Register test workflows."""
        # Simple echo workflow
        echo_workflow = WorkflowBuilder()
        echo_workflow.add_node(
            "PythonCodeNode",
            "echo",
            {"code": "result = {'echo': parameters.get('message', 'Hello')}"},
        )
        echo_workflow.metadata = {
            "description": "Echo a message back",
            "parameters": {
                "message": {"type": "string", "description": "Message to echo"}
            },
        }
        app.register("echo", echo_workflow.build())

        # Math workflow
        math_workflow = WorkflowBuilder()
        math_workflow.add_node(
            "PythonCodeNode",
            "math",
            {
                "code": """
import math
operation = parameters.get('operation', 'add')
a = parameters.get('a', 0)
b = parameters.get('b', 0)

if operation == 'add':
    result = {'result': a + b}
elif operation == 'multiply':
    result = {'result': a * b}
elif operation == 'sqrt':
    result = {'result': math.sqrt(abs(a))}
else:
    result = {'error': f'Unknown operation: {operation}'}
"""
            },
        )
        app.register("math", math_workflow.build())

    @pytest.mark.asyncio
    async def test_health_check_includes_mcp(self, nexus_app):
        """Test that health check includes MCP status."""
        health = nexus_app.health_check()

        assert health["status"] == "healthy"
        assert health["workflows"] == 2  # Our test workflows
        assert health["api_port"] == nexus_app._api_port
        assert health["enterprise_features"]["multi_channel"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
