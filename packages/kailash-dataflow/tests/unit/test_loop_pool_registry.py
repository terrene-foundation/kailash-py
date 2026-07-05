# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the per-loop pool drain registry (issue #1572).

The registry lives in core kailash (``kailash.utils.loop_pool_registry``)
because ``dataflow`` -> ``kailash`` is the only legal import direction. A
dataflow adapter pool registers DIRECTLY; a core ``EnterpriseConnectionPool``
pool is covered TRANSITIVELY via its inner adapter's ``connect()`` (both flow
through this one registry). These are Tier-1 unit tests of the registry
contract — no database, no infrastructure; the end-to-end bridge-drain
behavior against real MySQL/PG is exercised by
``tests/integration/test_issue_1572_bridge_loop_pool_drain.py``.
"""

import asyncio
import time

import pytest

from kailash.utils.loop_pool_registry import (
    _DRAIN_TIMEOUT_SECONDS,
    BRIDGE_LOOP_ATTR,
    _registry,
    drain_loop_pools,
    register_pool_drain_on_current_loop,
)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_register_is_noop_without_bridge_marker():
    """A running loop that LACKS the marker must not accumulate registrations.

    This is the memory-leak defense: pools created on a persistent app loop
    (FastAPI / Jupyter / a user's own asyncio.run) are never registered, so
    the registry cannot grow on a long-lived loop.
    """
    loop = asyncio.get_running_loop()
    assert not getattr(loop, BRIDGE_LOOP_ATTR, False)

    async def _drain():
        pass  # pragma: no cover — must never be registered/invoked

    register_pool_drain_on_current_loop(_drain)

    assert id(loop) not in _registry


@pytest.mark.regression
@pytest.mark.asyncio
async def test_register_and_drain_invokes_and_pops_when_marked():
    """A marked loop registers the drain, drain_loop_pools runs it, then pops."""
    loop = asyncio.get_running_loop()
    setattr(loop, BRIDGE_LOOP_ATTR, True)
    try:
        calls = []

        async def _drain():
            calls.append("drained")

        register_pool_drain_on_current_loop(_drain)
        assert id(loop) in _registry
        assert len(_registry[id(loop)]) == 1

        await drain_loop_pools(loop)

        # Drain callable invoked exactly once...
        assert calls == ["drained"]
        # ...and the entry popped (so a dead id(loop) is never retained).
        assert id(loop) not in _registry
    finally:
        # Leave no marker/entry behind for sibling tests sharing this loop.
        _registry.pop(id(loop), None)
        delattr(loop, BRIDGE_LOOP_ATTR)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_drain_never_raises_when_a_drain_callable_raises():
    """Best-effort teardown: a raising drain is logged at DEBUG, never propagated.

    A raise out of drain_loop_pools would crash the bridge worker in its
    finally block. All registered drains must be attempted even if one raises.
    """
    loop = asyncio.get_running_loop()
    setattr(loop, BRIDGE_LOOP_ATTR, True)
    try:
        calls = []

        async def _boom():
            calls.append("boom")
            raise RuntimeError("pool close failed")

        async def _ok():
            calls.append("ok")

        register_pool_drain_on_current_loop(_boom)
        register_pool_drain_on_current_loop(_ok)

        # Must NOT raise despite _boom raising.
        await drain_loop_pools(loop)

        # Both drains attempted (the raise did not abort the loop over drains).
        assert calls == ["boom", "ok"]
        assert id(loop) not in _registry
    finally:
        _registry.pop(id(loop), None)
        delattr(loop, BRIDGE_LOOP_ATTR)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_drain_bounds_a_slow_callable_by_timeout():
    """A drain that hangs > _DRAIN_TIMEOUT_SECONDS is bounded, not awaited forever.

    #1572 redteam Round 1: an unbounded drain of a hung disconnect() would be a
    NEW hang surface (pre-fix bare asyncio.run never awaited pool close). The
    drain MUST return in ~timeout, MUST NOT raise, and MUST still run siblings.
    """
    loop = asyncio.get_running_loop()
    setattr(loop, BRIDGE_LOOP_ATTR, True)
    try:
        calls = []

        async def _hangs():
            calls.append("hang_started")
            # Sleep well past the drain bound; wait_for must cancel this.
            await asyncio.sleep(_DRAIN_TIMEOUT_SECONDS + 30)
            calls.append("hang_finished")  # pragma: no cover — cancelled first

        async def _ok():
            calls.append("ok")

        register_pool_drain_on_current_loop(_hangs)
        register_pool_drain_on_current_loop(_ok)

        # Patch the module constant to a tiny bound so the test is fast, then
        # assert the drain returns within a small multiple of it.
        import kailash.utils.loop_pool_registry as registry_mod

        original = registry_mod._DRAIN_TIMEOUT_SECONDS
        registry_mod._DRAIN_TIMEOUT_SECONDS = 0.05
        try:
            started = time.monotonic()
            await drain_loop_pools(loop)  # must NOT hang, must NOT raise
            elapsed = time.monotonic() - started
        finally:
            registry_mod._DRAIN_TIMEOUT_SECONDS = original

        # Returned in ~timeout, nowhere near the 30s sleep.
        assert elapsed < 5.0
        # The hung drain started but was cut off; the sibling still ran.
        assert "hang_started" in calls
        assert "hang_finished" not in calls
        assert "ok" in calls
        assert id(loop) not in _registry
    finally:
        _registry.pop(id(loop), None)
        delattr(loop, BRIDGE_LOOP_ATTR)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_drain_unknown_loop_is_noop():
    """drain_loop_pools on a loop with no registrations returns cleanly."""
    loop = asyncio.get_running_loop()
    # No marker, no registration.
    await drain_loop_pools(loop)  # must not raise
    assert id(loop) not in _registry


@pytest.mark.regression
def test_register_without_running_loop_is_silent_noop():
    """No running loop -> silent no-op (nothing to bind a drain against)."""

    async def _drain():
        pass  # pragma: no cover

    # Called from sync context: asyncio.get_running_loop() raises RuntimeError,
    # which the helper swallows silently.
    register_pool_drain_on_current_loop(_drain)  # must not raise
