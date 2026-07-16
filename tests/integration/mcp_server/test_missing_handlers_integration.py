"""Integration tests for MCP missing handlers with real infrastructure."""

import asyncio
import logging
import time
from typing import Any, Dict

import pytest
import pytest_asyncio

from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.protocol.protocol import get_protocol_manager
from kailash_mcp.server import MCPServer
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
        test_logger = logging.getLogger("kailash_mcp.test")

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
    async def server_with_auth(self):
        """Create server with a real auth manager (provider-model API).

        The roots-filtering assertions set the user context directly on
        ``server.client_info`` below, so the auth manager only needs to be a
        valid ``AuthProvider``-backed manager — an in-memory API-key provider
        is real (no mocking) and requires no database.
        """
        # Real in-memory API-key provider (provider-model API). MCPServer
        # consumes an AuthProvider directly; the roots-filtering assertions set
        # the user context on server.client_info below, so no user store is
        # needed — the provider only has to be a valid AuthProvider.
        auth_provider = APIKeyAuth(
            keys={
                "test_user_key": {
                    "permissions": ["read", "write"],
                    "user_id": "test_user",
                    "organization_id": "org_123",
                }
            }
        )

        # Create server
        server = MCPServer("test_server", auth_provider=auth_provider)

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

        # Completion is served directly off the registered resource/prompt
        # registries by _handle_completion_complete — no separate provider-init
        # step is required (provider-model refactor).
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

        # Bind an approving HITL approver so the FORWARD-path tests in this
        # class exercise dispatch. Sampling fails CLOSED when no approver is
        # bound (MCP 2025-11-25 HITL, #1712 W4) — a server that accepts
        # sampling has an approver, the realistic production precondition.
        # Mirrors the unit-test fixture fix in
        # tests/unit/mcp_server/test_missing_handlers.py.
        server.set_sampling_approver(lambda ctx: True)

        return server

    async def _await_dispatch(self, server, timeout_iters: int = 500):
        """Yield the event loop until at least one sampling request has been
        dispatched to the mock transport, or fail loudly.

        Under the MCP 2025-11-25 server-initiated model, the handler DISPATCHES
        to the target client and AWAITS the client's reply — it does not return
        synchronously — so tests run it as a task and drive the reply back in.
        """
        for _ in range(timeout_iters):
            await asyncio.sleep(0)
            if server._transport.sent_messages:
                return
        raise AssertionError("sampling request was never dispatched")

    async def _reply(self, server, sampling_id, responding_client_id):
        """Feed a client completion back through the response router."""
        completion = {"role": "assistant", "content": {"type": "text", "text": "ok"}}
        return await server._route_server_initiated_response(
            sampling_id,
            {"jsonrpc": "2.0", "id": sampling_id, "result": completion},
            responding_client_id=responding_client_id,
        )

    @pytest.mark.asyncio
    async def test_sampling_routes_to_requesters_own_client(
        self, server_with_websocket
    ):
        """Sampling routes to the REQUESTER's OWN client; a requester that does
        not advertise sampling is rejected rather than routed to a different
        client's LLM (FINDING-4 cross-client isolation, #1712 W6)."""
        server = server_with_websocket

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

        # A requester WITHOUT the sampling capability is rejected and NOT routed
        # to a capable sibling client — no message is dispatched.
        rejected = await server._handle_sampling_create_message(
            {
                "messages": [{"role": "user", "content": "Test message"}],
                "temperature": 0.7,
                "client_id": "client_no_sampling",
            },
            "req_reject",
        )
        assert "error" in rejected
        assert "does not advertise sampling" in rejected["error"]["message"]
        assert server._transport.sent_messages == []

        # A capable requester dispatches to its OWN client and round-trips.
        task = asyncio.create_task(
            server._handle_sampling_create_message(
                {
                    "messages": [{"role": "user", "content": "Test message"}],
                    "temperature": 0.7,
                    "client_id": "client_with_sampling_1",
                },
                "req_ok",
            )
        )
        await self._await_dispatch(server)

        assert len(server._transport.sent_messages) == 1
        sent = server._transport.sent_messages[0]
        assert sent["client_id"] == "client_with_sampling_1"
        assert sent["message"]["method"] == "sampling/createMessage"
        sampling_id = sent["message"]["id"]
        assert sampling_id in server._pending_sampling_requests

        assert await self._reply(server, sampling_id, "client_with_sampling_1") is True
        result = await asyncio.wait_for(task, timeout=2)
        assert result["id"] == "req_ok"
        assert result["result"]["content"]["text"] == "ok"
        assert sampling_id not in server._pending_sampling_requests

    @pytest.mark.asyncio
    async def test_sampling_requests_are_tracked_with_timeout_info(
        self, server_with_websocket
    ):
        """Concurrent server-initiated sampling requests are each tracked in
        _pending_sampling_requests with provenance + timestamp until the target
        client replies."""
        server = server_with_websocket

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

        # Dispatch three concurrent requests; each awaits its own reply.
        tasks = [
            asyncio.create_task(
                server._handle_sampling_create_message(
                    {
                        "messages": [{"role": "user", "content": f"Message {i}"}],
                        "client_id": client_id,
                    },
                    f"req_{i}",
                )
            )
            for i in range(3)
        ]
        for _ in range(500):
            await asyncio.sleep(0)
            if len(server._pending_sampling_requests) == 3:
                break
        else:
            for t in tasks:
                t.cancel()
            raise AssertionError("not all sampling requests were tracked")

        # Each pending entry carries a recent timestamp + the target client.
        for pending in server._pending_sampling_requests.values():
            assert "timestamp" in pending
            assert time.time() - pending["timestamp"] < 5.0
            assert pending["client_id"] == client_id

        # Drain: reply to each so no task is left awaiting.
        for sampling_id in list(server._pending_sampling_requests):
            await self._reply(server, sampling_id, client_id)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
        assert len(server._pending_sampling_requests) == 0

    @pytest.mark.asyncio
    async def test_sampling_with_model_preferences(self, server_with_websocket):
        """Complex model preferences + system prompt + metadata are forwarded
        to the target client in the dispatched sampling request."""
        server = server_with_websocket

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

        # Complex model preferences (opaque client-provided forwarding payload).
        model_prefs = {
            "model": "test-model",
            "provider": "test-provider",
            "temperature": 0.7,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.3,
            "stop_sequences": ["END", "STOP"],
            "max_retries": 3,
        }

        task = asyncio.create_task(
            server._handle_sampling_create_message(
                {
                    "messages": [{"role": "user", "content": "Complex request"}],
                    "modelPreferences": model_prefs,
                    "systemPrompt": "You are an expert assistant",
                    "metadata": {"session_id": "abc123", "user_tier": "premium"},
                    "client_id": client_id,
                },
                "req_123",
            )
        )
        await self._await_dispatch(server)

        # Verify all parameters were forwarded correctly (snake_case wire shape).
        sent_msg = server._transport.sent_messages[0]["message"]
        params = sent_msg["params"]
        assert params["model_preferences"] == model_prefs
        assert params["system_prompt"] == "You are an expert assistant"
        assert params["metadata"]["user_tier"] == "premium"

        # Drain the awaiting handler.
        await self._reply(server, sent_msg["id"], client_id)
        await asyncio.wait_for(task, timeout=2)


@pytest.mark.integration
class TestCompleteIntegrationFlow(DockerIntegrationTestBase):
    """Test complete flow with all handlers integrated."""

    @pytest_asyncio.fixture
    async def full_server(self, postgres_conn):
        """Create fully configured server."""
        # Create all components
        event_store = EventStore(postgres_conn)

        # Real in-memory API-key provider (provider-model API)
        auth_provider = APIKeyAuth(keys=["test_full_server_key"])

        # Create server
        server = MCPServer(
            "test_server", event_store=event_store, auth_provider=auth_provider
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

        # 4. Check events were logged (read the in-memory event buffer by the
        # log handler's request id, matching the get_events(request_id=...) API)
        if server.event_store:
            events = await server.event_store.get_events(request_id="log_req")
            assert any(e.data.get("type") == "log_level_changed" for e in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
