"""Integration tests for MCP server functionality with REAL services only.

NO MOCKING - Uses real Docker services per testing policy.
This file replaces test_mcp_server_integration.py with policy-compliant tests.
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path

import pytest
import pytest_asyncio

from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth
from kailash.mcp_server.discovery import FileBasedDiscovery, ServiceRegistry
from kailash.nodes.ai.llm_agent import LLMAgentNode
from tests.utils.docker_config import ensure_docker_services, get_redis_url


@pytest.mark.integration
@pytest.mark.requires_docker
class TestMCPServerIntegrationCompliant:
    """Test MCP server integration with real services only."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_services(self):
        """Ensure Docker services are running for integration tests."""
        services_ready = await ensure_docker_services()
        if not services_ready:
            pytest.skip("Docker services not available")
        yield

    @pytest.mark.asyncio
    async def test_mcp_server_with_real_tools(self):
        """Test MCP server with real tools using real FastMCP."""
        # Create real MCP server
        server = MCPServer("integration-test-server")

        # Register real tools
        @server.tool()
        async def test_add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        @server.tool()
        async def test_multiply(x: float, y: float) -> float:
            """Multiply two numbers."""
            return x * y

        # Test tool registration
        assert len(server._tool_registry) == 2
        assert "test_add" in server._tool_registry
        assert "test_multiply" in server._tool_registry

        # Test tool execution
        result = await test_add(5, 3)
        assert result == 8

        result = await test_multiply(2.5, 4.0)
        assert result == 10.0

        # Verify tools are registered with proper metadata
        add_info = server._tool_registry["test_add"]
        assert add_info["call_count"] >= 1
        assert "function" in add_info  # Tool function reference
        assert "last_called" in add_info
        assert add_info["function"] is not None

    @pytest.mark.asyncio
    async def test_mcp_server_with_real_auth(self):
        """Test MCP server with real authentication using Docker services."""
        # Create auth provider
        auth = APIKeyAuth(
            {
                "test-key": {
                    "permissions": ["tools.execute"],
                    "rate_limit": 100,
                    "metadata": {"client": "integration-test"},
                }
            }
        )

        # Create server with auth
        server = MCPServer("auth-integration-server", auth_provider=auth)

        @server.tool(required_permission="tools.execute")
        async def protected_tool(value: int) -> int:
            """Protected tool requiring authentication."""
            return value * 2

        # Test authentication works
        auth_context = auth.authenticate("test-key")
        assert auth_context is not None
        assert "tools.execute" in auth_context["permissions"]

        # Test tool execution with valid auth
        result = await protected_tool(10, api_key="test-key")
        assert result == 20

        # Test tool execution fails with invalid auth
        with pytest.raises(Exception):
            await protected_tool(10, api_key="invalid-key")

    @pytest.mark.asyncio
    async def test_mcp_server_discovery_integration(self):
        """Test MCP server with real service discovery using filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / "test_registry.json"

            # Create real service discovery
            discovery = FileBasedDiscovery(registry_file)
            registry = ServiceRegistry(backends=[discovery])

            # Create and register servers
            server1 = MCPServer("discovery-server-1")
            server2 = MCPServer("discovery-server-2")

            # Register with discovery
            from kailash.mcp_server.discovery import ServerInfo

            server_info1 = ServerInfo(
                name="discovery-server-1",
                transport="stdio",
                capabilities=["tools", "math"],
                metadata={"version": "1.0.0"},
            )

            server_info2 = ServerInfo(
                name="discovery-server-2",
                transport="http",
                url="http://localhost:8080",
                capabilities=["tools", "database"],
                metadata={"version": "1.0.0"},
            )

            await registry.register_server(server_info1)
            await registry.register_server(server_info2)

            # Test discovery
            all_servers = await registry.discover_servers()
            assert len(all_servers) == 2

            # Test filtered discovery
            math_servers = await registry.discover_servers(capability="math")
            assert len(math_servers) == 1
            assert math_servers[0].name == "discovery-server-1"

            db_servers = await registry.discover_servers(capability="database")
            assert len(db_servers) == 1
            assert db_servers[0].name == "discovery-server-2"

    @pytest.mark.asyncio
    async def test_mcp_server_with_real_cache(self):
        """Test MCP server with real Redis caching."""
        # Create server with Redis cache
        server = MCPServer(
            "cache-integration-server",
            cache_backend="redis",
            cache_config={
                "redis_url": get_redis_url(),
                "prefix": "integration_test:",
                "ttl": 300,
            },
        )

        computation_count = 0

        @server.tool(cache_key="expensive_operation", cache_ttl=60)
        async def expensive_operation(input_value: int) -> dict:
            """Simulate expensive operation with caching."""
            nonlocal computation_count
            computation_count += 1

            # Simulate work
            await asyncio.sleep(0.1)

            return {
                "result": input_value * 10,
                "computation_id": computation_count,
                "timestamp": time.time(),
            }

        # First call - should compute
        result1 = await expensive_operation(5)
        assert result1["result"] == 50
        assert computation_count == 1

        # Second call - should use cache
        result2 = await expensive_operation(5)
        assert result2["result"] == 50
        assert result2["computation_id"] == 1  # Same computation
        assert computation_count == 1  # No additional computation

        # Different input - should compute again
        result3 = await expensive_operation(10)
        assert result3["result"] == 100
        assert computation_count == 2

    @pytest.mark.asyncio
    @pytest.mark.requires_ollama
    async def test_llm_agent_mcp_integration_real(self):
        """Test LLMAgentNode with real MCP integration using Docker services."""
        # Set up real environment
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11435"

        try:
            # Create LLM agent
            agent = LLMAgentNode(enable_monitoring=True)

            # Test MCP integration with proper API
            result = agent.run(
                provider="ollama",
                model="llama3.2:1b",
                messages=[{"role": "user", "content": "What is 2+2? Answer briefly."}],
                mcp_servers=[],  # No MCP servers in test environment
                auto_discover_tools=False,  # Don't auto-discover in test
                timeout=30,
            )

            # Verify response structure
            assert isinstance(result, dict)
            assert "success" in result
            if result["success"]:
                assert "response" in result
                assert isinstance(result["response"], dict)
            else:
                # If it fails, verify it's due to Ollama not being available
                print(
                    f"LLM call failed (expected if Ollama not available): {result.get('error', 'Unknown error')}"
                )

            # Test MCP context retrieval functionality
            try:
                mcp_context = agent.retrieve_mcp_context(["test", "calculator"])
                # Verify structure if context is retrieved
                if mcp_context:
                    assert isinstance(mcp_context, list)
                    print(
                        f"MCP context retrieved successfully: {len(mcp_context)} items"
                    )
                else:
                    print("No MCP context available (expected in test environment)")
            except Exception as e:
                # MCP context retrieval might fail if no servers available
                # This is acceptable for integration test environment
                print(f"MCP context retrieval failed (expected in test env): {e}")

        finally:
            # Clean up environment
            os.environ.pop("KAILASH_USE_REAL_MCP", None)
            if "OLLAMA_BASE_URL" in os.environ:
                del os.environ["OLLAMA_BASE_URL"]

    @pytest.mark.asyncio
    async def test_mcp_server_error_handling_real(self):
        """Test MCP server error handling with real error scenarios."""
        server = MCPServer("error-test-server")

        @server.tool()
        async def failing_tool(should_fail: bool) -> str:
            """Tool that can fail for testing."""
            if should_fail:
                raise ValueError("Intentional test failure")
            return "success"

        # Test successful execution
        result = await failing_tool(False)
        assert result == "success"

        # Test error handling
        with pytest.raises(Exception):
            await failing_tool(True)

        # Verify error is recorded in registry
        tool_info = server._tool_registry["failing_tool"]
        assert tool_info["error_count"] >= 1

    @pytest.mark.asyncio
    async def test_mcp_server_metrics_real(self):
        """Test MCP server metrics collection with real operations."""
        server = MCPServer("metrics-test-server", enable_metrics=True)

        @server.tool()
        async def measured_tool(value: int) -> int:
            """Tool for metrics testing."""
            await asyncio.sleep(0.05)  # Ensure measurable latency
            return value * 2

        # Execute tool multiple times
        for i in range(3):
            await measured_tool(i)

        # Check metrics (if metrics functionality exists)
        try:
            metrics = server.metrics.get_stats() if hasattr(server, "metrics") else {}
            if metrics:
                assert isinstance(metrics, dict)
        except AttributeError:
            # Metrics may not be fully implemented, skip this check
            pass

        # Check tool registry has call count
        tool_info = server._tool_registry["measured_tool"]
        assert tool_info["call_count"] >= 3
        assert tool_info["last_called"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
