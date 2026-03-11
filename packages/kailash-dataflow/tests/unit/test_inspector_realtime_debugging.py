"""
Unit tests for Inspector real-time debugging methods.

Tests:
- ExecutionEvent, RuntimeState, BreakpointInfo dataclasses
- watch_execution() - Monitor workflow execution with callbacks
- breakpoint_at_node() - Set breakpoints with optional conditions
- inspect_runtime_state() - Get current execution state
- parameter_values_at_node() - Get parameter values at node
- get_breakpoints() - List all breakpoints
- remove_breakpoint() - Remove specific breakpoint
- clear_breakpoints() - Clear all breakpoints
- get_execution_events() - Get execution event history
"""

import pytest
from dataflow.platform.inspector import (
    BreakpointInfo,
    ExecutionEvent,
    Inspector,
    RuntimeState,
)

from kailash.workflow.builder import WorkflowBuilder


class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self):
        self.nodes = {}
        self.connections = []

    def add_node(self, node_id, node_type="mock"):
        self.nodes[node_id] = {"id": node_id, "type": node_type}

    def add_connection(self, source_node, source_param, target_node, target_param):
        self.connections.append(
            {
                "source_node": source_node,
                "source_parameter": source_param,
                "target_node": target_node,
                "target_parameter": target_param,
            }
        )


class TestExecutionEventDataclass:
    """Test ExecutionEvent dataclass."""

    def test_execution_event_creation(self):
        """Test creating ExecutionEvent instance."""
        event = ExecutionEvent(
            event_type="node_start",
            node_id="process_data",
            timestamp=1635724800.0,
            data={"input": "test"},
        )

        assert event.event_type == "node_start"
        assert event.node_id == "process_data"
        assert event.timestamp == 1635724800.0
        assert event.data == {"input": "test"}
        assert event.error is None

    def test_execution_event_defaults(self):
        """Test ExecutionEvent default values."""
        event = ExecutionEvent(
            event_type="node_complete", node_id="process", timestamp=1635724800.0
        )

        assert event.data == {}
        assert event.error is None

    def test_execution_event_with_error(self):
        """Test ExecutionEvent with error."""
        event = ExecutionEvent(
            event_type="node_error",
            node_id="failing_node",
            timestamp=1635724800.0,
            error="Connection timeout",
        )

        assert event.event_type == "node_error"
        assert event.error == "Connection timeout"

    def test_execution_event_show(self):
        """Test ExecutionEvent show() method."""
        event = ExecutionEvent(
            event_type="node_start",
            node_id="process",
            timestamp=1635724800.0,
            data={"key": "value"},
        )

        output = event.show(color=False)

        assert "→ [node_start] process" in output
        assert "Data:" in output

    def test_execution_event_show_with_error(self):
        """Test ExecutionEvent show() method with error."""
        event = ExecutionEvent(
            event_type="node_error",
            node_id="failing_node",
            timestamp=1635724800.0,
            error="Test error",
        )

        output = event.show(color=False)

        assert "✗ [node_error] failing_node" in output
        assert "Error: Test error" in output


class TestRuntimeStateDataclass:
    """Test RuntimeState dataclass."""

    def test_runtime_state_creation(self):
        """Test creating RuntimeState instance."""
        state = RuntimeState(
            active_nodes=["node_b"],
            completed_nodes=["node_a"],
            pending_nodes=["node_c", "node_d"],
            execution_order=["node_a", "node_b", "node_c", "node_d"],
            current_node="node_b",
        )

        assert state.active_nodes == ["node_b"]
        assert state.completed_nodes == ["node_a"]
        assert state.pending_nodes == ["node_c", "node_d"]
        assert state.current_node == "node_b"

    def test_runtime_state_defaults(self):
        """Test RuntimeState default values."""
        state = RuntimeState(
            active_nodes=[],
            completed_nodes=[],
            pending_nodes=["node_a"],
            execution_order=["node_a"],
        )

        assert state.current_node is None
        assert state.parameter_values == {}
        assert state.events == []

    def test_runtime_state_with_parameters(self):
        """Test RuntimeState with parameter values."""
        state = RuntimeState(
            active_nodes=["node_b"],
            completed_nodes=["node_a"],
            pending_nodes=[],
            execution_order=["node_a", "node_b"],
            parameter_values={
                "node_a": {"output": "result_a"},
                "node_b": {"input": "result_a", "param": "value"},
            },
        )

        assert "node_a" in state.parameter_values
        assert state.parameter_values["node_a"]["output"] == "result_a"
        assert state.parameter_values["node_b"]["input"] == "result_a"

    def test_runtime_state_show(self):
        """Test RuntimeState show() method."""
        event = ExecutionEvent(
            event_type="node_start", node_id="node_a", timestamp=1635724800.0
        )

        state = RuntimeState(
            active_nodes=["node_b"],
            completed_nodes=["node_a"],
            pending_nodes=["node_c"],
            execution_order=["node_a", "node_b", "node_c"],
            current_node="node_b",
            events=[event],
        )

        output = state.show(color=False)

        assert "Runtime State" in output
        assert "Active Nodes:" in output
        assert "Completed Nodes:" in output
        assert "Current Node: node_b" in output
        assert "Completed: 1" in output
        assert "Active: 1" in output
        assert "Pending: 1" in output


class TestBreakpointInfoDataclass:
    """Test BreakpointInfo dataclass."""

    def test_breakpoint_info_creation(self):
        """Test creating BreakpointInfo instance."""
        breakpoint = BreakpointInfo(
            node_id="critical_node", condition="value > 100", enabled=True, hit_count=5
        )

        assert breakpoint.node_id == "critical_node"
        assert breakpoint.condition == "value > 100"
        assert breakpoint.enabled is True
        assert breakpoint.hit_count == 5

    def test_breakpoint_info_defaults(self):
        """Test BreakpointInfo default values."""
        breakpoint = BreakpointInfo(node_id="node_a")

        assert breakpoint.condition is None
        assert breakpoint.enabled is True
        assert breakpoint.hit_count == 0

    def test_breakpoint_info_show_unconditional(self):
        """Test show() method for unconditional breakpoint."""
        breakpoint = BreakpointInfo(node_id="node_a", enabled=True, hit_count=3)

        output = breakpoint.show(color=False)

        assert "Breakpoint at node_a" in output
        assert "enabled" in output
        assert "Hit count: 3" in output

    def test_breakpoint_info_show_conditional(self):
        """Test show() method for conditional breakpoint."""
        breakpoint = BreakpointInfo(
            node_id="node_b", condition="x > 50", enabled=True, hit_count=0
        )

        output = breakpoint.show(color=False)

        assert "Breakpoint at node_b" in output
        assert "Condition: x > 50" in output
        assert "enabled" in output

    def test_breakpoint_info_show_disabled(self):
        """Test show() method for disabled breakpoint."""
        breakpoint = BreakpointInfo(node_id="node_c", enabled=False)

        output = breakpoint.show(color=False)

        assert "Breakpoint at node_c" in output
        assert "disabled" in output


class TestWatchExecution:
    """Test watch_execution method."""

    def test_watch_execution_basic(self):
        """Test basic watch_execution without callback."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")
        workflow.add_node("node_b")
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)
        state = inspector.watch_execution(workflow)

        assert state is not None
        assert isinstance(state, RuntimeState)
        assert state.active_nodes == []
        assert state.completed_nodes == []
        assert len(state.pending_nodes) > 0

    def test_watch_execution_with_callback(self):
        """Test watch_execution with callback registration."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")

        callback_called = []

        def test_callback(event):
            callback_called.append(event)

        inspector = Inspector(None, workflow)
        state = inspector.watch_execution(workflow, callback=test_callback)

        # Callback should be registered
        assert len(inspector._execution_callbacks) == 1
        assert inspector._execution_callbacks[0] == test_callback

    def test_watch_execution_initializes_state(self):
        """Test watch_execution initializes runtime state."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")
        workflow.add_node("node_b")

        inspector = Inspector(None, workflow)
        state = inspector.watch_execution(workflow)

        assert inspector._runtime_state is state
        assert state.execution_order is not None
        assert state.parameter_values == {}
        assert state.events == []

    def test_watch_execution_no_workflow(self):
        """Test watch_execution with no workflow attached."""
        inspector = Inspector(None, None)
        state = inspector.watch_execution(None)

        # Should return state but with empty execution order
        assert isinstance(state, RuntimeState)
        assert state.execution_order == []


class TestBreakpointAtNode:
    """Test breakpoint_at_node method."""

    def test_breakpoint_unconditional(self):
        """Test setting unconditional breakpoint."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")

        inspector = Inspector(None, workflow)
        breakpoint = inspector.breakpoint_at_node("node_a")

        assert breakpoint.node_id == "node_a"
        assert breakpoint.condition is None
        assert breakpoint.enabled is True
        assert breakpoint.hit_count == 0

    def test_breakpoint_conditional(self):
        """Test setting conditional breakpoint."""
        workflow = MockWorkflow()
        workflow.add_node("critical_node")

        inspector = Inspector(None, workflow)
        breakpoint = inspector.breakpoint_at_node("critical_node", condition="x > 100")

        assert breakpoint.node_id == "critical_node"
        assert breakpoint.condition == "x > 100"
        assert breakpoint.enabled is True

    def test_breakpoint_stored(self):
        """Test breakpoint is stored in inspector."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        breakpoint = inspector.breakpoint_at_node("node_a")

        assert "node_a" in inspector._breakpoints
        assert inspector._breakpoints["node_a"] == breakpoint

    def test_breakpoint_overwrites_existing(self):
        """Test setting breakpoint overwrites existing one."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)

        # Set first breakpoint
        bp1 = inspector.breakpoint_at_node("node_a", condition="x > 10")
        assert inspector._breakpoints["node_a"].condition == "x > 10"

        # Set second breakpoint (should overwrite)
        bp2 = inspector.breakpoint_at_node("node_a", condition="y < 5")
        assert inspector._breakpoints["node_a"].condition == "y < 5"


class TestInspectRuntimeState:
    """Test inspect_runtime_state method."""

    def test_inspect_runtime_state_none(self):
        """Test inspect_runtime_state when no state exists."""
        inspector = Inspector(None, None)
        state = inspector.inspect_runtime_state()

        assert state is None

    def test_inspect_runtime_state_after_watch(self):
        """Test inspect_runtime_state after watch_execution."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")

        inspector = Inspector(None, workflow)

        # Initialize state with watch_execution
        watch_state = inspector.watch_execution(workflow)

        # Should return same state object
        state = inspector.inspect_runtime_state()
        assert state is watch_state
        assert state is inspector._runtime_state

    def test_inspect_runtime_state_returns_current_state(self):
        """Test inspect_runtime_state returns current state."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)

        # Manually set state
        test_state = RuntimeState(
            active_nodes=["node_a"],
            completed_nodes=[],
            pending_nodes=["node_b"],
            execution_order=["node_a", "node_b"],
        )
        inspector._runtime_state = test_state

        state = inspector.inspect_runtime_state()
        assert state is test_state
        assert state.active_nodes == ["node_a"]


class TestParameterValuesAtNode:
    """Test parameter_values_at_node method."""

    def test_parameter_values_no_state(self):
        """Test parameter_values_at_node when no state exists."""
        inspector = Inspector(None, None)
        values = inspector.parameter_values_at_node("node_a")

        assert values is None

    def test_parameter_values_node_not_in_state(self):
        """Test parameter_values_at_node when node not in state."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        inspector._runtime_state = RuntimeState(
            active_nodes=[],
            completed_nodes=[],
            pending_nodes=["node_a"],
            execution_order=["node_a"],
            parameter_values={},
        )

        values = inspector.parameter_values_at_node("node_a")
        assert values is None

    def test_parameter_values_node_in_state(self):
        """Test parameter_values_at_node when node has values."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        inspector._runtime_state = RuntimeState(
            active_nodes=[],
            completed_nodes=["node_a"],
            pending_nodes=[],
            execution_order=["node_a"],
            parameter_values={"node_a": {"input": "test", "output": "result"}},
        )

        values = inspector.parameter_values_at_node("node_a")
        assert values == {"input": "test", "output": "result"}

    def test_parameter_values_multiple_nodes(self):
        """Test parameter_values_at_node with multiple nodes."""
        workflow = MockWorkflow()

        inspector = Inspector(None, workflow)
        inspector._runtime_state = RuntimeState(
            active_nodes=[],
            completed_nodes=["node_a", "node_b"],
            pending_nodes=[],
            execution_order=["node_a", "node_b"],
            parameter_values={
                "node_a": {"value": 100},
                "node_b": {"value": 200},
            },
        )

        values_a = inspector.parameter_values_at_node("node_a")
        values_b = inspector.parameter_values_at_node("node_b")

        assert values_a == {"value": 100}
        assert values_b == {"value": 200}


class TestGetBreakpoints:
    """Test get_breakpoints method."""

    def test_get_breakpoints_empty(self):
        """Test get_breakpoints when no breakpoints exist."""
        inspector = Inspector(None, None)
        breakpoints = inspector.get_breakpoints()

        assert breakpoints == []

    def test_get_breakpoints_single(self):
        """Test get_breakpoints with single breakpoint."""
        inspector = Inspector(None, None)
        inspector.breakpoint_at_node("node_a")

        breakpoints = inspector.get_breakpoints()

        assert len(breakpoints) == 1
        assert breakpoints[0].node_id == "node_a"

    def test_get_breakpoints_multiple(self):
        """Test get_breakpoints with multiple breakpoints."""
        inspector = Inspector(None, None)
        inspector.breakpoint_at_node("node_a")
        inspector.breakpoint_at_node("node_b", condition="x > 10")
        inspector.breakpoint_at_node("node_c")

        breakpoints = inspector.get_breakpoints()

        assert len(breakpoints) == 3
        node_ids = [bp.node_id for bp in breakpoints]
        assert "node_a" in node_ids
        assert "node_b" in node_ids
        assert "node_c" in node_ids


class TestRemoveBreakpoint:
    """Test remove_breakpoint method."""

    def test_remove_breakpoint_exists(self):
        """Test removing existing breakpoint."""
        inspector = Inspector(None, None)
        inspector.breakpoint_at_node("node_a")
        inspector.breakpoint_at_node("node_b")

        # Remove node_a breakpoint
        removed = inspector.remove_breakpoint("node_a")

        assert removed is True
        assert "node_a" not in inspector._breakpoints
        assert "node_b" in inspector._breakpoints

    def test_remove_breakpoint_not_exists(self):
        """Test removing non-existent breakpoint."""
        inspector = Inspector(None, None)
        inspector.breakpoint_at_node("node_a")

        # Try to remove non-existent breakpoint
        removed = inspector.remove_breakpoint("node_b")

        assert removed is False
        assert "node_a" in inspector._breakpoints

    def test_remove_breakpoint_empty(self):
        """Test removing breakpoint when none exist."""
        inspector = Inspector(None, None)

        removed = inspector.remove_breakpoint("node_a")

        assert removed is False


class TestClearBreakpoints:
    """Test clear_breakpoints method."""

    def test_clear_breakpoints_empty(self):
        """Test clearing breakpoints when none exist."""
        inspector = Inspector(None, None)
        inspector.clear_breakpoints()

        assert len(inspector._breakpoints) == 0

    def test_clear_breakpoints_single(self):
        """Test clearing single breakpoint."""
        inspector = Inspector(None, None)
        inspector.breakpoint_at_node("node_a")

        inspector.clear_breakpoints()

        assert len(inspector._breakpoints) == 0

    def test_clear_breakpoints_multiple(self):
        """Test clearing multiple breakpoints."""
        inspector = Inspector(None, None)
        inspector.breakpoint_at_node("node_a")
        inspector.breakpoint_at_node("node_b")
        inspector.breakpoint_at_node("node_c")

        assert len(inspector._breakpoints) == 3

        inspector.clear_breakpoints()

        assert len(inspector._breakpoints) == 0


class TestGetExecutionEvents:
    """Test get_execution_events method."""

    def test_get_execution_events_empty(self):
        """Test get_execution_events when no events exist."""
        inspector = Inspector(None, None)
        events = inspector.get_execution_events()

        assert events == []

    def test_get_execution_events_with_events(self):
        """Test get_execution_events with events."""
        inspector = Inspector(None, None)

        # Manually add events
        event1 = ExecutionEvent(
            event_type="node_start", node_id="node_a", timestamp=1635724800.0
        )
        event2 = ExecutionEvent(
            event_type="node_complete", node_id="node_a", timestamp=1635724801.0
        )

        inspector._execution_events = [event1, event2]

        events = inspector.get_execution_events()

        assert len(events) == 2
        assert events[0].event_type == "node_start"
        assert events[1].event_type == "node_complete"

    def test_get_execution_events_returns_copy(self):
        """Test get_execution_events returns a copy."""
        inspector = Inspector(None, None)

        event = ExecutionEvent(
            event_type="node_start", node_id="node_a", timestamp=1635724800.0
        )
        inspector._execution_events = [event]

        events = inspector.get_execution_events()

        # Modify returned list
        events.append(
            ExecutionEvent(
                event_type="node_error", node_id="node_b", timestamp=1635724802.0
            )
        )

        # Original should not be modified
        assert len(inspector._execution_events) == 1


class TestRealtimeDebuggingIntegration:
    """Integration tests for real-time debugging methods."""

    def test_complete_debugging_workflow(self):
        """Test complete debugging workflow."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")
        workflow.add_node("node_b")
        workflow.add_connection("node_a", "output", "node_b", "input")

        inspector = Inspector(None, workflow)

        # 1. Set breakpoints
        bp1 = inspector.breakpoint_at_node("node_a")
        bp2 = inspector.breakpoint_at_node("node_b", condition="x > 100")

        # 2. Watch execution
        state = inspector.watch_execution(workflow)
        assert state is not None

        # 3. Check breakpoints
        breakpoints = inspector.get_breakpoints()
        assert len(breakpoints) == 2

        # 4. Inspect runtime state
        current_state = inspector.inspect_runtime_state()
        assert current_state is state

        # 5. Get parameter values (none yet)
        values = inspector.parameter_values_at_node("node_a")
        assert values is None

        # 6. Remove one breakpoint
        removed = inspector.remove_breakpoint("node_a")
        assert removed is True
        assert len(inspector.get_breakpoints()) == 1

        # 7. Clear all breakpoints
        inspector.clear_breakpoints()
        assert len(inspector.get_breakpoints()) == 0

    def test_callback_integration(self):
        """Test callback integration with watch_execution."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")

        callbacks_executed = []

        def callback1(event):
            callbacks_executed.append(("callback1", event))

        def callback2(event):
            callbacks_executed.append(("callback2", event))

        inspector = Inspector(None, workflow)

        # Register multiple callbacks
        inspector.watch_execution(workflow, callback=callback1)
        inspector.watch_execution(workflow, callback=callback2)

        # Both callbacks should be registered
        assert len(inspector._execution_callbacks) == 2

    def test_state_persistence(self):
        """Test state persistence across method calls."""
        workflow = MockWorkflow()
        workflow.add_node("node_a")

        inspector = Inspector(None, workflow)

        # Initialize state
        state1 = inspector.watch_execution(workflow)

        # Manually update state
        inspector._runtime_state.active_nodes.append("node_a")
        inspector._runtime_state.parameter_values["node_a"] = {"value": 42}

        # Verify state persists
        state2 = inspector.inspect_runtime_state()
        assert state2 is state1
        assert "node_a" in state2.active_nodes
        assert state2.parameter_values["node_a"]["value"] == 42

        # Parameter values should reflect updates
        values = inspector.parameter_values_at_node("node_a")
        assert values == {"value": 42}
