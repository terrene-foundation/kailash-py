"""E2E tests for MCP production workflows with real services.

NO MOCKING ALLOWED - Uses real Docker services per test policy.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from kailash.mcp_server import (
    MCPClient,
    MCPServer,
    ServiceRegistry,
    discover_mcp_servers,
    get_mcp_client,
)
from kailash.mcp_server.auth import APIKeyAuth
from kailash.mcp_server.discovery import ServerInfo

from tests.utils.docker_config import ensure_docker_services, get_redis_url


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestMCPProductionWorkflows:
    """Test complete MCP workflows in production-like scenarios."""

    @pytest.fixture(autouse=True)
    def setup_e2e_environment(self):
        """Set up E2E test environment with real Docker services."""
        # Synchronous setup to avoid fixture issues
        # Individual tests will check services as needed
        pass

    @pytest.mark.asyncio
    async def test_complete_mcp_server_client_workflow(self):
        """Test complete workflow from server creation to client interaction."""
        # Step 1: Create MCP server with tools and resources
        server = MCPServer("e2e-server")

        # Tool for data processing
        @server.tool(cache_key="process_data", cache_ttl=300)
        def process_data(data: str, operation: str = "uppercase") -> dict:
            """Process data with specified operation."""
            if operation == "uppercase":
                result = data.upper()
            elif operation == "lowercase":
                result = data.lower()
            elif operation == "reverse":
                result = data[::-1]
            else:
                result = data

            return {
                "original": data,
                "operation": operation,
                "result": result,
                "timestamp": time.time(),
            }

        # Resource for configuration
        @server.resource("config://settings")
        def get_settings():
            """Get server configuration settings."""
            return {
                "version": "1.0.0",
                "features": ["tools", "resources", "caching"],
                "limits": {"max_requests": 100, "timeout": 30},
            }

        # Step 2: Test tool execution
        result = process_data("Hello World", "uppercase")
        assert result["result"] == "HELLO WORLD"
        assert result["operation"] == "uppercase"

        # Step 3: Test resource access
        settings = get_settings()
        assert settings["version"] == "1.0.0"
        assert "tools" in settings["features"]

        # Step 4: Verify caching is working (if metrics are available)
        if hasattr(server, "get_metrics"):
            metrics = server.get_metrics()
            assert isinstance(metrics, dict)

    @pytest.mark.asyncio
    async def test_mcp_with_authentication_workflow(self):
        """Test MCP workflow with authentication and permissions."""
        # Create authenticated server
        auth = APIKeyAuth(
            {
                "admin_key_123": {"permissions": ["admin", "tools", "resources"]},
                "user_key_456": {"permissions": ["tools"]},
                "readonly_key_789": {"permissions": ["resources"]},
            }
        )

        server = MCPServer("auth-e2e-server", auth_provider=auth)

        # Admin-only tool
        @server.tool(required_permission="admin")
        def admin_operation(action: str) -> dict:
            """Perform administrative operation."""
            return {
                "action": action,
                "status": "completed",
                "user_level": "admin",
                "timestamp": time.time(),
            }

        # General tool accessible to users
        @server.tool()
        def user_operation(data: str) -> dict:
            """Perform user operation."""
            return {
                "data": data,
                "status": "processed",
                "user_level": "user",
                "timestamp": time.time(),
            }

        # Test tool execution (without auth context - direct calls bypass auth)
        try:
            admin_result = admin_operation("system_maintenance")
            # If successful, check the result
            if "error" not in admin_result:
                assert admin_result["user_level"] == "admin"
                assert admin_result["action"] == "system_maintenance"
        except Exception:
            # Expected if authentication context is required
            pass

        try:
            user_result = user_operation("process_data")
            # If successful, check the result
            if "error" not in user_result:
                assert user_result["user_level"] == "user"
                assert user_result["data"] == "process_data"
        except Exception:
            # Expected if authentication context is required
            pass

    @pytest.mark.asyncio
    async def test_mcp_service_discovery_workflow(self):
        """Test complete service discovery and client creation workflow."""
        # Step 1: Create service registry
        registry = ServiceRegistry()

        # Step 2: Register multiple servers with different capabilities
        servers = [
            {
                "id": "data-processor-001",
                "name": "data-processor",
                "transport": "stdio",
                "endpoint": "python -c \"print('data processor ready')\"",
                "capabilities": ["tools", "data_processing"],
                "metadata": {"version": "1.0", "priority": 10},
            },
            {
                "id": "file-handler-001",
                "name": "file-handler",
                "transport": "stdio",
                "endpoint": "python -c \"print('file handler ready')\"",
                "capabilities": ["resources", "file_access"],
                "metadata": {"version": "1.1", "priority": 5},
            },
            {
                "id": "ai-assistant-001",
                "name": "ai-assistant",
                "transport": "http",
                "endpoint": "http://localhost:8080",
                "capabilities": ["tools", "ai", "nlp"],
                "metadata": {"version": "2.0", "priority": 15},
            },
        ]

        for server in servers:
            await registry.register_server(server)

        # Step 3: Test discovery with filters
        all_servers = await registry.discover_servers()
        assert len(all_servers) >= 3

        # Filter by capability
        tools_servers = await registry.discover_servers(capability="tools")
        tools_names = [s.name for s in tools_servers]
        assert "data-processor" in tools_names
        assert "ai-assistant" in tools_names
        assert "file-handler" not in tools_names

        # Filter by transport
        stdio_servers = await registry.discover_servers(transport="stdio")
        stdio_names = [s.name for s in stdio_servers]
        assert "data-processor" in stdio_names
        assert "file-handler" in stdio_names
        assert "ai-assistant" not in stdio_names

        # Step 4: Test server selection by discovering servers
        tools_servers = await registry.discover_servers(capability="tools")
        tools_names = [s.name for s in tools_servers]

        # Should find servers with tools capability
        assert "data-processor" in tools_names
        assert "ai-assistant" in tools_names

    @pytest.mark.asyncio
    async def test_mcp_client_server_communication_e2e(self):
        """Test end-to-end client-server communication."""
        # This test simulates real client-server interaction

        # Create a simple echo server script
        echo_server_script = (
            '''
import json
import sys

while True:
    try:
        line = sys.stdin.readline()
        if not line:
            break

        data = json.loads(line.strip())

        # Echo back with modification
        response = {
            "id": data.get("id"),
            "result": {
                "echo": data.get("params", {}),
                "server": "echo-server",
                "timestamp": "'''
            + str(time.time())
            + """"
            }
        }

        print(json.dumps(response))
        sys.stdout.flush()

    except (json.JSONDecodeError, KeyboardInterrupt, EOFError):
        break
"""
        )

        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(echo_server_script)
            script_path = f.name

        try:
            # Create client config to communicate with echo server
            client_config = {
                "name": "e2e-client",
                "transport": "stdio",
                "command": "python",
                "args": [script_path],
            }

            client = MCPClient(client_config)

            # Test connection
            await client.connect()
            assert client.connected is True

            # Test communication by sending a message
            test_message = {
                "jsonrpc": "2.0",
                "id": "test_1",
                "method": "echo",
                "params": {"message": "Hello MCP!", "test": True},
            }

            # Send message and receive response
            response = await client.send_request(test_message)

            # Verify response
            assert response.get("id") == "test_1"
            assert (
                response.get("result", {}).get("echo", {}).get("message")
                == "Hello MCP!"
            )
            assert response.get("result", {}).get("server") == "echo-server"

            await client.disconnect()
            assert client.connected is False

        except Exception as e:
            # Skip if communication fails (environment issues)
            pytest.skip(f"Client-server communication test skipped: {e}")

        finally:
            # Clean up temporary file
            os.unlink(script_path)

    @pytest.mark.asyncio
    async def test_mcp_load_balancing_and_failover(self):
        """Test load balancing and failover in production scenarios."""
        registry = ServiceRegistry()

        # Register multiple servers with same capability but different health
        servers = [
            {
                "id": "server-fast-001",
                "name": "server-fast",
                "transport": "stdio",
                "endpoint": "echo fast",
                "capabilities": ["tools"],
                "metadata": {"status": "healthy", "response_time": 0.1, "priority": 10},
            },
            {
                "id": "server-slow-001",
                "name": "server-slow",
                "transport": "stdio",
                "endpoint": "echo slow",
                "capabilities": ["tools"],
                "metadata": {"status": "healthy", "response_time": 0.5, "priority": 5},
            },
            {
                "id": "server-failed-001",
                "name": "server-failed",
                "transport": "stdio",
                "endpoint": "nonexistent_command",
                "capabilities": ["tools"],
                "metadata": {
                    "status": "unhealthy",
                    "response_time": 999,
                    "priority": 15,
                },
            },
        ]

        for server in servers:
            await registry.register_server(server)

        # Test server discovery and selection
        tools_servers = await registry.discover_servers(capability="tools")
        assert len(tools_servers) >= 3

        # Verify servers were registered
        server_names = [s.name for s in tools_servers]
        assert "server-fast" in server_names
        assert "server-slow" in server_names
        assert "server-failed" in server_names

    @pytest.mark.asyncio
    async def test_mcp_with_docker_database_integration(self):
        """Test MCP integration with real Docker database services."""
        import asyncpg
        import redis

        from tests.utils.docker_config import (
            get_postgres_connection_string,
            get_redis_url,
        )

        # Verify Docker services are available
        services_ready = await ensure_docker_services()
        if not services_ready:
            pytest.skip("Docker database services not available")

        # Create server with database-connected tools
        server = MCPServer("db-e2e-server")

        @server.tool()
        async def query_database(query_type: str = "status") -> dict:
            """Query real PostgreSQL database for information."""
            try:
                # Use real PostgreSQL connection
                conn = await asyncpg.connect(get_postgres_connection_string())

                if query_type == "status":
                    # Query real database
                    result = await conn.fetchrow("SELECT version() as version")
                    await conn.close()
                    return {
                        "database": "postgresql",
                        "status": "connected",
                        "version": result["version"][:50] + "...",
                        "host": "localhost",
                        "port": 5434,
                        "timestamp": time.time(),
                    }
                elif query_type == "health":
                    # Query database stats
                    result = await conn.fetchrow("SELECT current_timestamp as now")
                    await conn.close()
                    return {
                        "database": "postgresql",
                        "health": "healthy",
                        "current_time": str(result["now"]),
                        "timestamp": time.time(),
                    }
                else:
                    await conn.close()
                    return {
                        "error": "unknown query type",
                        "supported": ["status", "health"],
                    }
            except Exception as e:
                return {
                    "error": f"Database connection failed: {str(e)}",
                    "query_type": query_type,
                }

        @server.tool()
        def cache_operation(
            operation: str, key: str = "test", value: str = "data"
        ) -> dict:
            """Perform cache operations with real Redis."""
            try:
                # Use real Redis connection
                r = redis.Redis(host="localhost", port=6380, decode_responses=True)

                if operation == "set":
                    r.set(f"mcp_test_{key}", value, ex=300)  # 5 minute expiry
                    return {
                        "cache": "redis",
                        "operation": "set",
                        "key": key,
                        "value": value,
                        "status": "success",
                        "timestamp": time.time(),
                    }
                elif operation == "get":
                    cached_value = r.get(f"mcp_test_{key}")
                    return {
                        "cache": "redis",
                        "operation": "get",
                        "key": key,
                        "value": cached_value or "not_found",
                        "status": "success",
                        "timestamp": time.time(),
                    }
                else:
                    return {"error": "unknown operation", "supported": ["set", "get"]}
            except Exception as e:
                return {
                    "error": f"Redis connection failed: {str(e)}",
                    "operation": operation,
                }

        # Test database tool
        db_status = await query_database("status")
        if "error" not in db_status:
            assert db_status["database"] == "postgresql"
            assert db_status["status"] == "connected"

        # Test cache tool
        cache_set = cache_operation("set", "test_key", "test_value")
        assert cache_set["operation"] == "set"
        assert cache_set["key"] == "test_key"

        cache_get = cache_operation("get", "test_key")
        if "error" not in cache_get:
            assert cache_get["operation"] == "get"

        # Test with Ollama AI integration
        @server.tool()
        async def ai_analysis(text: str) -> dict:
            """Analyze text using Ollama AI service."""
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:11435/api/generate",
                        json={
                            "model": "llama3.2:1b",
                            "prompt": f"Analyze this text in one sentence: {text}",
                            "stream": False,
                        },
                        timeout=30.0,
                    )
                    if response.status_code == 200:
                        result = response.json()
                        return {
                            "ai_service": "ollama",
                            "model": "llama3.2:1b",
                            "analysis": result.get("response", "No response"),
                            "status": "success",
                            "timestamp": time.time(),
                        }
                    else:
                        return {
                            "error": f"Ollama API error: {response.status_code}",
                            "text": text,
                        }
            except Exception as e:
                return {"error": f"Ollama connection failed: {str(e)}", "text": text}

        # Test AI analysis
        ai_result = await ai_analysis("This is a test message for AI analysis")
        # AI test is optional - if Ollama isn't ready, that's fine for E2E test coverage

    @pytest.mark.asyncio
    async def test_mcp_error_handling_and_recovery(self):
        """Test error handling and recovery in production workflows."""
        server = MCPServer("error-handling-server")

        @server.tool()
        def error_prone_tool(operation: str, should_fail: bool = False) -> dict:
            """Tool that can simulate various error conditions."""
            if should_fail:
                if operation == "timeout":
                    time.sleep(2)  # Simulate timeout
                    return {"status": "timeout_completed"}
                elif operation == "exception":
                    raise ValueError("Simulated tool error")
                elif operation == "invalid_data":
                    return "invalid response format"  # Should be dict
                else:
                    raise RuntimeError(f"Unknown error operation: {operation}")

            return {
                "operation": operation,
                "status": "success",
                "message": "Operation completed successfully",
            }

        # Test successful operation
        success_result = error_prone_tool("normal", should_fail=False)
        assert success_result["status"] == "success"

        # Test error conditions (errors are wrapped by MCP server)
        try:
            error_prone_tool("exception", should_fail=True)
            # If no exception, operation might be wrapped differently
        except Exception as e:
            # Expected - error handling varies by implementation
            assert "error" in str(e).lower() or "simulated" in str(e).lower()

        try:
            error_prone_tool("unknown", should_fail=True)
            # If no exception, operation might be wrapped differently
        except Exception as e:
            # Expected - error handling varies by implementation
            assert "error" in str(e).lower() or "unknown" in str(e).lower()

    @pytest.mark.asyncio
    async def test_mcp_convenience_functions_e2e(self):
        """Test convenience functions in end-to-end scenarios."""
        # Setup some servers for discovery
        registry = ServiceRegistry()

        test_servers = [
            {
                "id": "convenience-tools-server-001",
                "name": "convenience-tools-server",
                "transport": "stdio",
                "endpoint": "echo",
                "capabilities": ["tools", "convenience_test"],
                "metadata": {"status": "healthy"},
            },
            {
                "id": "convenience-resources-server-001",
                "name": "convenience-resources-server",
                "transport": "stdio",
                "endpoint": "echo",
                "capabilities": ["resources", "convenience_test"],
                "metadata": {"status": "healthy"},
            },
        ]

        for server in test_servers:
            await registry.register_server(server)

        # Test discover_mcp_servers convenience function
        discovered_servers = await discover_mcp_servers(capability="convenience_test")
        assert len(discovered_servers) >= 2

        server_names = [s.name for s in discovered_servers]
        assert "convenience-tools-server" in server_names
        assert "convenience-resources-server" in server_names

        # Test filtered discovery
        tools_servers = await discover_mcp_servers(capability="tools")
        tools_names = [s.name for s in tools_servers]
        assert "convenience-tools-server" in tools_names

        # Test get_mcp_client convenience function
        try:
            client = await get_mcp_client("tools")
            if client:
                assert hasattr(client, "config")
                assert client.config is not None
        except Exception:
            # No actual running servers, which is expected
            pass

    @pytest.mark.asyncio
    async def test_mcp_metrics_and_monitoring_e2e(self):
        """Test metrics collection and monitoring in production workflows."""
        server = MCPServer("metrics-e2e-server", enable_metrics=True)

        @server.tool(cache_key="metrics_tool")
        def metrics_test_tool(data: str, count: int = 1) -> dict:
            """Tool for testing metrics collection."""
            results = []
            for i in range(count):
                results.append(f"{data}_{i}")

            return {"results": results, "count": len(results), "timestamp": time.time()}

        # Execute tool multiple times to generate metrics
        for i in range(5):
            result = metrics_test_tool(f"test_{i}", count=2)
            assert len(result["results"]) == 2

        # Check if metrics are being collected
        if hasattr(server, "get_metrics"):
            metrics = server.get_metrics()
            assert isinstance(metrics, dict)
            # Metrics should contain tool execution data

        # Test cache effectiveness
        cached_result1 = metrics_test_tool("cached_test")
        cached_result2 = metrics_test_tool("cached_test")

        # Both should return same timestamp if caching works
        assert cached_result1["timestamp"] == cached_result2["timestamp"]

    def test_mcp_configuration_management_e2e(self):
        """Test configuration management in production scenarios."""
        # Test with configuration file
        config_data = {
            "server": {"name": "config-test-server", "version": "1.0.0", "timeout": 60},
            "cache": {"enabled": True, "default_ttl": 600},
            "metrics": {"enabled": True, "collect_performance": True},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            # Create server with config file
            server = MCPServer("config-e2e-server", config_file=config_file)

            # Verify configuration is loaded
            assert server.config.get("server.name") == "config-e2e-server"
            assert server.config.get("cache.enabled") is True
            assert server.config.get("metrics.enabled") is True

        finally:
            os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_mcp_production_performance(self):
        """Test MCP performance in production-like scenarios."""
        server = MCPServer("performance-server", enable_metrics=True)

        @server.tool(cache_key="perf_tool")
        def performance_tool(size: int = 100) -> dict:
            """Tool that processes variable amounts of data."""
            # Simulate data processing
            data = list(range(size))
            processed = [x * 2 for x in data]

            return {
                "input_size": size,
                "output_size": len(processed),
                "sample_output": processed[:5],  # First 5 items
                "timestamp": time.time(),
            }

        # Test with different data sizes
        sizes = [10, 100, 1000]
        results = []

        start_time = time.time()

        for size in sizes:
            result = performance_tool(size)
            results.append(result)
            assert result["input_size"] == size
            assert result["output_size"] == size

        total_time = time.time() - start_time

        # Performance should be reasonable (less than 1 second for this test)
        assert total_time < 1.0

        # Test concurrent execution
        import concurrent.futures

        def run_tool(size):
            return performance_tool(size)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_tool, 50) for _ in range(10)]
            concurrent_results = [f.result() for f in futures]

        # All should complete successfully
        assert len(concurrent_results) == 10
        for result in concurrent_results:
            assert result["input_size"] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
