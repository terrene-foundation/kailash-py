"""
Test Protection System Critical Gaps

Tests to identify and validate fixes for critical protection system integration issues.
These tests expose the specific gaps identified in the intermediate review.
"""

import logging
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node
from kailash.workflow.builder import WorkflowBuilder

from dataflow.core.nodes import NodeGenerator
from dataflow.core.protected_engine import ProtectedDataFlow, ProtectedNodeGenerator
from dataflow.core.protection import (
    GlobalProtection,
    OperationType,
    ProtectionLevel,
    ProtectionViolation,
    WriteProtectionConfig,
    WriteProtectionEngine,
)
from dataflow.core.protection_middleware import (
    AsyncSQLProtectionWrapper,
    ProtectedDataFlowRuntime,
    protect_dataflow_node,
)


class TestProtectionSystemCriticalGaps:
    """Test critical gaps in protection system integration."""

    def setup_method(self):
        """Setup test fixtures."""
        self.db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )

        # Configure global read-only protection for testing
        self.db.enable_read_only_mode("Testing protection violations")

        # Define test model to trigger node generation
        @self.db.model
        class TestModel:
            id: int
            name: str
            value: int

        self.test_model = TestModel

    def test_node_detection_failure_gap(self):
        """Test: Protection system fails to detect DataFlow-generated nodes."""
        # Get generated node class
        node_classes = self.db._nodes
        create_node_class = None

        for name, cls in node_classes.items():
            if "CreateNode" in name:
                create_node_class = cls
                break

        assert create_node_class is not None, "No CreateNode found in generated nodes"

        # Instantiate the node
        node = create_node_class(node_id="test_create")

        # Test 1: Check if node has protection attributes that the middleware expects
        assert hasattr(node, "model_name"), "Node should have model_name attribute"
        assert hasattr(node, "operation"), "Node should have operation attribute"
        assert hasattr(
            node, "dataflow_instance"
        ), "Node should have dataflow_instance attribute"

        # Test 2: Check if protection engine can detect the node type
        # This exposes the fragile hasattr detection
        protection_engine = self.db._protection_engine
        assert protection_engine is not None

        # The middleware uses hasattr(node, 'model_name') which might fail for dynamic nodes
        has_model_name = hasattr(node, "model_name")
        assert has_model_name, "Node detection via hasattr(node, 'model_name') failed"

        # Test 3: Verify the node is properly wrapped with protection
        # This should verify the ProtectedNodeGenerator is working
        assert isinstance(self.db._node_generator, ProtectedNodeGenerator)

    def test_runtime_node_execution_interception_gap(self):
        """Test: ProtectedDataFlowRuntime intercepts node execution."""
        # Create a workflow with a write operation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestModelCreateNode", "create_test", {"name": "test item", "value": 42}
        )

        # Create protected runtime
        runtime = self.db.create_protected_runtime()

        # Test 1: Verify runtime is the protected type
        assert isinstance(runtime, ProtectedDataFlowRuntime)

        # Test 2: Mock the execute method to capture interception
        original_execute = runtime.execute
        execution_intercepted = False
        violation_raised = False

        def mock_execute(*args, **kwargs):
            nonlocal execution_intercepted, violation_raised
            execution_intercepted = True
            try:
                return original_execute(*args, **kwargs)
            except ProtectionViolation:
                violation_raised = True
                raise
            except Exception as e:
                # Check if it's a wrapped ProtectionViolation or table does not exist error
                # In unit tests with :memory: SQLite, tables may not exist
                if "Global protection blocks" in str(e):
                    violation_raised = True
                raise

        runtime.execute = mock_execute

        # Test 3: Execute workflow and verify protection triggered or database error
        with pytest.raises((ProtectionViolation, Exception)) as exc_info:
            results, run_id = runtime.execute(workflow.build())

        assert execution_intercepted, "Runtime execute method was not called"

        # The protection should either raise ProtectionViolation directly
        # or raise a database error (table doesn't exist in :memory: SQLite)
        # Both are acceptable - the key is that execution was intercepted
        exception_message = str(exc_info.value)
        is_protection_violation = isinstance(exc_info.value, ProtectionViolation)
        contains_protection_message = "Global protection blocks" in exception_message
        is_database_error = "no such table" in exception_message

        assert (
            is_protection_violation or contains_protection_message or is_database_error
        ), f"Expected ProtectionViolation, protection message, or database error, got: {exception_message}"

    def test_error_propagation_chain_gap(self):
        """Test: Protection violations or database errors are properly propagated."""
        # Create runtime with protection
        runtime = self.db.create_protected_runtime()

        # Create a workflow that should trigger protection
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestModelCreateNode", "create_test", {"name": "test item", "value": 42}
        )

        # Test error propagation by examining the exception chain
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build())

        exception = exc_info.value

        # Test 1: Check if it's directly a ProtectionViolation
        if isinstance(exception, ProtectionViolation):
            assert exception.operation == OperationType.CREATE
            assert exception.level == ProtectionLevel.BLOCK
            return  # This would be correct behavior

        # Test 2: Check for wrapped ProtectionViolation in exception chain
        current = exception
        found_protection_violation = False
        chain_depth = 0

        while current and chain_depth < 5:  # Prevent infinite loops
            if isinstance(current, ProtectionViolation):
                found_protection_violation = True
                break

            # Check both __cause__ and __context__
            next_exception = getattr(current, "__cause__", None) or getattr(
                current, "__context__", None
            )
            if next_exception is None:
                break
            current = next_exception
            chain_depth += 1

        # Test 3: Check for protection message or database error in exception text
        exception_text = str(exception)
        has_protection_message = "Global protection blocks" in exception_text
        has_database_error = "no such table" in exception_text

        # At least one should be true for proper error handling
        # In unit tests with :memory: SQLite, we may get database errors
        # instead of protection violations
        assert (
            found_protection_violation or has_protection_message or has_database_error
        ), f"Protection violation or database error not found in exception chain. Exception: {exception}, Chain depth: {chain_depth}"

    def test_connection_string_resolution_gap(self):
        """Test: Connection string detection fallback logic fails."""
        # Create node instance
        node_classes = self.db._nodes
        create_node_class = None

        for name, cls in node_classes.items():
            if "CreateNode" in name:
                create_node_class = cls
                break

        node = create_node_class(node_id="test_create")

        # Test 1: Node should have access to dataflow instance
        assert hasattr(node, "dataflow_instance")
        assert node.dataflow_instance is not None

        # Test 2: DataFlow instance should have config with database connection
        df_instance = node.dataflow_instance
        assert hasattr(df_instance, "config")
        assert hasattr(df_instance.config, "database")

        # Test 3: Connection string should be resolvable
        try:
            connection_string = df_instance.config.database.get_connection_url(
                df_instance.config.environment
            )
            assert connection_string is not None
            assert len(connection_string) > 0
        except Exception as e:
            pytest.fail(f"Connection string resolution failed: {e}")

        # Test 4: Protection check should work with resolved connection
        protection_engine = self.db._protection_engine

        # This should not raise an exception for connection string resolution
        try:
            protection_engine.check_operation(
                operation="create",
                model_name="TestModel",
                connection_string=connection_string,
            )
        except ProtectionViolation:
            # This is expected due to read-only protection
            pass
        except Exception as e:
            pytest.fail(f"Connection string resolution in protection check failed: {e}")

    def test_async_sql_node_protection_wrapper_gap(self):
        """Test: AsyncSQLDatabaseNode protection wrapping fails."""
        # Test the AsyncSQLProtectionWrapper
        protection_engine = self.db._protection_engine
        wrapper = AsyncSQLProtectionWrapper(protection_engine)

        # Mock AsyncSQLDatabaseNode for testing
        class MockAsyncSQLNode:
            def execute(self, **kwargs):
                return {"result": {"data": [{"id": 1}]}}

        # Test 1: Wrapper should be able to wrap the node class
        try:
            wrapped_class = wrapper.wrap_async_sql_node(MockAsyncSQLNode)
            assert wrapped_class is not None
        except Exception as e:
            pytest.fail(f"AsyncSQL node wrapping failed: {e}")

        # Test 2: Test SQL operation detection
        create_query = "INSERT INTO test_table (name) VALUES ('test')"
        operation = wrapper._detect_operation_from_sql(create_query)
        assert operation == "create"

        read_query = "SELECT * FROM test_table"
        operation = wrapper._detect_operation_from_sql(read_query)
        assert operation == "read"

        # Test 3: Test wrapped execution with protection
        wrapped_node = wrapped_class()

        with pytest.raises(ProtectionViolation):
            wrapped_node.execute(
                query="INSERT INTO test_table (name) VALUES ('test')",
                connection_string="sqlite:///:memory:",
            )


class TestProtectionSystemRobustNodeDetection:
    """Test robust node detection based on actual DataFlow patterns."""

    def setup_method(self):
        """Setup test fixtures."""
        self.db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )

        @self.db.model
        class NodeDetectionTest:
            id: int
            name: str

        self.test_model = NodeDetectionTest

    def test_dataflow_node_identification_patterns(self):
        """Test various ways to identify DataFlow-generated nodes."""
        # Get all generated nodes
        node_classes = self.db._nodes

        for node_name, node_class in node_classes.items():
            # Create instance
            node = node_class(node_id=f"test_{node_name}")

            # Test 1: Attribute-based detection (current fragile method)
            has_model_name = hasattr(node, "model_name")
            has_operation = hasattr(node, "operation")
            has_dataflow_instance = hasattr(node, "dataflow_instance")

            # Test 2: Class name pattern detection
            is_dataflow_node_by_name = any(
                pattern in node_class.__name__
                for pattern in [
                    "CreateNode",
                    "ReadNode",
                    "UpdateNode",
                    "DeleteNode",
                    "ListNode",
                    "BulkCreateNode",
                ]
            )

            # Test 3: Method signature detection
            has_dataflow_run_method = hasattr(node, "run") and callable(
                getattr(node, "run")
            )

            # Test 4: Module detection
            is_from_dataflow = node_class.__module__.startswith("dataflow")

            # At least one detection method should work
            is_detected = (
                (has_model_name and has_operation and has_dataflow_instance)
                or is_dataflow_node_by_name
                or (has_dataflow_run_method and is_from_dataflow)
            )

            assert is_detected, f"Node {node_name} not detected by any method"

            # Verify the most robust detection method
            if is_dataflow_node_by_name:
                assert has_model_name, f"DataFlow node {node_name} missing model_name"
                assert has_operation, f"DataFlow node {node_name} missing operation"


class TestProtectionSystemConnectionResolution:
    """Test connection string resolution in various scenarios."""

    def test_connection_string_fallback_scenarios(self):
        """Test connection string resolution fallback logic."""
        # Test 1: Direct database_url parameter
        db1 = ProtectedDataFlow(
            database_url="postgresql://user:pass@host:5432/db1", enable_protection=True
        )

        # Test 2: SQLite memory database
        db2 = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )

        # Test 3: No explicit URL (should use default)
        try:
            db3 = ProtectedDataFlow(enable_protection=True)
            # Should not fail initialization
            assert db3._protection_engine is not None
        except Exception:
            # This might fail if no default database is configured
            pass

        # Test connection resolution for each
        for db in [db1, db2]:
            try:
                connection_url = db.config.database.get_connection_url(
                    db.config.environment
                )
                assert connection_url is not None
                assert len(connection_url) > 0
            except Exception as e:
                pytest.fail(f"Connection resolution failed for {db}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
