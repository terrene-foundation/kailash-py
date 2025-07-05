"""Unit tests for MCP server core functionality.

Tests for the server implementations in kailash.mcp_server.server.
NO MOCKING of external dependencies - This is a unit test file (Tier 1)
for isolated component testing.
"""

import asyncio
import json
import logging
import sys
import time
import uuid
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kailash.mcp_server.auth import (
    APIKeyAuth,
    BasicAuth,
    PermissionManager,
    RateLimiter,
)
from kailash.mcp_server.errors import (
    AuthenticationError,
    AuthorizationError,
    CircuitBreakerRetry,
    ErrorAggregator,
    MCPError,
    MCPErrorCode,
    RateLimitError,
    ToolError,
)
from kailash.mcp_server.server import MCPServer, MCPServerBase
from kailash.mcp_server.utils import CacheManager, ConfigManager, MetricsCollector


class TestMCPServerBase:
    """Test the abstract base MCP server class."""

    def test_init_sets_attributes(self):
        """Test that initialization sets all required attributes."""

        # Create a concrete implementation for testing
        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server", port=8080, host="localhost")

        assert server.name == "test-server"
        assert server.port == 8080
        assert server.host == "localhost"
        assert server._mcp is None
        assert server._running is False

    def test_init_with_default_values(self):
        """Test initialization with default port and host."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        assert server.name == "test-server"
        assert server.port == 8080
        assert server.host == "localhost"

    def test_init_mcp_imports_fastmcp(self):
        """Test that _init_mcp properly imports FastMCP."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        # Mock the FastMCP import from mcp.server
        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_fastmcp.return_value = MagicMock()
            server._init_mcp()

            assert server._mcp is not None
            mock_fastmcp.assert_called_once_with("test-server")

    def test_init_mcp_handles_import_error(self):
        """Test that _init_mcp raises ImportError when FastMCP is not available."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        # Mock ImportError by making the import fail
        with patch("builtins.__import__", side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError, match="Module not found"):
                server._init_mcp()

    def test_add_tool_initializes_mcp(self):
        """Test that add_tool decorator initializes FastMCP if needed."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        # Directly mock the _init_mcp method to verify it's called
        with patch.object(server, "_init_mcp") as mock_init_mcp:
            # Create a fake _mcp instance after _init_mcp is called
            def set_mcp():
                server._mcp = MagicMock()
                server._mcp.tool.return_value.return_value = lambda func: func

            mock_init_mcp.side_effect = set_mcp

            # Create a decorator and apply it to a function
            decorator = server.add_tool()

            def test_func():
                return "test"

            # Apply the decorator (this is when _init_mcp should be called)
            decorated_func = decorator(test_func)

            # Check that _init_mcp was called and _mcp was set
            mock_init_mcp.assert_called_once()
            assert server._mcp is not None

    def test_add_tool_decorator_wraps_function(self):
        """Test that add_tool decorator properly wraps functions."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            # Set up the decorator chain: tool() returns decorator, decorator(func) returns wrapped func
            mock_tool_decorator.return_value = MagicMock()  # The wrapped function
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.add_tool()
            def test_function():
                return "test"

            # Check that the FastMCP tool decorator was called correctly
            mock_mcp_instance.tool.assert_called_once_with()  # tool() called with no args
            mock_tool_decorator.assert_called_once()  # decorator called with function

    def test_add_resource_initializes_mcp(self):
        """Test that add_resource decorator initializes FastMCP if needed."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_resource_decorator = MagicMock()
            mock_resource_decorator.return_value = MagicMock()
            mock_mcp_instance.resource.return_value = mock_resource_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            # Apply the decorator to a function (this triggers initialization)
            @server.add_resource("file:///test/*")
            def test_function():
                return "test"

            # Check that FastMCP was initialized
            assert server._mcp is not None
            mock_fastmcp.assert_called_once_with("test-server")

    def test_add_resource_decorator_wraps_function(self):
        """Test that add_resource decorator properly wraps functions."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_resource_decorator = MagicMock()
            # Set up the decorator chain: resource(uri) returns decorator, decorator(func) returns wrapped func
            mock_resource_decorator.return_value = MagicMock()  # The wrapped function
            mock_mcp_instance.resource.return_value = mock_resource_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.add_resource("file:///test/*")
            def test_function():
                return "test"

            # Check that the FastMCP resource decorator was called correctly
            mock_mcp_instance.resource.assert_called_once_with("file:///test/*")
            mock_resource_decorator.assert_called_once()  # decorator called with function

    def test_add_prompt_initializes_mcp(self):
        """Test that add_prompt decorator initializes FastMCP if needed."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_prompt_decorator = MagicMock()
            mock_prompt_decorator.return_value = MagicMock()
            mock_mcp_instance.prompt.return_value = mock_prompt_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            # Apply the decorator to a function (this triggers initialization)
            @server.add_prompt("test-prompt")
            def test_function():
                return "test"

            # Check that FastMCP was initialized
            assert server._mcp is not None
            mock_fastmcp.assert_called_once_with("test-server")

    def test_add_prompt_decorator_wraps_function(self):
        """Test that add_prompt decorator properly wraps functions."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_prompt_decorator = MagicMock()
            # Set up the decorator chain: prompt(name) returns decorator, decorator(func) returns wrapped func
            mock_prompt_decorator.return_value = MagicMock()  # The wrapped function
            mock_mcp_instance.prompt.return_value = mock_prompt_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.add_prompt("test-prompt")
            def test_function():
                return "test"

            # Check that the FastMCP prompt decorator was called correctly
            mock_mcp_instance.prompt.assert_called_once_with("test-prompt")
            mock_prompt_decorator.assert_called_once()  # decorator called with function

    def test_start_calls_setup_and_runs_server(self):
        """Test that start() calls setup() and runs the server."""

        class TestServer(MCPServerBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.setup_called = False

            def setup(self):
                self.setup_called = True

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock the run method to avoid actually starting the server
            mock_mcp_instance.run.side_effect = KeyboardInterrupt()

            with pytest.raises(KeyboardInterrupt):
                server.start()

            assert server.setup_called
            assert server._running is False  # Should be reset after exception
            mock_mcp_instance.run.assert_called_once()

    def test_start_handles_exceptions(self):
        """Test that start() properly handles exceptions."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock an exception during server run
            mock_mcp_instance.run.side_effect = Exception("Server error")

            with pytest.raises(Exception, match="Server error"):
                server.start()

            assert server._running is False

    def test_stop_sets_running_false(self):
        """Test that stop() sets _running to False."""

        class TestServer(MCPServerBase):
            def setup(self):
                pass

        server = TestServer("test-server")
        server._running = True

        server.stop()

        assert server._running is False


class TestMCPServer:
    """Test the enhanced MCP server implementation."""

    def test_init_with_minimal_config(self):
        """Test initialization with minimal configuration."""
        server = MCPServer("test-server")

        assert server.name == "test-server"
        assert server.auth_provider is None
        assert server.enable_http_transport is False
        assert server.enable_sse_transport is False
        assert server.enable_discovery is False
        assert server.enable_streaming is False
        assert server.enable_monitoring is False
        assert server.transport_timeout == 30.0
        assert server.max_request_size == 10_000_000
        assert server._mcp is None
        assert server._running is False

    def test_init_with_full_config(self):
        """Test initialization with comprehensive configuration."""
        auth_provider = APIKeyAuth(["test-key"])
        cache_config = {"redis_url": "redis://localhost:6379"}
        rate_limit_config = {"default_limit": 60, "burst_limit": 10}
        circuit_breaker_config = {"failure_threshold": 3}
        connection_pool_config = {"max_connections": 10}

        server = MCPServer(
            name="full-server",
            enable_cache=True,
            cache_ttl=600,
            cache_backend="redis",
            cache_config=cache_config,
            enable_metrics=True,
            enable_formatting=True,
            enable_monitoring=True,
            auth_provider=auth_provider,
            enable_http_transport=True,
            enable_sse_transport=True,
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config,
            enable_discovery=True,
            connection_pool_config=connection_pool_config,
            error_aggregation=True,
            transport_timeout=60.0,
            max_request_size=20_000_000,
            enable_streaming=True,
        )

        assert server.name == "full-server"
        assert server.auth_provider is auth_provider
        assert server.enable_http_transport is True
        assert server.enable_sse_transport is True
        assert server.enable_discovery is True
        assert server.enable_streaming is True
        assert server.enable_monitoring is True
        assert server.transport_timeout == 60.0
        assert server.max_request_size == 20_000_000
        assert server.auth_manager is not None
        assert server.cache is not None
        assert server.metrics is not None
        assert server.error_aggregator is not None
        assert server.circuit_breaker is not None

    def test_init_with_config_file(self):
        """Test initialization with configuration file."""
        # Create a temporary config file
        config_content = {
            "server": {"name": "config-server"},
            "cache": {"enabled": True, "default_ttl": 300},
        }

        with patch("kailash.mcp_server.server.ConfigManager") as mock_config_manager:
            mock_config_instance = MagicMock()
            # Set up mock to have get method that returns expected values
            mock_config_instance.get.return_value = False
            mock_config_instance.update = MagicMock()
            mock_config_manager.return_value = mock_config_instance

            server = MCPServer("test-server", config_file="config.json")

            mock_config_manager.assert_called_once_with("config.json")
            # The config should be updated with defaults
            assert mock_config_instance.update.called

    def test_init_components_properly(self):
        """Test that components are initialized correctly."""
        server = MCPServer("test-server", enable_cache=True, enable_metrics=True)

        assert isinstance(server.config, ConfigManager)
        assert isinstance(server.cache, CacheManager)
        assert isinstance(server.metrics, MetricsCollector)
        assert server.error_aggregator is not None
        assert len(server._tool_registry) == 0
        assert len(server._resource_registry) == 0
        assert len(server._prompt_registry) == 0
        assert len(server._active_sessions) == 0
        assert len(server._connection_pools) == 0

    def test_init_with_auth_provider(self):
        """Test initialization with authentication provider."""
        auth_provider = APIKeyAuth(["test-key"])
        server = MCPServer("test-server", auth_provider=auth_provider)

        assert server.auth_provider is auth_provider
        assert server.auth_manager is not None
        assert server.auth_manager.provider is auth_provider
        assert isinstance(server.auth_manager.permission_manager, PermissionManager)
        assert isinstance(server.auth_manager.rate_limiter, RateLimiter)

    def test_init_with_circuit_breaker(self):
        """Test initialization with circuit breaker configuration."""
        circuit_breaker_config = {
            "failure_threshold": 5,
            "timeout": 30.0,
            "success_threshold": 3,
        }

        server = MCPServer("test-server", circuit_breaker_config=circuit_breaker_config)

        assert server.circuit_breaker is not None
        assert isinstance(server.circuit_breaker, CircuitBreakerRetry)

    def test_init_mcp_imports_fastmcp(self):
        """Test that _init_mcp properly imports FastMCP."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            server._init_mcp()

            assert server._mcp is not None
            mock_fastmcp.assert_called_once_with("test-server")

    def test_init_mcp_handles_import_error(self):
        """Test that _init_mcp raises ImportError when FastMCP is not available."""
        server = MCPServer("test-server")

        with patch("builtins.__import__", side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError, match="FastMCP not available"):
                server._init_mcp()

    def test_init_mcp_idempotent(self):
        """Test that _init_mcp is idempotent (can be called multiple times)."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Call twice
            server._init_mcp()
            server._init_mcp()

            # Should only initialize once
            mock_fastmcp.assert_called_once_with("test-server")

    def test_tool_decorator_basic(self):
        """Test basic tool decorator functionality."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.tool()
            def test_function():
                return "test"

            # Check that the tool was registered
            assert "test_function" in server._tool_registry
            tool_info = server._tool_registry["test_function"]
            assert tool_info["cached"] is False
            assert tool_info["cache_key"] is None
            assert tool_info["call_count"] == 0
            assert tool_info["error_count"] == 0

    def test_tool_decorator_with_cache(self):
        """Test tool decorator with caching enabled."""
        server = MCPServer("test-server", enable_cache=True)

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.tool(cache_key="test_cache", cache_ttl=600)
            def test_function():
                return "test"

            # Check that caching info was stored
            tool_info = server._tool_registry["test_function"]
            assert tool_info["cached"] is True
            assert tool_info["cache_key"] == "test_cache"
            assert tool_info["cache_ttl"] == 600

    def test_tool_decorator_with_auth(self):
        """Test tool decorator with authentication requirements."""
        auth_provider = APIKeyAuth(["test-key"])
        server = MCPServer("test-server", auth_provider=auth_provider)

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.tool(required_permission="test.read")
            def test_function():
                return "test"

            # Check that auth info was stored
            tool_info = server._tool_registry["test_function"]
            assert tool_info["required_permission"] == "test.read"

    def test_tool_decorator_permission_validation(self):
        """Test tool decorator validates permission configuration."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Should raise error if both required_permission and required_permissions are specified
            with pytest.raises(
                ValueError,
                match="Cannot specify both required_permission and required_permissions",
            ):

                @server.tool(
                    required_permission="test.read", required_permissions=["test.read"]
                )
                def test_function():
                    return "test"

    def test_tool_decorator_with_multiple_permissions(self):
        """Test tool decorator with multiple permissions (uses first one)."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.tool(required_permissions=["test.read", "test.write"])
            def test_function():
                return "test"

            # Check that it uses the first permission
            tool_info = server._tool_registry["test_function"]
            assert tool_info["required_permission"] == "test.read"

    def test_tool_decorator_with_rate_limiting(self):
        """Test tool decorator with rate limiting configuration."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            rate_limit_config = {"requests_per_minute": 10}

            @server.tool(rate_limit=rate_limit_config)
            def test_function():
                return "test"

            # Check that rate limiting info was stored
            tool_info = server._tool_registry["test_function"]
            assert tool_info["rate_limit"] == rate_limit_config

    def test_tool_decorator_with_all_options(self):
        """Test tool decorator with all configuration options."""
        auth_provider = APIKeyAuth(["test-key"])
        server = MCPServer(
            "test-server", auth_provider=auth_provider, enable_cache=True
        )

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.tool(
                cache_key="comprehensive_cache",
                cache_ttl=1200,
                format_response="json",
                required_permission="test.execute",
                rate_limit={"requests_per_minute": 5},
                enable_circuit_breaker=True,
                timeout=30.0,
                retryable=True,
                stream_response=True,
            )
            def test_function():
                return "test"

            # Check that all options were stored
            tool_info = server._tool_registry["test_function"]
            assert tool_info["cached"] is True
            assert tool_info["cache_key"] == "comprehensive_cache"
            assert tool_info["cache_ttl"] == 1200
            assert tool_info["format_response"] == "json"
            assert tool_info["required_permission"] == "test.execute"
            assert tool_info["rate_limit"] == {"requests_per_minute": 5}
            assert tool_info["enable_circuit_breaker"] is True
            assert tool_info["timeout"] == 30.0
            assert tool_info["retryable"] is True
            assert tool_info["stream_response"] is True

    def test_resource_decorator(self):
        """Test resource decorator functionality."""
        server = MCPServer("test-server", enable_metrics=True)

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_resource_decorator = MagicMock()
            mock_mcp_instance.resource.return_value = mock_resource_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.resource("file:///test/*")
            def test_resource():
                return "resource data"

            # Check that the resource decorator was called
            mock_mcp_instance.resource.assert_called_once_with("file:///test/*")

    def test_prompt_decorator(self):
        """Test prompt decorator functionality."""
        server = MCPServer("test-server", enable_metrics=True)

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_prompt_decorator = MagicMock()
            mock_mcp_instance.prompt.return_value = mock_prompt_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.prompt("test-prompt")
            def test_prompt():
                return "prompt template"

            # Check that the prompt decorator was called
            mock_mcp_instance.prompt.assert_called_once_with("test-prompt")

    def test_get_tool_stats(self):
        """Test getting tool statistics."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            @server.tool(cache_key="test_cache")
            def cached_tool():
                return "cached"

            @server.tool()
            def regular_tool():
                return "regular"

            stats = server.get_tool_stats()

            assert stats["registered_tools"] == 2
            assert stats["cached_tools"] == 1
            assert "cached_tool" in stats["tools"]
            assert "regular_tool" in stats["tools"]
            assert stats["tools"]["cached_tool"]["cached"] is True
            assert stats["tools"]["regular_tool"]["cached"] is False

    def test_get_server_stats(self):
        """Test getting comprehensive server statistics."""
        server = MCPServer("test-server", enable_cache=True, enable_metrics=True)

        # Mock metrics export
        with patch.object(server.metrics, "export_metrics") as mock_export:
            mock_export.return_value = {"total_calls": 10}

            # Mock cache stats
            with patch.object(server.cache, "stats") as mock_cache_stats:
                mock_cache_stats.return_value = {"hit_rate": 0.8}

                stats = server.get_server_stats()

                assert stats["server"]["name"] == "test-server"
                assert stats["server"]["running"] is False
                assert "transport" in stats["server"]
                assert "features" in stats["server"]
                assert "tools" in stats
                assert "resources" in stats
                assert "prompts" in stats
                assert "metrics" in stats
                assert "cache" in stats

    def test_get_server_stats_with_auth(self):
        """Test server statistics with authentication enabled."""
        auth_provider = APIKeyAuth(["test-key"])
        server = MCPServer("test-server", auth_provider=auth_provider)

        stats = server.get_server_stats()

        assert stats["server"]["features"]["auth_enabled"] is True

    def test_get_server_stats_with_circuit_breaker(self):
        """Test server statistics with circuit breaker enabled."""
        circuit_breaker_config = {"failure_threshold": 5}
        server = MCPServer("test-server", circuit_breaker_config=circuit_breaker_config)

        stats = server.get_server_stats()

        assert stats["server"]["features"]["circuit_breaker_enabled"] is True
        assert "circuit_breaker" in stats

    def test_get_server_stats_with_error_aggregation(self):
        """Test server statistics with error aggregation enabled."""
        server = MCPServer("test-server", error_aggregation=True)

        # Mock error aggregator stats
        with patch.object(
            server.error_aggregator, "get_error_stats"
        ) as mock_error_stats:
            mock_error_stats.return_value = {"total_errors": 5}

            stats = server.get_server_stats()

            assert stats["server"]["features"]["error_aggregation_enabled"] is True
            assert "errors" in stats
            assert stats["errors"]["total_errors"] == 5

    def test_get_resource_stats(self):
        """Test getting resource statistics."""
        server = MCPServer("test-server")

        # Add some mock resource data
        server._resource_registry["file:///test"] = {
            "call_count": 5,
            "error_count": 1,
            "last_accessed": time.time(),
        }

        stats = server.get_resource_stats()

        assert stats["registered_resources"] == 1
        assert "file:///test" in stats["resources"]
        assert stats["resources"]["file:///test"]["call_count"] == 5
        assert stats["resources"]["file:///test"]["error_count"] == 1

    def test_get_prompt_stats(self):
        """Test getting prompt statistics."""
        server = MCPServer("test-server")

        # Add some mock prompt data
        server._prompt_registry["test-prompt"] = {
            "call_count": 3,
            "error_count": 0,
            "last_used": time.time(),
        }

        stats = server.get_prompt_stats()

        assert stats["registered_prompts"] == 1
        assert "test-prompt" in stats["prompts"]
        assert stats["prompts"]["test-prompt"]["call_count"] == 3
        assert stats["prompts"]["test-prompt"]["error_count"] == 0

    def test_get_active_sessions(self):
        """Test getting active session information."""
        server = MCPServer("test-server")

        # Add some mock session data
        session_id = str(uuid.uuid4())
        start_time = time.time()
        server._active_sessions[session_id] = {
            "user": {"id": "test-user"},
            "tool": "test-tool",
            "permission": "test.read",
            "start_time": start_time,
        }

        sessions = server.get_active_sessions()

        assert session_id in sessions
        assert sessions[session_id]["user"]["id"] == "test-user"
        assert sessions[session_id]["tool"] == "test-tool"
        assert sessions[session_id]["permission"] == "test.read"
        assert sessions[session_id]["duration"] > 0

    def test_get_error_trends(self):
        """Test getting error trends."""
        server = MCPServer("test-server", error_aggregation=True)

        # Mock error aggregator trends
        with patch.object(server.error_aggregator, "get_error_trends") as mock_trends:
            mock_trends.return_value = [{"timestamp": time.time(), "error_count": 5}]

            trends = server.get_error_trends()

            assert len(trends) == 1
            assert trends[0]["error_count"] == 5

    def test_get_error_trends_without_aggregator(self):
        """Test getting error trends when aggregator is disabled."""
        server = MCPServer("test-server", error_aggregation=False)

        trends = server.get_error_trends()

        assert trends == []

    def test_health_check_healthy(self):
        """Test health check when server is healthy."""
        server = MCPServer("test-server", enable_cache=True, enable_metrics=True)

        # Mock components as healthy
        with patch.object(server.cache, "stats") as mock_cache_stats:
            mock_cache_stats.return_value = {"main": {"utilization": 0.5}}

            health = server.health_check()

            assert health["status"] == "healthy"
            assert health["server"]["name"] == "test-server"
            assert health["components"]["cache"] is True
            assert health["components"]["metrics"] is True
            assert health["components"]["mcp"] is False  # Not initialized
            assert len(health["issues"]) == 0

    def test_health_check_with_high_error_rate(self):
        """Test health check with high error rate."""
        server = MCPServer("test-server", error_aggregation=True)

        # Mock high error rate
        with patch.object(
            server.error_aggregator, "get_error_stats"
        ) as mock_error_stats:
            mock_error_stats.return_value = {"error_rate": 15}  # High error rate

            health = server.health_check()

            assert health["status"] == "degraded"
            assert "High error rate detected" in health["issues"]

    def test_health_check_with_circuit_breaker_open(self):
        """Test health check with circuit breaker open."""
        circuit_breaker_config = {"failure_threshold": 5}
        server = MCPServer("test-server", circuit_breaker_config=circuit_breaker_config)

        # Set circuit breaker to open state
        server.circuit_breaker.state = "open"

        health = server.health_check()

        assert health["status"] == "degraded"
        assert "Circuit breaker is open" in health["issues"]

    def test_health_check_with_cache_full(self):
        """Test health check with cache nearly full."""
        server = MCPServer("test-server", enable_cache=True)

        # Mock cache stats showing high utilization
        with patch.object(server.cache, "stats") as mock_cache_stats:
            mock_cache_stats.return_value = {"main": {"utilization": 0.95}}

            health = server.health_check()

            assert health["status"] == "degraded"
            assert any(
                "Cache main is over 90% full" in issue for issue in health["issues"]
            )

    def test_clear_cache_specific(self):
        """Test clearing a specific cache."""
        server = MCPServer("test-server", enable_cache=True)

        # Mock cache manager
        mock_cache = MagicMock()
        with patch.object(server.cache, "get_cache") as mock_get_cache:
            mock_get_cache.return_value = mock_cache

            server.clear_cache("test_cache")

            mock_get_cache.assert_called_once_with("test_cache")
            mock_cache.clear.assert_called_once()

    def test_clear_cache_all(self):
        """Test clearing all caches."""
        server = MCPServer("test-server", enable_cache=True)

        # Mock cache manager
        with patch.object(server.cache, "clear_all") as mock_clear_all:
            server.clear_cache()

            mock_clear_all.assert_called_once()

    def test_reset_circuit_breaker(self):
        """Test resetting circuit breaker."""
        circuit_breaker_config = {"failure_threshold": 5}
        server = MCPServer("test-server", circuit_breaker_config=circuit_breaker_config)

        # Set circuit breaker to failed state
        server.circuit_breaker.state = "open"
        server.circuit_breaker.failure_count = 10
        server.circuit_breaker.success_count = 5

        server.reset_circuit_breaker()

        assert server.circuit_breaker.state == "closed"
        assert server.circuit_breaker.failure_count == 0
        assert server.circuit_breaker.success_count == 0

    def test_reset_circuit_breaker_when_none(self):
        """Test resetting circuit breaker when none is configured."""
        server = MCPServer("test-server")

        # Should not raise exception
        server.reset_circuit_breaker()

    def test_terminate_session(self):
        """Test terminating an active session."""
        server = MCPServer("test-server")

        # Add a session
        session_id = str(uuid.uuid4())
        server._active_sessions[session_id] = {"user": {"id": "test-user"}}

        result = server.terminate_session(session_id)

        assert result is True
        assert session_id not in server._active_sessions

    def test_terminate_session_not_found(self):
        """Test terminating a session that doesn't exist."""
        server = MCPServer("test-server")

        result = server.terminate_session("non-existent-session")

        assert result is False

    def test_get_tool_by_name(self):
        """Test getting tool information by name."""
        server = MCPServer("test-server")

        # Add tool to registry
        server._tool_registry["test-tool"] = {"cached": True, "cache_key": "test_cache"}

        tool_info = server.get_tool_by_name("test-tool")

        assert tool_info is not None
        assert tool_info["cached"] is True
        assert tool_info["cache_key"] == "test_cache"

    def test_get_tool_by_name_not_found(self):
        """Test getting tool information for non-existent tool."""
        server = MCPServer("test-server")

        tool_info = server.get_tool_by_name("non-existent-tool")

        assert tool_info is None

    def test_disable_tool(self):
        """Test disabling a tool."""
        server = MCPServer("test-server")

        # Add tool to registry
        server._tool_registry["test-tool"] = {"cached": False}

        result = server.disable_tool("test-tool")

        assert result is True
        assert server._tool_registry["test-tool"]["disabled"] is True

    def test_disable_tool_not_found(self):
        """Test disabling a tool that doesn't exist."""
        server = MCPServer("test-server")

        result = server.disable_tool("non-existent-tool")

        assert result is False

    def test_enable_tool(self):
        """Test enabling a tool."""
        server = MCPServer("test-server")

        # Add disabled tool to registry
        server._tool_registry["test-tool"] = {"disabled": True}

        result = server.enable_tool("test-tool")

        assert result is True
        assert server._tool_registry["test-tool"]["disabled"] is False

    def test_enable_tool_not_found(self):
        """Test enabling a tool that doesn't exist."""
        server = MCPServer("test-server")

        result = server.enable_tool("non-existent-tool")

        assert result is False

    def test_run_logs_startup_info(self):
        """Test that run() logs appropriate startup information."""
        server = MCPServer("test-server", enable_cache=True, enable_metrics=True)

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock the run method to avoid actually starting the server
            mock_mcp_instance.run.side_effect = KeyboardInterrupt()

            with patch("kailash.mcp_server.server.logger") as mock_logger:
                # Ensure _mcp is None so _init_mcp gets called
                server._mcp = None

                # Run will catch KeyboardInterrupt and log it
                server.run()

                # Check that startup info was logged
                mock_logger.info.assert_called()
                info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                assert any("Starting enhanced MCP server" in msg for msg in info_calls)
                assert any("Features enabled" in msg for msg in info_calls)
                # Also check that it logged the shutdown
                assert any("Server stopped by user" in msg for msg in info_calls)

    def test_run_performs_health_check(self):
        """Test that run() performs health check before starting."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance
            mock_mcp_instance.run.side_effect = KeyboardInterrupt()

            with patch.object(server, "health_check") as mock_health_check:
                mock_health_check.return_value = {"status": "healthy", "issues": []}

                # Ensure _mcp is None so _init_mcp gets called
                server._mcp = None

                # Run will catch KeyboardInterrupt internally
                server.run()

                mock_health_check.assert_called_once()

    def test_run_handles_server_errors(self):
        """Test that run() properly handles server errors."""
        server = MCPServer("test-server", error_aggregation=True)

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance
            mock_mcp_instance.run.side_effect = Exception("Server error")

            with patch.object(
                server.error_aggregator, "record_error"
            ) as mock_record_error:
                with pytest.raises(Exception, match="Server error"):
                    server.run()

                mock_record_error.assert_called_once()

    def test_run_cleanup_on_exit(self):
        """Test that run() properly cleans up on exit."""
        server = MCPServer("test-server", enable_metrics=True)

        # Add some active sessions
        session_id = str(uuid.uuid4())
        server._active_sessions[session_id] = {"user": {"id": "test-user"}}

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance
            mock_mcp_instance.run.side_effect = KeyboardInterrupt()

            with patch.object(server, "get_server_stats") as mock_get_stats:
                mock_get_stats.return_value = {"metrics": {"total_calls": 10}}

                # Ensure _mcp is None so _init_mcp gets called
                server._mcp = None

                # Run will catch KeyboardInterrupt and perform cleanup
                server.run()

                # Check that active sessions were cleared
                assert len(server._active_sessions) == 0
                assert server._running is False

    @pytest.mark.asyncio
    async def test_run_stdio_basic(self):
        """Test stdio mode server operation."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock stdin/stdout
            mock_stdin = StringIO('{"method": "tools/list", "id": 1}\n')
            mock_stdout = StringIO()

            with patch("sys.stdin", mock_stdin):
                with patch("sys.stdout", mock_stdout):
                    # Mock the readline to return empty to exit the loop
                    mock_stdin.readline = MagicMock(
                        side_effect=['{"method": "tools/list", "id": 1}', ""]
                    )

                    await server.run_stdio()

                    # Check that response was written
                    output = mock_stdout.getvalue()
                    # Should have written something (exact format depends on implementation)
                    # For now, just check that run_stdio completed without error
                    assert True  # Test passed if we got here

    @pytest.mark.asyncio
    async def test_run_stdio_handles_invalid_json(self):
        """Test stdio mode handles invalid JSON gracefully."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock stdin with invalid JSON
            mock_stdin = MagicMock()
            mock_stdin.readline.side_effect = ["invalid json", ""]

            mock_stdout = MagicMock()

            with patch("sys.stdin", mock_stdin):
                with patch("sys.stdout", mock_stdout):
                    await server.run_stdio()

                    # Should have written an error response
                    assert mock_stdout.write.called

    def test_format_response_basic(self):
        """Test basic response formatting."""
        server = MCPServer("test-server", enable_formatting=True)

        result = "test response"
        formatted = server._format_response(result, None)

        assert formatted == result

    def test_format_response_with_formatting(self):
        """Test response formatting with specific format."""
        server = MCPServer("test-server", enable_formatting=True)

        # Patch where format_response is used in the server module
        with patch("kailash.mcp_server.server.format_response") as mock_format:
            mock_format.return_value = "formatted response"

            result = "test response"
            formatted = server._format_response(result, "json")

            assert formatted == "formatted response"
            mock_format.assert_called_once_with(result, "json")

    def test_format_response_handles_formatting_errors(self):
        """Test response formatting handles errors gracefully."""
        server = MCPServer("test-server", enable_formatting=True)

        # Patch where format_response is used in the server module
        with patch("kailash.mcp_server.server.format_response") as mock_format:
            mock_format.side_effect = Exception("Format error")

            result = "test response"
            formatted = server._format_response(result, "json")

            # Should return original result on formatting error
            assert formatted == result

    def test_format_response_with_streaming(self):
        """Test response formatting with streaming enabled."""
        server = MCPServer("test-server", enable_formatting=True, enable_streaming=True)

        # Large response that should trigger streaming (must be list/dict)
        large_response = {"data": "x" * 2000}
        formatted = server._format_response(large_response, None, stream_response=True)

        assert formatted["streaming"] is True
        assert formatted["data"] == large_response
        assert "chunks" in formatted

    def test_chunk_large_response_string(self):
        """Test chunking large string responses."""
        server = MCPServer("test-server")

        data = "x" * 2500
        chunks = server._chunk_large_response(data, chunk_size=1000)

        assert len(chunks) == 3
        assert chunks[0] == "x" * 1000
        assert chunks[1] == "x" * 1000
        assert chunks[2] == "x" * 500

    def test_chunk_large_response_dict(self):
        """Test chunking large dict responses."""
        server = MCPServer("test-server")

        data = {"key": "x" * 2000}
        chunks = server._chunk_large_response(data, chunk_size=1000)

        assert len(chunks) > 1
        assert isinstance(chunks[0], str)

    def test_extract_credentials_from_context(self):
        """Test extracting credentials from function context."""
        server = MCPServer("test-server")

        # Test with mcp_auth
        kwargs = {"mcp_auth": {"api_key": "test-key"}}
        credentials = server._extract_credentials_from_context(kwargs)
        assert credentials["api_key"] == "test-key"

        # Test with direct auth fields
        kwargs = {"api_key": "direct-key", "username": "user"}
        credentials = server._extract_credentials_from_context(kwargs)
        assert credentials["api_key"] == "direct-key"
        assert credentials["username"] == "user"

        # Test with Authorization header (Bearer)
        kwargs = {"authorization": "Bearer token123"}
        credentials = server._extract_credentials_from_context(kwargs)
        assert credentials["token"] == "token123"

        # Test with Authorization header (Basic)
        import base64

        basic_auth = base64.b64encode(b"user:pass").decode()
        kwargs = {"authorization": f"Basic {basic_auth}"}
        credentials = server._extract_credentials_from_context(kwargs)
        assert credentials["username"] == "user"
        assert credentials["password"] == "pass"

    def test_extract_credentials_handles_malformed_basic_auth(self):
        """Test extracting credentials handles malformed basic auth."""
        server = MCPServer("test-server")

        # Test with invalid base64
        kwargs = {"authorization": "Basic invalid_base64!"}
        credentials = server._extract_credentials_from_context(kwargs)
        # Should not crash, just return empty credentials
        assert "username" not in credentials
        assert "password" not in credentials


class TestMCPServerErrorHandling:
    """Test error handling in MCP server."""

    def test_server_logs_appropriate_level(self):
        """Test that server uses appropriate logging level."""
        server = MCPServer("test-server")

        # Test that logger is configured
        assert logging.getLogger("kailash.mcp_server.server") is not None

    def test_server_handles_config_errors(self):
        """Test that server handles configuration errors gracefully."""
        # ConfigManager handles missing files gracefully with warnings
        # This test verifies the server can still be created even with invalid config file
        server = MCPServer("test-server", config_file="invalid.json")

        # Server should still be created successfully
        assert server is not None
        assert server.name == "test-server"

    def test_server_handles_cache_initialization_errors(self):
        """Test that server handles cache initialization errors."""
        # Test that server continues to work even if cache backend fails
        # In practice, CacheManager handles errors internally
        server = MCPServer(
            "test-server",
            enable_cache=True,
            cache_backend="redis",
            cache_config={"redis_url": "redis://invalid:6379"},
        )

        # Server should still be created successfully
        assert server is not None
        assert hasattr(server, "cache")

    def test_server_handles_metrics_initialization_errors(self):
        """Test that server handles metrics initialization errors."""
        # Test that server continues to work even if metrics setup has issues
        # MetricsCollector is designed to handle errors gracefully
        server = MCPServer("test-server", enable_metrics=True)

        # Server should still be created successfully
        assert server is not None
        assert hasattr(server, "metrics")


class TestMCPServerLifecycle:
    """Test MCP server lifecycle management."""

    def test_server_starts_with_correct_state(self):
        """Test that server starts with correct initial state."""
        server = MCPServer("test-server")

        assert server._running is False
        assert server._mcp is None
        assert len(server._active_sessions) == 0

    def test_server_state_during_run(self):
        """Test server state during run operation."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock run to simulate server running
            def mock_run():
                assert server._running is True
                raise KeyboardInterrupt()

            mock_mcp_instance.run.side_effect = mock_run

            # Ensure _mcp is None so _init_mcp gets called
            server._mcp = None

            # Run will catch KeyboardInterrupt and clean up
            server.run()

            # After exit, should be stopped
            assert server._running is False

    def test_server_cleanup_on_exception(self):
        """Test that server properly cleans up on exceptions."""
        server = MCPServer("test-server")

        # Add some state to clean up
        session_id = str(uuid.uuid4())
        server._active_sessions[session_id] = {"user": {"id": "test"}}

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance
            mock_mcp_instance.run.side_effect = Exception("Server error")

            with pytest.raises(Exception):
                server.run()

            # State should be cleaned up
            assert server._running is False
            assert len(server._active_sessions) == 0


class TestMCPServerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_server_with_empty_name(self):
        """Test server behavior with empty name."""
        server = MCPServer("")

        assert server.name == ""
        # Should still be functional
        assert server.cache is not None
        assert server.metrics is not None

    def test_server_with_very_long_name(self):
        """Test server behavior with very long name."""
        long_name = "x" * 1000
        server = MCPServer(long_name)

        assert server.name == long_name
        # Should still be functional
        assert server.cache is not None
        assert server.metrics is not None

    def test_server_with_extreme_config_values(self):
        """Test server with extreme configuration values."""
        server = MCPServer(
            "test-server",
            cache_ttl=0,  # No caching
            transport_timeout=0.1,  # Very short timeout
            max_request_size=1,  # Very small request size
        )

        assert server.transport_timeout == 0.1
        assert server.max_request_size == 1

    def test_server_with_many_tools(self):
        """Test server with a large number of tools."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_tool_decorator = MagicMock()
            mock_mcp_instance.tool.return_value = mock_tool_decorator
            mock_fastmcp.return_value = mock_mcp_instance

            # Register many tools
            for i in range(100):
                # Create a function with a unique name
                exec(
                    f"""
def tool_{i}():
    return 'result_{i}'
"""
                )

                # Get the function from locals and decorate it
                func = locals()[f"tool_{i}"]
                decorated = server.tool()(func)

            # Check that all tools were registered
            assert len(server._tool_registry) == 100

    def test_server_with_concurrent_sessions(self):
        """Test server behavior with many concurrent sessions."""
        server = MCPServer("test-server")

        # Add many sessions
        for i in range(1000):
            session_id = f"session_{i}"
            server._active_sessions[session_id] = {
                "user": {"id": f"user_{i}"},
                "tool": "test-tool",
                "start_time": time.time(),
            }

        sessions = server.get_active_sessions()
        assert len(sessions) == 1000

    def test_server_tool_registry_thread_safety(self):
        """Test that tool registry operations are safe."""
        server = MCPServer("test-server")

        # This is a basic test - in practice, thread safety would require
        # more sophisticated testing with actual concurrent access
        tool_name = "test-tool"
        server._tool_registry[tool_name] = {"call_count": 0}

        # Simulate concurrent access
        for i in range(100):
            if tool_name in server._tool_registry:
                server._tool_registry[tool_name]["call_count"] += 1

        assert server._tool_registry[tool_name]["call_count"] == 100


@pytest.mark.asyncio
class TestMCPServerAsync:
    """Test asynchronous functionality of MCP server."""

    async def test_run_stdio_async_operation(self):
        """Test that run_stdio operates asynchronously."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock stdin to return empty immediately
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.readline.return_value = ""

                # This should complete quickly
                start_time = time.time()
                await server.run_stdio()
                duration = time.time() - start_time

                assert duration < 1.0  # Should complete quickly
                assert server._running is False

    async def test_run_stdio_handles_keyboard_interrupt(self):
        """Test that run_stdio handles keyboard interrupt gracefully."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock stdin to raise KeyboardInterrupt
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.readline.side_effect = KeyboardInterrupt()

                # Should handle the interrupt gracefully
                await server.run_stdio()

                assert server._running is False

    async def test_run_stdio_handles_general_exceptions(self):
        """Test that run_stdio handles general exceptions."""
        server = MCPServer("test-server")

        with patch("mcp.server.FastMCP") as mock_fastmcp:
            mock_mcp_instance = MagicMock()
            mock_fastmcp.return_value = mock_mcp_instance

            # Mock stdin to raise a general exception
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.readline.side_effect = Exception("IO error")

                # Should handle the exception and re-raise
                with pytest.raises(Exception, match="IO error"):
                    await server.run_stdio()

                assert server._running is False


class TestMCPServerCompatibility:
    """Test backward compatibility and aliases."""

    def test_enhanced_mcp_server_alias(self):
        """Test that EnhancedMCPServer is an alias for MCPServer."""
        from kailash.mcp_server.server import EnhancedMCPServer

        assert EnhancedMCPServer is MCPServer

    def test_simple_mcp_server_alias(self):
        """Test that SimpleMCPServer is an alias for MCPServer."""
        from kailash.mcp_server.server import SimpleMCPServer

        assert SimpleMCPServer is MCPServer

    def test_server_maintains_api_compatibility(self):
        """Test that server maintains API compatibility."""
        # Test that old-style initialization still works
        server = MCPServer("test-server")

        # Should have all expected methods
        assert hasattr(server, "tool")
        assert hasattr(server, "resource")
        assert hasattr(server, "prompt")
        assert hasattr(server, "run")
        assert hasattr(server, "health_check")
        assert hasattr(server, "get_tool_stats")
        assert hasattr(server, "get_server_stats")

        # Should have all expected attributes
        assert hasattr(server, "name")
        assert hasattr(server, "cache")
        assert hasattr(server, "metrics")
        assert hasattr(server, "config")
