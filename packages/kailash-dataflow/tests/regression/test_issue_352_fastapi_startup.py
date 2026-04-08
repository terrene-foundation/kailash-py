# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for kailash-py#352 — model_registry uses sync
runtime.execute() from async context (FastAPI startup).

Before the fix:

- ``DataFlow.start()`` under FastAPI/uvicorn ran inside an event loop.
- ``ModelRegistry._create_model_registry_table()`` called
  ``self.runtime.execute(workflow.build())`` on an
  :class:`AsyncLocalRuntime`.
- ``AsyncLocalRuntime.execute()`` refuses to run from inside an event
  loop (to prevent Docker/FastAPI thread-creation deadlocks) and
  raises ``RuntimeError("AsyncLocalRuntime.execute() called from async
  context. Use 'await runtime.execute_workflow_async(workflow, inputs)'
  instead.")``.
- The model registry swallowed the exception and continued with the
  ``dataflow_model_registry`` table uncreated, causing every subsequent
  model registration to silently no-op.

After the fix:

- ``ModelRegistry._execute_workflow_sync_safe(workflow)`` dispatches on
  ``self._is_async``:
  * ``False`` → sync ``LocalRuntime.execute()`` path (unchanged).
  * ``True`` + no running loop → ``asyncio.run`` the async variant once.
  * ``True`` + running loop → offload to a worker thread that owns a
    fresh event loop, runs ``execute_workflow_async`` there, and
    returns the result without touching the caller's loop.
- All 13 ``results, _ = self.runtime.execute(workflow.build())`` call
  sites now delegate to the helper.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from dataflow.core.model_registry import ModelRegistry, _normalize_runtime_result

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# _normalize_runtime_result
# ---------------------------------------------------------------------------


def test_normalize_tuple_result() -> None:
    """Tuple shape — the most common return from execute_workflow_async."""
    result = ({"node": {"ok": True}}, "run-123")
    results, run_id = _normalize_runtime_result(result)
    assert results == {"node": {"ok": True}}
    assert run_id == "run-123"


def test_normalize_envelope_dict_result() -> None:
    """``{"results": ..., "run_id": ...}`` envelope shape."""
    result = {"results": {"node": {"ok": True}}, "run_id": "run-456"}
    results, run_id = _normalize_runtime_result(result)
    assert results == {"node": {"ok": True}}
    assert run_id == "run-456"


def test_normalize_plain_dict_result() -> None:
    """Plain dict (legacy) — treated as results with no run_id."""
    result = {"node_a": {"ok": True}, "node_b": {"ok": False}}
    results, run_id = _normalize_runtime_result(result)
    assert results == result
    assert run_id is None


def test_normalize_unknown_shape_returns_empty() -> None:
    """Unknown type — defensive fallback to empty tuple."""
    results, run_id = _normalize_runtime_result("not-a-valid-result")
    assert results == {}
    assert run_id is None


# ---------------------------------------------------------------------------
# _execute_workflow_sync_safe dispatch
# ---------------------------------------------------------------------------


class _FakeWorkflow:
    def __init__(self, built: Any = None) -> None:
        self._built = built or {"workflow": "ddl"}

    def build(self) -> Any:
        return self._built


class _FakeSyncRuntime:
    """Stand-in for LocalRuntime: records sync execute() calls."""

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.return_value: Tuple[Dict[str, Any], Optional[str]] = (
            {"node_a": {"ok": True}},
            "sync-run",
        )

    def execute(self, workflow_built: Any) -> Tuple[Dict[str, Any], Optional[str]]:
        self.calls.append(workflow_built)
        return self.return_value


class _FakeAsyncRuntime:
    """Stand-in for AsyncLocalRuntime.

    * ``execute()`` mimics the real refusal: raises RuntimeError if a
      loop is running. The helper must NEVER hit this path because the
      dispatch uses ``execute_workflow_async`` in async mode.
    * ``execute_workflow_async()`` is an async coroutine that records
      its call and returns the configured tuple shape.
    """

    def __init__(self) -> None:
        self.sync_execute_calls = 0
        self.async_calls: list[Any] = []
        self.return_value: Tuple[Dict[str, Any], str] = (
            {"node_a": {"ok": True}},
            "async-run",
        )

    def execute(self, workflow_built: Any) -> Any:
        self.sync_execute_calls += 1
        raise RuntimeError(
            "AsyncLocalRuntime.execute() called from async context. "
            "Use 'await runtime.execute_workflow_async(workflow, inputs)' "
            "instead. This prevents thread creation which causes "
            "Docker/FastAPI deadlocks."
        )

    async def execute_workflow_async(
        self, workflow_built: Any, inputs: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        self.async_calls.append((workflow_built, inputs))
        return self.return_value


def _build_registry(runtime: Any, is_async: bool) -> ModelRegistry:
    """Construct a ModelRegistry without calling __init__.

    ``ModelRegistry.__init__`` pulls in ``TransactionManager`` and a
    real runtime detection routine; the helper under test does not use
    any of that.  Bypass __init__ with ``__new__`` and seed just the
    attributes the helper reads.
    """
    registry = ModelRegistry.__new__(ModelRegistry)
    registry.runtime = runtime
    registry._is_async = is_async
    return registry


def test_execute_workflow_sync_safe_sync_path_uses_sync_runtime() -> None:
    """Sync runtime → direct sync execute(), no bridging."""
    runtime = _FakeSyncRuntime()
    registry = _build_registry(runtime, is_async=False)

    results, run_id = registry._execute_workflow_sync_safe(_FakeWorkflow())
    assert results == {"node_a": {"ok": True}}
    assert run_id == "sync-run"
    assert len(runtime.calls) == 1


def test_execute_workflow_sync_safe_async_path_outside_loop() -> None:
    """Async runtime + no running loop → asyncio.run(execute_workflow_async)."""
    runtime = _FakeAsyncRuntime()
    registry = _build_registry(runtime, is_async=True)

    results, run_id = registry._execute_workflow_sync_safe(_FakeWorkflow())
    assert results == {"node_a": {"ok": True}}
    assert run_id == "async-run"
    assert runtime.sync_execute_calls == 0
    assert len(runtime.async_calls) == 1


def test_execute_workflow_sync_safe_async_path_inside_loop_uses_worker_thread() -> None:
    """Async runtime + running loop → worker-thread bridge, NOT sync execute.

    This is the gh#352 regression: prior to the fix, calling
    ``runtime.execute()`` from inside an event loop raised the
    AsyncLocalRuntime refusal. The helper now offloads to a worker
    thread with a fresh event loop and never touches the caller's
    loop.
    """
    runtime = _FakeAsyncRuntime()
    registry = _build_registry(runtime, is_async=True)

    async def _caller() -> Tuple[Dict[str, Any], Optional[str]]:
        # We're inside an event loop — exactly the failure condition.
        return registry._execute_workflow_sync_safe(_FakeWorkflow())

    results, run_id = asyncio.run(_caller())

    assert results == {"node_a": {"ok": True}}
    assert run_id == "async-run"
    # CRITICAL: the helper MUST NOT fall back to the sync refusal path.
    assert runtime.sync_execute_calls == 0, (
        "Helper fell back to runtime.execute() from inside a loop — "
        "gh#352 regression."
    )
    assert len(runtime.async_calls) == 1


def test_execute_workflow_sync_safe_accepts_prebuilt_workflow() -> None:
    """Helper must also accept an already-built workflow (no .build())."""
    runtime = _FakeSyncRuntime()
    registry = _build_registry(runtime, is_async=False)

    prebuilt = {"workflow": "prebuilt"}
    registry._execute_workflow_sync_safe(prebuilt)
    assert runtime.calls == [prebuilt]


def test_execute_workflow_sync_safe_bridges_multiple_calls_in_sequence() -> None:
    """Multiple helper calls from the same event loop MUST all succeed.

    Guards against the worker-thread executor leaking state between
    calls (e.g. a closed loop on the second invocation).
    """
    runtime = _FakeAsyncRuntime()
    registry = _build_registry(runtime, is_async=True)

    async def _caller() -> int:
        for _ in range(3):
            results, _run_id = registry._execute_workflow_sync_safe(_FakeWorkflow())
            assert results == {"node_a": {"ok": True}}
        return len(runtime.async_calls)

    total_async_calls = asyncio.run(_caller())
    assert total_async_calls == 3
    assert runtime.sync_execute_calls == 0
