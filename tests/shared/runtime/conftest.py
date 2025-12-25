"""
Shared fixtures and utilities for runtime parity testing.

This module provides:
- Parametrized runtime fixtures that run tests against both sync and async
- Helper functions for executing workflows with appropriate methods
- Common test data and workflows
"""

import asyncio
import inspect
from typing import Any, Dict

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime


@pytest.fixture(
    params=[
        pytest.param(LocalRuntime, id="sync"),
        pytest.param(AsyncLocalRuntime, id="async"),
    ]
)
def runtime_class(request):
    """
    Parametrize tests to run against both sync and async runtimes.

    Usage:
        def test_something(runtime_class):
            runtime = runtime_class()
            # Test runs twice: once with LocalRuntime, once with AsyncLocalRuntime
    """
    return request.param


@pytest.fixture
def runtime_instance(runtime_class):
    """
    Create runtime instance for testing.

    Provides a clean runtime instance for each test.
    """
    return runtime_class()


def execute_runtime(runtime, workflow, **kwargs) -> Dict[str, Any]:
    """
    Execute workflow with appropriate method for runtime type.

    Both sync and async runtimes now return the same structure: (results, run_id)
    - LocalRuntime: uses execute() -> (results, run_id)
    - AsyncLocalRuntime: uses execute_workflow_async() -> (results, run_id)

    Args:
        runtime: Runtime instance (LocalRuntime or AsyncLocalRuntime)
        workflow: Workflow to execute
        **kwargs: Additional execution parameters (parameters, inputs, etc.)

    Returns:
        Results dictionary with node outputs extracted

    Example:
        >>> runtime = LocalRuntime()
        >>> results = execute_runtime(runtime, workflow, parameters={"input": "data"})
    """
    # Normalize parameter naming: convert 'parameters' to 'inputs' for AsyncLocalRuntime
    if "parameters" in kwargs and "inputs" not in kwargs:
        kwargs["inputs"] = kwargs.pop("parameters")

    # Check if runtime has async execution method
    if hasattr(runtime, "execute_workflow_async") and inspect.iscoroutinefunction(
        runtime.execute_workflow_async
    ):
        # AsyncLocalRuntime: use async method -> (results, run_id)
        raw_results, run_id = asyncio.run(
            runtime.execute_workflow_async(workflow, **kwargs)
        )
    else:
        # LocalRuntime: use sync method (convert back to 'parameters' if needed)
        if "inputs" in kwargs and "parameters" not in kwargs:
            kwargs["parameters"] = kwargs.pop("inputs")
        # Use context manager for LocalRuntime
        with runtime:
            raw_results, run_id = runtime.execute(workflow, **kwargs)

    # Normalize nested result structure: extract "result" key from each node output
    normalized = {}
    for node_id, node_output in raw_results.items():
        if isinstance(node_output, dict) and "result" in node_output:
            # Extract the actual result
            normalized[node_id] = node_output["result"]
        else:
            normalized[node_id] = node_output

    return normalized


def execute_runtime_with_run_id(runtime, workflow, **kwargs) -> tuple:
    """
    Execute workflow and return both results and run_id.

    Both sync and async runtimes now return: (results, run_id)

    Args:
        runtime: Runtime instance
        workflow: Workflow to execute
        **kwargs: Execution parameters

    Returns:
        Tuple of (results, run_id)
    """
    # Normalize parameter naming: convert 'parameters' to 'inputs' for AsyncLocalRuntime
    if "parameters" in kwargs and "inputs" not in kwargs:
        kwargs["inputs"] = kwargs.pop("parameters")

    if hasattr(runtime, "execute_workflow_async") and inspect.iscoroutinefunction(
        runtime.execute_workflow_async
    ):
        # AsyncLocalRuntime: now returns (results, run_id) just like sync
        return asyncio.run(runtime.execute_workflow_async(workflow, **kwargs))
    else:
        # LocalRuntime: convert back to 'parameters' if needed
        if "inputs" in kwargs and "parameters" not in kwargs:
            kwargs["parameters"] = kwargs.pop("inputs")
        # Use context manager for LocalRuntime
        with runtime:
            return runtime.execute(workflow, **kwargs)


def is_async_runtime(runtime) -> bool:
    """
    Check if runtime is async.

    Args:
        runtime: Runtime instance

    Returns:
        True if AsyncLocalRuntime, False if LocalRuntime
    """
    return isinstance(runtime, AsyncLocalRuntime)


def is_sync_runtime(runtime) -> bool:
    """
    Check if runtime is sync.

    Args:
        runtime: Runtime instance

    Returns:
        True if LocalRuntime (and not AsyncLocalRuntime), False otherwise
    """
    return isinstance(runtime, LocalRuntime) and not isinstance(
        runtime, AsyncLocalRuntime
    )
