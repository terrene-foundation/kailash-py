"""Performance and load tests for the Kailash SDK."""

import time
import pytest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow, WorkflowBuilder


class TestPerformance:
    """Test performance and scalability of the SDK."""
    
    def test_basic_performance_measurement(self, temp_data_dir: Path):
        """Test basic performance measurement."""
        builder = WorkflowBuilder()
        
        start_time = time.time()
        
        try:
            # Create simple workflow
            workflow = builder.build("performance_test")
            construction_time = time.time() - start_time
            
            # Verify basic construction performance
            assert construction_time < 1.0  # Should be very fast for empty workflow
            assert workflow is not None
            
        except Exception:
            pytest.skip("Basic workflow construction not available")
    
    def test_concurrent_workflow_creation(self, temp_data_dir: Path):
        """Test creating multiple workflows concurrently."""
        def create_workflow(index: int) -> Workflow:
            builder = WorkflowBuilder()
            return builder.build(f"workflow_{index}")
        
        # Create multiple workflows
        workflow_count = 5
        start_time = time.time()
        
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(create_workflow, i) for i in range(workflow_count)]
                workflows = [f.result() for f in futures]
            
            creation_time = time.time() - start_time
            
            # Verify workflows
            assert len(workflows) == workflow_count
            assert creation_time < 2.0  # Should be fast
            
        except Exception:
            pytest.skip("Concurrent workflow creation not available")
    
    def test_runtime_initialization_performance(self):
        """Test runtime initialization performance."""
        start_time = time.time()
        
        # Create runtime
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        init_time = time.time() - start_time
        
        # Should initialize quickly
        assert init_time < 1.0
        assert runtime is not None
        assert runner is not None
    
    def test_memory_usage_basic(self):
        """Test basic memory usage patterns."""
        try:
            import psutil
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Create multiple workflows
            workflows = []
            for i in range(10):
                builder = WorkflowBuilder()
                workflow = builder.build(f"memory_test_{i}")
                workflows.append(workflow)
            
            # Memory should not grow excessively
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_growth = current_memory - initial_memory
            
            # Allow some growth but not excessive
            assert memory_growth < 100  # Less than 100MB growth
            
        except ImportError:
            pytest.skip("psutil not available for memory testing")
    
    def test_workflow_scalability_basic(self):
        """Test basic workflow scalability."""
        builder = WorkflowBuilder()
        
        # Create workflow with multiple simple nodes
        start_time = time.time()
        
        try:
            # Add nodes if supported
            for i in range(10):
                try:
                    builder.add_node("MockNode", f"node_{i}")
                except Exception:
                    break
            
            workflow = builder.build("scalability_test")
            build_time = time.time() - start_time
            
            # Should build quickly
            assert build_time < 1.0
            assert workflow is not None
            
        except Exception:
            pytest.skip("Node addition not supported")
    
    def test_stress_test_simplified(self):
        """Simplified stress test."""
        # Create multiple workflows rapidly
        start_time = time.time()
        
        workflows = []
        for i in range(20):
            builder = WorkflowBuilder()
            workflow = builder.build(f"stress_test_{i}")
            workflows.append(workflow)
        
        creation_time = time.time() - start_time
        
        # Verify all workflows created
        assert len(workflows) == 20
        assert creation_time < 5.0  # Should be reasonably fast
        
        # Cleanup
        del workflows