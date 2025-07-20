"""
Integration tests for enhanced connection validation error messages.

Tests Task 1.4: Improved Error Messages in real workflow execution context
- Tests enhanced error messages in LocalRuntime with real workflows
- Tests connection path reconstruction in complex workflows
- Tests error categorization with real node validation failures
- Tests actionable guidance generation with real use cases
"""

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowValidationError, WorkflowExecutionError


class TestEnhancedConnectionValidationIntegration:
    """Integration tests for enhanced connection validation error messages."""

    def test_type_mismatch_error_enhancement(self):
        """Test enhanced error messages for type mismatches in real workflows."""
        workflow = WorkflowBuilder()
        
        # Create a workflow that passes an integer where a string is required
        workflow.add_node("PythonCodeNode", "source", {
            "code": "result = 123"  # Returns integer
        })
        workflow.add_node("CSVReaderNode", "reader", {})
        
        # This connection will cause a type mismatch - integer to file_path (string required)
        workflow.add_connection("source", "result", "reader", "file_path")
        
        runtime = LocalRuntime(connection_validation="strict")
        
        # Should get enhanced error message with connection path
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # Verify enhanced error message components
        assert "source.result → reader.file_path" in error_msg  # Connection path
        assert ("Type Mismatch" in error_msg or "type mismatch" in error_msg.lower())  # Categorization
        assert ("Suggestion:" in error_msg or "suggestion" in error_msg.lower())  # Actionable guidance
        assert ("Example:" in error_msg or "example" in error_msg.lower())  # Code example
        
    def test_missing_parameter_error_enhancement(self):
        """Test enhanced error messages for missing required parameters."""
        workflow = WorkflowBuilder()
        
        # Create a workflow with missing required parameter  
        workflow.add_node("PythonCodeNode", "source", {
            "code": "result = {'data': [1, 2, 3]}"
        })
        workflow.add_node("CSVWriterNode", "writer", {
            # Missing required 'file_path' parameter - will be provided via connection
        })
        
        # Connect data but not the required file_path
        workflow.add_connection("source", "result.data", "writer", "data")
        # Missing connection for file_path parameter
        
        runtime = LocalRuntime(connection_validation="strict")
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # Verify enhanced error for missing parameter
        assert "writer" in error_msg  # Target node mentioned
        assert ("missing" in error_msg.lower() or "required" in error_msg.lower())  # Missing parameter category
        assert "file_path" in error_msg.lower()  # Specific parameter mentioned
        assert ("add_connection" in error_msg or "workflow.add_connection" in error_msg)  # Actionable guidance
        
    def test_security_violation_error_enhancement(self):
        """Test enhanced error messages for security violations."""
        workflow = WorkflowBuilder()
        
        # Create a workflow with potential SQL injection
        workflow.add_node("PythonCodeNode", "malicious_source", {
            "code": "result = {'query': \"'; DROP TABLE users; --\"}"  # Malicious SQL
        })
        workflow.add_node("PythonCodeNode", "sql_consumer", {
            "code": "result = f'SELECT * FROM table WHERE condition = {query}'"
        })
        
        # Connection that could enable SQL injection
        workflow.add_connection("malicious_source", "result.query", "sql_consumer", "query")
        
        runtime = LocalRuntime(connection_validation="strict")
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # Verify enhanced security error message
        assert "malicious_source.result.query → sql_consumer.query" in error_msg  # Connection path
        assert ("SECURITY" in error_msg or "security" in error_msg.lower())  # Security categorization
        assert ("SQL" in error_msg or "injection" in error_msg.lower())  # Specific security issue
        # Should NOT contain the actual malicious SQL in error message
        assert "DROP TABLE" not in error_msg
        assert ("SANITIZED" in error_msg or "REDACTED" in error_msg)  # Value sanitization
        
    def test_complex_workflow_connection_path_reconstruction(self):
        """Test connection path reconstruction in complex workflows."""
        workflow = WorkflowBuilder()
        
        # Create a complex workflow with multiple levels
        workflow.add_node("PythonCodeNode", "data_source", {
            "code": "result = {'users': [{'id': 1, 'name': 'test'}]}"
        })
        workflow.add_node("PythonCodeNode", "transformer", {
            "code": "result = {'processed_data': [item['name'] for item in users]}"
        })
        workflow.add_node("PythonCodeNode", "analyzer", {
            "code": "result = len(data)"  # Expects string/list, will get dict
        })
        
        # Multi-level connections
        workflow.add_connection("data_source", "result.users", "transformer", "users")
        workflow.add_connection("transformer", "result", "analyzer", "data")  # This will cause type error
        
        runtime = LocalRuntime(connection_validation="strict")
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # Should identify the specific failing connection in the chain
        assert "transformer.result → analyzer.data" in error_msg
        # Should provide context about the workflow structure
        assert "transformer" in error_msg
        assert "analyzer" in error_msg
        
    def test_dataflow_node_error_enhancement(self):
        """Test enhanced error messages with DataFlow nodes."""
        pytest.importorskip("dataflow", reason="DataFlow not available")
        
        from dataflow import DataFlow
        
        # Set up DataFlow with test model
        db = DataFlow()
        
        @db.model  
        class TestUser:
            name: str
            email: str
            
        workflow = WorkflowBuilder()
        
        # Create workflow with DataFlow integration
        workflow.add_node("PythonCodeNode", "source", {
            "code": "result = {'user_data': {'name': 123, 'email': 'test@example.com'}}"  # Wrong type for name
        })
        workflow.add_node("TestUserCreateNode", "create_user", {})
        
        # Connect with type mismatch
        workflow.add_connection("source", "result.user_data.name", "create_user", "name")
        workflow.add_connection("source", "result.user_data.email", "create_user", "email")
        
        runtime = LocalRuntime(connection_validation="strict")
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # DataFlow-specific enhanced error message
        assert "source.result.user_data.name → create_user.name" in error_msg
        assert ("DataFlow" in error_msg or "model" in error_msg.lower())  # DataFlow context
        assert ("type" in error_msg.lower() and "mismatch" in error_msg.lower())  # Type error
        
    def test_nested_parameter_connection_errors(self):
        """Test error messages for nested parameter connections."""
        workflow = WorkflowBuilder()
        
        # Source with nested data structure
        workflow.add_node("PythonCodeNode", "api_response", {
            "code": """result = {
                'response': {
                    'data': {
                        'users': [{'profile': {'name': 'John', 'age': '30'}}]  # age as string
                    }
                }
            }"""
        })
        
        # Consumer expecting different structure
        workflow.add_node("PythonCodeNode", "age_calculator", {
            "code": "result = age + 1"  # Expects integer age
        })
        
        # Deep nested connection that will fail
        workflow.add_connection(
            "api_response", 
            "result.response.data.users[0].profile.age", 
            "age_calculator", 
            "age"
        )
        
        runtime = LocalRuntime(connection_validation="strict")
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # Should show the complex nested connection path
        expected_path = "api_response.result.response.data.users[0].profile.age → age_calculator.age"
        assert expected_path in error_msg or "api_response" in error_msg and "age_calculator" in error_msg
        
    def test_validation_mode_affects_error_detail(self):
        """Test that validation mode affects error message detail level."""
        workflow = WorkflowBuilder()
        
        workflow.add_node("PythonCodeNode", "source", {
            "code": "result = 123"  # Wrong type
        })
        workflow.add_node("PythonCodeNode", "consumer", {
            "code": "result = len(data)"  # Expects iterable
        })
        workflow.add_connection("source", "result", "consumer", "data")
        
        # Test strict mode - should get full enhanced error
        strict_runtime = LocalRuntime(connection_validation="strict")
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as strict_exc:
            strict_runtime.execute(workflow.build())
            
        strict_error = str(strict_exc.value)
        
        # Strict mode should have enhanced details
        assert "source.result → consumer.data" in strict_error
        assert ("Suggestion:" in strict_error or "suggestion" in strict_error.lower())
        
        # Test warn mode - should log warning but continue
        warn_runtime = LocalRuntime(connection_validation="warn") 
        
        # In warn mode, should not raise exception but log warning
        # The execution might still fail but due to runtime error, not validation error
        try:
            warn_runtime.execute(workflow.build())
        except Exception as e:
            # Should be a runtime error, not validation error
            # Enhanced validation error should be in logs, not exception
            pass
            
    def test_multiple_connection_errors_reporting(self):
        """Test error reporting when multiple connections have issues."""
        workflow = WorkflowBuilder()
        
        workflow.add_node("PythonCodeNode", "source", {
            "code": "result = {'data1': 123, 'data2': 'text'}"
        })
        workflow.add_node("PythonCodeNode", "consumer1", {
            "code": "result = len(data)"  # Expects iterable, gets int
        })
        workflow.add_node("PythonCodeNode", "consumer2", {
            "code": "result = data + 5"  # Expects int, gets string 
        })
        
        # Both connections will fail validation
        workflow.add_connection("source", "result.data1", "consumer1", "data")  # int -> expects iterable
        workflow.add_connection("source", "result.data2", "consumer2", "data")  # string -> expects int
        
        runtime = LocalRuntime(connection_validation="strict")
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)) as exc_info:
            runtime.execute(workflow.build())
            
        error_msg = str(exc_info.value)
        
        # Should identify the first connection that fails
        # (May not show all failures at once, but should be clear about which one failed)
        assert ("consumer1" in error_msg or "consumer2" in error_msg)
        assert "source.result.data" in error_msg
        
    def test_error_message_performance_impact(self):
        """Test that enhanced error messages don't significantly impact performance."""
        import time
        
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "source", {
            "code": "result = 123"  # Will cause type error
        })
        workflow.add_node("PythonCodeNode", "consumer", {
            "code": "result = len(data)"  # Expects iterable
        })
        workflow.add_connection("source", "result", "consumer", "data")
        
        runtime = LocalRuntime(connection_validation="strict")
        
        # Measure time for error generation
        start_time = time.time()
        
        with pytest.raises((WorkflowValidationError, WorkflowExecutionError)):
            runtime.execute(workflow.build())
            
        end_time = time.time()
        error_time = end_time - start_time
        
        # Error message generation should add minimal overhead (<100ms for simple workflow)
        assert error_time < 0.1  # Less than 100ms total (including workflow execution)