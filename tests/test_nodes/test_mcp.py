"""Unit tests for MCP (Model Context Protocol) nodes."""

from unittest.mock import Mock, patch

import pytest

from kailash.nodes.mcp import MCPClient, MCPResource, MCPServer


class TestMCPResource:
    """Test cases for MCPResource node."""

    def test_create_text_resource(self):
        """Test creating a text resource."""
        node = MCPResource()
        result = node.run(
            operation="create",
            uri="test://resource/document.txt",
            content="This is test content",
            metadata={
                "name": "Test Document",
                "description": "A test document",
                "tags": ["test", "document"],
            },
        )

        assert result["success"] is True
        assert result["operation"] == "create"
        assert "resource" in result

        resource = result["resource"]
        assert resource["uri"] == "test://resource/document.txt"
        assert resource["name"] == "Test Document"
        assert resource["content"] == "This is test content"
        assert resource["mimeType"] == "text/plain"
        assert "version" in resource
        assert "created_at" in resource

    def test_create_json_resource(self):
        """Test creating a JSON resource."""
        node = MCPResource()
        test_data = {"key": "value", "number": 42, "list": [1, 2, 3]}

        result = node.run(
            operation="create",
            uri="test://resource/data.json",
            content=test_data,
            metadata={"name": "Test Data", "mimeType": "application/json"},
        )

        assert result["success"] is True
        resource = result["resource"]
        assert resource["mimeType"] == "application/json"
        assert "key" in resource["content"]  # JSON serialized content

    def test_update_resource(self):
        """Test updating an existing resource."""
        node = MCPResource()
        result = node.run(
            operation="update",
            uri="test://resource/document.txt",
            content="Updated content",
            metadata={"name": "Updated Document"},
            version="2.0",
        )

        assert result["success"] is True
        assert result["operation"] == "update"
        assert "changes" in result
        assert result["changes"]["content"] == "Updated content"
        assert result["changes"]["version"] == "2.0"

    def test_validate_resource(self):
        """Test resource validation."""
        node = MCPResource()
        result = node.run(
            operation="validate",
            uri="test://resource/valid.txt",
            content="Valid content",
            schema={"type": "string", "minLength": 5},
        )

        assert result["success"] is True
        assert result["operation"] == "validate"
        assert result["valid"] is True
        assert len(result["results"]["errors"]) == 0

    def test_validate_invalid_resource(self):
        """Test validation of invalid resource."""
        node = MCPResource()
        result = node.run(
            operation="validate",
            uri="test://resource/invalid.txt",
            content=123,  # Number instead of string
            schema={"type": "string"},
        )

        assert result["success"] is True
        assert result["valid"] is False
        assert len(result["results"]["errors"]) > 0

    def test_list_resources(self):
        """Test listing resources."""
        node = MCPResource()
        result = node.run(operation="list")

        assert result["success"] is True
        assert result["operation"] == "list"
        assert "resources" in result
        assert "total_count" in result
        assert isinstance(result["resources"], list)

    def test_list_resources_with_filter(self):
        """Test listing resources with filters."""
        node = MCPResource()
        result = node.run(
            operation="list",
            metadata={"filter": {"mimeType": "application/json", "min_size": 100}},
        )

        assert result["success"] is True
        assert result["filter_applied"] is True
        assert "filter_criteria" in result

    def test_delete_resource(self):
        """Test deleting a resource."""
        node = MCPResource()
        result = node.run(
            operation="delete", uri="test://resource/to_delete.txt", auto_notify=True
        )

        assert result["success"] is True
        assert result["operation"] == "delete"
        assert "deleted_resource" in result
        assert result["notifications"]["sent"] is True

    def test_invalid_operation(self):
        """Test handling of invalid operations."""
        node = MCPResource()
        result = node.run(operation="invalid_op")

        assert result["success"] is False
        assert "Unsupported operation" in result["error"]
        assert "supported_operations" in result

    def test_create_without_uri(self):
        """Test create operation without URI."""
        node = MCPResource()
        result = node.run(operation="create", content="Test content")

        assert result["success"] is False
        assert "URI is required" in result["error"]

    def test_create_without_content(self):
        """Test create operation without content."""
        node = MCPResource()
        result = node.run(operation="create", uri="test://resource/empty.txt")

        assert result["success"] is False
        assert "Content is required" in result["error"]


class TestMCPClient:
    """Test cases for MCPClient node."""

    def test_list_resources(self):
        """Test listing resources from MCP server."""
        node = MCPClient()
        server_config = {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_server"],
        }

        result = node.run(server_config=server_config, operation="list_resources")

        assert result["success"] is True
        assert result["operation"] == "list_resources"
        assert "resources" in result
        assert "resource_count" in result
        assert result["mock"] is True

    def test_read_resource(self):
        """Test reading a specific resource."""
        node = MCPClient()
        server_config = {
            "name": "test-server", 
            "transport": "stdio",
            "command": "mcp-test-server"  # Add required command
        }

        result = node.run(
            server_config=server_config,
            operation="read_resource",
            resource_uri="file:///test/document.txt",
        )

        assert result["success"] is True
        assert result["operation"] == "read_resource"
        assert "resource" in result
        assert result["resource"]["uri"] == "file:///test/document.txt"

    def test_list_tools(self):
        """Test listing available tools."""
        node = MCPClient()
        server_config = {
            "name": "test-server", 
            "transport": "stdio",
            "command": "mcp-test-server"  # Add required command
        }

        result = node.run(server_config=server_config, operation="list_tools")

        assert result["success"] is True
        assert "tools" in result
        assert "tool_count" in result
        assert isinstance(result["tools"], list)

    def test_call_tool(self):
        """Test calling a tool on the server."""
        node = MCPClient()
        server_config = {
            "name": "test-server", 
            "transport": "stdio",
            "command": "mcp-test-server"  # Add required command
        }

        result = node.run(
            server_config=server_config,
            operation="call_tool",
            tool_name="create_file",
            tool_arguments={"path": "/tmp/test.txt", "content": "test content"},
        )

        assert result["success"] is True
        assert result["tool_name"] == "create_file"
        assert "result" in result
        assert result["tool_arguments"]["path"] == "/tmp/test.txt"

    def test_get_prompt(self):
        """Test getting a prompt from the server."""
        node = MCPClient()
        server_config = {
            "name": "test-server", 
            "transport": "stdio",
            "command": "mcp-test-server"  # Add required command
        }

        result = node.run(
            server_config=server_config,
            operation="get_prompt",
            prompt_name="summarize_document",
            prompt_arguments={"document": "Test document content", "max_length": "100"},
        )

        assert result["success"] is True
        assert result["prompt_name"] == "summarize_document"
        assert "prompt" in result
        assert "content" in result["prompt"]

    def test_http_transport(self):
        """Test HTTP transport configuration."""
        node = MCPClient()
        server_config = {
            "name": "test-server",
            "transport": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer token"},
        }

        result = node.run(server_config=server_config, operation="list_resources")

        assert result["success"] is True
        assert result["transport"] == "http"
        assert result["url"] == "http://localhost:8080"

    def test_missing_server_config(self):
        """Test error handling for missing server config."""
        node = MCPClient()

        with pytest.raises(Exception):
            node.run(operation="list_resources")

    def test_invalid_operation(self):
        """Test handling of unsupported operations."""
        node = MCPClient()
        server_config = {
            "name": "test-server", 
            "transport": "stdio",
            "command": "mcp-test-server"  # Add required command
        }

        result = node.run(server_config=server_config, operation="invalid_operation")

        assert result["success"] is False
        assert "Unsupported operation" in result["error"]

    def test_call_tool_without_name(self):
        """Test tool call without tool name."""
        node = MCPClient()
        server_config = {
            "name": "test-server", 
            "transport": "stdio",
            "command": "mcp-test-server"  # Add required command
        }

        result = node.run(server_config=server_config, operation="call_tool")

        assert result["success"] is False
        assert "tool_name is required" in result["error"]


class TestMCPServer:
    """Test cases for MCPServer node."""

    def test_configure_basic_server(self):
        """Test basic server configuration."""
        node = MCPServer()

        result = node.run(
            server_config={"name": "test-server", "transport": "stdio"},
            resources=[
                {
                    "uri": "test://data/metrics.json",
                    "name": "Test Metrics",
                    "content": {"views": 100, "users": 10},
                }
            ],
            auto_start=True,
        )

        assert result["success"] is True
        assert "server" in result
        assert result["server"]["server_name"] == "test-server"
        assert result["server"]["resources_count"] == 1
        assert result["mock"] is True

    def test_configure_with_tools(self):
        """Test server configuration with tools."""
        node = MCPServer()

        tools = [
            {
                "name": "analyze_data",
                "description": "Analyze dataset",
                "parameters": {
                    "type": "object",
                    "properties": {"dataset": {"type": "string"}},
                },
            }
        ]

        result = node.run(
            server_config={"name": "test-server", "transport": "stdio"}, tools=tools
        )

        assert result["success"] is True
        assert result["server"]["tools_count"] == 1
        assert "code" in result

    def test_configure_with_prompts(self):
        """Test server configuration with prompts."""
        node = MCPServer()

        prompts = [
            {
                "name": "summarize",
                "description": "Summarize content",
                "template": "Summarize: {content}",
                "arguments": [{"name": "content", "required": True}],
            }
        ]

        result = node.run(
            server_config={"name": "test-server", "transport": "stdio"}, prompts=prompts
        )

        assert result["success"] is True
        assert result["server"]["prompts_count"] == 1

    def test_http_server_config(self):
        """Test HTTP server configuration."""
        node = MCPServer()

        result = node.run(
            server_config={
                "name": "http-server",
                "transport": "http",
                "host": "localhost",
                "port": 8080,
            },
            auto_start=True,
        )

        assert result["success"] is True
        server_info = result["server"]
        assert server_info["transport"] == "http"
        assert server_info["host"] == "localhost"
        assert server_info["port"] == 8080

    def test_resource_providers(self):
        """Test dynamic resource providers."""
        node = MCPServer()

        resource_providers = {
            "data://tables/*": "list_tables",
            "file://workspace/*": "list_files",
        }

        result = node.run(
            server_config={"name": "dynamic-server", "transport": "stdio"},
            resource_providers=resource_providers,
        )

        assert result["success"] is True
        assert result["server"]["providers_count"] == 2

    def test_authentication_config(self):
        """Test server with authentication."""
        node = MCPServer()

        auth_config = {"type": "bearer", "token": "secret-token"}

        result = node.run(
            server_config={"name": "secure-server", "transport": "http"},
            authentication=auth_config,
        )

        assert result["success"] is True
        # Authentication details are part of generated code, not returned separately in mock
        assert "code" in result

    def test_generated_code_structure(self):
        """Test that generated server code has proper structure."""
        node = MCPServer()

        result = node.run(
            server_config={"name": "code-test-server", "transport": "stdio"},
            resources=[{"uri": "test://resource", "content": "test"}],
            tools=[{"name": "test_tool", "description": "Test tool"}],
            prompts=[{"name": "test_prompt", "template": "Test: {input}"}],
        )

        assert result["success"] is True
        code = result["code"]

        # Check for key components in generated code
        assert "from mcp.server.fastmcp import FastMCP" in code
        assert "mcp = FastMCP(" in code
        assert "@mcp.resource(" in code
        assert "@mcp.tool(" in code
        assert "@mcp.prompt(" in code
        assert 'if __name__ == "__main__":' in code


@pytest.fixture
def sample_mcp_config():
    """Sample MCP configuration for testing."""
    return {
        "server_config": {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_mcp_server"],
        },
        "resources": [
            {
                "uri": "test://data/sample.json",
                "name": "Sample Data",
                "content": {"test": "data"},
            }
        ],
        "tools": [
            {
                "name": "process_data",
                "description": "Process data",
                "parameters": {"type": "object"},
            }
        ],
    }


def test_mcp_integration_flow(sample_mcp_config):
    """Test complete MCP integration flow."""
    # Create resource
    resource_node = MCPResource()
    resource_result = resource_node.run(
        operation="create",
        uri="test://integration/flow.json",
        content={"flow": "test", "step": 1},
    )

    assert resource_result["success"] is True

    # Configure server
    server_node = MCPServer()
    server_result = server_node.run(**sample_mcp_config)

    assert server_result["success"] is True

    # Connect client
    client_node = MCPClient()
    client_result = client_node.run(
        server_config=sample_mcp_config["server_config"], operation="list_resources"
    )

    assert client_result["success"] is True
    assert client_result["resource_count"] >= 1
