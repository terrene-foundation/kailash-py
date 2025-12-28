"""
Unit tests for runtime success detection functionality.

This module tests the centralized success detection utility that handles
both Python exceptions and return value content (e.g., {"success": False}).

Test focus:
- Success detection utility logic
- DataFlow return pattern parsing
- Backward compatibility with exception-only detection
- Configuration behavior
- Edge cases and malformed data
"""

from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.base import Node
from kailash.runtime.local import (
    LocalRuntime,
    detect_success,
    should_stop_on_content_failure,
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class MockSuccessNode(Node):
    """Mock node that returns success patterns."""

    def get_parameters(self) -> dict:
        return {}

    def execute(self, **kwargs) -> Dict[str, Any]:
        return {"success": True, "data": "operation completed"}


class MockFailureNode(Node):
    """Mock node that returns failure patterns."""

    def get_parameters(self) -> dict:
        return {}

    def execute(self, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "operation failed", "details": "test error"}


class MockExceptionNode(Node):
    """Mock node that raises exceptions (current behavior)."""

    def get_parameters(self) -> dict:
        return {}

    def execute(self, **kwargs) -> Dict[str, Any]:
        raise ValueError("Traditional exception-based failure")


class MockMalformedNode(Node):
    """Mock node that returns malformed success/failure patterns."""

    def get_parameters(self) -> dict:
        from kailash.nodes.base import NodeParameter

        return {"mode": NodeParameter(name="mode", type=str, default="missing_success")}

    def execute(self, mode: str = "missing_success", **kwargs) -> Dict[str, Any]:
        if mode == "missing_success":
            return {"error": "no success field"}
        elif mode == "non_boolean_success":
            return {"success": "yes", "data": "invalid success type"}
        elif mode == "none_return":
            return None
        elif mode == "empty_dict":
            return {}
        else:
            return {"success": True, "data": "valid"}


class TestSuccessDetectionUtility:
    """Test the centralized success detection utility."""

    def test_detect_success_from_return_value_true(self):
        """Test success detection when return value contains success: True."""
        # detect_success is imported at module level

        result = {"success": True, "data": "completed"}
        is_success, error_info = detect_success(result)

        assert is_success is True
        assert error_info is None

    def test_detect_success_from_return_value_false(self):
        """Test success detection when return value contains success: False."""
        # detect_success is imported at module level

        result = {"success": False, "error": "operation failed"}
        is_success, error_info = detect_success(result)

        assert is_success is False
        assert error_info == "operation failed"

    def test_detect_success_from_return_value_false_with_details(self):
        """Test success detection with detailed error information."""
        # detect_success is imported at module level

        result = {
            "success": False,
            "error": "validation failed",
            "details": "required field missing",
            "code": "VALIDATION_ERROR",
        }
        is_success, error_info = detect_success(result)

        assert is_success is False
        assert error_info == "validation failed"

    def test_detect_success_no_success_field_defaults_true(self):
        """Test that missing success field defaults to True (backward compatibility)."""
        # detect_success is imported at module level

        result = {"data": "some data", "count": 5}
        is_success, error_info = detect_success(result)

        assert is_success is True
        assert error_info is None

    def test_detect_success_none_return_defaults_true(self):
        """Test that None return value defaults to True (backward compatibility)."""
        # detect_success is imported at module level

        is_success, error_info = detect_success(None)

        assert is_success is True
        assert error_info is None

    def test_detect_success_empty_dict_defaults_true(self):
        """Test that empty dict defaults to True (backward compatibility)."""
        # detect_success is imported at module level

        is_success, error_info = detect_success({})

        assert is_success is True
        assert error_info is None

    def test_detect_success_non_boolean_success_field(self):
        """Test handling of non-boolean success field values."""
        # detect_success is imported at module level

        # String "false" should be treated as True (truthy)
        result = {"success": "false", "data": "test"}
        is_success, error_info = detect_success(result)
        assert is_success is True

        # Empty string should be treated as False (falsy)
        result = {"success": "", "error": "empty success"}
        is_success, error_info = detect_success(result)
        assert is_success is False
        assert error_info == "empty success"

        # Zero should be treated as False
        result = {"success": 0, "error": "zero success"}
        is_success, error_info = detect_success(result)
        assert is_success is False
        assert error_info == "zero success"

    def test_detect_success_non_dict_return_defaults_true(self):
        """Test that non-dict return values default to True."""
        # detect_success is imported at module level

        # String return
        is_success, error_info = detect_success("some string result")
        assert is_success is True
        assert error_info is None

        # List return
        is_success, error_info = detect_success([1, 2, 3])
        assert is_success is True
        assert error_info is None

        # Number return
        is_success, error_info = detect_success(42)
        assert is_success is True
        assert error_info is None


class TestRuntimeSuccessDetectionIntegration:
    """Test LocalRuntime integration with success detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = LocalRuntime()

    def test_runtime_detects_success_from_return_value(self):
        """Test that runtime detects success from return value content."""
        # Create workflow with success node
        workflow = WorkflowBuilder()
        workflow.add_node(MockSuccessNode, "success_node", {})
        built_workflow = workflow.build()

        # Execute workflow
        with self.runtime:
            results, run_id = self.runtime.execute(built_workflow)

        # Should complete successfully
        assert run_id is not None
        assert "success_node" in results
        assert results["success_node"]["success"] is True

    def test_runtime_detects_failure_from_return_value(self):
        """Test that runtime detects failure from return value content."""
        # Create workflow with failure node
        workflow = WorkflowBuilder()
        workflow.add_node(MockFailureNode, "failure_node", {})
        built_workflow = workflow.build()

        # Execute workflow - this should currently complete but we want it to fail
        with pytest.raises(
            Exception
        ):  # This test should fail until we implement the fix
            with self.runtime:
                results, run_id = self.runtime.execute(built_workflow)

    def test_runtime_backward_compatibility_with_exceptions(self):
        """Test that runtime still handles traditional exceptions correctly."""
        # Create workflow with exception node (single node, no dependents)
        workflow = WorkflowBuilder()
        workflow.add_node(MockExceptionNode, "exception_node", {})
        built_workflow = workflow.build()

        # Execute workflow - single node exceptions are stored in results, not propagated
        with self.runtime:
            results, run_id = self.runtime.execute(built_workflow)

        # Should complete with run_id but exception stored in results
        assert run_id is not None
        assert "exception_node" in results
        exception_result = results["exception_node"]
        assert exception_result["failed"] is True
        assert exception_result["error_type"] == "ValueError"
        assert "Traditional exception-based failure" in exception_result["error"]

    def test_runtime_handles_malformed_return_values(self):
        """Test that runtime gracefully handles malformed return values."""
        # Test missing success field
        workflow = WorkflowBuilder()
        workflow.add_node(
            MockMalformedNode, "malformed_node", {"mode": "missing_success"}
        )
        built_workflow = workflow.build()

        with self.runtime:
            results, run_id = self.runtime.execute(built_workflow)

        assert run_id is not None  # Should default to success

        # Test None return
        workflow = WorkflowBuilder()
        workflow.add_node(MockMalformedNode, "malformed_node", {"mode": "none_return"})
        built_workflow = workflow.build()

        with self.runtime:
            results, run_id = self.runtime.execute(built_workflow)

        assert run_id is not None  # Should default to success

    def test_runtime_configuration_content_aware_mode(self):
        """Test runtime configuration for content-aware success detection."""
        # Create runtime with content-aware mode enabled
        runtime = LocalRuntime(content_aware_success_detection=True)

        # Test with failure node
        workflow = WorkflowBuilder()
        workflow.add_node(MockFailureNode, "failure_node", {})
        built_workflow = workflow.build()

        # Should fail when content-aware mode is enabled
        with pytest.raises(Exception):
            with runtime:
                results, run_id = runtime.execute(built_workflow)

    def test_runtime_configuration_legacy_mode(self):
        """Test runtime configuration for legacy exception-only mode."""
        # Create runtime with legacy mode (content-aware disabled)
        runtime = LocalRuntime(content_aware_success_detection=False)

        # Test with failure node
        workflow = WorkflowBuilder()
        workflow.add_node(MockFailureNode, "failure_node", {})
        built_workflow = workflow.build()

        # Should complete successfully in legacy mode (ignores return value)
        with runtime:
            results, run_id = runtime.execute(built_workflow)

        assert run_id is not None
        assert results["failure_node"]["success"] is False  # Data preserved


class TestDataFlowPatternCompatibility:
    """Test compatibility with DataFlow-specific return patterns."""

    def test_dataflow_bulk_create_success_pattern(self):
        """Test success detection with DataFlow bulk create success pattern."""
        # detect_success is imported at module level

        # Typical DataFlow success response
        result = {
            "success": True,
            "records_processed": 100,
            "batches": 10,
            "execution_time": 1.5,
        }

        is_success, error_info = detect_success(result)
        assert is_success is True
        assert error_info is None

    def test_dataflow_bulk_create_failure_pattern(self):
        """Test success detection with DataFlow bulk create failure pattern."""
        # detect_success is imported at module level

        # Typical DataFlow failure response
        result = {"success": False, "error": "Data cannot be None", "rows_affected": 0}

        is_success, error_info = detect_success(result)
        assert is_success is False
        assert error_info == "Data cannot be None"

    def test_dataflow_transaction_failure_pattern(self):
        """Test success detection with DataFlow transaction failure pattern."""
        # detect_success is imported at module level

        # DataFlow transaction failure response
        result = {
            "success": False,
            "error": "Transaction failed",
            "transaction_id": "tx_123",
            "rollback_status": "completed",
        }

        is_success, error_info = detect_success(result)
        assert is_success is False
        assert error_info == "Transaction failed"

    def test_dataflow_migration_failure_pattern(self):
        """Test success detection with DataFlow migration failure pattern."""
        # detect_success is imported at module level

        # DataFlow migration failure response
        result = {"success": False, "error": "Migration tx_456 not found"}

        is_success, error_info = detect_success(result)
        assert is_success is False
        assert error_info == "Migration tx_456 not found"


class TestPerformanceImpact:
    """Test performance impact of success detection."""

    def test_success_detection_performance(self):
        """Test that success detection has minimal performance impact."""
        # detect_success is imported at module level
        import time

        # Test with typical success response
        result = {"success": True, "data": "test"}

        # Measure performance
        start_time = time.time()
        for _ in range(1000):
            detect_success(result)
        end_time = time.time()

        # Should complete 1000 operations in well under 1 second
        assert (end_time - start_time) < 0.1

    def test_success_detection_memory_usage(self):
        """Test that success detection doesn't create memory leaks."""
        # detect_success is imported at module level
        import gc

        # Force garbage collection
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Run many success detections
        for i in range(1000):
            result = {"success": True, "data": f"test_{i}"}
            detect_success(result)

        # Force garbage collection again
        gc.collect()
        final_objects = len(gc.get_objects())

        # Should not have significant object growth
        object_growth = final_objects - initial_objects
        assert object_growth < 100  # Allow some growth but not excessive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
