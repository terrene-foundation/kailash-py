"""Integration tests for handler workflow execution.

NO MOCKING - Tests use real AsyncLocalRuntime to execute handler workflows.
This verifies the full pipeline from handler function to workflow execution.
"""

import os
import sys

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import AsyncLocalRuntime

# --- Handler functions under test ---


async def async_greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}


def sync_multiply(a: int, b: int) -> dict:
    return {"product": a * b}


async def handler_with_defaults(
    text: str, max_length: int = 100, uppercase: bool = False
) -> dict:
    result = text[:max_length]
    if uppercase:
        result = result.upper()
    return {"result": result, "length": len(result)}


async def handler_that_raises(x: int) -> dict:
    if x < 0:
        raise ValueError(f"x must be non-negative, got {x}")
    return {"result": x}


async def handler_returns_nested(data: dict) -> dict:
    return {"processed": True, "data": data, "keys": list(data.keys())}


def _get_handler_result(results: dict) -> dict:
    """Extract handler node output from results dict.

    The results dict is keyed by node_id. For make_handler_workflow,
    the node_id is the second argument passed to the function.
    This helper gets the first (and only) node's result.
    """
    if not results:
        return {}
    # Single-node workflow - get the only result
    return next(iter(results.values()), {})


# --- Integration tests with real runtime ---


class TestHandlerWorkflowExecution:
    """Test handler workflows using real AsyncLocalRuntime."""

    @pytest.mark.asyncio
    async def test_async_handler_execution(self):
        """Execute an async handler workflow end-to-end."""
        workflow = make_handler_workflow(async_greet, "greet")
        runtime = AsyncLocalRuntime()

        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"name": "World", "greeting": "Hi"}
        )

        assert run_id is not None
        # The result is in the handler node's output
        handler_result = _get_handler_result(results)
        assert handler_result.get("message") == "Hi, World!"

    @pytest.mark.asyncio
    async def test_sync_handler_execution(self):
        """Execute a sync handler workflow - sync function runs in executor."""
        workflow = make_handler_workflow(sync_multiply, "multiply")
        runtime = AsyncLocalRuntime()

        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"a": 6, "b": 7}
        )

        assert run_id is not None
        handler_result = _get_handler_result(results)
        assert handler_result.get("product") == 42

    @pytest.mark.asyncio
    async def test_default_parameter_injection(self):
        """Default parameters should be used when not provided in inputs."""
        workflow = make_handler_workflow(handler_with_defaults, "defaults")
        runtime = AsyncLocalRuntime()

        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"text": "Hello World"}
        )

        handler_result = _get_handler_result(results)
        assert handler_result.get("result") == "Hello World"
        assert handler_result.get("length") == 11

    @pytest.mark.asyncio
    async def test_override_defaults(self):
        """Explicitly provided values should override defaults."""
        workflow = make_handler_workflow(handler_with_defaults, "defaults")
        runtime = AsyncLocalRuntime()

        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"text": "hello world", "uppercase": True, "max_length": 5}
        )

        handler_result = _get_handler_result(results)
        assert handler_result.get("result") == "HELLO"

    @pytest.mark.asyncio
    async def test_error_propagation(self):
        """Errors from handlers should propagate as execution errors."""
        workflow = make_handler_workflow(handler_that_raises, "raiser")
        runtime = AsyncLocalRuntime()

        with pytest.raises(Exception, match="x must be non-negative"):
            await runtime.execute_workflow_async(workflow, inputs={"x": -1})

    @pytest.mark.asyncio
    async def test_dict_input_passthrough(self):
        """Dict inputs should pass through to handler correctly."""
        workflow = make_handler_workflow(handler_returns_nested, "nested")
        runtime = AsyncLocalRuntime()

        input_data = {"key1": "value1", "key2": "value2"}
        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"data": input_data}
        )

        handler_result = _get_handler_result(results)
        assert handler_result.get("processed") is True
        assert handler_result.get("keys") == ["key1", "key2"]

    @pytest.mark.asyncio
    async def test_multiple_executions_same_workflow(self):
        """A handler workflow should be reusable across multiple executions."""
        workflow = make_handler_workflow(async_greet, "greet")
        runtime = AsyncLocalRuntime()

        results1, _ = await runtime.execute_workflow_async(
            workflow, inputs={"name": "Alice"}
        )
        results2, _ = await runtime.execute_workflow_async(
            workflow, inputs={"name": "Bob"}
        )

        assert _get_handler_result(results1).get("message") == "Hello, Alice!"
        assert _get_handler_result(results2).get("message") == "Hello, Bob!"
