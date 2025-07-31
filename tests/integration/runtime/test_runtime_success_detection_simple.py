"""
Simple integration tests for runtime success detection without external dependencies.

This module tests the runtime success detection functionality with mock nodes
that simulate DataFlow patterns without requiring real database connections.
"""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.utils.success_detection import ContentAwareExecutionError
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import Node, NodeParameter


class MockDataFlowSuccessNode(Node):
    """Mock node that returns DataFlow-like success patterns."""
    
    def get_parameters(self) -> dict:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }
    
    def execute(self, data=None, **kwargs):
        # Debug: print what we received
        print(f"DEBUG MockDataFlowSuccessNode: data={data}, kwargs={kwargs}")
        
        # Simulate DataFlow success pattern
        if data is None or (isinstance(data, list) and len(data) == 0):
            return {"success": False, "error": "No data provided for bulk create"}
        
        # Simulate successful database insertion
        return {
            "success": True,
            "rows_affected": len(data),
            "inserted": len(data),
            "performance_metrics": {
                "execution_time_seconds": 0.1,
                "records_per_second": len(data) * 10
            }
        }


class MockDataFlowFailureNode(Node):
    """Mock node that returns DataFlow-like failure patterns."""
    
    def get_parameters(self) -> dict:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=None)
        }
    
    def execute(self, data=None, **kwargs):
        # Simulate DataFlow failure patterns
        if data is None:
            return {"success": False, "error": "Data cannot be None"}
        
        if isinstance(data, list) and len(data) == 0:
            return {"success": False, "error": "No data provided for bulk create"}
        
        # This shouldn't be reached in our failure tests
        return {"success": True, "rows_affected": len(data)}


class TestRuntimeSuccessDetectionSimple:
    """Simple integration tests for runtime success detection."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runtime_legacy = LocalRuntime(content_aware_success_detection=False)
        self.runtime_fixed = LocalRuntime(content_aware_success_detection=True)
    
    def test_runtime_detects_success_pattern(self):
        """Test that runtime correctly processes success patterns."""
        workflow = WorkflowBuilder()
        workflow.add_node(MockDataFlowSuccessNode, "success_test", {
            "data": [
                {"name": "Alice", "email": "alice@test.com"},
                {"name": "Bob", "email": "bob@test.com"}
            ]
        })
        
        # Both runtimes should complete successfully
        results_legacy, run_id_legacy = self.runtime_legacy.execute(workflow.build())
        results_fixed, run_id_fixed = self.runtime_fixed.execute(workflow.build())
        
        # Both should succeed
        assert run_id_legacy is not None
        assert run_id_fixed is not None
        
        # Check success patterns
        for results in [results_legacy, results_fixed]:
            result = results["success_test"]
            assert result["success"] is True
            assert result["rows_affected"] == 2
            assert "performance_metrics" in result
    
    def test_runtime_detects_failure_pattern_legacy_vs_fixed(self):
        """Test difference between legacy and fixed runtime for failure patterns."""
        workflow = WorkflowBuilder()
        workflow.add_node(MockDataFlowFailureNode, "failure_test", {"data": None})  # Will cause failure
        
        # Legacy runtime should complete (demonstrates the bug)
        results_legacy, run_id_legacy = self.runtime_legacy.execute(workflow.build())
        assert run_id_legacy is not None
        
        # Check that DataFlow returned failure but runtime completed
        failure_result = results_legacy["failure_test"]
        assert failure_result["success"] is False
        assert "Data cannot be None" in failure_result["error"]
        print(f"LEGACY BUG DEMONSTRATED: Runtime completed despite success=False")
        print(f"Result: {failure_result}")
        
        # Fixed runtime should detect the failure and stop
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results_fixed, run_id_fixed = self.runtime_fixed.execute(workflow.build())
        
        assert "failure_test" in str(exc_info.value)
        assert "Data cannot be None" in str(exc_info.value)
        print(f"FIX CONFIRMED: Fixed runtime detected failure: {exc_info.value}")
    
    def test_runtime_mixed_workflow_behavior(self):
        """Test mixed success/failure workflow behavior."""
        workflow = WorkflowBuilder()
        
        # Success node
        workflow.add_node(MockDataFlowSuccessNode, "success_node", {
            "data": [{"name": "Success User", "email": "success@test.com"}]
        })
        
        # Failure node
        workflow.add_node(MockDataFlowFailureNode, "failure_node", {"data": []})  # Empty data causes failure
        
        # Legacy runtime: both nodes execute, workflow completes
        results_legacy, run_id_legacy = self.runtime_legacy.execute(workflow.build())
        assert run_id_legacy is not None
        assert "success_node" in results_legacy
        assert "failure_node" in results_legacy
        
        # Check individual results
        success_result = results_legacy["success_node"]
        failure_result = results_legacy["failure_node"]
        
        assert success_result["success"] is True
        assert failure_result["success"] is False
        print(f"LEGACY BUG: Mixed workflow completed despite failure")
        print(f"Success result: {success_result}")
        print(f"Failure result: {failure_result}")
        
        # Fixed runtime: should stop at first failure
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results_fixed, run_id_fixed = self.runtime_fixed.execute(workflow.build())
        
        assert "failure_node" in str(exc_info.value)
        print(f"FIX CONFIRMED: Mixed workflow stopped at failure: {exc_info.value}")
    
    def test_runtime_backward_compatibility_with_traditional_nodes(self):
        """Test that traditional nodes work correctly with new runtime."""
        # Traditional node that doesn't return success/failure pattern
        class TraditionalNode(Node):
            def get_parameters(self) -> dict:
                return {}
            
            def execute(self, **kwargs):
                return {"result": "traditional data", "count": 42}
        
        workflow = WorkflowBuilder()
        workflow.add_node(TraditionalNode, "traditional", {})
        workflow.add_node(MockDataFlowSuccessNode, "dataflow", {
            "data": [{"name": "Test", "email": "test@example.com"}]
        })
        
        # Both runtimes should work correctly
        for runtime in [self.runtime_legacy, self.runtime_fixed]:
            results, run_id = runtime.execute(workflow.build())
            
            assert run_id is not None
            assert "traditional" in results
            assert "dataflow" in results
            
            # Traditional node returns data without success field
            traditional_result = results["traditional"]
            assert "success" not in traditional_result
            assert traditional_result["result"] == "traditional data"
            
            # DataFlow node returns success field
            dataflow_result = results["dataflow"]
            assert dataflow_result["success"] is True
            assert dataflow_result["rows_affected"] == 1
    
    def test_runtime_configuration_validation(self):
        """Test that runtime configuration works correctly."""
        # Test explicit content-aware enabled
        runtime_enabled = LocalRuntime(content_aware_success_detection=True)
        assert runtime_enabled.content_aware_success_detection is True
        
        # Test explicit content-aware disabled
        runtime_disabled = LocalRuntime(content_aware_success_detection=False)
        assert runtime_disabled.content_aware_success_detection is False
        
        # Test default behavior (should be enabled)
        runtime_default = LocalRuntime()
        assert runtime_default.content_aware_success_detection is True
        
        # Test behavior difference
        workflow = WorkflowBuilder()
        workflow.add_node(MockDataFlowFailureNode, "config_test", {"data": None})
        
        # Disabled should complete
        results_disabled, run_id_disabled = runtime_disabled.execute(workflow.build())
        assert run_id_disabled is not None
        assert results_disabled["config_test"]["success"] is False
        
        # Enabled should fail
        with pytest.raises(ContentAwareExecutionError):
            runtime_enabled.execute(workflow.build())
    
    def test_runtime_performance_impact(self):
        """Test that success detection doesn't significantly impact performance."""
        import time
        
        # Create workflow with successful node
        def create_workflow():
            workflow = WorkflowBuilder()
            workflow.add_node(MockDataFlowSuccessNode, "perf_test", {
                "data": [{"name": f"User{i}", "email": f"user{i}@test.com"} for i in range(100)]
            })
            return workflow
        
        # Test legacy runtime
        start_time = time.time()
        for _ in range(5):
            results, run_id = self.runtime_legacy.execute(create_workflow().build())
            assert results["perf_test"]["success"] is True
        legacy_time = time.time() - start_time
        
        # Test fixed runtime
        start_time = time.time()
        for _ in range(5):
            results, run_id = self.runtime_fixed.execute(create_workflow().build())
            assert results["perf_test"]["success"] is True
        fixed_time = time.time() - start_time
        
        print(f"Legacy runtime (5 runs): {legacy_time:.3f}s")
        print(f"Fixed runtime (5 runs): {fixed_time:.3f}s")
        
        # Performance should be similar (within 50% difference for simple test)
        performance_ratio = max(legacy_time, fixed_time) / min(legacy_time, fixed_time)
        assert performance_ratio < 1.5, f"Performance difference too large: {performance_ratio}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])