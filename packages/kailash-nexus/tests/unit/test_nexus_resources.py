"""Unit tests for Nexus resource management.

Tests the resource providers that expose workflow definitions,
documentation, and data through the MCP protocol.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add nexus src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Test Component 3: Resource Providers


@pytest.fixture
def mock_server():
    """Create a mock MCP server."""
    server = Mock()
    server.resource = Mock()

    # Track registered resources
    server._resources = {}

    def mock_resource(pattern):
        def decorator(func):
            server._resources[pattern] = func
            return func

        return decorator

    server.resource = mock_resource
    return server


@pytest.fixture
def mock_nexus():
    """Create a mock Nexus instance."""
    nexus = Mock()
    nexus._workflows = {}
    nexus._api_port = 8000
    nexus._mcp_port = 3001
    # Use private attributes (matching core.py implementation)
    nexus._enable_auth = False
    nexus._enable_monitoring = False
    nexus._enable_discovery = False
    nexus.rate_limit_config = {}
    nexus._get_enabled_transports = Mock(return_value=["websocket"])
    return nexus


@pytest.fixture
def resource_manager(mock_server, mock_nexus):
    """Create a resource manager instance."""
    from nexus.resources import NexusResourceManager

    return NexusResourceManager(mock_server, mock_nexus)


class TestNexusResourceManager:
    """Test the NexusResourceManager class."""


class TestWorkflowResources:
    """Test workflow definition resources."""

    @pytest.mark.asyncio
    async def test_workflow_resource_found(
        self, mock_server, mock_nexus, resource_manager
    ):
        """Test retrieving an existing workflow resource."""
        # Add a mock workflow
        mock_workflow = Mock()
        mock_node = Mock(
            __class__=Mock(__name__="TestNode"), _config={"param": "value"}
        )
        # Mock get_input_schema and get_output_schema to return proper dictionaries
        mock_node.get_input_schema.return_value = {"input_param": {"type": "string"}}
        mock_node.get_output_schema.return_value = {"output_param": {"type": "string"}}
        mock_workflow._nodes = {"node1": mock_node}
        mock_workflow._connections = [
            {"source": "node1", "output": "out", "target": "node2", "input": "in"}
        ]
        # Fix metadata to support "in" operator
        mock_workflow.metadata = {}
        mock_nexus._workflows["test_workflow"] = mock_workflow

        # Get the resource handler
        handler = mock_server._resources["workflow://*"]

        # Call handler
        result = await handler("workflow://test_workflow")

        assert result["uri"] == "workflow://test_workflow"
        assert result["mimeType"] == "application/json"

        # Parse content
        content = json.loads(result["content"])
        assert content["name"] == "test_workflow"
        assert content["type"] == "workflow"
        assert len(content["nodes"]) == 1
        assert content["nodes"][0]["id"] == "node1"
        assert content["nodes"][0]["type"] == "TestNode"
        assert len(content["connections"]) == 1

    @pytest.mark.asyncio
    async def test_workflow_resource_not_found(
        self, mock_server, mock_nexus, resource_manager
    ):
        """Test retrieving a non-existent workflow resource."""
        handler = mock_server._resources["workflow://*"]

        result = await handler("workflow://nonexistent")

        assert result["uri"] == "workflow://nonexistent"
        assert result["mimeType"] == "application/json"
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_workflow_with_metadata(
        self, mock_server, mock_nexus, resource_manager
    ):
        """Test workflow resource with metadata."""
        # Create workflow with metadata
        mock_workflow = Mock()
        mock_workflow.metadata = {
            "description": "Test workflow",
            "version": "1.0.0",
            "parameters": {"input": {"type": "string", "required": True}},
        }
        mock_workflow._nodes = {}
        mock_workflow._connections = []
        mock_nexus._workflows["metadata_workflow"] = mock_workflow

        handler = mock_server._resources["workflow://*"]
        result = await handler("workflow://metadata_workflow")

        content = json.loads(result["content"])
        assert content["metadata"] == mock_workflow.metadata
        assert content["schema"]["inputs"] == mock_workflow.metadata["parameters"]


class TestDocumentationResources:
    """Test documentation resources."""

    @pytest.mark.asyncio
    async def test_quickstart_documentation(self, mock_server, resource_manager):
        """Test retrieving quickstart documentation."""
        handler = mock_server._resources["docs://*"]

        result = await handler("docs://quickstart")

        assert result["uri"] == "docs://quickstart"
        assert result["mimeType"] == "text/markdown"
        assert "# Nexus Quick Start Guide" in result["content"]
        assert "pip install kailash-nexus" in result["content"]

    @pytest.mark.asyncio
    async def test_api_documentation(self, mock_server, resource_manager):
        """Test retrieving API documentation."""
        handler = mock_server._resources["docs://*"]

        result = await handler("docs://api")

        assert result["uri"] == "docs://api"
        assert result["mimeType"] == "text/markdown"
        assert "# Nexus API Reference" in result["content"]
        assert "/workflows/{name}" in result["content"]

    @pytest.mark.asyncio
    async def test_mcp_documentation(self, mock_server, resource_manager):
        """Test retrieving MCP documentation."""
        handler = mock_server._resources["docs://*"]

        result = await handler("docs://mcp")

        assert result["uri"] == "docs://mcp"
        assert result["mimeType"] == "text/markdown"
        assert "# MCP Integration Guide" in result["content"]
        assert "ws://localhost:3001" in result["content"]

    @pytest.mark.asyncio
    async def test_documentation_not_found(self, mock_server, resource_manager):
        """Test retrieving non-existent documentation."""
        handler = mock_server._resources["docs://*"]

        result = await handler("docs://nonexistent")

        assert result["uri"] == "docs://nonexistent"
        assert result["mimeType"] == "text/plain"
        assert "error" in result
        assert "not found" in result["error"]


class TestDataResources:
    """Test data resources with security."""

    @pytest.mark.asyncio
    async def test_data_resource_security_check(self, mock_server, resource_manager):
        """Test security checks for data resources."""
        handler = mock_server._resources["data://*"]

        # Try to access forbidden paths
        forbidden_paths = [
            "../etc/passwd",
            "/etc/shadow",
            ".env",
            "secret_key.pem",
            "passwords.txt",
        ]

        for path in forbidden_paths:
            result = await handler(f"data://{path}")
            assert "error" in result
            assert "Access denied" in result["error"]

    @pytest.mark.asyncio
    async def test_data_resource_examples(self, mock_server, resource_manager):
        """Test predefined example data resources."""
        handler = mock_server._resources["data://*"]

        result = await handler("data://examples/sample.json")

        assert result["uri"] == "data://examples/sample.json"
        assert result["mimeType"] == "application/json"

        content = json.loads(result["content"])
        assert "example" in content
        assert content["example"] == "data"

    @pytest.mark.asyncio
    async def test_data_resource_file_read(
        self, mock_server, resource_manager, tmp_path
    ):
        """Test reading allowed data files."""
        # Use a real temporary directory and file
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_file = data_dir / "config.json"
        config_file.write_text('{"test": "data"}')

        # Patch the safe_base to use our temp directory
        with patch("os.path.abspath") as mock_abspath:
            # Setup abspath to return proper paths
            def abspath_side_effect(path):
                if path == "./data":
                    return str(data_dir)
                elif path.startswith(str(data_dir)):
                    return path
                else:
                    # For os.path.join(safe_base, resource_path)
                    return str(data_dir / path.split("/")[-1])

            mock_abspath.side_effect = abspath_side_effect

            handler = mock_server._resources["data://*"]
            result = await handler("data://config.json")

            assert result["uri"] == "data://config.json"
            assert result["mimeType"] == "application/json"
            assert result["content"] == '{"test": "data"}'

    def test_mime_type_detection(self, resource_manager):
        """Test MIME type detection for various file types."""
        test_cases = {
            "file.json": "application/json",
            "file.xml": "application/xml",
            "file.txt": "text/plain",
            "file.md": "text/markdown",
            "file.html": "text/html",
            "file.css": "text/css",
            "file.js": "application/javascript",
            "file.py": "text/x-python",
            "file.yaml": "application/x-yaml",
            "file.yml": "application/x-yaml",
            "file.unknown": "application/octet-stream",
        }

        for filename, expected_mime in test_cases.items():
            assert resource_manager._get_mime_type(filename) == expected_mime


class TestConfigurationResources:
    """Test configuration resources."""

    @pytest.mark.asyncio
    async def test_platform_configuration(
        self, mock_server, mock_nexus, resource_manager
    ):
        """Test platform configuration resource."""
        handler = mock_server._resources["config://*"]

        result = await handler("config://platform")

        assert result["uri"] == "config://platform"
        assert result["mimeType"] == "application/json"

        config = json.loads(result["content"])
        assert config["name"] == "Kailash Nexus"
        assert config["version"] == "1.0.0"
        assert config["api_port"] == 8000
        assert config["mcp_port"] == 3001
        assert config["features"]["auth"] is False
        assert config["features"]["transports"] == ["websocket"]

    @pytest.mark.asyncio
    async def test_workflows_configuration(
        self, mock_server, mock_nexus, resource_manager
    ):
        """Test workflows configuration resource."""
        # Add test workflows
        mock_nexus._workflows = {"workflow1": Mock(), "workflow2": Mock()}

        handler = mock_server._resources["config://*"]
        result = await handler("config://workflows")

        config = json.loads(result["content"])
        assert config["registered"] == ["workflow1", "workflow2"]
        assert config["count"] == 2

    @pytest.mark.asyncio
    async def test_limits_configuration(
        self, mock_server, mock_nexus, resource_manager
    ):
        """Test limits configuration resource."""
        mock_nexus.rate_limit_config = {"default": 100}

        handler = mock_server._resources["config://*"]
        result = await handler("config://limits")

        config = json.loads(result["content"])
        assert config["rate_limit"] == {"default": 100}
        assert config["max_workflows"] == 1000
        assert config["max_connections"] == 10000

    @pytest.mark.asyncio
    async def test_unknown_configuration(self, mock_server, resource_manager):
        """Test unknown configuration key."""
        handler = mock_server._resources["config://*"]

        result = await handler("config://unknown")

        config = json.loads(result["content"])
        assert "error" in config
        assert "Unknown configuration key" in config["error"]


class TestHelpResources:
    """Test help resources."""

    @pytest.mark.asyncio
    async def test_getting_started_help(self, mock_server, resource_manager):
        """Test getting started help."""
        handler = mock_server._resources["help://*"]

        result = await handler("help://getting-started")

        assert result["uri"] == "help://getting-started"
        assert result["mimeType"] == "text/markdown"
        assert "# Getting Started with Nexus" in result["content"]

    @pytest.mark.asyncio
    async def test_workflows_help(self, mock_server, resource_manager):
        """Test workflows help."""
        handler = mock_server._resources["help://*"]

        result = await handler("help://workflows")

        assert result["uri"] == "help://workflows"
        assert result["mimeType"] == "text/markdown"
        assert "# Working with Workflows" in result["content"]

    @pytest.mark.asyncio
    async def test_troubleshooting_help(self, mock_server, resource_manager):
        """Test troubleshooting help."""
        handler = mock_server._resources["help://*"]

        result = await handler("help://troubleshooting")

        assert result["uri"] == "help://troubleshooting"
        assert result["mimeType"] == "text/markdown"
        assert "# Troubleshooting" in result["content"]
        assert "Port already in use" in result["content"]

    @pytest.mark.asyncio
    async def test_unknown_help_topic(self, mock_server, resource_manager):
        """Test unknown help topic."""
        handler = mock_server._resources["help://*"]

        result = await handler("help://unknown-topic")

        assert result["uri"] == "help://unknown-topic"
        assert result["mimeType"] == "text/markdown"
        assert "# Help: unknown-topic" in result["content"]
        assert "No specific help available" in result["content"]
        assert "Available help topics:" in result["content"]


class TestCustomResourceRegistration:
    """Test custom resource registration."""

    def test_register_custom_resource(self, mock_server, resource_manager):
        """Test registering a custom resource handler."""

        # Define custom handler
        async def custom_handler(uri: str) -> Dict[str, Any]:
            return {"uri": uri, "mimeType": "text/plain", "content": "Custom resource"}

        # Register custom resource
        resource_manager.register_custom_resource("custom://*", custom_handler)

        # Should be registered
        assert "custom://*" in mock_server._resources
        assert mock_server._resources["custom://*"] == custom_handler


class TestWorkflowSchemaExtraction:
    """Test workflow schema extraction."""

    def test_extract_workflow_inputs_from_metadata(self, resource_manager):
        """Test extracting inputs from workflow metadata."""
        workflow = Mock()
        workflow.metadata = {
            "parameters": {
                "input1": {"type": "string", "required": True},
                "input2": {"type": "number", "default": 0},
            }
        }

        inputs = resource_manager._extract_workflow_inputs(workflow)
        assert inputs == workflow.metadata["parameters"]

    def test_extract_workflow_inputs_from_nodes(self, resource_manager):
        """Test extracting inputs from workflow nodes.

        NOTE: Automatic node schema inference is deferred to v1.1.
        Currently returns empty dict if metadata not provided.
        """
        workflow = Mock()
        workflow.metadata = {}

        node = Mock()
        node.get_input_schema = Mock(return_value={"data": {"type": "array"}})

        workflow._nodes = {"node1": node}

        inputs = resource_manager._extract_workflow_inputs(workflow)
        # v1.0: Returns empty dict (automatic inference deferred to v1.1)
        assert inputs == {}

    def test_extract_workflow_outputs(self, resource_manager):
        """Test extracting workflow outputs.

        NOTE: Automatic node schema inference is deferred to v1.1.
        Currently returns empty dict if metadata not provided.
        """
        workflow = Mock()
        workflow.metadata = {}  # Mock needs to support "in" operator

        node = Mock()
        node.get_output_schema = Mock(return_value={"result": {"type": "object"}})

        workflow._nodes = {"node1": node}

        outputs = resource_manager._extract_workflow_outputs(workflow)
        # v1.0: Returns empty dict (automatic inference deferred to v1.1)
        assert outputs == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
