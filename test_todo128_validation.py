#!/usr/bin/env python3
"""
TODO-128 Validation Suite
Tests for cycle convergence fixes.
"""

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


def test_deterministic_execution():
    """Test that cycles execute deterministically."""
    workflow = WorkflowBuilder()
    
    # Source
    workflow.add_node("PythonCodeNode", "source", {
        "code": "result = {'value': 10, 'iteration': 0}"
    })
    
    # Processor
    workflow.add_node("PythonCodeNode", "processor", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 3
result = {
    'value': value,
    'iteration': iteration,
    'deterministic_id': f'iter_{iteration}_val_{value}'
}
"""
    })
    
    # Condition
    workflow.add_node("SwitchNode", "condition", {
        "condition_field": "value",
        "operator": "<",
        "value": 25
    })
    
    # Final
    workflow.add_node("PythonCodeNode", "final", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
result = {'final_value': input_data.get('value', 0), 'final_iteration': input_data.get('iteration', 0)}
"""
    })
    
    # Connect
    workflow.add_connection("source", "result", "condition", "input_data")
    workflow.add_connection("condition", "true_output", "processor", "parameters")
    workflow.add_connection("condition", "false_output", "final", "parameters")
    
    # Create cycle
    built_workflow = workflow.build()
    cycle = built_workflow.create_cycle("deterministic_test")
    cycle.connect("processor", "condition", mapping={"result": "input_data"})
    cycle.max_iterations(8)
    cycle.build()
    
    # Run twice
    runtime = LocalRuntime()
    result1, _ = runtime.execute(built_workflow)
    result2, _ = runtime.execute(built_workflow)
    
    # Check determinism
    final1 = result1["final"]["result"]
    final2 = result2["final"]["result"]
    
    assert final1 == final2, f"Non-deterministic results: {final1} vs {final2}"
    assert final1["final_value"] == 25
    assert final1["final_iteration"] == 5
    
    return "✅ PASS: Deterministic execution - 25 at iteration 5"


def test_no_double_execution():
    """Test that nodes don't execute multiple times per iteration."""
    workflow = WorkflowBuilder()
    
    # Initial state
    workflow.add_node("PythonCodeNode", "init", {
        "code": "result = {'count': 0, 'execution_log': []}"
    })
    
    # Counter node - properly uses cycle parameters
    workflow.add_node("PythonCodeNode", "counter", {
        "code": """
# Get input from parameters (cycle-aware)
input_data = parameters if isinstance(parameters, dict) else {}
count = input_data.get('count', 0) + 1
execution_log = input_data.get('execution_log', []).copy()
execution_log.append(f'execution_{count}')

# Continue if count < 3
result = {
    'count': count, 
    'continue': count < 3,
    'execution_log': execution_log
}
"""
    })
    
    # Switch
    workflow.add_node("SwitchNode", "switch", {
        "condition_field": "continue",
        "operator": "==",
        "value": True
    })
    
    # Final
    workflow.add_node("PythonCodeNode", "final", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
result = {
    'final_count': input_data.get('count', 0),
    'execution_history': input_data.get('execution_log', [])
}
"""
    })
    
    # Connect
    workflow.add_connection("init", "result", "counter", "parameters")
    workflow.add_connection("counter", "result", "switch", "input_data")
    workflow.add_connection("switch", "false_output", "final", "parameters")
    
    # Create cycle
    built_workflow = workflow.build()
    cycle = built_workflow.create_cycle("count_test")
    cycle.connect("switch", "counter", mapping={"true_output": "parameters"})
    cycle.max_iterations(5)
    cycle.build()
    
    runtime = LocalRuntime()
    result, _ = runtime.execute(built_workflow)
    
    final_result = result["final"]["result"]
    final_count = final_result["final_count"]
    execution_history = final_result["execution_history"]
    
    # Verify exactly 3 executions
    assert final_count == 3, f"Expected 3 executions, got {final_count}"
    assert len(execution_history) == 3, f"Expected 3 execution logs, got {len(execution_history)}"
    assert execution_history == ['execution_1', 'execution_2', 'execution_3'], f"Unexpected execution history: {execution_history}"
    
    return "✅ PASS: No double execution - Final count: 3"


def test_natural_termination():
    """Test natural cycle termination based on conditions."""
    workflow = WorkflowBuilder()
    
    # Temperature sensor
    workflow.add_node("PythonCodeNode", "sensor", {
        "code": "result = {'temperature': 10, 'steps': 0}"
    })
    
    # Heater
    workflow.add_node("PythonCodeNode", "heater", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
temp = input_data.get('temperature', 0) + 10
steps = input_data.get('steps', 0) + 1
result = {'temperature': temp, 'steps': steps}
"""
    })
    
    # Thermostat
    workflow.add_node("SwitchNode", "thermostat", {
        "condition_field": "temperature",
        "operator": "<",
        "value": 40
    })
    
    # Done
    workflow.add_node("PythonCodeNode", "done", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
result = {'final_temp': input_data.get('temperature', 0), 'total_steps': input_data.get('steps', 0)}
"""
    })
    
    # Connect
    workflow.add_connection("sensor", "result", "thermostat", "input_data")
    workflow.add_connection("thermostat", "true_output", "heater", "parameters")
    workflow.add_connection("thermostat", "false_output", "done", "parameters")
    
    # Create cycle
    built_workflow = workflow.build()
    cycle = built_workflow.create_cycle("heating_cycle")
    cycle.connect("heater", "thermostat", mapping={"result": "input_data"})
    cycle.max_iterations(10)
    cycle.build()
    
    runtime = LocalRuntime()
    result, _ = runtime.execute(built_workflow)
    
    final = result["done"]["result"]
    assert final["final_temp"] == 40
    assert final["total_steps"] == 3
    
    return "✅ PASS: Natural termination - Final temp: 40, Steps: 3"


def test_hierarchical_switches():
    """Test hierarchical switch integration with cycles."""
    workflow = WorkflowBuilder()
    
    # Data source
    workflow.add_node("PythonCodeNode", "data_source", {
        "code": """
result = {
    'process_a': True,
    'process_b': False,
    'value_a': 10,
    'iteration': 0
}
"""
    })
    
    # Primary switch
    workflow.add_node("SwitchNode", "primary_switch", {
        "condition_field": "process_a",
        "operator": "==",
        "value": True
    })
    
    # Secondary switch
    workflow.add_node("SwitchNode", "secondary_switch", {
        "condition_field": "value_a",
        "operator": "<",
        "value": 50
    })
    
    # Processor A
    workflow.add_node("PythonCodeNode", "processor_a", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
value = input_data.get('value_a', 0) + 5
iteration = input_data.get('iteration', 0) + 1
result = {
    'process_a': True,
    'process_b': False,
    'value_a': value,
    'iteration': iteration
}
"""
    })
    
    # Merge results
    workflow.add_node("MergeNode", "merge", {
        "merge_type": "merge_dict",
        "skip_none": True
    })
    
    # Connect workflow
    workflow.add_connection("data_source", "result", "primary_switch", "input_data")
    workflow.add_connection("primary_switch", "true_output", "secondary_switch", "input_data")
    workflow.add_connection("secondary_switch", "true_output", "processor_a", "parameters")
    workflow.add_connection("data_source", "result", "merge", "data1")
    workflow.add_connection("primary_switch", "false_output", "merge", "data2")
    workflow.add_connection("secondary_switch", "false_output", "merge", "data3")
    
    # Create cycle
    built_workflow = workflow.build()
    cycle = built_workflow.create_cycle("process_a_cycle")
    cycle.connect("processor_a", "secondary_switch", mapping={"result": "input_data"})
    cycle.max_iterations(15)
    cycle.build()
    
    runtime = LocalRuntime()
    result, _ = runtime.execute(built_workflow)
    
    merged_data = result["merge"]["merged_data"]
    assert merged_data["value_a"] == 50
    assert merged_data["iteration"] == 8
    
    return "✅ PASS: Hierarchical switches - value_a: 50, iteration: 8"


def test_parameter_propagation():
    """Test correct parameter propagation between iterations."""
    workflow = WorkflowBuilder()
    
    # Initialize
    workflow.add_node("PythonCodeNode", "init", {
        "code": "result = {'accumulated': [], 'step': 0}"
    })
    
    # Accumulator
    workflow.add_node("PythonCodeNode", "accumulator", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
accumulated = input_data.get('accumulated', []).copy()
step = input_data.get('step', 0) + 1
accumulated.append(f'step_{step}')
result = {'accumulated': accumulated, 'step': step}
"""
    })
    
    # Check
    workflow.add_node("SwitchNode", "check", {
        "condition_field": "step",
        "operator": "<",
        "value": 3
    })
    
    # Final
    workflow.add_node("PythonCodeNode", "final", {
        "code": """
input_data = parameters if isinstance(parameters, dict) else {}
result = {'all_steps': input_data.get('accumulated', [])}
"""
    })
    
    # Connect
    workflow.add_connection("init", "result", "check", "input_data")
    workflow.add_connection("check", "true_output", "accumulator", "parameters")
    workflow.add_connection("check", "false_output", "final", "parameters")
    
    # Create cycle
    built_workflow = workflow.build()
    cycle = built_workflow.create_cycle("accumulate_cycle")
    cycle.connect("accumulator", "check", mapping={"result": "input_data"})
    cycle.max_iterations(5)
    cycle.build()
    
    runtime = LocalRuntime()
    result, _ = runtime.execute(built_workflow)
    
    all_steps = result["final"]["result"]["all_steps"]
    assert all_steps == ['step_1', 'step_2', 'step_3']
    
    return "✅ PASS: Parameter propagation - Accumulated: ['step_1', 'step_2', 'step_3']"


def main():
    """Run all validation tests."""
    print("🔍 TODO-128 VALIDATION TESTS")
    print("=" * 50)
    
    tests = [
        ("Deterministic Cycle Execution", test_deterministic_execution),
        ("No Double Execution", test_no_double_execution),
        ("Natural Cycle Termination", test_natural_termination),
        ("Hierarchical Switches Integration", test_hierarchical_switches),
        ("Parameter Propagation Correctness", test_parameter_propagation)
    ]
    
    for name, test_fn in tests:
        print(f"=== Testing {name} ===")
        try:
            result = test_fn()
            print(result)
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
    
    print("=" * 50)


if __name__ == "__main__":
    main()