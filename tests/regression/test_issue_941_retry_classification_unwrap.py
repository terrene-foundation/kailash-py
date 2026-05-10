# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #941 — retry classification preserves user
exception type after LocalRuntime swallows leaf-node failures.

Surfaced by /redteam Round 2 against PR #940 (the #929 round-trip
serialization fix). Once #929 unblocked workflow construction, the lifecycle-
hooks test ``test_failure_path_classifies_retry_vs_final`` exposed a separate
gap: ``LocalRuntime._should_stop_on_error`` returns ``False`` when a failed
node has no downstream dependents, so the runtime records the failure in
``results`` and returns NORMALLY. The distributed Worker's retry/final
classification only fires on raised exceptions, so a silently-recorded leaf
failure looked like success and ``on_task_retry`` / ``on_task_failure``
handlers never ran.

Two regressions guarded here:

1. **Leaf-node failures propagate as exceptions.** ``Worker._execute_workflow_sync``
   now scans the recorded ``results`` for any ``failed: True`` payload and
   raises so the upstream classifier can fire retry vs final.

2. **User-meaningful exception type survives SDK wrapping.** ``PythonCodeNode``
   wraps user errors in ``NodeExecutionError`` (chained via ``__context__``).
   ``Worker._execute_workflow_sync`` walks the cause/context chain past SDK
   wrappers so ``failure_event.exception`` carries the user's original error
   type (``ZeroDivisionError`` / ``ValueError`` / etc.), not the bookkeeping
   ``NodeExecutionError``.

Per ``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep",
these tests CALL the function and assert raise/return — they do NOT grep
source for literal substrings.
"""

from __future__ import annotations

import pytest

from kailash.runtime.distributed import TaskMessage, Worker, _unwrap_node_failure
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow.builder import WorkflowBuilder


def _failing_workflow(code: str):
    """1-node Python workflow whose body raises the requested exception."""

    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "fail",
        {"name": "fail", "code": code},
    )
    return builder.build()


@pytest.mark.regression
def test_unwrap_returns_user_exception_when_present_in_chain():
    """Walks past NodeExecutionError to surface ZeroDivisionError."""

    try:
        try:
            raise ZeroDivisionError("intentional")
        except ZeroDivisionError:
            raise NodeExecutionError("Code execution failed: intentional")
    except NodeExecutionError as wrapper:
        payload = {
            "failed": True,
            "error": str(wrapper),
            "error_type": "NodeExecutionError",
            "_exception": wrapper,
        }
        unwrapped = _unwrap_node_failure(payload, "fail")

    assert isinstance(unwrapped, ZeroDivisionError), (
        f"_unwrap_node_failure MUST surface the user's original exception "
        f"type past the SDK wrapper; got {type(unwrapped).__name__}"
    )
    assert str(unwrapped) == "intentional"


@pytest.mark.regression
def test_unwrap_returns_wrapper_when_chain_is_only_wrapper():
    """When the chain has nothing user-meaningful, return the wrapper itself."""

    wrapper = NodeExecutionError("standalone wrapper, no cause")
    payload = {
        "failed": True,
        "error": str(wrapper),
        "error_type": "NodeExecutionError",
        "_exception": wrapper,
    }
    unwrapped = _unwrap_node_failure(payload, "fail")

    assert unwrapped is wrapper, (
        "When the chain contains no non-wrapper exception, _unwrap_node_failure "
        "MUST return the wrapper rather than fabricate a different type."
    )


@pytest.mark.regression
def test_unwrap_falls_back_to_named_builtin_when_exception_object_absent():
    """JSON round-trip strips the exception object — reconstruct by name."""

    payload = {
        "failed": True,
        "error": "boom",
        "error_type": "ValueError",
    }
    unwrapped = _unwrap_node_failure(payload, "fail")

    assert isinstance(unwrapped, ValueError)
    assert str(unwrapped) == "boom"


@pytest.mark.regression
def test_unwrap_falls_back_to_runtimeerror_for_unknown_type_name():
    """Unknown / non-builtin error_type names degrade to RuntimeError."""

    payload = {
        "failed": True,
        "error": "boom",
        "error_type": "DefinitelyNotABuiltin",
    }
    unwrapped = _unwrap_node_failure(payload, "fail")

    assert isinstance(unwrapped, RuntimeError)
    assert str(unwrapped) == "boom"


@pytest.mark.regression
def test_unwrap_handles_self_referential_chain_without_infinite_loop():
    """A pathological self-referential cause chain MUST terminate."""

    wrapper = NodeExecutionError("loop")
    wrapper.__cause__ = wrapper  # pathological
    payload = {
        "failed": True,
        "error": "loop",
        "error_type": "NodeExecutionError",
        "_exception": wrapper,
    }
    unwrapped = _unwrap_node_failure(payload, "fail")

    # The walk visits `wrapper`, sees it is a wrapper, follows __cause__ back
    # to itself, detects the cycle, and falls back to the original exception.
    assert unwrapped is wrapper


@pytest.mark.regression
def test_execute_workflow_sync_raises_on_leaf_node_failure():
    """LocalRuntime swallows leaf failures; the Worker MUST re-raise."""

    worker = Worker(redis_url="redis://localhost:6380", concurrency=1)
    workflow_dict = _failing_workflow(
        "raise ZeroDivisionError('intentional')"
    ).to_dict()
    task = TaskMessage(
        task_id="regression-941-leaf",
        workflow_data=workflow_dict,
        parameters={},
        attempts=1,
        max_attempts=2,
    )

    runtime = worker._get_runtime()

    # The user-meaningful exception type MUST survive past the SDK wrapper.
    with pytest.raises(ZeroDivisionError, match="intentional"):
        worker._execute_workflow_sync(runtime, task)


@pytest.mark.regression
def test_execute_workflow_sync_succeeds_when_no_node_fails():
    """Success path stays untouched: no failed payloads, no raise."""

    worker = Worker(redis_url="redis://localhost:6380", concurrency=1)
    workflow_dict = _failing_workflow("result = 7 * 6").to_dict()
    task = TaskMessage(
        task_id="regression-941-success",
        workflow_data=workflow_dict,
        parameters={},
        attempts=1,
        max_attempts=2,
    )

    runtime = worker._get_runtime()
    results = worker._execute_workflow_sync(runtime, task)

    # Successful execution returns the runtime's results dict — no failed
    # payloads — and no exception escapes.
    assert isinstance(results, dict)
    assert all(
        not (isinstance(v, dict) and v.get("failed") is True) for v in results.values()
    )
