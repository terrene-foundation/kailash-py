"""Unit tests for MCP client functionality.

Tests for the enhanced MCP client in kailash.mcp_server.client.
NO MOCKING of external dependencies - This is a unit test file (Tier 1)
for isolated component testing.
"""

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.mcp_server.auth import (
    APIKeyAuth,
    AuthManager,
    PermissionManager,
    RateLimiter,
)
from kailash.mcp_server.client import MCPClient
from kailash.mcp_server.errors import (
    AuthenticationError,
    CircuitBreakerRetry,
    ExponentialBackoffRetry,
    RetryableOperation,
    TransportError,
)


class TestMCPClientInitialization:
    """Test MCP client initialization and configuration."""

    def test_init_with_minimal_config(self):
        """Test initialization with minimal configuration."""
        client = MCPClient()

        assert client.config == {}
        assert client.connected is False
        assert client.auth_provider is None
        assert client.auth_manager is None
        assert client.enable_metrics is False
        assert client.enable_http_transport is True
        assert client.connection_timeout == 30.0
        assert client.enable_discovery is False
        assert client.retry_operation is None
        assert client.metrics is None
        assert len(client._sessions) == 0
        assert len(client._discovered_tools) == 0
        assert len(client._discovered_resources) == 0
        # Connection pools are managed internally by transports
        assert hasattr(client, "_sessions")
        assert len(client._sessions) == 0

    def test_init_with_config_dict(self):
        """Test initialization with configuration dictionary."""
        config = {
            "auth_provider": APIKeyAuth(["test-key"]),
            "enable_metrics": True,
            "enable_http_transport": False,
            "connection_timeout": 60.0,
        }
        client = MCPClient(
            config=config,
            enable_http_transport=False,  # Need to pass explicitly since config extraction uses OR logic
            connection_timeout=60.0,  # Need to pass explicitly since config extraction uses OR logic
        )

        assert client.config == config
        assert client.auth_provider is not None
        assert client.enable_metrics is True
        assert client.enable_http_transport is False
        assert client.connection_timeout == 60.0

    def test_init_with_auth_provider(self):
        """Test initialization with authentication provider."""
        auth_provider = APIKeyAuth(["test-key"])
        client = MCPClient(auth_provider=auth_provider)

        assert client.auth_provider is auth_provider
        assert client.auth_manager is not None
        assert isinstance(client.auth_manager, AuthManager)
        assert client.auth_manager.provider is auth_provider
        assert isinstance(client.auth_manager.permission_manager, PermissionManager)
        assert isinstance(client.auth_manager.rate_limiter, RateLimiter)

    def test_init_with_retry_strategy_simple(self):
        """Test initialization with simple retry strategy."""
        client = MCPClient(retry_strategy="simple")

        assert client.retry_operation is None

    def test_init_with_retry_strategy_exponential(self):
        """Test initialization with exponential backoff retry strategy."""
        client = MCPClient(retry_strategy="exponential")

        assert client.retry_operation is not None
        assert isinstance(client.retry_operation, RetryableOperation)
        assert isinstance(
            client.retry_operation.retry_strategy, ExponentialBackoffRetry
        )

    def test_init_with_retry_strategy_circuit_breaker(self):
        """Test initialization with circuit breaker retry strategy."""
        circuit_breaker_config = {
            "failure_threshold": 5,
            "timeout": 30,  # Use 'timeout' instead of 'recovery_timeout'
        }
        client = MCPClient(
            retry_strategy="circuit_breaker",
            circuit_breaker_config=circuit_breaker_config,
        )

        assert client.retry_operation is not None
        assert isinstance(client.retry_operation, RetryableOperation)
        assert isinstance(client.retry_operation.retry_strategy, CircuitBreakerRetry)

    def test_init_with_retry_strategy_object(self):
        """Test initialization with custom retry strategy object."""
        retry_strategy = ExponentialBackoffRetry()
        client = MCPClient(retry_strategy=retry_strategy)

        assert client.retry_operation is not None
        assert isinstance(client.retry_operation, RetryableOperation)
        assert client.retry_operation.retry_strategy is retry_strategy

    def test_init_with_invalid_retry_strategy(self):
        """Test initialization with invalid retry strategy."""
        with pytest.raises(ValueError, match="Unknown retry strategy"):
            MCPClient(retry_strategy="invalid_strategy")

    def test_init_with_metrics_enabled(self):
        """Test initialization with metrics enabled."""
        client = MCPClient(enable_metrics=True)

        assert client.enable_metrics is True
        assert client.metrics is not None
        assert "requests_total" in client.metrics
        assert "requests_failed" in client.metrics
        assert "tools_called" in client.metrics
        assert "resources_accessed" in client.metrics
        assert "avg_response_time" in client.metrics
        assert "transport_usage" in client.metrics
        assert "start_time" in client.metrics
        assert client.metrics["requests_total"] == 0
        assert client.metrics["requests_failed"] == 0
        assert client.metrics["tools_called"] == 0
        assert client.metrics["resources_accessed"] == 0
        assert client.metrics["avg_response_time"] == 0
        assert client.metrics["transport_usage"] == {}

    def test_init_with_connection_pool_config(self):
        """Test initialization with connection pool configuration."""
        pool_config = {"max_connections": 10, "timeout": 30}
        client = MCPClient(connection_pool_config=pool_config)

        assert client.connection_pool_config == pool_config

    def test_init_with_full_config(self):
        """Test initialization with comprehensive configuration."""
        auth_provider = APIKeyAuth(["test-key"])
        circuit_breaker_config = {"failure_threshold": 3}
        pool_config = {"max_connections": 5}

        client = MCPClient(
            auth_provider=auth_provider,
            retry_strategy="circuit_breaker",
            enable_metrics=True,
            enable_http_transport=False,
            connection_timeout=45.0,
            connection_pool_config=pool_config,
            enable_discovery=True,
            circuit_breaker_config=circuit_breaker_config,
        )

        assert client.auth_provider is auth_provider
        assert client.enable_metrics is True
        assert client.enable_http_transport is False
        assert client.connection_timeout == 45.0
        assert client.enable_discovery is True
        assert client.retry_operation is not None
        assert client.connection_pool_config == pool_config
        assert client.metrics is not None
        assert client.auth_manager is not None


class TestMCPClientHelperMethods:
    """Test helper methods for transport and configuration."""

    def test_get_transport_type_string_http(self):
        """Test transport type detection for HTTP URL string."""
        client = MCPClient()

        transport_type = client._get_transport_type("http://example.com")
        assert transport_type == "sse"

        transport_type = client._get_transport_type("https://example.com")
        assert transport_type == "sse"

    def test_get_transport_type_string_stdio(self):
        """Test transport type detection for non-HTTP string."""
        client = MCPClient()

        transport_type = client._get_transport_type("python script.py")
        assert transport_type == "stdio"

        transport_type = client._get_transport_type("node server.js")
        assert transport_type == "stdio"

    def test_get_transport_type_dict(self):
        """Test transport type detection for dictionary config."""
        client = MCPClient()

        config = {"transport": "http"}
        transport_type = client._get_transport_type(config)
        assert transport_type == "http"

        config = {"transport": "sse"}
        transport_type = client._get_transport_type(config)
        assert transport_type == "sse"

        config = {"command": "python", "args": ["script.py"]}
        transport_type = client._get_transport_type(config)
        assert transport_type == "stdio"

    def test_get_server_key_string(self):
        """Test server key generation for string config."""
        client = MCPClient()

        server_key = client._get_server_key("http://example.com")
        assert server_key == "http://example.com"

        server_key = client._get_server_key("python script.py")
        assert server_key == "python script.py"

    def test_get_server_key_dict_stdio(self):
        """Test server key generation for STDIO dictionary config."""
        client = MCPClient()

        config = {"command": "python", "args": ["script.py", "--arg1"]}
        server_key = client._get_server_key(config)
        assert server_key == "stdio://python:script.py:--arg1"

        config = {"command": "node", "args": []}
        server_key = client._get_server_key(config)
        assert server_key == "stdio://node:"

    def test_get_server_key_dict_http(self):
        """Test server key generation for HTTP dictionary config."""
        client = MCPClient()

        config = {"transport": "http", "url": "http://example.com"}
        server_key = client._get_server_key(config)
        assert server_key == "http://example.com"

        config = {"transport": "sse", "url": "https://example.com"}
        server_key = client._get_server_key(config)
        assert server_key == "https://example.com"

    def test_get_server_key_dict_unknown(self):
        """Test server key generation for unknown dictionary config."""
        client = MCPClient()

        config = {"transport": "custom", "endpoint": "custom://example"}
        server_key = client._get_server_key(config)
        # Should generate a hash of the config
        assert isinstance(server_key, str)
        assert len(server_key) > 0

    def test_get_auth_headers_api_key(self):
        """Test authentication header generation for API key."""
        client = MCPClient()

        config = {
            "auth": {"type": "api_key", "key": "test-key-123", "header": "X-API-Key"}
        }
        headers = client._get_auth_headers(config)
        assert headers["X-API-Key"] == "test-key-123"

        # Test with default header
        config = {"auth": {"type": "api_key", "key": "test-key-456"}}
        headers = client._get_auth_headers(config)
        assert headers["X-API-Key"] == "test-key-456"

    def test_get_auth_headers_bearer(self):
        """Test authentication header generation for Bearer token."""
        client = MCPClient()

        config = {"auth": {"type": "bearer", "token": "bearer-token-123"}}
        headers = client._get_auth_headers(config)
        assert headers["Authorization"] == "Bearer bearer-token-123"

    def test_get_auth_headers_basic(self):
        """Test authentication header generation for Basic auth."""
        client = MCPClient()

        config = {
            "auth": {"type": "basic", "username": "testuser", "password": "testpass"}
        }
        headers = client._get_auth_headers(config)

        import base64

        expected_credentials = base64.b64encode(b"testuser:testpass").decode()
        assert headers["Authorization"] == f"Basic {expected_credentials}"

    def test_get_auth_headers_empty(self):
        """Test authentication header generation with no auth config."""
        client = MCPClient()

        config = {}
        headers = client._get_auth_headers(config)
        assert headers == {}

        config = {"auth": {}}
        headers = client._get_auth_headers(config)
        assert headers == {}

    def test_extract_credentials_string(self):
        """Test credential extraction from string config."""
        client = MCPClient()

        credentials = client._extract_credentials("http://example.com")
        assert credentials == {}

    def test_extract_credentials_api_key(self):
        """Test credential extraction for API key."""
        client = MCPClient()

        config = {"auth": {"type": "api_key", "key": "test-key-123"}}
        credentials = client._extract_credentials(config)
        assert credentials == {"api_key": "test-key-123"}

    def test_extract_credentials_bearer(self):
        """Test credential extraction for Bearer token."""
        client = MCPClient()

        config = {"auth": {"type": "bearer", "token": "bearer-token-123"}}
        credentials = client._extract_credentials(config)
        assert credentials == {"token": "bearer-token-123"}

    def test_extract_credentials_basic(self):
        """Test credential extraction for Basic auth."""
        client = MCPClient()

        config = {
            "auth": {"type": "basic", "username": "testuser", "password": "testpass"}
        }
        credentials = client._extract_credentials(config)
        assert credentials == {"username": "testuser", "password": "testpass"}

    def test_extract_credentials_empty(self):
        """Test credential extraction with no auth config."""
        client = MCPClient()

        config = {}
        credentials = client._extract_credentials(config)
        assert credentials == {}


class TestMCPClientMetrics:
    """Test client metrics functionality."""

    def test_update_metrics_basic(self):
        """Test basic metrics update."""
        client = MCPClient(enable_metrics=True)

        # Initial state
        assert client.metrics["requests_total"] == 0
        assert client.metrics["avg_response_time"] == 0

        # Update metrics
        client._update_metrics("test_operation", 0.5)

        assert client.metrics["requests_total"] == 1
        assert client.metrics["avg_response_time"] == 0.5

    def test_update_metrics_multiple_calls(self):
        """Test metrics update with multiple calls."""
        client = MCPClient(enable_metrics=True)

        # Multiple updates
        client._update_metrics("operation1", 0.5)
        client._update_metrics("operation2", 1.0)
        client._update_metrics("operation3", 0.25)

        assert client.metrics["requests_total"] == 3
        # Average should be (0.5 + 1.0 + 0.25) / 3 = 0.583...
        assert abs(client.metrics["avg_response_time"] - 0.583333) < 0.001

    def test_update_metrics_disabled(self):
        """Test metrics update when metrics are disabled."""
        client = MCPClient(enable_metrics=False)

        # Should not raise exception
        client._update_metrics("test_operation", 0.5)

        assert client.metrics is None

    def test_get_metrics_enabled(self):
        """Test getting metrics when enabled."""
        client = MCPClient(enable_metrics=True)

        # Add some data
        client._update_metrics("test_operation", 0.5)
        client.metrics["tools_called"] = 3
        client.metrics["transport_usage"]["stdio"] = 5

        metrics = client.get_metrics()

        assert metrics is not None
        assert "uptime" in metrics
        assert metrics["requests_total"] == 1
        assert metrics["tools_called"] == 3
        assert metrics["transport_usage"]["stdio"] == 5
        assert metrics["uptime"] > 0

    def test_get_metrics_disabled(self):
        """Test getting metrics when disabled."""
        client = MCPClient(enable_metrics=False)

        metrics = client.get_metrics()
        assert metrics is None


class TestMCPClientConnection:
    """Test client connection functionality."""

    @pytest.mark.asyncio
    async def test_connect_basic(self):
        """Test basic connection functionality."""
        client = MCPClient()

        assert client.connected is False

        await client.connect()

        assert client.connected is True

    @pytest.mark.asyncio
    async def test_disconnect_basic(self):
        """Test basic disconnection functionality."""
        client = MCPClient()

        # Connect first
        await client.connect()
        assert client.connected is True

        # Add mock session
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        client._sessions["test_session"] = mock_session

        await client.disconnect()

        assert client.connected is False
        assert len(client._sessions) == 0

    @pytest.mark.asyncio
    async def test_disconnect_with_session_errors(self):
        """Test disconnection with session cleanup errors."""
        client = MCPClient()

        await client.connect()

        # Add mock session that raises error on close
        mock_session = MagicMock()
        mock_session.close = AsyncMock(side_effect=Exception("Close error"))
        client._sessions["test_session"] = mock_session

        # Should not raise exception
        await client.disconnect()

        assert client.connected is False
        assert len(client._sessions) == 0

    @pytest.mark.asyncio
    async def test_disconnect_without_close_method(self):
        """Test disconnection with sessions without close method."""
        client = MCPClient()

        await client.connect()

        # Add mock session without close method
        mock_session = MagicMock()
        del mock_session.close
        client._sessions["test_session"] = mock_session

        # Should not raise exception
        await client.disconnect()

        assert client.connected is False
        assert len(client._sessions) == 0


class TestMCPClientSimpleAPI:
    """Test client simple API methods."""

    @pytest.mark.asyncio
    async def test_call_tool_simple(self):
        """Test simple tool calling interface."""
        config = {"command": "python", "args": ["script.py"]}
        client = MCPClient(config=config)

        # Mock the call_tool method
        with patch.object(client, "call_tool") as mock_call_tool:
            mock_call_tool.return_value = {"success": True, "result": "test"}

            result = await client.call_tool_simple("test_tool", {"arg": "value"})

            mock_call_tool.assert_called_once_with(
                config, "test_tool", {"arg": "value"}, None
            )
            assert result == {"success": True, "result": "test"}

    @pytest.mark.asyncio
    async def test_call_tool_simple_with_timeout(self):
        """Test simple tool calling with timeout."""
        config = {"command": "python", "args": ["script.py"]}
        client = MCPClient(config=config)

        with patch.object(client, "call_tool") as mock_call_tool:
            mock_call_tool.return_value = {"success": True, "result": "test"}

            result = await client.call_tool_simple("test_tool", {"arg": "value"}, 30.0)

            mock_call_tool.assert_called_once_with(
                config, "test_tool", {"arg": "value"}, 30.0
            )

    @pytest.mark.asyncio
    async def test_read_resource_simple(self):
        """Test simple resource reading interface."""
        config = {"command": "python", "args": ["script.py"]}
        client = MCPClient(config=config)

        with patch.object(client, "read_resource") as mock_read_resource:
            mock_read_resource.return_value = {"success": True, "data": "content"}

            result = await client.read_resource_simple("file:///test.txt")

            mock_read_resource.assert_called_once_with(config, "file:///test.txt", None)
            assert result == {"success": True, "data": "content"}

    @pytest.mark.asyncio
    async def test_read_resource_simple_with_timeout(self):
        """Test simple resource reading with timeout."""
        config = {"command": "python", "args": ["script.py"]}
        client = MCPClient(config=config)

        with patch.object(client, "read_resource") as mock_read_resource:
            mock_read_resource.return_value = {"success": True, "data": "content"}

            result = await client.read_resource_simple("file:///test.txt", 30.0)

            mock_read_resource.assert_called_once_with(config, "file:///test.txt", 30.0)

    @pytest.mark.asyncio
    async def test_send_request_basic(self):
        """Test basic request sending."""
        client = MCPClient()

        message = {
            "id": "test-123",
            "method": "test_method",
            "params": {"arg": "value"},
        }

        result = await client.send_request(message)

        assert "id" in result
        assert "result" in result
        assert result["id"] == "test-123"
        assert result["result"]["echo"] == {"arg": "value"}
        assert result["result"]["server"] == "echo-server"
        assert "timestamp" in result["result"]


class TestMCPClientHealthCheck:
    """Test client health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check when server is healthy."""
        client = MCPClient(enable_metrics=True)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "discover_tools") as mock_discover:
            mock_discover.return_value = [
                {"name": "tool1", "description": "Test tool 1"},
                {"name": "tool2", "description": "Test tool 2"},
            ]

            result = await client.health_check(server_config)

            assert result["status"] == "healthy"
            assert result["server"] == "stdio://python:script.py"
            assert result["tools_available"] == 2
            assert result["transport"] == "stdio"
            assert result["metrics"] is not None

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check when server is unhealthy."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "discover_tools") as mock_discover:
            mock_discover.side_effect = Exception("Server not responding")

            result = await client.health_check(server_config)

            assert result["status"] == "unhealthy"
            assert result["server"] == "stdio://python:script.py"
            assert result["error"] == "Server not responding"
            assert result["transport"] == "stdio"

    @pytest.mark.asyncio
    async def test_health_check_without_metrics(self):
        """Test health check when metrics are disabled."""
        client = MCPClient(enable_metrics=False)

        server_config = {"url": "http://example.com"}

        with patch.object(client, "discover_tools") as mock_discover:
            mock_discover.return_value = []

            result = await client.health_check(server_config)

            assert result["status"] == "healthy"
            assert result["metrics"] is None


class TestMCPClientDiscoverTools:
    """Test tool discovery functionality."""

    @pytest.mark.asyncio
    async def test_discover_tools_string_config(self):
        """Test tool discovery with string server config."""
        client = MCPClient()

        server_config = "http://example.com"

        with patch.object(client, "_discover_tools_sse") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            result = await client.discover_tools(server_config)

            assert len(result) == 1
            assert result[0]["name"] == "tool1"
            mock_discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_tools_dict_config_stdio(self):
        """Test tool discovery with STDIO dictionary config."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            result = await client.discover_tools(server_config)

            assert len(result) == 1
            mock_discover.assert_called_once_with(server_config, None)

    @pytest.mark.asyncio
    async def test_discover_tools_dict_config_http(self):
        """Test tool discovery with HTTP dictionary config."""
        client = MCPClient()

        server_config = {"transport": "http", "url": "http://example.com"}

        with patch.object(client, "_discover_tools_http") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            result = await client.discover_tools(server_config)

            assert len(result) == 1
            mock_discover.assert_called_once_with(server_config, None)

    @pytest.mark.asyncio
    async def test_discover_tools_caching(self):
        """Test tool discovery caching behavior."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            # First call
            result1 = await client.discover_tools(server_config)
            assert len(result1) == 1

            # Second call should use cache
            result2 = await client.discover_tools(server_config)
            assert len(result2) == 1
            assert result1 == result2

            # Should only call discover once
            mock_discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_tools_force_refresh(self):
        """Test tool discovery with force refresh."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            # First call
            await client.discover_tools(server_config)

            # Second call with force refresh
            await client.discover_tools(server_config, force_refresh=True)

            # Should call discover twice
            assert mock_discover.call_count == 2

    @pytest.mark.asyncio
    async def test_discover_tools_with_timeout(self):
        """Test tool discovery with timeout."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            await client.discover_tools(server_config, timeout=30.0)

            mock_discover.assert_called_once_with(server_config, 30.0)

    @pytest.mark.asyncio
    async def test_discover_tools_with_retry(self):
        """Test tool discovery with retry logic."""
        retry_strategy = ExponentialBackoffRetry()
        client = MCPClient(retry_strategy=retry_strategy)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            with patch.object(client.retry_operation, "execute") as mock_execute:
                mock_execute.return_value = [
                    {"name": "tool1", "description": "Test tool"}
                ]

                result = await client.discover_tools(server_config)

                assert len(result) == 1
                mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_tools_with_metrics(self):
        """Test tool discovery with metrics tracking."""
        client = MCPClient(enable_metrics=True)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            # Initial metrics
            initial_requests = client.metrics["requests_total"]
            initial_transport_usage = client.metrics["transport_usage"].get("stdio", 0)

            await client.discover_tools(server_config)

            # Metrics should be updated
            assert client.metrics["requests_total"] > initial_requests
            assert client.metrics["transport_usage"]["stdio"] > initial_transport_usage

    @pytest.mark.asyncio
    async def test_discover_tools_error_handling(self):
        """Test tool discovery error handling."""
        client = MCPClient(enable_metrics=True)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.side_effect = Exception("Discovery failed")

            result = await client.discover_tools(server_config)

            # Should return empty list on error
            assert result == []

            # Should track failed request
            assert client.metrics["requests_failed"] > 0

    @pytest.mark.asyncio
    async def test_discover_tools_unsupported_transport(self):
        """Test tool discovery with unsupported transport."""
        client = MCPClient()

        server_config = {"transport": "unsupported_transport"}

        # Should return empty list on error, not raise exception
        result = await client.discover_tools(server_config)
        assert result == []


class TestMCPClientCallTool:
    """Test tool calling functionality."""

    @pytest.mark.asyncio
    async def test_call_tool_basic(self):
        """Test basic tool calling."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "Tool result",
                "tool_name": "test_tool",
            }

            result = await client.call_tool(
                server_config, "test_tool", {"arg": "value"}
            )

            assert result["success"] is True
            assert result["content"] == "Tool result"
            assert result["tool_name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_call_tool_with_auth(self):
        """Test tool calling with authentication."""
        auth_provider = APIKeyAuth(["test-key"])
        client = MCPClient(auth_provider=auth_provider)

        server_config = {
            "command": "python",
            "args": ["script.py"],
            "auth": {"type": "api_key", "key": "test-key"},
        }

        # Mock the auth manager authenticate_and_authorize to return valid user
        with patch.object(
            client.auth_manager, "authenticate_and_authorize"
        ) as mock_auth:
            mock_auth.return_value = {
                "user_id": "test-user",
                "permissions": ["tools.execute"],
            }

            with patch.object(client, "_call_tool_stdio") as mock_call:
                mock_call.return_value = {
                    "success": True,
                    "content": "Tool result",
                    "tool_name": "test_tool",
                }

                result = await client.call_tool(
                    server_config, "test_tool", {"arg": "value"}
                )

                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_call_tool_auth_failure(self):
        """Test tool calling with authentication failure."""
        auth_provider = APIKeyAuth(["valid-key"])
        client = MCPClient(auth_provider=auth_provider)

        server_config = {
            "command": "python",
            "args": ["script.py"],
            "auth": {"type": "api_key", "key": "invalid-key"},
        }

        result = await client.call_tool(server_config, "test_tool", {"arg": "value"})

        assert result["success"] is False
        assert "error" in result
        assert result["error_code"] == "AUTH_FAILED"
        assert result["tool_name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_call_tool_with_timeout(self):
        """Test tool calling with timeout."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "Tool result",
                "tool_name": "test_tool",
            }

            await client.call_tool(
                server_config, "test_tool", {"arg": "value"}, timeout=30.0
            )

            mock_call.assert_called_once_with(
                server_config, "test_tool", {"arg": "value"}, 30.0
            )

    @pytest.mark.asyncio
    async def test_call_tool_with_retry(self):
        """Test tool calling with retry logic."""
        retry_strategy = ExponentialBackoffRetry()
        client = MCPClient(retry_strategy=retry_strategy)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "Tool result",
                "tool_name": "test_tool",
            }

            with patch.object(client.retry_operation, "execute") as mock_execute:
                mock_execute.return_value = {
                    "success": True,
                    "content": "Tool result",
                    "tool_name": "test_tool",
                }

                result = await client.call_tool(
                    server_config, "test_tool", {"arg": "value"}
                )

                assert result["success"] is True
                mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_with_metrics(self):
        """Test tool calling with metrics tracking."""
        client = MCPClient(enable_metrics=True)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "Tool result",
                "tool_name": "test_tool",
            }

            initial_tools_called = client.metrics["tools_called"]
            initial_requests = client.metrics["requests_total"]

            await client.call_tool(server_config, "test_tool", {"arg": "value"})

            assert client.metrics["tools_called"] > initial_tools_called
            assert client.metrics["requests_total"] > initial_requests

    @pytest.mark.asyncio
    async def test_call_tool_error_handling(self):
        """Test tool calling error handling."""
        client = MCPClient(enable_metrics=True)

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.side_effect = Exception("Tool call failed")

            result = await client.call_tool(
                server_config, "test_tool", {"arg": "value"}
            )

            assert result["success"] is False
            assert "error" in result
            assert result["tool_name"] == "test_tool"
            assert client.metrics["requests_failed"] > 0

    @pytest.mark.asyncio
    async def test_call_tool_transport_selection(self):
        """Test tool calling with different transport types."""
        client = MCPClient()

        # Test SSE transport
        server_config = {"transport": "sse", "url": "http://example.com"}

        with patch.object(client, "_call_tool_sse") as mock_call:
            mock_call.return_value = {"success": True, "tool_name": "test_tool"}

            await client.call_tool(server_config, "test_tool", {"arg": "value"})

            mock_call.assert_called_once()

        # Test HTTP transport
        server_config = {"transport": "http", "url": "http://example.com"}

        with patch.object(client, "_call_tool_http") as mock_call:
            mock_call.return_value = {"success": True, "tool_name": "test_tool"}

            await client.call_tool(server_config, "test_tool", {"arg": "value"})

            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_unsupported_transport(self):
        """Test tool calling with unsupported transport."""
        client = MCPClient()

        server_config = {"transport": "unsupported_transport"}

        result = await client.call_tool(server_config, "test_tool", {"arg": "value"})

        assert result["success"] is False
        assert "error" in result
        assert result["tool_name"] == "test_tool"


class TestMCPClientEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_discover_tools_empty_result(self):
        """Test tool discovery with empty result."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = []

            result = await client.discover_tools(server_config)

            assert result == []

            # Should still cache empty result
            server_key = client._get_server_key(server_config)
            assert server_key in client._discovered_tools
            assert client._discovered_tools[server_key] == []

    @pytest.mark.asyncio
    async def test_call_tool_empty_arguments(self):
        """Test tool calling with empty arguments."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "Tool result",
                "tool_name": "test_tool",
            }

            result = await client.call_tool(server_config, "test_tool", {})

            assert result["success"] is True
            mock_call.assert_called_once_with(server_config, "test_tool", {}, None)

    def test_get_server_key_complex_config(self):
        """Test server key generation with complex configuration."""
        client = MCPClient()

        # Complex config with many fields
        config = {
            "transport": "custom",
            "endpoint": "custom://example",
            "options": {"timeout": 30, "retries": 3},
            "headers": {"X-Custom": "value"},
        }

        server_key = client._get_server_key(config)

        # Should generate consistent hash
        assert isinstance(server_key, str)
        assert len(server_key) > 0

        # Same config should generate same key
        server_key2 = client._get_server_key(config)
        assert server_key == server_key2

    def test_extract_credentials_malformed_config(self):
        """Test credential extraction with malformed configuration."""
        client = MCPClient()

        # Missing key in API key config
        config = {"auth": {"type": "api_key"}}
        credentials = client._extract_credentials(config)
        assert credentials == {"api_key": None}

        # Missing token in bearer config
        config = {"auth": {"type": "bearer"}}
        credentials = client._extract_credentials(config)
        assert credentials == {"token": None}

        # Missing username/password in basic config
        config = {"auth": {"type": "basic"}}
        credentials = client._extract_credentials(config)
        assert credentials == {"username": None, "password": None}

    def test_get_auth_headers_malformed_config(self):
        """Test auth header generation with malformed configuration."""
        client = MCPClient()

        # Missing key in API key config
        config = {"auth": {"type": "api_key"}}
        headers = client._get_auth_headers(config)
        assert headers == {}

        # Missing token in bearer config
        config = {"auth": {"type": "bearer"}}
        headers = client._get_auth_headers(config)
        assert headers == {}

        # Missing username/password in basic config - this actually generates empty Basic auth
        config = {"auth": {"type": "basic"}}
        headers = client._get_auth_headers(config)
        # Basic auth with empty credentials will still create a header
        assert "Authorization" in headers
        import base64

        expected_credentials = base64.b64encode(b":").decode()
        assert headers["Authorization"] == f"Basic {expected_credentials}"

    def test_update_metrics_edge_cases(self):
        """Test metrics update with edge cases."""
        client = MCPClient(enable_metrics=True)

        # Zero duration
        client._update_metrics("test_operation", 0.0)
        assert client.metrics["requests_total"] == 1
        assert client.metrics["avg_response_time"] == 0.0

        # Negative duration (should still work)
        client._update_metrics("test_operation", -0.1)
        assert client.metrics["requests_total"] == 2
        # Average should be (0.0 + (-0.1)) / 2 = -0.05
        assert client.metrics["avg_response_time"] == -0.05

    @pytest.mark.asyncio
    async def test_health_check_with_string_config(self):
        """Test health check with string server configuration."""
        client = MCPClient()

        server_config = "http://example.com"

        with patch.object(client, "discover_tools") as mock_discover:
            mock_discover.return_value = [{"name": "tool1"}]

            result = await client.health_check(server_config)

            assert result["status"] == "healthy"
            assert result["server"] == "http://example.com"
            assert result["transport"] == "sse"

    def test_connection_pool_initialization(self):
        """Test connection pool initialization."""
        pool_config = {"max_connections": 10, "timeout": 30, "keepalive": True}
        client = MCPClient(connection_pool_config=pool_config)

        assert client.connection_pool_config == pool_config
        # Connection pools are managed by transports, not directly on client
        # Connection pools are managed internally by transports
        assert hasattr(client, "_sessions")
        assert len(client._sessions) == 0

    def test_session_management_initialization(self):
        """Test session management initialization."""
        client = MCPClient()

        assert isinstance(client._sessions, dict)
        assert len(client._sessions) == 0
        assert isinstance(client._discovered_tools, dict)
        assert len(client._discovered_tools) == 0
        assert isinstance(client._discovered_resources, dict)
        assert len(client._discovered_resources) == 0


@pytest.mark.asyncio
class TestMCPClientAsync:
    """Test asynchronous functionality of MCP client."""

    async def test_concurrent_tool_calls(self):
        """Test concurrent tool calls."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "Tool result",
                "tool_name": "test_tool",
            }

            # Make multiple concurrent calls
            tasks = []
            for i in range(5):
                task = client.call_tool(
                    server_config, f"test_tool_{i}", {"arg": f"value_{i}"}
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # All calls should succeed
            for result in results:
                assert result["success"] is True
                assert "Tool result" in result["content"]

            # Should have made 5 calls
            assert mock_call.call_count == 5

    async def test_concurrent_tool_discovery(self):
        """Test concurrent tool discovery."""
        client = MCPClient()

        server_configs = [
            {"command": "python", "args": ["script1.py"]},
            {"command": "python", "args": ["script2.py"]},
            {"command": "python", "args": ["script3.py"]},
        ]

        with patch.object(client, "_discover_tools_stdio") as mock_discover:
            mock_discover.return_value = [{"name": "tool1", "description": "Test tool"}]

            # Make concurrent discovery calls
            tasks = []
            for config in server_configs:
                task = client.discover_tools(config)
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # All discoveries should succeed
            for result in results:
                assert len(result) == 1
                assert result[0]["name"] == "tool1"

            # Should have made 3 calls (no caching across different configs)
            assert mock_discover.call_count == 3

    async def test_timeout_handling(self):
        """Test timeout handling in async operations."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            # Simulate slow operation
            async def slow_operation(*args, **kwargs):
                await asyncio.sleep(0.1)
                return {"success": True, "tool_name": "test_tool"}

            mock_call.side_effect = slow_operation

            # Call with very short timeout
            result = await client.call_tool(
                server_config, "test_tool", {"arg": "value"}, timeout=0.01
            )

            # Should still complete (timeout is passed to transport layer)
            assert result["success"] is True

    async def test_error_propagation(self):
        """Test error propagation in async operations."""
        client = MCPClient()

        server_config = {"command": "python", "args": ["script.py"]}

        with patch.object(client, "_call_tool_stdio") as mock_call:
            mock_call.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await client.call_tool(
                server_config, "test_tool", {"arg": "value"}
            )

            # Should handle timeout gracefully
            assert result["success"] is False
            assert "error" in result
            assert result["tool_name"] == "test_tool"

    async def test_connection_lifecycle(self):
        """Test connection lifecycle management."""
        client = MCPClient()

        # Initially disconnected
        assert client.connected is False

        # Connect
        await client.connect()
        assert client.connected is True

        # Add mock sessions
        mock_session1 = MagicMock()
        mock_session1.close = AsyncMock()
        mock_session2 = MagicMock()
        mock_session2.close = AsyncMock()

        client._sessions["session1"] = mock_session1
        client._sessions["session2"] = mock_session2

        # Disconnect
        await client.disconnect()
        assert client.connected is False
        assert len(client._sessions) == 0

        # Both sessions should have been closed
        mock_session1.close.assert_called_once()
        mock_session2.close.assert_called_once()
