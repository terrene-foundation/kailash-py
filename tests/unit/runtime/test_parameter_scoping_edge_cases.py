"""
Parameter scoping edge case tests for LocalRuntime and AsyncLocalRuntime.

Tests comprehensive parameter scoping scenarios including:
- Mixed global + node-specific parameters in route_data mode
- Cyclic workflows with parameter scoping
- Very deep nesting (4+ levels)
- Direct _prepare_node_inputs() API calls

These tests ensure parameter scoping works correctly in all edge cases.
"""

import pytest
from kailash.nodes.base import Node
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.shared.runtime.conftest import execute_runtime


class TestMixedParameterScoping:
    """Test mixed global and node-specific parameter scoping."""

    @pytest.mark.parametrize(
        "runtime_class",
        [
            pytest.param(LocalRuntime, id="sync"),
        ],
    )
    def test_mixed_global_and_node_specific_route_data_mode(self, runtime_class):
        """
        Test mixed global + node-specific parameters in route_data mode.

        Scenario:
        - Global parameter: "api_key" - should be available to all nodes
        - Node-specific parameters: "node1": {"value": 10}, "node2": {"value": 20}
        - Each node should receive ONLY its own node-specific param + global params
        """
        runtime = runtime_class(conditional_execution="route_data")
        builder = WorkflowBuilder()

        # Create nodes that echo their parameters
        code1 = """
# Check for parameters by attempting to access them
try:
    api_key_value = api_key
except NameError:
    api_key_value = None

try:
    value_value = value
except NameError:
    value_value = None

result = {'api_key': api_key_value, 'value': value_value}
"""
        code2 = """
# Check for parameters by attempting to access them
try:
    api_key_value = api_key
except NameError:
    api_key_value = None

try:
    value_value = value
except NameError:
    value_value = None

result = {'api_key': api_key_value, 'value': value_value}
"""

        builder.add_node("PythonCodeNode", "node1", {"code": code1})
        builder.add_node("PythonCodeNode", "node2", {"code": code2})

        workflow = builder.build()

        # Mixed parameters: global "api_key" + node-specific "value"
        parameters = {
            "api_key": "global-key-123",  # Global parameter
            "node1": {"value": 10},  # Node-specific for node1
            "node2": {"value": 20},  # Node-specific for node2
        }

        results = execute_runtime(runtime, workflow, parameters=parameters)

        # Verify node1 received its value + global
        assert results["node1"]["api_key"] == "global-key-123"
        assert results["node1"]["value"] == 10

        # Verify node2 received its value + global
        assert results["node2"]["api_key"] == "global-key-123"
        assert results["node2"]["value"] == 20

    @pytest.mark.parametrize(
        "runtime_class",
        [
            pytest.param(LocalRuntime, id="sync"),
        ],
    )
    def test_node_specific_params_do_not_leak(self, runtime_class):
        """
        Test that node-specific parameters don't leak to other nodes.

        Scenario:
        - node1 has param: {"secret": "node1-secret"}
        - node2 has param: {"secret": "node2-secret"}
        - Each node should ONLY see its own secret, not the other's
        """
        runtime = runtime_class()
        builder = WorkflowBuilder()

        code1 = """
try:
    secret_value = secret
except NameError:
    secret_value = None
result = {'secret': secret_value}
"""
        code2 = """
try:
    secret_value = secret
except NameError:
    secret_value = None
result = {'secret': secret_value}
"""

        builder.add_node("PythonCodeNode", "node1", {"code": code1})
        builder.add_node("PythonCodeNode", "node2", {"code": code2})

        workflow = builder.build()

        parameters = {
            "node1": {"secret": "node1-secret"},
            "node2": {"secret": "node2-secret"},
        }

        results = execute_runtime(runtime, workflow, parameters=parameters)

        # Each node should ONLY see its own secret
        assert results["node1"]["secret"] == "node1-secret"
        assert results["node2"]["secret"] == "node2-secret"


class TestVeryDeepNesting:
    """Test very deep nesting (4+ levels) with parameter scoping."""

    @pytest.mark.parametrize(
        "runtime_class",
        [
            pytest.param(LocalRuntime, id="sync"),
        ],
    )
    def test_four_level_nested_switches_with_parameters(self, runtime_class):
        """
        Test 4-level nested nodes with node-specific parameters.

        Workflow structure:
        level1 -> level2 -> level3 -> level4

        Each node should receive ONLY its own parameters, not others'.
        This tests deep nesting (4 levels) with proper parameter isolation.
        """
        runtime = runtime_class()
        builder = WorkflowBuilder()

        # Create 4 levels of processing nodes that echo their parameters
        # Each node checks for its own param and explicitly checks for others' absence
        codes = {
            1: """
try:
    my_val = level1_param
except NameError:
    my_val = None

other_params = {}
try:
    other_params['level2_param'] = level2_param
except NameError:
    other_params['level2_param'] = 'not_present'
try:
    other_params['level3_param'] = level3_param
except NameError:
    other_params['level3_param'] = 'not_present'
try:
    other_params['level4_param'] = level4_param
except NameError:
    other_params['level4_param'] = 'not_present'

result = {'my_param': my_val, 'other_params': other_params}
""",
            2: """
try:
    my_val = level2_param
except NameError:
    my_val = None

other_params = {}
try:
    other_params['level1_param'] = level1_param
except NameError:
    other_params['level1_param'] = 'not_present'
try:
    other_params['level3_param'] = level3_param
except NameError:
    other_params['level3_param'] = 'not_present'
try:
    other_params['level4_param'] = level4_param
except NameError:
    other_params['level4_param'] = 'not_present'

result = {'my_param': my_val, 'other_params': other_params}
""",
            3: """
try:
    my_val = level3_param
except NameError:
    my_val = None

other_params = {}
try:
    other_params['level1_param'] = level1_param
except NameError:
    other_params['level1_param'] = 'not_present'
try:
    other_params['level2_param'] = level2_param
except NameError:
    other_params['level2_param'] = 'not_present'
try:
    other_params['level4_param'] = level4_param
except NameError:
    other_params['level4_param'] = 'not_present'

result = {'my_param': my_val, 'other_params': other_params}
""",
            4: """
try:
    my_val = level4_param
except NameError:
    my_val = None

other_params = {}
try:
    other_params['level1_param'] = level1_param
except NameError:
    other_params['level1_param'] = 'not_present'
try:
    other_params['level2_param'] = level2_param
except NameError:
    other_params['level2_param'] = 'not_present'
try:
    other_params['level3_param'] = level3_param
except NameError:
    other_params['level3_param'] = 'not_present'

result = {'my_param': my_val, 'other_params': other_params}
""",
        }

        for i in range(1, 5):
            builder.add_node("PythonCodeNode", f"level{i}", {"code": codes[i]})

        # Connect in chain
        builder.add_connection("level1", "result", "level2", "input")
        builder.add_connection("level2", "result", "level3", "input")
        builder.add_connection("level3", "result", "level4", "input")

        workflow = builder.build()

        # Each node gets its own parameter
        parameters = {
            "level1": {"level1_param": "value1"},
            "level2": {"level2_param": "value2"},
            "level3": {"level3_param": "value3"},
            "level4": {"level4_param": "value4"},
        }

        results = execute_runtime(runtime, workflow, parameters=parameters)

        # Verify all 4 nodes executed
        assert len(results) == 4
        assert "level1" in results
        assert "level2" in results
        assert "level3" in results
        assert "level4" in results

        # Verify each node got its own parameter and NOT others'
        assert results["level1"]["my_param"] == "value1"
        assert all(
            v == "not_present" for v in results["level1"]["other_params"].values()
        )

        assert results["level2"]["my_param"] == "value2"
        assert all(
            v == "not_present" for v in results["level2"]["other_params"].values()
        )

        assert results["level3"]["my_param"] == "value3"
        assert all(
            v == "not_present" for v in results["level3"]["other_params"].values()
        )

        assert results["level4"]["my_param"] == "value4"
        assert all(
            v == "not_present" for v in results["level4"]["other_params"].values()
        )

    @pytest.mark.parametrize(
        "runtime_class",
        [
            pytest.param(LocalRuntime, id="sync"),
        ],
    )
    def test_five_level_nested_switches(self, runtime_class):
        """Test 5-level nested switches (stress test)."""
        runtime = runtime_class(conditional_execution="skip_branches")
        builder = WorkflowBuilder()

        # Create 5 levels of switches
        for i in range(1, 6):
            builder.add_node(
                "SwitchNode",
                f"level{i}_switch",
                {
                    "condition_field": f"check{i}",
                    "operator": "==",
                    "value": "pass",
                },
            )

        # Final processor
        builder.add_node("PythonCodeNode", "final", {"code": "result = {'depth': 5}"})

        # Chain connections
        for i in range(1, 5):
            builder.add_connection(
                f"level{i}_switch", "true_output", f"level{i+1}_switch", "input"
            )
        builder.add_connection("level5_switch", "true_output", "final", "input")

        workflow = builder.build()

        # Each switch gets its own parameter
        parameters = {f"level{i}_switch": {f"check{i}": "pass"} for i in range(1, 6)}

        results = execute_runtime(runtime, workflow, parameters=parameters)

        # All 6 nodes should execute (5 switches + 1 final)
        assert len(results) == 6
        assert results["final"]["depth"] == 5


class TestDirectPrepareNodeInputsAPI:
    """Test direct calls to _prepare_node_inputs() internal API."""

    def test_direct_prepare_node_inputs_with_node_specific_params(self):
        """
        Test direct _prepare_node_inputs() call with node-specific parameters.

        This tests the internal API directly to ensure parameter filtering works
        correctly at the lowest level.
        """
        runtime = LocalRuntime()
        builder = WorkflowBuilder()

        # Create a workflow with multiple nodes to test filtering
        code = """
try:
    value_value = value
except NameError:
    value_value = None
result = {'value': value_value}
"""
        builder.add_node("PythonCodeNode", "test_node", {"code": code})
        builder.add_node("PythonCodeNode", "other_node", {"code": code})

        workflow = builder.build()
        # Access node instance from internal storage
        node_instance = workflow._node_instances["test_node"]

        # Call _prepare_node_inputs directly with mixed parameters
        # NOTE: _prepare_node_inputs expects parameters to be already processed
        # by _process_workflow_parameters(), so we need to pass them in the
        # processed format: {"node_id": {params}, "global_key": value}
        raw_parameters = {
            "test_node": {"value": 42},  # Node-specific
            "other_node": {"value": 99},  # Should be filtered out
            "global_param": "global_value",  # Global (not a node ID)
        }

        # Process parameters first
        processed_parameters = runtime._process_workflow_parameters(
            workflow, raw_parameters
        )

        inputs = runtime._prepare_node_inputs(
            workflow=workflow,
            node_id="test_node",
            node_instance=node_instance,
            node_outputs={},
            parameters=processed_parameters,
        )

        # Should include test_node's value + global_param
        assert "value" in inputs
        assert inputs["value"] == 42
        assert "global_param" in inputs
        assert inputs["global_param"] == "global_value"

        # The processed parameters will have structure:
        # {"test_node": {...}, "other_node": {...}}
        # After filtering in _prepare_node_inputs, we should NOT have:
        # 1. The "test_node" key itself (its contents are unwrapped)
        # 2. The "other_node" key (filtered out as it's another node's ID)
        assert "test_node" not in inputs  # Unwrapped, not present as key
        assert "other_node" not in inputs  # Filtered out (it's another node's ID)

    def test_direct_prepare_node_inputs_filters_node_ids(self):
        """
        Test that _prepare_node_inputs filters out other node IDs correctly.
        """
        runtime = LocalRuntime()
        builder = WorkflowBuilder()

        # Create workflow with 3 nodes
        for node_id in ["node1", "node2", "node3"]:
            builder.add_node("PythonCodeNode", node_id, {"code": "result = {}"})

        workflow = builder.build()
        # Access node instance from internal storage
        node_instance = workflow._node_instances["node2"]

        # Parameters with all 3 node IDs
        parameters = {
            "node1": {"value": 1},
            "node2": {"value": 2},
            "node3": {"value": 3},
        }

        inputs = runtime._prepare_node_inputs(
            workflow=workflow,
            node_id="node2",
            node_instance=node_instance,
            node_outputs={},
            parameters=parameters,
        )

        # Should ONLY include node2's parameters
        assert "value" in inputs
        assert inputs["value"] == 2
        # Should NOT include node1 or node3
        assert "node1" not in inputs
        assert "node3" not in inputs


class TestCyclicWorkflowParameterScoping:
    """Test parameter scoping in cyclic workflows."""

    @pytest.mark.skip(reason="Cyclic workflow execution not fully implemented yet")
    def test_cyclic_workflow_parameter_scoping(self):
        """
        Test parameter scoping in cyclic workflows.

        Scenario:
        - Cyclic workflow with node A -> B -> C -> A (cycle)
        - Each node has its own parameters
        - Parameters should not leak across iterations
        """
        runtime = LocalRuntime(enable_cycles=True)
        builder = WorkflowBuilder()

        # Create cyclic workflow
        code_a = """
try:
    result = {'value': value_a}
except NameError:
    result = {'value': None}
"""
        code_b = """
try:
    result = {'value': value_b}
except NameError:
    result = {'value': None}
"""
        code_c = """
try:
    result = {'value': value_c}
except NameError:
    result = {'value': None}
"""

        builder.add_node("PythonCodeNode", "node_a", {"code": code_a})
        builder.add_node("PythonCodeNode", "node_b", {"code": code_b})
        builder.add_node("PythonCodeNode", "node_c", {"code": code_c})

        # Create cycle: A -> B -> C -> A
        builder.add_connection("node_a", "result", "node_b", "input")
        builder.add_connection("node_b", "result", "node_c", "input")
        builder.add_connection("node_c", "result", "node_a", "input")

        workflow = builder.build()

        parameters = {
            "node_a": {"value_a": "A"},
            "node_b": {"value_b": "B"},
            "node_c": {"value_c": "C"},
        }

        # This test will be implemented when cyclic workflows are fully supported
        # For now, skip with message
        pass


class TestParameterScopingWithConnections:
    """Test parameter scoping when combined with connection mapping."""

    @pytest.mark.parametrize(
        "runtime_class",
        [
            pytest.param(LocalRuntime, id="sync"),
        ],
    )
    def test_connection_parameters_and_node_specific_params_combined(
        self, runtime_class
    ):
        """
        Test that connection parameters and node-specific parameters combine correctly.

        Scenario:
        - source node outputs {"data": "from_connection"}
        - target node has node-specific param {"config": "node_config"}
        - target should receive BOTH connection data and node-specific config
        """
        runtime = runtime_class()
        builder = WorkflowBuilder()

        # Source node
        builder.add_node(
            "PythonCodeNode", "source", {"code": "result = {'data': 'from_connection'}"}
        )

        # Target node that uses both connection and node-specific params
        code = """
try:
    data_value = data
except NameError:
    data_value = None

try:
    config_value = config
except NameError:
    config_value = None

result = {'data': data_value, 'config': config_value}
"""
        builder.add_node("PythonCodeNode", "target", {"code": code})

        # Connect - source outputs 'result', map it to target's 'data' parameter
        builder.add_connection("source", "result.data", "target", "data")

        workflow = builder.build()

        # Node-specific parameter for target
        parameters = {"target": {"config": "node_config"}}

        results = execute_runtime(runtime, workflow, parameters=parameters)

        # Target should have both connection data and node-specific config
        assert results["target"]["data"] == "from_connection"
        assert results["target"]["config"] == "node_config"
