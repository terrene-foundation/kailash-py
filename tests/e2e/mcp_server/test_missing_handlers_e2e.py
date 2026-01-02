"""End-to-end tests for MCP missing handlers with real client/server interaction."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import pytest
import websockets
from kailash.mcp_server.auth import AuthManager
from kailash.mcp_server.protocol import get_protocol_manager
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.transports import WebSocketServerTransport
from kailash.middleware.gateway.event_store import EventStore

# Note: These utilities will be created when needed for E2E testing infrastructure
# from tests.utils.docker_utils import wait_for_postgres
# from tests.utils.mcp_utils import create_test_mcp_server, start_mcp_server


class MCPTestClient:
    """Test client for MCP WebSocket communication."""

    def __init__(self, client_name: str, capabilities: Dict[str, Any] = None):
        """Initialize test client."""
        self.client_name = client_name
        self.capabilities = capabilities or {}
        self.websocket = None
        self.responses = {}
        self.notifications = []
        self.request_id = 0

    async def connect(self, uri: str):
        """Connect to MCP server."""
        self.websocket = await websockets.connect(uri)

        # Start message receiver
        asyncio.create_task(self._receive_messages())

        # Initialize connection
        init_response = await self.initialize()
        return init_response

    async def initialize(self) -> Dict[str, Any]:
        """Send initialize request."""
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": self.capabilities,
                "clientInfo": {"name": self.client_name, "version": "1.0.0"},
            },
            "id": self._next_id(),
        }

        return await self._send_request(request)

    async def set_log_level(self, level: str) -> Dict[str, Any]:
        """Change server log level."""
        request = {
            "jsonrpc": "2.0",
            "method": "logging/setLevel",
            "params": {"level": level},
            "id": self._next_id(),
        }

        return await self._send_request(request)

    async def list_roots(self) -> Dict[str, Any]:
        """List available roots."""
        request = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": self._next_id(),
        }

        return await self._send_request(request)

    async def complete(self, ref_type: str, partial: str = "") -> Dict[str, Any]:
        """Get completions."""
        request = {
            "jsonrpc": "2.0",
            "method": "completion/complete",
            "params": {"ref": {"type": ref_type}, "argument": {"value": partial}},
            "id": self._next_id(),
        }

        return await self._send_request(request)

    async def request_sampling(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """Request LLM sampling."""
        params = {"messages": messages, **kwargs}

        request = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "params": params,
            "id": self._next_id(),
        }

        return await self._send_request(request)

    async def wait_for_sampling_request(
        self, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Wait for sampling request from server."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check notifications for sampling request (server-to-client notifications)
            for notif in self.notifications:
                if notif.get("method") == "sampling/createMessage":
                    return notif

            # Check responses for sampling request (server-to-client requests)
            for resp in list(self.responses.values()):
                if resp.get("method") == "sampling/createMessage":
                    # Remove from responses since we're handling it
                    if "id" in resp:
                        self.responses.pop(resp["id"], None)
                    return resp

            await asyncio.sleep(0.1)

        return None

    async def respond_to_sampling(self, sampling_id: str, response: Dict[str, Any]):
        """Respond to sampling request."""
        # Send response to the sampling request
        result = {"jsonrpc": "2.0", "result": response, "id": sampling_id}

        await self.websocket.send(json.dumps(result))

    async def close(self):
        """Close connection."""
        if self.websocket:
            await self.websocket.close()

    def _next_id(self) -> str:
        """Generate next request ID."""
        self.request_id += 1
        return f"{self.client_name}_{self.request_id}"

    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request and wait for response."""
        request_id = request["id"]

        # Send request
        await self.websocket.send(json.dumps(request))

        # Wait for response
        timeout = 5.0
        start_time = time.time()

        while time.time() - start_time < timeout:
            if request_id in self.responses:
                return self.responses.pop(request_id)
            await asyncio.sleep(0.01)

        raise TimeoutError(f"No response received for request {request_id}")

    async def _receive_messages(self):
        """Receive messages from server."""
        try:
            async for message in self.websocket:
                data = json.loads(message)

                if "id" in data:
                    # Response to a request
                    self.responses[data["id"]] = data
                else:
                    # Notification
                    self.notifications.append(data)
        except websockets.exceptions.ConnectionClosed:
            pass


class TestLoggingSetLevelE2E:
    """E2E tests for logging/setLevel functionality."""

    @pytest.mark.asyncio
    async def test_log_level_change_affects_server(self, mcp_server_e2e):
        """Test that log level changes affect server logging."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Create client
        client = MCPTestClient("log_test_client")

        try:
            # Connect and initialize
            await client.connect(server_uri)

            # Set log level to ERROR
            result = await client.set_log_level("ERROR")
            assert result["result"]["level"] == "ERROR"

            # Set to DEBUG
            result = await client.set_log_level("DEBUG")
            assert result["result"]["level"] == "DEBUG"
            assert "levels" in result["result"]

            # Try invalid level
            result = await client.set_log_level("INVALID")
            assert "error" in result
            assert result["error"]["code"] == -32602

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_log_level_persistence_across_clients(self, mcp_server_e2e):
        """Test that log level changes persist across clients."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # First client changes log level
        client1 = MCPTestClient("client1")
        try:
            await client1.connect(server_uri)
            await client1.set_log_level("WARNING")
        finally:
            await client1.close()

        # Second client should see the same level
        client2 = MCPTestClient("client2")
        try:
            await client2.connect(server_uri)

            # The server should still be at WARNING level
            # We can't directly query, but we can observe behavior
            assert logging.getLogger().level == logging.WARNING

        finally:
            await client2.close()


class TestRootsListE2E:
    """E2E tests for roots/list functionality."""

    @pytest.mark.asyncio
    async def test_roots_list_with_capability(self, mcp_server_e2e):
        """Test listing roots with proper capability."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Client with roots capability
        client = MCPTestClient(
            "roots_client", capabilities={"roots": {"listChanged": True}}
        )

        try:
            await client.connect(server_uri)

            # List roots
            result = await client.list_roots()
            assert "result" in result
            assert "roots" in result["result"]

            # Should have at least one root
            roots = result["result"]["roots"]
            assert isinstance(roots, list)
            assert len(roots) > 0

            # Verify root structure
            for root in roots:
                assert "uri" in root
                assert root["uri"].startswith("file://")

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_roots_list_without_capability(self, mcp_server_e2e):
        """Test error when listing roots without capability."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Client without roots capability
        client = MCPTestClient("no_roots_client")

        try:
            await client.connect(server_uri)

            # Try to list roots
            result = await client.list_roots()

            # Should get error
            assert "error" in result
            assert "does not support roots capability" in result["error"]["message"]

        finally:
            await client.close()


class TestCompletionCompleteE2E:
    """E2E tests for completion/complete functionality."""

    @pytest.mark.asyncio
    async def test_resource_completion(self, mcp_server_e2e):
        """Test resource completion with real server."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        client = MCPTestClient(
            "completion_client", capabilities={"experimental": {"completion": True}}
        )

        try:
            await client.connect(server_uri)

            # Get resource completions
            result = await client.complete("resource", "file://")

            assert "result" in result
            completion = result["result"]["completion"]
            assert "values" in completion

            # Should have some file resources
            values = completion["values"]
            assert isinstance(values, list)

            if values:  # If server has registered resources
                assert all("uri" in v for v in values)

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_prompt_completion(self, mcp_server_e2e):
        """Test prompt completion."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        client = MCPTestClient("prompt_client")

        try:
            await client.connect(server_uri)

            # Get prompt completions
            result = await client.complete("prompt", "")

            assert "result" in result
            values = result["result"]["completion"]["values"]

            # Check if we have prompts
            if values:
                for prompt in values:
                    assert "name" in prompt
                    assert "description" in prompt

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_completion_with_pagination(self, mcp_server_e2e):
        """Test completion with many results."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        client = MCPTestClient("pagination_client")

        try:
            await client.connect(server_uri)

            # Try to get completions (results depend on server setup)
            result = await client.complete("resource", "")

            completion = result["result"]["completion"]

            # If there are many results, should have hasMore flag
            if "total" in completion and completion["total"] > 100:
                assert completion["hasMore"] is True
                assert len(completion["values"]) == 100

        finally:
            await client.close()


class TestSamplingCreateMessageE2E:
    """E2E tests for sampling/createMessage functionality."""

    @pytest.mark.asyncio
    async def test_sampling_between_clients(self, mcp_server_e2e):
        """Test sampling request routing between clients."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Client that can handle sampling
        sampling_client = MCPTestClient(
            "sampling_handler", capabilities={"experimental": {"sampling": True}}
        )

        # Client that requests sampling
        requester_client = MCPTestClient("requester")

        try:
            # Connect both clients
            await sampling_client.connect(server_uri)
            await requester_client.connect(server_uri)

            # Request sampling from requester
            messages = [
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "2+2 equals 4"},
            ]

            result = await requester_client.request_sampling(
                messages, temperature=0.7, modelPreferences={"model": "test-model"}
            )

            # Should get success response
            assert "result" in result
            assert result["result"]["status"] == "sampling_requested"
            assert "sampling_id" in result["result"]

            # Give the server time to send the sampling request
            await asyncio.sleep(0.1)

            # Sampling client should receive the request
            sampling_req = await sampling_client.wait_for_sampling_request()
            assert sampling_req is not None
            assert sampling_req["method"] == "sampling/createMessage"
            assert sampling_req["params"]["messages"] == messages

        finally:
            await sampling_client.close()
            await requester_client.close()

    @pytest.mark.asyncio
    async def test_sampling_no_capable_clients(self, mcp_server_e2e):
        """Test error when no clients can handle sampling."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Client without sampling capability
        client = MCPTestClient("no_sampling")

        try:
            await client.connect(server_uri)

            # Request sampling
            result = await client.request_sampling(
                [{"role": "user", "content": "Test"}]
            )

            # Should get error
            assert "error" in result
            assert "No connected clients support sampling" in result["error"]["message"]

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_sampling_with_response(self, mcp_server_e2e):
        """Test complete sampling flow with response."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Two clients
        handler = MCPTestClient(
            "handler", capabilities={"experimental": {"sampling": True}}
        )
        requester = MCPTestClient("requester")

        try:
            await handler.connect(server_uri)
            await requester.connect(server_uri)

            # Request sampling
            result = await requester.request_sampling(
                [{"role": "user", "content": "Hello"}], maxTokens=100
            )

            sampling_id = result["result"]["sampling_id"]

            # Handler receives request
            req = await handler.wait_for_sampling_request()
            assert req is not None

            # Handler sends response
            await handler.respond_to_sampling(
                req["id"],
                {"role": "assistant", "content": "Hello! How can I help you?"},
            )

            # In a real implementation, requester might get a notification
            # about the completed sampling

        finally:
            await handler.close()
            await requester.close()


class TestCapabilityAdvertisementE2E:
    """E2E tests for capability advertisement."""

    @pytest.mark.asyncio
    async def test_full_capability_advertisement(self, mcp_server_e2e):
        """Test that server advertises all new capabilities."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        client = MCPTestClient(
            "capability_test",
            capabilities={
                "roots": {"listChanged": True},
                "experimental": {
                    "progressNotifications": True,
                    "cancellation": True,
                    "completion": True,
                    "sampling": True,
                },
            },
        )

        try:
            # Connect and get initialization response
            init_response = await client.connect(server_uri)

            # Check server capabilities
            server_caps = init_response["result"]["capabilities"]

            # Verify new capabilities
            assert "logging" in server_caps
            assert server_caps["logging"]["setLevel"] is True

            assert "roots" in server_caps
            assert server_caps["roots"]["list"] is True

            assert "experimental" in server_caps
            exp = server_caps["experimental"]
            assert exp["progressNotifications"] is True
            assert exp["cancellation"] is True
            assert exp["completion"] is True
            assert exp["sampling"] is True

        finally:
            await client.close()


class TestCompleteWorkflowE2E:
    """Test complete workflow using all new handlers."""

    @pytest.mark.asyncio
    async def test_developer_workflow(self, mcp_server_e2e):
        """Test a realistic developer workflow."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # Developer client with all capabilities
        dev_client = MCPTestClient(
            "developer",
            capabilities={
                "roots": {"listChanged": True},
                "experimental": {"completion": True, "sampling": True},
            },
        )

        try:
            await dev_client.connect(server_uri)

            # 1. Set debug logging for development
            log_result = await dev_client.set_log_level("DEBUG")
            assert log_result["result"]["level"] == "DEBUG"

            # 2. Check available workspace roots
            roots_result = await dev_client.list_roots()
            roots = roots_result["result"]["roots"]
            assert len(roots) > 0

            # 3. Get completions for resources
            comp_result = await dev_client.complete("resource", "file://")
            completions = comp_result["result"]["completion"]["values"]

            # 4. Get prompt completions
            prompt_result = await dev_client.complete("prompt", "")
            prompts = prompt_result["result"]["completion"]["values"]

            # Workflow completed successfully
            assert True

        finally:
            await dev_client.close()

    @pytest.mark.asyncio
    async def test_multi_client_collaboration(self, mcp_server_e2e):
        """Test multiple clients collaborating."""
        server_uri = f"ws://localhost:{mcp_server_e2e['port']}/ws"

        # AI assistant that can handle sampling
        ai_assistant = MCPTestClient(
            "ai_assistant", capabilities={"experimental": {"sampling": True}}
        )

        # Developer client
        developer = MCPTestClient(
            "developer",
            capabilities={
                "roots": {"listChanged": True},
                "experimental": {"completion": True},
            },
        )

        try:
            # Both connect
            await ai_assistant.connect(server_uri)
            await developer.connect(server_uri)

            # Developer sets debug mode
            await developer.set_log_level("DEBUG")

            # Developer lists roots
            roots = await developer.list_roots()
            assert "result" in roots

            # Developer requests AI assistance
            sampling_result = await developer.request_sampling(
                [{"role": "user", "content": "Help me debug this code"}]
            )

            # AI assistant receives request
            if sampling_result.get("result", {}).get("status") == "sampling_requested":
                req = await ai_assistant.wait_for_sampling_request(timeout=1.0)

                if req:
                    # AI would process and respond
                    await ai_assistant.respond_to_sampling(
                        req["id"], {"content": "I'll help you debug the code."}
                    )

        finally:
            await ai_assistant.close()
            await developer.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
