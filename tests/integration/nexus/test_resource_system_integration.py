"""Tier 2 Integration Tests for Resource System (NO MOCKING).

Tests the MCP resource system with real configuration and workflow metadata.
Validates the stub fixes in resources.py.
"""

import json

import pytest
from kailash.mcp_server import MCPServer
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus
from nexus.resources import NexusResourceManager


@pytest.mark.integration
class TestResourceSystemIntegration:
    """Integration tests for MCP resource management."""

    def test_workflow_definition_resource_extraction(self):
        """Test extracting workflow definitions as resources.

        CRITICAL: Tests _extract_workflow_info() method that was a stub.
        NO MOCKING - uses real workflows and metadata.
        """
        # Create real workflow with metadata
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "step1", {"code": "result = {'value': 10}"})
        workflow.add_node(
            "PythonCodeNode", "step2", {"code": "result = {'value': input_value * 2}"}
        )
        workflow.add_connection("step1", "result", "step2", "input_value")
        built_workflow = workflow.build()

        # Add metadata to workflow
        built_workflow.metadata = {
            "description": "Test workflow",
            "version": "1.0",
            "parameters": {"input_value": {"type": "int", "default": 5}},
        }

        # Create Nexus and resource manager
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Register workflow
        nexus._workflows["test_workflow"] = built_workflow

        # Extract workflow info (REAL EXTRACTION, not mocked)
        workflow_info = resource_manager._extract_workflow_info(
            "test_workflow", built_workflow
        )

        # Verify extraction
        assert workflow_info["name"] == "test_workflow"
        assert workflow_info["type"] == "workflow"
        assert len(workflow_info["nodes"]) == 2
        assert len(workflow_info["connections"]) == 1

        # Verify metadata included
        assert workflow_info["metadata"]["description"] == "Test workflow"
        assert workflow_info["metadata"]["version"] == "1.0"

        # Verify schema extraction
        assert "schema" in workflow_info
        assert "inputs" in workflow_info["schema"]
        assert "outputs" in workflow_info["schema"]

    def test_workflow_input_schema_extraction(self):
        """Test extracting workflow input schemas from metadata.

        Tests _extract_workflow_inputs() with explicit metadata.
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "process",
            {"code": "result = {'output': name + ' processed'}"},
        )
        built_workflow = workflow.build()

        # Add input schema to metadata
        built_workflow.metadata = {
            "parameters": {
                "name": {"type": "string", "required": True},
                "age": {"type": "integer", "default": 0},
            }
        }

        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Extract input schema
        inputs = resource_manager._extract_workflow_inputs(built_workflow)

        # Verify schema extracted from metadata
        assert "name" in inputs
        assert inputs["name"]["type"] == "string"
        assert inputs["name"]["required"] is True
        assert "age" in inputs
        assert inputs["age"]["default"] == 0

    def test_workflow_output_schema_extraction(self):
        """Test extracting workflow output schemas from metadata.

        Tests _extract_workflow_outputs() with explicit metadata.
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "generate",
            {"code": "result = {'status': 'success', 'data': []}"},
        )
        built_workflow = workflow.build()

        # Add output schema to metadata
        built_workflow.metadata = {
            "output_schema": {"status": {"type": "string"}, "data": {"type": "array"}}
        }

        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Extract output schema
        outputs = resource_manager._extract_workflow_outputs(built_workflow)

        # Verify schema extracted
        assert "status" in outputs
        assert outputs["status"]["type"] == "string"
        assert "data" in outputs
        assert outputs["data"]["type"] == "array"

    def test_documentation_resource_retrieval(self):
        """Test retrieving documentation resources.

        Tests _get_documentation() method with predefined docs.
        NO MOCKING - uses real documentation content.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Get quickstart documentation
        quickstart = resource_manager._get_documentation("quickstart")
        assert quickstart is not None
        assert "# Nexus Quick Start Guide" in quickstart
        assert "pip install kailash-nexus" in quickstart

        # Get API documentation
        api_docs = resource_manager._get_documentation("api")
        assert api_docs is not None
        assert "# Nexus API Reference" in api_docs
        assert "/workflows/{name}" in api_docs

        # Get MCP documentation
        mcp_docs = resource_manager._get_documentation("mcp")
        assert mcp_docs is not None
        assert "# MCP Integration Guide" in mcp_docs
        assert "ws://localhost:3001" in mcp_docs

        # Test non-existent documentation
        missing = resource_manager._get_documentation("nonexistent")
        assert missing is None

    def test_mime_type_detection(self):
        """Test MIME type detection for resources.

        Tests _get_mime_type() with various file extensions.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Test various MIME types
        assert resource_manager._get_mime_type("file.json") == "application/json"
        assert resource_manager._get_mime_type("file.xml") == "application/xml"
        assert resource_manager._get_mime_type("file.txt") == "text/plain"
        assert resource_manager._get_mime_type("file.md") == "text/markdown"
        assert resource_manager._get_mime_type("file.html") == "text/html"
        assert resource_manager._get_mime_type("file.py") == "text/x-python"
        assert resource_manager._get_mime_type("file.yaml") == "application/x-yaml"
        assert resource_manager._get_mime_type("file.yml") == "application/x-yaml"
        assert (
            resource_manager._get_mime_type("file.unknown")
            == "application/octet-stream"
        )

    def test_resource_security_checks(self):
        """Test security checks for resource access.

        Tests _is_allowed_resource() with forbidden patterns.
        NO MOCKING - real security validation.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Test allowed paths
        assert resource_manager._is_allowed_resource("data/public.json") is True
        assert resource_manager._is_allowed_resource("docs/readme.md") is True

        # Test forbidden paths
        assert resource_manager._is_allowed_resource("../etc/passwd") is False
        assert resource_manager._is_allowed_resource("/etc/shadow") is False
        assert resource_manager._is_allowed_resource("secret_data.json") is False
        assert resource_manager._is_allowed_resource("password_file.txt") is False
        assert resource_manager._is_allowed_resource("api_key.json") is False
        assert resource_manager._is_allowed_resource(".env") is False

    def test_configuration_resource_retrieval(self):
        """Test retrieving configuration resources.

        Tests _get_configuration() with platform config.
        """
        nexus = Nexus(
            api_port=8005,
            mcp_port=3006,
            enable_auth=True,
            enable_monitoring=True,
            auto_discovery=False,
            enable_durability=False,
        )
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Get platform configuration
        platform_config = resource_manager._get_configuration("platform")

        # Verify configuration content
        assert platform_config["name"] == "Kailash Nexus"
        assert platform_config["api_port"] == 8005
        assert platform_config["mcp_port"] == 3006
        assert platform_config["features"]["auth"] is True
        assert platform_config["features"]["monitoring"] is True

        # Get workflows configuration
        nexus._workflows["test_wf"] = object()  # Add a workflow
        workflows_config = resource_manager._get_configuration("workflows")
        assert workflows_config["count"] == 1
        assert "test_wf" in workflows_config["registered"]

        # Get limits configuration
        limits_config = resource_manager._get_configuration("limits")
        assert "rate_limit" in limits_config
        assert "max_workflows" in limits_config

        # Test unknown configuration key
        unknown = resource_manager._get_configuration("unknown_key")
        assert "error" in unknown

    def test_help_content_retrieval(self):
        """Test retrieving help content for topics.

        Tests _get_help_content() with various topics.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Get getting-started help
        getting_started = resource_manager._get_help_content("getting-started")
        assert "# Getting Started with Nexus" in getting_started
        assert "docs://quickstart" in getting_started

        # Get workflows help
        workflows_help = resource_manager._get_help_content("workflows")
        assert "# Working with Workflows" in workflows_help

        # Get troubleshooting help
        troubleshooting = resource_manager._get_help_content("troubleshooting")
        assert "# Troubleshooting" in troubleshooting
        assert "Port already in use" in troubleshooting

        # Get help for unknown topic (should return generic help)
        unknown_help = resource_manager._get_help_content("unknown_topic")
        assert "unknown_topic" in unknown_help
        assert "Available help topics:" in unknown_help

    def test_data_resource_security_isolation(self):
        """Test that data resources are properly isolated and secured.

        Tests _get_data_content() with path traversal attempts.
        NO MOCKING - real file system security checks.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        mcp_server = MCPServer("test_server")
        resource_manager = NexusResourceManager(mcp_server, nexus)

        # Test example data
        example_data = resource_manager._get_data_content("examples/sample.json")
        assert example_data is not None
        parsed = json.loads(example_data)
        assert "example" in parsed

        # Test path traversal attempt (should return None due to security check)
        malicious_path = "../../../etc/passwd"
        result = resource_manager._get_data_content(malicious_path)
        assert result is None  # Security check should prevent access
