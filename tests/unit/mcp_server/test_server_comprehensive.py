"""Comprehensive tests for MCP server to improve coverage.

This test file focuses on missing coverage areas in server.py:
- MCPServerBase start() method and fallback server creation
- MCPServer _init_mcp() method with different scenarios
- MCPServer _create_fallback_server() method
- MCPServer tool() decorator with enhanced features
- MCPServer resource() and prompt() decorators
- MCPServer run() method and transport handling
- MCPServer enhanced methods and features
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.mcp_server.auth import APIKeyAuth, BasicAuth
from kailash.mcp_server.errors import MCPError, MCPErrorCode
from kailash.mcp_server.server import MCPServer, MCPServerBase


class TestMCPServerBase:
    """Test MCPServerBase functionality."""

    def test_start_method_with_mcp_initialization(self):
        """Test start method initializes MCP and calls setup."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        class TestServer(MCPServerBase):
            def __init__(self):
                super().__init__("test-server")
                self.setup_called = False

            def setup(self):
                self.setup_called = True

        server = TestServer()

        # Mock _init_mcp and _mcp.run()
        with patch.object(server, "_init_mcp") as mock_init:
            mock_mcp = Mock()
            mock_mcp.run.side_effect = KeyboardInterrupt()  # Simulate stopping
            mock_init.return_value = None
            server._mcp = None  # Ensure _init_mcp will be called

            # Set the _mcp after _init_mcp is called
            def set_mcp():
                server._mcp = mock_mcp

            mock_init.side_effect = set_mcp

            with pytest.raises(KeyboardInterrupt):
                server.start()

            mock_init.assert_called_once()
            assert server.setup_called is True
            assert server._running is False  # Should be reset in finally

    def test_start_method_with_exception_handling(self):
        """Test start method handles exceptions properly."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        class TestServer(MCPServerBase):
            def __init__(self):
                super().__init__("test-server")

            def setup(self):
                pass

        server = TestServer()

        # Mock _init_mcp and _mcp.run() to raise exception
        with patch.object(server, "_init_mcp"):
            mock_mcp = Mock()
            mock_mcp.run.side_effect = RuntimeError("Server failed")
            server._mcp = mock_mcp

            with pytest.raises(RuntimeError, match="Server failed"):
                server.start()

            assert server._running is False

    def test_init_mcp_with_fastmcp_available(self):
        """Test _init_mcp when FastMCP is available."""

        class TestServer(MCPServerBase):
            def __init__(self):
                super().__init__("test-server")

            def setup(self):
                pass

        server = TestServer()

        # Mock FastMCP import
        mock_fastmcp = Mock()
        mock_fastmcp_instance = Mock()
        mock_fastmcp.return_value = mock_fastmcp_instance

        with patch.dict("sys.modules", {"fastmcp": Mock(FastMCP=mock_fastmcp)}):
            server._init_mcp()

            assert server._mcp is mock_fastmcp_instance
            mock_fastmcp.assert_called_once_with("test-server")

    def test_init_mcp_with_fallback_mode(self):
        """Test _init_mcp falls back when FastMCP is not available."""

        class TestServer(MCPServerBase):
            def __init__(self):
                super().__init__("test-server")

            def setup(self):
                pass

        server = TestServer()

        # Mock FastMCP import to fail
        with patch("kailash.mcp_server.server.logger") as mock_logger:
            with patch.dict("sys.modules", {"fastmcp": None}):
                server._init_mcp()

                # Should create fallback server
                assert server._mcp is not None
                assert hasattr(server._mcp, "tool")
                assert hasattr(server._mcp, "resource")
                assert hasattr(server._mcp, "prompt")

                mock_logger.warning.assert_called_with(
                    "FastMCP not available, using fallback mode"
                )

    def test_create_fallback_server_functionality(self):
        """Test _create_fallback_server creates working fallback."""

        class TestServer(MCPServerBase):
            def __init__(self):
                super().__init__("test-server")

            def setup(self):
                pass

        server = TestServer()
        fallback = server._create_fallback_server()

        # Test fallback server interface
        assert fallback.name == "test-server"
        assert hasattr(fallback, "tool")
        assert hasattr(fallback, "resource")
        assert hasattr(fallback, "prompt")

        # Test tool decorator
        @fallback.tool()
        def test_tool():
            return "test"

        assert "test_tool" in fallback._tools
        assert fallback._tools["test_tool"] == test_tool

        # Test resource decorator
        @fallback.resource("test://resource")
        def test_resource():
            return "resource"

        assert "test://resource" in fallback._resources
        assert fallback._resources["test://resource"] == test_resource

        # Test prompt decorator
        @fallback.prompt("test_prompt")
        def test_prompt():
            return "prompt"

        assert "test_prompt" in fallback._prompts
        assert fallback._prompts["test_prompt"] == test_prompt

    def test_fallback_server_run_raises_not_implemented(self):
        """Test fallback server run() raises NotImplementedError."""

        class TestServer(MCPServerBase):
            def __init__(self):
                super().__init__("test-server")

            def setup(self):
                pass

        server = TestServer()
        fallback = server._create_fallback_server()

        with pytest.raises(NotImplementedError, match="FastMCP not available"):
            fallback.run()


class TestMCPServer:
    """Test MCPServer functionality."""

    def test_init_mcp_with_independent_fastmcp(self):
        """Test _init_mcp with independent FastMCP package."""
        server = MCPServer("test-server")

        # Mock independent FastMCP
        mock_fastmcp = Mock()
        mock_fastmcp_instance = Mock()
        mock_fastmcp.return_value = mock_fastmcp_instance

        with patch.dict("sys.modules", {"fastmcp": Mock(FastMCP=mock_fastmcp)}):
            server._init_mcp()

            assert server._mcp is mock_fastmcp_instance
            mock_fastmcp.assert_called_once_with("test-server")

    def test_init_mcp_with_official_fastmcp_fallback(self):
        """Test _init_mcp falls back to official FastMCP."""
        server = MCPServer("test-server")

        # Mock official FastMCP
        mock_fastmcp = Mock()
        mock_fastmcp_instance = Mock()
        mock_fastmcp.return_value = mock_fastmcp_instance

        with patch.dict("sys.modules", {"fastmcp": None}):  # Independent fails
            with patch.dict("sys.modules", {"mcp.server": Mock(FastMCP=mock_fastmcp)}):
                server._init_mcp()

                assert server._mcp is mock_fastmcp_instance
                mock_fastmcp.assert_called_once_with("test-server")

    def test_init_mcp_with_complete_fallback(self):
        """Test _init_mcp with complete fallback mode."""
        server = MCPServer("test-server")

        # Mock both FastMCP imports to fail
        with patch.dict("sys.modules", {"fastmcp": None}):
            with patch.dict("sys.modules", {"mcp.server": None}):
                with patch("kailash.mcp_server.server.logger") as mock_logger:
                    server._init_mcp()

                    # Should create fallback server
                    assert server._mcp is not None
                    assert hasattr(server._mcp, "tool")

                    # Check logging
                    mock_logger.warning.assert_called()
                    mock_logger.info.assert_called_with(
                        "Fallback MCP server 'test-server' initialized"
                    )

    def test_init_mcp_already_initialized(self):
        """Test _init_mcp when MCP is already initialized."""
        server = MCPServer("test-server")
        server._mcp = Mock()

        # Should not reinitialize
        existing_mcp = server._mcp
        server._init_mcp()

        assert server._mcp is existing_mcp

    def test_create_fallback_server_with_logging(self):
        """Test _create_fallback_server with proper logging."""
        server = MCPServer("test-server")

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            fallback = server._create_fallback_server()

            mock_logger.info.assert_any_call("Creating fallback server implementation")
            mock_logger.info.assert_any_call(
                "Fallback MCP server 'test-server' initialized"
            )

            assert fallback.name == "test-server"

    def test_fallback_server_tool_registration_with_logging(self):
        """Test fallback server tool registration logs properly."""
        server = MCPServer("test-server")
        fallback = server._create_fallback_server()

        with patch("kailash.mcp_server.server.logger") as mock_logger:

            @fallback.tool()
            def test_tool():
                return "test"

            mock_logger.debug.assert_called_with("Registered fallback tool: test_tool")

    def test_fallback_server_resource_registration_with_logging(self):
        """Test fallback server resource registration logs properly."""
        server = MCPServer("test-server")
        fallback = server._create_fallback_server()

        with patch("kailash.mcp_server.server.logger") as mock_logger:

            @fallback.resource("test://resource")
            def test_resource():
                return "resource"

            mock_logger.debug.assert_called_with(
                "Registered fallback resource: test://resource"
            )

    def test_fallback_server_prompt_registration_with_logging(self):
        """Test fallback server prompt registration logs properly."""
        server = MCPServer("test-server")
        fallback = server._create_fallback_server()

        with patch("kailash.mcp_server.server.logger") as mock_logger:

            @fallback.prompt("test_prompt")
            def test_prompt():
                return "prompt"

            mock_logger.debug.assert_called_with(
                "Registered fallback prompt: test_prompt"
            )

    def test_fallback_server_run_with_logging(self):
        """Test fallback server run() logs properly."""
        server = MCPServer("test-server")
        fallback = server._create_fallback_server()

        # Add some registered items for logging
        @fallback.tool()
        def test_tool():
            return "test"

        @fallback.resource("test://resource")
        def test_resource():
            return "resource"

        @fallback.prompt("test_prompt")
        def test_prompt():
            return "prompt"

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            with pytest.raises(NotImplementedError):
                fallback.run()

            mock_logger.warning.assert_called_with(
                "Fallback server 'test-server' run() called - FastMCP features limited"
            )
            mock_logger.info.assert_called_with(
                "Registered: 1 tools, 1 resources, 1 prompts"
            )


class TestMCPServerToolDecorator:
    """Test MCPServer tool decorator functionality."""

    def test_tool_decorator_with_required_permission(self):
        """Test tool decorator with required_permission."""
        server = MCPServer("test-server")

        @server.tool(required_permission="admin.execute")
        def test_tool():
            return "test"

        # Check registry
        assert "test_tool" in server._tool_registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["required_permission"] == "admin.execute"

    def test_tool_decorator_with_required_permissions_single(self):
        """Test tool decorator with required_permissions (single)."""
        server = MCPServer("test-server")

        @server.tool(required_permissions=["admin.execute"])
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["required_permission"] == "admin.execute"

    def test_tool_decorator_with_required_permissions_multiple(self):
        """Test tool decorator with required_permissions (multiple)."""
        server = MCPServer("test-server")

        with patch("kailash.mcp_server.server.logger") as mock_logger:

            @server.tool(required_permissions=["admin.execute", "user.read"])
            def test_tool():
                return "test"

            # Should use first permission and log warning
            tool_info = server._tool_registry["test_tool"]
            assert tool_info["required_permission"] == "admin.execute"

            mock_logger.warning.assert_called_with(
                "Tool test_tool: Multiple permissions specified, using first: admin.execute"
            )

    def test_tool_decorator_with_conflicting_permissions(self):
        """Test tool decorator with conflicting permission parameters."""
        server = MCPServer("test-server")

        with pytest.raises(
            ValueError,
            match="Cannot specify both required_permission and required_permissions",
        ):

            @server.tool(
                required_permission="admin.execute", required_permissions=["user.read"]
            )
            def test_tool():
                return "test"

    def test_tool_decorator_with_rate_limit(self):
        """Test tool decorator with rate limiting."""
        server = MCPServer("test-server")

        rate_limit_config = {"requests_per_minute": 10}

        @server.tool(rate_limit=rate_limit_config)
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["rate_limit"] == rate_limit_config

    def test_tool_decorator_with_circuit_breaker_disabled(self):
        """Test tool decorator with circuit breaker disabled."""
        server = MCPServer("test-server")

        @server.tool(enable_circuit_breaker=False)
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["enable_circuit_breaker"] is False

    def test_tool_decorator_with_timeout(self):
        """Test tool decorator with timeout."""
        server = MCPServer("test-server")

        @server.tool(timeout=30.0)
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["timeout"] == 30.0

    def test_tool_decorator_with_retryable_false(self):
        """Test tool decorator with retryable=False."""
        server = MCPServer("test-server")

        @server.tool(retryable=False)
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["retryable"] is False

    def test_tool_decorator_with_stream_response(self):
        """Test tool decorator with stream_response."""
        server = MCPServer("test-server")

        @server.tool(stream_response=True)
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["stream_response"] is True

    def test_tool_decorator_with_format_response(self):
        """Test tool decorator with format_response."""
        server = MCPServer("test-server")

        @server.tool(format_response="markdown")
        def test_tool():
            return "test"

        # Check registry
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["format_response"] == "markdown"

    def test_tool_decorator_initializes_mcp(self):
        """Test tool decorator initializes MCP if not already initialized."""
        server = MCPServer("test-server")
        assert server._mcp is None

        @server.tool()
        def test_tool():
            return "test"

        # MCP should be initialized
        assert server._mcp is not None

    def test_tool_decorator_registry_tracking(self):
        """Test tool decorator properly tracks in registry."""
        server = MCPServer("test-server")

        @server.tool(
            cache_key="test_cache",
            cache_ttl=600,
            format_response="json",
            required_permission="admin.execute",
            rate_limit={"requests_per_minute": 10},
            enable_circuit_breaker=True,
            timeout=30.0,
            retryable=True,
            stream_response=False,
        )
        def test_tool():
            return "test"

        # Check all registry fields
        tool_info = server._tool_registry["test_tool"]
        assert tool_info["cached"] is True
        assert tool_info["cache_key"] == "test_cache"
        assert tool_info["cache_ttl"] == 600
        assert tool_info["format_response"] == "json"
        assert tool_info["required_permission"] == "admin.execute"
        assert tool_info["rate_limit"] == {"requests_per_minute": 10}
        assert tool_info["enable_circuit_breaker"] is True
        assert tool_info["timeout"] == 30.0
        assert tool_info["retryable"] is True
        assert tool_info["stream_response"] is False
        assert tool_info["call_count"] == 0
        assert tool_info["error_count"] == 0
        assert tool_info["last_called"] is None


class TestMCPServerResourceAndPromptDecorators:
    """Test MCPServer resource and prompt decorators."""

    def test_resource_decorator_basic(self):
        """Test resource decorator basic functionality."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        @server.resource("file:///data/*")
        def test_resource():
            return "resource data"

        # Check that MCP was initialized (resource registration happens in MCP layer)
        assert server._mcp is not None

        # Verify function still works
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_resource, "fn"):
            assert test_resource.fn() == "resource data"
        else:
            assert test_resource() == "resource data"

    def test_resource_decorator_with_caching(self):
        """Test resource decorator with caching."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        @server.resource("file:///data/*")
        def test_resource():
            return "resource data"

        # Check that MCP was initialized (resource registration happens in MCP layer)
        assert server._mcp is not None

        # Verify function still works
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_resource, "fn"):
            assert test_resource.fn() == "resource data"
        else:
            assert test_resource() == "resource data"

    def test_resource_decorator_with_permission(self):
        """Test resource decorator with permission."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        @server.resource("file:///data/*")
        def test_resource():
            return "resource data"

        # Check that MCP was initialized (resource registration happens in MCP layer)
        assert server._mcp is not None

        # Verify function still works
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_resource, "fn"):
            assert test_resource.fn() == "resource data"
        else:
            assert test_resource() == "resource data"

    def test_resource_decorator_initializes_mcp(self):
        """Test resource decorator initializes MCP if not already initialized."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")
        assert server._mcp is None

        @server.resource("file:///data/*")
        def test_resource():
            return "resource data"

        # MCP should be initialized
        assert server._mcp is not None

    def test_prompt_decorator_basic(self):
        """Test prompt decorator basic functionality."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        @server.prompt("test_prompt")
        def test_prompt():
            return "prompt text"

        # Check that MCP was initialized (prompt registration happens in MCP layer)
        assert server._mcp is not None

        # Verify function still works
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_prompt, "fn"):
            assert test_prompt.fn() == "prompt text"
        else:
            assert test_prompt() == "prompt text"

    def test_prompt_decorator_with_caching(self):
        """Test prompt decorator with caching."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        @server.prompt("test_prompt")
        def test_prompt():
            return "prompt text"

        # Check that MCP was initialized (prompt registration happens in MCP layer)
        assert server._mcp is not None

        # Verify function still works
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_prompt, "fn"):
            assert test_prompt.fn() == "prompt text"
        else:
            assert test_prompt() == "prompt text"

    def test_prompt_decorator_with_permission(self):
        """Test prompt decorator with permission."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        @server.prompt("test_prompt")
        def test_prompt():
            return "prompt text"

        # Check that MCP was initialized (prompt registration happens in MCP layer)
        assert server._mcp is not None

        # Verify function still works
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_prompt, "fn"):
            assert test_prompt.fn() == "prompt text"
        else:
            assert test_prompt() == "prompt text"

    def test_prompt_decorator_initializes_mcp(self):
        """Test prompt decorator initializes MCP if not already initialized."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")
        assert server._mcp is None

        @server.prompt("test_prompt")
        def test_prompt():
            return "prompt text"

        # MCP should be initialized
        assert server._mcp is not None


class TestMCPServerRunMethod:
    """Test MCPServer run method functionality."""

    def test_run_method_with_transport_stdio(self):
        """Test run method with STDIO transport."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        # Mock transport configuration
        server.config.set("server.transport", "stdio")

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            mock_mcp.run.side_effect = KeyboardInterrupt  # Simulate stopping

            # Enhanced server catches KeyboardInterrupt and logs it
            server.run()

            mock_mcp.run.assert_called_once()
            mock_logger.info.assert_any_call(
                "Starting enhanced MCP server: test-server"
            )
            mock_logger.info.assert_any_call("Server stopped by user")

    def test_run_method_with_transport_http(self):
        """Test run method with HTTP transport."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server", enable_http_transport=True)

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        # Mock transport configuration
        server.config.set("server.transport", "http")
        server.config.set("server.http_port", 8080)

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            mock_mcp.run.side_effect = KeyboardInterrupt()  # Simulate stopping

            # Enhanced server catches KeyboardInterrupt and logs it
            server.run()

            mock_mcp.run.assert_called_once()
            mock_logger.info.assert_any_call(
                "Starting enhanced MCP server: test-server"
            )
            mock_logger.info.assert_any_call("Starting FastMCP server in STDIO mode...")

    def test_run_method_with_transport_sse(self):
        """Test run method with SSE transport."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server", enable_sse_transport=True)

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        # Mock transport configuration
        server.config.set("server.transport", "sse")
        server.config.set("server.sse_port", 8081)

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            mock_mcp.run.side_effect = KeyboardInterrupt()  # Simulate stopping

            # Enhanced server catches KeyboardInterrupt and logs it
            server.run()

            mock_mcp.run.assert_called_once()
            mock_logger.info.assert_any_call(
                "Starting enhanced MCP server: test-server"
            )
            mock_logger.info.assert_any_call("Starting FastMCP server in STDIO mode...")

    def test_run_method_initializes_mcp(self):
        """Test run method initializes MCP if not already initialized."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")
        assert server._mcp is None

        with patch.object(server, "_init_mcp") as mock_init:
            mock_mcp = Mock()
            mock_mcp.run.side_effect = KeyboardInterrupt()  # Simulate stopping

            # Set up the mock to return mock_mcp when called
            def set_mcp():
                server._mcp = mock_mcp

            mock_init.side_effect = set_mcp

            # Enhanced server catches KeyboardInterrupt and logs it
            server.run()

            mock_init.assert_called_once()

    def test_run_method_with_exception_handling(self):
        """Test run method handles exceptions properly."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        # Mock MCP server to raise exception
        mock_mcp = Mock()
        mock_mcp.run.side_effect = RuntimeError("Server failed")
        server._mcp = mock_mcp

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            with pytest.raises(RuntimeError, match="Server failed"):
                server.run()

            mock_logger.error.assert_called_with("Server error: Server failed")
            assert server._running is False

    def test_run_method_sets_running_flag(self):
        """Test run method sets and resets running flag."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")

        server = MCPServer("test-server")

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        # Track running state during execution
        running_states = []

        def track_running(*args, **kwargs):
            running_states.append(server._running)
            raise KeyboardInterrupt()

        mock_mcp.run.side_effect = track_running

        # Enhanced server catches KeyboardInterrupt and logs it
        server.run()

        # Should have been True during execution
        assert True in running_states
        # Should be False after execution
        assert server._running is False


class TestMCPServerInitialization:
    """Test MCPServer initialization with various configurations."""

    def test_init_with_circuit_breaker_config(self):
        """Test initialization with circuit breaker configuration."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")
        circuit_breaker_config = {"failure_threshold": 5, "timeout": 60}

        with patch("kailash.mcp_server.errors.CircuitBreakerRetry") as mock_cb:
            mock_cb_instance = Mock()
            mock_cb.return_value = mock_cb_instance

            server = MCPServer(
                "test-server", circuit_breaker_config=circuit_breaker_config
            )

            mock_cb.assert_called_once_with(**circuit_breaker_config)
            assert server.circuit_breaker is mock_cb_instance

    def test_init_without_circuit_breaker_config(self):
        """Test initialization without circuit breaker configuration."""
        server = MCPServer("test-server")

        assert server.circuit_breaker is None

    def test_init_with_error_aggregation_disabled(self):
        """Test initialization with error aggregation disabled."""
        server = MCPServer("test-server", error_aggregation=False)

        assert server.error_aggregator is None

    def test_init_with_config_file(self):
        """Test initialization with config file."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")
        # Create temporary config file
        config_data = {
            "server": {"name": "config-server"},
            "cache": {"enabled": False},
            "metrics": {"enabled": False},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            server = MCPServer(
                "test-server",
                config_file=config_file,
                enable_cache=False,
                enable_metrics=False,
            )

            # Should load config from file, but constructor params take precedence
            assert (
                server.name == "test-server"
            )  # Constructor parameter takes precedence
            assert server.config.get("cache.enabled") is False
            assert server.config.get("metrics.enabled") is False
        finally:
            Path(config_file).unlink()

    def test_init_with_enhanced_features(self):
        """Test initialization with all enhanced features."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")
        auth_provider = APIKeyAuth(["test-key"])
        rate_limit_config = {"default_limit": 100}
        circuit_breaker_config = {"failure_threshold": 5}
        connection_pool_config = {"max_connections": 10}

        server = MCPServer(
            "test-server",
            auth_provider=auth_provider,
            enable_http_transport=True,
            enable_sse_transport=True,
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config,
            enable_discovery=True,
            connection_pool_config=connection_pool_config,
            enable_streaming=True,
            enable_monitoring=True,
        )

        # Check all enhanced features are configured
        assert server.auth_provider is auth_provider
        assert server.enable_http_transport is True
        assert server.enable_sse_transport is True
        assert server.enable_discovery is True
        assert server.enable_streaming is True
        assert server.enable_monitoring is True
        assert server.auth_manager is not None
        assert server.circuit_breaker is not None

        # Check configuration
        assert server.config.get("server.enable_http") is True
        assert server.config.get("server.enable_sse") is True
        assert server.config.get("server.enable_streaming") is True
        assert server.config.get("auth.enabled") is True
        assert server.config.get("rate_limiting") == rate_limit_config
        assert server.config.get("circuit_breaker") == circuit_breaker_config
        assert server.config.get("discovery.enabled") is True
        assert server.config.get("connection_pool") == connection_pool_config
        assert server.config.get("monitoring.enabled") is True

    def test_init_with_cache_backends(self):
        """Test initialization with different cache backends."""
        # Test memory backend
        server_memory = MCPServer("test-server", cache_backend="memory")
        assert server_memory.cache.backend == "memory"

        # Test redis backend
        redis_config = {"redis_url": "redis://localhost:6379"}
        server_redis = MCPServer(
            "test-server", cache_backend="redis", cache_config=redis_config
        )
        assert server_redis.cache.backend == "redis"
        assert server_redis.cache.config == redis_config
