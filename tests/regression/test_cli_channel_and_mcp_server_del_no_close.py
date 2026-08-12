# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression pins: ``CLIChannel.__del__`` and ``MiddlewareMCPServer.__del__``
must not call ``close()``.

These are the last two sites of the finalizer bug class. Before the fix both
emitted a ``ResourceWarning`` and then called ``self.close()`` inside a bare
``try/except Exception: pass``. ``rules/patterns.md`` § "Async Resource
Cleanup" BLOCKS exactly this: a finalizer MUST emit ``ResourceWarning`` and
return, because ``__del__`` can fire from inside Python's logging machinery
during GC while the root logging lock is held by that very thread.

Both ``close()`` methods reach logging on the same path::

    close() -> self.runtime.release() -> LocalRuntime.close()
      -> logger.debug("Explicit close() called for runtime ...")
      -> LocalRuntime._cleanup_event_loop()
         -> logger.debug / logger.warning
         -> loop.run_until_complete(...) on a persistent event loop
         -> loop.close()

The ``except Exception: pass`` did NOT make it safe -- a deadlock is not an
exception. The finalizer blocks forever holding a lock; nothing is raised and
nothing is caught.

Sibling of ``packages/kailash-nexus/tests/regression/
test_mcp_channel_del_no_close.py`` (MCPChannel site),
``test_nexus_del_no_close.py`` (Nexus site) and
``packages/kailash-dataflow/tests/regression/
test_dataflow_del_no_async_cleanup.py`` (DataFlow site, issue #1000). Every
prior site in this class carries a pin; these two shipped without one, which
is the gap this file closes.

Which tests here are EVIDENCE, and which are guards
---------------------------------------------------
Verified against the pre-fix ``__del__`` bodies (``git stash`` of the fix):
the four ``TestDelDoesNot*`` cases RED, the rest pass both ways.

DISCRIMINATING (red pre-fix, green post-fix) -- these carry the proof:

* ``test_cli_channel_del_does_not_invoke_close``
* ``test_cli_channel_del_does_not_release_the_runtime``
* ``test_mcp_server_del_does_not_invoke_close``
* ``test_mcp_server_del_does_not_release_the_runtime``

NON-DISCRIMINATING (green BOTH pre- and post-fix) -- guards, not evidence:

* ``test_del_holds_no_lock_while_a_sibling_thread_logs``

  The deadlock is NON-DETERMINISTIC: it fires only when GC finalizes the
  object while the root logging lock happens to be held. This cannot
  reproduce that race on demand, so its green says nothing about whether the
  bug is present. It is kept because it WOULD catch a deterministic hang, and
  because it bounds the failure to a 10s timeout instead of wedging the
  suite -- but a green here MUST NOT be cited as proof the finalizer is safe.

* the ``ResourceWarning`` contract tests and ``test_close_still_releases_*``

  These pin behaviour the fix deliberately did NOT change. They exist to
  catch over-correction (deleting the warning, or gutting ``close()`` along
  with the finalizer), so passing both ways is correct for them.
"""

from __future__ import annotations

import gc
import threading
import warnings
from unittest.mock import patch

import pytest

from kailash.channels.base import ChannelConfig, ChannelType
from kailash.channels.cli_channel import CLIChannel
from kailash.middleware.mcp.enhanced_server import MiddlewareMCPServer
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

pytestmark = pytest.mark.regression


def _drain(runtime) -> None:
    """Release every outstanding reference on a deliberately-leaked runtime.

    The finalizer no longer releases anything (that is the whole point of this
    file), so tests that drop an unclosed object must hand the runtime back
    themselves or the leak bleeds into sibling tests.
    """
    if runtime is None:
        return
    while getattr(runtime, "ref_count", 0) > 0:
        runtime.release()


def _cli_channel(runtime=None) -> CLIChannel:
    return CLIChannel(
        config=ChannelConfig(
            name="regression-del-cli",
            channel_type=ChannelType.CLI,
        ),
        runtime=runtime,
    )


def _mcp_server(runtime=None) -> MiddlewareMCPServer:
    return MiddlewareMCPServer(runtime=runtime)


class TestCLIChannelDelDoesNotClose:
    """``CLIChannel.__del__`` performs zero cleanup work."""

    def test_cli_channel_del_does_not_invoke_close(self):
        """Patch ``close`` to record invocations; the finalizer must not call it."""
        calls: list[str] = []
        real_close = CLIChannel.close

        def _recording_close(self, *args, **kwargs):
            calls.append("close")
            return real_close(self, *args, **kwargs)

        runtime = AsyncLocalRuntime()
        channel = _cli_channel(runtime=runtime)

        try:
            with patch.object(CLIChannel, "close", _recording_close):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    del channel
                    gc.collect()

            assert calls == [], (
                f"CLIChannel.__del__ called close() {len(calls)} time(s). The "
                "finalizer must emit ResourceWarning and return -- close() "
                "reaches runtime.release() -> _cleanup_event_loop(), which "
                "emits logger.debug/logger.warning and drives "
                "loop.run_until_complete. That deadlocks when __del__ fires "
                "from inside logging during GC. See rules/patterns.md "
                "§ 'Async Resource Cleanup'."
            )
        finally:
            _drain(runtime)

    def test_cli_channel_del_does_not_release_the_runtime(self):
        """Broader invariant: the finalizer releases no reference by any route.

        ``close()`` is not the only banned path -- a hand-rolled
        ``self.runtime.release()`` inside ``__del__`` reaches the same
        ``_cleanup_event_loop()`` logging code. Pinning the ref count catches
        every cleanup route, not just the one that goes through ``close()``.
        """
        runtime = AsyncLocalRuntime()
        channel = _cli_channel(runtime=runtime)
        before = runtime.ref_count
        assert before >= 1

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del channel
                gc.collect()

            assert runtime.ref_count == before, (
                f"ref_count moved {before} -> {runtime.ref_count} after GC. "
                "CLIChannel.__del__ must not release, close, or otherwise "
                "touch the runtime -- every release path re-enters logging."
            )
        finally:
            _drain(runtime)

    def test_del_holds_no_lock_while_a_sibling_thread_logs(self):
        """The deadlock shape, exercised directly. NON-DISCRIMINATING guard.

        Passes both pre- and post-fix -- see the module docstring. The race
        cannot be forced, so this only catches a DETERMINISTIC hang. If the
        finalizer ever blocks, this times out instead of wedging the suite.
        """
        import logging

        log = logging.getLogger("regression.del.deadlock.cli")
        stop = threading.Event()
        runtime = AsyncLocalRuntime()

        def _chatter():
            while not stop.is_set():
                log.debug("keeping the logging lock warm")

        noise = threading.Thread(target=_chatter, daemon=True, name="log-chatter")
        noise.start()

        finished = threading.Event()

        def _finalize():
            channel = _cli_channel(runtime=runtime)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del channel
                gc.collect()
            finished.set()

        worker = threading.Thread(target=_finalize, daemon=True, name="finalizer")
        worker.start()

        try:
            assert finished.wait(timeout=10.0), (
                "Finalizing an unclosed CLIChannel did not complete within 10s "
                "while a sibling thread was logging -- the finalizer is doing "
                "cleanup work that re-enters the logging machinery."
            )
        finally:
            stop.set()
            noise.join(timeout=5.0)
            worker.join(timeout=5.0)
            _drain(runtime)


class TestMiddlewareMCPServerDelDoesNotClose:
    """``MiddlewareMCPServer.__del__`` performs zero cleanup work.

    The server the MCP channel drives, and the un-swept sibling of the
    channel's own finalizer.
    """

    def test_mcp_server_del_does_not_invoke_close(self):
        calls: list[str] = []
        real_close = MiddlewareMCPServer.close

        def _recording_close(self, *args, **kwargs):
            calls.append("close")
            return real_close(self, *args, **kwargs)

        runtime = LocalRuntime()
        server = _mcp_server(runtime=runtime)

        try:
            with patch.object(MiddlewareMCPServer, "close", _recording_close):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    del server
                    gc.collect()

            assert calls == [], (
                f"MiddlewareMCPServer.__del__ called close() {len(calls)} "
                "time(s). The finalizer must emit ResourceWarning and return "
                "-- close() reaches LocalRuntime.close() -> "
                "_cleanup_event_loop(), which emits logger.debug/"
                "logger.warning. That deadlocks when __del__ fires from "
                "inside logging during GC. See rules/patterns.md § 'Async "
                "Resource Cleanup'."
            )
        finally:
            _drain(runtime)

    def test_mcp_server_del_does_not_release_the_runtime(self):
        runtime = LocalRuntime()
        server = _mcp_server(runtime=runtime)
        before = runtime.ref_count
        assert before >= 1

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                del server
                gc.collect()

            assert runtime.ref_count == before, (
                f"ref_count moved {before} -> {runtime.ref_count} after GC. "
                "MiddlewareMCPServer.__del__ must not release, close, or "
                "otherwise touch the runtime -- every release path re-enters "
                "logging."
            )
        finally:
            _drain(runtime)


class TestDelResourceWarningContract:
    """Dropping ``close()`` must not drop the user-facing leak signal."""

    def test_unclosed_cli_channel_emits_resource_warning(self):
        runtime = AsyncLocalRuntime()
        channel = _cli_channel(runtime=runtime)

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                del channel
                gc.collect()

            resource_warnings = [
                w for w in caught if issubclass(w.category, ResourceWarning)
            ]
            assert resource_warnings, (
                "CLIChannel.__del__ must emit ResourceWarning for an unclosed "
                "instance -- it is the only remaining signal now that the "
                "(deadlock-prone) close() call is gone."
            )
            assert any("CLIChannel" in str(w.message) for w in resource_warnings), (
                "The ResourceWarning must name CLIChannel so the operator can "
                "find the leaking object; got: "
                f"{[str(w.message) for w in resource_warnings]}"
            )
        finally:
            _drain(runtime)

    def test_closed_cli_channel_emits_no_resource_warning(self):
        """The warning is a leak signal, not noise on every drop."""
        runtime = AsyncLocalRuntime()
        channel = _cli_channel(runtime=runtime)
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
                "A properly closed CLIChannel must not warn on finalization; "
                f"got: {[str(w.message) for w in resource_warnings]}"
            )
        finally:
            _drain(runtime)

    def test_unclosed_mcp_server_emits_resource_warning(self):
        runtime = LocalRuntime()
        server = _mcp_server(runtime=runtime)

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                del server
                gc.collect()

            resource_warnings = [
                w for w in caught if issubclass(w.category, ResourceWarning)
            ]
            assert resource_warnings, (
                "MiddlewareMCPServer.__del__ must emit ResourceWarning for an "
                "unclosed instance -- it is the only remaining signal now "
                "that the (deadlock-prone) close() call is gone."
            )
            assert any(
                "MiddlewareMCPServer" in str(w.message) for w in resource_warnings
            ), (
                "The ResourceWarning must name MiddlewareMCPServer so the "
                "operator can find the leaking object; got: "
                f"{[str(w.message) for w in resource_warnings]}"
            )
        finally:
            _drain(runtime)


class TestCloseStillCleansUp:
    """Removing cleanup from ``__del__`` must not remove it from ``close()``."""

    def test_close_still_releases_the_cli_channel_runtime(self):
        runtime = AsyncLocalRuntime()
        channel = _cli_channel(runtime=runtime)
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

    def test_close_still_releases_the_mcp_server_runtime(self):
        runtime = LocalRuntime()
        server = _mcp_server(runtime=runtime)
        before = runtime.ref_count

        try:
            server.close()

            assert runtime.ref_count == before - 1, (
                f"close() must release exactly one reference; ref_count went "
                f"{before} -> {runtime.ref_count}. The explicit path is the "
                "ONLY cleanup path now that __del__ does nothing."
            )
            assert server.runtime is None
        finally:
            _drain(runtime)
