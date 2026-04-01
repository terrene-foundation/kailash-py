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
        """The closure created by _register_workflow_as_mcp_tool must use self.runtime.

        Note: In WebSocket-only mode (default), _mcp_server is None since the
        old Nexus MCPServer was removed.  This test manually injects a mock
        server to verify the closure wiring.
        """
        from nexus import Nexus

        app = Nexus()

        # In WebSocket-only mode, _mcp_server is None.
        # Inject a mock to test the closure behaviour.
        app._mcp_server = MagicMock()
        app._mcp_server._tools = {}

        # Create a mock workflow
        mock_workflow = MagicMock()
        mock_workflow.nodes = {"test_node": MagicMock()}
        mock_workflow.metadata = None

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

        # Inject mock server (WebSocket-only mode has no server by default)
        app._mcp_server = MagicMock()
        app._mcp_server._tools = {}

        # Create a mock workflow
        mock_workflow = MagicMock()
        mock_workflow.nodes = {"test_node": MagicMock()}
        mock_workflow.metadata = None

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

    # NOTE: TestMCPServerSharedRuntime was removed along with the old
    # nexus.mcp.server.MCPServer class.  The shared runtime pattern is now
    # tested through the unified kailash-platform MCP server in
    # tests/unit/mcp/test_platform_server.py.

    # NOTE: TestMCPWebSocketServerSharedRuntime was removed along with the old
    # nexus.mcp_websocket_server.MCPWebSocketServer class.


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
