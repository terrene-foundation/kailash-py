# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 integration tests for AsyncLocalRuntime lifecycle management (M1-002, M1-003).

Moved from tests/unit/runtime/test_runtime_lifecycle.py because these tests
instantiate AsyncLocalRuntime (creates thread pools) and use asyncio.run()
which can conflict with pytest-asyncio event loops in CI.
"""

from __future__ import annotations

import asyncio

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime


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
