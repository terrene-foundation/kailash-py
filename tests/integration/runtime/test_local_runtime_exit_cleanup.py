# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression for issue #917 — LocalRuntime.__exit__ must not leave
``AsyncSQLDatabaseNode.clear_shared_pools`` coroutine un-awaited under the
``wait_for`` cancel/timeout race during shutdown.

Per ``rules/zero-tolerance.md`` Rule 1 the warning MUST be fixed (not
deferred) — and per the issue's acceptance criteria the regression test
runs under ``-W error::RuntimeWarning`` so any drop in the cleanup path
flips the warning to a typed exception that the test catches.
"""

from __future__ import annotations

import asyncio
import warnings

import pytest

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
def test_exit_does_not_leave_clear_shared_pools_coroutine_un_awaited() -> None:
    """The ``__exit__`` cleanup path MUST fully await or close the
    ``AsyncSQLDatabaseNode.clear_shared_pools`` coroutine.

    Reproduces the failure mode from issue #917: when the runtime is
    exited under context-manager-driven shutdown that may race the
    cleanup, the inner coroutine constructed eagerly as an argument to
    ``asyncio.wait_for`` was being GC'd un-awaited, emitting a
    ``RuntimeWarning: coroutine 'AsyncSQLDatabaseNode.clear_shared_pools'
    was never awaited``.

    This test executes a minimal workflow inside a ``with LocalRuntime()``
    block and asserts no ``RuntimeWarning`` mentioning
    ``clear_shared_pools`` is recorded.
    """
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        with LocalRuntime() as runtime:
            wf = WorkflowBuilder()
            wf.add_node(
                "PythonCodeNode",
                "noop",
                {"code": "result = {'ok': True}"},
            )
            results, _ = runtime.execute(wf.build())
            assert results["noop"]["result"]["ok"] is True

        # __exit__ has now run the cleanup path; no un-awaited-coroutine
        # warning must surface.
        offenders = [
            str(w.message)
            for w in recorded
            if issubclass(w.category, RuntimeWarning)
            and "clear_shared_pools" in str(w.message)
            and "never awaited" in str(w.message).lower()
        ]
        assert not offenders, (
            "LocalRuntime.__exit__ left clear_shared_pools coroutine "
            f"un-awaited (issue #917 regression). Offenders: {offenders}"
        )


@pytest.mark.integration
def test_exit_handles_wait_for_failure_without_un_awaited_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force the failure mode in the issue body: ``asyncio.wait_for``
    fails before scheduling the inner coroutine, so the inner coroutine
    is referenced but never awaited.

    Pre-fix the cleanup path constructs ``_clear_pools(graceful=True)``
    inline as the first argument to ``wait_for``; if ``wait_for`` raises
    before its body awaits the coroutine, the coroutine is GC'd and
    Python emits ``RuntimeWarning: coroutine ... was never awaited``.

    Post-fix the ``finally`` block explicitly closes the coroutine when
    it is still in the ``CORO_CREATED`` state, so no warning surfaces.
    """

    real_clear = AsyncSQLDatabaseNode.clear_shared_pools

    real_wait_for = asyncio.wait_for

    def failing_wait_for(coro, timeout):
        # Simulate a wait_for that raises *before* it can await ``coro``
        # — pre-fix this leaks ``coro`` un-awaited; post-fix the
        # ``finally`` block closes ``coro`` defensively.
        raise asyncio.TimeoutError("simulated cancel-before-start")

    monkeypatch.setattr(asyncio, "wait_for", failing_wait_for)

    # Ensure clear_shared_pools is a coroutine function so the
    # cleanup path constructs a coroutine (default state on a fresh
    # AsyncSQLDatabaseNode class).
    assert asyncio.iscoroutinefunction(real_clear)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        runtime = LocalRuntime()
        wf = WorkflowBuilder()
        wf.add_node(
            "PythonCodeNode",
            "noop",
            {"code": "result = {'ok': True}"},
        )
        results, _ = runtime.execute(wf.build())
        assert results["noop"]["result"]["ok"] is True

        runtime.close()

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
            f"(issue #917 regression). Offenders: {offenders}"
        )


@pytest.mark.integration
def test_explicit_close_does_not_leave_coroutine_un_awaited() -> None:
    """Same invariant via explicit ``close()`` — the alternative shutdown
    path that also runs ``_cleanup_event_loop``."""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        runtime = LocalRuntime()
        wf = WorkflowBuilder()
        wf.add_node(
            "PythonCodeNode",
            "noop",
            {"code": "result = {'ok': True}"},
        )
        results, _ = runtime.execute(wf.build())
        assert results["noop"]["result"]["ok"] is True

        runtime.close()

        offenders = [
            str(w.message)
            for w in recorded
            if issubclass(w.category, RuntimeWarning)
            and "clear_shared_pools" in str(w.message)
            and "never awaited" in str(w.message).lower()
        ]
        assert not offenders, (
            "LocalRuntime.close() left clear_shared_pools coroutine "
            f"un-awaited (issue #917 regression). Offenders: {offenders}"
        )
