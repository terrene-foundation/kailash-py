"""Golden Pattern 9: AsyncLocalRuntime Pattern - Validation Tests.

Validates async runtime execution for Docker/FastAPI contexts.
"""

import asyncio

import pytest

from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestGoldenPattern9AsyncRuntime:
    """Validate Pattern 9: AsyncLocalRuntime Pattern."""

    @pytest.mark.asyncio
    async def test_async_runtime_execute(self):
        """AsyncLocalRuntime executes workflows asynchronously."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "process",
            {"code": "result = {'value': 42, 'async': True}"},
        )

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert results["process"]["result"]["value"] == 42
        assert results["process"]["result"]["async"] is True

    @pytest.mark.asyncio
    async def test_async_runtime_returns_same_structure(self):
        """AsyncLocalRuntime returns same (results, run_id) tuple as LocalRuntime."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "step", {"code": "result = {'done': True}"})

        runtime = AsyncLocalRuntime()
        output = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert isinstance(output, tuple)
        assert len(output) == 2
        results, run_id = output
        assert isinstance(results, dict)
        assert isinstance(run_id, str)

    def test_sync_runtime_for_cli(self):
        """LocalRuntime works for sync/CLI contexts."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "step", {"code": "result = {'sync': True}"})

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["step"]["result"]["sync"] is True

    @pytest.mark.asyncio
    async def test_async_runtime_with_inputs(self):
        """AsyncLocalRuntime passes inputs to workflow."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "echo",
            {
                "code": """
try:
    msg = msg
except NameError:
    msg = "default"
result = {'echo': msg}
"""
            },
        )

        workflow.add_workflow_inputs("echo", {"msg": "msg"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(), inputs={"msg": "hello"}
        )

        assert results["echo"]["result"]["echo"] == "hello"

    def test_runtime_reuse(self):
        """Runtime instance can be reused across multiple executions."""
        runtime = LocalRuntime()

        for i in range(3):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", "step", {"code": f"result = {{'iteration': {i}}}"}
            )
            results, _ = runtime.execute(workflow.build())
            assert results["step"]["result"]["iteration"] == i
