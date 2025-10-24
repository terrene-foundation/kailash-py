"""Integration tests for MCP missing handlers with real infrastructure."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict

import pytest
import pytest_asyncio
from kailash.mcp_server.auth import AuthManager
from kailash.mcp_server.protocol import get_protocol_manager
from kailash.mcp_server.server import MCPServer
from kailash.middleware.gateway.event_store import EventStore

from tests.integration.docker_test_base import DockerIntegrationTestBase
from tests.utils.docker_config import ensure_docker_services


@pytest.mark.integration
class TestLoggingSetLevelIntegration(DockerIntegrationTestBase):
    """Integration tests for logging/setLevel handler."""

    @pytest_asyncio.fixture
    async def server_with_event_store(self, postgres_conn):
        """Create server with real event store."""
        # Create event store with real database
        event_store = EventStore(postgres_conn)

        # Create server
        server = MCPServer("test_server", event_store=event_store)

        # Initialize a client
        client_id = "test_client"
        await server._handle_initialize(
            {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "init_123",
            client_id,
        )

        return server

    @pytest.mark.asyncio
    async def test_log_level_persistence_with_event_store(
        self, server_with_event_store
    ):
        """Test that log level changes are persisted in event store."""
        server = server_with_event_store

        # Change log level
        result = await server._handle_logging_set_level(
            {"level": "WARNING", "client_id": "test_client"}, "req_123"
        )

        # Verify success
        assert result["result"]["level"] == "WARNING"

        # Query event store for the event
        events = await server.event_store.get_events(request_id="req_123")

        # Verify event was recorded
        assert len(events) == 1
        event = events[0]
        assert event.data["type"] == "log_level_changed"
        assert event.data["level"] == "WARNING"
        assert event.data["changed_by"] == "test_client"

    @pytest.mark.asyncio
    async def test_log_level_affects_server_logging(self, server_with_event_store):
        """Test that log level change affects actual server logging."""
        server = server_with_event_store

        # Set to ERROR level
        await server._handle_logging_set_level({"level": "ERROR"}, "req_123")

        # Create a test logger
        test_logger = logging.getLogger("kailash.mcp_server.test")

        # Capture log output
        import io

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        test_logger.addHandler(handler)

        # Try logging at different levels
        test_logger.debug("Debug message")
        test_logger.info("Info message")
        test_logger.warning("Warning message")
        test_logger.error("Error message")

        # Only ERROR should be logged
        output = log_capture.getvalue()
        assert "Debug message" not in output
        assert "Info message" not in output
        assert "Warning message" not in output
        assert "Error message" in output

        # Cleanup
        test_logger.removeHandler(handler)


@pytest.mark.integration
class TestRootsListIntegration(DockerIntegrationTestBase):
    """Integration tests for roots/list handler."""

    @pytest_asyncio.fixture
    async def server_with_auth(self, postgres_conn):
        """Create server with real auth manager."""
        # Create auth manager
        auth_manager = AuthManager(secret_key="test_secret", db_pool=postgres_conn)

        # Create test user
        await auth_manager.create_user(
            username="test_user", password="test_pass", organization_id="org_123"
        )

        # Create server
        server = MCPServer("test_server", auth_provider=auth_manager)

        # Add some roots
        protocol_mgr = get_protocol_manager()
        protocol_mgr.roots._roots = []  # Clear existing
        protocol_mgr.roots.add_root("file:///public", "Public", "Public files")
        protocol_mgr.roots.add_root("file:///private", "Private", "Private files")
        protocol_mgr.roots.add_root("file:///workspace", "Workspace", "Work files")

        return server

    @pytest.mark.asyncio
    async def test_roots_list_with_auth_filtering(self, server_with_auth):
        """Test roots filtering based on user permissions."""
        server = server_with_auth

        # Initialize client with auth
        client_id = "auth_client"
        await server._handle_initialize(
            {
                "protocolVersion": "0.1.0",
                "capabilities": {"roots": {"listChanged": True}},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "init_123",
            client_id,
        )

        # Update client info with user context
        server.client_info[client_id]["user_id"] = "test_user"
        server.client_info[client_id]["organization_id"] = "org_123"

        # List roots
        result = await server._handle_roots_list({"client_id": client_id}, "req_123")

        # Should get all roots (no specific filtering in this test)
        assert "roots" in result["result"]
        roots = result["result"]["roots"]
        assert len(roots) == 3

    @pytest.mark.asyncio
    async def test_roots_with_custom_access_validator(self, server_with_auth):
        """Test roots with custom access validation."""
        server = server_with_auth
        protocol_mgr = get_protocol_manager()

        # Add custom validator that only allows workspace access
        async def workspace_only_validator(uri: str, operation: str):
            return "workspace" in uri

        protocol_mgr.roots.add_access_validator(workspace_only_validator)

        # Initialize client
        client_id = "restricted_client"
        await server._handle_initialize(
            {
                "protocolVersion": "0.1.0",
                "capabilities": {"roots": {"listChanged": True}},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "init_123",
            client_id,
        )

        # List roots
        result = await server._handle_roots_list({"client_id": client_id}, "req_123")

        # Should only get workspace root
        roots = result["result"]["roots"]
        assert len(roots) == 1
        assert roots[0]["uri"] == "file:///workspace"


@pytest.mark.integration
class TestCompletionCompleteIntegration(DockerIntegrationTestBase):
    """Integration tests for completion/complete handler."""

    @pytest_asyncio.fixture
    async def server_with_data(self):
        """Create server with real resources and prompts."""
        server = MCPServer("test_server")

        # Register real resources using FastMCP decorators
        @server.resource("file:///{category}/{filename}")
        async def file_resource(category: str, filename: str) -> str:
            """Access files by category and name."""
            return f"Content of {filename} in {category}"

        @server.resource("config:///{section}")
        async def config_resource(section: str) -> Dict[str, Any]:
            """Access configuration sections."""
            configs = {
                "database": {"host": "localhost", "port": 5432},
                "redis": {"host": "localhost", "port": 6379},
                "api": {"timeout": 30, "retry": 3},
            }
            return configs.get(section, {})

        @server.resource("user:///{user_id}/profile")
        async def user_profile(user_id: str) -> Dict[str, Any]:
            """Get user profile."""
            return {
                "id": user_id,
                "name": f"User {user_id}",
                "created_at": "2024-01-01",
            }

        # Register real prompts
        @server.prompt("analyze_data")
        async def analyze_prompt(data: str, format: str = "json") -> str:
            """Analyze data in specified format."""
            return f"Analyze this {format} data: {data}"

        @server.prompt("summarize_text")
        async def summarize_prompt(text: str, max_length: int = 100) -> str:
            """Summarize text to specified length."""
            return f"Summarize to {max_length} chars: {text}"

        @server.prompt("code_review")
        async def code_review_prompt(code: str, language: str = "python") -> str:
            """Review code in specified language."""
            return f"Review this {language} code: {code}"

        # Initialize completion providers
        await server._initialize_completion_providers()

        return server

    @pytest.mark.asyncio
    async def test_resource_completion_with_patterns(self, server_with_data):
        """Test resource completion with URI patterns."""
        server = server_with_data

        # Test file:// completion
        result = await server._handle_completion_complete(
            {"ref": {"type": "resource"}, "argument": {"value": "file://"}}, "req_123"
        )

        # Should return file resource template
        values = result["result"]["completion"]["values"]
        assert len(values) >= 1
        assert any("file:///" in v["uri"] for v in values)

        # Test config:// completion
        result = await server._handle_completion_complete(
            {"ref": {"type": "resource"}, "argument": {"value": "config://"}}, "req_123"
        )

        values = result["result"]["completion"]["values"]
        assert any("config:///" in v["uri"] for v in values)

    @pytest.mark.asyncio
    async def test_prompt_completion_with_metadata(self, server_with_data):
        """Test prompt completion returns full metadata."""
        server = server_with_data

        # Test completion for "analyze"
        result = await server._handle_completion_complete(
            {"ref": {"type": "prompt"}, "argument": {"value": "ana"}}, "req_123"
        )

        # Should return analyze_data prompt
        values = result["result"]["completion"]["values"]
        assert len(values) == 1
        assert values[0]["name"] == "analyze_data"
        assert "description" in values[0]
        assert "arguments" in values[0]

    @pytest.mark.asyncio
    async def test_completion_performance(self, server_with_data):
        """Test completion performance with many items."""
        server = server_with_data

        # Add many resources
        for i in range(200):
            server._resource_registry[f"perf://resource_{i}"] = {
                "name": f"Resource {i}",
                "description": f"Performance test resource {i}",
            }

        # Time the completion
        start_time = time.time()

        result = await server._handle_completion_complete(
            {"ref": {"type": "resource"}, "argument": {"value": "perf://"}}, "req_123"
        )

        elapsed = time.time() - start_time

        # Should complete quickly even with many items
        assert elapsed < 0.1  # 100ms max

        # Should limit results and indicate more available
        completion = result["result"]["completion"]
        assert len(completion["values"]) == 100
        assert completion["hasMore"] is True
        assert completion["total"] == 200


@pytest.mark.integration
class TestSamplingCreateMessageIntegration(DockerIntegrationTestBase):
    """Integration tests for sampling/createMessage handler."""

    @pytest_asyncio.fixture
    async def server_with_websocket(self):
        """Create server with WebSocket transport."""
        # Create server with WebSocket support
        server = MCPServer("test_server")

        # Mock WebSocket transport that tracks messages
        class MockWebSocketTransport:
            def __init__(self):
                self.sent_messages = []
                self.clients = {}

            async def send_message(self, message: Dict[str, Any], client_id: str):
                self.sent_messages.append(
                    {
                        "client_id": client_id,
                        "message": message,
                        "timestamp": time.time(),
                    }
                )

            def has_client(self, client_id: str) -> bool:
                return client_id in self.clients

        server._transport = MockWebSocketTransport()

        return server

    @pytest.mark.asyncio
    async def test_sampling_multi_client_routing(self, server_with_websocket):
        """Test sampling routes to correct client."""
        server = server_with_websocket

        # Initialize multiple clients with different capabilities
        clients = [
            ("client_no_sampling", {"roots": {"list": True}}),
            ("client_with_sampling_1", {"experimental": {"sampling": True}}),
            ("client_with_sampling_2", {"experimental": {"sampling": True}}),
        ]

        for client_id, capabilities in clients:
            await server._handle_initialize(
                {
                    "protocolVersion": "0.1.0",
                    "capabilities": capabilities,
                    "clientInfo": {"name": client_id, "version": "1.0"},
                },
                f"init_{client_id}",
                client_id,
            )
            server._transport.clients[client_id] = True

        # Request sampling
        result = await server._handle_sampling_create_message(
            {
                "messages": [{"role": "user", "content": "Test message"}],
                "temperature": 0.7,
                "client_id": "client_no_sampling",  # Requesting client
            },
            "req_123",
        )

        # Should succeed and route to first capable client
        assert result["result"]["status"] == "sampling_requested"
        assert result["result"]["target_client"] == "client_with_sampling_1"

        # Verify message was sent
        assert len(server._transport.sent_messages) == 1
        sent = server._transport.sent_messages[0]
        assert sent["client_id"] == "client_with_sampling_1"
        assert sent["message"]["method"] == "sampling/createMessage"

    @pytest.mark.asyncio
    async def test_sampling_request_timeout_tracking(self, server_with_websocket):
        """Test sampling requests are tracked with timeout info."""
        server = server_with_websocket

        # Initialize sampling client
        client_id = "sampling_client"
        await server._handle_initialize(
            {
                "protocolVersion": "0.1.0",
                "capabilities": {"experimental": {"sampling": True}},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "init_123",
            client_id,
        )
        server._transport.clients[client_id] = True

        # Send multiple sampling requests
        request_ids = []
        for i in range(3):
            result = await server._handle_sampling_create_message(
                {
                    "messages": [{"role": "user", "content": f"Message {i}"}],
                    "client_id": "requester",
                },
                f"req_{i}",
            )
            request_ids.append(result["result"]["sampling_id"])

        # All should be tracked
        assert len(server._pending_sampling_requests) == 3

        # Verify each has timestamp
        for req_id in request_ids:
            pending = server._pending_sampling_requests[req_id]
            assert "timestamp" in pending
            assert time.time() - pending["timestamp"] < 1.0

    @pytest.mark.asyncio
    async def test_sampling_with_model_preferences(self, server_with_websocket):
        """Test sampling with complex model preferences."""
        server = server_with_websocket

        # Initialize client
        client_id = "model_test_client"
        await server._handle_initialize(
            {
                "protocolVersion": "0.1.0",
                "capabilities": {"experimental": {"sampling": True}},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "init_123",
            client_id,
        )
        server._transport.clients[client_id] = True

        # Complex model preferences
        model_prefs = {
            "model": "gpt-4",
            "provider": "openai",
            "temperature": 0.7,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.3,
            "stop_sequences": ["END", "STOP"],
            "max_retries": 3,
        }

        # Request with preferences
        result = await server._handle_sampling_create_message(
            {
                "messages": [{"role": "user", "content": "Complex request"}],
                "modelPreferences": model_prefs,
                "systemPrompt": "You are an expert assistant",
                "metadata": {"session_id": "abc123", "user_tier": "premium"},
                "client_id": "requester",
            },
            "req_123",
        )

        # Verify all parameters were forwarded correctly
        sent_msg = server._transport.sent_messages[0]["message"]
        params = sent_msg["params"]
        assert params["model_preferences"] == model_prefs
        assert params["system_prompt"] == "You are an expert assistant"
        assert params["metadata"]["user_tier"] == "premium"


@pytest.mark.integration
class TestCompleteIntegrationFlow(DockerIntegrationTestBase):
    """Test complete flow with all handlers integrated."""

    @pytest_asyncio.fixture
    async def full_server(self, postgres_conn):
        """Create fully configured server."""
        # Create all components
        event_store = EventStore(postgres_conn)

        auth_manager = AuthManager(secret_key="test_secret", db_pool=postgres_conn)

        # Create server
        server = MCPServer(
            "test_server", event_store=event_store, auth_provider=auth_manager
        )

        # Add roots
        protocol_mgr = get_protocol_manager()
        protocol_mgr.roots.add_root("file:///workspace", "Workspace", "Main workspace")

        # Add resources and prompts
        @server.resource("config:///{env}/{key}")
        async def config_resource(env: str, key: str) -> str:
            return f"{key} value for {env}"

        @server.prompt("debug_analyze")
        async def debug_prompt(code: str) -> str:
            return f"Debug analysis for: {code}"

        return server

    @pytest.mark.asyncio
    async def test_full_capability_flow(self, full_server):
        """Test using all new handlers in sequence."""
        server = full_server

        # Initialize client with all capabilities
        client_id = "full_test_client"
        init_result = await server._handle_initialize(
            {
                "protocolVersion": "0.1.0",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "experimental": {
                        "sampling": True,
                        "progressNotifications": True,
                        "completion": True,
                    },
                },
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "init_123",
            client_id,
        )

        # Verify all capabilities are advertised
        caps = init_result["result"]["capabilities"]
        assert caps["logging"]["setLevel"] is True
        assert caps["roots"]["list"] is True
        assert caps["experimental"]["completion"] is True
        assert caps["experimental"]["sampling"] is True

        # 1. Change log level
        log_result = await server._handle_logging_set_level(
            {"level": "DEBUG", "client_id": client_id}, "log_req"
        )
        assert log_result["result"]["level"] == "DEBUG"

        # 2. List roots
        roots_result = await server._handle_roots_list(
            {"client_id": client_id}, "roots_req"
        )
        assert len(roots_result["result"]["roots"]) > 0

        # 3. Get completions
        completion_result = await server._handle_completion_complete(
            {"ref": {"type": "prompt"}, "argument": {"value": "debug"}}, "comp_req"
        )
        assert len(completion_result["result"]["completion"]["values"]) > 0

        # 4. Check events were logged
        if server.event_store:
            events = await server.event_store.query_events(limit=10)
            assert any(e["type"] == "log_level_changed" for e in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
