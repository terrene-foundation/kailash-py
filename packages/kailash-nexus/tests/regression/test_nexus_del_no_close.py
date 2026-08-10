# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: ``Nexus.__del__`` must not call ``close()``.

Before the fix, ``Nexus.__del__`` emitted a ``ResourceWarning`` and then called
``self.close()``. ``rules/patterns.md`` § "Async Resource Cleanup" BLOCKS
exactly this: a finalizer MUST emit ``ResourceWarning`` and return, because
``__del__`` can fire from inside Python's logging machinery during GC while the
root logging lock is held by that very thread.

``Nexus.close()`` reaches logging and event-loop work on at least three
branches:

* ``WebSocketTransport.close()`` → ``logger.info("WebSocketTransport stopped")``
  (``nexus/transports/websocket.py``) — a direct log emission;
* the gateway branch: ``EnterpriseWorkflowServer.close()`` →
  ``WorkflowServer.close()`` → ``logger.debug("Error closing WorkflowAPI …")``;
* ``self.runtime.release()`` → ``LocalRuntime.close()`` →
  ``LocalRuntime._cleanup_event_loop()``, which emits ``logger.debug`` /
  ``logger.warning``, drives ``loop.run_until_complete(...)`` on a persistent
  event loop, and lazily ``import``s ``AsyncSQLDatabaseNode`` (import lock)
  before ``loop.close()``.

Any of those re-enters ``logging`` (or the import lock) from a finalizer that
logging itself may have triggered — the lock-order deadlock recorded as the
2026-04-16 "DataFlow unit suite hangs" incident and fixed for ``DataFlow`` in
issue #1000. ``Nexus`` was the un-swept sibling site of the same bug class.

The fix: ``__del__`` warns and returns. Real cleanup stays the caller's
responsibility via ``app.close()``, ``app.stop()``, or
``with Nexus(...) as app:``.

Sibling of ``packages/kailash-dataflow/tests/regression/
test_dataflow_del_no_async_cleanup.py`` (same bug class, DataFlow site) and of
``test_issue_1285_close_cascades_runtime.py`` (which pins what ``close()``
itself must release).
"""

from __future__ import annotations

import asyncio
import gc
import warnings
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.regression


def _drain(runtime) -> None:
    """Release every outstanding reference on a deliberately-leaked runtime.

    The finalizer no longer releases anything (that is the whole point of this
    file), so tests that drop an unclosed Nexus must hand the runtime back
    themselves or the leak bleeds into sibling tests.
    """
    if runtime is None:
        return
    while getattr(runtime, "ref_count", 0) > 0:
        runtime.release()


class TestDelDoesNotClose:
    """``__del__`` performs zero cleanup work."""

    def test_del_does_not_invoke_close(self):
        """Patch ``close`` to record invocations; the finalizer must not call it."""
        from nexus import Nexus

        calls: list[str] = []
        real_close = Nexus.close

        def _recording_close(self, *args, **kwargs):
            calls.append("close")
            return real_close(self, *args, **kwargs)

        app = Nexus(api_port=20191, mcp_port=20192, enable_durability=False)
        runtime = app.runtime

        try:
            with patch.object(Nexus, "close", _recording_close):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    del app
                    gc.collect()

            assert calls == [], (
                f"Nexus.__del__ called close() {len(calls)} time(s). The "
                "finalizer must emit ResourceWarning and return — close() "
                "reaches logger.info/logger.debug and loop.run_until_complete, "
                "which deadlocks when __del__ fires from inside logging during "
                "GC. See rules/patterns.md § 'Async Resource Cleanup'."
            )
        finally:
            _drain(runtime)

    def test_del_does_not_release_the_runtime(self):
        """Broader invariant: the finalizer releases no reference by any route.

        ``close()`` is not the only banned path — a hand-rolled
        ``self.runtime.release()`` inside ``__del__`` reaches the same
        ``LocalRuntime.close()`` → ``_cleanup_event_loop()`` logging/event-loop
        code. Pinning the ref count catches every cleanup route, not just the
        one that goes through ``close()``.
        """
        from nexus import Nexus

        app = Nexus(api_port=20193, mcp_port=20194, enable_durability=False)
        runtime = app.runtime
        before = runtime.ref_count
        assert before >= 1

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del app
                gc.collect()

            assert runtime.ref_count == before, (
                f"ref_count moved {before} -> {runtime.ref_count} after GC. "
                "Nexus.__del__ must not release, close, or otherwise touch the "
                "shared runtime — every release path re-enters logging."
            )
        finally:
            _drain(runtime)

    async def test_del_inside_a_running_loop_does_not_hang(self):
        """The deadlock scenario: finalize an unclosed Nexus under a live loop.

        Before the fix this path ran ``loop.run_until_complete`` on the
        runtime's persistent loop from inside an already-running loop. 5s is
        ~50x the expected runtime.
        """
        from nexus import Nexus

        holder: dict[str, object] = {}

        async def _scenario() -> None:
            app = Nexus(api_port=20195, mcp_port=20196, enable_durability=False)
            holder["runtime"] = app.runtime
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del app
                gc.collect()

        try:
            await asyncio.wait_for(_scenario(), timeout=5.0)
        finally:
            _drain(holder.get("runtime"))


class TestDelResourceWarningContract:
    """Dropping ``close()`` must not drop the user-facing leak signal."""

    def test_unclosed_nexus_emits_resource_warning(self):
        from nexus import Nexus

        app = Nexus(api_port=20197, mcp_port=20198, enable_durability=False)
        runtime = app.runtime

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                del app
                gc.collect()

            resource_warnings = [
                w for w in caught if issubclass(w.category, ResourceWarning)
            ]
            assert resource_warnings, (
                "Nexus.__del__ must emit ResourceWarning for an unclosed "
                "instance — it is the only remaining signal now that the "
                "(deadlock-prone) close() call is gone."
            )
            message = str(resource_warnings[0].message)
            assert "Unclosed Nexus" in message
            # The warning MUST name a cleanup entry point that actually exists.
            assert "close()" in message
            assert hasattr(Nexus, "close")
            assert hasattr(Nexus, "__enter__") and hasattr(Nexus, "__exit__")
        finally:
            _drain(runtime)

    def test_closed_nexus_emits_no_resource_warning(self):
        """``close()`` clears ``runtime``, so the finalizer stays silent."""
        from nexus import Nexus

        app = Nexus(api_port=20199, mcp_port=20200, enable_durability=False)
        app.close()
        assert app.runtime is None

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            del app
            gc.collect()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert (
            not resource_warnings
        ), f"ResourceWarning emitted after close(): {resource_warnings}"

    def test_context_manager_exit_closes(self):
        """``with Nexus(...) as app:`` is a real cleanup path the warning names."""
        from nexus import Nexus

        with Nexus(api_port=20201, mcp_port=20202, enable_durability=False) as app:
            assert app.runtime is not None
        assert app.runtime is None


class TestDelOnPartiallyConstructedInstance:
    """Class-level defaults keep the finalizer safe when ``__init__`` never ran."""

    def test_del_on_uninitialised_instance_does_not_raise(self):
        """``Nexus.__new__`` skips ``__init__`` — the shape a raising ctor leaves.

        Without the class-level ``runtime = None`` default this raises
        ``AttributeError`` inside GC, which CPython can only print as
        "Exception ignored in: <function Nexus.__del__>" — masking the real
        constructor failure.
        """
        from nexus import Nexus

        assert Nexus.runtime is None, (
            "Nexus must declare a class-level `runtime` default so __del__ is "
            "safe on a partially-constructed instance."
        )

        app = Nexus.__new__(Nexus)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            app.__del__()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert not resource_warnings, (
            "A Nexus whose __init__ never ran holds no runtime and must not "
            f"warn about leaking one: {resource_warnings}"
        )
