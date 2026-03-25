# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for runtime lifecycle management (M1-001, M1-002, M1-003).

Tests reference counting, async close cleanup, and async context manager
for LocalRuntime and AsyncLocalRuntime.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


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

    def test_thread_safety(self):
        rt = LocalRuntime()
        errors = []

        def acquire_release():
            try:
                for _ in range(100):
                    rt.acquire()
                for _ in range(100):
                    rt.release()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=acquire_release) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert rt.ref_count == 1  # Only original ref remains
        rt.close()

    def test_del_forces_cleanup(self):
        """__del__ on unclosed runtime forces cleanup and emits ResourceWarning."""
        import warnings

        rt = LocalRuntime()
        rt._ensure_event_loop()
        assert rt._persistent_loop is not None
        assert rt.ref_count == 1

        # Call __del__ directly to test its behavior deterministically.
        # In production, __del__ is called by the garbage collector.
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt.__del__()

        # Verify ResourceWarning was emitted
        resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
        assert len(resource_warnings) == 1
        assert "Unclosed LocalRuntime" in str(resource_warnings[0].message)

        # Verify cleanup actually happened
        assert rt._persistent_loop is None
        assert rt.ref_count == 0

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


class TestAsyncClose:
    """M1-002: AsyncLocalRuntime.close() cleans up all resources."""

    def test_close_cleans_up_thread_pool(self):
        rt = AsyncLocalRuntime()
        assert rt.thread_pool is not None
        rt.close()
        # After close, thread_pool should be None (cleaned by async cleanup or sync fallback)
        assert rt.thread_pool is None

    def test_close_clears_semaphore(self):
        rt = AsyncLocalRuntime()
        # Directly set the semaphore to simulate it having been created
        # (normally created lazily in async context via execution_semaphore property)
        rt._semaphore = asyncio.Semaphore(10)
        assert rt._semaphore is not None
        rt.close()
        assert rt._semaphore is None

    def test_close_is_idempotent(self):
        rt = AsyncLocalRuntime()
        rt.close()
        rt.close()  # Should not raise

    def test_close_respects_ref_count(self):
        rt = AsyncLocalRuntime()
        rt.acquire()  # ref_count = 2
        rt.close()  # ref_count = 1, no cleanup
        assert rt.ref_count == 1
        # Thread pool should still exist
        assert rt.thread_pool is not None
        rt.close()  # ref_count = 0, actual cleanup

    def test_close_cleans_event_loop(self):
        rt = AsyncLocalRuntime()
        rt._ensure_event_loop()
        assert rt._persistent_loop is not None
        rt.close()
        assert rt._persistent_loop is None

    def test_del_forces_cleanup(self):
        """AsyncLocalRuntime __del__ emits ResourceWarning and forces cleanup."""
        import warnings

        rt = AsyncLocalRuntime()
        rt._ensure_event_loop()
        assert rt._persistent_loop is not None
        assert rt.ref_count == 1

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rt.__del__()

        resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
        assert len(resource_warnings) == 1
        assert "Unclosed AsyncLocalRuntime" in str(resource_warnings[0].message)

        # Verify cleanup happened
        assert rt._persistent_loop is None
        assert rt.ref_count == 0

    def test_inherits_acquire_release(self):
        """AsyncLocalRuntime inherits acquire/release from LocalRuntime."""
        rt = AsyncLocalRuntime()
        assert rt.ref_count == 1
        result = rt.acquire()
        assert result is rt
        assert rt.ref_count == 2
        rt.release()
        assert rt.ref_count == 1
        rt.close()


class TestAsyncContextManager:
    """M1-003: AsyncLocalRuntime async context manager."""

    def test_async_with_works(self):
        async def _test():
            async with AsyncLocalRuntime() as rt:
                assert rt is not None
                assert rt._is_context_managed

        asyncio.run(_test())

    def test_async_with_cleans_up(self):
        async def _test():
            async with AsyncLocalRuntime() as rt:
                pass
            return rt

        rt = asyncio.run(_test())
        assert rt._cleaned_up or rt._persistent_loop is None

    def test_async_with_cleans_thread_pool(self):
        async def _test():
            async with AsyncLocalRuntime() as rt:
                assert rt.thread_pool is not None
            return rt

        rt = asyncio.run(_test())
        assert rt.thread_pool is None

    def test_async_with_does_not_interfere_with_sync_context_manager(self):
        """Sync context manager (inherited from LocalRuntime) still works."""
        with LocalRuntime() as rt:
            assert rt._is_context_managed
            assert rt.ref_count == 1
        # After exit, cleaned up
        assert rt._persistent_loop is None

    def test_async_with_resets_context_managed_flag(self):
        async def _test():
            rt = AsyncLocalRuntime()
            async with rt:
                assert rt._is_context_managed
            assert not rt._is_context_managed
            return rt

        rt = asyncio.run(_test())
        assert not rt._is_context_managed
