"""Unit tests for M3-001: Nexus shared runtime.

Tests that Nexus, MCPServer, and MCPWebSocketServer share a single
AsyncLocalRuntime instead of creating per-request runtimes. This
eliminates the DoS vector from unbounded runtime creation.

Tier 1 (Unit) - Fast, isolated, uses mocks for external services only.
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


def _stub_workflow():
    """Build a real single-node Workflow for MCP tool-registration tests.

    A ``MagicMock`` workflow would satisfy every attribute access
    ``_register_workflow_as_mcp_tool`` performs, which is exactly how the
    previous version of these tests passed against a registration path that
    recorded nothing.  The runtime is patched out in the tests that execute
    the tool, so this workflow is never actually run.
    """
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "test_node", {"code": "result = {}"})
    return builder.build()


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
    """Test that _register_workflow_as_mcp_tool uses self.runtime, not a new one.

    These tests run against the REAL ``kailash_mcp.MCPServer`` that
    ``Nexus.__init__`` builds — not an injected mock.  A bare ``MagicMock``
    auto-satisfies ``hasattr(server, "tool") and callable(server.tool)``, so
    the decorator branch in ``_register_workflow_as_mcp_tool`` "succeeds"
    against it while recording nothing.  Every assertion below would then be
    vacuous.  The real server is what production uses and is cheap to build
    (no FastMCP, no network) — see ``Nexus._initialize_mcp_server``.
    """

    def test_workflow_tool_registers_in_tool_registry_not_tools_dict(self):
        """Registration MUST land in ``_tool_registry`` — the dict tools/list reads.

        ``MCPServer._handle_list_tools`` (kailash_mcp/server.py:2837) iterates
        ``_tool_registry``.  The FastMCP fallback shim's ``_tools`` dict
        (kailash_mcp/server.py:1338) is invisible to it, so a workflow
        registered by a direct ``_tools`` write is silently undiscoverable
        over the WebSocket JSON-RPC channel.  That direct write is what
        ``_register_workflow_as_mcp_tool`` did before the guard landed
        (commit 9504d5f9c); this test is the tripwire for reintroducing it.
        """
        from nexus import Nexus

        app = Nexus()
        try:
            # Production wiring: the real Core SDK MCPServer, as built by
            # Nexus._initialize_mcp_server.
            assert (
                app._mcp_server is not None
            ), "Nexus must build a real MCPServer; the closure test is vacuous without one"

            workflow = _stub_workflow()
            app._register_workflow_as_mcp_tool("test_workflow", workflow)

            # The tool MUST be in the registry tools/list reads from.
            assert "test_workflow" in app._mcp_server._tool_registry, (
                "workflow tool missing from _tool_registry — tools/list will not "
                "surface it over WebSocket"
            )

            # And it MUST be reachable through the JSON-RPC surface an MCP
            # client actually calls, not merely present in a dict.
            listed = asyncio.run(app._mcp_server._handle_list_tools({}, request_id=1))
            names = [tool["name"] for tool in listed["result"]["tools"]]
            assert (
                "test_workflow" in names
            ), f"tools/list did not advertise the workflow tool; got {names}"
        finally:
            app.close()

    @pytest.mark.asyncio
    async def test_workflow_tool_does_not_create_new_runtime(self):
        """The registered MCP tool closure must NOT create AsyncLocalRuntime()."""
        from nexus import Nexus

        app = Nexus()
        try:
            workflow = _stub_workflow()
            app._register_workflow_as_mcp_tool("test_workflow", workflow)

            # Reach the closure through the same registry tools/call dispatch
            # uses, so a regression that stops populating _tool_registry fails
            # here too rather than silently testing a detached function.
            tool_func = app._mcp_server._tool_registry["test_workflow"][
                "original_function"
            ]

            # Patch AsyncLocalRuntime to detect if it gets called
            with patch("nexus.core.AsyncLocalRuntime") as mock_runtime_cls:
                app.runtime.execute_workflow_async = AsyncMock(
                    return_value=({"test_node": {"result": "ok"}}, "run-123")
                )

                result = await tool_func(input_data="test")

                # AsyncLocalRuntime() should NOT have been called (no new runtime)
                mock_runtime_cls.assert_not_called()

                # The shared runtime is the one that actually ran the workflow.
                app.runtime.execute_workflow_async.assert_awaited_once()
                called_workflow = app.runtime.execute_workflow_async.await_args.args[0]
                assert called_workflow is workflow

                # tools/call wraps the return value in str(); it must be JSON.
                # A single node whose ``result`` is a scalar is surfaced as
                # ``{"result": <scalar>, "run_id": ...}`` — see the payload
                # branch in ``Nexus._register_workflow_as_mcp_tool``.
                assert json.loads(result) == {"result": "ok", "run_id": "run-123"}
        finally:
            app.close()

    def test_registration_raises_when_no_registry_surface_exists(self):
        """No ``tool()`` and no ``_tools`` MUST raise, not warn-and-continue.

        The two tests above pin the HAPPY path: the decorator lands the tool in
        ``_tool_registry``.  They cannot see the FAILURE path, where neither
        registration surface is reachable — the pre-fix code logged a warning
        and returned, so ``register()`` went on to log "Workflow registered
        successfully!" for a tool ``tools/list`` would never advertise.  That
        is the same silent-undiscoverability defect reached through the error
        branch (zero-tolerance Rule 3).
        """
        from nexus import Nexus

        class NoRegistrySurfaceServer:
            """MCP server exposing neither registration surface.

            Written as an explicit class rather than a ``MagicMock`` because a
            MagicMock auto-creates BOTH ``tool`` and ``_tools``, so the branch
            under test would never be reached and the assertion would be
            vacuous — the exact false green this module was ported to remove.
            """

        app = Nexus()
        real_server = app._mcp_server
        try:
            app._mcp_server = NoRegistrySurfaceServer()
            with pytest.raises(RuntimeError) as exc_info:
                app._register_workflow_as_mcp_tool("test_workflow", _stub_workflow())

            message = str(exc_info.value)
            assert "NoRegistrySurfaceServer" in message
            assert "tools/list" in message
        finally:
            # Put the real server back BEFORE close(): close() releases the
            # runtime refs held by whatever ``_mcp_server`` points at, so
            # leaving the stub in place strands the real server's acquired
            # reference (tests/regression/test_issue_1285_close_cascades_runtime.py
            # is the global detector for exactly that leak).
            app._mcp_server = real_server
            app.close()

    def test_registration_raises_when_tool_decorator_fails_with_no_fallback(self):
        """A failing ``tool()`` with no ``_tools`` fallback MUST surface the cause.

        The decorator's exception is caught so the ``_tools`` fallback can be
        tried; when that fallback does not exist either, the original failure
        MUST reach the caller rather than being left in a log line.
        """
        from nexus import Nexus

        class FailingToolServer:
            def tool(self, *args, **kwargs):
                raise ValueError("registry is sealed")

        app = Nexus()
        real_server = app._mcp_server
        try:
            app._mcp_server = FailingToolServer()
            with pytest.raises(RuntimeError, match="registry is sealed"):
                app._register_workflow_as_mcp_tool("test_workflow", _stub_workflow())
        finally:
            # See the sibling test above: restore before close() or the real
            # server's acquired runtime reference is stranded.
            app._mcp_server = real_server
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
