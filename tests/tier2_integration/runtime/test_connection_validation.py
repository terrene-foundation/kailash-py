"""
Integration tests for connection parameter validation in LocalRuntime.

Tests the implementation of connection validation modes and parameter validation
at the runtime level.
"""

import logging

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class RecordingNode(Node):
    """Real integer validation with observation of the inputs it receives."""

    def __init__(self, **kwargs):
        self.validation_calls = []
        super().__init__(**kwargs)

    def get_parameters(self):
        return {"count": NodeParameter(name="count", type=int, required=True)}

    def validate_inputs(self, **kwargs):
        self.validation_calls.append(dict(kwargs))
        return super().validate_inputs(**kwargs)

    def run(self, **kwargs):
        return kwargs


class MixedNode(RecordingNode):
    def get_parameters(self):
        return {
            "param1": NodeParameter(name="param1", type=str, required=True),
            "param2": NodeParameter(name="param2", type=int, required=True),
        }


def _workflow(node, connected=False, target="count"):
    workflow = Workflow(workflow_id="validation", name="Validation")
    workflow.add_node("test_node", node)
    if connected:
        workflow.add_node("source", "PythonCodeNode", code="result = 1")
        workflow.connect("source", "test_node", {"result": target})
    node.validation_calls.clear()
    return workflow


def _validation_warnings(caplog):
    return [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.getMessage().startswith("Node input validation failed:")
    ]


class TestLocalRuntimeConnectionValidation:
    """Integration tests for LocalRuntime connection validation."""

    def test_runtime_accepts_connection_validation_parameter(self, request):
        """LocalRuntime should accept connection_validation parameter."""
        # Test default value
        runtime = LocalRuntime()
        request.addfinalizer(runtime.close)
        assert hasattr(runtime, "connection_validation")
        assert runtime.connection_validation == "warn"  # Default

        # Test explicit values
        runtime_off = LocalRuntime(connection_validation="off")
        request.addfinalizer(runtime_off.close)
        assert runtime_off.connection_validation == "off"

        runtime_strict = LocalRuntime(connection_validation="strict")
        request.addfinalizer(runtime_strict.close)
        assert runtime_strict.connection_validation == "strict"

        # Test invalid value
        with pytest.raises(ValueError):
            LocalRuntime(connection_validation="invalid")

    def test_prepare_node_inputs_calls_validate_inputs(self):
        """Validate real node inputs against configuration and runtime overrides."""
        node = RecordingNode(count=7)
        workflow = _workflow(node)
        with LocalRuntime(connection_validation="strict") as runtime:
            config_only = runtime._prepare_node_inputs(
                workflow, "test_node", node, {}, {}
            )
            inputs = runtime._prepare_node_inputs(
                workflow, "test_node", node, {}, {"test_node": {"count": "9"}}
            )
        assert config_only == {}
        assert node.validation_calls == [{"count": 7}, {"count": "9"}]
        assert inputs == {"count": 9}

    def test_validation_modes_behavior(self, caplog):
        """Off bypasses validation; warn reports safely; strict raises."""
        node = RecordingNode()
        workflow = _workflow(node)
        parameters = {"test_node": {"count": "private-input-marker"}}
        with LocalRuntime(connection_validation="off") as runtime:
            inputs = runtime._prepare_node_inputs(
                workflow, "test_node", node, {}, parameters
            )
        assert node.validation_calls == []
        assert inputs == parameters["test_node"]
        assert not _validation_warnings(caplog)

        with LocalRuntime(connection_validation="warn") as runtime:
            inputs = runtime._prepare_node_inputs(
                workflow, "test_node", node, {}, parameters
            )
        assert len(node.validation_calls) == 1
        assert inputs == parameters["test_node"]
        warnings = _validation_warnings(caplog)
        assert len(warnings) == 1
        assert "NodeValidationError" in warnings[0].getMessage()
        assert "private-input-marker" not in caplog.text

        with LocalRuntime(connection_validation="strict") as runtime:
            with pytest.raises(
                WorkflowExecutionError, match="Connection Validation Error"
            ):
                runtime._prepare_node_inputs(
                    workflow, "test_node", node, {}, parameters
                )
        assert len(node.validation_calls) == 2

    def test_connection_parameters_are_validated(self):
        """A real connection supplies the value rejected by node validation."""
        node = RecordingNode()
        workflow = _workflow(node, connected=True)
        with LocalRuntime(connection_validation="strict") as runtime:
            with pytest.raises(
                WorkflowExecutionError, match="Connection Validation Error"
            ):
                runtime._prepare_node_inputs(
                    workflow,
                    "test_node",
                    node,
                    {"source": {"result": "not_a_number"}},
                    {},
                )
        assert node.validation_calls == [{"count": "not_a_number"}]

    def test_mixed_parameter_sources(self):
        """Validate connection, configuration, and direct parameters together."""
        node = MixedNode(param2=7)
        workflow = _workflow(node, connected=True, target="param1")
        with LocalRuntime(connection_validation="strict") as runtime:
            inputs = runtime._prepare_node_inputs(
                workflow,
                "test_node",
                node,
                {"source": {"result": "from_connection"}},
                {"param2": 42},
            )
        validated_result = {"param1": "from_connection", "param2": 42}
        assert node.validation_calls == [validated_result]
        assert "param1" in node.validation_calls[0]
        assert "param2" in node.validation_calls[0]
        assert inputs == validated_result

    def test_validation_performance_caching(self):
        """Cached parameter mappings must validate each new value."""
        node = RecordingNode()
        workflow = _workflow(node)
        node.clear_cache()
        with LocalRuntime(connection_validation="strict") as runtime:
            for count in (1, 2):
                assert runtime._prepare_node_inputs(
                    workflow, "test_node", node, {}, {"count": count}
                ) == {"count": count}
            assert node.get_cache_stats()["hits"] >= 1
            with pytest.raises(
                WorkflowExecutionError, match="Connection Validation Error"
            ):
                runtime._prepare_node_inputs(
                    workflow, "test_node", node, {}, {"count": "invalid"}
                )
        assert node.validation_calls == [
            {"count": 1},
            {"count": 2},
            {"count": "invalid"},
        ]

    def test_backward_compatibility(self):
        """Existing workflows should work without modification."""
        # Create a simple workflow
        workflow = WorkflowBuilder()

        class SimpleNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                return {"output": kwargs.get("input", "default")}

        with pytest.warns(UserWarning, match=r"^✅ CUSTOM NODE USAGE CORRECT\n"):
            workflow.add_node(SimpleNode, "node1", {})
        with pytest.warns(UserWarning, match=r"^✅ CUSTOM NODE USAGE CORRECT\n"):
            workflow.add_node(SimpleNode, "node2", {})
        workflow.add_connection("node1", "output", "node2", "input")

        # Should work with default settings
        with LocalRuntime() as runtime:  # Default is "warn"
            results, _ = runtime.execute(workflow.build(), {})

        assert "node1" in results
        assert "node2" in results
        # Verify backward compatibility - node2 receives node1's output
        assert results["node1"]["output"] == "default"
        assert results["node2"]["output"] == "default"
