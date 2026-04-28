"""Unit tests for the EnterpriseConnectionPool idle-timeout reaper (DPI-B3 / #698).

Tier 1 — fakes the pool object via a duck-typed stub satisfying the
``is_idle()`` / ``close()`` protocol the reaper expects. Exercises the
reaper's idle-detection + reap-from-registry path against time-warped
inputs (no real sleep). The Tier 2 regression that exercises the reaper
against real PostgreSQL pools lives in
``tests/regression/test_issue_697_pool_leak.py``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from kailash.nodes.data.async_sql import (
    _POOL_DEFAULTS,
    _PROCESS_POOL_REGISTRY,
    _REAPER_TASKS,
    AsyncSQLDatabaseNode,
    EnterpriseConnectionPool,
    _ensure_reaper_started,
    _idle_pool_reaper_loop,
    set_pool_defaults,
)


class _ReapablePoolStub:
    """Duck-typed stub satisfying the reaper's pool protocol.

    Per ``rules/testing.md`` § Tier 1 — Protocol-Satisfying Deterministic
    Adapters: this is a ``typing.Protocol``-satisfying stub, not a mock.
    The reaper iterates ``is_idle(now)`` and ``await close()``; the stub
    implements both deterministically.
    """

    def __init__(self, name: str, idle: bool = True) -> None:
        self.name = name
        self._idle = idle
        self._reaped_count = 0
        self.closed = False

    def is_idle(self, now: float) -> bool:
        return self._idle

    async def close(self) -> None:
        self.closed = True


def test_idle_timeout_property_reads_pool_defaults_when_no_override(monkeypatch):
    """idle_timeout property reflects the current process default."""
    pool = EnterpriseConnectionPool(
        pool_id="t1",
        database_config=None,  # type: ignore[arg-type]
        adapter_class=type,
        enable_analytics=False,
    )
    set_pool_defaults(idle_timeout=42)
    assert pool.idle_timeout == 42


def test_idle_timeout_property_uses_constructor_override():
    """Per-pool idle_timeout override takes precedence over process default."""
    pool = EnterpriseConnectionPool(
        pool_id="t2",
        database_config=None,  # type: ignore[arg-type]
        adapter_class=type,
        enable_analytics=False,
        idle_timeout=15,
    )
    assert pool.idle_timeout == 15
    set_pool_defaults(idle_timeout=999)
    # Override pinned — does NOT follow the process default
    assert pool.idle_timeout == 15


def test_is_idle_false_on_fresh_pool():
    """Freshly-created pool is not idle (constructor seeds last_activity)."""
    pool = EnterpriseConnectionPool(
        pool_id="t3",
        database_config=None,  # type: ignore[arg-type]
        adapter_class=type,
        enable_analytics=False,
        idle_timeout=10,
    )
    # last_activity_at = time.monotonic() at __init__ — call now to compare
    assert pool.is_idle() is False


def test_is_idle_true_when_now_exceeds_last_activity_plus_timeout():
    """is_idle becomes True once last_activity drifts past idle_timeout."""
    pool = EnterpriseConnectionPool(
        pool_id="t4",
        database_config=None,  # type: ignore[arg-type]
        adapter_class=type,
        enable_analytics=False,
        idle_timeout=2,
    )
    # Force last_activity to "5 seconds ago" — exceeds 2-second timeout
    pool._last_activity_at = time.monotonic() - 5
    assert pool.is_idle() is True


def test_is_idle_false_when_within_timeout_window():
    """is_idle is False while now - last_activity < timeout."""
    pool = EnterpriseConnectionPool(
        pool_id="t5",
        database_config=None,  # type: ignore[arg-type]
        adapter_class=type,
        enable_analytics=False,
        idle_timeout=10,
    )
    # last_activity = 3s ago, timeout = 10s → not yet idle
    pool._last_activity_at = time.monotonic() - 3
    assert pool.is_idle() is False


@pytest.mark.asyncio
async def test_reaper_closes_idle_pool_and_removes_from_registry():
    """One iteration: idle pool is closed and dropped from registry."""
    set_pool_defaults(idle_timeout=4)  # interval = 1s
    pool = _ReapablePoolStub("idle_one", idle=True)
    _PROCESS_POOL_REGISTRY["idle_one"] = pool
    assert AsyncSQLDatabaseNode.pool_count() == 1

    _ensure_reaper_started()
    # Sleep just past one reaper interval.
    await asyncio.sleep(1.5)

    assert pool.closed is True
    assert "idle_one" not in _PROCESS_POOL_REGISTRY
    assert pool._reaped_count == 1


@pytest.mark.asyncio
async def test_reaper_does_not_close_active_pool():
    """A pool whose is_idle() returns False survives the reaper."""
    set_pool_defaults(idle_timeout=4)
    pool = _ReapablePoolStub("active_one", idle=False)
    _PROCESS_POOL_REGISTRY["active_one"] = pool

    _ensure_reaper_started()
    await asyncio.sleep(1.5)

    assert pool.closed is False
    assert "active_one" in _PROCESS_POOL_REGISTRY


@pytest.mark.asyncio
async def test_reaper_one_task_per_event_loop_idempotent():
    """Calling _ensure_reaper_started twice in same loop yields one task."""
    _ensure_reaper_started()
    first_task = _REAPER_TASKS[id(asyncio.get_running_loop())]
    _ensure_reaper_started()
    second_task = _REAPER_TASKS[id(asyncio.get_running_loop())]
    assert first_task is second_task


@pytest.mark.asyncio
async def test_reaper_survives_pool_close_error():
    """A pool whose close() raises does NOT kill the reaper."""

    class _BrokenCloseStub:
        def __init__(self) -> None:
            self._reaped_count = 0

        def is_idle(self, now: float) -> bool:
            return True

        async def close(self) -> None:
            raise RuntimeError("simulated close failure")

    set_pool_defaults(idle_timeout=4)
    broken = _BrokenCloseStub()
    healthy = _ReapablePoolStub("healthy", idle=True)
    _PROCESS_POOL_REGISTRY["broken"] = broken
    _PROCESS_POOL_REGISTRY["healthy"] = healthy

    _ensure_reaper_started()
    await asyncio.sleep(1.5)

    # Reaper survived → healthy pool was reaped despite broken pool's failure
    assert healthy.closed is True
    assert "healthy" not in _PROCESS_POOL_REGISTRY
    assert broken  # pin


@pytest.mark.asyncio
async def test_reaper_cancellation_exits_cleanly():
    """Cancelling the reaper task surfaces no error to other awaiters."""
    _ensure_reaper_started()
    task = _REAPER_TASKS[id(asyncio.get_running_loop())]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
