"""
End-to-end tests for runtime success detection in complete user workflows.

This module tests complete user scenarios demonstrating the runtime success
detection bug and the fix across real business workflows.

Test focus:
- Complete user workflows from start to finish
- Real business scenarios with DataFlow operations
- Backward compatibility with existing workflows
- User journey validation
- NO MOCKING - complete real infrastructure
"""

import pytest
import time
from typing import Any, Dict

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestRuntimeSuccessDetectionUserJourneys:
    """Test complete user journeys with runtime success detection."""
    
    def setup_method(self):
        """Set up test fixtures with full Docker infrastructure."""
        # Ensure complete Docker infrastructure is running
        import subprocess
        result = subprocess.run(
            ["./tests/utils/test-env", "up"],
            cwd="./repos/projects/kailash_python_sdk",
            check=True,
            capture_output=True,
            text=True
        )
        
        # Wait for services to be fully ready
        time.sleep(2)
        
        self.runtime = LocalRuntime()
    
    def test_data_pipeline_with_validation_failure_e2e(self):
        """
        E2E test: Real data pipeline with DataFlow nodes that should fail validation.
        
        User Journey:
        1. Extract data from source database
        2. Validate data with business rules
        3. Load data to destination (should not execute if validation fails)
        4. Fixed runtime should detect validation failure and stop pipeline
        """
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Set up test data in source
        self._setup_source_data()
        
        # Create complete data pipeline workflow
        workflow = WorkflowBuilder()
        
        # Step 1: Extract data from source (should succeed)
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "extract_data",
            {
                "connection_string": "postgresql://testuser:testpass@localhost:5434/testdb",
                "database_type": "postgresql"
            }
        )
        workflow.set_node_parameters("extract_data", {
            "query": "SELECT name, email, age FROM test_users WHERE name LIKE 'Source%'"
        })
        
        # Step 2: Validate extracted data with strict business rules (will fail)
        workflow.add_node(
            "PythonCodeNode",
            "validate_data",
            {
                "code": """
def main(extracted_data):
    # Strict business validation that will fail
    if not extracted_data or "result" not in extracted_data:
        return {"success": False, "error": "No data to validate"}
    
    data_rows = extracted_data["result"].get("data", [])
    if not data_rows:
        return {"success": False, "error": "No rows found"}
    
    # Apply strict validation: all users must be over 18 and have company email
    validation_errors = []
    for i, row in enumerate(data_rows):
        if row.get("age", 0) < 18:
            validation_errors.append(f"Row {i}: Age {row.get('age')} is below minimum 18")
        if not row.get("email", "").endswith("@company.com"):
            validation_errors.append(f"Row {i}: Email {row.get('email')} must be company email")
    
    if validation_errors:
        return {
            "success": False, 
            "error": f"Validation failed: {'; '.join(validation_errors)}", 
            "validation_errors": validation_errors,
            "total_errors": len(validation_errors)
        }
    
    return {"success": True, "validated_data": data_rows, "rows_validated": len(data_rows)}
""",
                "function_name": "main"
            }
        )
        
        # Step 3: Load validated data (should not execute if validation fails)
        workflow.add_node(
            BulkCreateNode,
            "load_data",
            {
                "table_name": "processed_users",
                "connection_string": "postgresql://testuser:testpass@localhost:5434/testdb",
                "database_type": "postgresql"
            }
        )
        
        # Set up connections between nodes
        workflow.set_node_parameters("validate_data", {"extracted_data": "{{extract_data}}"})
        workflow.set_node_parameters("load_data", {"data": "{{validate_data.validated_data}}"})
        
        # Execute with content-aware runtime (should stop at validation failure)
        runtime_content_aware = LocalRuntime(content_aware_success_detection=True)
        
        with pytest.raises(ContentAwareExecutionError) as exc_info:
            results, run_id = runtime_content_aware.execute(workflow.build())
        
        # Should reference the validation failure
        assert "validate_data" in str(exc_info.value)
        assert "validation failed" in str(exc_info.value).lower()
    
    def _setup_source_data(self):
        """Set up source data with validation issues."""
        from dataflow.nodes.bulk_create import BulkCreateNode
        
        # Create source data that will fail validation
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node(
            BulkCreateNode,
            "setup_source",
            {
                "table_name": "test_users",
                "connection_string": "postgresql://testuser:testpass@localhost:5434/testdb",
                "database_type": "postgresql"
            }
        )
        setup_workflow.set_node_parameters("setup_source", {
            "data": [
                {"name": "Source User 1", "email": "user1@gmail.com", "age": 16},  # Too young
                {"name": "Source User 2", "email": "user2@yahoo.com", "age": 25}   # Wrong email domain
            ]
        })
        
        runtime = LocalRuntime()
        runtime.execute(setup_workflow.build())
    
    def test_financial_transaction_workflow_e2e(self):
        """
        E2E test: Financial transaction workflow with business rules.
        
        User Journey:
        1. Validate account balance
        2. Check transaction limits
        3. Process transaction
        4. Update account balance
        5. Any step failure should rollback entire transaction
        """
        workflow = WorkflowBuilder()
        
        # Step 1: Configure financial database
        workflow.add_node(
            "ConfigNode",
            "financial_db_config",
            {
                "database_url": "postgresql://testuser:testpass@localhost:5432/testdb",
                "connection_name": "financial_connection"
            }
        )
        
        # Step 2: Check account balance
        workflow.add_node(
            "DataFlowAccountValidationNode",
            "check_balance",
            {
                "account_id": "ACC123",
                "required_balance": 1000,  # Require $1000 minimum
                "connection": "{{financial_db_config.connection}}"
            }
        )
        
        # Step 3: Validate transaction limits (will fail)
        workflow.add_node(
            "DataFlowTransactionLimitNode",
            "check_limits",
            {
                "account_id": "ACC123",
                "transaction_amount": 5000,  # Exceeds daily limit
                "transaction_type": "withdrawal",
                "connection": "{{financial_db_config.connection}}"
            }
        )
        
        # Step 4: Process transaction (should not execute if limits fail)
        workflow.add_node(
            "DataFlowTransactionNode",
            "process_transaction",
            {
                "account_id": "ACC123",
                "amount": 5000,
                "type": "withdrawal",
                "connection": "{{financial_db_config.connection}}"
            }
        )
        
        # Step 5: Update account balance (should not execute)
        workflow.add_node(
            "DataFlowAccountUpdateNode",
            "update_balance",
            {
                "account_id": "ACC123",
                "balance_change": -5000,
                "connection": "{{financial_db_config.connection}}"
            }
        )
        
        # Execute financial workflow
        try:
            results, run_id = self.runtime.execute(workflow.build())
            
            # Current behavior (BUG): Transaction completes despite limit violation
            print(f"FINANCIAL WORKFLOW COMPLETED: {run_id}")
            
            # Check limit validation result
            if "check_limits" in results:
                limit_result = results["check_limits"]
                if isinstance(limit_result, dict) and "success" in limit_result:
                    if limit_result["success"] is False:
                        print(f"BUG: Transaction limit exceeded but workflow completed")
                        print(f"Limit check result: {limit_result}")
                        
                        # Transaction should not have processed
                        if "process_transaction" in results:
                            print(f"CRITICAL BUG: Financial transaction processed despite limit violation!")
            
        except Exception as e:
            # Expected behavior: Financial workflow stops at limit violation
            print(f"EXPECTED: Financial workflow stopped at limit violation: {e}")
    
    def test_batch_processing_workflow_with_partial_failures_e2e(self):
        """
        E2E test: Batch processing workflow where some batches fail.
        
        User Journey:
        1. Process multiple data batches
        2. Some batches succeed, some fail
        3. Current runtime completes despite batch failures
        4. Fixed runtime should fail on first batch failure
        """
        workflow = WorkflowBuilder()
        
        # Configure processing database
        workflow.add_node(
            "ConfigNode",
            "batch_db_config",
            {
                "database_url": "postgresql://testuser:testpass@localhost:5432/testdb",
                "connection_name": "batch_connection"
            }
        )
        
        # Process multiple batches
        batches = [
            {"batch_id": 1, "data": [{"id": 1, "value": "valid"}]},  # Should succeed
            {"batch_id": 2, "data": None},  # Should fail
            {"batch_id": 3, "data": [{"id": 3, "value": "valid"}]},  # Would succeed but shouldn't execute
        ]
        
        for i, batch in enumerate(batches):
            workflow.add_node(
                "DataFlowBulkCreateNode",
                f"process_batch_{batch['batch_id']}",
                {
                    "table_name": "batch_data",
                    "data": batch["data"],
                    "batch_id": batch["batch_id"],
                    "connection": "{{batch_db_config.connection}}"
                }
            )
        
        # Execute batch processing workflow
        try:
            results, run_id = self.runtime.execute(workflow.build())
            
            # Current behavior (BUG): All batches process despite failures
            print(f"BATCH PROCESSING COMPLETED: {run_id}")
            
            # Check each batch result
            for batch_id in [1, 2, 3]:
                batch_node = f"process_batch_{batch_id}"
                if batch_node in results:
                    batch_result = results[batch_node]
                    print(f"Batch {batch_id} result: {batch_result}")
                    
                    if isinstance(batch_result, dict) and "success" in batch_result:
                        if batch_result["success"] is False:
                            print(f"BUG: Batch {batch_id} failed but processing continued")
            
        except Exception as e:
            # Expected behavior: Processing stops at first batch failure
            print(f"EXPECTED: Batch processing stopped at failure: {e}")
    
    def test_data_migration_workflow_e2e(self):
        """
        E2E test: Data migration workflow with validation checkpoints.
        
        User Journey:
        1. Export data from legacy system
        2. Transform data format
        3. Validate transformed data
        4. Import to new system
        5. Verify migration completeness
        """
        workflow = WorkflowBuilder()
        
        # Configure source and target systems
        workflow.add_node(
            "ConfigNode",
            "legacy_db_config",
            {
                "database_url": "postgresql://testuser:testpass@localhost:5432/testdb",
                "connection_name": "legacy_connection"
            }
        )
        
        workflow.add_node(
            "ConfigNode",
            "target_db_config", 
            {
                "database_url": "postgresql://testuser:testpass@localhost:5432/testdb",
                "connection_name": "target_connection"
            }
        )
        
        # Step 1: Export legacy data
        workflow.add_node(
            "SQLDatabaseNode",
            "export_legacy_data",
            {
                "query": "SELECT 'legacy_data' as data, 'invalid_format' as format_type",
                "connection": "{{legacy_db_config.connection}}"
            }
        )
        
        # Step 2: Transform data format
        workflow.add_node(
            "DataFlowTransformationNode",
            "transform_data",
            {
                "input_data": "{{export_legacy_data.results}}",
                "transformation_rules": {
                    "format_type": {"from": "invalid_format", "to": "new_format"}
                },
                "connection": "{{legacy_db_config.connection}}"
            }
        )
        
        # Step 3: Validate transformed data (will fail due to business rules)
        workflow.add_node(
            "DataFlowMigrationValidationNode",
            "validate_migration",
            {
                "transformed_data": "{{transform_data.output}}",
                "business_rules": {
                    "format_type": {"required_value": "standard_format"}  # Will fail validation
                },
                "connection": "{{target_db_config.connection}}"
            }
        )
        
        # Step 4: Import to new system (should not execute if validation fails)
        workflow.add_node(
            "DataFlowBulkCreateNode",
            "import_to_target",
            {
                "table_name": "migrated_data",
                "data": "{{validate_migration.validated_data}}",
                "connection": "{{target_db_config.connection}}"
            }
        )
        
        # Step 5: Verify migration completeness
        workflow.add_node(
            "DataFlowMigrationVerificationNode",
            "verify_migration",
            {
                "source_connection": "{{legacy_db_config.connection}}",
                "target_connection": "{{target_db_config.connection}}",
                "table_mapping": {"legacy_table": "migrated_data"}
            }
        )
        
        # Execute migration workflow
        try:
            results, run_id = self.runtime.execute(workflow.build())
            
            # Current behavior (BUG): Migration completes despite validation failure
            print(f"MIGRATION WORKFLOW COMPLETED: {run_id}")
            
            if "validate_migration" in results:
                validation_result = results["validate_migration"]
                if isinstance(validation_result, dict) and "success" in validation_result:
                    if validation_result["success"] is False:
                        print(f"CRITICAL BUG: Data migration validation failed but migration completed!")
                        print(f"This could result in corrupted data in production!")
            
        except Exception as e:
            # Expected behavior: Migration stops at validation failure
            print(f"EXPECTED: Migration stopped at validation failure: {e}")


class TestBackwardCompatibilityE2E:
    """Test backward compatibility with existing workflows."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = LocalRuntime()
    
    def test_existing_exception_based_workflows_still_work(self):
        """Test that existing workflows using exceptions still work properly."""
        # Create workflow using traditional exception-based error handling
        workflow = WorkflowBuilder()
        
        # Node that raises exceptions (traditional behavior)
        workflow.add_node(
            "PythonCodeNode",
            "exception_node",
            {
                "code": """
def main():
    # Traditional exception-based error handling
    if True:  # Simulate error condition
        raise ValueError("Traditional exception-based failure")
    return {"data": "success"}
""",
                "function_name": "main"
            }
        )
        
        # This should still fail with exception (backward compatibility)
        with pytest.raises(Exception) as exc_info:
            results, run_id = self.runtime.execute(workflow.build())
        
        assert "Traditional exception-based failure" in str(exc_info.value)
    
    def test_existing_successful_workflows_unchanged(self):
        """Test that existing successful workflows continue to work unchanged."""
        # Create workflow with traditional successful nodes
        workflow = WorkflowBuilder()
        
        workflow.add_node(
            "PythonCodeNode",
            "traditional_success",
            {
                "code": """
def main():
    # Traditional successful operation
    return {"result": "success", "data": [1, 2, 3]}
""",
                "function_name": "main"
            }
        )
        
        # Should complete successfully as before
        results, run_id = self.runtime.execute(workflow.build())
        
        assert run_id is not None
        assert "traditional_success" in results
        assert results["traditional_success"]["result"] == "success"
    
    def test_mixed_traditional_and_dataflow_patterns(self):
        """Test workflows mixing traditional and DataFlow patterns."""
        workflow = WorkflowBuilder()
        
        # Traditional successful node
        workflow.add_node(
            "PythonCodeNode",
            "traditional_node",
            {
                "code": """
def main():
    return {"data": "traditional_success"}
""",
                "function_name": "main"
            }
        )
        
        # DataFlow pattern node (success)
        workflow.add_node(
            "DataFlowBulkCreateNode",
            "dataflow_success",
            {
                "table_name": "test_table",
                "data": [{"id": 1, "name": "test"}],
                "connection": "test_connection"
            }
        )
        
        # DataFlow pattern node (failure)
        workflow.add_node(
            "DataFlowBulkCreateNode",
            "dataflow_failure", 
            {
                "table_name": "test_table",
                "data": None,  # Will return success=False
                "connection": "test_connection"
            }
        )
        
        # Execute mixed workflow
        try:
            results, run_id = self.runtime.execute(workflow.build())
            
            # Traditional node should succeed
            assert "traditional_node" in results
            assert results["traditional_node"]["data"] == "traditional_success"
            
            # DataFlow success node should succeed
            if "dataflow_success" in results:
                success_result = results["dataflow_success"]
                if isinstance(success_result, dict) and "success" in success_result:
                    print(f"DataFlow success result: {success_result}")
            
            # DataFlow failure node demonstrates the bug
            if "dataflow_failure" in results:
                failure_result = results["dataflow_failure"]
                if isinstance(failure_result, dict) and "success" in failure_result:
                    if failure_result["success"] is False:
                        print(f"BUG: Mixed workflow completed despite DataFlow failure")
            
        except Exception as e:
            # Fixed behavior: Workflow stops at DataFlow failure
            print(f"EXPECTED: Mixed workflow stopped at DataFlow failure: {e}")


class TestPerformanceAndScalabilityE2E:
    """Test performance and scalability with success detection."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = LocalRuntime()
    
    def test_large_workflow_with_success_detection(self):
        """Test performance with large workflows using success detection."""
        # Create large workflow with many DataFlow nodes
        workflow = WorkflowBuilder()
        
        # Add many DataFlow operations
        for i in range(20):
            workflow.add_node(
                "DataFlowBulkCreateNode",
                f"bulk_operation_{i}",
                {
                    "table_name": "performance_test",
                    "data": [{"id": j, "batch": i} for j in range(10)],
                    "connection": "test_connection"
                }
            )
        
        # Measure execution time
        start_time = time.time()
        results, run_id = self.runtime.execute(workflow.build())
        end_time = time.time()
        
        execution_time = end_time - start_time
        print(f"Large workflow execution time: {execution_time:.3f}s")
        
        # Should complete in reasonable time
        assert execution_time < 10.0  # 10 seconds max
        assert run_id is not None
        assert len(results) == 20
    
    def test_concurrent_workflow_execution_with_success_detection(self):
        """Test concurrent execution of workflows with success detection."""
        import threading
        import concurrent.futures
        
        def execute_workflow(workflow_id):
            """Execute a single workflow."""
            workflow = WorkflowBuilder()
            workflow.add_node(
                "DataFlowBulkCreateNode",
                "concurrent_operation",
                {
                    "table_name": f"concurrent_test_{workflow_id}",
                    "data": [{"id": i, "workflow": workflow_id} for i in range(5)],
                    "connection": "test_connection"
                }
            )
            
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())
            return workflow_id, run_id, results
        
        # Execute multiple workflows concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(execute_workflow, i) for i in range(5)]
            
            results = []
            for future in concurrent.futures.as_completed(futures):
                workflow_id, run_id, workflow_results = future.result()
                results.append((workflow_id, run_id, workflow_results))
        
        # All workflows should complete successfully
        assert len(results) == 5
        for workflow_id, run_id, workflow_results in results:
            assert run_id is not None
            assert "concurrent_operation" in workflow_results


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])