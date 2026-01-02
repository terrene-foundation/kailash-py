"""Test suite for PythonCodeNode variable isolation across executions.

This test suite validates the critical P0 bug fix for variable persistence
across PythonCodeNode executions. Variables from one execution must NOT be
accessible in subsequent executions.

Bug Report: Variable persistence causes data leakage between workflow executions,
particularly severe in Nexus deployments where the same workflow instance serves
multiple concurrent API requests.
"""

import pytest
from kailash.nodes.code.python import CodeExecutor, PythonCodeNode


class TestPythonCodeVariableIsolation:
    """Test variable isolation across PythonCodeNode executions."""

    def test_variable_persistence_bug_reproduction(self):
        """CRITICAL: Reproduce the variable persistence bug.

        This test reproduces the exact scenario from the bug report where
        variables from one execution persist into the next execution.
        """
        node = PythonCodeNode(
            name="test_isolation",
            code="""
try:
    val = optional_param
except NameError:
    val = "NOT_SET"

result = {'value': val}
""",
        )

        # Execution 1: WITH parameter
        result1 = node.run(optional_param="FIRST")
        assert (
            result1["result"]["value"] == "FIRST"
        ), f"First execution failed: {result1}"

        # Execution 2: WITHOUT parameter - must get "NOT_SET"
        result2 = node.run()

        # THIS IS THE BUG: If this fails, variables are persisting
        assert result2["result"]["value"] == "NOT_SET", (
            f"CRITICAL BUG: Variable persisted from previous execution! "
            f"Expected 'NOT_SET', got '{result2['result']['value']}'. "
            f"This means data from execution 1 leaked into execution 2."
        )

    def test_nexus_multi_request_scenario(self):
        """Test the exact Nexus scenario: multiple requests with optional parameters.

        This simulates the production bug where User A's search filter leaks
        into User B's request.
        """
        # Simulate Nexus workflow registration (single node instance)
        search_node = PythonCodeNode(
            name="prepare_search",
            code="""
# Check if search_text was provided
try:
    st = search_text
except NameError:
    st = None

# Build search filter
filter_str = ""
if st:
    filter_str = f"name ILIKE '%{st}%'"

result = {
    'filter': filter_str,
    'has_filter': bool(filter_str)
}
""",
        )

        # Request 1: User A searches for "technology"
        result1 = search_node.run(search_text="technology")
        assert result1["result"]["filter"] == "name ILIKE '%technology%'"
        assert result1["result"]["has_filter"] is True

        # Request 2: User B searches with NO filter
        result2 = search_node.run()

        # BUG CHECK: User B should NOT see User A's filter
        assert result2["result"]["filter"] == "", (
            f"DATA LEAKAGE: User B's request contains User A's search filter! "
            f"Expected empty string, got '{result2['result']['filter']}'"
        )
        assert result2["result"]["has_filter"] is False

    def test_multiple_variable_persistence(self):
        """Test that multiple variables don't persist across executions."""
        node = PythonCodeNode(
            name="multi_var",
            code="""
# These variables should NOT persist between executions
# Use try/except pattern to detect undefined variables
try:
    counter = counter + 1
except NameError:
    counter = 1

try:
    temp = temp * 2
except NameError:
    temp = 10

try:
    flag = not flag
except NameError:
    flag = True

result = {
    'counter': counter,
    'temp': temp,
    'flag': flag
}
""",
        )

        # Execution 1
        result1 = node.run()
        assert result1["result"]["counter"] == 1
        assert result1["result"]["temp"] == 10
        assert result1["result"]["flag"] is True

        # Execution 2 - all variables should reset
        result2 = node.run()
        assert result2["result"]["counter"] == 1, "counter persisted!"
        assert result2["result"]["temp"] == 10, "temp persisted!"
        assert result2["result"]["flag"] is True, "flag persisted!"

    def test_code_executor_direct_isolation(self):
        """Test CodeExecutor directly to isolate the root cause."""
        executor = CodeExecutor()

        # First execution sets a variable
        code1 = "secret = 'password123'; result = secret"
        result1 = executor.execute_code(code1, {})
        assert result1["result"] == "password123"

        # Second execution should NOT see 'secret'
        code2 = """
try:
    leaked = secret
except NameError:
    leaked = "ISOLATED"
result = leaked
"""
        result2 = executor.execute_code(code2, {})
        assert result2["result"] == "ISOLATED", (
            f"CRITICAL: Variable 'secret' leaked between executions! "
            f"Got: {result2['result']}"
        )

    def test_input_parameters_dont_persist(self):
        """Test that input parameters from one execution don't persist."""
        node = PythonCodeNode(
            name="test_inputs",
            code="""
# user_id should only exist if passed as input
try:
    uid = user_id
except NameError:
    uid = "ANONYMOUS"

result = {'user_id': uid}
""",
        )

        # Execution 1: WITH user_id
        result1 = node.run(user_id="user123")
        assert result1["result"]["user_id"] == "user123"

        # Execution 2: WITHOUT user_id
        result2 = node.run()
        assert (
            result2["result"]["user_id"] == "ANONYMOUS"
        ), "Input parameter 'user_id' persisted from previous execution!"

    def test_complex_data_structure_isolation(self):
        """Test that complex data structures don't leak between executions."""
        node = PythonCodeNode(
            name="complex_data",
            code="""
# Build a list from optional items
items = []

try:
    items.append(item1)
except NameError:
    pass

try:
    items.append(item2)
except NameError:
    pass

result = {'items': items, 'count': len(items)}
""",
        )

        # Execution 1: Two items
        result1 = node.run(item1="apple", item2="banana")
        assert result1["result"]["items"] == ["apple", "banana"]
        assert result1["result"]["count"] == 2

        # Execution 2: One item
        result2 = node.run(item1="cherry")
        assert result2["result"]["items"] == [
            "cherry"
        ], f"Previous items persisted! Expected ['cherry'], got {result2['result']['items']}"
        assert result2["result"]["count"] == 1

        # Execution 3: No items
        result3 = node.run()
        assert (
            result3["result"]["items"] == []
        ), f"Items from previous executions persisted! Got {result3['result']['items']}"
        assert result3["result"]["count"] == 0


class TestPythonCodeVariableIsolationRegression:
    """Regression tests to ensure the fix doesn't break existing functionality."""

    def test_imports_still_work(self):
        """Test that imports in the code still work correctly."""
        node = PythonCodeNode(
            name="test_imports",
            code="""
import math
result = math.sqrt(16)
""",
        )

        result = node.run()
        assert result["result"] == 4.0

    def test_from_imports_still_work(self):
        """Test that from imports still work correctly."""
        node = PythonCodeNode(
            name="test_from_imports",
            code="""
from datetime import datetime
result = datetime.now().year >= 2024
""",
        )

        result = node.run()
        assert result["result"] is True

    def test_allowed_modules_still_accessible(self):
        """Test that pre-loaded allowed modules are still accessible."""
        node = PythonCodeNode(
            name="test_modules",
            code="""
# Test multiple allowed modules
import random
import math

result = {
    'has_random': hasattr(random, 'randint'),
    'has_math': hasattr(math, 'pi'),
    'pi_value': math.pi
}
""",
        )

        result = node.run()
        assert result["result"]["has_random"] is True
        assert result["result"]["has_math"] is True
        assert abs(result["result"]["pi_value"] - 3.14159) < 0.001

    def test_input_parameters_work_correctly(self):
        """Test that input parameters are correctly passed to the code."""
        node = PythonCodeNode(
            name="test_inputs",
            code="""
result = {
    'doubled': value * 2,
    'message': f"Hello, {name}!"
}
""",
        )

        result = node.run(value=21, name="World")
        assert result["result"]["doubled"] == 42
        assert result["result"]["message"] == "Hello, World!"

    def test_multiple_executions_with_different_inputs(self):
        """Test that multiple executions with different inputs work correctly."""
        node = PythonCodeNode(
            name="test_multi",
            code="""
result = x + y
""",
        )

        result1 = node.run(x=10, y=5)
        assert result1["result"] == 15

        result2 = node.run(x=100, y=50)
        assert result2["result"] == 150

        result3 = node.run(x=-10, y=20)
        assert result3["result"] == 10

    def test_workflow_context_functions_still_work(self):
        """Test that workflow context functions remain accessible after fix."""
        node = PythonCodeNode(
            name="test_context",
            code="""
set_workflow_context('test_key', 'test_value')
retrieved = get_workflow_context('test_key')
result = retrieved
""",
        )

        result = node.run()
        assert result["result"] == "test_value"

    def test_exception_handling_still_works(self):
        """Test that exception handling in user code still works."""
        node = PythonCodeNode(
            name="test_exceptions",
            code="""
try:
    risky = 10 / divisor
except ZeroDivisionError:
    risky = "infinity"

result = risky
""",
        )

        result1 = node.run(divisor=2)
        assert result1["result"] == 5.0

        result2 = node.run(divisor=0)
        assert result2["result"] == "infinity"

    def test_return_value_filtering_still_works(self):
        """Test that private variables and inputs are still filtered from results."""
        node = PythonCodeNode(
            name="test_filtering",
            code="""
_private = "should not appear"
__double_private = "also hidden"
input_value = input_value  # Should be filtered
public_result = "this should appear"
result = public_result
""",
        )

        result = node.run(input_value="test")

        # Check that result contains what it should
        assert result["result"] == "this should appear"

        # Check that private variables don't appear in output
        # (The node should only return 'result', not all variables)
        assert "_private" not in result
        assert "__double_private" not in result
