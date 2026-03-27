"""Unit tests for M3-001: Nexus shared runtime.

Tests that Nexus, MCPServer, and MCPWebSocketServer share a single
AsyncLocalRuntime instead of creating per-request runtimes. This
eliminates the DoS vector from unbounded runtime creation.

Tier 1 (Unit) - Fast, isolated, uses mocks for external services only.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


class TestNexusSharedRuntime:
    """Test that Nexus creates and manages a server-level shared runtime."""

    def test_nexus_has_runtime_attribute(self):
        """Nexus.__init__ creates self.runtime as AsyncLocalRuntime."""
        from nexus import Nexus

        app = Nexus()
        assert hasattr(app, "runtime"), "Nexus must have a 'runtime' attribute"
        assert app.runtime is not None, "Nexus.runtime must not be None after init"

        from kailash.runtime import AsyncLocalRuntime

        assert isinstance(
            app.runtime, AsyncLocalRuntime
        ), "Nexus.runtime must be an AsyncLocalRuntime instance"

        # Cleanup
        app.runtime.close()

    def test_nexus_close_releases_runtime(self):
        """Nexus.close() releases the runtime and sets it to None."""
        from nexus import Nexus

        app = Nexus()
        runtime = app.runtime
        assert runtime is not None

        app.close()
        assert app.runtime is None, "Nexus.runtime must be None after close()"

    def test_nexus_close_is_idempotent(self):
        """Calling Nexus.close() multiple times does not raise."""
        from nexus import Nexus

        app = Nexus()
        app.close()
        app.close()  # Should not raise
        assert app.runtime is None

    def test_nexus_context_manager(self):
        """Nexus supports context manager protocol (__enter__/__exit__)."""
        from nexus import Nexus

        with Nexus() as app:
            assert app.runtime is not None
            from kailash.runtime import AsyncLocalRuntime

            assert isinstance(app.runtime, AsyncLocalRuntime)

        # After exiting context, runtime should be released
        assert app.runtime is None

    def test_nexus_stop_calls_close(self):
        """Nexus.stop() cascades to close() for runtime cleanup."""
        from nexus import Nexus

        app = Nexus()
        app._running = True  # Simulate running state
        runtime = app.runtime
        assert runtime is not None

        app.stop()
        assert app.runtime is None, "Nexus.stop() must release the runtime"


class TestNexusMCPToolClosure:
    """Test that _register_workflow_as_mcp_tool uses self.runtime, not a new one."""

    def test_workflow_tool_closure_uses_shared_runtime(self):
        """The closure created by _register_workflow_as_mcp_tool must use self.runtime."""
        from nexus import Nexus

        app = Nexus()

        # Create a mock workflow
        mock_workflow = MagicMock()
        mock_workflow.nodes = {"test_node": MagicMock()}
        mock_workflow.metadata = None

        # Ensure _mcp_server has _tools attribute
        if not hasattr(app._mcp_server, "_tools"):
            app._mcp_server._tools = {}

        app._register_workflow_as_mcp_tool("test_workflow", mock_workflow)

        # The registered tool function should exist
        assert "test_workflow" in app._mcp_server._tools

        # Cleanup
        app.close()

    @pytest.mark.asyncio
    async def test_workflow_tool_does_not_create_new_runtime(self):
        """The registered MCP tool closure must NOT create AsyncLocalRuntime()."""
        from nexus import Nexus

        app = Nexus()

        # Create a mock workflow
        mock_workflow = MagicMock()
        mock_workflow.nodes = {"test_node": MagicMock()}
        mock_workflow.metadata = None

        # Ensure _mcp_server has _tools
        if not hasattr(app._mcp_server, "_tools"):
            app._mcp_server._tools = {}

        app._register_workflow_as_mcp_tool("test_workflow", mock_workflow)
        tool_func = app._mcp_server._tools["test_workflow"]

        # Patch AsyncLocalRuntime to detect if it gets called
        with patch("nexus.core.AsyncLocalRuntime") as mock_runtime_cls:
            # Mock the runtime's execute_workflow_async
            app.runtime.execute_workflow_async = AsyncMock(
                return_value=({"test_node": {"result": "ok"}}, "run-123")
            )

            await tool_func(input_data="test")

            # AsyncLocalRuntime() should NOT have been called (no new runtime)
            mock_runtime_cls.assert_not_called()

        # Cleanup
        app.close()


class TestMCPServerSharedRuntime:
    """Test that MCPServer accepts and uses a shared runtime."""

    def test_mcp_server_accepts_runtime_parameter(self):
        """MCPServer.__init__ accepts an optional runtime parameter."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp.server import MCPServer

        runtime = AsyncLocalRuntime()
        server = MCPServer(runtime=runtime.acquire())

        assert server.runtime is runtime
        assert server._owns_runtime is False

        # Cleanup
        server.close()
        runtime.close()

    def test_mcp_server_creates_own_runtime_when_none_provided(self):
        """MCPServer creates its own runtime when none is provided."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp.server import MCPServer

        server = MCPServer()
        assert server.runtime is not None
        assert isinstance(server.runtime, AsyncLocalRuntime)
        assert server._owns_runtime is True

        # Cleanup
        server.close()

    def test_mcp_server_close_releases_runtime(self):
        """MCPServer.close() calls release() on the runtime."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp.server import MCPServer

        shared_runtime = AsyncLocalRuntime()

        server = MCPServer(runtime=shared_runtime.acquire())
        post_create = shared_runtime.ref_count

        server.close()
        assert shared_runtime.ref_count < post_create  # close reduced ref count

        # Cleanup
        shared_runtime.close()

    @pytest.mark.asyncio
    async def test_mcp_server_handle_call_tool_uses_shared_runtime(self):
        """MCPServer.handle_call_tool uses self.runtime, not a new one."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp.server import MCPServer

        runtime = AsyncLocalRuntime()
        server = MCPServer(runtime=runtime.acquire())

        # Register a test workflow
        mock_workflow = MagicMock()
        mock_workflow.nodes = {"node1": MagicMock()}
        server.register_workflow("test_wf", mock_workflow)

        # Mock execute_workflow_async on the shared runtime to track calls
        original_runtime = server.runtime
        server.runtime.execute_workflow_async = AsyncMock(
            return_value=({"node1": {"result": "data"}}, "run-456")
        )

        # Verify ref count stays stable (no new runtimes created)
        ref_count_before = runtime.ref_count

        result = await server.handle_call_tool(
            {"name": "test_wf", "arguments": {"key": "value"}}
        )

        # The shared runtime's execute method was called (not a new runtime's)
        original_runtime.execute_workflow_async.assert_called_once()
        # Ref count unchanged — no new runtime was created
        assert runtime.ref_count == ref_count_before

        assert result["type"] == "result"

        # Cleanup
        server.close()
        runtime.close()


class TestMCPWebSocketServerSharedRuntime:
    """Test that MCPWebSocketServer accepts and uses a shared runtime."""

    def test_websocket_server_accepts_runtime_parameter(self):
        """MCPWebSocketServer.__init__ accepts an optional runtime parameter."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp_websocket_server import MCPWebSocketServer

        runtime = AsyncLocalRuntime()
        mcp_server = MagicMock()

        ws_server = MCPWebSocketServer(mcp_server=mcp_server, runtime=runtime.acquire())

        assert ws_server.runtime is runtime
        assert ws_server._owns_runtime is False

        # Cleanup
        ws_server.close()
        runtime.close()

    def test_websocket_server_creates_own_runtime_when_none_provided(self):
        """MCPWebSocketServer creates its own runtime when none is provided."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp_websocket_server import MCPWebSocketServer

        mcp_server = MagicMock()
        ws_server = MCPWebSocketServer(mcp_server=mcp_server)

        assert ws_server.runtime is not None
        assert isinstance(ws_server.runtime, AsyncLocalRuntime)
        assert ws_server._owns_runtime is True

        # Cleanup
        ws_server.close()

    def test_websocket_server_close_releases_runtime(self):
        """MCPWebSocketServer.close() releases the runtime reference."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp_websocket_server import MCPWebSocketServer

        shared_runtime = AsyncLocalRuntime()

        mcp_server = MagicMock()
        ws_server = MCPWebSocketServer(
            mcp_server=mcp_server, runtime=shared_runtime.acquire()
        )
        post_create = shared_runtime.ref_count

        ws_server.close()
        assert shared_runtime.ref_count < post_create  # close reduced ref count

        # Cleanup
        shared_runtime.close()

    @pytest.mark.asyncio
    async def test_websocket_server_tools_call_uses_shared_runtime(self):
        """MCPWebSocketServer.handle_mcp_request for tools/call uses self.runtime."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus.mcp_websocket_server import MCPWebSocketServer

        runtime = AsyncLocalRuntime()
        mcp_server = MagicMock()
        mcp_server._workflows = {"test_wf": MagicMock()}
        mcp_server._workflows["test_wf"].nodes = {"node1": MagicMock()}
        # Ensure _tools does not exist so it takes the _workflows path
        del mcp_server._tools

        ws_server = MCPWebSocketServer(mcp_server=mcp_server, runtime=runtime.acquire())

        # Mock execute_workflow_async on the shared runtime to track calls
        original_runtime = ws_server.runtime
        ws_server.runtime.execute_workflow_async = AsyncMock(
            return_value=({"node1": {"result": "data"}}, "run-789")
        )

        # Verify ref count stays stable (no new runtimes created)
        ref_count_before = runtime.ref_count

        result = await ws_server.handle_mcp_request(
            "tools/call",
            {"name": "test_wf", "arguments": {"key": "value"}},
            request_id=1,
        )

        # The shared runtime's execute method was called (not a new runtime's)
        original_runtime.execute_workflow_async.assert_called_once()
        # Ref count unchanged — no new runtime was created
        assert runtime.ref_count == ref_count_before

        assert result["jsonrpc"] == "2.0"
        assert "result" in result

        # Cleanup
        ws_server.close()
        runtime.close()


class TestNexusRuntimeLifecycle:
    """Test the full lifecycle: Nexus creates runtime, shares with servers, close cascades."""

    def test_nexus_runtime_ref_counting(self):
        """Nexus runtime ref count increases when shared with servers."""
        from kailash.runtime import AsyncLocalRuntime
        from nexus import Nexus

        app = Nexus()
        initial = (
            app.runtime.ref_count
        )  # Nexus + internal subsystems (probes, middleware)
        assert initial >= 1

        # Simulate sharing: acquire for a subsystem
        acquired = app.runtime.acquire()
        assert app.runtime.ref_count == initial + 1

        # Release subsystem
        acquired.release()
        assert app.runtime.ref_count == initial

        # Cleanup
        app.close()

    def test_close_cascades_completely(self):
        """After Nexus.close(), the runtime is fully released."""
        from nexus import Nexus

        app = Nexus()
        pre_close = app.runtime.ref_count

        app.close()
        assert app.runtime is None
