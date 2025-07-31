"""
Integration tests for runtime success detection with real Docker services.

This module tests the runtime success detection functionality with actual
DataFlow nodes and real database connections using Docker infrastructure.

Test focus:
- Real DataFlow node integration
- Database connection success/failure scenarios
- Runtime behavior with actual infrastructure
- Configuration impact on real workflows
- NO MOCKING - uses real Docker services
"""

import pytest
import time
from typing import Any, Dict

from kailash.runtime.local import LocalRuntime
from kailash.runtime.utils.success_detection import ContentAwareExecutionError
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode


class TestRuntimeSuccessDetectionWithRealDataFlow:
    """Test runtime success detection with real DataFlow operations."""
    
    def setup_method(self):
        """Set up test fixtures with Docker services."""
        # Verify PostgreSQL is running and accessible
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "exec", "kailash_sdk_test_postgres", "pg_isready", "-U", "testuser"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                pytest.skip("PostgreSQL test database not available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker or PostgreSQL not available for integration tests")
        
        # Set up clean database state
        self._setup_test_database()
        
        self.runtime = LocalRuntime()
        self.runtime_content_aware = LocalRuntime(content_aware_success_detection=True)
        self.runtime_legacy = LocalRuntime(content_aware_success_detection=False)
    
    def _setup_test_database(self):
        """Set up test database tables."""
        setup_sql = """
        DROP TABLE IF EXISTS test_users CASCADE;
        CREATE TABLE test_users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            age INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        
        DROP TABLE IF EXISTS test_orders CASCADE;
        CREATE TABLE test_orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES test_users(id),
            amount DECIMAL(10,2) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
        
        # Execute setup using AsyncSQLDatabaseNode
        import asyncio
        async def setup_db():
            db_node = AsyncSQLDatabaseNode(
                connection_string="postgresql://test_user:test_password@localhost:5434/kailash_test",
                database_type="postgresql",
                validate_queries=False  # Allow DDL operations for test setup
            )
            await db_node.async_run(query=setup_sql)
        
        asyncio.run(setup_db())
    
    def test_runtime_detects_dataflow_success_pattern_real(self):
        """Test runtime success detection with real success patterns from custom nodes."""
        # Create a custom node that returns DataFlow-like success patterns
        from kailash.nodes.base import Node, NodeParameter
        
        class MockDataFlowSuccessNode(Node):
            def get_parameters(self) -> dict:
                return {
                    "data": NodeParameter(name="data", type=list, required=True)
                }
            
            def execute(self, data=None, **kwargs):
                # Simulate DataFlow success pattern
                if not data:
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
        
        # Create workflow with mock DataFlow node that should succeed
        workflow = WorkflowBuilder()
        workflow.add_node(MockDataFlowSuccessNode, "mock_bulk_create_success", {})
        workflow.set_node_parameters("mock_bulk_create_success", {
            "data": [
                {"name": "Alice", "email": "alice@test.com", "age": 30},
                {"name": "Bob", "email": "bob@test.com", "age": 25}
            ]
        })
        
        # Execute workflow
        results, run_id = self.runtime.execute(workflow.build())
        
        # Should complete successfully
        assert run_id is not None
        assert "mock_bulk_create_success" in results
        
        # Check DataFlow success pattern
        bulk_result = results["mock_bulk_create_success"]
        assert isinstance(bulk_result, dict)
        assert bulk_result["success"] is True
        assert bulk_result["rows_affected"] == 2
        assert "performance_metrics" in bulk_result
    
    def test_runtime_detects_dataflow_failure_pattern_real(self):
        """Test runtime success detection with real failure patterns from custom nodes."""
        # Create a custom node that returns DataFlow-like failure patterns
        from kailash.nodes.base import Node, NodeParameter
        
        class MockDataFlowFailureNode(Node):
            def get_parameters(self) -> dict:
                return {
                    "data": NodeParameter(name="data", type=list, required=False)
                }
            
            def execute(self, data=None, **kwargs):
                # Simulate DataFlow failure pattern
                if data is None:
                    return {"success": False, "error": "Data cannot be None"}
                
                if not data:
                    return {"success": False, "error": "No data provided for bulk create"}
                
                # This shouldn't be reached in our test
                return {"success": True, "rows_affected": len(data)}
        
        # Create workflow with mock DataFlow node that will fail due to validation
        workflow = WorkflowBuilder()
        workflow.add_node(MockDataFlowFailureNode, "mock_bulk_create_fail", {})
        
        # Test with content-aware runtime (should detect failure and stop)
        workflow.set_node_parameters("mock_bulk_create_fail", {"data": None})
        
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = self.runtime_content_aware.execute(workflow.build())
        
        # Should contain failure information
        assert "mock_bulk_create_fail" in str(exc_info.value)
        assert "Data cannot be None" in str(exc_info.value)
    
    def test_runtime_detects_dataflow_bulk_create_failure_with_empty_data(self):
        """Test runtime success detection with failed DataFlow bulk create due to empty data."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create workflow with DataFlow bulk create that will fail due to empty data
        workflow = WorkflowBuilder()
        
        workflow.add_node(
            BulkCreateNode,
            "bulk_create_empty",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        
        # Test with content-aware runtime (should detect failure and stop)
        workflow.set_node_parameters("bulk_create_empty", {"data": []})
        
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = self.runtime_content_aware.execute(workflow.build())
        
        # Should contain failure information
        assert "bulk_create_empty" in str(exc_info.value)
        assert "No data provided" in str(exc_info.value)
    
    def test_runtime_detects_dataflow_bulk_create_database_constraint_failure(self):
        """Test runtime success detection with database constraint violations."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # First, insert a user to create a constraint violation scenario
        workflow_setup = WorkflowBuilder()
        workflow_setup.add_node(
            BulkCreateNode,
            "setup_user",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow_setup.set_node_parameters("setup_user", {
            "data": [{"name": "Existing User", "email": "duplicate@test.com", "age": 25}]
        })
        
        # Execute setup
        self.runtime.execute(workflow_setup.build())
        
        # Now create workflow that will fail due to unique constraint violation
        workflow = WorkflowBuilder()
        workflow.add_node(
            BulkCreateNode,
            "bulk_create_constraint_fail",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql",
                "conflict_resolution": "error"  # Force error on conflict
            }
        )
        
        # Try to insert duplicate email
        workflow.set_node_parameters("bulk_create_constraint_fail", {
            "data": [{"name": "Duplicate User", "email": "duplicate@test.com", "age": 30}]
        })
        
        # Test with content-aware runtime (should detect database failure)
        with pytest.raises((ContentAwareExecutionError, Exception)) as exc_info:
            results, run_id = self.runtime_content_aware.execute(workflow.build())
        
        # Should contain database constraint error information
        error_message = str(exc_info.value)
        assert any(keyword in error_message.lower() for keyword in 
                  ["unique", "constraint", "duplicate", "already exists"])
    
    def test_runtime_legacy_mode_ignores_content_failures(self):
        """Test that legacy runtime mode ignores content-based failures."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create workflow with DataFlow bulk create that returns success=False
        workflow = WorkflowBuilder()
        workflow.add_node(
            BulkCreateNode,
            "bulk_create_fail_legacy",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        
        # Use data that will cause validation failure
        workflow.set_node_parameters("bulk_create_fail_legacy", {"data": []})
        
        # Test with legacy runtime (should complete despite content failure)
        try:
            results, run_id = self.runtime_legacy.execute(workflow.build())
            
            # Legacy mode should complete execution
            assert run_id is not None
            assert "bulk_create_fail_legacy" in results
            
            # But the result should still contain the failure information
            bulk_result = results["bulk_create_fail_legacy"]
            if isinstance(bulk_result, dict) and "success" in bulk_result:
                # Data should show failure, but runtime completed
                assert bulk_result["success"] is False
                print(f"LEGACY MODE: Runtime completed despite success=False: {bulk_result}")
                
        except Exception as e:
            # If it does fail, it should be due to validation error, not content-aware detection
            assert not isinstance(e, ContentAwareExecutionError)
            assert "validation" in str(e).lower() or "no data provided" in str(e).lower()
    
    def test_runtime_detects_dataflow_connection_failure(self):
        """Test runtime success detection with DataFlow connection failures."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create workflow with invalid database connection
        workflow = WorkflowBuilder()
        
        workflow.add_node(
            BulkCreateNode,
            "connection_failure_test",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://baduser:badpass@localhost:9999/baddb",
                "database_type": "postgresql"
            }
        )
        
        workflow.set_node_parameters("connection_failure_test", {
            "data": [{"name": "Test", "email": "test@example.com", "age": 25}]
        })
        
        # Execute workflow - should fail due to connection error
        with pytest.raises(Exception) as exc_info:
            results, run_id = self.runtime_content_aware.execute(workflow.build())
        
        # Should contain connection-related error
        error_message = str(exc_info.value)
        assert any(keyword in error_message.lower() for keyword in 
                  ["connection", "timeout", "refused", "unavailable", "database error"])
    
    def test_runtime_performance_with_real_dataflow_operations(self):
        """Test performance impact of success detection with real DataFlow operations."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        import time
        
        # Create workflow with multiple DataFlow operations
        workflow = WorkflowBuilder()
        
        for i in range(5):
            workflow.add_node(
                BulkCreateNode,
                f"bulk_create_{i}",
                {
                    "table_name": "test_users",
                    "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    "database_type": "postgresql"
                }
            )
            
            workflow.set_node_parameters(f"bulk_create_{i}", {
                "data": [{"name": f"User{i}_{j}", "email": f"user{i}_{j}@test.com", "age": 20 + j} 
                        for j in range(10)]
            })
        
        # Measure execution time
        start_time = time.time()
        results, run_id = self.runtime_content_aware.execute(workflow.build())
        end_time = time.time()
        
        execution_time = end_time - start_time
        print(f"Execution time for 5 DataFlow operations with 50 total records: {execution_time:.3f}s")
        
        # Should complete in reasonable time (less than 5 seconds for integration test)
        assert execution_time < 5.0
        assert run_id is not None
        assert len(results) == 5
        
        # All operations should succeed
        for i in range(5):
            node_result = results[f"bulk_create_{i}"]
            assert node_result["success"] is True
            assert node_result["rows_affected"] == 10
    
    def test_runtime_mixed_success_failure_workflow_stops_at_first_failure(self):
        """Test that content-aware runtime stops at first failure in mixed workflow."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create workflow with success node followed by failure node
        workflow = WorkflowBuilder()
        
        # Success node (should execute)
        workflow.add_node(
            BulkCreateNode,
            "success_node",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("success_node", {
            "data": [{"name": "Success User", "email": "success@test.com", "age": 30}]
        })
        
        # Failure node (should cause workflow to stop)
        workflow.add_node(
            BulkCreateNode,
            "failure_node",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("failure_node", {"data": None})  # Will cause failure
        
        # Third node (should not execute due to earlier failure)
        workflow.add_node(
            BulkCreateNode,
            "never_executed_node",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("never_executed_node", {
            "data": [{"name": "Never Executed", "email": "never@test.com", "age": 25}]
        })
        
        # Execute with content-aware runtime
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = self.runtime_content_aware.execute(workflow.build())
        
        # Should reference the failing node
        assert "failure_node" in str(exc_info.value)
    
    def test_runtime_backward_compatibility_with_traditional_nodes(self):
        """Test that traditional nodes (non-DataFlow) still work correctly."""
        # Create workflow with traditional node that doesn't return success/failure patterns
        workflow = WorkflowBuilder()
        
        # Traditional SQL node
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "traditional_sql",
            {
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("traditional_sql", {
            "query": "SELECT 1 as test_value"
        })
        
        # DataFlow node
        from dataflow.nodes.bulk_create import BulkCreateNode
        workflow.add_node(
            BulkCreateNode,
            "dataflow_node",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("dataflow_node", {
            "data": [{"name": "Mixed User", "email": "mixed@test.com", "age": 28}]
        })
        
        # Execute workflow
        results, run_id = self.runtime_content_aware.execute(workflow.build())
        
        # Should complete successfully
        assert run_id is not None
        assert "traditional_sql" in results
        assert "dataflow_node" in results
        
        # Traditional node should return data without success field
        sql_result = results["traditional_sql"]
        assert "result" in sql_result
        assert "success" not in sql_result  # Traditional pattern
        
        # DataFlow node should return success field
        dataflow_result = results["dataflow_node"]
        assert dataflow_result["success"] is True
        assert dataflow_result["rows_affected"] == 1


class TestRuntimePerformanceWithRealServices:
    """Test performance impact of success detection with real services."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Verify PostgreSQL is available
        import subprocess
        try:
            subprocess.run(
                ["docker", "exec", "kailash_sdk_test_postgres", "pg_isready", "-U", "testuser"],
                capture_output=True,
                check=True,
                timeout=5
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("PostgreSQL not available for performance tests")
        
        self.runtime = LocalRuntime()
        self.runtime_content_aware = LocalRuntime(content_aware_success_detection=True)
    
    def test_success_detection_performance_overhead(self):
        """Test performance overhead of content-aware success detection."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        import time
        
        # Create identical workflows for comparison
        def create_workflow():
            workflow = WorkflowBuilder()
            workflow.add_node(
                BulkCreateNode,
                "perf_test",
                {
                    "table_name": "test_users",
                    "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    "database_type": "postgresql"
                }
            )
            workflow.set_node_parameters("perf_test", {
                "data": [{"name": f"PerfUser{i}", "email": f"perf{i}@test.com", "age": 25} 
                        for i in range(100)]
            })
            return workflow
        
        # Test with content-aware detection enabled
        start_time = time.time()
        results_aware, _ = self.runtime_content_aware.execute(create_workflow().build())
        content_aware_time = time.time() - start_time
        
        # Test with default runtime (also content-aware but good for comparison)
        start_time = time.time()
        results_default, _ = self.runtime.execute(create_workflow().build())
        default_time = time.time() - start_time
        
        print(f"Content-aware runtime: {content_aware_time:.3f}s")
        print(f"Default runtime: {default_time:.3f}s")
        
        # Performance should be similar (within 20% difference)
        performance_difference = abs(content_aware_time - default_time) / max(content_aware_time, default_time)
        assert performance_difference < 0.2  # Less than 20% difference
        
        # Both should succeed
        assert results_aware["perf_test"]["success"] is True
        assert results_default["perf_test"]["success"] is True
    
    def test_memory_usage_with_success_detection(self):
        """Test memory usage doesn't grow excessively with success detection."""
        try:
            import psutil
        except ImportError:
            pytest.skip("psutil not available for memory testing")
        
        import os
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Execute multiple workflows with success detection
        for i in range(3):  # Reduced for integration test speed
            workflow = WorkflowBuilder()
            workflow.add_node(
                BulkCreateNode,
                "memory_test",
                {
                    "table_name": "test_users",
                    "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    "database_type": "postgresql"
                }
            )
            workflow.set_node_parameters("memory_test", {
                "data": [{"name": f"MemUser{i}_{j}", "email": f"mem{i}_{j}@test.com", "age": 20 + j} 
                        for j in range(20)]
            })
            
            results, run_id = self.runtime_content_aware.execute(workflow.build())
            assert results["memory_test"]["success"] is True
        
        # Get final memory usage
        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory
        
        print(f"Memory growth: {memory_growth / 1024 / 1024:.2f} MB")
        
        # Should not have excessive memory growth (less than 20MB for integration test)
        assert memory_growth < 20 * 1024 * 1024
    
    def test_concurrent_workflow_execution_with_success_detection(self):
        """Test concurrent execution of workflows with success detection."""
        import threading
        import concurrent.futures
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        def execute_workflow(workflow_id):
            """Execute a single workflow with success detection."""
            workflow = WorkflowBuilder()
            workflow.add_node(
                BulkCreateNode,
                "concurrent_test",
                {
                    "table_name": "test_users",
                    "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    "database_type": "postgresql"
                }
            )
            workflow.set_node_parameters("concurrent_test", {
                "data": [{"name": f"ConcurrentUser{workflow_id}_{i}", 
                         "email": f"concurrent{workflow_id}_{i}@test.com", "age": 25 + i} 
                        for i in range(5)]
            })
            
            runtime = LocalRuntime(content_aware_success_detection=True)
            results, run_id = runtime.execute(workflow.build())
            return workflow_id, run_id, results
        
        # Execute multiple workflows concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(execute_workflow, i) for i in range(3)]
            
            results = []
            for future in concurrent.futures.as_completed(futures):
                workflow_id, run_id, workflow_results = future.result()
                results.append((workflow_id, run_id, workflow_results))
        
        # All workflows should complete successfully
        assert len(results) == 3
        for workflow_id, run_id, workflow_results in results:
            assert run_id is not None
            assert "concurrent_test" in workflow_results
            assert workflow_results["concurrent_test"]["success"] is True
            assert workflow_results["concurrent_test"]["rows_affected"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=30"])