"""Focused test to verify the FastMCP import fix."""

import pytest


@pytest.mark.integration
class TestFastMCPImportFix:
    """Test that the FastMCP import fix is working correctly."""

    def test_enhanced_mcp_server_import_no_error(self):
        """Test that MCPServer can be imported without import errors."""
        # This is the core test - if the import fix failed, this would raise
        # ModuleNotFoundError: No module named 'mcp.server.fastmcp'
        try:
            from kailash.mcp_server.server import MCPServer

            # If we get here, the import succeeded
            assert True
        except ModuleNotFoundError as e:
            if "mcp.server.fastmcp" in str(e):
                pytest.fail(
                    f"FastMCP import fix not working! Still trying to import from "
                    f"'mcp.server.fastmcp' instead of 'mcp.server': {e}"
                )
            else:
                # Some other import error - re-raise
                raise
        except ImportError as e:
            # This is expected if mcp package is not installed
            if "FastMCP not available" in str(e) or "No module named 'mcp'" in str(e):
                pytest.skip("MCP package not installed - this is expected")
            else:
                # Unexpected import error
                raise

    def test_enhanced_mcp_server_creation(self):
        """Test creating an MCPServer instance."""
        try:
            from kailash.mcp_server.server import MCPServer

            # Create a server instance
            server = MCPServer(name="test-import-fix-server")

            # Basic assertions
            assert server.name == "test-import-fix-server"
            assert hasattr(server, "_init_mcp")
            assert hasattr(server, "tool")
            assert hasattr(server, "resource")
            assert hasattr(server, "run")

        except ImportError as e:
            if "FastMCP not available" in str(e) or "No module named 'mcp'" in str(e):
                pytest.skip("MCP package not installed - this is expected")
            else:
                raise

    def test_init_mcp_method_exists_and_correct(self):
        """Test that _init_mcp method has the correct import."""
        from kailash.mcp_server.server import MCPServer

        server = MCPServer(name="test-server")

        # Try to initialize MCP - this will fail if mcp package not installed
        # but that's OK, we're testing the import path
        try:
            server._init_mcp()
        except ImportError as e:
            # Check the error message doesn't mention the old import path
            error_str = str(e)
            assert (
                "mcp.server.fastmcp" not in error_str
            ), f"Old import path still being used: {error_str}"

            # The error should be about 'mcp.server' or just 'mcp'
            assert (
                "No module named 'mcp'" in error_str
                or "No module named 'mcp.server'" in error_str
                or "FastMCP not available" in error_str
            ), f"Unexpected import error: {error_str}"

    def test_tool_decorator_available(self):
        """Test that tool decorator is available and doesn't crash on import issues."""
        from kailash.mcp_server.server import MCPServer

        server = MCPServer(name="test-server")

        # Define a tool - this should work even if MCP not installed
        try:

            @server.tool()
            def test_tool(query: str) -> str:
                return f"Result: {query}"

            # The tool function might be wrapped by MCP, check if it's callable
            # In fallback mode, it's still a function; in real MCP, it might be a FunctionTool
            if hasattr(test_tool, "__call__") and not hasattr(test_tool, "fn"):
                # Direct function call (fallback mode)
                result = test_tool("test")
            elif hasattr(test_tool, "fn"):
                # MCP FunctionTool object - call the underlying function via 'fn' attribute
                result = test_tool.fn("test")
            else:
                # Skip if we can't determine how to call it
                pytest.skip("Unable to determine how to call decorated tool function")

            assert result == "Result: test"

        except ImportError as e:
            if "FastMCP not available" in str(e) or "No module named 'mcp'" in str(e):
                pytest.skip("MCP package not installed - this is expected")
            else:
                raise

    def test_resource_decorator_available(self):
        """Test that resource decorator is available."""
        from kailash.mcp_server.server import MCPServer

        server = MCPServer(name="test-server")

        # Define a resource - this should work even if MCP not installed
        try:

            @server.resource("test://resource")
            def test_resource():
                return {"content": "test data"}

            # The decorator returns a FunctionResource object
            # We need to check that the resource was registered
            assert hasattr(test_resource, "__name__") or hasattr(
                test_resource, "function"
            )
            # Resource registration successful

        except ImportError as e:
            if "FastMCP not available" in str(e) or "No module named 'mcp'" in str(e):
                pytest.skip("MCP package not installed - this is expected")
            else:
                raise

    def test_error_scenario_user_reported(self):
        """Test the exact scenario reported by the user."""
        # This simulates what happens when ai_hub tries to use MCPServer
        try:
            from kailash.mcp_server.server import MCPServer

            # Create server like in agent_server.py
            server = MCPServer(name="agent-server")

            # Register a tool like in the user's code
            @server.tool(cache_key="todos", cache_ttl=300)
            def list_todos():
                return ["todo1", "todo2"]

            # If we get here without ModuleNotFoundError about fastmcp, the fix works
            assert True

        except ModuleNotFoundError as e:
            if "mcp.server.fastmcp" in str(e):
                pytest.fail(
                    "The exact user-reported error still occurs! "
                    f"Import still looking for 'mcp.server.fastmcp': {e}"
                )
            else:
                raise
        except ImportError as e:
            if "FastMCP not available" in str(e):
                # This is expected if MCP not installed
                pytest.skip("MCP package not installed")
            else:
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
