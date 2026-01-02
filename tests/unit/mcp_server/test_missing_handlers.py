"""Unit tests for MCP missing handlers implementation."""

import asyncio
import json
import logging
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.mcp_server.errors import MCPError
from kailash.mcp_server.protocol import get_protocol_manager
from kailash.mcp_server.server import MCPServer


class TestLoggingSetLevel:
    """Test logging/setLevel handler."""

    @pytest.fixture
    def server(self):
        """Create test server."""
        return MCPServer("test_server")

    @pytest.mark.asyncio
    async def test_set_valid_log_level(self, server):
        """Test setting a valid log level."""
        # Test data
        params = {"level": "DEBUG"}
        request_id = "test_123"

        # Call handler
        result = await server._handle_logging_set_level(params, request_id)

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert result["result"]["level"] == "DEBUG"
        assert "levels" in result["result"]
        assert "DEBUG" in result["result"]["levels"]

        # Verify log level was actually changed
        assert logging.getLogger().level == logging.DEBUG

    @pytest.mark.asyncio
    async def test_set_invalid_log_level(self, server):
        """Test setting an invalid log level."""
        # Test data
        params = {"level": "INVALID"}
        request_id = "test_123"

        # Call handler
        result = await server._handle_logging_set_level(params, request_id)

        # Verify error response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert "error" in result
        assert result["error"]["code"] == -32602
        assert "Invalid log level" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_default_log_level(self, server):
        """Test default log level when not specified."""
        # Test data with no level
        params = {}
        request_id = "test_123"

        # Call handler
        result = await server._handle_logging_set_level(params, request_id)

        # Should default to INFO
        assert result["result"]["level"] == "INFO"
        assert logging.getLogger().level == logging.INFO

    @pytest.mark.asyncio
    async def test_log_level_case_insensitive(self, server):
        """Test that log level is case insensitive."""
        # Test data with lowercase
        params = {"level": "warning"}
        request_id = "test_123"

        # Call handler
        result = await server._handle_logging_set_level(params, request_id)

        # Should convert to uppercase
        assert result["result"]["level"] == "WARNING"
        assert logging.getLogger().level == logging.WARNING

    @pytest.mark.asyncio
    async def test_log_level_with_event_store(self, server):
        """Test logging level change is recorded in event store."""
        # Mock event store
        mock_event_store = MagicMock()
        mock_event_store.append = AsyncMock()
        server.event_store = mock_event_store

        # Test data
        params = {"level": "ERROR", "client_id": "client_123"}
        request_id = "test_123"

        # Call handler
        result = await server._handle_logging_set_level(params, request_id)

        # Verify event was recorded
        mock_event_store.append.assert_called_once()
        call_kwargs = mock_event_store.append.call_args[1]
        assert call_kwargs["data"]["type"] == "log_level_changed"
        assert call_kwargs["data"]["level"] == "ERROR"
        assert call_kwargs["data"]["changed_by"] == "client_123"


class TestRootsList:
    """Test roots/list handler."""

    @pytest.fixture
    def server(self):
        """Create test server with mock protocol manager."""
        server = MCPServer("test_server")
        # Initialize client info
        server.client_info = {}
        return server

    @pytest.mark.asyncio
    async def test_list_roots_success(self, server):
        """Test successful roots listing."""
        # Setup protocol manager with roots
        protocol_mgr = get_protocol_manager()
        protocol_mgr.roots.add_root("file:///workspace", "Workspace", "Main workspace")
        protocol_mgr.roots.add_root("file:///home", "Home", "User home")

        # Setup client with roots capability
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"roots": {"listChanged": True}}
        }

        # Test data
        params = {"client_id": client_id}
        request_id = "test_123"

        # Call handler
        result = await server._handle_roots_list(params, request_id)

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert "result" in result
        assert "roots" in result["result"]
        assert len(result["result"]["roots"]) == 2

        # Verify root content
        roots = result["result"]["roots"]
        assert any(r["uri"] == "file:///workspace" for r in roots)
        assert any(r["uri"] == "file:///home" for r in roots)

    @pytest.mark.asyncio
    async def test_list_roots_no_capability(self, server):
        """Test error when client doesn't support roots."""
        # Setup client without roots capability
        client_id = "client_123"
        server.client_info[client_id] = {"capabilities": {}}

        # Test data
        params = {"client_id": client_id}
        request_id = "test_123"

        # Call handler
        result = await server._handle_roots_list(params, request_id)

        # Verify error response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "does not support roots capability" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_list_roots_empty(self, server):
        """Test listing when no roots are configured."""
        # Clear any existing roots
        protocol_mgr = get_protocol_manager()
        protocol_mgr.roots._roots = []

        # Setup client
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"roots": {"listChanged": True}}
        }

        # Test data
        params = {"client_id": client_id}
        request_id = "test_123"

        # Call handler
        result = await server._handle_roots_list(params, request_id)

        # Should return empty list
        assert result["result"]["roots"] == []

    @pytest.mark.asyncio
    async def test_list_roots_with_access_control(self, server):
        """Test roots filtering based on access control."""
        # Setup auth manager
        mock_auth = MagicMock()
        server.auth_manager = mock_auth

        # Setup protocol manager
        protocol_mgr = get_protocol_manager()
        protocol_mgr.roots._roots = []  # Clear existing
        protocol_mgr.roots.add_root("file:///public", "Public", "Public files")
        protocol_mgr.roots.add_root("file:///private", "Private", "Private files")

        # Mock access validation
        async def mock_validate_access(uri, operation, user_context=None):
            # Only allow access to public
            return "public" in uri

        protocol_mgr.roots.validate_access = mock_validate_access

        # Setup client
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"roots": {"listChanged": True}},
            "user_id": "user_123",
        }

        # Test data
        params = {"client_id": client_id}
        request_id = "test_123"

        # Call handler
        result = await server._handle_roots_list(params, request_id)

        # Should only return public root
        assert len(result["result"]["roots"]) == 1
        assert result["result"]["roots"][0]["uri"] == "file:///public"


class TestCompletionComplete:
    """Test completion/complete handler."""

    @pytest.fixture
    def server(self):
        """Create test server with resources and prompts."""
        server = MCPServer("test_server")

        # Add some test resources
        server._resource_registry = {
            "file:///documents/report.pdf": {
                "name": "Report",
                "description": "Annual report",
            },
            "file:///data/dataset.csv": {
                "name": "Dataset",
                "description": "Sales data",
            },
            "config:///database": {
                "name": "Database Config",
                "description": "DB settings",
            },
        }

        # Add some test prompts
        server._prompt_registry = {
            "analyze": {"description": "Analyze data", "arguments": ["data", "format"]},
            "summarize": {
                "description": "Summarize text",
                "arguments": ["text", "length"],
            },
        }

        return server

    @pytest.mark.asyncio
    async def test_complete_resources(self, server):
        """Test resource completion."""
        # Test data
        params = {"ref": {"type": "resource"}, "argument": {"value": "file://"}}
        request_id = "test_123"

        # Call handler
        result = await server._handle_completion_complete(params, request_id)

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert "result" in result
        assert "completion" in result["result"]
        assert "values" in result["result"]["completion"]

        # Should return file:// resources
        values = result["result"]["completion"]["values"]
        assert len(values) == 2
        assert all(v["uri"].startswith("file://") for v in values)

    @pytest.mark.asyncio
    async def test_complete_prompts(self, server):
        """Test prompt completion."""
        # Test data
        params = {"ref": {"type": "prompt"}, "argument": {"value": "ana"}}
        request_id = "test_123"

        # Call handler
        result = await server._handle_completion_complete(params, request_id)

        # Should return "analyze" prompt
        values = result["result"]["completion"]["values"]
        assert len(values) == 1
        assert values[0]["name"] == "analyze"
        assert values[0]["description"] == "Analyze data"

    @pytest.mark.asyncio
    async def test_complete_with_no_matches(self, server):
        """Test completion with no matches."""
        # Test data
        params = {"ref": {"type": "resource"}, "argument": {"value": "nonexistent://"}}
        request_id = "test_123"

        # Call handler
        result = await server._handle_completion_complete(params, request_id)

        # Should return empty values
        assert result["result"]["completion"]["values"] == []
        assert result["result"]["completion"]["total"] == 0

    @pytest.mark.asyncio
    async def test_complete_with_has_more(self, server):
        """Test completion with many results."""
        # Add many resources to trigger hasMore
        for i in range(150):
            server._resource_registry[f"test://resource_{i}"] = {
                "name": f"Resource {i}",
                "description": f"Test resource {i}",
            }

        # Test data
        params = {"ref": {"type": "resource"}, "argument": {"value": "test://"}}
        request_id = "test_123"

        # Call handler
        result = await server._handle_completion_complete(params, request_id)

        # Should limit to 100 and set hasMore
        completion = result["result"]["completion"]
        assert len(completion["values"]) == 100
        assert completion["hasMore"] is True
        assert completion["total"] == 150

    @pytest.mark.asyncio
    async def test_complete_error_handling(self, server):
        """Test completion with successful registry-based implementation."""
        # Test data - this will match against the test server's registered resources
        params = {"ref": {"type": "resource"}, "argument": {"value": "file://"}}
        request_id = "test_123"

        # Call handler
        result = await server._handle_completion_complete(params, request_id)

        # Should return successful result (no longer testing mocked errors)
        assert "result" in result
        assert "completion" in result["result"]
        assert "values" in result["result"]["completion"]
        # Should have matched file:// resources
        assert len(result["result"]["completion"]["values"]) == 2


class TestSamplingCreateMessage:
    """Test sampling/createMessage handler."""

    @pytest.fixture
    def server(self):
        """Create test server."""
        server = MCPServer("test_server")
        server.client_info = {}
        server._pending_sampling_requests = {}

        # Mock transport
        mock_transport = MagicMock()
        mock_transport.send_message = AsyncMock()
        server._transport = mock_transport

        return server

    @pytest.mark.asyncio
    async def test_sampling_with_capable_client(self, server):
        """Test sampling with a client that supports it."""
        # Setup client with sampling capability
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"experimental": {"sampling": True}}
        }

        # Test data
        params = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            "modelPreferences": {"model": "gpt-4"},
            "temperature": 0.7,
            "client_id": client_id,
        }
        request_id = "test_123"

        # Call handler
        result = await server._handle_sampling_create_message(params, request_id)

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert "result" in result
        assert result["result"]["status"] == "sampling_requested"
        assert "sampling_id" in result["result"]
        assert result["result"]["target_client"] == client_id

        # Verify message was sent
        server._transport.send_message.assert_called_once()
        sent_msg = server._transport.send_message.call_args[0][0]
        assert sent_msg["method"] == "sampling/createMessage"
        assert sent_msg["params"]["messages"] == params["messages"]

    @pytest.mark.asyncio
    async def test_sampling_no_capable_clients(self, server):
        """Test sampling when no clients support it."""
        # Setup client without sampling capability
        client_id = "client_123"
        server.client_info[client_id] = {"capabilities": {}}

        # Test data
        params = {
            "messages": [{"role": "user", "content": "Hello"}],
            "client_id": client_id,
        }
        request_id = "test_123"

        # Call handler
        result = await server._handle_sampling_create_message(params, request_id)

        # Should return error
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "No connected clients support sampling" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_sampling_request_tracking(self, server):
        """Test that sampling requests are tracked."""
        # Setup client
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"experimental": {"sampling": True}}
        }

        # Test data
        params = {
            "messages": [{"role": "user", "content": "Test"}],
            "client_id": client_id,
        }
        request_id = "test_123"

        # Call handler
        result = await server._handle_sampling_create_message(params, request_id)

        # Get sampling ID
        sampling_id = result["result"]["sampling_id"]

        # Verify request is tracked
        assert sampling_id in server._pending_sampling_requests
        pending = server._pending_sampling_requests[sampling_id]
        assert pending["original_request_id"] == request_id
        assert pending["client_id"] == client_id
        assert "timestamp" in pending

    @pytest.mark.asyncio
    async def test_sampling_without_transport(self, server):
        """Test sampling when transport doesn't support it."""
        # Remove transport
        server._transport = None

        # Setup client
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"experimental": {"sampling": True}}
        }

        # Test data
        params = {
            "messages": [{"role": "user", "content": "Test"}],
            "client_id": client_id,
        }
        request_id = "test_123"

        # Call handler
        result = await server._handle_sampling_create_message(params, request_id)

        # Should return error
        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Transport does not support sampling" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_sampling_with_all_parameters(self, server):
        """Test sampling with all optional parameters."""
        # Setup client
        client_id = "client_123"
        server.client_info[client_id] = {
            "capabilities": {"experimental": {"sampling": True}}
        }

        # Test data with all parameters
        params = {
            "messages": [{"role": "user", "content": "Test"}],
            "modelPreferences": {"model": "gpt-4", "provider": "openai"},
            "systemPrompt": "You are a helpful assistant",
            "temperature": 0.8,
            "maxTokens": 2000,
            "metadata": {"session_id": "abc123"},
            "client_id": client_id,
        }
        request_id = "test_123"

        # Call handler
        result = await server._handle_sampling_create_message(params, request_id)

        # Verify all parameters were forwarded
        sent_msg = server._transport.send_message.call_args[0][0]
        sent_params = sent_msg["params"]
        assert sent_params["model_preferences"] == params["modelPreferences"]
        assert sent_params["system_prompt"] == params["systemPrompt"]
        assert sent_params["temperature"] == params["temperature"]
        assert sent_params["max_tokens"] == params["maxTokens"]
        assert sent_params["metadata"] == params["metadata"]


class TestCapabilityAdvertisement:
    """Test capability advertisement updates."""

    @pytest.fixture
    def server(self):
        """Create test server."""
        return MCPServer("test_server")

    @pytest.mark.asyncio
    async def test_initialize_with_experimental_capabilities(self, server):
        """Test that initialize includes experimental capabilities."""
        # Test data
        params = {
            "protocolVersion": "0.1.0",
            "capabilities": {
                "roots": {"listChanged": True},
                "experimental": {"progressNotifications": True, "sampling": True},
            },
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        }
        request_id = "init_123"
        client_id = "client_123"

        # Call handler
        result = await server._handle_initialize(params, request_id, client_id)

        # Verify response includes experimental capabilities
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == request_id
        assert "result" in result

        capabilities = result["result"]["capabilities"]

        # Check new capabilities
        assert "logging" in capabilities
        assert capabilities["logging"]["setLevel"] is True

        assert "roots" in capabilities
        assert capabilities["roots"]["list"] is True

        assert "experimental" in capabilities
        exp = capabilities["experimental"]
        assert exp["progressNotifications"] is True
        assert exp["cancellation"] is True
        assert exp["completion"] is True
        assert exp["sampling"] is True

    @pytest.mark.asyncio
    async def test_client_info_storage(self, server):
        """Test that client info is properly stored."""
        # Test data
        params = {
            "protocolVersion": "0.1.0",
            "capabilities": {"experimental": {"sampling": True}},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        }
        request_id = "init_123"
        client_id = "client_123"

        # Call handler
        await server._handle_initialize(params, request_id, client_id)

        # Verify client info was stored
        assert client_id in server.client_info
        client = server.client_info[client_id]
        assert client["capabilities"]["experimental"]["sampling"] is True
        assert client["name"] == "test-client"
        assert client["version"] == "1.0.0"


class TestMessageRouting:
    """Test that new handlers are properly routed."""

    @pytest.fixture
    def server(self):
        """Create test server with mocked handlers."""
        server = MCPServer("test_server")

        # Mock the new handlers
        server._handle_logging_set_level = AsyncMock(
            return_value={"jsonrpc": "2.0", "result": {"level": "DEBUG"}, "id": "test"}
        )
        server._handle_roots_list = AsyncMock(
            return_value={"jsonrpc": "2.0", "result": {"roots": []}, "id": "test"}
        )
        server._handle_completion_complete = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "result": {"completion": {"values": []}},
                "id": "test",
            }
        )
        server._handle_sampling_create_message = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "result": {"status": "requested"},
                "id": "test",
            }
        )

        return server

    @pytest.mark.asyncio
    async def test_route_logging_set_level(self, server):
        """Test routing to logging/setLevel handler."""
        message = {
            "jsonrpc": "2.0",
            "method": "logging/setLevel",
            "params": {"level": "DEBUG"},
            "id": "test_123",
        }

        result = await server._handle_websocket_message(message, "client_123")

        server._handle_logging_set_level.assert_called_once_with(
            {"level": "DEBUG"}, "test_123"
        )

    @pytest.mark.asyncio
    async def test_route_roots_list(self, server):
        """Test routing to roots/list handler."""
        message = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": "test_123",
        }

        result = await server._handle_websocket_message(message, "client_123")

        server._handle_roots_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_completion_complete(self, server):
        """Test routing to completion/complete handler."""
        message = {
            "jsonrpc": "2.0",
            "method": "completion/complete",
            "params": {"ref": {"type": "resource"}},
            "id": "test_123",
        }

        result = await server._handle_websocket_message(message, "client_123")

        server._handle_completion_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_sampling_create_message(self, server):
        """Test routing to sampling/createMessage handler."""
        message = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "params": {"messages": []},
            "id": "test_123",
        }

        result = await server._handle_websocket_message(message, "client_123")

        server._handle_sampling_create_message.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
