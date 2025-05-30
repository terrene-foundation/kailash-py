"""Testing utilities for Kailash workflows and nodes."""

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeValidationError, WorkflowExecutionError
from kailash.tracking import TaskManager
from kailash.workflow import Workflow


class MockNode(Node):
    """Mock node for testing purposes."""

    def __init__(self, **kwargs):
        """Initialize mock node with test behavior."""
        super().__init__(**kwargs)
        self._return_value = kwargs.get("return_value", {"output": "test"})
        self._should_fail = kwargs.get("should_fail", False)
        self._fail_message = kwargs.get("fail_message", "Mock failure")
        self._execution_count = 0

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define mock parameters."""
        return {
            "input": NodeParameter(
                name="input", type=Any, required=False, description="Mock input"
            ),
            "return_value": NodeParameter(
                name="return_value",
                type=dict,
                required=False,
                default={"output": "test"},
                description="Value to return",
            ),
            "should_fail": NodeParameter(
                name="should_fail",
                type=bool,
                required=False,
                default=False,
                description="Whether the node should fail",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute mock node logic."""
        self._execution_count += 1

        if self._should_fail:
            raise RuntimeError(self._fail_message)

        # Return configured value or default
        return self._return_value

    @property
    def execution_count(self) -> int:
        """Get the number of times this node was executed."""
        return self._execution_count


class TestDataGenerator:
    """Generate test data for workflow testing."""

    @staticmethod
    def generate_csv_data(
        rows: int = 10, columns: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate mock CSV data."""
        if columns is None:
            columns = ["id", "name", "value", "category"]

        data = []
        categories = ["A", "B", "C", "D"]

        for i in range(rows):
            row = {
                "id": i + 1,
                "name": f"Item_{i+1}",
                "value": (i + 1) * 10 + (i % 3),
                "category": categories[i % len(categories)],
            }

            # Only include requested columns
            row = {k: v for k, v in row.items() if k in columns}
            data.append(row)

        return data

    @staticmethod
    def generate_json_data(structure: str = "simple") -> Union[Dict, List]:
        """Generate mock JSON data."""
        if structure == "simple":
            return {
                "name": "Test Data",
                "version": "1.0",
                "data": [{"id": 1, "value": "test1"}, {"id": 2, "value": "test2"}],
            }
        elif structure == "nested":
            return {
                "metadata": {"created": "2024-01-01", "author": "test"},
                "records": [
                    {"id": 1, "nested": {"key": "value1"}},
                    {"id": 2, "nested": {"key": "value2"}},
                ],
            }
        elif structure == "array":
            return [
                {"id": 1, "data": "value1"},
                {"id": 2, "data": "value2"},
                {"id": 3, "data": "value3"},
            ]
        else:
            return {"type": structure}

    @staticmethod
    def generate_text_data(lines: int = 5) -> str:
        """Generate mock text data."""
        text_lines = []
        for i in range(lines):
            text_lines.append(f"This is line {i+1} of the test text.")
            if i % 2 == 0:
                text_lines.append(
                    f"It contains some interesting data about item {i+1}."
                )

        return "\n".join(text_lines)


class WorkflowTestHelper:
    """Helper class for testing workflows."""

    def __init__(self):
        """Initialize test helper."""
        self.runtime = LocalRuntime(debug=True)
        self.task_manager = None

    def create_test_workflow(self, name: str = "test_workflow") -> Workflow:
        """Create a simple test workflow."""
        workflow = Workflow(name=name)

        # Add some mock nodes
        workflow.add_node("input", MockNode(), return_value={"data": [1, 2, 3]})
        workflow.add_node("process", MockNode(), return_value={"processed": [2, 4, 6]})
        workflow.add_node("output", MockNode(), return_value={"result": "success"})

        # Connect nodes
        workflow.connect("input", "process", {"data": "input"})
        workflow.connect("process", "output", {"processed": "data"})

        return workflow

    def run_workflow(
        self,
        workflow: Workflow,
        with_tracking: bool = True,
        parameters: Optional[Dict] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Run a workflow with optional tracking."""
        if with_tracking:
            self.task_manager = TaskManager()
        else:
            self.task_manager = None

        return self.runtime.execute(workflow, self.task_manager, parameters)

    def assert_workflow_success(
        self, workflow: Workflow, expected_nodes: Optional[List[str]] = None
    ):
        """Assert that a workflow runs successfully."""
        results, run_id = self.run_workflow(workflow)

        # Check that all expected nodes were executed
        if expected_nodes:
            for node_id in expected_nodes:
                assert node_id in results, f"Node {node_id} was not executed"
                assert (
                    "error" not in results[node_id]
                ), f"Node {node_id} failed: {results[node_id].get('error')}"

        return results, run_id

    def assert_node_output(
        self,
        results: Dict[str, Any],
        node_id: str,
        expected_keys: List[str],
        expected_values: Optional[Dict] = None,
    ):
        """Assert that a node produced expected output."""
        assert node_id in results, f"Node {node_id} not found in results"

        node_output = results[node_id]

        # Check expected keys
        for key in expected_keys:
            assert key in node_output, f"Key '{key}' not found in {node_id} output"

        # Check expected values if provided
        if expected_values:
            for key, expected_value in expected_values.items():
                assert (
                    node_output.get(key) == expected_value
                ), f"Node {node_id} key '{key}' expected {expected_value}, got {node_output.get(key)}"


class NodeTestHelper:
    """Helper class for testing individual nodes."""

    @staticmethod
    def test_node_parameters(node: Node, expected_params: Dict[str, type]):
        """Test that a node has expected parameters."""
        params = node.get_parameters()

        for param_name, expected_type in expected_params.items():
            assert param_name in params, f"Parameter '{param_name}' not found"
            param = params[param_name]
            assert (
                param.type == expected_type
            ), f"Parameter '{param_name}' expected type {expected_type}, got {param.type}"

    @staticmethod
    def test_node_execution(
        node: Node,
        inputs: Dict[str, Any],
        expected_keys: List[str],
        should_fail: bool = False,
    ) -> Dict[str, Any]:
        """Test node execution with given inputs."""
        if should_fail:
            try:
                result = node.execute(**inputs)
                assert False, "Node execution should have failed but didn't"
            except (NodeValidationError, WorkflowExecutionError):
                return {}
        else:
            result = node.execute(**inputs)

            # Check expected output keys
            for key in expected_keys:
                assert key in result, f"Expected key '{key}' not found in output"

            return result

    @staticmethod
    def test_node_validation(
        node: Node, valid_inputs: Dict[str, Any], invalid_inputs: List[Dict[str, Any]]
    ):
        """Test node input validation."""
        # Test valid inputs
        try:
            node.validate_inputs(**valid_inputs)
        except NodeValidationError:
            assert False, "Valid inputs failed validation"

        # Test invalid inputs
        for invalid_input in invalid_inputs:
            try:
                node.validate_inputs(**invalid_input)
                assert False, f"Invalid input {invalid_input} passed validation"
            except NodeValidationError:
                pass  # Expected


class TestReporter:
    """Generate test reports for workflows."""

    def __init__(self, task_manager: TaskManager):
        """Initialize reporter with task manager."""
        self.task_manager = task_manager

    def generate_run_report(self, run_id: str) -> Dict[str, Any]:
        """Generate a detailed report for a workflow run."""
        run = self.task_manager.get_run_summary(run_id)
        tasks = self.task_manager.list_tasks(run_id)

        report = {
            "run_id": run_id,
            "workflow": run.workflow_name,
            "status": run.status,
            "duration": run.duration,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "summary": {
                "total_tasks": run.task_count,
                "completed": run.completed_tasks,
                "failed": run.failed_tasks,
            },
            "tasks": [],
        }

        # Add task details
        for task in tasks:
            task_info = {
                "node_id": task.node_id,
                "node_type": task.node_type,
                "status": task.status,
                "duration": task.duration,
            }

            if task.error:
                task_info["error"] = task.error

            report["tasks"].append(task_info)

        return report

    def save_report(self, report: Dict[str, Any], output_path: str):
        """Save report to file."""
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)


# Convenience functions
def create_test_node(node_type: str = "MockNode", **config) -> Node:
    """Create a test node instance."""
    if node_type == "MockNode":
        return MockNode(**config)
    else:
        # Try to get from registry
        from kailash.nodes import NodeRegistry

        node_class = NodeRegistry.get(node_type)
        return node_class(**config)


def create_test_workflow(
    name: str = "test_workflow", nodes: Optional[List[Dict]] = None
) -> Workflow:
    """Create a test workflow with specified nodes."""
    workflow = Workflow(name=name)

    if nodes:
        for node_config in nodes:
            node_id = node_config["id"]
            node_type = node_config.get("type", "MockNode")
            config = node_config.get("config", {})

            node = create_test_node(node_type, **config)
            workflow.add_node(node_id, node, **config)

        # Add connections if specified
        if "connections" in node_config:
            for conn in node_config["connections"]:
                workflow.connect(conn["from"], conn["to"], conn.get("mapping", {}))

    return workflow
