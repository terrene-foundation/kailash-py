# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for LocalRuntime lifecycle management (M1-001).

Tests reference counting and context manager for LocalRuntime.
AsyncLocalRuntime tests moved to tests/tier2_integration/runtime/test_runtime_lifecycle_async.py.
"""

from __future__ import annotations

import pytest

from kailash.runtime.local import LocalRuntime


class TestRefCounting:
    """M1-001: Reference counting in LocalRuntime."""

    def test_initial_ref_count_is_one(self):
        with LocalRuntime() as rt:
            assert rt.ref_count == 1

    def test_acquire_increments(self):
        with LocalRuntime() as rt:
            rt.acquire()
            assert rt.ref_count == 2
            rt.release()  # Clean up the extra ref

    def test_acquire_returns_self(self):
        with LocalRuntime() as rt:
            result = rt.acquire()
            assert result is rt
            rt.release()

    def test_close_decrements_without_cleanup_when_refs_remain(self):
        rt = LocalRuntime()
        rt._ensure_event_loop()  # Force event loop creation
        rt.acquire()  # ref_count = 2
        rt.close()  # ref_count = 1, no cleanup
        assert rt.ref_count == 1
        # Runtime should still be usable — event loop intact
        assert rt._persistent_loop is not None
        rt.close()  # ref_count = 0, actual cleanup

    def test_close_at_zero_triggers_cleanup(self):
        rt = LocalRuntime()
        rt._ensure_event_loop()  # Force event loop creation
        assert rt._persistent_loop is not None
        rt.close()
        assert rt._persistent_loop is None

    def test_acquire_on_closed_raises(self):
        rt = LocalRuntime()
        rt.close()
        with pytest.raises(RuntimeError, match="Cannot acquire a closed runtime"):
            rt.acquire()

    def test_release_is_close_alias(self):
        rt = LocalRuntime()
        rt.acquire()  # ref_count = 2
        rt.release()  # ref_count = 1
        assert rt.ref_count == 1
        rt.close()  # final cleanup

    def test_del_warns_and_performs_no_cleanup(self):
        """__del__ on an unclosed runtime WARNS and returns; it cleans up nothing.

        Renamed from ``test_del_forces_cleanup`` (issue #2107). The old name and
        its final two assertions pinned the exact behaviour ``rules/patterns.md``
        § "Async Resource Cleanup" BLOCKS: forcing ``close()`` from a finalizer.
        ``close()`` emits ``logger.debug``, takes ``self._loop_lock`` and drives
        ``_cleanup_event_loop()`` -- and a finalizer fires at an arbitrary
        bytecode boundary on whichever thread drops the last reference, so it can
        re-enter the root logging lock or ``_loop_lock``. Neither is reentrant,
        so the process deadlocks.

        The ResourceWarning half of the old contract is unchanged and still
        asserted below; only the forced-cleanup half is inverted.
        """
        import warnings

        rt = LocalRuntime()
        rt._ensure_event_loop()
        assert rt._persistent_loop is not None
        assert rt.ref_count == 1

        try:
            # Call __del__ directly to test its behavior deterministically.
            # In production, __del__ is called by the garbage collector.
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                rt.__del__()

            # The leak signal is preserved -- it is now the ONLY thing __del__ does.
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 1
            assert "Unclosed LocalRuntime" in str(resource_warnings[0].message)

            # And nothing was cleaned up: that is the deadlock fix, not a leak.
            # The event loop is released deterministically by close()/__exit__.
            assert rt._persistent_loop is not None, (
                "__del__ must not tear down the event loop: _cleanup_event_loop() "
                "logs and runs loop.run_until_complete, which deadlocks when the "
                "finalizer fires from inside logging during GC (issue #2107)."
            )
            assert rt.ref_count == 1, (
                "__del__ must not decrement the ref count -- every release path "
                "reaches the logging-and-lock code above (issue #2107)."
            )
        finally:
            rt.close()

    def test_context_manager_close_at_ref_one(self):
        """Context manager exit calls close(), which should fully clean up at ref_count=1."""
        rt = None
        with LocalRuntime() as runtime:
            runtime._ensure_event_loop()
            rt = runtime
        # After with-block, close() was called, ref_count should be 0
        assert rt.ref_count == 0
        assert rt._persistent_loop is None

    def test_multiple_acquires_and_releases(self):
        rt = LocalRuntime()
        rt.acquire()  # 2
        rt.acquire()  # 3
        rt.acquire()  # 4
        assert rt.ref_count == 4
        rt.release()  # 3
        rt.release()  # 2
        rt.release()  # 1
        assert rt.ref_count == 1
        rt.close()  # 0, cleanup

    def test_close_idempotent_after_zero(self):
        """Calling close() multiple times after ref_count reaches 0 should not raise."""
        rt = LocalRuntime()
        rt.close()  # ref_count = 0
        rt.close()  # Already at 0, should be safe no-op
        rt.close()  # Still safe
