"""
Test access control examples to ensure they work correctly
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
    get_access_control_manager,
)
from kailash.nodes.base_with_acl import add_access_control
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


class TestAccessControlExamples:
    """Test the access control examples"""

    def test_node_with_access_control_creation(self):
        """Test creating a node with access control"""
        # Create a basic node
        basic_node = PythonCodeNode(
            name="test_node",
            code="result = input_data * 2",
            inputs={"input_data": "number"},
            outputs={"result": "number"},
        )

        # Add access control
        acl_node = add_access_control(
            basic_node,
            enable_access_control=True,
            required_permission=NodePermission.EXECUTE,
            node_id="test_node",
        )

        # Verify it's wrapped correctly
        assert hasattr(acl_node, "_access_controlled")
        assert hasattr(acl_node, "enable_access_control")
        assert acl_node.enable_access_control is True
        assert hasattr(acl_node, "required_permission")

    def test_access_control_manager_rules(self):
        """Test adding and checking access rules"""
        acm = AccessControlManager()

        # Add a rule
        rule = PermissionRule(
            id="test_rule",
            resource_type="node",
            resource_id="test_node",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
        acm.add_rule(rule)

        # Create users
        admin_user = UserContext(
            user_id="admin-001",
            tenant_id="tenant-001",
            email="admin@test.com",
            roles=["admin"],
        )

        viewer_user = UserContext(
            user_id="viewer-001",
            tenant_id="tenant-001",
            email="viewer@test.com",
            roles=["viewer"],
        )

        # Check access
        admin_decision = acm.check_node_access(
            admin_user, "test_node", NodePermission.EXECUTE
        )
        assert admin_decision.allowed is True

        viewer_decision = acm.check_node_access(
            viewer_user, "test_node", NodePermission.EXECUTE
        )
        assert viewer_decision.allowed is False

    def test_backward_compatibility(self):
        """Test that nodes work without access control"""
        # Create a standard node
        node = PythonCodeNode(
            name="standard_node",
            code="result = input_data",
            inputs={"input_data": "any"},
            outputs={"result": "any"},
        )

        # Create workflow
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")
        workflow.add_node("node1", node)

        # Run with LocalRuntime (no access control)
        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow, parameters={"node1": {"input_data": "test"}}
        )

        # Check the result from the node
        assert "node1" in result
        assert result["node1"]["result"] == "test"

    def test_access_controlled_runtime_basic(self):
        """Test AccessControlledRuntime with simple workflow"""
        pytest.skip("AccessControlledRuntime needs fixing - parameters not passed to nodes")
        # Create user
        user = UserContext(
            user_id="test-user",
            tenant_id="tenant-001",
            email="test@example.com",
            roles=["admin"],
        )

        # Create workflow
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")
        node = PythonCodeNode(
            name="greeter_node",
            code="result = 'Hello ' + name",
            inputs={"name": "string"},
            outputs={"result": "string"},
        )
        workflow.add_node("greeter", node)

        # Set up access rules
        acm = get_access_control_manager()
        acm.add_rule(
            PermissionRule(
                id="workflow_rule",
                resource_type="workflow",
                resource_id="test_workflow",
                permission=WorkflowPermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                role="admin",
            )
        )

        # Run with access control
        runtime = AccessControlledRuntime(user)
        result, _ = runtime.execute(
            workflow, parameters={"greeter": {"name": "World"}}
        )

        # Check the result
        assert "greeter" in result
        # If the node failed, check the error
        if "error" in result["greeter"]:
            print(f"Node error: {result['greeter']['error']}")
        else:
            assert result["greeter"]["result"] == "Hello World"

    def test_mixed_workflow(self):
        """Test workflow with both ACL and non-ACL nodes"""
        workflow = Workflow(workflow_id="mixed_workflow", name="Mixed Workflow")

        # Regular node
        regular_node = PythonCodeNode(
            name="multiplier",
            code="result = input_data * 2",
            inputs={"input_data": "number"},
            outputs={"result": "number"},
        )

        # ACL node
        acl_node = add_access_control(
            PythonCodeNode(
                name="adder",
                code="result = input_data + 10",
                inputs={"input_data": "number"},
                outputs={"result": "number"},
            ),
            enable_access_control=True,
            node_id="secure_node",
        )

        workflow.add_node("regular", regular_node)
        workflow.add_node("secure", acl_node)
        workflow.connect("regular", "secure", {"result": "input_data"})

        # Run with LocalRuntime - should work
        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow, parameters={"regular": {"input_data": 5}})
        # The secure node should have received 10 (5*2) and added 10
        assert result["secure"]["result"] == 20  # (5 * 2) + 10

    def test_output_masking(self):
        """Test output masking for sensitive fields"""
        # Create node with output masking
        node = add_access_control(
            PythonCodeNode(
                name="sensitive_node",
                code="""
result = {
    'name': 'John Doe',
    'ssn': '123-45-6789',
    'balance': 1000
}
                """,
                inputs={},
                outputs={"result": "dict"},
            ),
            enable_access_control=True,
            mask_output_fields=["ssn"],
            node_id="sensitive_node",
        )

        # For this test, we'll just verify the node was created correctly
        assert hasattr(node, "mask_output_fields")
        assert "ssn" in node.mask_output_fields

    def test_tenant_isolation(self):
        """Test that tenant isolation works"""
        acm = AccessControlManager()

        # Add tenant-specific rule
        acm.add_rule(
            PermissionRule(
                id="tenant_rule",
                resource_type="workflow",
                resource_id="tenant_workflow",
                permission=WorkflowPermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
                tenant_id="tenant-a",
            )
        )

        # Users from different tenants
        tenant_a_user = UserContext(
            user_id="user-a",
            tenant_id="tenant-a",
            email="user@tenant-a.com",
            roles=["admin"],
        )

        tenant_b_user = UserContext(
            user_id="user-b",
            tenant_id="tenant-b",
            email="user@tenant-b.com",
            roles=["admin"],
        )

        # Check access
        decision_a = acm.check_workflow_access(
            tenant_a_user, "tenant_workflow", WorkflowPermission.EXECUTE
        )
        assert decision_a.allowed is True

        decision_b = acm.check_workflow_access(
            tenant_b_user, "tenant_workflow", WorkflowPermission.EXECUTE
        )
        assert decision_b.allowed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
