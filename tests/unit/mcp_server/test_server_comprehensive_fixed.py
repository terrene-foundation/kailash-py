"""Comprehensive tests for MCP server to improve coverage - Fixed version.

This test file focuses on missing coverage areas in server.py.
"""

import json
import logging
import tempfile
import time
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
            server._mcp = None  # Ensure _init_mcp will be called

            # Set up the mock to return mock_mcp when called
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

        with patch("kailash.mcp_server.server.logger"):
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

        with patch("kailash.mcp_server.server.logger"):
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

        with patch("kailash.mcp_server.server.logger"):
            with patch.dict("sys.modules", {"fastmcp": None}):  # Independent fails
                with patch.dict(
                    "sys.modules", {"mcp.server": Mock(FastMCP=mock_fastmcp)}
                ):
                    server._init_mcp()

                    assert server._mcp is mock_fastmcp_instance
                    mock_fastmcp.assert_called_once_with("test-server")

    def test_init_mcp_with_complete_fallback(self):
        """Test _init_mcp with complete fallback mode."""
        server = MCPServer("test-server")

        # Mock both FastMCP imports to fail
        with patch("kailash.mcp_server.server.logger") as mock_logger:
            with patch.dict("sys.modules", {"fastmcp": None}):
                with patch.dict("sys.modules", {"mcp.server": None}):
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


class TestMCPServerRunMethod:
    """Test MCPServer run method functionality."""

    def test_run_method_basic(self):
        """Test run method basic functionality."""
        server = MCPServer("test-server")

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        with patch("kailash.mcp_server.server.logger") as mock_logger:
            mock_mcp.run.side_effect = KeyboardInterrupt()  # Simulate stopping

            server.run()

            mock_mcp.run.assert_called_once()
            mock_logger.info.assert_any_call(
                "Starting enhanced MCP server: test-server"
            )
            mock_logger.info.assert_any_call("Server stopped by user")

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
            server._mcp = None  # Ensure _init_mcp will be called

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

        server.run()

        # Should have been True during execution
        assert True in running_states
        # Should be False after execution
        assert server._running is False

    def test_run_method_health_check(self):
        """Test run method performs health check."""
        server = MCPServer("test-server")

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        with patch.object(server, "health_check") as mock_health:
            mock_health.return_value = {"status": "healthy"}
            mock_mcp.run.side_effect = KeyboardInterrupt()

            server.run()

            mock_health.assert_called_once()

    def test_run_method_with_unhealthy_health_check(self):
        """Test run method with unhealthy health check."""
        server = MCPServer("test-server")

        # Mock MCP server
        mock_mcp = Mock()
        server._mcp = mock_mcp

        with patch.object(server, "health_check") as mock_health:
            with patch("kailash.mcp_server.server.logger") as mock_logger:
                mock_health.return_value = {
                    "status": "degraded",
                    "issues": ["Test issue"],
                }
                mock_mcp.run.side_effect = KeyboardInterrupt()

                server.run()

                mock_logger.warning.assert_called_with(
                    "Server health check shows issues: ['Test issue']"
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

    def test_tool_decorator_with_enhanced_features(self):
        """Test tool decorator with all enhanced features."""
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
        server = MCPServer("test-server")

        @server.resource("file:///data/*")
        def test_resource():
            return "resource data"

        # MCP should be initialized
        assert server._mcp is not None

    def test_prompt_decorator_basic(self):
        """Test prompt decorator basic functionality."""
        server = MCPServer("test-server")

        @server.prompt("test_prompt")
        def test_prompt():
            return "prompt text"

        # MCP should be initialized
        assert server._mcp is not None


class TestMCPServerHelperMethods:
    """Test MCPServer helper methods."""

    def test_format_response_without_formatting(self):
        """Test _format_response when formatting is disabled."""
        server = MCPServer("test-server")
        server.config.set("formatting.enabled", False)

        result = {"test": "data"}
        formatted = server._format_response(result, "json")

        assert formatted == result

    def test_format_response_with_streaming(self):
        """Test _format_response with streaming enabled."""
        server = MCPServer("test-server")

        # Large result that should trigger streaming
        result = {"data": "x" * 2000}
        formatted = server._format_response(result, None, stream_response=True)

        assert formatted["streaming"] is True
        assert formatted["data"] == result
        assert "chunks" in formatted

    def test_chunk_large_response_string(self):
        """Test _chunk_large_response with string data."""
        server = MCPServer("test-server")

        data = "x" * 2500
        chunks = server._chunk_large_response(data, chunk_size=1000)

        assert len(chunks) == 3
        assert chunks[0] == "x" * 1000
        assert chunks[1] == "x" * 1000
        assert chunks[2] == "x" * 500

    def test_chunk_large_response_dict(self):
        """Test _chunk_large_response with dict data."""
        server = MCPServer("test-server")

        data = {"key": "x" * 2000}
        chunks = server._chunk_large_response(data, chunk_size=1000)

        assert len(chunks) > 1
        assert isinstance(chunks[0], str)

    def test_extract_credentials_from_context(self):
        """Test _extract_credentials_from_context method."""
        server = MCPServer("test-server")

        kwargs = {
            "api_key": "test-key",
            "username": "test-user",
            "password": "test-pass",
            "other_param": "value",
        }

        credentials = server._extract_credentials_from_context(kwargs)

        assert credentials["api_key"] == "test-key"
        assert credentials["username"] == "test-user"
        assert credentials["password"] == "test-pass"
        assert "other_param" not in credentials

    def test_extract_credentials_with_mcp_auth(self):
        """Test _extract_credentials_from_context with mcp_auth."""
        server = MCPServer("test-server")

        kwargs = {"mcp_auth": {"token": "mcp-token"}, "other_param": "value"}

        credentials = server._extract_credentials_from_context(kwargs)

        assert credentials["token"] == "mcp-token"
        assert "other_param" not in credentials

    def test_extract_credentials_with_authorization_header(self):
        """Test _extract_credentials_from_context with authorization header."""
        server = MCPServer("test-server")

        kwargs = {"authorization": "Bearer test-token"}

        credentials = server._extract_credentials_from_context(kwargs)

        assert credentials["token"] == "test-token"

    def test_extract_credentials_with_basic_auth(self):
        """Test _extract_credentials_from_context with basic auth."""
        server = MCPServer("test-server")

        import base64

        auth_string = base64.b64encode(b"user:pass").decode()
        kwargs = {"authorization": f"Basic {auth_string}"}

        credentials = server._extract_credentials_from_context(kwargs)

        assert credentials["username"] == "user"
        assert credentials["password"] == "pass"


class TestMCPServerInitialization:
    """Test MCPServer initialization with various configurations."""

    def test_init_without_circuit_breaker_config(self):
        """Test initialization without circuit breaker configuration."""
        server = MCPServer("test-server")

        assert server.circuit_breaker is None

    def test_init_with_error_aggregation_disabled(self):
        """Test initialization with error aggregation disabled."""
        server = MCPServer("test-server", error_aggregation=False)

        assert server.error_aggregator is None

    def test_init_with_enhanced_features(self):
        """Test initialization with all enhanced features."""
        try:
            import mcp.server.fastmcp
        except ImportError:
            pytest.skip("mcp.server.fastmcp not available")
        auth_provider = APIKeyAuth(["test-key"])

        server = MCPServer(
            "test-server",
            auth_provider=auth_provider,
            enable_http_transport=True,
            enable_sse_transport=True,
            enable_discovery=True,
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

        # Check configuration
        assert server.config.get("server.enable_http") is True
        assert server.config.get("server.enable_sse") is True
        assert server.config.get("server.enable_streaming") is True
        assert server.config.get("auth.enabled") is True
        assert server.config.get("discovery.enabled") is True
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


class TestMCPServerStats:
    """Test MCPServer statistics methods."""

    def test_get_server_stats(self):
        """Test get_server_stats method."""
        server = MCPServer("test-server")

        stats = server.get_server_stats()

        assert isinstance(stats, dict)
        assert "server" in stats
        assert "tools" in stats
        assert "resources" in stats
        assert "prompts" in stats
        assert stats["server"]["name"] == "test-server"
        assert stats["server"]["running"] is False

    def test_get_resource_stats(self):
        """Test get_resource_stats method."""
        server = MCPServer("test-server")

        stats = server.get_resource_stats()

        assert isinstance(stats, dict)
        assert "registered_resources" in stats
        assert "resources" in stats
        assert stats["registered_resources"] == 0

    def test_get_prompt_stats(self):
        """Test get_prompt_stats method."""
        server = MCPServer("test-server")

        stats = server.get_prompt_stats()

        assert isinstance(stats, dict)
        assert "registered_prompts" in stats
        assert "prompts" in stats
        assert stats["registered_prompts"] == 0

    def test_get_active_sessions(self):
        """Test get_active_sessions method."""
        server = MCPServer("test-server")

        # Add mock session
        server._active_sessions["test-session"] = {
            "user": {"id": "user1"},
            "tool": "test_tool",
            "permission": "test.permission",
            "start_time": time.time(),
        }

        sessions = server.get_active_sessions()

        assert isinstance(sessions, dict)
        assert "test-session" in sessions
        assert sessions["test-session"]["user"]["id"] == "user1"
        assert sessions["test-session"]["tool"] == "test_tool"

    def test_get_error_trends_without_aggregator(self):
        """Test get_error_trends when no error aggregator is configured."""
        server = MCPServer("test-server", error_aggregation=False)

        trends = server.get_error_trends()

        assert trends == []

    def test_health_check_healthy(self):
        """Test health_check returns healthy status."""
        server = MCPServer("test-server")

        health = server.health_check()

        assert isinstance(health, dict)
        assert "status" in health
        assert "server" in health
        assert "components" in health
        assert "resources" in health
        assert health["status"] == "healthy"
        assert health["server"]["name"] == "test-server"

    def test_health_check_with_high_error_rate(self):
        """Test health_check with high error rate."""
        server = MCPServer("test-server")

        # Mock error aggregator to return high error rate
        with patch.object(server, "error_aggregator") as mock_aggregator:
            mock_aggregator.get_error_stats.return_value = {"error_rate": 15}

            health = server.health_check()

            assert health["status"] == "degraded"

    def test_health_check_with_circuit_breaker_open(self):
        """Test health_check with circuit breaker open."""
        server = MCPServer("test-server")

        # Mock circuit breaker to be open
        with patch.object(server, "circuit_breaker") as mock_cb:
            mock_cb.state = "open"

            health = server.health_check()

            assert health["status"] == "degraded"
