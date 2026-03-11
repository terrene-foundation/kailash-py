"""
Unit tests for Inspector parameter tracing methods.

Tests:
- ParameterTrace dataclass and show() method
- trace_parameter() - DFS backward tracing
- parameter_flow() - BFS forward tracing
- find_parameter_source() - Simple source lookup
- parameter_dependencies() - All dependencies for a node
- parameter_consumers() - All consumers of an output
"""

import pytest
from dataflow.platform.inspector import Inspector, ParameterTrace

from kailash.workflow.builder import WorkflowBuilder


class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self):
        self.nodes = {}
        self.connections = []

    def add_connection(self, source_node, source_param, target_node, target_param):
        self.connections.append(
            {
                "source_node": source_node,
                "source_parameter": source_param,
                "target_node": target_node,
                "target_parameter": target_param,
            }
        )


class TestParameterTraceDataclass:
    """Test ParameterTrace dataclass."""

    def test_parameter_trace_creation(self):
        """Test creating ParameterTrace instance."""
        trace = ParameterTrace(
            parameter_name="email",
            source_node="fetch_user",
            source_parameter="user_email",
            transformations=[{"type": "dot_notation", "details": "data.email → email"}],
            consumers=["create_user", "send_email"],
            parameter_type="str",
            is_complete=True,
        )

        assert trace.parameter_name == "email"
        assert trace.source_node == "fetch_user"
        assert trace.source_parameter == "user_email"
        assert len(trace.transformations) == 1
        assert len(trace.consumers) == 2
        assert trace.is_complete is True

    def test_parameter_trace_defaults(self):
        """Test ParameterTrace default values."""
        trace = ParameterTrace(parameter_name="test_param")

        assert trace.parameter_name == "test_param"
        assert trace.source_node is None
        assert trace.source_parameter is None
        assert trace.transformations == []
        assert trace.consumers == []
        assert trace.parameter_type is None
        assert trace.is_complete is True
        assert trace.missing_sources == []

    def test_parameter_trace_show_complete(self):
        """Test show() method for complete trace."""
        trace = ParameterTrace(
            parameter_name="email",
            source_node="fetch_user",
            source_parameter="user_email",
            transformations=[
                {
                    "type": "dot_notation",
                    "details": "data.email → email",
                    "from": "data.email",
                    "to": "email",
                }
            ],
            is_complete=True,
        )

        output = trace.show(color=False)

        assert "Parameter Trace: email" in output
        assert "Source:" in output
        assert "Node: fetch_user" in output
        assert "Parameter: user_email" in output
        assert "Transformations (1):" in output
        assert "Dot Notation: data.email → email" in output
        assert "Flow:" in output

    def test_parameter_trace_show_incomplete(self):
        """Test show() method for incomplete trace."""
        trace = ParameterTrace(
            parameter_name="missing_param",
            is_complete=False,
            missing_sources=["No source found for node.missing_param"],
        )

        output = trace.show(color=False)

        assert "Parameter Trace: missing_param" in output
        assert "Workflow input" in output
        assert "Missing Sources:" in output
        assert "No source found" in output


class TestTraceParameter:
    """Test trace_parameter method."""

    def test_trace_simple_parameter(self):
        """Test tracing simple parameter with direct connection."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        trace = inspector.trace_parameter("node_b", "input")

        assert trace.parameter_name == "input"
        assert trace.source_node == "node_a"
        assert trace.source_parameter == "output"
        assert trace.is_complete is True
        # Parameter name change is a transformation
        assert len(trace.transformations) == 1
        assert trace.transformations[0]["type"] == "mapping"

    def test_trace_parameter_with_mapping(self):
        """Test tracing parameter with name mapping."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "user_data", "node_b", "input_data")

        inspector = Inspector(None, workflow)
        trace = inspector.trace_parameter("node_b", "input_data")

        assert trace.parameter_name == "input_data"
        assert trace.source_node == "node_a"
        assert trace.source_parameter == "user_data"
        assert trace.is_complete is True
        assert len(trace.transformations) == 1
        assert trace.transformations[0]["type"] == "mapping"
        assert "user_data → input_data" in trace.transformations[0]["details"]

    def test_trace_parameter_with_dot_notation(self):
        """Test tracing parameter with dot notation."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "data.user.email", "node_b", "email")

        inspector = Inspector(None, workflow)
        trace = inspector.trace_parameter("node_b", "email")

        assert trace.parameter_name == "email"
        assert trace.source_node == "node_a"
        assert trace.source_parameter == "data.user.email"
        assert trace.is_complete is True
        assert len(trace.transformations) == 1
        assert trace.transformations[0]["type"] == "dot_notation"

    def test_trace_parameter_chain(self):
        """Test tracing parameter through multiple nodes."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")
        workflow.add_connection("node_b", "result", "node_c", "data")

        inspector = Inspector(None, workflow)
        trace = inspector.trace_parameter("node_c", "data")

        # Should trace back to node_b (direct source)
        assert trace.parameter_name == "data"
        assert trace.source_node == "node_b"
        assert trace.source_parameter == "result"

    def test_trace_parameter_no_source(self):
        """Test tracing parameter with no source (workflow input)."""
        workflow = MockWorkflow()
        # No connections to this parameter

        inspector = Inspector(None, workflow)
        trace = inspector.trace_parameter("node_a", "input")

        assert trace.parameter_name == "input"
        assert trace.source_node is None
        assert trace.is_complete is True  # Complete but no source = workflow input
        assert len(trace.transformations) == 0

    def test_trace_parameter_no_workflow(self):
        """Test tracing parameter with no workflow attached."""
        inspector = Inspector(None, None)
        trace = inspector.trace_parameter("node_a", "input")

        assert trace.parameter_name == "input"
        assert trace.is_complete is False
        assert "No workflow attached" in trace.missing_sources[0]


class TestParameterFlow:
    """Test parameter_flow method."""

    def test_flow_simple_parameter(self):
        """Test flowing parameter forward through workflow."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        traces = inspector.parameter_flow("node_a", "output")

        assert len(traces) == 1
        assert traces[0].parameter_name == "input"
        assert traces[0].source_node == "node_a"
        assert traces[0].source_parameter == "output"

    def test_flow_multiple_consumers(self):
        """Test flowing parameter to multiple consumers."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input1")
        workflow.add_connection("node_a", "output", "node_c", "input2")

        inspector = Inspector(None, workflow)
        traces = inspector.parameter_flow("node_a", "output")

        assert len(traces) == 2
        param_names = [trace.parameter_name for trace in traces]
        assert "input1" in param_names
        assert "input2" in param_names

    def test_flow_with_transformations(self):
        """Test flowing parameter with transformations."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "user_data", "node_b", "input_data")

        inspector = Inspector(None, workflow)
        traces = inspector.parameter_flow("node_a", "user_data")

        assert len(traces) == 1
        assert traces[0].parameter_name == "input_data"
        assert len(traces[0].transformations) == 1
        assert traces[0].transformations[0]["type"] == "mapping"

    def test_flow_no_consumers(self):
        """Test flowing parameter with no consumers."""
        workflow = MockWorkflow()
        # No outgoing connections from node_a

        inspector = Inspector(None, workflow)
        traces = inspector.parameter_flow("node_a", "output")

        assert len(traces) == 0

    def test_flow_no_workflow(self):
        """Test flowing parameter with no workflow attached."""
        inspector = Inspector(None, None)
        traces = inspector.parameter_flow("node_a", "output")

        assert len(traces) == 0


class TestFindParameterSource:
    """Test find_parameter_source method."""

    def test_find_source_exists(self):
        """Test finding source when it exists."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        source = inspector.find_parameter_source("node_b", "input")

        assert source == "node_a"

    def test_find_source_none(self):
        """Test finding source when it doesn't exist (workflow input)."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        source = inspector.find_parameter_source("node_a", "input")

        assert source is None

    def test_find_source_no_workflow(self):
        """Test finding source with no workflow attached."""
        inspector = Inspector(None, None)
        source = inspector.find_parameter_source("node_a", "input")

        assert source is None


class TestParameterDependencies:
    """Test parameter_dependencies method."""

    def test_dependencies_single_parameter(self):
        """Test getting dependencies for node with single parameter."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        deps = inspector.parameter_dependencies("node_b")

        assert len(deps) == 1
        assert "input" in deps
        assert deps["input"].source_node == "node_a"
        assert deps["input"].source_parameter == "output"

    def test_dependencies_multiple_parameters(self):
        """Test getting dependencies for node with multiple parameters."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output1", "node_c", "input1")
        workflow.add_connection("node_b", "output2", "node_c", "input2")

        inspector = Inspector(None, workflow)
        deps = inspector.parameter_dependencies("node_c")

        assert len(deps) == 2
        assert "input1" in deps
        assert "input2" in deps
        assert deps["input1"].source_node == "node_a"
        assert deps["input2"].source_node == "node_b"

    def test_dependencies_no_parameters(self):
        """Test getting dependencies for node with no incoming connections."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        deps = inspector.parameter_dependencies("node_a")

        assert len(deps) == 0

    def test_dependencies_duplicate_parameters(self):
        """Test getting dependencies with duplicate parameter names (should deduplicate)."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")
        # Simulating duplicate connection (shouldn't happen in practice)
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        deps = inspector.parameter_dependencies("node_b")

        # Should only have one entry despite duplicate connections
        assert len(deps) == 1
        assert "input" in deps

    def test_dependencies_no_workflow(self):
        """Test getting dependencies with no workflow attached."""
        inspector = Inspector(None, None)
        deps = inspector.parameter_dependencies("node_a")

        assert len(deps) == 0


class TestParameterConsumers:
    """Test parameter_consumers method."""

    def test_consumers_single_consumer(self):
        """Test finding single consumer of output parameter."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        consumers = inspector.parameter_consumers("node_a", "output")

        assert len(consumers) == 1
        assert "node_b" in consumers

    def test_consumers_multiple_consumers(self):
        """Test finding multiple consumers of output parameter."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_b", "input1")
        workflow.add_connection("node_a", "output", "node_c", "input2")

        inspector = Inspector(None, workflow)
        consumers = inspector.parameter_consumers("node_a", "output")

        assert len(consumers) == 2
        assert "node_b" in consumers
        assert "node_c" in consumers

    def test_consumers_different_output_params(self):
        """Test filtering by specific output parameter."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output1", "node_b", "input1")
        workflow.add_connection("node_a", "output2", "node_c", "input2")

        inspector = Inspector(None, workflow)
        consumers = inspector.parameter_consumers("node_a", "output1")

        assert len(consumers) == 1
        assert "node_b" in consumers
        assert "node_c" not in consumers

    def test_consumers_no_consumers(self):
        """Test finding consumers when there are none."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        consumers = inspector.parameter_consumers("node_a", "output")

        assert len(consumers) == 0

    def test_consumers_sorted(self):
        """Test that consumers are returned sorted."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "output", "node_z", "input")
        workflow.add_connection("node_a", "output", "node_b", "input")
        workflow.add_connection("node_a", "output", "node_m", "input")

        inspector = Inspector(None, workflow)
        consumers = inspector.parameter_consumers("node_a", "output")

        assert consumers == ["node_b", "node_m", "node_z"]

    def test_consumers_no_workflow(self):
        """Test finding consumers with no workflow attached."""
        inspector = Inspector(None, None)
        consumers = inspector.parameter_consumers("node_a", "output")

        assert len(consumers) == 0


class TestParameterTracingIntegration:
    """Integration tests for parameter tracing methods."""

    def test_complex_workflow_tracing(self):
        """Test tracing in a complex workflow with multiple paths."""
        workflow = MockWorkflow()

        # Build complex workflow:
        # node_a (output) → node_b (input) → node_b (result) → node_d (data)
        #                → node_c (input) → node_c (result) → node_e (data)
        workflow.add_connection("node_a", "output", "node_b", "input")
        workflow.add_connection("node_a", "output", "node_c", "input")
        workflow.add_connection("node_b", "result", "node_d", "data")
        workflow.add_connection("node_c", "result", "node_e", "data")

        inspector = Inspector(None, workflow)

        # Test trace_parameter
        trace_d = inspector.trace_parameter("node_d", "data")
        assert trace_d.source_node == "node_b"
        assert trace_d.source_parameter == "result"

        # Test parameter_flow
        flows = inspector.parameter_flow("node_a", "output")
        assert len(flows) >= 2  # At least two paths

        # Test parameter_dependencies
        deps_d = inspector.parameter_dependencies("node_d")
        assert "data" in deps_d

        # Test parameter_consumers
        consumers_a = inspector.parameter_consumers("node_a", "output")
        assert len(consumers_a) == 2
        assert "node_b" in consumers_a
        assert "node_c" in consumers_a

    def test_dot_notation_transformation_tracking(self):
        """Test tracking dot notation transformations through workflow."""
        workflow = MockWorkflow()
        workflow.add_connection("node_a", "data.user.profile.email", "node_b", "email")
        workflow.add_connection("node_b", "processed_email", "node_c", "user_email")

        inspector = Inspector(None, workflow)

        # Trace from node_b
        trace_b = inspector.trace_parameter("node_b", "email")
        assert trace_b.source_parameter == "data.user.profile.email"
        assert len(trace_b.transformations) == 1
        assert trace_b.transformations[0]["type"] == "dot_notation"

        # Trace from node_c
        trace_c = inspector.trace_parameter("node_c", "user_email")
        assert trace_c.source_node == "node_b"
        assert trace_c.source_parameter == "processed_email"
        assert len(trace_c.transformations) == 1
        assert trace_c.transformations[0]["type"] == "mapping"

    def test_cycle_detection_in_tracing(self):
        """Test that parameter tracing handles cycles correctly."""
        workflow = MockWorkflow()

        # Create a cycle: node_a → node_b → node_c → node_a
        workflow.add_connection("node_a", "output", "node_b", "input")
        workflow.add_connection("node_b", "output", "node_c", "input")
        workflow.add_connection("node_c", "output", "node_a", "input")

        inspector = Inspector(None, workflow)

        # Should not infinite loop
        trace = inspector.trace_parameter("node_b", "input")
        assert trace is not None

        # Should detect visited nodes
        flows = inspector.parameter_flow("node_a", "output")
        assert len(flows) >= 0  # Should complete without hanging
