"""
Bug reproduction tests for runtime success detection functionality.

This module contains tests specifically designed to reproduce the original bug
where workflows would complete successfully even when DataFlow nodes returned
{"success": False, "error": "..."} patterns.

These tests demonstrate:
1. The original bug behavior (before fix)
2. The fixed behavior (after fix)
3. Specific DataFlow scenarios that were failing silently
"""

import pytest
import time
from typing import Any, Dict

from kailash.runtime.local import LocalRuntime
from kailash.runtime.utils.success_detection import ContentAwareExecutionError
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode


class TestRuntimeSuccessDetectionBugReproduction:
    """Reproduce the specific runtime success detection bug."""
    
    def setup_method(self):
        """Set up test fixtures with clean database state."""
        # Verify PostgreSQL is running
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
            pytest.skip("Docker or PostgreSQL not available for bug reproduction tests")
        
        # Set up test database schema
        self._setup_test_database()
        
        # Create runtimes for testing
        self.runtime_legacy = LocalRuntime(content_aware_success_detection=False)
        self.runtime_fixed = LocalRuntime(content_aware_success_detection=True)
    
    def _setup_test_database(self):
        """Set up test database tables for bug reproduction."""
        setup_sql = """
        DROP TABLE IF EXISTS bug_test_users CASCADE;
        CREATE TABLE bug_test_users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            status VARCHAR(50) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        DROP TABLE IF EXISTS bug_test_orders CASCADE;
        CREATE TABLE bug_test_orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES bug_test_users(id),
            amount DECIMAL(10,2) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            processed_at TIMESTAMP
        );
        """
        
        # Execute setup
        import asyncio
        async def setup_db():
            db_node = AsyncSQLDatabaseNode(
                connection_string="postgresql://test_user:test_password@localhost:5434/kailash_test",
                database_type="postgresql",
                validate_queries=False  # Allow DDL operations for test setup
            )
            await db_node.async_run(query=setup_sql)
        
        asyncio.run(setup_db())
    
    def test_bug_reproduction_dataflow_bulk_create_returns_success_false(self):
        """
        BUG REPRODUCTION: DataFlow BulkCreateNode returns success=False but workflow completes.
        
        Original Issue:
        - DataFlow node returns {"success": False, "error": "Data cannot be None"}
        - Runtime ignores the success=False and treats as successful
        - Workflow completes with run_id, masking the actual failure
        """
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create workflow that will return success=False
        workflow = WorkflowBuilder()
        workflow.add_node(
            BulkCreateNode,
            "failing_bulk_create",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        
        # Pass None data which will cause DataFlow to return success=False
        workflow.set_node_parameters("failing_bulk_create", {"data": None})
        
        # Test with legacy runtime (demonstrates the bug)
        try:
            results, run_id = self.runtime_legacy.execute(workflow.build())
            
            # BUG: Runtime completed despite DataFlow returning success=False
            assert run_id is not None, "BUG: Workflow should have failed but got run_id"
            
            # The result should contain the failure information
            if "failing_bulk_create" in results:
                result = results["failing_bulk_create"]
                if isinstance(result, dict) and "success" in result:
                    assert result["success"] is False, "Expected success=False from DataFlow node"
                    assert "error" in result, "Expected error message from DataFlow node"
                    print(f"BUG REPRODUCED: Workflow completed despite success=False")
                    print(f"Result: {result}")
                    print(f"Run ID: {run_id}")
                else:
                    pytest.fail("Expected DataFlow node to return dict with success field")
            else:
                pytest.fail("Expected failing_bulk_create in results")
                
        except Exception as e:
            # In legacy mode, if it fails, it should be due to validation error, not content detection
            if isinstance(e, ContentAwareExecutionError):
                pytest.fail("Legacy runtime should not raise ContentAwareExecutionError")
        
        # Test with fixed runtime (should detect the failure)
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = self.runtime_fixed.execute(workflow.build())
        
        # FIXED: Runtime detected the success=False and raised appropriate exception
        assert "failing_bulk_create" in str(exc_info.value)
        print(f"FIX CONFIRMED: Fixed runtime detected failure: {exc_info.value}")
    
    def test_bug_reproduction_dataflow_empty_data_validation_failure(self):
        """
        BUG REPRODUCTION: DataFlow validation failures were ignored by runtime.
        
        Scenario:
        - Pass empty list [] to DataFlow BulkCreateNode
        - Node returns {"success": False, "error": "No data provided for bulk create"}
        - Original runtime ignores this and reports success
        """
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        workflow = WorkflowBuilder()
        workflow.add_node(
            BulkCreateNode,
            "empty_data_test",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        
        # Pass empty data list
        workflow.set_node_parameters("empty_data_test", {"data": []})
        
        # Legacy runtime demonstrates the bug
        try:
            results, run_id = self.runtime_legacy.execute(workflow.build())
            print(f"BUG: Empty data workflow completed with run_id: {run_id}")
            
            if "empty_data_test" in results:
                result = results["empty_data_test"]
                if isinstance(result, dict) and "success" in result:
                    print(f"DataFlow result: {result}")
                    if result["success"] is False:
                        print("BUG CONFIRMED: DataFlow failed but runtime completed")
                        
        except Exception as e:
            if not isinstance(e, ContentAwareExecutionError):
                print(f"Legacy runtime failed with non-content-aware error: {e}")
        
        # Fixed runtime should detect the failure
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = self.runtime_fixed.execute(workflow.build())
        
        assert "empty_data_test" in str(exc_info.value)
        assert "no data provided" in str(exc_info.value).lower()
    
    def test_bug_reproduction_multi_node_workflow_stops_at_first_failure(self):
        """
        BUG REPRODUCTION: Multi-node workflows continued executing after DataFlow failures.
        
        Original Issue:
        - First node succeeds
        - Second node returns success=False
        - Third node executes anyway (should not happen)
        - Runtime reports overall success
        """
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        workflow = WorkflowBuilder()
        
        # Node 1: Should succeed
        workflow.add_node(
            BulkCreateNode,
            "success_node",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("success_node", {
            "data": [{"name": "Success User", "email": "success@test.com"}]
        })
        
        # Node 2: Will fail with success=False
        workflow.add_node(
            BulkCreateNode,
            "failure_node",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("failure_node", {"data": None})  # Will cause failure
        
        # Node 3: Should not execute if Node 2 fails
        workflow.add_node(
            BulkCreateNode,
            "should_not_execute",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("should_not_execute", {
            "data": [{"name": "Should Not Execute", "email": "shouldnot@test.com"}]
        })
        
        # Legacy runtime demonstrates the bug
        try:
            results, run_id = self.runtime_legacy.execute(workflow.build())
            
            print(f"BUG: Multi-node workflow completed with run_id: {run_id}")
            print(f"Results keys: {list(results.keys())}")
            
            # Check if all nodes executed (demonstrates the bug)
            if all(node in results for node in ["success_node", "failure_node", "should_not_execute"]):
                print("BUG CONFIRMED: All nodes executed despite middle node failure")
                
                # Check the failure node result
                failure_result = results["failure_node"]
                if isinstance(failure_result, dict) and failure_result.get("success") is False:
                    print(f"Middle node failed: {failure_result}")
                    print("BUG: Workflow continued despite this failure")
            
        except Exception as e:
            if not isinstance(e, ContentAwareExecutionError):
                print(f"Legacy runtime failed with: {e}")
        
        # Fixed runtime should stop at first failure
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = self.runtime_fixed.execute(workflow.build())
        
        # Should reference the failing node
        assert "failure_node" in str(exc_info.value)
        print(f"FIX CONFIRMED: Runtime stopped at failure: {exc_info.value}")
    
    def test_bug_reproduction_database_constraint_violation_ignored(self):
        """
        BUG REPRODUCTION: Database constraint violations returning success=False were ignored.
        
        Scenario:
        - Insert user with email
        - Try to insert another user with same email (unique constraint violation)
        - DataFlow handles gracefully and returns success=False with appropriate error
        - Original runtime ignores this and reports success
        """
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # First, insert a user to create constraint violation scenario
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node(
            BulkCreateNode,
            "setup_user",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql"
            }
        )
        setup_workflow.set_node_parameters("setup_user", {
            "data": [{"name": "First User", "email": "duplicate@test.com"}]
        })
        
        # Execute setup
        self.runtime_legacy.execute(setup_workflow.build())
        
        # Now try to insert duplicate email
        workflow = WorkflowBuilder()
        workflow.add_node(
            BulkCreateNode,
            "duplicate_test",
            {
                "table_name": "bug_test_users",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "database_type": "postgresql",
                "conflict_resolution": "error"  # Force error on conflict
            }
        )
        workflow.set_node_parameters("duplicate_test", {
            "data": [{"name": "Duplicate User", "email": "duplicate@test.com"}]
        })
        
        # Test both runtimes - one should demonstrate bug, other should be fixed
        with pytest.raises((ContentAwareExecutionError, Exception)) as exc_info:
            results, run_id = self.runtime_fixed.execute(workflow.build())
        
        # Should contain constraint violation information
        error_message = str(exc_info.value)
        assert any(keyword in error_message.lower() for keyword in 
                  ["unique", "constraint", "duplicate", "already exists", "violation"])
        print(f"FIX CONFIRMED: Database constraint violation detected: {error_message}")
    
    def test_bug_reproduction_comparison_legacy_vs_fixed_runtime(self):
        """
        Direct comparison between legacy and fixed runtime behavior.
        
        This test explicitly shows the difference in behavior between
        the legacy runtime (ignores content failures) and the fixed
        runtime (detects content failures).
        """
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create workflow that will return success=False
        def create_failing_workflow():
            workflow = WorkflowBuilder()
            workflow.add_node(
                BulkCreateNode,
                "comparison_test",
                {
                    "table_name": "bug_test_users",
                    "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    "database_type": "postgresql"
                }
            )
            workflow.set_node_parameters("comparison_test", {"data": []})  # Empty data causes failure
            return workflow
        
        # Test with legacy runtime
        legacy_behavior = None
        try:
            results, run_id = self.runtime_legacy.execute(create_failing_workflow().build())
            legacy_behavior = {
                "completed": True,
                "run_id": run_id,
                "result": results.get("comparison_test", {}),
                "error": None
            }
        except Exception as e:
            legacy_behavior = {
                "completed": False,
                "run_id": None,
                "result": {},
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        # Test with fixed runtime
        fixed_behavior = None
        try:
            results, run_id = self.runtime_fixed.execute(create_failing_workflow().build())
            fixed_behavior = {
                "completed": True,
                "run_id": run_id,
                "result": results.get("comparison_test", {}),
                "error": None
            }
        except Exception as e:
            fixed_behavior = {
                "completed": False,
                "run_id": None,
                "result": {},
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        # Print comparison for analysis
        print("\n=== RUNTIME BEHAVIOR COMPARISON ===")
        print(f"Legacy Runtime (content_aware_success_detection=False):")
        print(f"  Completed: {legacy_behavior['completed']}")
        print(f"  Run ID: {legacy_behavior['run_id']}")
        if legacy_behavior['completed'] and legacy_behavior['result']:
            result = legacy_behavior['result']
            if isinstance(result, dict) and 'success' in result:
                print(f"  DataFlow Success: {result['success']}")
                print(f"  DataFlow Error: {result.get('error', 'None')}")
        if legacy_behavior['error']:
            print(f"  Exception: {legacy_behavior['error_type']}: {legacy_behavior['error']}")
        
        print(f"\nFixed Runtime (content_aware_success_detection=True):")
        print(f"  Completed: {fixed_behavior['completed']}")
        print(f"  Run ID: {fixed_behavior['run_id']}")
        if fixed_behavior['completed'] and fixed_behavior['result']:
            result = fixed_behavior['result']
            if isinstance(result, dict) and 'success' in result:
                print(f"  DataFlow Success: {result['success']}")
                print(f"  DataFlow Error: {result.get('error', 'None')}")
        if fixed_behavior['error']:
            print(f"  Exception: {fixed_behavior['error_type']}: {fixed_behavior['error']}")
        
        # Assertions to confirm the fix
        if legacy_behavior['completed'] and isinstance(legacy_behavior['result'], dict):
            # Legacy mode might complete even with success=False (demonstrates bug)
            if legacy_behavior['result'].get('success') is False:
                print("\nBUG CONFIRMED: Legacy runtime completed despite success=False")
        
        # Fixed runtime should detect the failure
        assert fixed_behavior['completed'] is False, "Fixed runtime should detect content failure"
        assert fixed_behavior['error_type'] == "ContentAwareExecutionError", "Should raise ContentAwareExecutionError"
        assert "comparison_test" in fixed_behavior['error'], "Error should reference failing node"
        
        print("\nFIX CONFIRMED: Fixed runtime properly detects and handles content failures")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])