# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #950 -- ``with LocalRuntime()`` triggered "coroutine 'wait_for'
was never awaited" RuntimeWarning on cleanup.

The bug: ``LocalRuntime._cleanup_event_loop`` created the ``wait_for(...)``
coroutine at outer scope, then called ``loop.run_until_complete(...)`` on it.
When ``run_until_complete`` raised before consuming the wait_for coroutine
(e.g. when an outer event loop is already running, as inside an
``async def`` test under pytest-asyncio or a Nexus handler), the wait_for
coroutine became unreachable and surfaced ``RuntimeWarning: coroutine
'wait_for' was never awaited`` at GC.

Adopting the SDK-recommended ``with LocalRuntime() as runtime:`` pattern
(per the LocalRuntime.execute() deprecation message) made the warning
visible across the test suite, blocking zero-tolerance Rule 1 (no new
RuntimeWarnings).

Fix: detect outer running loop and skip async cleanup (the outer loop owns
the AsyncSQL pool lifecycle in that case). When no outer loop is running,
wrap the wait_for in an inner ``async def`` so only one coroutine escapes
scope; closing it cleans up the inner wait_for cleanly even if
run_until_complete raises before consuming the wrapper.

Acceptance criteria from issue #950:
- ``with LocalRuntime() as runtime: runtime.execute(workflow.build())``
  produces zero ``RuntimeWarning``s.
- After fix, the in-test usage at
  ``tests/integration/runtime/test_async_local_dataflow_integration.py::
  test_async_runtime_matches_local_runtime_dataflow`` MUST be switchable
  back to the ``with LocalRuntime()`` form without surfacing the warning.
"""

import asyncio
import warnings

import pytest

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.regression
def test_localruntime_context_manager_clean_roundtrip_no_warning():
    """Acceptance criterion 1: clean ``with LocalRuntime()`` round-trip
    produces zero ``RuntimeWarning`` from the cleanup path.

    Reproduces the user-facing scenario from the issue body verbatim.
    """
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "x", {"code": "result = 1"})

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with LocalRuntime() as runtime:
            results, _ = runtime.execute(wb.build())
        assert results["x"]["result"] == 1


@pytest.mark.regression
def test_localruntime_context_manager_inside_outer_loop_no_wait_for_warning():
    """Acceptance criterion 2: ``with LocalRuntime()`` inside an outer
    asyncio loop (the pytest-asyncio / Nexus / Jupyter case) MUST NOT
    leak the wait_for coroutine.

    This is the failure mode that originally surfaced #950: when
    ``LocalRuntime.__exit__`` ran inside an outer running loop, the
    persistent loop's ``run_until_complete`` raised "Cannot run the event
    loop while another loop is running" before consuming the
    ``asyncio.wait_for`` coroutine, leaving it unawaited.
    """

    async def _scenario() -> int:
        wb = WorkflowBuilder()
        wb.add_node("PythonCodeNode", "x", {"code": "result = 42"})
        with LocalRuntime() as runtime:
            results, _ = runtime.execute(wb.build())
        return results["x"]["result"]

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = asyncio.run(_scenario())

    assert result == 42


@pytest.mark.regression
def test_localruntime_context_manager_repeated_no_warning():
    """Multiple sequential ``with LocalRuntime()`` blocks MUST stay
    warning-clean. Guards against "first run silent, second run leaks"
    cleanup-state regressions in the persistent-loop disposal path.
    """
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "x", {"code": "result = 1"})

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        for _ in range(3):
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(wb.build())
            assert results["x"]["result"] == 1
