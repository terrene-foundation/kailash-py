# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: DataFlow.__del__ must not run async cleanup.

Before the fix, ``DataFlow.__del__`` called ``self.close()`` which routed
to ``async_safe_run(...)``. When ``__del__`` was triggered from inside
Python's logging machinery (e.g. GC while ``logging.isEnabledFor`` held
the root logging lock) with a pytest-asyncio / FastAPI / Jupyter event
loop already running, ``async_safe_run`` dispatched to a worker thread
that created a new asyncio loop. ``asyncio.new_event_loop()`` calls
``logger.debug(...)`` during selector-events init, blocking on the same
root logging lock the finalizer thread still held — classic lock-order
deadlock. The unit test suite froze with no traceback; ``pytest --timeout``
did not reliably fire because the finalizer thread was blocked below
pytest's timeout hook.

The faulthandler traceback that identified this was:

    Thread 0x...: in aiosqlite.core._connection_worker_thread
    Thread 0x...: in logging.disable → asyncio.new_event_loop
                    → run_coro_in_new_loop (async_utils.py:227)
    Thread 0x...: in __del__ (engine.py:2923)
                    → close (engine.py:9011)
                    → async_safe_run
                    → _run_in_thread_pool.future.result  ← blocks forever

This test reproduces the deadlock by creating a DataFlow inside a running
event loop, dropping the last reference, and forcing GC. Before the fix
the deadlock would hang forever — the test would be killed by the outer
timeout with an opaque traceback. After the fix ``__del__`` only emits
the ``ResourceWarning`` contract (zero asyncio work), so the call returns
immediately.

See rules/patterns.md § "Async Resource Cleanup — MUST NOT use asyncio
in __del__".
"""

from __future__ import annotations

import asyncio
import gc
import warnings
from unittest.mock import patch

import pytest

from dataflow import DataFlow

pytestmark = [pytest.mark.regression]


@pytest.mark.asyncio
async def test_dataflow_del_does_not_deadlock_in_running_loop():
    """__del__ on an unclosed DataFlow inside a running loop must not hang.

    The outer pytest-asyncio fixture is already running a loop. Dropping
    the reference and calling gc.collect() inside that loop exercises
    the path that deadlocked.
    """

    async def _scenario():
        df = DataFlow("sqlite:///:memory:")
        assert df is not None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            del df
            gc.collect()

    # 5 seconds is ~20x the expected runtime; before the fix this would
    # block on a thread-pool future that never completes.
    await asyncio.wait_for(_scenario(), timeout=5.0)


@pytest.mark.asyncio
async def test_dataflow_del_does_not_invoke_async_safe_run():
    """Behavioural guard: __del__ must not call async_safe_run().

    The async-cleanup-in-finalizer bug is structural — the only
    deadlock-free implementation is "__del__ emits ResourceWarning and
    does nothing else." A call to async_safe_run() inside __del__
    reintroduces the lock-order bug even if today's test runner happens
    to schedule in an order that hides it.

    This test patches ``async_safe_run`` to raise; if __del__ touches it
    the test fails loudly. This is the behavioural equivalent per
    rules/testing.md § "Behavioral Regression Tests Over Source-Grep".
    """
    invocation_count = {"n": 0}

    def _fail_if_called(*args, **kwargs):
        invocation_count["n"] += 1
        raise RuntimeError(
            "async_safe_run must not be called from DataFlow.__del__ — "
            "this reintroduces the lock-order deadlock documented in "
            "rules/patterns.md § 'Async Resource Cleanup'."
        )

    df = DataFlow("sqlite:///:memory:")
    # Patch the import site inside engine.py, not the module-level export.
    with patch("dataflow.core.engine.async_safe_run", side_effect=_fail_if_called):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            del df
            gc.collect()
    assert invocation_count["n"] == 0, (
        f"async_safe_run was called {invocation_count['n']} times from "
        "__del__ — the finalizer must be asyncio-free."
    )


@pytest.mark.asyncio
async def test_dataflow_del_emits_resource_warning_when_unclosed():
    """Contract: __del__ MUST still emit ResourceWarning for unclosed DataFlow.

    Removing self.close() from __del__ must not remove the user-facing
    signal — operators and tests still need to see "you forgot to close
    this DataFlow instance".
    """
    df = DataFlow("sqlite:///:memory:")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        del df
        gc.collect()
    resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert resource_warnings, (
        "DataFlow.__del__ must emit ResourceWarning when the instance "
        "was not closed — this is the replacement for the (unsafe) "
        "self.close() call that previously caused the deadlock."
    )
    assert "Unclosed DataFlow" in str(resource_warnings[0].message)


@pytest.mark.asyncio
async def test_dataflow_close_async_closes_cleanly():
    """close_async() is the supported async cleanup path; __del__ must not duplicate it."""
    df = DataFlow("sqlite:///:memory:")
    await df.close_async()
    assert df._closed is True

    # Second close is a no-op.
    await df.close_async()
    assert df._closed is True

    # GC after explicit close MUST NOT emit ResourceWarning.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        del df
        gc.collect()
    resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert (
        not resource_warnings
    ), f"ResourceWarning emitted after close_async(): {resource_warnings}"
