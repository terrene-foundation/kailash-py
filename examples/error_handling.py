#!/usr/bin/env python3
"""
Error Handling Example

This example demonstrates comprehensive error handling in Kailash:
1. Node-level error handling
2. Workflow-level error handling  
3. Custom exception types
4. Error recovery strategies
5. Logging and debugging
6. Graceful degradation

Shows how to build resilient workflows that handle failures gracefully.
"""

import sys
import time
import random
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime

# Add the parent directory to the path to import kailash
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kailash.nodes.base import Node, NodeParameter, NodeMetadata
from kailash.nodes.code.python import PythonCodeNode
from kailash.sdk_exceptions import (
    NodeValidationError,
    NodeExecutionError,
    NodeConfigurationError,
    WorkflowValidationError,
    WorkflowExecutionError
)
from kailash.workflow.graph import Workflow
from kailash.runtime.local import LocalRuntime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_unreliable_data_source():
    """Create a node that simulates an unreliable data source."""
    def fetch_data(failure_rate: float = 0.3) -> Dict[str, Any]:
        """Fetch data with possible failures."""
        # Simulate random failures
        if random.random() < failure_rate:
            failure_types = ["network", "auth", "data", "timeout"]
            failure_type = random.choice(failure_types)
            
            if failure_type == "network":
                raise NodeExecutionError("Connection refused to data source")
            elif failure_type == "auth":
                raise NodeExecutionError("Invalid authentication credentials")
            elif failure_type == "data":
                raise NodeExecutionError("Corrupted data received")
            elif failure_type == "timeout":
                time.sleep(1)  # Simulate delay
                raise NodeExecutionError("Operation timed out")
        
        # Simulate successful data retrieval
        return {
            "data": [{"id": i, "value": random.random()} for i in range(10)],
            "timestamp": datetime.now().isoformat(),
            "status": "success"
        }
    
    input_schema = {
        'failure_rate': NodeParameter(
            name='failure_rate',
            type=float,
            required=False,
            default=0.3,
            description='Probability of failure (0-1)'
        )
    }
    
    output_schema = {
        'data': NodeParameter(
            name='data',
            type=list,
            required=True,
            description='Fetched data records'
        ),
        'timestamp': NodeParameter(
            name='timestamp',
            type=str,
            required=True,
            description='Fetch timestamp'
        ),
        'status': NodeParameter(
            name='status',
            type=str,
            required=True,
            description='Fetch status'
        )
    }
    
    return PythonCodeNode.from_function(
        func=fetch_data,
        name="unreliable_data_source",
        description="Simulates an unreliable data source",
        input_schema=input_schema,
        output_schema=output_schema
    )


def create_data_validator_with_recovery():
    """Create a node that validates data and attempts recovery."""
    def validate_and_recover(data: list, strict_mode: bool = False) -> Dict[str, Any]:
        """Validate data with recovery strategies."""
        errors = []
        warnings = []
        recovered_items = 0
        valid_data = []
        
        # Validate each item
        for item in data:
            try:
                # Check required fields
                if "id" not in item:
                    raise NodeValidationError("Missing required field: id")
                if "value" not in item:
                    raise NodeValidationError("Missing required field: value")
                
                # Check value range
                value = item.get("value")
                if value is not None:
                    if not 0 <= value <= 1:
                        raise NodeValidationError(f"Value {value} out of range [0, 1]")
                
                valid_data.append(item)
                
            except NodeValidationError as e:
                if strict_mode:
                    errors.append(str(e))
                else:
                    # Attempt recovery
                    recovered_item = item.copy()
                    
                    # Fill missing fields
                    if "id" not in recovered_item:
                        recovered_item["id"] = f"generated_{random.randint(1000, 9999)}"
                    if "value" not in recovered_item:
                        recovered_item["value"] = 0.5  # Default value
                    
                    # Fix out of range values
                    if "value" in recovered_item:
                        recovered_item["value"] = max(0, min(1, recovered_item["value"]))
                    
                    valid_data.append(recovered_item)
                    recovered_items += 1
                    warnings.append(f"Recovered item {recovered_item.get('id')}: {e}")
        
        # Check overall data quality
        if not valid_data and errors:
            raise NodeExecutionError(f"Data validation failed: {'; '.join(errors)}")
        
        return {
            "data": valid_data,
            "validation_summary": {
                "total_items": len(data),
                "valid_items": len(valid_data),
                "recovered_items": recovered_items,
                "errors": errors,
                "warnings": warnings
            }
        }
    
    input_schema = {
        'data': NodeParameter(
            name='data',
            type=list,
            required=True,
            description='Data to validate'
        ),
        'strict_mode': NodeParameter(
            name='strict_mode',
            type=bool,
            required=False,
            default=False,
            description='Whether to fail on validation errors'
        )
    }
    
    output_schema = {
        'data': NodeParameter(
            name='data',
            type=list,
            required=True,
            description='Validated data'
        ),
        'validation_summary': NodeParameter(
            name='validation_summary',
            type=dict,
            required=True,
            description='Validation summary report'
        )
    }
    
    return PythonCodeNode.from_function(
        func=validate_and_recover,
        name="data_validator",
        description="Validates data with recovery strategies",
        input_schema=input_schema,
        output_schema=output_schema
    )


def create_circuit_breaker():
    """Create a node implementing circuit breaker pattern."""
    # This will use a simple in-memory state
    state = {"status": "closed", "failure_count": 0, "last_failure": None}
    
    def circuit_breaker_operation(data: Any, failure_threshold: int = 3) -> Dict[str, Any]:
        """Execute with circuit breaker protection."""
        # Check circuit breaker state
        if state["status"] == "open":
            # Check if enough time has passed to try again
            if state["last_failure"]:
                time_since_failure = (datetime.now() - state["last_failure"]).seconds
                if time_since_failure < 30:  # 30 second timeout
                    raise NodeExecutionError(f"Circuit breaker is OPEN")
                else:
                    state["status"] = "half_open"
                    logger.info("Circuit breaker: Attempting reset (half-open)")
        
        try:
            # Simulate operation that might fail
            if random.random() < 0.2:  # 20% failure rate
                raise NodeExecutionError("Protected operation failed")
            
            # On success, reset failure count
            if state["status"] == "half_open":
                state["status"] = "closed"
                logger.info("Circuit breaker: CLOSED (recovered)")
            state["failure_count"] = 0
            
            return {
                "status": "success",
                "data": data,
                "circuit_state": state["status"]
            }
            
        except Exception as e:
            # On failure, increment count
            state["failure_count"] += 1
            state["last_failure"] = datetime.now()
            
            if state["failure_count"] >= failure_threshold:
                state["status"] = "open"
                logger.warning(f"Circuit breaker: OPEN (threshold reached)")
            
            raise
    
    input_schema = {
        'data': NodeParameter(
            name='data',
            type=Any,
            required=True,
            description='Input data'
        ),
        'failure_threshold': NodeParameter(
            name='failure_threshold',
            type=int,
            required=False,
            default=3,
            description='Number of failures before opening circuit'
        )
    }
    
    output_schema = {
        'status': NodeParameter(
            name='status',
            type=str,
            required=True,
            description='Operation status'
        ),
        'data': NodeParameter(
            name='data',
            type=Any,
            required=True,
            description='Processed data'
        ),
        'circuit_state': NodeParameter(
            name='circuit_state',
            type=str,
            required=True,
            description='Circuit breaker state'
        )
    }
    
    return PythonCodeNode.from_function(
        func=circuit_breaker_operation,
        name="circuit_breaker",
        description="Circuit breaker pattern implementation",
        input_schema=input_schema,
        output_schema=output_schema
    )


def create_error_aggregator():
    """Create a node that aggregates and reports errors."""
    def aggregate_errors(validation_summary: dict) -> Dict[str, Any]:
        """Aggregate errors from various sources."""
        # Extract errors and warnings
        errors = validation_summary.get("errors", [])
        warnings = validation_summary.get("warnings", [])
        
        # Categorize errors
        error_categories = {
            "critical": [],
            "warning": [],
            "info": []
        }
        
        for error in errors:
            if "Missing required" in error:
                error_categories["critical"].append(error)
            else:
                error_categories["warning"].append(error)
        
        for warning in warnings:
            error_categories["info"].append(warning)
        
        # Generate report
        report = {
            "summary": {
                "total_errors": len(errors),
                "total_warnings": len(warnings),
                "by_category": {
                    cat: len(items) for cat, items in error_categories.items()
                }
            },
            "details": error_categories,
            "timestamp": datetime.now().isoformat()
        }
        
        # Determine workflow status
        if error_categories["critical"]:
            workflow_status = "failed"
        elif error_categories["warning"]:
            workflow_status = "degraded"
        else:
            workflow_status = "healthy"
        
        # Recommend actions
        recommended_actions = []
        if errors:
            recommended_actions.append("Review and fix data quality issues")
        if warnings:
            recommended_actions.append("Monitor data recovery patterns")
        
        return {
            "error_report": report,
            "workflow_status": workflow_status,
            "recommended_actions": recommended_actions
        }
    
    input_schema = {
        'validation_summary': NodeParameter(
            name='validation_summary',
            type=dict,
            required=True,
            description='Validation summary from validator'
        )
    }
    
    output_schema = {
        'error_report': NodeParameter(
            name='error_report',
            type=dict,
            required=True,
            description='Aggregated error report'
        ),
        'workflow_status': NodeParameter(
            name='workflow_status',
            type=str,
            required=True,
            description='Overall workflow status'
        ),
        'recommended_actions': NodeParameter(
            name='recommended_actions',
            type=list,
            required=True,
            description='Recommended actions'
        )
    }
    
    return PythonCodeNode.from_function(
        func=aggregate_errors,
        name="error_aggregator",
        description="Aggregates and analyzes errors",
        input_schema=input_schema,
        output_schema=output_schema
    )


def create_error_handling_workflow():
    """Create a workflow demonstrating error handling patterns."""
    
    print("Creating error handling workflow...")
    
    # Create workflow
    workflow = Workflow(
        name="error_handling_demo",
        description="Demonstrates error handling patterns"
    )
    
    # Create nodes
    unreliable_source = create_unreliable_data_source()
    validator = create_data_validator_with_recovery()
    circuit_breaker = create_circuit_breaker()
    error_aggregator = create_error_aggregator()
    
    # Add nodes to workflow
    workflow.add_node(node_id='source', node_or_type=unreliable_source, config={
        'failure_rate': 0.4  # 40% failure rate for demo
    })
    
    workflow.add_node(node_id='validator', node_or_type=validator, config={
        'strict_mode': False  # Enable recovery
    })
    
    workflow.add_node(node_id='circuit', node_or_type=circuit_breaker, config={
        'failure_threshold': 3
    })
    
    workflow.add_node(node_id='aggregator', node_or_type=error_aggregator)
    
    # Connect nodes
    workflow.connect('source', 'validator', {'data': 'data'})
    workflow.connect('validator', 'circuit', {'data': 'data'})
    workflow.connect('validator', 'aggregator', {'validation_summary': 'validation_summary'})
    
    return workflow


def demonstrate_error_handling():
    """Demonstrate various error handling scenarios."""
    
    print("\n=== Error Handling Demonstration ===")
    
    workflow = create_error_handling_workflow()
    runner = LocalRuntime()
    
    # Run multiple iterations to show different error scenarios
    for i in range(5):
        print(f"\n--- Iteration {i + 1} ---")
        
        try:
            results, run_id = runner.execute(workflow)
            
            print(f"Execution completed successfully")
            print(f"Run ID: {run_id}")
            
            # Show results
            for node_id, output in results.items():
                if node_id == 'aggregator':
                    report = output['error_report']
                    print(f"\nError Report:")
                    print(f"  Total errors: {report['summary']['total_errors']}")
                    print(f"  Total warnings: {report['summary']['total_warnings']}")
                    print(f"  Workflow status: {output['workflow_status']}")
                    
                    if output['recommended_actions']:
                        print("  Recommended actions:")
                        for action in output['recommended_actions']:
                            print(f"    - {action}")
                elif node_id == 'circuit':
                    print(f"Circuit breaker state: {output.get('circuit_state', 'unknown')}")
            
        except Exception as e:
            print(f"Workflow failed: {e}")
            print(f"Error type: {type(e).__name__}")
        
        time.sleep(1)  # Wait between iterations


def demonstrate_node_retry():
    """Demonstrate node-level retry mechanisms."""
    
    print("\n=== Node Retry Demonstration ===")
    
    # Create a node with retry logic
    retry_count = {"count": 0}
    
    def flaky_operation() -> Dict[str, Any]:
        """Operation that fails a few times before succeeding."""
        retry_count["count"] += 1
        
        # Fail the first 2 attempts
        if retry_count["count"] < 3:
            raise NodeExecutionError(f"Attempt {retry_count['count']} failed")
        
        return {
            "status": "success",
            "attempts": retry_count["count"],
            "data": {"message": "Finally succeeded!"}
        }
    
    flaky_node = PythonCodeNode.from_function(
        func=flaky_operation,
        name="flaky_node",
        description="Node that fails before succeeding"
    )
    
    # Create a simple workflow
    workflow = Workflow(name="retry_demo")
    workflow.add_node(node_id='flaky', node_or_type=flaky_node)
    
    runner = LocalRuntime()
    
    # Run with custom retry logic
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"\nAttempt {attempt + 1}/{max_retries}")
            results, run_id = runner.execute(workflow)
            
            print(f"Success! Results: {results['flaky']}")
            break
            
        except Exception as e:
            print(f"Failed: {e}")
            if attempt < max_retries - 1:
                print("Retrying...")
                time.sleep(1)
            else:
                print("Max retries exceeded")


def main():
    """Main entry point for error handling examples."""
    
    print("=== Kailash Error Handling Examples ===\n")
    
    examples = [
        ("Error Handling Workflow", demonstrate_error_handling),
        ("Node Retry Mechanisms", demonstrate_node_retry)
    ]
    
    for name, example_func in examples:
        print(f"\n{'='*50}")
        print(f"Running: {name}")
        print('='*50)
        
        try:
            example_func()
        except Exception as e:
            print(f"Example failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n=== All examples completed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())