# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #1002 — DataFlow.close() / close_async() MUST close
EVERY cached runtime, not only `self.runtime`.

Per ``workspaces/issue-1002-aiosqlite-fixture-cleanup/journal/0006-DISCOVERY-...md``
and commit ``e79fca27``: the `runtime` property resolves to ONE runtime for the
calling context (override OR per-loop AsyncLocalRuntime OR sync singleton). An
instance can hold all three concurrently if it has been accessed from a sync
context, an async-loop A, and via the `_runtime_override` setter. Pre-fix,
`close()` / `close_async()` only closed `self.runtime` — the other two leaked
LocalRuntime references kept aiosqlite background threads alive at
``_Py_Finalize`` time, producing the post-pytest-summary hang.

This test exercises the cache-clearing contract directly: prime all three
runtime caches with recording stubs, run close() / close_async(), assert (a)
each cached runtime had close() invoked, AND (b) all three caches are emptied.

Tier 1 — no real database. Protocol-Satisfying stubs per
``rules/testing.md`` § "3-Tier Testing" carve-out (deterministic adapter
satisfying the `runtime.close()` shape, not a mock).
"""

from __future__ import annotations

from typing import cast

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

from dataflow import DataFlow

pytestmark = [pytest.mark.regression]


class _RecordingRuntime:
    """Protocol-satisfying recording stub matching ``LocalRuntime.close()``
    and ``AsyncLocalRuntime.close()`` shape (both are synchronous on the
    Kailash runtime surface — see ``src/kailash/runtime/*.py``)."""

    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


def _prime_all_runtime_caches(
    db: DataFlow,
) -> tuple[_RecordingRuntime, _RecordingRuntime, _RecordingRuntime]:
    """Prime ``_runtime_override`` + one ``_loop_runtime_cache`` entry +
    ``_sync_runtime_singleton`` with distinct recording stubs. Returns the
    three stubs so the caller can assert close() invocation."""
    override = _RecordingRuntime()
    per_loop = _RecordingRuntime()
    sync_singleton = _RecordingRuntime()

    # Protocol-Satisfying-Adapter cast per rules/testing.md § "Protocol Adapters":
    # the engine's cleanup loop only invokes .close(), which all three stubs
    # implement. cast() makes the structural-typing contract explicit for
    # pyright without forcing a nominal-type inheritance.
    db._runtime_override = cast(LocalRuntime, override)
    # _loop_runtime_cache is keyed by loop-id (int); use a sentinel int.
    if not hasattr(db, "_loop_runtime_cache") or db._loop_runtime_cache is None:
        db._loop_runtime_cache = {}
    db._loop_runtime_cache[0] = cast(AsyncLocalRuntime, per_loop)
    db._sync_runtime_singleton = cast(LocalRuntime, sync_singleton)

    return override, per_loop, sync_singleton


def test_sync_close_releases_all_cached_runtimes() -> None:
    """``DataFlow.close()`` MUST close every cached runtime AND clear all
    three caches. Pre-fix, only ``self.runtime`` was closed — leaking the
    other two cached references."""
    db = DataFlow(":memory:", auto_migrate=False)
    try:
        override, per_loop, sync_singleton = _prime_all_runtime_caches(db)

        assert override.close_count == 0
        assert per_loop.close_count == 0
        assert sync_singleton.close_count == 0

        db.close()

        assert (
            override.close_count >= 1
        ), "sync close() did not close _runtime_override — issue #1002 regressed"
        assert (
            per_loop.close_count >= 1
        ), "sync close() did not close _loop_runtime_cache entry — issue #1002 regressed"
        assert (
            sync_singleton.close_count >= 1
        ), "sync close() did not close _sync_runtime_singleton — issue #1002 regressed"
        assert db._runtime_override is None
        assert db._loop_runtime_cache == {}
        assert db._sync_runtime_singleton is None
    finally:
        if not db._closed:
            db.close()


@pytest.mark.asyncio
async def test_async_close_releases_all_cached_runtimes() -> None:
    """``DataFlow.close_async()`` MUST also close every cached runtime —
    parity with the sync ``close()`` fix is the structural defense per
    ``rules/patterns.md`` § "Paired Public Surface — Consistent Async-ness"."""
    db = DataFlow(":memory:", auto_migrate=False)
    try:
        override, per_loop, sync_singleton = _prime_all_runtime_caches(db)

        await db.close_async()

        assert override.close_count >= 1
        assert per_loop.close_count >= 1
        assert sync_singleton.close_count >= 1
        assert db._runtime_override is None
        assert db._loop_runtime_cache == {}
        assert db._sync_runtime_singleton is None
    finally:
        if not db._closed:
            db.close()


def test_sync_close_tolerates_runtime_close_failure_and_still_clears_caches() -> None:
    """Per the fix's per-runtime ``try/except: logger.debug``, one runtime
    raising in close() MUST NOT block the others, AND all three caches
    MUST still be emptied."""

    class _FailingRuntime:
        def close(self) -> None:
            raise RuntimeError("simulated runtime close failure")

    good_override = _RecordingRuntime()
    bad_loop = _FailingRuntime()
    good_sync = _RecordingRuntime()

    db = DataFlow(":memory:", auto_migrate=False)
    try:
        db._runtime_override = cast(LocalRuntime, good_override)
        db._loop_runtime_cache = {0: cast(AsyncLocalRuntime, bad_loop)}
        db._sync_runtime_singleton = cast(LocalRuntime, good_sync)

        db.close()  # MUST NOT raise

        assert (
            good_override.close_count == 1
        ), "sibling cleanup blocked by failing runtime"
        assert good_sync.close_count == 1, "sibling cleanup blocked by failing runtime"
        assert db._runtime_override is None
        assert db._loop_runtime_cache == {}
        assert db._sync_runtime_singleton is None
    finally:
        if not db._closed:
            db.close()
