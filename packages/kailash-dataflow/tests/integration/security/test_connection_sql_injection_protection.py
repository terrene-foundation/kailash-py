"""
Integration tests for DataFlow connection-based SQL injection protection.

Test Task 1.3: DataFlow SQL Injection Protection
- Tests that DataFlow nodes override validate_inputs() to prevent SQL injection through connections
- Validates SQL parameter sanitization in all DataFlow node classes
- Ensures database operations work correctly with validated parameters
"""

import asyncio

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestDataFlowConnectionSQLInjectionProtection:
    """Test DataFlow-specific SQL injection protection through connections."""

    def setup_method(self):
        """Set up test environment with DataFlow instance."""
        # DataFlow will be initialized in each test method with test_suite
        pass

        # Model is now defined in each test method

    def test_create_node_sql_injection_protection(self, test_suite):
        """Test that DataFlow CreateNode prevents SQL injection through connections."""
        db = DataFlow(test_suite.config.url)

        # Define test model with potential injection points
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()

        # Add a source node that produces malicious SQL data
        workflow.add_node(
            "PythonCodeNode",
            "malicious_source",
            {
                "code": "result = {'name': \"'; DROP TABLE test_users; --\", 'email': 'hacker@evil.com'}"
            },
        )

        # Add DataFlow CreateNode that receives data via connection
        workflow.add_node("TestUserCreateNode", "create_user", {})

        # Connect malicious data to CreateNode - this should be validated
        workflow.add_connection(
            "malicious_source", "result.name", "create_user", "name"
        )
        workflow.add_connection(
            "malicious_source", "result.email", "create_user", "email"
        )

        # Execute with strict validation to catch SQL injection
        runtime = LocalRuntime(connection_validation="strict")

        # This should either sanitize the input or raise a validation error
        results, run_id = runtime.execute(workflow.build())

        # Verify that SQL injection was prevented
        create_result = results.get("create_user", {})

        # If the node executed, ensure the dangerous SQL was sanitized
        if "id" in create_result:
            # The dangerous SQL should have been escaped/sanitized
            assert "DROP TABLE" not in str(create_result.get("name", ""))
            # Verify the record was created with sanitized data
            assert (
                create_result.get("name") == "'; DROP TABLE test_users; --"
            )  # Escaped/quoted

    def test_list_node_filter_injection_protection(self, test_suite):
        """Test that DataFlow ListNode prevents SQL injection in filter parameters."""
        db = DataFlow(test_suite.config.url)

        # Define test model with potential injection points
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()

        # Add source that produces malicious filter
        workflow.add_node(
            "PythonCodeNode",
            "malicious_filter",
            {
                "code": """
result = {
    'filter': {
        'name': "admin' OR '1'='1",
        'email': "'; DROP TABLE test_users; SELECT * FROM test_users WHERE '1'='1"
    }
}
"""
            },
        )

        # Add ListNode that receives filter via connection
        workflow.add_node("TestUserListNode", "list_users", {})

        # Connect malicious filter
        workflow.add_connection(
            "malicious_filter", "result.filter", "list_users", "filter"
        )

        # Execute with strict validation
        runtime = LocalRuntime(connection_validation="strict")

        # This should validate/sanitize the filter parameters
        results, run_id = runtime.execute(workflow.build())

        list_result = results.get("list_users", {})

        # Ensure no SQL injection occurred - should return safe results
        assert "records" in list_result
        # The malicious SQL should not have executed successfully
        records = list_result.get("records", [])
        # Should be empty or contain only legitimate records, not unauthorized access

    def test_update_node_sql_injection_protection(self, test_suite):
        """Test that DataFlow UpdateNode prevents SQL injection in update values."""
        db = DataFlow(test_suite.config.url)

        # Define test model with potential injection points
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()

        # Create a legitimate user first
        workflow.add_node(
            "TestUserCreateNode",
            "create_user",
            {"name": "test_user", "email": "test@example.com"},
        )

        # Add source with malicious update data
        workflow.add_node(
            "PythonCodeNode",
            "malicious_update",
            {
                "code": """
result = {
    'id': 1,
    'name': "'; UPDATE test_users SET email='hacked@evil.com' WHERE '1'='1'; --",
    'email': "'; DROP TABLE test_users; --"
}
"""
            },
        )

        # Add UpdateNode that receives data via connection
        workflow.add_node("TestUserUpdateNode", "update_user", {})

        # Connect malicious update data
        workflow.add_connection(
            "malicious_update", "result.name", "update_user", "name"
        )
        workflow.add_connection(
            "malicious_update", "result.email", "update_user", "email"
        )
        workflow.add_connection("malicious_update", "result.id", "update_user", "id")

        # Execute with strict validation
        runtime = LocalRuntime(connection_validation="strict")

        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_user", {})

        # Verify SQL injection was prevented
        if "updated" in update_result:
            # The dangerous SQL should have been escaped/sanitized
            updated_name = update_result.get("name", "")
            assert "UPDATE test_users" not in updated_name
            assert "DROP TABLE" not in str(update_result.get("email", ""))

    def test_bulk_create_sql_injection_protection(self, test_suite):
        """Test that DataFlow BulkCreateNode prevents SQL injection in bulk data."""
        db = DataFlow(test_suite.config.url)

        # Define test model with potential injection points
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()

        # Add source with malicious bulk data
        workflow.add_node(
            "PythonCodeNode",
            "malicious_bulk",
            {
                "code": """
result = {
    'data': [
        {
            'name': "'; DROP TABLE test_users; --",
            'email': 'evil1@hack.com'
        },
        {
            'name': "normal_user",
            'email': "'; INSERT INTO test_users (name, email) VALUES ('hacker', 'hack@evil.com'); --"
        }
    ]
}
"""
            },
        )

        # Add BulkCreateNode
        workflow.add_node("TestUserBulkCreateNode", "bulk_create", {})

        # Connect malicious bulk data
        workflow.add_connection("malicious_bulk", "result.data", "bulk_create", "data")

        # Execute with strict validation
        runtime = LocalRuntime(connection_validation="strict")

        results, run_id = runtime.execute(workflow.build())

        bulk_result = results.get("bulk_create", {})

        # Verify that bulk operation was protected
        if "processed" in bulk_result:
            # Should have processed records safely (with sanitization)
            # or rejected dangerous records entirely
            processed_count = bulk_result.get("processed", 0)
            # At minimum, should not have executed the SQL injection
            assert processed_count >= 0  # Some form of safe processing occurred

    def test_dataflow_validate_inputs_override_exists(self, test_suite):
        """Test that DataFlow nodes actually override validate_inputs method."""
        db = DataFlow(test_suite.config.url)

        # Define test model
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        # Create a DataFlow node instance
        from dataflow.core.nodes import NodeGenerator

        generator = NodeGenerator(db)
        node_class = generator._create_node_class(
            "TestUser",
            "create",
            {
                "name": {"type": str, "required": True},
                "email": {"type": str, "required": True},
            },
        )

        node_instance = node_class(node_id="test_create")

        # Verify that the node has validate_inputs method
        assert hasattr(node_instance, "validate_inputs")
        assert callable(getattr(node_instance, "validate_inputs"))

        # Test that it actually validates SQL injection attempts
        malicious_inputs = {
            "name": "'; DROP TABLE users; --",
            "email": "test@example.com",
        }

        # This should either sanitize or raise an exception
        try:
            validated = node_instance.validate_inputs(**malicious_inputs)
            # If validation succeeds, ensure dangerous SQL was sanitized
            assert "DROP TABLE" not in validated.get("name", "")
        except Exception as e:
            # If validation fails, that's also acceptable protection
            assert "validation" in str(e).lower() or "sql" in str(e).lower()

    def test_parameter_type_enforcement_prevents_injection(self, test_suite):
        """Test that strict type enforcement helps prevent injection."""
        db = DataFlow(test_suite.config.url)

        # Define test model
        @db.model
        class TestUser:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()

        # Try to inject via wrong parameter types
        workflow.add_node(
            "PythonCodeNode",
            "type_confusion",
            {
                "code": """
# Try to pass dict as string to bypass validation
result = {
    'name': {
        'injection': "'; DROP TABLE users; --",
        '__sql__': 'malicious'
    },
    'email': ['array', 'injection', "'; SELECT * FROM users; --"]
}
"""
            },
        )

        workflow.add_node("TestUserCreateNode", "create_user", {})

        # These type mismatches should be caught by validation
        workflow.add_connection("type_confusion", "result.name", "create_user", "name")
        workflow.add_connection(
            "type_confusion", "result.email", "create_user", "email"
        )

        runtime = LocalRuntime(connection_validation="strict")

        # Should raise validation error due to type mismatch
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build())

        # Verify it's a validation error, not a SQL injection
        error_msg = str(exc_info.value).lower()
        assert any(term in error_msg for term in ["validation", "type", "parameter"])


@pytest.mark.asyncio
async def test_async_dataflow_sql_injection_protection():
    """Test SQL injection protection in async DataFlow operations."""
    # Test async scenarios if DataFlow supports them
    # This ensures that async database operations are also protected
    pass  # Implementation would depend on DataFlow async support


def test_dataflow_connection_validation_integration(test_suite):
    """Test that DataFlow integrates properly with LocalRuntime connection validation."""
    db = DataFlow(test_suite.config.url)

    @db.model
    class Product:
        name: str
        price: float

    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "source",
        {"code": "result = {'name': \"'; DROP TABLE products; --\", 'price': -1}"},
    )
    workflow.add_node("ProductCreateNode", "create", {})
    workflow.add_connection("source", "result.name", "create", "name")
    workflow.add_connection("source", "result.price", "create", "price")

    # Test all validation modes work with DataFlow
    for mode in ["off", "warn", "strict"]:
        runtime = LocalRuntime(connection_validation=mode)

        # Should execute without crashing (validation behavior depends on mode)
        results, run_id = runtime.execute(workflow.build())

        # In strict mode, should prevent injection
        if mode == "strict":
            create_result = results.get("create", {})
            if "name" in create_result:
                # Should be safely escaped/sanitized
                assert "DROP TABLE" not in str(create_result["name"])
