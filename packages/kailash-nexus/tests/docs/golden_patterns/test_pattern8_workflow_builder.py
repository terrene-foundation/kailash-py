"""Golden Pattern 8: Workflow Builder Pattern - Validation Tests.

Validates multi-step workflows with connections and data flow.
"""

import pytest

from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestGoldenPattern8WorkflowBuilder:
    """Validate Pattern 8: Workflow Builder Pattern."""

    def test_workflow_build_required(self):
        """Workflow must call .build() before execution."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "step1", {"code": "result = {'value': 42}"})

        built = workflow.build()
        assert built is not None

        runtime = LocalRuntime()
        results, run_id = runtime.execute(built)
        assert results["step1"]["result"]["value"] == 42

    def test_multi_step_workflow(self):
        """Multi-step workflow with data transformation."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "validate",
            {
                "code": """
result = {
    'valid': True,
    'data': {'name': 'test', 'value': 100}
}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "transform",
            {
                "code": """
result = {
    'transformed': True,
    'output': 'processed'
}
"""
            },
        )

        workflow.add_connection("validate", "result", "transform", "input_data")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["validate"]["result"]["valid"] is True
        assert results["transform"]["result"]["transformed"] is True

    def test_workflow_returns_tuple(self):
        """Runtime.execute returns (results, run_id) tuple."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "step", {"code": "result = {'done': True}"})

        runtime = LocalRuntime()
        output = runtime.execute(workflow.build())

        assert isinstance(output, tuple)
        assert len(output) == 2
        results, run_id = output
        assert isinstance(results, dict)
        assert isinstance(run_id, str)

    def test_workflow_with_string_node_ids(self):
        """Node IDs must be string literals."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode", "first_step", {"code": "result = {'step': 1}"}
        )
        workflow.add_node(
            "PythonCodeNode", "second_step", {"code": "result = {'step': 2}"}
        )

        workflow.add_connection("first_step", "result", "second_step", "data")

        built = workflow.build()
        assert built is not None

    @pytest.mark.asyncio
    async def test_workflow_inputs(self):
        """Workflow can receive external inputs."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "process",
            {
                "code": """
try:
    name = name
except NameError:
    name = "default"
result = {'greeting': f'Hello, {name}!'}
"""
            },
        )

        workflow.add_workflow_inputs("process", {"name": "name"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(), inputs={"name": "World"}
        )
        assert results["process"]["result"]["greeting"] == "Hello, World!"
