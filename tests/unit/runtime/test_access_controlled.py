"""
Unit tests for kailash.runtime.access_controlled module.

Tests the AccessControlledRuntime class which provides access control wrapper
around the standard LocalRuntime. Tests cover:
- Basic runtime functionality
- Access control integration
- Permission validation
- Error handling
- Edge cases and security scenarios

NO MOCKING - Tests verify actual runtime behavior with real components.
"""

from unittest.mock import patch

import pytest
from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
    get_access_control_manager,
)
from kailash.nodes.base import Node
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class TestAccessControlledRuntime:
    """Test AccessControlledRuntime class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure nodes are properly registered
        from tests.node_registry_utils import ensure_nodes_registered

        ensure_nodes_registered()

    def test_init_with_user_context(self):
        """Test initialization with user context."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        runtime = AccessControlledRuntime(user_context=user)

        assert runtime.user_context == user
        assert isinstance(runtime.base_runtime, LocalRuntime)

    def test_init_with_custom_runtime(self):
        """Test initialization with custom runtime."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["admin"],
        )
        custom_runtime = LocalRuntime()

        runtime = AccessControlledRuntime(
            user_context=user, base_runtime=custom_runtime
        )

        assert runtime.user_context == user
        assert runtime.base_runtime is custom_runtime

    def test_execute_with_disabled_access_control(self, mock_node_factory):
        """Test execute method when access control is disabled (default)."""
        # Create a test node using the factory
        TestNode = mock_node_factory("TestNode", execute_return={"result": 5.0})

        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # Create a simple workflow
        builder = WorkflowBuilder()
        builder.add_node("TestNode", "test_node", {"value": 2.5})
        workflow = builder.build()

        # Should execute without access control checks (default behavior)
        with AccessControlledRuntime(user_context=user) as runtime:
            result, run_id = runtime.execute(workflow)

        assert result is not None
        assert run_id is not None
        assert "test_node" in result
        assert result["test_node"]["result"] == 5.0

    def test_execute_with_enabled_access_control_allowed(self, mock_node_factory):
        """Test execute method with access control enabled and permission granted."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # Create a test node using the factory
        TestNode = mock_node_factory("TestNode", execute_return={"result": "allowed"})

        # Enable access control and grant permissions
        acm = get_access_control_manager()
        acm.enabled = False
        acm.rules.clear()
        acm._cache.clear()
        acm.enabled = True

        # Add workflow permission
        workflow_rule = PermissionRule(
            id="test_workflow_rule",
            resource_type="workflow",
            resource_id="test_workflow",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            user_id="test_user",
        )
        acm.add_rule(workflow_rule)

        try:
            # Create workflow
            builder = WorkflowBuilder()
            builder.add_node(
                "TestNode",
                "test_node",
                {},
            )
            workflow = builder.build()
            workflow.workflow_id = "test_workflow"

            # Should execute successfully
            with AccessControlledRuntime(user_context=user) as runtime:
                result, run_id = runtime.execute(workflow)

            assert result is not None
            assert run_id is not None
            assert "test_node" in result
            assert result["test_node"]["result"] == "allowed"

        finally:
            # Cleanup
            acm.enabled = False
            acm.rules.clear()

    def test_execute_with_enabled_access_control_denied(self):
        """Test execute method with access control enabled and permission denied."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # Enable access control without granting permissions
        acm = get_access_control_manager()
        acm.enabled = False  # Reset first
        acm.rules.clear()  # Clear any existing rules
        acm._cache.clear()  # Clear cache
        acm.enabled = True

        try:
            # Create workflow
            builder = WorkflowBuilder()
            builder.add_node(
                "PythonCodeNode",
                "test_node",
                {"code": "result = {'result': 'should_not_execute'}"},
            )
            workflow = builder.build()
            workflow.workflow_id = "test_workflow"

            # Should raise PermissionError due to no matching rules
            with pytest.raises(PermissionError, match="Access denied"):
                with AccessControlledRuntime(user_context=user) as runtime:
                    runtime.execute(workflow)

        finally:
            # Cleanup
            acm.enabled = False
            acm.rules.clear()

    def test_create_controlled_workflow(self, mock_node_factory):
        """Test _create_controlled_workflow method."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        runtime = AccessControlledRuntime(user_context=user)

        # Create a simple test node using the factory to avoid registry conflicts
        TestNode = mock_node_factory("SimpleTestNode2", execute_return={"result": 8.0})

        # Create original workflow
        builder = WorkflowBuilder()
        builder.add_node("SimpleTestNode2", "test_node", {"value": 4.0})
        original_workflow = builder.build()

        # Create controlled workflow
        controlled_workflow = runtime._create_controlled_workflow(original_workflow)

        assert controlled_workflow is not original_workflow
        assert controlled_workflow.workflow_id == original_workflow.workflow_id
        assert len(controlled_workflow.graph.nodes) == len(
            original_workflow.graph.nodes
        )

        # Verify node is wrapped
        controlled_node_data = controlled_workflow.graph.nodes["test_node"]
        original_node_data = original_workflow.graph.nodes["test_node"]
        assert controlled_node_data is not original_node_data
        assert "node" in controlled_node_data

    def test_create_controlled_node(self):
        """Test _create_controlled_node method."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        runtime = AccessControlledRuntime(user_context=user)

        # Create original node
        from kailash.nodes.code.python import PythonCodeNode

        original_node = PythonCodeNode(
            name="test_node", code="result = {'result': 'original'}"
        )

        # Create controlled node
        controlled_node = runtime._create_controlled_node("test_node", original_node)

        assert controlled_node is not original_node
        assert hasattr(controlled_node, "_original_node")
        assert controlled_node._original_node is original_node
        assert controlled_node._node_id == "test_node"

    def test_controlled_node_execution_allowed(self):
        """Test controlled node execution when permission is granted."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        runtime = AccessControlledRuntime(user_context=user)

        # Enable access control and grant permission
        acm = get_access_control_manager()
        acm.enabled = False
        acm.rules.clear()
        acm._cache.clear()
        acm.enabled = True

        # Grant both execute and read permissions
        execute_rule = PermissionRule(
            id="test_node_execute_rule",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            user_id="test_user",
        )
        acm.add_rule(execute_rule)

        read_rule = PermissionRule(
            id="test_node_read_rule",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.READ_OUTPUT,
            effect=PermissionEffect.ALLOW,
            user_id="test_user",
        )
        acm.add_rule(read_rule)

        try:
            # Create controlled node
            from kailash.nodes.code.python import PythonCodeNode

            original_node = PythonCodeNode(
                name="test_node", code="result = {'result': 'allowed'}"
            )

            controlled_node = runtime._create_controlled_node(
                "test_node", original_node
            )

            # Should execute successfully
            result = controlled_node.run()
            assert result["result"]["result"] == "allowed"

        finally:
            # Cleanup
            acm.enabled = False
            acm.rules.clear()

    def test_controlled_node_execution_denied(self):
        """Test controlled node execution when permission is denied."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        runtime = AccessControlledRuntime(user_context=user)

        # Enable access control without granting permission
        acm = get_access_control_manager()
        acm.enabled = False
        acm.rules.clear()
        acm._cache.clear()
        acm.enabled = True

        try:
            # Create controlled node
            from kailash.nodes.code.python import PythonCodeNode

            original_node = PythonCodeNode(
                name="test_node", code="result = {'result': 'should_not_execute'}"
            )

            controlled_node = runtime._create_controlled_node(
                "test_node", original_node
            )

            # Should return empty result (not raise exception)
            result = controlled_node.run()
            assert result == {}

        finally:
            # Cleanup
            acm.enabled = False
            acm.rules.clear()

    def test_mask_fields_functionality(self):
        """Test _mask_fields static method."""
        data = {
            "public_field": "visible",
            "sensitive_field": "secret",
            "another_field": "also_secret",
            "nested": {"sensitive_field": "nested_secret"},
        }

        fields_to_mask = ["sensitive_field", "another_field"]

        masked_data = AccessControlledRuntime._mask_fields(data, fields_to_mask)

        assert masked_data["public_field"] == "visible"
        assert masked_data["sensitive_field"] == "***MASKED***"
        assert masked_data["another_field"] == "***MASKED***"
        # Nested fields should not be masked (only top-level)
        assert masked_data["nested"]["sensitive_field"] == "nested_secret"

    def test_mask_fields_empty_fields(self):
        """Test _mask_fields with empty fields list."""
        data = {"field1": "value1", "field2": "value2"}

        masked_data = AccessControlledRuntime._mask_fields(data, [])

        assert masked_data == data

    def test_mask_fields_nonexistent_fields(self):
        """Test _mask_fields with nonexistent fields."""
        data = {"field1": "value1", "field2": "value2"}

        masked_data = AccessControlledRuntime._mask_fields(data, ["nonexistent"])

        assert masked_data == data

    def test_edge_case_empty_workflow(self):
        """Test execution with empty workflow."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # Create empty workflow
        workflow = Workflow(workflow_id="empty", name="Empty Workflow")

        # Should handle empty workflow gracefully
        with AccessControlledRuntime(user_context=user) as runtime:
            result, run_id = runtime.execute(workflow)

        assert result is not None
        assert run_id is not None
        assert isinstance(result, dict)

    def test_error_handling_invalid_user_context(self):
        """Test error handling with invalid user context."""
        # This should not raise TypeError as the implementation doesn't validate types
        # It will just store the invalid value
        runtime = AccessControlledRuntime(user_context="invalid")
        assert runtime.user_context == "invalid"

    def test_error_handling_invalid_runtime(self):
        """Test error handling with invalid runtime."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # This should not raise TypeError as the implementation doesn't validate types
        # It will just store the invalid value
        runtime = AccessControlledRuntime(user_context=user, base_runtime="invalid")
        assert runtime.base_runtime == "invalid"

    def test_backward_compatibility(self, mock_node_factory):
        """Test that access control is disabled by default for backward compatibility."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # Access control should be disabled by default
        acm = get_access_control_manager()
        assert not acm.enabled

        # Create a test node using the factory
        TestNode = mock_node_factory(
            "TestNode", execute_return={"result": "backward_compatible"}
        )

        # Should execute without any access control checks
        builder = WorkflowBuilder()
        builder.add_node(
            "TestNode",
            "test_node",
            {},
        )
        workflow = builder.build()

        with AccessControlledRuntime(user_context=user) as runtime:
            result, run_id = runtime.execute(workflow)

        assert result is not None
        assert result["test_node"]["result"] == "backward_compatible"

    def test_security_scenarios(self):
        """Test various security scenarios."""
        user = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["analyst"],
        )

        # Test with potentially malicious code
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test_node",
            {
                "code": """
import os
try:
    # This should be controlled by access control
    os.environ['TEST_VAR'] = 'set_by_node'
    result = {'result': 'potentially_dangerous'}
except Exception as e:
    result = {'error': str(e)}
"""
            },
        )
        workflow = builder.build()

        # Should execute (access control disabled by default)
        with AccessControlledRuntime(user_context=user) as runtime:
            result, run_id = runtime.execute(workflow)

        assert result is not None
        assert "test_node" in result
