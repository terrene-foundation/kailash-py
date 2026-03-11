"""
Unit tests for CLI debug command.

Tests the dataflow-debug command for interactive debugging,
breakpoints, parameter inspection, and step execution.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner


class TestDebugCommand:
    """Test suite for debug command."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    @pytest.fixture
    def workflow_with_nodes(self):
        """Create workflow with multiple nodes."""
        workflow = Mock()
        workflow.nodes = {
            "input_node": Mock(type="InputNode", params={"data": "test"}),
            "process_node": Mock(type="ProcessNode", params={"key": "value"}),
            "output_node": Mock(type="OutputNode", params={}),
        }
        workflow.connections = [
            {"source": "input_node", "target": "process_node"},
            {"source": "process_node", "target": "output_node"},
        ]
        workflow.name = "debug_workflow"
        return workflow

    def test_debug_command_breakpoint_setting(self, runner):
        """
        Test debug command sets breakpoints on nodes.

        Expected behavior:
        - Accepts --breakpoint flag with node name
        - Pauses execution at specified node
        - Shows node state and parameters
        """
        from dataflow.cli.commands import debug

        with patch("dataflow.cli.debug.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock()},
                connections=[],
                name="test_workflow",
            )

            with patch("dataflow.cli.debug.DebugRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value
                mock_instance.set_breakpoint.return_value = True
                mock_instance.execute.return_value = ({"result": "data"}, "run123")

                result = runner.invoke(debug, ["workflow.py", "--breakpoint", "node1"])

                assert result.exit_code == 0
                mock_instance.set_breakpoint.assert_called_with("node1")
                assert (
                    "breakpoint" in result.output.lower()
                    or "node1" in result.output.lower()
                )

    def test_debug_command_parameter_inspection(self, runner):
        """
        Test debug command inspects node parameters.

        Expected behavior:
        - --inspect-node flag shows node details
        - Displays parameters and their values
        - Shows parameter types and validation
        """
        from dataflow.cli.commands import debug

        with patch("dataflow.cli.debug.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={
                    "target_node": Mock(
                        type="ProcessNode", params={"key1": "value1", "key2": 42}
                    )
                },
                connections=[],
                name="test_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                node_info = {
                    "name": "target_node",
                    "type": "ProcessNode",
                    "parameters": {
                        "key1": {"value": "value1", "type": "str"},
                        "key2": {"value": 42, "type": "int"},
                    },
                    "inputs": [],
                    "outputs": ["result"],
                }
                mock_inspector.return_value.inspect_node.return_value = node_info

                result = runner.invoke(
                    debug, ["workflow.py", "--inspect-node", "target_node"]
                )

                assert result.exit_code == 0
                assert "target_node" in result.output
                assert "key1" in result.output or "parameters" in result.output.lower()

    def test_debug_command_step_execution(self, runner):
        """
        Test debug command supports step-by-step execution.

        Expected behavior:
        - --step flag enables step mode
        - Executes one node at a time
        - Shows intermediate results
        """
        from dataflow.cli.commands import debug

        with patch("dataflow.cli.debug.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock()},
                connections=[{"source": "node1", "target": "node2"}],
                name="step_workflow",
            )

            with patch("dataflow.cli.debug.DebugRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value

                # Mock step execution
                step_results = [
                    {
                        "node": "node1",
                        "status": "completed",
                        "output": {"data": "step1"},
                    },
                    {
                        "node": "node2",
                        "status": "completed",
                        "output": {"data": "step2"},
                    },
                ]
                mock_instance.step.side_effect = step_results
                mock_instance.has_next_step.side_effect = [True, True, False]

                # Use runner.invoke with input to simulate user pressing Enter
                result = runner.invoke(
                    debug, ["workflow.py", "--step"], input="\n\n\n"
                )  # Simulate pressing Enter 3 times

                assert result.exit_code == 0
                assert (
                    "step" in result.output.lower() or "node" in result.output.lower()
                )

    def test_debug_command_interactive_mode(self, runner):
        """
        Test debug command interactive mode (mocked).

        Expected behavior:
        - Starts interactive debugger session
        - Supports commands: continue, step, inspect, break
        - Shows workflow state
        """
        from dataflow.cli.commands import debug

        with patch("dataflow.cli.debug.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock()}, connections=[], name="interactive_workflow"
            )

            with patch("dataflow.cli.debug.DebugRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value
                mock_instance.interactive_session.return_value = {
                    "commands_executed": 3,
                    "final_state": "completed",
                }

                # Mock interactive input: inspect node1, continue, exit
                result = runner.invoke(
                    debug,
                    ["workflow.py", "--interactive"],
                    input="inspect node1\ncontinue\nexit\n",
                )

                assert result.exit_code == 0
                # Interactive mode should show some prompt or help
                assert len(result.output) > 0
