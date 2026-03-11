"""
Tier 1 Unit Tests for Kaizen Builtin MCP Server

Tests the MCP server infrastructure, tool registration, and metadata.
"""

import inspect

from kaizen.mcp.builtin_server.decorators import mcp_tool
from kaizen.mcp.builtin_server.server import KaizenMCPServer, server
from kaizen.mcp.builtin_server.tools import api, bash, file, web


class TestMCPServerInfrastructure:
    """Test MCP server basic infrastructure."""

    def test_server_instance_created(self):
        """Test that server instance is created successfully."""
        assert server is not None
        assert isinstance(server, KaizenMCPServer)

    def test_server_metadata(self):
        """Test server has correct metadata."""
        assert server.name == "kaizen_builtin"
        assert (
            server.description
            == "Kaizen builtin tools - file operations, HTTP requests, bash commands, web scraping"
        )
        assert server.version == "1.0.0"

    def test_server_has_tool_registry(self):
        """Test server has tool registry."""
        assert hasattr(server, "_tool_registry")
        assert isinstance(server._tool_registry, dict)

    def test_auto_register_tools_method(self):
        """Test auto_register_tools method exists."""
        assert hasattr(server, "auto_register_tools")
        assert callable(server.auto_register_tools)


class TestToolRegistration:
    """Test that all 12 tools are registered correctly."""

    def test_total_tools_registered(self):
        """Test that exactly 12 tools are registered."""
        assert len(server._tool_registry) == 12

    def test_file_tools_registered(self):
        """Test all 5 file tools are registered."""
        file_tools = [
            "read_file",
            "write_file",
            "delete_file",
            "list_directory",
            "file_exists",
        ]
        for tool in file_tools:
            assert tool in server._tool_registry, f"File tool '{tool}' not registered"

    def test_api_tools_registered(self):
        """Test all 4 HTTP tools are registered."""
        api_tools = ["http_get", "http_post", "http_put", "http_delete"]
        for tool in api_tools:
            assert tool in server._tool_registry, f"API tool '{tool}' not registered"

    def test_bash_tool_registered(self):
        """Test bash tool is registered."""
        assert "bash_command" in server._tool_registry

    def test_web_tools_registered(self):
        """Test all 2 web tools are registered."""
        web_tools = ["fetch_url", "extract_links"]
        for tool in web_tools:
            assert tool in server._tool_registry, f"Web tool '{tool}' not registered"


class TestToolMetadata:
    """Test tool metadata from @mcp_tool decorator."""

    def test_file_tools_have_metadata(self):
        """Test file tools have @mcp_tool metadata."""
        tools = [
            file.read_file,
            file.write_file,
            file.delete_file,
            file.list_directory,
            file.file_exists,
        ]
        for tool_func in tools:
            assert hasattr(
                tool_func, "_is_mcp_tool"
            ), f"{tool_func.__name__} missing _is_mcp_tool attribute"
            assert tool_func._is_mcp_tool is True
            assert hasattr(tool_func, "_mcp_name")
            assert hasattr(tool_func, "_mcp_description")

    def test_api_tools_have_metadata(self):
        """Test API tools have @mcp_tool metadata."""
        tools = [api.http_get, api.http_post, api.http_put, api.http_delete]
        for tool_func in tools:
            assert hasattr(tool_func, "_is_mcp_tool")
            assert tool_func._is_mcp_tool is True
            assert hasattr(tool_func, "_mcp_name")
            assert hasattr(tool_func, "_mcp_description")

    def test_bash_tool_has_metadata(self):
        """Test bash tool has @mcp_tool metadata."""
        assert hasattr(bash.bash_command, "_is_mcp_tool")
        assert bash.bash_command._is_mcp_tool is True
        assert hasattr(bash.bash_command, "_mcp_name")
        assert bash.bash_command._mcp_description is not None

    def test_web_tools_have_metadata(self):
        """Test web tools have @mcp_tool metadata."""
        tools = [web.fetch_url, web.extract_links]
        for tool_func in tools:
            assert hasattr(tool_func, "_is_mcp_tool")
            assert tool_func._is_mcp_tool is True
            assert hasattr(tool_func, "_mcp_name")
            assert hasattr(tool_func, "_mcp_description")

    def test_all_tools_are_async(self):
        """Test all tools are async coroutines."""
        all_tools = [
            file.read_file,
            file.write_file,
            file.delete_file,
            file.list_directory,
            file.file_exists,
            api.http_get,
            api.http_post,
            api.http_put,
            api.http_delete,
            bash.bash_command,
            web.fetch_url,
            web.extract_links,
        ]
        for tool_func in all_tools:
            assert inspect.iscoroutinefunction(
                tool_func
            ), f"{tool_func.__name__} is not async"


class TestMCPToolDecorator:
    """Test @mcp_tool decorator functionality."""

    def test_decorator_adds_metadata(self):
        """Test decorator adds correct metadata attributes."""

        @mcp_tool(
            name="test_tool",
            description="Test description",
            parameters={"param1": {"type": "string"}},
        )
        async def test_function():
            pass

        assert test_function._is_mcp_tool is True
        assert test_function._mcp_name == "test_tool"
        assert test_function._mcp_description == "Test description"
        assert test_function._mcp_parameters == {"param1": {"type": "string"}}

    def test_decorator_with_defaults(self):
        """Test decorator uses function name and docstring as defaults."""

        @mcp_tool()
        async def my_custom_tool():
            """Custom tool description."""
            pass

        assert my_custom_tool._is_mcp_tool is True
        assert my_custom_tool._mcp_name == "my_custom_tool"
        assert my_custom_tool._mcp_description == "Custom tool description."
        assert my_custom_tool._mcp_parameters == {}

    def test_decorator_preserves_function(self):
        """Test decorator preserves original function."""

        @mcp_tool(name="test")
        async def original_function(x, y):
            return x + y

        # Function should still be callable
        assert inspect.iscoroutinefunction(original_function)


class TestToolModules:
    """Test individual tool modules."""

    def test_file_module_exports(self):
        """Test file module has all expected tools."""
        expected = [
            "read_file",
            "write_file",
            "delete_file",
            "list_directory",
            "file_exists",
        ]
        for name in expected:
            assert hasattr(file, name), f"file module missing {name}"

    def test_api_module_exports(self):
        """Test API module has all expected tools."""
        expected = ["http_get", "http_post", "http_put", "http_delete"]
        for name in expected:
            assert hasattr(api, name), f"api module missing {name}"

    def test_bash_module_exports(self):
        """Test bash module has expected tool."""
        assert hasattr(bash, "bash_command")

    def test_web_module_exports(self):
        """Test web module has all expected tools."""
        expected = ["fetch_url", "extract_links"]
        for name in expected:
            assert hasattr(web, name), f"web module missing {name}"
