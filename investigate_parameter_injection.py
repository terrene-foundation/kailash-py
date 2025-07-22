#!/usr/bin/env python3
"""
Investigation of parameter injection edge cases in LocalRuntime.

This script investigates potential conditions where runtime parameters
might not be injected as expected, based on the code analysis.
"""

import logging
import sys
from typing import Any, Dict

# Add src to Python path
sys.path.insert(0, "src")

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code.python import PythonCodeNode


def setup_debug_logging():
    """Setup detailed debug logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def test_edge_case_1_empty_parameters():
    """Test edge case: Empty parameters dict."""
    print("\n=== Edge Case 1: Empty Parameters ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'result': f'processed: {input_value}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    
    # Test with empty dict
    try:
        results, run_id = runtime.execute(workflow.build(), parameters={})
        print(f"Empty dict results: {results}")
    except Exception as e:
        print(f"Empty dict error: {e}")
    
    # Test with None
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=None)
        print(f"None parameters results: {results}")
    except Exception as e:
        print(f"None parameters error: {e}")


def test_edge_case_2_workflow_context_extraction():
    """Test edge case: workflow_context parameter extraction."""
    print("\n=== Edge Case 2: Workflow Context Extraction ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'result': f'processed: {input_value}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    
    # Test with workflow_context in parameters - this gets extracted and may affect processing
    parameters = {
        "workflow_context": {"session_id": "test_session"},
        "input_value": "test_data"
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"Workflow context results: {results}")
    except Exception as e:
        print(f"Workflow context error: {e}")


def test_edge_case_3_parameter_format_separation():
    """Test edge case: Parameter format separation logic."""
    print("\n=== Edge Case 3: Parameter Format Separation ===")
    
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(
        lambda input_value: {"result": f"processed: {input_value}"},
        name="processor"
    )
    workflow.add_node_instance("processor", node)
    
    runtime = LocalRuntime(debug=True)
    
    # Test mixed format that might confuse the separation logic
    parameters = {
        "processor": {"input_value": "node_specific_value"},  # Node-specific
        "input_value": "workflow_level_value",  # Workflow-level - same param name
        "some_other_param": "other_value"  # Workflow-level
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"Mixed format results: {results}")
        print(f"Should show node_specific_value (node-specific takes precedence)")
    except Exception as e:
        print(f"Mixed format error: {e}")


def test_edge_case_4_connection_validation_modes():
    """Test edge case: Different connection validation modes affecting parameter injection."""
    print("\n=== Edge Case 4: Connection Validation Modes ===")
    
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(
        lambda input_value: {"result": f"processed: {input_value}"},
        name="processor"
    )
    workflow.add_node_instance("processor", node)
    
    parameters = {"input_value": "test_data"}
    
    # Test with different validation modes
    for mode in ["off", "warn", "strict"]:
        print(f"\n--- Testing with connection_validation='{mode}' ---")
        runtime = LocalRuntime(debug=True, connection_validation=mode)
        
        try:
            results, run_id = runtime.execute(workflow.build(), parameters=parameters)
            print(f"Mode {mode} results: {results}")
        except Exception as e:
            print(f"Mode {mode} error: {e}")


def test_edge_case_5_workflow_parameter_injector_failure():
    """Test edge case: WorkflowParameterInjector failures."""
    print("\n=== Edge Case 5: WorkflowParameterInjector Failure Scenarios ===")
    
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(
        lambda input_value: {"result": f"processed: {input_value}"},
        name="processor"
    )
    workflow.add_node_instance("processor", node)
    
    runtime = LocalRuntime(debug=True)
    
    # Test with parameters that should trigger injector logic but might fail
    parameters = {
        "input_value": "test_data",
        "very_long_parameter_name_that_might_cause_issues": "value",
        123: "invalid_key_type",  # Invalid key type
        "nested": {"deeply": {"nested": {"value": "test"}}},  # Deep nesting
        "": "empty_key",  # Empty key
        None: "none_key",  # None key
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"Complex parameters results: {results}")
    except Exception as e:
        print(f"Complex parameters error: {e}")


def test_edge_case_6_node_not_in_workflow():
    """Test edge case: Node ID not found in workflow."""
    print("\n=== Edge Case 6: Node ID Not in Workflow ===")
    
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(
        lambda input_value: {"result": f"processed: {input_value}"},
        name="processor"
    )
    workflow.add_node_instance("processor", node)
    
    runtime = LocalRuntime(debug=True)
    
    # Parameters for non-existent node
    parameters = {
        "non_existent_node": {"param": "value"},
        "processor": {"input_value": "valid_data"}
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"Non-existent node results: {results}")
    except Exception as e:
        print(f"Non-existent node error: {e}")


def test_edge_case_7_secret_provider_interactions():
    """Test edge case: Secret provider affecting parameter processing."""
    print("\n=== Edge Case 7: Secret Provider Interactions ===")
    
    from kailash.runtime.secret_provider import EnvironmentSecretProvider
    
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(
        lambda input_value, secret_param=None: {"result": f"processed: {input_value}, secret: {secret_param}"},
        name="processor"
    )
    workflow.add_node_instance("processor", node)
    
    # Mock secret provider
    secret_provider = EnvironmentSecretProvider()
    runtime = LocalRuntime(debug=True, secret_provider=secret_provider)
    
    parameters = {"input_value": "test_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"Secret provider results: {results}")
    except Exception as e:
        print(f"Secret provider error: {e}")


def test_edge_case_8_cyclic_workflow_parameters():
    """Test edge case: Cyclic workflows and parameter handling."""
    print("\n=== Edge Case 8: Cyclic Workflow Parameter Handling ===")
    
    workflow = WorkflowBuilder()
    
    # Create nodes for potential cycle
    node1 = PythonCodeNode.from_function(
        lambda input_value: {"output": f"step1: {input_value}"},
        name="step1"
    )
    node2 = PythonCodeNode.from_function(
        lambda input_from_step1: {"output": f"step2: {input_from_step1}"},
        name="step2"
    )
    
    workflow.add_node_instance("step1", node1)
    workflow.add_node_instance("step2", node2)
    workflow.add_connection("step1", "output", "step2", "input_from_step1")
    
    runtime = LocalRuntime(debug=True, enable_cycles=True)
    parameters = {"input_value": "initial_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"Cyclic workflow results: {results}")
    except Exception as e:
        print(f"Cyclic workflow error: {e}")


def test_edge_case_9_async_vs_sync_execution():
    """Test edge case: Async vs sync execution affecting parameters."""
    print("\n=== Edge Case 9: Async vs Sync Execution ===")
    
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(
        lambda input_value: {"result": f"processed: {input_value}"},
        name="processor"
    )
    workflow.add_node_instance("processor", node)
    
    parameters = {"input_value": "test_data"}
    
    # Test with async enabled/disabled
    for enable_async in [True, False]:
        print(f"\n--- Testing with enable_async={enable_async} ---")
        runtime = LocalRuntime(debug=True, enable_async=enable_async)
        
        try:
            results, run_id = runtime.execute(workflow.build(), parameters=parameters)
            print(f"Async={enable_async} results: {results}")
        except Exception as e:
            print(f"Async={enable_async} error: {e}")


def test_edge_case_10_parameter_override_precedence():
    """Test edge case: Parameter override precedence logic."""
    print("\n=== Edge Case 10: Parameter Override Precedence ===")
    
    workflow = WorkflowBuilder()
    
    # Node with default config
    node = PythonCodeNode.from_function(
        lambda input_value="default_from_function": {"result": f"processed: {input_value}"},
        name="processor"
    )
    node.config["input_value"] = "default_from_config"
    workflow.add_node_instance("processor", node)
    
    runtime = LocalRuntime(debug=True)
    
    # Test different parameter sources
    test_cases = [
        # Node-specific parameters (should override config)
        {"processor": {"input_value": "from_node_specific_params"}},
        # Workflow-level parameters (should be injected)
        {"input_value": "from_workflow_level_params"},
        # Mixed parameters (node-specific should win)
        {
            "processor": {"input_value": "from_node_specific"},
            "input_value": "from_workflow_level"
        }
    ]
    
    for i, params in enumerate(test_cases):
        print(f"\n--- Test case {i+1}: {params} ---")
        try:
            results, run_id = runtime.execute(workflow.build(), parameters=params)
            print(f"Results: {results}")
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Run all edge case investigations."""
    print("Investigating LocalRuntime Parameter Injection Edge Cases")
    print("=" * 60)
    
    setup_debug_logging()
    
    # Run all edge case tests
    test_edge_case_1_empty_parameters()
    test_edge_case_2_workflow_context_extraction()
    test_edge_case_3_parameter_format_separation()
    test_edge_case_4_connection_validation_modes()
    test_edge_case_5_workflow_parameter_injector_failure()
    test_edge_case_6_node_not_in_workflow()
    test_edge_case_7_secret_provider_interactions()
    test_edge_case_8_cyclic_workflow_parameters()
    test_edge_case_9_async_vs_sync_execution()
    test_edge_case_10_parameter_override_precedence()
    
    print("\n" + "=" * 60)
    print("Investigation complete. Check the debug logs above for detailed parameter flow.")


if __name__ == "__main__":
    main()