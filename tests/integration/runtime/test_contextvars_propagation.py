"""Regression tests for contextvars.Context propagation across thread boundaries.

Issue #1200: AsyncLocalRuntime and LocalRuntime dropped the caller's
contextvars.Context when dispatching node execution across a thread boundary.
A ContextVar set by the caller before execute* was invisible inside a node's
run() (it saw the default).

There are three affected dispatch sites across two classes:
  1. AsyncLocalRuntime._execute_sync_workflow      -> loop.run_in_executor
  2. AsyncLocalRuntime._execute_sync_node_in_thread -> loop.run_in_executor
  3. LocalRuntime._execute_sync                     -> raw threading.Thread

The fix snapshots the caller's context with contextvars.copy_context() in the
calling frame and runs the dispatched callable through ctx.run(...), mirroring
stdlib asyncio.to_thread copy_context semantics.

NO MOCKING — these exercise the real runtimes against real node execution.
"""

import asyncio
import contextvars

import pytest

from kailash.nodes.base import Node, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# A request-scoped ContextVar with a sentinel default. The bug surfaces when a
# node observes the default instead of the value the caller set before execute*.
_ctx_sentinel: contextvars.ContextVar[str] = contextvars.ContextVar(
    "issue_1200_sentinel", default="DEFAULT"
)


@register_node()
class ReadContextVarNode(Node):
    """Sync node that reports the value of the issue-1200 ContextVar.

    A sync node so it is dispatched across the thread boundary the bug lives on
    (async nodes run on the event-loop thread and never lose context).
    """

    def get_parameters(self):
        return {}

    def run(self, **kwargs):
        return {"seen": _ctx_sentinel.get()}


@register_node()
class PassThroughAsyncNode(AsyncNode):
    """Async node forcing the AsyncLocalRuntime mixed-async execution path.

    Its presence alongside a sync node makes the runtime dispatch the sync node
    via ``_execute_sync_node_in_thread`` (site 2) rather than the sync-only
    workflow path (site 1). AsyncNode subclasses implement ``async_run()``.
    """

    def get_parameters(self):
        return {}

    async def async_run(self, **kwargs):
        await asyncio.sleep(0)
        return {"value": "async-ok"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_runtime_sync_only_workflow_propagates_contextvar():
    """Site 1: sync-only workflow under AsyncLocalRuntime.

    A sync-only workflow routes through ``_execute_sync_workflow`` ->
    ``loop.run_in_executor``. The node MUST observe the caller-set value.
    """
    _ctx_sentinel.set("SET-BY-CALLER-A")

    builder = WorkflowBuilder()
    builder.add_node("ReadContextVarNode", "reader", {})
    workflow = builder.build()

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow, inputs={})

    assert results["reader"]["seen"] == "SET-BY-CALLER-A", (
        "contextvar lost across the AsyncLocalRuntime sync-only workflow "
        f"thread hop: got {results['reader']['seen']!r}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_runtime_sync_node_in_mixed_workflow_propagates_contextvar():
    """Site 2: sync node within a mixed async workflow under AsyncLocalRuntime.

    The async node forces the mixed-async path so the sync node is dispatched
    via ``_execute_sync_node_in_thread`` -> ``loop.run_in_executor``.
    """
    _ctx_sentinel.set("SET-BY-CALLER-B")

    builder = WorkflowBuilder()
    builder.add_node("PassThroughAsyncNode", "asyncer", {})
    builder.add_node("ReadContextVarNode", "reader", {})
    workflow = builder.build()

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow, inputs={})

    assert results["reader"]["seen"] == "SET-BY-CALLER-B", (
        "contextvar lost across the AsyncLocalRuntime sync-node thread hop "
        f"in a mixed async workflow: got {results['reader']['seen']!r}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_local_runtime_sync_execute_from_running_loop_propagates_contextvar():
    """Site 3: sync ``LocalRuntime.execute()`` from inside a running loop.

    Being inside this pytest-asyncio coroutine means a loop is already running,
    so ``execute()`` dispatches to ``_execute_sync`` -> raw ``threading.Thread``
    (which starts with an empty context). The node MUST still observe the
    caller-set value.
    """
    _ctx_sentinel.set("SET-BY-CALLER-C")

    builder = WorkflowBuilder()
    builder.add_node("ReadContextVarNode", "reader", {})
    workflow = builder.build()

    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow)

    assert results["reader"]["seen"] == "SET-BY-CALLER-C", (
        "contextvar lost across the LocalRuntime raw-thread hop "
        f"(sync execute from running loop): got {results['reader']['seen']!r}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_runtime_no_contextvar_set_sees_default():
    """Negative/regression: a workflow that does NOT use contextvars is unaffected.

    With no caller set(), the node sees the ContextVar's default — confirming
    the copy_context() wrap introduces no behavior change for the common case.
    """
    # Deliberately do NOT call _ctx_sentinel.set() in this test's context.
    builder = WorkflowBuilder()
    builder.add_node("ReadContextVarNode", "reader", {})
    workflow = builder.build()

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow, inputs={})

    assert results["reader"]["seen"] == "DEFAULT", (
        "node observed an unexpected contextvar value when the caller set "
        f"nothing: got {results['reader']['seen']!r}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_local_runtime_no_contextvar_set_sees_default():
    """Negative/regression: LocalRuntime path is unaffected when no var is set."""
    builder = WorkflowBuilder()
    builder.add_node("ReadContextVarNode", "reader", {})
    workflow = builder.build()

    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow)

    assert results["reader"]["seen"] == "DEFAULT", (
        "node observed an unexpected contextvar value via LocalRuntime when "
        f"the caller set nothing: got {results['reader']['seen']!r}"
    )
