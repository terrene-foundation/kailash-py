# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression for issue #942 — LocalRuntime._execute_sync's pool-cleanup
``finally`` block must not leak an un-awaited ``wait_for`` coroutine when
``loop.run_until_complete`` raises before driving the wrapper.

Per ``rules/zero-tolerance.md`` Rule 1 the warning MUST be fixed (not
deferred). Per the issue's acceptance criteria the regression test runs
under ``-W error::RuntimeWarning`` so any drop in the cleanup path flips
the warning to a typed exception that the test catches.

Sibling of ``tests/integration/runtime/test_local_runtime_exit_cleanup.py``
which covers the ``_cleanup_event_loop`` path on ``__exit__`` / ``close``.
This file covers the OTHER cleanup site — ``_execute_sync.finally`` —
that lives inside the worker-thread that ``LocalRuntime.execute`` spawns
when called from within an existing event loop (pytest-asyncio, Nexus,
Jupyter, Kaizen agent loop).
"""

from __future__ import annotations

import asyncio
import warnings

import pytest

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.regression
@pytest.mark.asyncio
async def test_execute_sync_from_async_context_no_wait_for_warning() -> None:
    """The cleanup ``finally`` in ``_execute_sync`` MUST NOT leak the
    ``wait_for`` coroutine.

    Reproduces the failure mode from issue #942: when ``runtime.execute``
    is called from within an existing event loop (e.g., pytest-asyncio
    test, Nexus handler), the runtime spawns a worker thread that creates
    its own loop, runs the workflow, and tears down the loop in
    ``finally``. The pre-fix cleanup passed ``asyncio.wait_for(...)``
    directly to ``loop.run_until_complete``; if the run_until_complete
    raised or the loop was closing, the inner ``wait_for`` coroutine was
    GC'd un-awaited, surfacing as
    ``RuntimeWarning: coroutine 'wait_for' was never awaited``.

    Post-fix the cleanup wraps in an inner ``async def`` and explicitly
    closes the wrapper coroutine, mirroring the ``_cleanup_event_loop``
    pattern that already fixed the sibling cleanup path.
    """
    # pytest-asyncio active loop → LocalRuntime.execute MUST take the
    # _execute_sync path (worker thread + nested loop).
    asyncio.get_running_loop()

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        # Drive the runtime synchronously from inside the async test.
        # `run_in_executor` mirrors how production callers (workers,
        # Nexus handlers) reach the sync path.
        def _run_sync() -> dict:
            runtime = LocalRuntime()
            wf = WorkflowBuilder()
            wf.add_node(
                "PythonCodeNode",
                "noop",
                {"code": "result = {'ok': True}"},
            )
            results, _ = runtime.execute(wf.build())
            return results

        results = await asyncio.get_running_loop().run_in_executor(None, _run_sync)
        assert results["noop"]["result"]["ok"] is True

        offenders = [
            str(w.message)
            for w in recorded
            if issubclass(w.category, RuntimeWarning)
            and "never awaited" in str(w.message).lower()
            and ("wait_for" in str(w.message) or "clear_shared_pools" in str(w.message))
        ]
        assert not offenders, (
            "_execute_sync finally-block left an un-awaited coroutine "
            f"(issue #942 regression). Offenders: {offenders}"
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_execute_sync_wait_for_failure_does_not_leak_coroutine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force the failure mode in the issue body: ``asyncio.wait_for``
    raises before scheduling the inner coroutine, so the inner coroutine
    is constructed but never awaited.

    Pre-fix: ``_execute_sync.finally`` constructed ``_clear_pools(...)``
    inline as the first argument to ``wait_for``; if ``wait_for`` raised
    before its body awaited the coroutine, the coroutine was GC'd and
    Python emitted ``RuntimeWarning: coroutine ... was never awaited``.

    Post-fix: the cleanup ``finally`` block explicitly closes the wrapper
    coroutine, which in turn closes the orphaned inner ``wait_for`` and
    ``_clear_pools`` coroutines, so no warning surfaces.
    """
    real_clear = AsyncSQLDatabaseNode.clear_shared_pools
    real_wait_for = asyncio.wait_for

    # Sanity: ensure the cleanup path will construct a coroutine.
    assert asyncio.iscoroutinefunction(real_clear)

    def failing_wait_for(coro, timeout):  # noqa: D401
        # Simulate a wait_for that fails BEFORE driving its inner coro
        # AND does NOT close the coro arg — this is the worst-case
        # contract violation the post-fix ``finally`` block must defend
        # against (close the inner coroutine even when wait_for orphans
        # it). Pre-fix this leaks ``coro`` un-awaited; post-fix the
        # wrapper's ``finally`` closes ``_inner`` defensively.
        raise asyncio.TimeoutError("simulated cancel-before-start")

    monkeypatch.setattr(asyncio, "wait_for", failing_wait_for)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        def _run_sync() -> dict:
            runtime = LocalRuntime()
            wf = WorkflowBuilder()
            wf.add_node(
                "PythonCodeNode",
                "noop",
                {"code": "result = {'ok': True}"},
            )
            results, _ = runtime.execute(wf.build())
            return results

        results = await asyncio.get_running_loop().run_in_executor(None, _run_sync)
        assert results["noop"]["result"]["ok"] is True

        # Restore wait_for so subsequent tests are unaffected.
        monkeypatch.setattr(asyncio, "wait_for", real_wait_for)

        offenders = [
            str(w.message)
            for w in recorded
            if issubclass(w.category, RuntimeWarning)
            and "never awaited" in str(w.message).lower()
        ]
        assert not offenders, (
            "wait_for cancel-before-start path left a coroutine un-awaited "
            f"(issue #942 regression). Offenders: {offenders}"
        )
