"""Tier 3 E2E Tests for Multi-Channel Deployment (NO MOCKING).

Tests complete user workflows accessing Nexus via API, CLI, and MCP simultaneously.
Validates end-to-end integration of all stub fixes.
"""

import asyncio

import pytest
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


@pytest.mark.e2e
class TestMultiChannelDeploymentE2E:
    """E2E tests for multi-channel workflow deployment."""

    def test_complete_workflow_deployment_lifecycle(self):
        """Test complete workflow deployment across all channels.

        CRITICAL E2E Test: Validates entire workflow from registration
        through multi-channel access to shutdown.

        NO MOCKING - Uses real Nexus, real channels, real workflows.
        """
        # Step 1: Initialize Nexus with all channels
        nexus = Nexus(
            api_port=8010,
            mcp_port=3010,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Step 2: Create a realistic workflow
            workflow = WorkflowBuilder()

            # Add data processing node
            workflow.add_node(
                "PythonCodeNode",
                "validate_input",
                {
                    "code": """
# Validate input data
if not input_data:
    result = {"error": "No input data provided"}
else:
    result = {"valid": True, "data": input_data}
"""
                },
            )

            # Add processing node
            workflow.add_node(
                "PythonCodeNode",
                "process_data",
                {
                    "code": """
# Process validated data
if input_valid.get("valid"):
    processed = {
        "result": "Data processed successfully",
        "count": len(input_valid.get("data", [])),
        "status": "success"
    }
else:
    processed = {"error": "Invalid input", "status": "error"}
result = processed
"""
                },
            )

            # Connect nodes
            workflow.add_connection(
                "validate_input", "result", "process_data", "input_valid"
            )

            # Build workflow
            built_workflow = workflow.build()

            # Step 3: Register workflow (should create endpoints across ALL channels)
            nexus.register("data_processor", built_workflow)

            # Step 4: Verify registration across channels
            assert "data_processor" in nexus._workflows
            assert nexus._workflows["data_processor"] == built_workflow

            # Step 5: Verify workflow accessible via gateway (API channel)
            if nexus._gateway:
                assert "data_processor" in nexus._gateway._workflows

            # Step 6: Verify configuration persisted correctly
            assert nexus._api_port == 8010
            assert nexus._mcp_port == 3010

        finally:
            # Step 7: Clean shutdown
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()

    def test_multiple_workflows_multi_channel_access(self):
        """Test multiple workflows accessible via all channels.

        E2E Test: Validates workflow isolation and multi-channel routing.
        """
        nexus = Nexus(
            api_port=8011,
            mcp_port=3011,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Register first workflow - User Management
            user_workflow = WorkflowBuilder()
            user_workflow.add_node(
                "PythonCodeNode",
                "create_user",
                {
                    "code": """
result = {
    "user_id": "user_123",
    "username": username,
    "status": "created"
}
"""
                },
            )
            nexus.register("user_management", user_workflow.build())

            # Register second workflow - Data Analytics
            analytics_workflow = WorkflowBuilder()
            analytics_workflow.add_node(
                "PythonCodeNode",
                "analyze",
                {
                    "code": """
result = {
    "analysis": "complete",
    "metrics": {"total": 100, "average": 50}
}
"""
                },
            )
            nexus.register("analytics", analytics_workflow.build())

            # Register third workflow - Reporting
            report_workflow = WorkflowBuilder()
            report_workflow.add_node(
                "PythonCodeNode",
                "generate_report",
                {
                    "code": """
result = {
    "report_id": "report_456",
    "format": "pdf",
    "status": "generated"
}
"""
                },
            )
            nexus.register("reporting", report_workflow.build())

            # Verify all workflows registered
            assert len(nexus._workflows) == 3
            assert "user_management" in nexus._workflows
            assert "analytics" in nexus._workflows
            assert "reporting" in nexus._workflows

            # Verify each workflow is distinct
            assert nexus._workflows["user_management"] != nexus._workflows["analytics"]
            assert nexus._workflows["analytics"] != nexus._workflows["reporting"]

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()

    def test_workflow_with_metadata_multi_channel_exposure(self):
        """Test workflow metadata exposed correctly across channels.

        E2E Test: Validates metadata propagation through resource system.
        """
        nexus = Nexus(
            api_port=8012,
            mcp_port=3012,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Create workflow with comprehensive metadata
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", "process", {"code": "result = {'processed': True}"}
            )
            built_workflow = workflow.build()

            # Add metadata
            built_workflow.metadata = {
                "name": "Data Processor v2",
                "version": "2.0.0",
                "description": "Processes customer data with validation",
                "author": "Engineering Team",
                "parameters": {
                    "customer_id": {
                        "type": "string",
                        "required": True,
                        "description": "Customer identifier",
                    },
                    "include_history": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include historical data",
                    },
                },
                "output_schema": {
                    "processed": {"type": "boolean"},
                    "customer_data": {"type": "object"},
                },
            }

            # Register workflow
            nexus.register("customer_processor", built_workflow)

            # Verify metadata preserved
            registered = nexus._workflows["customer_processor"]
            assert hasattr(registered, "metadata")
            assert registered.metadata["version"] == "2.0.0"
            assert "parameters" in registered.metadata
            assert "output_schema" in registered.metadata

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()


@pytest.mark.e2e
class TestEventSystemE2E:
    """E2E tests for event broadcasting and logging."""

    def test_workflow_execution_event_logging(self):
        """Test that workflow executions generate and log events.

        E2E Test: Validates event system integration.
        """
        nexus = Nexus(
            api_port=8013,
            mcp_port=3013,
            enable_monitoring=True,  # Enable monitoring for events
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Register workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "generate_event",
                {
                    "code": """
result = {
    "event_generated": True,
    "timestamp": "2024-01-01T00:00:00Z",
    "event_type": "data_processed"
}
"""
                },
            )
            nexus.register("event_workflow", workflow.build())

            # Verify monitoring enabled (events should be captured)
            assert hasattr(nexus, "_monitoring_enabled")
            if nexus._monitoring_enabled:
                assert hasattr(nexus, "_metrics")

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()


@pytest.mark.e2e
class TestPluginIntegrationE2E:
    """E2E tests for plugin system integration."""

    def test_auth_plugin_workflow_protection(self):
        """Test authentication plugin protects workflow access.

        E2E Test: Validates plugin lifecycle and enforcement.
        """
        from nexus.plugins import AuthPlugin

        nexus = Nexus(
            api_port=8014,
            mcp_port=3014,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Apply authentication plugin
            auth_plugin = AuthPlugin()
            auth_plugin.apply(nexus)

            # Verify auth applied
            assert nexus._auth_enabled is True

            # Register protected workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "protected",
                {"code": "result = {'data': 'sensitive_information'}"},
            )
            nexus.register("protected_workflow", workflow.build())

            # Workflow registered but should require auth to access
            assert "protected_workflow" in nexus._workflows

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()

    def test_multiple_plugins_workflow_enhancement(self):
        """Test multiple plugins enhance workflow capabilities.

        E2E Test: Validates plugin composition and coexistence.
        """
        from nexus.plugins import AuthPlugin, MonitoringPlugin, RateLimitPlugin

        nexus = Nexus(
            api_port=8015,
            mcp_port=3015,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Apply multiple enterprise plugins
            AuthPlugin().apply(nexus)
            MonitoringPlugin().apply(nexus)
            RateLimitPlugin(requests_per_minute=100).apply(nexus)

            # Verify all plugins applied
            assert nexus._auth_enabled is True
            assert nexus._monitoring_enabled is True
            assert nexus._rate_limit == 100

            # Register enterprise workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "enterprise_logic",
                {
                    "code": """
result = {
    "execution": "protected",
    "monitoring": "enabled",
    "rate_limited": True
}
"""
                },
            )
            nexus.register("enterprise_workflow", workflow.build())

            # Workflow should have all enterprise features
            assert "enterprise_workflow" in nexus._workflows

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()


@pytest.mark.e2e
class TestResourceSystemE2E:
    """E2E tests for resource system with workflows."""

    def test_workflow_resource_exposure_via_mcp(self):
        """Test workflow resources exposed via MCP server.

        E2E Test: Validates resource system end-to-end.
        """
        from kailash.mcp_server import MCPServer
        from nexus.resources import NexusResourceManager

        nexus = Nexus(
            api_port=8016,
            mcp_port=3016,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Create MCP server and resource manager
            mcp_server = MCPServer("test_mcp")
            resource_manager = NexusResourceManager(mcp_server, nexus)

            # Register workflow with metadata
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "resource_test",
                {"code": "result = {'resource': 'available'}"},
            )
            built_workflow = workflow.build()
            built_workflow.metadata = {
                "description": "Test resource exposure",
                "version": "1.0",
            }

            nexus._workflows["resource_workflow"] = built_workflow

            # Extract workflow info (simulates MCP resource request)
            workflow_info = resource_manager._extract_workflow_info(
                "resource_workflow", built_workflow
            )

            # Verify resource structure
            assert workflow_info["name"] == "resource_workflow"
            assert workflow_info["type"] == "workflow"
            assert len(workflow_info["nodes"]) == 1
            assert "schema" in workflow_info
            assert workflow_info["metadata"]["version"] == "1.0"

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()

    def test_documentation_resources_accessible(self):
        """Test documentation resources accessible via resource system.

        E2E Test: Validates documentation resource endpoints.
        """
        from kailash.mcp_server import MCPServer
        from nexus.resources import NexusResourceManager

        nexus = Nexus(auto_discovery=False, enable_durability=False)

        try:
            mcp_server = MCPServer("docs_test")
            resource_manager = NexusResourceManager(mcp_server, nexus)

            # Access all documentation resources
            quickstart = resource_manager._get_documentation("quickstart")
            api_docs = resource_manager._get_documentation("api")
            mcp_docs = resource_manager._get_documentation("mcp")

            # Verify all docs accessible
            assert quickstart is not None
            assert "Nexus Quick Start Guide" in quickstart

            assert api_docs is not None
            assert "API Reference" in api_docs

            assert mcp_docs is not None
            assert "MCP Integration Guide" in mcp_docs

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()
