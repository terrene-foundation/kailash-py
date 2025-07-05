#!/usr/bin/env python3
"""Test PythonCodeNode result handling."""

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create a simple workflow to test result handling
workflow = Workflow("test_result", "Test Result Handling")

# Test 1: Simple result assignment
test1 = PythonCodeNode(
    name="test1",
    code="""
# Test simple result assignment
result = {"message": "Hello", "value": 42}
""",
)
workflow.add_node("test1", test1)

# Test 2: Result with unwrapping
test2 = PythonCodeNode(
    name="test2",
    code="""
# Test unwrapping input - inputs are mapped to 'input_data'
try:
    # input_data should be available as a variable
    message = input_data.get("message", "No message")
    value = input_data.get("value", 0)
    print(f"Got input: {input_data}")
except NameError:
    message = "No input_data variable"
    value = 0
    print("No input_data variable found")

# Create output - NOW we can use 'result' since it's not an input
result = {
    "processed_message": f"Processed: {message}",
    "doubled_value": value * 2
}

print(f"Setting result to: {result}")
""",
)
workflow.add_node("test2", test2)
workflow.connect("test1", "test2", mapping={"result": "input_data"})

# Run the workflow
runtime = LocalRuntime()
try:
    results, run_id = runtime.execute(workflow)
    print("✅ Test passed!")
    print(f"Test 1 result: {results.get('test1')}")
    print(f"Test 2 result: {results.get('test2')}")
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback

    traceback.print_exc()
