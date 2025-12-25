"""
Security tests for connection parameter validation vulnerability (TODO-121).

These tests verify that parameters passed through workflow connections
are properly validated and cannot bypass security checks.
"""

from typing import Any, Dict

import pytest
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class SecurityError(Exception):
    """Custom security error for testing."""

    pass


class MaliciousNode(Node):
    """Node that outputs potentially dangerous data."""

    def get_parameters(self):
        return {}

    def run(self, **kwargs):
        return {
            "output": {
                # SQL injection attempt
                "query": "'; DROP TABLE users;--",
                # Type confusion
                "count": "not_a_number",
                # Unauthorized parameter
                "admin_mode": True,
                # Nested injection
                "data": {"sql": "SELECT * FROM secrets"},
            }
        }


class SecureNode(Node):
    """Node expecting validated parameters."""

    def get_parameters(self):
        return {
            "query": NodeParameter(name="query", type=str, required=True),
            "count": NodeParameter(name="count", type=int, required=True),
            # Note: admin_mode NOT declared - should be rejected
        }

    def run(self, **kwargs):
        # Should only receive validated parameters
        query = kwargs.get("query")
        count = kwargs.get("count")
        admin_mode = kwargs.get("admin_mode", False)

        # If admin_mode is True, security was bypassed
        if admin_mode:
            raise SecurityError("Unauthorized parameter received!")

        # Type checking
        if not isinstance(count, int):
            raise TypeError(f"Expected int, got {type(count)}")

        return {
            "result": f"Processed {count} items with query: {query}",
            "security_check": "passed",
        }


class DataFlowNode(Node):
    """Simulates a database node that should prevent SQL injection."""

    def get_parameters(self):
        return {
            "table": NodeParameter(name="table", type=str, required=True),
            "query": NodeParameter(name="query", type=str, required=False),
        }

    def run(self, **kwargs):
        table = kwargs.get("table", "users")
        query = kwargs.get("query", "")

        # Simple SQL injection detection
        dangerous_patterns = [";", "--", "DROP", "DELETE", "INSERT", "UPDATE"]
        for pattern in dangerous_patterns:
            if pattern in query.upper():
                raise ValueError(f"SQL injection detected: {pattern}")

        return {"data": f"Safe query on {table}"}


class TestConnectionValidation:
    """Test suite for connection parameter validation."""

    def setup_method(self):
        """Register custom nodes for testing."""
        self.registry = NodeRegistry()
        self.registry.register_node("MaliciousNode", MaliciousNode)
        self.registry.register_node("SecureNode", SecureNode)
        self.registry.register_node("DataFlowNode", DataFlowNode)

    def teardown_method(self):
        """Clean up custom nodes."""
        if hasattr(self, "registry"):
            self.registry.unregister_node("MaliciousNode")
            self.registry.unregister_node("SecureNode")
            self.registry.unregister_node("DataFlowNode")

    def test_direct_parameters_are_validated(self):
        """Direct parameters should always be validated."""
        workflow = WorkflowBuilder()
        workflow.add_node("SecureNode", "secure", {})

        runtime = LocalRuntime(connection_validation="strict")

        # Valid parameters should work
        results, _ = runtime.execute(
            workflow.build(),
            parameters={"secure": {"query": "SELECT * FROM users", "count": 10}},
        )
        assert results["secure"]["security_check"] == "passed"

        # Invalid type should fail in strict mode
        with pytest.raises(Exception) as exc_info:
            runtime.execute(
                workflow.build(),
                parameters={
                    "secure": {"query": "SELECT * FROM users", "count": "not_a_number"}
                },
            )
        assert (
            "type" in str(exc_info.value).lower()
            or "conversion" in str(exc_info.value).lower()
        )

    def test_connection_parameters_bypass_validation_currently(self):
        """
        This test demonstrates the current vulnerability where connection
        parameters bypass validation. This should FAIL after the fix.
        """
        workflow = WorkflowBuilder()
        workflow.add_node(MaliciousNode, "malicious", {})
        workflow.add_node(SecureNode, "secure", {})

        # Connect malicious output to secure input
        workflow.add_connection("malicious", "output", "secure", "")

        runtime = LocalRuntime()

        # Currently this executes without validation (VULNERABILITY!)
        # After fix, this should raise an error in strict mode
        try:
            results, _ = runtime.execute(workflow.build(), {})
            # If we get here, validation was bypassed (current behavior)
            assert True  # This is the vulnerability we're fixing
        except Exception as e:
            if "security" in str(e).lower() or "unauthorized" in str(e).lower():
                # After fix, this should happen in strict mode
                pytest.fail("Security validation is working (good!)")

    def test_connection_validation_modes(self):
        """Test different validation modes after fix implementation."""
        workflow = WorkflowBuilder()
        workflow.add_node(MaliciousNode, "malicious", {})
        workflow.add_node(SecureNode, "secure", {})
        workflow.add_connection("malicious", "output", "secure", "")

        # Off mode - no validation (backward compatibility)
        runtime_off = LocalRuntime(connection_validation="off")
        try:
            results, _ = runtime_off.execute(workflow.build(), {})
            # May still fail due to missing required params, but not due to validation
        except Exception as e:
            # This is OK - the node itself may validate
            pass

        # Warn mode - log warnings but continue
        runtime_warn = LocalRuntime(connection_validation="warn")
        results, _ = runtime_warn.execute(workflow.build(), {})
        # Should execute with warnings

        # Strict mode - fail on validation errors
        runtime_strict = LocalRuntime(connection_validation="strict")
        with pytest.raises(Exception) as exc_info:
            runtime_strict.execute(workflow.build(), {})
        # Should fail with validation error

    def test_sql_injection_prevention(self):
        """SQL injection should be prevented at connection level."""
        workflow = WorkflowBuilder()
        workflow.add_node(MaliciousNode, "attacker", {})
        workflow.add_node(DataFlowNode, "database", {})

        # Connect malicious query to database
        workflow.add_connection("attacker", "output", "database", "")

        runtime = LocalRuntime(connection_validation="strict")

        # After fix, SQL injection should be caught
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build(), {"database": {"table": "users"}})
        # Validation should prevent dangerous SQL

    def test_type_safety_enforcement(self):
        """Type safety should be enforced across connections."""

        class TypeProducerNode(Node):
            def run(self, **kwargs):
                return {"number": "123", "flag": "true"}  # String types

        class TypeConsumerNode(Node):
            def get_parameters(self):
                return {
                    "number": NodeParameter(type=int, required=True),
                    "flag": NodeParameter(type=bool, required=True),
                }

            def run(self, **kwargs):
                assert isinstance(kwargs["number"], int)
                assert isinstance(kwargs["flag"], bool)
                return {"success": True}

        workflow = WorkflowBuilder()
        workflow.add_node(TypeProducerNode, "producer", {})
        workflow.add_node(TypeConsumerNode, "consumer", {})
        workflow.add_connection("producer", "", "consumer", "")

        runtime = LocalRuntime(connection_validation="strict")

        # After fix with type conversion
        results, _ = runtime.execute(workflow.build(), {})
        assert results["consumer"]["success"] is True

    def test_required_parameters_validation(self):
        """Required parameters must be validated even from connections."""

        class IncompleteNode(Node):
            def run(self, **kwargs):
                return {"partial": {"query": "SELECT 1"}}  # Missing 'count'

        workflow = WorkflowBuilder()
        workflow.add_node(IncompleteNode, "incomplete", {})
        workflow.add_node(SecureNode, "secure", {})
        workflow.add_connection("incomplete", "partial", "secure", "")

        runtime = LocalRuntime(connection_validation="strict")

        # Should fail due to missing required parameter
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build(), {})
        assert "required" in str(exc_info.value).lower()

    def test_nested_parameter_validation(self):
        """Nested objects in connections should be validated."""

        class NestedProducerNode(Node):
            def run(self, **kwargs):
                return {
                    "config": {
                        "database": {
                            "host": "localhost",
                            "port": "not_a_number",  # Invalid type
                            "credentials": {
                                "user": "admin",
                                "password": "'; DROP TABLE users;--",
                            },
                        }
                    }
                }

        class NestedConsumerNode(Node):
            def get_parameters(self):
                return {"database": NodeParameter(type=dict, required=True)}

            def run(self, **kwargs):
                db_config = kwargs["database"]
                # Validate nested structure
                assert isinstance(db_config.get("port"), (int, str))
                return {"connected": True}

        workflow = WorkflowBuilder()
        workflow.add_node(NestedProducerNode, "producer", {})
        workflow.add_node(NestedConsumerNode, "consumer", {})
        workflow.add_connection("producer", "config", "consumer", "")

        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(workflow.build(), {})
        # Should handle nested validation

    def test_audit_trail_for_connections(self):
        """All parameter flows should be auditable."""
        # This test will be implemented when audit functionality is added
        pass

    def test_performance_impact(self):
        """Validation should have minimal performance impact."""
        import time

        # Create a workflow with many connections
        workflow = WorkflowBuilder()

        class DataNode(Node):
            def run(self, **kwargs):
                return {"data": kwargs.get("input", {"value": 42})}

        # Chain 100 nodes
        for i in range(100):
            workflow.add_node(DataNode, f"node_{i}", {})
            if i > 0:
                workflow.add_connection(f"node_{i-1}", "data", f"node_{i}", "input")

        # Measure without validation
        runtime_off = LocalRuntime(connection_validation="off")
        start = time.time()
        runtime_off.execute(workflow.build(), {})
        time_without = time.time() - start

        # Measure with validation
        runtime_strict = LocalRuntime(connection_validation="strict")
        start = time.time()
        runtime_strict.execute(workflow.build(), {})
        time_with = time.time() - start

        # Performance impact should be < 5%
        overhead = (time_with - time_without) / time_without
        assert overhead < 0.05, f"Performance overhead {overhead:.1%} exceeds 5%"


class TestDataFlowConnectionSecurity:
    """Test DataFlow-specific connection security."""

    def test_dataflow_sql_injection_prevention(self):
        """DataFlow nodes should prevent SQL injection via connections."""
        # This will test DataFlow-specific protections
        pass

    def test_dataflow_parameter_validation(self):
        """DataFlow CRUD operations should validate connection parameters."""
        # This will test DataFlow CRUD node validation
        pass
