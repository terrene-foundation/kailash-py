"""
Unit tests for core member variable runtime injection (M5-001).

Tests that 9 core classes:
1. Accept an optional runtime parameter in __init__
2. Properly acquire runtime references (incrementing ref_count)
3. Set _owns_runtime = False when runtime is injected
4. Set _owns_runtime = True when creating their own runtime
5. Have a close() or stop() method that releases the runtime
6. Remain backward-compatible when no runtime is provided

These are Tier 1 unit tests -- fast, isolated, no Docker.
"""

import warnings

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


# ---------------------------------------------------------------------------
# 1. CLIChannel
# ---------------------------------------------------------------------------
class TestCLIChannelRuntimeInjection:
    """Test CLIChannel accepts and manages an injected runtime."""

    def _make_channel(self, runtime=None):
        from kailash.channels.cli_channel import CLIChannel
        from kailash.channels.base import ChannelConfig, ChannelType

        config = ChannelConfig(
            name="test-cli",
            channel_type=ChannelType.CLI,
        )
        return CLIChannel(config=config, runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = AsyncLocalRuntime()
        try:
            channel = self._make_channel(runtime=runtime)
            assert channel.runtime is runtime
            channel.runtime.release()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = AsyncLocalRuntime()
        initial = runtime.ref_count
        channel = self._make_channel(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert channel._owns_runtime is False
        finally:
            channel.runtime.release()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        channel = self._make_channel()
        try:
            assert channel.runtime is not None
            assert isinstance(channel.runtime, AsyncLocalRuntime)
            assert channel._owns_runtime is True
        finally:
            channel.runtime.close()

    @pytest.mark.asyncio
    async def test_stop_releases_runtime(self):
        runtime = AsyncLocalRuntime()
        initial = runtime.ref_count
        channel = self._make_channel(runtime=runtime)
        assert runtime.ref_count == initial + 1

        await channel.stop()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 2. MCPChannel
# ---------------------------------------------------------------------------
class TestMCPChannelRuntimeInjection:
    """Test MCPChannel accepts and manages an injected runtime."""

    def _make_channel(self, runtime=None):
        from kailash.channels.mcp_channel import MCPChannel
        from kailash.channels.base import ChannelConfig, ChannelType

        config = ChannelConfig(
            name="test-mcp",
            channel_type=ChannelType.MCP,
        )
        return MCPChannel(config=config, runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = LocalRuntime()
        try:
            channel = self._make_channel(runtime=runtime)
            assert channel.runtime is runtime
            channel.runtime.release()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = LocalRuntime()
        initial = runtime.ref_count
        channel = self._make_channel(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert channel._owns_runtime is False
        finally:
            channel.runtime.release()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        channel = self._make_channel()
        try:
            assert channel.runtime is not None
            assert isinstance(channel.runtime, LocalRuntime)
            assert channel._owns_runtime is True
        finally:
            channel.runtime.close()

    @pytest.mark.asyncio
    async def test_stop_releases_runtime(self):
        runtime = LocalRuntime()
        initial = runtime.ref_count
        channel = self._make_channel(runtime=runtime)
        assert runtime.ref_count == initial + 1

        await channel.stop()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 3. MiddlewareMCPServer (in enhanced_server.py)
# ---------------------------------------------------------------------------
class TestMiddlewareMCPServerRuntimeInjection:
    """Test MiddlewareMCPServer accepts and manages an injected runtime."""

    def _make_server(self, runtime=None):
        from kailash.middleware.mcp.enhanced_server import MiddlewareMCPServer

        return MiddlewareMCPServer(runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = LocalRuntime()
        try:
            server = self._make_server(runtime=runtime)
            assert server.runtime is runtime
            server.runtime.release()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = LocalRuntime()
        initial = runtime.ref_count
        server = self._make_server(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert server._owns_runtime is False
        finally:
            server.runtime.release()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        server = self._make_server()
        try:
            assert server.runtime is not None
            assert isinstance(server.runtime, LocalRuntime)
            assert server._owns_runtime is True
        finally:
            server.runtime.close()

    @pytest.mark.asyncio
    async def test_stop_releases_runtime(self):
        runtime = LocalRuntime()
        initial = runtime.ref_count
        server = self._make_server(runtime=runtime)
        assert runtime.ref_count == initial + 1

        await server.stop()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 4. DurableRequest
# ---------------------------------------------------------------------------
class TestDurableRequestRuntimeInjection:
    """Test DurableRequest accepts and manages an injected runtime."""

    def _make_request(self, runtime=None):
        from kailash.middleware.gateway.durable_request import DurableRequest

        return DurableRequest(runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = LocalRuntime()
        try:
            req = self._make_request(runtime=runtime)
            assert req._injected_runtime is runtime
            req.close()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = LocalRuntime()
        initial = runtime.ref_count
        req = self._make_request(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert req._owns_runtime is False
        finally:
            req.close()
            runtime.close()

    def test_constructor_creates_no_runtime_when_none(self):
        """DurableRequest creates runtime lazily in _execute_workflow, not in __init__."""
        req = self._make_request()
        # runtime is None until _execute_workflow is called
        assert req.runtime is None
        assert req._owns_runtime is True
        req.close()

    def test_close_releases_injected_runtime(self):
        runtime = LocalRuntime()
        initial = runtime.ref_count
        req = self._make_request(runtime=runtime)
        assert runtime.ref_count == initial + 1

        req.close()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 5. WorkflowBasedMiddleware
# ---------------------------------------------------------------------------
class TestWorkflowBasedMiddlewareRuntimeInjection:
    """Test WorkflowBasedMiddleware accepts and manages an injected runtime."""

    def _make_middleware(self, runtime=None):
        from kailash.middleware.core.workflows import WorkflowBasedMiddleware

        return WorkflowBasedMiddleware(runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = AsyncLocalRuntime(debug=True, max_concurrency=10)
        try:
            mw = self._make_middleware(runtime=runtime)
            assert mw.runtime is runtime
            mw.close()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = AsyncLocalRuntime(debug=True, max_concurrency=10)
        initial = runtime.ref_count
        mw = self._make_middleware(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert mw._owns_runtime is False
        finally:
            mw.close()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        mw = self._make_middleware()
        try:
            assert mw.runtime is not None
            assert isinstance(mw.runtime, AsyncLocalRuntime)
            assert mw._owns_runtime is True
        finally:
            mw.close()

    def test_close_releases_runtime(self):
        runtime = AsyncLocalRuntime(debug=True, max_concurrency=10)
        initial = runtime.ref_count
        mw = self._make_middleware(runtime=runtime)
        assert runtime.ref_count == initial + 1

        mw.close()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 6. AgentUIMiddleware
# ---------------------------------------------------------------------------
class TestAgentUIMiddlewareRuntimeInjection:
    """Test AgentUIMiddleware accepts and manages an injected runtime."""

    def _make_middleware(self, runtime=None):
        from kailash.middleware.core.agent_ui import AgentUIMiddleware

        return AgentUIMiddleware(runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = LocalRuntime(enable_async=True)
        try:
            mw = self._make_middleware(runtime=runtime)
            assert mw.runtime is runtime
            mw.close()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = LocalRuntime(enable_async=True)
        initial = runtime.ref_count
        mw = self._make_middleware(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert mw._owns_runtime is False
        finally:
            mw.close()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        mw = self._make_middleware()
        try:
            assert mw.runtime is not None
            assert isinstance(mw.runtime, LocalRuntime)
            assert mw._owns_runtime is True
        finally:
            mw.close()

    def test_close_releases_runtime(self):
        runtime = LocalRuntime(enable_async=True)
        initial = runtime.ref_count
        mw = self._make_middleware(runtime=runtime)
        assert runtime.ref_count == initial + 1

        mw.close()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 7. WorkflowAPI
# ---------------------------------------------------------------------------
class TestWorkflowAPIRuntimeInjection:
    """Test WorkflowAPI accepts and manages an injected runtime."""

    def _make_api(self, runtime=None):
        from kailash.api.workflow_api import WorkflowAPI
        from kailash.workflow.builder import WorkflowBuilder

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "test_node", {"code": "result = 'ok'"})
        return WorkflowAPI(builder, runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = AsyncLocalRuntime()
        try:
            api = self._make_api(runtime=runtime)
            assert api.runtime is runtime
            api.close()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = AsyncLocalRuntime()
        initial = runtime.ref_count
        api = self._make_api(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert api._owns_runtime is False
        finally:
            api.close()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        api = self._make_api()
        try:
            assert api.runtime is not None
            assert isinstance(api.runtime, AsyncLocalRuntime)
            assert api._owns_runtime is True
        finally:
            api.close()

    def test_close_releases_runtime(self):
        runtime = AsyncLocalRuntime()
        initial = runtime.ref_count
        api = self._make_api(runtime=runtime)
        assert runtime.ref_count == initial + 1

        api.close()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 8. WorkflowTestHelper
# ---------------------------------------------------------------------------
class TestWorkflowTestHelperRuntimeInjection:
    """Test WorkflowTestHelper accepts and manages an injected runtime."""

    def _make_helper(self, runtime=None):
        from kailash.runtime.testing import WorkflowTestHelper

        return WorkflowTestHelper(runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = LocalRuntime(debug=True)
        try:
            helper = self._make_helper(runtime=runtime)
            assert helper.runtime is runtime
            helper.close()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = LocalRuntime(debug=True)
        initial = runtime.ref_count
        helper = self._make_helper(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert helper._owns_runtime is False
        finally:
            helper.close()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        helper = self._make_helper()
        try:
            assert helper.runtime is not None
            assert isinstance(helper.runtime, LocalRuntime)
            assert helper._owns_runtime is True
        finally:
            helper.close()

    def test_close_releases_runtime(self):
        runtime = LocalRuntime(debug=True)
        initial = runtime.ref_count
        helper = self._make_helper(runtime=runtime)
        assert runtime.ref_count == initial + 1

        helper.close()
        assert runtime.ref_count == initial
        runtime.close()


# ---------------------------------------------------------------------------
# 9. EnterpriseWorkflowServer
# ---------------------------------------------------------------------------
class TestEnterpriseWorkflowServerRuntimeInjection:
    """Test EnterpriseWorkflowServer accepts and manages an injected runtime."""

    def _make_server(self, runtime=None):
        from kailash.servers.enterprise_workflow_server import EnterpriseWorkflowServer

        return EnterpriseWorkflowServer(runtime=runtime)

    def test_constructor_accepts_runtime_parameter(self):
        runtime = AsyncLocalRuntime()
        try:
            server = self._make_server(runtime=runtime)
            assert server._async_runtime is runtime
            server.close()
        finally:
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        runtime = AsyncLocalRuntime()
        initial = runtime.ref_count
        server = self._make_server(runtime=runtime)
        try:
            assert runtime.ref_count == initial + 1
            assert server._owns_runtime is False
        finally:
            server.close()
            runtime.close()

    def test_constructor_creates_runtime_when_none(self):
        server = self._make_server()
        try:
            if server._async_runtime is not None:
                assert isinstance(server._async_runtime, AsyncLocalRuntime)
            assert server._owns_runtime is True
        finally:
            server.close()

    def test_close_releases_runtime(self):
        runtime = AsyncLocalRuntime()
        initial = runtime.ref_count
        server = self._make_server(runtime=runtime)
        assert runtime.ref_count == initial + 1

        server.close()
        assert runtime.ref_count == initial
        runtime.close()
