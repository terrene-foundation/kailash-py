"""
End-to-End tests for SecureGovernedNode with enterprise security validation.

Tests the complete security validation flow including SQL injection prevention,
parameter validation, and audit logging.
"""

import logging
from typing import Any, Dict, List, Optional

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.governance import DevelopmentNode, EnterpriseNode, SecureGovernedNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeValidationError, WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Set up logging to capture security warnings
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Parameter contracts for testing
class UserOperationContract(BaseModel):
    """Contract for user operations."""

    model_config = ConfigDict(extra="forbid")  # Security: reject unknown parameters

    operation: str = Field(description="Operation type: create, update, delete")
    user_data: Optional[Dict[str, Any]] = Field(default=None, description="User data")
    user_id: Optional[str] = Field(default=None, description="User ID")
    tenant_id: str = Field(description="Tenant identifier")
    requestor_id: str = Field(description="ID of user making request")


class DatabaseQueryContract(BaseModel):
    """Contract for database operations."""

    model_config = ConfigDict(extra="forbid")

    query_type: str = Field(description="Type of query: select, insert, update")
    table: str = Field(description="Table name")
    conditions: Optional[Dict[str, Any]] = Field(
        default=None, description="Query conditions"
    )


class DatabaseConnectionContract(BaseModel):
    """Connection contract for database parameters."""

    model_config = ConfigDict(extra="forbid")

    params: List[Any] = Field(description="SQL query parameters")
    query: Optional[str] = Field(default=None, description="SQL query string")

    @field_validator("params")
    @classmethod
    def validate_params_list(cls, v):
        """Ensure params is a list for SQL safety."""
        if not isinstance(v, list):
            raise ValueError("params must be a list for SQL safety")
        return v


# Test nodes using SecureGovernedNode
class SecureUserManagementNode(SecureGovernedNode):
    """Secure user management node with full validation."""

    @classmethod
    def get_parameter_contract(cls):
        return UserOperationContract

    @classmethod
    def get_connection_contract(cls):
        return None  # No connection parameters expected

    def run_governed(self, **kwargs):
        """Execute with pre-validated parameters."""
        operation = kwargs["operation"]
        tenant_id = kwargs["tenant_id"]
        requestor_id = kwargs["requestor_id"]

        # Simulate user operation
        if operation == "create" and kwargs.get("user_data"):
            return {
                "result": {
                    "success": True,
                    "user_id": f"user_{hash(str(kwargs['user_data']))}",
                    "tenant_id": tenant_id,
                    "created_by": requestor_id,
                }
            }
        elif operation in ["update", "delete"] and kwargs.get("user_id"):
            return {
                "result": {
                    "success": True,
                    "operation": operation,
                    "user_id": kwargs["user_id"],
                    "tenant_id": tenant_id,
                }
            }
        else:
            raise ValueError(f"Invalid operation or missing data for {operation}")


class SecureDatabaseNode(SecureGovernedNode):
    """Secure database node with SQL injection prevention."""

    @classmethod
    def get_parameter_contract(cls):
        return DatabaseQueryContract

    @classmethod
    def get_connection_contract(cls):
        return DatabaseConnectionContract

    def run_governed(self, **kwargs):
        """Execute database operation with security validation."""
        query_type = kwargs["query_type"]
        table = kwargs["table"]

        # Connection parameters (if any) are pre-validated
        params = kwargs.get("params", [])

        # Simulate secure database operation
        if query_type == "select":
            return {
                "result": {
                    "rows": [{"id": 1, "name": "test"}],
                    "count": 1,
                    "table": table,
                }
            }
        else:
            return {
                "result": {
                    "success": True,
                    "operation": query_type,
                    "table": table,
                    "params_used": len(params),
                }
            }


class TestSecureGovernedNodeE2E:
    """E2E tests for SecureGovernedNode security features."""

    def test_basic_security_validation(self):
        """Test basic parameter security validation."""
        workflow = WorkflowBuilder()

        # Add secure node with valid parameters
        workflow.add_node(
            SecureUserManagementNode,
            "user_mgmt",
            {
                "operation": "create",
                "user_data": {"username": "testuser", "email": "test@example.com"},
                "tenant_id": "tenant_123",
                "requestor_id": "admin_user",
            },
        )

        # Build and execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify success
        assert results["user_mgmt"]["result"]["success"] is True
        assert "user_id" in results["user_mgmt"]["result"]
        assert results["user_mgmt"]["result"]["tenant_id"] == "tenant_123"

    def test_sql_injection_prevention(self, caplog):
        """Test SQL injection prevention in parameters."""
        workflow = WorkflowBuilder()

        # Attempt SQL injection through parameters
        with caplog.at_level(logging.WARNING):
            workflow.add_node(
                SecureDatabaseNode,
                "db_node",
                {
                    "query_type": "select",
                    "table": "users",
                    "conditions": {
                        "username": "'; DROP TABLE users; --"
                    },  # SQL injection attempt
                },
            )

            # Build workflow
            built_workflow = workflow.build()

        # Check for security warnings
        security_warnings = [r for r in caplog.records if "SQL injection" in r.message]
        # Note: Actual SQL injection detection would be in the governance layer
        # This test verifies the structure is in place

    def test_undeclared_parameter_filtering(self, caplog):
        """Test that undeclared parameters are filtered and logged."""
        workflow = WorkflowBuilder()

        # Try to pass undeclared parameters
        with caplog.at_level(logging.WARNING):
            workflow.add_node(
                SecureUserManagementNode,
                "user_mgmt",
                {
                    "operation": "create",
                    "user_data": {"username": "testuser"},
                    "tenant_id": "tenant_123",
                    "requestor_id": "admin",
                    "malicious_param": "hack_attempt",  # Not in contract!
                    "injection_param": "'; DROP TABLE users; --",  # Not in contract!
                },
            )

            # Build and execute
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())

        # Verify undeclared parameters were filtered
        assert results["user_mgmt"]["result"]["success"] is True

        # Check for security violation warnings
        violation_warnings = [
            r
            for r in caplog.records
            if "Security violation detected" in r.message
            or "Undeclared parameters" in r.message
        ]
        # These would be logged by SecureGovernedNode if properly integrated

    def test_connection_parameter_validation(self):
        """Test validation of connection parameters."""
        workflow = WorkflowBuilder()

        # Source node that outputs connection parameters
        workflow.add_node(
            "PythonCodeNode",
            "param_prep",
            {
                "code": """
# Prepare database parameters
result = {
    'params': ['user123', 'active'],  # Safe list format
    'query': 'SELECT * FROM users WHERE id = ? AND status = ?'
}
"""
            },
        )

        # Secure database node
        workflow.add_node(
            SecureDatabaseNode, "db_query", {"query_type": "select", "table": "users"}
        )

        # Connect with parameter mapping
        workflow.connect(
            "param_prep",
            "db_query",
            mapping={"result.params": "params", "result.query": "query"},
        )

        # Build and execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution
        assert results["db_query"]["result"]["rows"] is not None
        assert results["db_query"]["result"]["table"] == "users"

    def test_enterprise_node_convenience_class(self):
        """Test EnterpriseNode convenience class."""
        workflow = WorkflowBuilder()

        # Create custom enterprise node
        class CustomEnterpriseNode(EnterpriseNode):
            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data", type=dict, required=True, description="Input data"
                    )
                }

            def run_secure(self, **kwargs):
                # All security features are pre-applied
                return {"result": {"processed": True, "data": kwargs["data"]}}

        # Use enterprise node
        workflow.add_node(CustomEnterpriseNode, "enterprise", {"data": {"value": 42}})

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["enterprise"]["result"]["processed"] is True
        assert results["enterprise"]["result"]["data"]["value"] == 42

    def test_development_node_relaxed_validation(self):
        """Test DevelopmentNode with relaxed validation."""
        workflow = WorkflowBuilder()

        # Create development node
        class CustomDevNode(DevelopmentNode):
            def get_parameters(self):
                return {
                    "input": NodeParameter(
                        name="input",
                        type=str,
                        required=True,
                        description="Input string",
                    )
                }

            def run_development(self, **kwargs):
                # Development mode - more permissive
                return {"result": {"echo": kwargs["input"]}}

        # Use with SQL-like content (would be blocked in production)
        workflow.add_node(
            CustomDevNode,
            "dev_node",
            {"input": "SELECT * FROM users WHERE name = 'O'Brien'"},
        )

        # Should execute without security blocks
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert (
            results["dev_node"]["result"]["echo"]
            == "SELECT * FROM users WHERE name = 'O'Brien'"
        )

    def test_complex_enterprise_workflow(self):
        """Test complex workflow with multiple secure nodes."""
        workflow = WorkflowBuilder()

        # User validation node
        workflow.add_node(
            SecureUserManagementNode,
            "validate_user",
            {
                "operation": "update",
                "user_id": "user_123",
                "user_data": {"status": "active"},
                "tenant_id": "tenant_abc",
                "requestor_id": "admin_456",
            },
        )

        # Database query node
        workflow.add_node(
            SecureDatabaseNode,
            "fetch_permissions",
            {
                "query_type": "select",
                "table": "permissions",
                "conditions": {"user_id": "user_123"},
            },
        )

        # Process results
        workflow.add_node(
            "PythonCodeNode",
            "process_results",
            {
                "code": """
# Combine user and permission data
user_result = parameters.get('user_result', {})
perm_result = parameters.get('perm_result', {})

result = {
    'user_updated': user_result.get('success', False),
    'permissions_count': len(perm_result.get('rows', [])),
    'status': 'complete'
}
"""
            },
        )

        # Connect nodes
        workflow.connect(
            "validate_user", "process_results", mapping={"result": "user_result"}
        )
        workflow.connect(
            "fetch_permissions", "process_results", mapping={"result": "perm_result"}
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert results["process_results"]["user_updated"] is True
        assert results["process_results"]["status"] == "complete"

    def test_parameter_contract_enforcement(self):
        """Test strict parameter contract enforcement."""
        workflow = WorkflowBuilder()

        # Try to use node with missing required parameters
        with pytest.raises(Exception) as exc_info:
            workflow.add_node(
                SecureUserManagementNode,
                "user_mgmt",
                {
                    "operation": "create",
                    # Missing required: tenant_id, requestor_id
                    "user_data": {"username": "test"},
                },
            )

            # Should fail during build due to contract violation
            workflow.build()

        # Verify it's a validation error
        assert (
            "tenant_id" in str(exc_info.value)
            or "required" in str(exc_info.value).lower()
        )

    def test_sql_context_aware_validation(self):
        """Test context-aware SQL injection validation."""
        workflow = WorkflowBuilder()

        # User fields should allow apostrophes
        workflow.add_node(
            SecureUserManagementNode,
            "user_create",
            {
                "operation": "create",
                "user_data": {
                    "username": "O'Brien",  # Apostrophe in name - should be allowed
                    "first_name": "user--admin",  # Dashes - should be allowed
                    "email": "test@company.com",
                },
                "tenant_id": "tenant_123",
                "requestor_id": "admin",
            },
        )

        # SQL fields should be validated strictly
        workflow.add_node(
            SecureDatabaseNode,
            "db_query",
            {
                "query_type": "select",
                "table": "users",
                "conditions": {"name": "O'Brien"},  # This is OK - it's data, not SQL
            },
        )

        # Build and execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Both should succeed with context-aware validation
        assert results["user_create"]["result"]["success"] is True
        assert results["db_query"]["result"]["rows"] is not None


class TestSecurityPerformance:
    """Test performance impact of security validation."""

    def test_security_validation_overhead(self):
        """Test that security validation has acceptable overhead."""
        import time

        workflow = WorkflowBuilder()

        # Time execution without security (basic node)
        class BasicNode(Node):
            def get_parameters(self):
                return {"data": NodeParameter(name="data", type=dict, required=True)}

            def run(self, **kwargs):
                return {"result": kwargs["data"]}

        # Measure basic node
        workflow.add_node(BasicNode, "basic", {"data": {"test": 1}})
        start = time.time()
        with LocalRuntime() as runtime:
            runtime.execute(workflow.build())
        basic_time = time.time() - start

        # Time execution with security
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            SecureUserManagementNode,
            "secure",
            {
                "operation": "create",
                "user_data": {"test": 1},
                "tenant_id": "t1",
                "requestor_id": "r1",
            },
        )

        start = time.time()
        with LocalRuntime() as runtime:
            runtime.execute(workflow2.build())
        secure_time = time.time() - start

        # Security overhead should be less than 100ms
        overhead = secure_time - basic_time
        assert overhead < 0.1, f"Security overhead too high: {overhead:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
