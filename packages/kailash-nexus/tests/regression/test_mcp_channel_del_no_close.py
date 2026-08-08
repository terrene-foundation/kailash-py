# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: ``MCPChannel.__del__`` must not call ``close()``.

Before the fix, ``MCPChannel.__del__`` emitted a ``ResourceWarning`` and then
called ``self.close()`` inside a bare ``try/except Exception: pass``.
``rules/patterns.md`` § "Async Resource Cleanup" BLOCKS exactly this: a
finalizer MUST emit ``ResourceWarning`` and return, because ``__del__`` can
fire from inside Python's logging machinery during GC while the root logging
lock is held by that very thread.

``MCPChannel.close()`` reaches logging and event-loop work on a single but
unavoidable path::

    close() -> self.runtime.release() -> LocalRuntime.close()
      -> logger.debug("Explicit close() called for runtime ...")
      -> LocalRuntime._cleanup_event_loop()
         -> logger.debug / logger.warning
         -> loop.run_until_complete(...) on a persistent event loop
         -> a lazy ``AsyncSQLDatabaseNode`` import (import lock)
         -> loop.close()

Any of those re-enters ``logging`` (or the import lock) from a finalizer that
logging itself may have triggered — the lock-order deadlock recorded as the
2026-04-16 "DataFlow unit suite hangs" incident and fixed for ``DataFlow`` in
issue #1000. ``MCPChannel`` is the THIRD site of that bug class: DataFlow was
swept in #1000, ``Nexus`` in ``test_nexus_del_no_close.py``, and this channel
was left behind.

The ``except Exception: pass`` around the old ``self.close()`` did NOT make it
safe — a deadlock is not an exception. The finalizer blocks forever holding a
lock; nothing is raised and nothing is caught.

The fix: ``__del__`` warns and returns. Real cleanup stays the caller's
responsibility via ``channel.close()`` or ``await channel.stop()``.

Sibling of ``test_nexus_del_no_close.py`` (same bug class, Nexus site) and of
``packages/kailash-dataflow/tests/regression/
test_dataflow_del_no_async_cleanup.py`` (DataFlow site).

Which tests here are EVIDENCE, and which are guards
---------------------------------------------------
Verified against the pre-fix ``__del__`` on ``origin/main``: **2 of the 7 red**.

DISCRIMINATING (red pre-fix, green post-fix) — these carry the proof:

* ``test_del_does_not_invoke_close``
* ``test_del_does_not_release_the_runtime``

NON-DISCRIMINATING (green BOTH pre- and post-fix) — guards, not evidence:

* ``test_del_holds_no_lock_while_a_sibling_thread_logs``
* ``test_del_inside_a_running_loop_does_not_hang``

  The deadlock is NON-DETERMINISTIC: it fires only when GC finalizes the
  object while the root logging lock happens to be held (``rules/patterns.md``
  § "Async Resource Cleanup"). These two cannot reproduce that race on
  demand, so their green says nothing about whether the bug is present. They
  are kept because they WOULD catch a deterministic hang, and because they
  bound the failure to a 10s/5s timeout instead of wedging the suite — but a
  green here MUST NOT be cited as proof the finalizer is safe.

* ``test_unclosed_channel_emits_resource_warning`` /
  ``test_closed_channel_emits_no_resource_warning`` /
  ``test_close_releases_the_runtime``

  These pin behaviour the fix deliberately did NOT change. They exist to
  catch over-correction (deleting the warning, or gutting ``close()`` along
  with the finalizer), so passing both ways is correct for them.
"""

import asyncio
import gc
import threading
import warnings
from unittest.mock import patch

import pytest

from kailash.channels.base import ChannelConfig, ChannelType
from kailash.channels.mcp_channel import MCPChannel
from kailash.runtime.local import LocalRuntime

pytestmark = pytest.mark.regression


class _InertMCPServer:
    """Minimal stand-in so no real MCP server is constructed.

    ``MCPChannel.__init__`` builds one via ``_create_mcp_server()`` when none
    is supplied; these tests are about the finalizer, not the server.
    """

    def run(self) -> None:  # pragma: no cover - never started here
        raise AssertionError("run() must not be invoked by these tests")


def _drain(runtime) -> None:
    """Release every outstanding reference on a deliberately-leaked runtime.

    The finalizer no longer releases anything (that is the whole point of this
    file), so tests that drop an unclosed channel must hand the runtime back
    themselves or the leak bleeds into sibling tests.
    """
    if runtime is None:
        return
    while getattr(runtime, "ref_count", 0) > 0:
        runtime.release()


def _make_channel(runtime=None) -> MCPChannel:
    return MCPChannel(
        config=ChannelConfig(
            name="regression-del-channel",
            channel_type=ChannelType.MCP,
            host="127.0.0.1",
            port=0,
        ),
        mcp_server=_InertMCPServer(),
        runtime=runtime,
    )


class TestDelDoesNotClose:
    """``__del__`` performs zero cleanup work."""

    def test_del_does_not_invoke_close(self):
        """Patch ``close`` to record invocations; the finalizer must not call it."""
        calls: list[str] = []
        real_close = MCPChannel.close

        def _recording_close(self, *args, **kwargs):
            calls.append("close")
            return real_close(self, *args, **kwargs)

        runtime = LocalRuntime()
        channel = _make_channel(runtime=runtime)

        try:
            with patch.object(MCPChannel, "close", _recording_close):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    del channel
                    gc.collect()

            assert calls == [], (
                f"MCPChannel.__del__ called close() {len(calls)} time(s). The "
                "finalizer must emit ResourceWarning and return — close() "
                "reaches LocalRuntime.close() -> _cleanup_event_loop(), which "
                "emits logger.debug/logger.warning and drives "
                "loop.run_until_complete. That deadlocks when __del__ fires "
                "from inside logging during GC. See rules/patterns.md "
                "§ 'Async Resource Cleanup'."
            )
        finally:
            _drain(runtime)

    def test_del_does_not_release_the_runtime(self):
        """Broader invariant: the finalizer releases no reference by any route.

        ``close()`` is not the only banned path — a hand-rolled
        ``self.runtime.release()`` inside ``__del__`` reaches the same
        ``LocalRuntime.close()`` -> ``_cleanup_event_loop()`` logging code.
        Pinning the ref count catches every cleanup route, not just the one
        that goes through ``close()``.
        """
        runtime = LocalRuntime()
        channel = _make_channel(runtime=runtime)
        before = runtime.ref_count
        assert before >= 1

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del channel
                gc.collect()

            assert runtime.ref_count == before, (
                f"ref_count moved {before} -> {runtime.ref_count} after GC. "
                "MCPChannel.__del__ must not release, close, or otherwise "
                "touch the runtime — every release path re-enters logging."
            )
        finally:
            _drain(runtime)

    def test_del_holds_no_lock_while_a_sibling_thread_logs(self):
        """The deadlock shape, exercised directly. NON-DISCRIMINATING guard.

        Passes both pre- and post-fix — see the module docstring. The race
        cannot be forced, so this only catches a DETERMINISTIC hang.

        Finalize an unclosed channel on one thread while another thread is
        actively logging. Pre-fix the finalizer re-entered logging (via
        ``close()`` -> ``LocalRuntime.close()`` -> ``logger.debug``) from a
        context that may already hold the root logging lock. If the finalizer
        ever blocks, this test times out instead of hanging the whole suite.
        """
        import logging

        log = logging.getLogger("regression.del.deadlock")
        stop = threading.Event()
        runtime = LocalRuntime()

        def _chatter():
            while not stop.is_set():
                log.debug("keeping the logging lock warm")

        noise = threading.Thread(target=_chatter, daemon=True, name="log-chatter")
        noise.start()

        finished = threading.Event()

        def _finalize():
            channel = _make_channel(runtime=runtime)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del channel
                gc.collect()
            finished.set()

        worker = threading.Thread(target=_finalize, daemon=True, name="finalizer")
        worker.start()

        try:
            assert finished.wait(timeout=10.0), (
                "Finalizing an unclosed MCPChannel did not complete within 10s "
                "while a sibling thread was logging — the finalizer is doing "
                "cleanup work that re-enters the logging machinery."
            )
        finally:
            stop.set()
            noise.join(timeout=5.0)
            worker.join(timeout=5.0)
            _drain(runtime)

    async def test_del_inside_a_running_loop_does_not_hang(self):
        """Finalize an unclosed channel under a live event loop.

        NON-DISCRIMINATING guard — passes both pre- and post-fix. See the
        module docstring.

        Pre-fix this path could run ``loop.run_until_complete`` on the
        runtime's persistent loop from inside an already-running loop. 5s is
        ~50x the expected runtime.
        """
        runtime = LocalRuntime()

        async def _scenario() -> None:
            channel = _make_channel(runtime=runtime)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del channel
                gc.collect()

        try:
            await asyncio.wait_for(_scenario(), timeout=5.0)
        finally:
            _drain(runtime)


class TestDelResourceWarningContract:
    """Dropping ``close()`` must not drop the user-facing leak signal."""

    def test_unclosed_channel_emits_resource_warning(self):
        runtime = LocalRuntime()
        channel = _make_channel(runtime=runtime)

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                del channel
                gc.collect()

            resource_warnings = [
                w for w in caught if issubclass(w.category, ResourceWarning)
            ]
            assert resource_warnings, (
                "MCPChannel.__del__ must emit ResourceWarning for an unclosed "
                "instance — it is the only remaining signal now that the "
                "(deadlock-prone) close() call is gone."
            )
            assert any("MCPChannel" in str(w.message) for w in resource_warnings), (
                "The ResourceWarning must name MCPChannel so the operator can "
                "find the leaking object; got: "
                f"{[str(w.message) for w in resource_warnings]}"
            )
        finally:
            _drain(runtime)

    def test_closed_channel_emits_no_resource_warning(self):
        """The warning is a leak signal, not noise on every drop."""
        runtime = LocalRuntime()
        channel = _make_channel(runtime=runtime)
        channel.close()

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                del channel
                gc.collect()

            resource_warnings = [
                w for w in caught if issubclass(w.category, ResourceWarning)
            ]
            assert not resource_warnings, (
                "A properly closed MCPChannel must not warn on finalization; "
                f"got: {[str(w.message) for w in resource_warnings]}"
            )
        finally:
            _drain(runtime)


class TestCloseStillCleansUp:
    """Removing cleanup from ``__del__`` must not remove it from ``close()``."""

    def test_close_releases_the_runtime(self):
        runtime = LocalRuntime()
        channel = _make_channel(runtime=runtime)
        before = runtime.ref_count

        try:
            channel.close()

            assert runtime.ref_count == before - 1, (
                f"close() must release exactly one reference; ref_count went "
                f"{before} -> {runtime.ref_count}. The explicit path is the "
                "ONLY cleanup path now that __del__ does nothing."
            )
            assert channel.runtime is None
        finally:
            _drain(runtime)
