"""Tier 3 E2E Tests for Complete User Workflows (NO MOCKING).

Tests realistic end-to-end user scenarios including workflow discovery,
session management, and cross-channel operations.
"""

import os
import tempfile
from pathlib import Path

import pytest
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus
from nexus.channels import create_session_manager
from nexus.discovery import discover_workflows


@pytest.mark.e2e
class TestWorkflowDiscoveryUserFlowE2E:
    """E2E tests for workflow discovery user flows."""

    def test_user_creates_workflows_and_nexus_discovers_them(self):
        """Test complete workflow: user creates files, Nexus discovers them.

        CRITICAL E2E: Real user workflow from file creation to discovery.
        NO MOCKING - uses real file system and discovery.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: User creates workflow files
            workflows_dir = Path(tmpdir) / "workflows"
            workflows_dir.mkdir()

            # User workflow 1: Data validation
            (workflows_dir / "validate_data.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

def create_validation_workflow():
    '''User-created validation workflow'''
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "validate", {
        "code": '''
if not data:
    result = {"valid": False, "error": "No data"}
elif not isinstance(data, dict):
    result = {"valid": False, "error": "Data must be dict"}
else:
    result = {"valid": True, "data": data}
'''
    })

    return workflow.build()

validation = create_validation_workflow()
"""
            )

            # User workflow 2: Data transformation
            (workflows_dir / "transform_data.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

transform_workflow = WorkflowBuilder()
transform_workflow.add_node("PythonCodeNode", "transform", {
    "code": '''
# Transform data to uppercase
transformed = {k: v.upper() if isinstance(v, str) else v
               for k, v in input_data.items()}
result = {"transformed": transformed, "count": len(transformed)}
'''
})
"""
            )

            # Step 2: Nexus discovers workflows
            discovered = discover_workflows(tmpdir)

            # Step 3: Verify discovery results
            assert len(discovered) >= 2

            # Step 4: User initializes Nexus and registers discovered workflows
            nexus = Nexus(
                api_port=8020,
                mcp_port=3020,
                auto_discovery=False,
                enable_durability=False,
            )

            try:
                # Register discovered workflows
                for name, workflow in discovered.items():
                    nexus.register(name, workflow)

                # Verify all workflows registered
                assert len(nexus._workflows) >= 2

                # Workflows now accessible via all channels
                for name in discovered.keys():
                    assert name in nexus._workflows

            finally:
                if hasattr(nexus, "shutdown"):
                    nexus.shutdown()

    def test_user_deploys_project_with_auto_discovery(self):
        """Test user deploys project directory and Nexus auto-discovers workflows.

        E2E Test: Simulates real project deployment scenario.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: User sets up project structure
            project_root = Path(tmpdir)

            # Create app directory
            app_dir = project_root / "app"
            app_dir.mkdir()

            # Create workflows subdirectory
            workflows_dir = app_dir / "workflows"
            workflows_dir.mkdir()

            # Step 2: User creates multiple workflow files
            (workflows_dir / "auth_workflow.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

auth_flow = WorkflowBuilder()
auth_flow.add_node("PythonCodeNode", "authenticate", {
    "code": "result = {'authenticated': True, 'user_id': user}"
})
"""
            )

            (workflows_dir / "data_workflow.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

data_flow = WorkflowBuilder()
data_flow.add_node("PythonCodeNode", "fetch_data", {
    "code": "result = {'data': [1, 2, 3], 'count': 3}"
})
"""
            )

            # Step 3: User discovers workflows from project
            discovered = discover_workflows(str(project_root))

            # Step 4: Verify workflows found
            assert len(discovered) >= 2

            # Step 5: User initializes and deploys
            nexus = Nexus(
                api_port=8021,
                mcp_port=3021,
                auto_discovery=False,
                enable_durability=False,
            )

            try:
                # Bulk register all discovered workflows
                for workflow_name, workflow in discovered.items():
                    nexus.register(workflow_name, workflow)

                # All workflows now deployed
                assert len(nexus._workflows) >= 2

            finally:
                if hasattr(nexus, "shutdown"):
                    nexus.shutdown()


@pytest.mark.e2e
class TestSessionManagementUserFlowE2E:
    """E2E tests for session management across user interactions."""

    def test_user_session_across_multiple_channels(self):
        """Test user session persisting across API, CLI, and MCP channels.

        CRITICAL E2E: Real session management across channels.
        NO MOCKING - uses real session manager.
        """
        # Step 1: Create session manager
        session_manager = create_session_manager()

        # Step 2: User starts session via API
        api_session = session_manager.create_session("user_session_123", "api")

        # Verify initial session state
        assert api_session["id"] == "user_session_123"
        assert api_session["created_by"] == "api"
        assert api_session["channels"] == ["api"]

        # Step 3: User updates session with data (e.g., user preferences)
        session_manager.update_session(
            "user_session_123",
            {"user_id": "user_456", "theme": "dark", "language": "en"},
        )

        # Step 4: User switches to CLI channel
        cli_session = session_manager.sync_session("user_session_123", "cli")

        # Session should sync with user data preserved
        assert cli_session is not None
        assert "cli" in cli_session["channels"]
        assert "api" in cli_session["channels"]
        assert cli_session["data"]["user_id"] == "user_456"
        assert cli_session["data"]["theme"] == "dark"

        # Step 5: User accesses via MCP channel
        mcp_session = session_manager.sync_session("user_session_123", "mcp")

        # Session accessible from all three channels
        assert "mcp" in mcp_session["channels"]
        assert len(mcp_session["channels"]) == 3
        assert all(ch in mcp_session["channels"] for ch in ["api", "cli", "mcp"])

        # Step 6: User updates preferences from MCP
        session_manager.update_session(
            "user_session_123",
            {"theme": "light", "notifications": True},  # Changed preference
        )

        # Step 7: User goes back to API - changes should persist
        final_session = session_manager.sync_session("user_session_123", "api")
        assert final_session["data"]["theme"] == "light"  # Updated value
        assert final_session["data"]["notifications"] is True

    def test_multi_user_session_isolation(self):
        """Test that different user sessions are properly isolated.

        E2E Test: Validates session isolation in multi-user scenario.
        """
        session_manager = create_session_manager()

        # User 1 creates session
        user1_session = session_manager.create_session("user1_session", "api")
        session_manager.update_session(
            "user1_session", {"user_id": "user_001", "role": "admin"}
        )

        # User 2 creates session
        user2_session = session_manager.create_session("user2_session", "api")
        session_manager.update_session(
            "user2_session", {"user_id": "user_002", "role": "viewer"}
        )

        # User 3 creates session
        user3_session = session_manager.create_session("user3_session", "cli")
        session_manager.update_session(
            "user3_session", {"user_id": "user_003", "role": "editor"}
        )

        # Retrieve and verify isolation
        retrieved_user1 = session_manager.sync_session("user1_session", "api")
        retrieved_user2 = session_manager.sync_session("user2_session", "api")
        retrieved_user3 = session_manager.sync_session("user3_session", "cli")

        # Each session should have distinct data
        assert retrieved_user1["data"]["user_id"] == "user_001"
        assert retrieved_user1["data"]["role"] == "admin"

        assert retrieved_user2["data"]["user_id"] == "user_002"
        assert retrieved_user2["data"]["role"] == "viewer"

        assert retrieved_user3["data"]["user_id"] == "user_003"
        assert retrieved_user3["data"]["role"] == "editor"

        # Sessions should not interfere
        assert retrieved_user1["data"] != retrieved_user2["data"]
        assert retrieved_user2["data"] != retrieved_user3["data"]


@pytest.mark.e2e
class TestEnterpriseWorkflowDeploymentE2E:
    """E2E tests for enterprise workflow deployment scenarios."""

    def test_production_deployment_with_all_features(self):
        """Test production deployment with auth, monitoring, and rate limiting.

        CRITICAL E2E: Real production-like deployment scenario.
        """
        from nexus.plugins import AuthPlugin, MonitoringPlugin, RateLimitPlugin

        # Step 1: Initialize Nexus with production configuration
        nexus = Nexus(
            api_port=8022,
            mcp_port=3022,
            enable_auth=False,  # Will apply via plugin
            enable_monitoring=False,  # Will apply via plugin
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Step 2: Apply enterprise plugins
            AuthPlugin().apply(nexus)
            MonitoringPlugin().apply(nexus)
            RateLimitPlugin(requests_per_minute=1000).apply(nexus)

            # Step 3: Deploy critical workflows
            # Order processing workflow
            order_workflow = WorkflowBuilder()
            order_workflow.add_node(
                "PythonCodeNode",
                "validate_order",
                {
                    "code": """
result = {
    "order_id": order_id,
    "valid": True,
    "timestamp": "2024-01-01T00:00:00Z"
}
"""
                },
            )
            order_workflow.add_node(
                "PythonCodeNode",
                "process_payment",
                {
                    "code": """
result = {
    "payment_status": "success",
    "transaction_id": "txn_123",
    "amount": total
}
"""
                },
            )
            order_workflow.add_connection(
                "validate_order", "result", "process_payment", "order_data"
            )
            nexus.register("order_processing", order_workflow.build())

            # Inventory management workflow
            inventory_workflow = WorkflowBuilder()
            inventory_workflow.add_node(
                "PythonCodeNode",
                "check_stock",
                {
                    "code": """
result = {
    "product_id": product_id,
    "in_stock": True,
    "quantity": 50
}
"""
                },
            )
            nexus.register("inventory_check", inventory_workflow.build())

            # Customer service workflow
            support_workflow = WorkflowBuilder()
            support_workflow.add_node(
                "PythonCodeNode",
                "create_ticket",
                {
                    "code": """
result = {
    "ticket_id": "TICK-001",
    "customer_id": customer_id,
    "status": "open"
}
"""
                },
            )
            nexus.register("support_ticket", support_workflow.build())

            # Step 4: Verify production deployment
            assert len(nexus._workflows) == 3

            # All enterprise features enabled
            assert nexus._auth_enabled is True
            assert nexus._monitoring_enabled is True
            assert nexus._rate_limit == 1000

            # All workflows registered and protected
            assert "order_processing" in nexus._workflows
            assert "inventory_check" in nexus._workflows
            assert "support_ticket" in nexus._workflows

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()

    def test_workflow_versioning_and_updates(self):
        """Test deploying and updating workflow versions.

        E2E Test: Validates workflow update scenarios.
        """
        nexus = Nexus(
            api_port=8023,
            mcp_port=3023,
            auto_discovery=False,
            enable_durability=False,
        )

        try:
            # Step 1: Deploy v1.0 of workflow
            workflow_v1 = WorkflowBuilder()
            workflow_v1.add_node(
                "PythonCodeNode",
                "process_v1",
                {"code": "result = {'version': '1.0', 'features': ['basic']}"},
            )
            built_v1 = workflow_v1.build()
            built_v1.metadata = {"version": "1.0"}

            nexus.register("data_processor", built_v1)

            # Verify v1 deployed
            assert nexus._workflows["data_processor"].metadata["version"] == "1.0"

            # Step 2: Deploy v2.0 (update)
            workflow_v2 = WorkflowBuilder()
            workflow_v2.add_node(
                "PythonCodeNode",
                "process_v2",
                {
                    "code": "result = {'version': '2.0', 'features': ['basic', 'advanced']}"
                },
            )
            built_v2 = workflow_v2.build()
            built_v2.metadata = {"version": "2.0"}

            nexus.register("data_processor", built_v2)  # Update existing

            # Verify v2 replaced v1
            assert nexus._workflows["data_processor"].metadata["version"] == "2.0"

        finally:
            if hasattr(nexus, "shutdown"):
                nexus.shutdown()
