# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #2079 / #2081 — pool disposal must not hang.

Every ``disconnect()`` / ``close()`` in ``kailash.nodes.data.async_sql`` used
the same check-await-null shape::

    if self._pool:                 # <- N concurrent callers all pass here
        await self._pool.close()
        self._pool = None

``_shared_pools`` hands ONE adapter to every node on the same DSN + loop, so N
concurrent ``disconnect()`` calls all entered the driver close while the other
N-1 tasks still had queries in flight. For asyncpg that is unrecoverable:
``Pool._check_init`` gates on ``_closed``, which ``Pool.close()`` only sets in
its ``finally``, so ``acquire()`` keeps succeeding for the whole duration of a
close. A holder released past ``wait_until_released()`` is re-acquired by
another task, ``PoolConnectionHolder.close()`` then runs against a connection
with a live query, and the resulting ``await self._con.close()`` waits forever
for a server acknowledgement that can never arrive.

Captured from the hung process, ~10 of these pending simultaneously::

    ---- TASK 'Task-633' done=False ----
      File ".../asyncpg/pool.py", line 268, in close
        await self._con.close()

with the main thread parked in ``selectors.select``. On CI that consumed the
whole 30-minute job budget having executed 3 of 22 tests.

The fix is two-part, and each part is pinned separately below:

  1. CLAIM-THEN-CLOSE — bind the handle to a local and null the attribute
     BEFORE awaiting, so exactly one caller drives the driver close and the
     rest wait on that same disposal.
  2. BOUND THE GRACEFUL CLOSE — escalate to the driver's forced terminate on
     expiry, so a connection already wedged by some other cause cannot park
     the event loop.

Tier 1 (this module's first three tests) is infra-free and deterministic, so
it runs in the every-PR regression gate. Tier 2 reproduces the original
50-concurrent-disposal scenario against a real Postgres.

TIMEOUT MARKERS ARE LOAD-BEARING. Without the fix these tests do not fail —
they HANG. The marker is what converts the hang into a legible failure.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from urllib.parse import urlparse

import pytest

from kailash.nodes.data.async_sql import (
    DatabaseConfig,
    DatabaseType,
    PostgreSQLAdapter,
    set_pool_defaults,
)

# ``_idle_target`` is imported INSIDE its test, deliberately. It is a symbol
# this fix introduces, and a module-level import of it turns a pre-fix run of
# this file into a collection ImportError — which would hide the hang the
# other tests exist to demonstrate behind an unrelated failure.

pytestmark = [pytest.mark.regression]

PG_DSN = os.environ.get(
    "TEST_POSTGRES_DSN",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _pg_reachable(dsn: str) -> bool:
    parsed = urlparse(dsn)
    host, port = parsed.hostname or "localhost", parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Deterministic stand-ins. These are protocol-satisfying objects, NOT mocks:
# they implement the real asyncpg pool surface the adapter calls, and their
# behaviour (a graceful close that never completes) is the exact behaviour a
# protocol-corrupted asyncpg pool exhibits. Nothing is patched or bypassed.
# ---------------------------------------------------------------------------


class _WedgedPool:
    """A pool whose GRACEFUL close never completes — the observed failure.

    Mirrors ``asyncpg.pool.PoolConnectionHolder.close()`` stranded on
    ``await self._con.close()``: the coroutine is entered and then waits on a
    future nothing will ever resolve. ``terminate()`` is the driver's forced,
    non-blocking variant and DOES complete.
    """

    def __init__(self) -> None:
        self.close_calls = 0
        self.terminate_calls = 0
        self.close_entered = asyncio.Event()

    async def close(self) -> None:
        self.close_calls += 1
        self.close_entered.set()
        await asyncio.Event().wait()  # never set — waits forever

    def terminate(self) -> None:
        self.terminate_calls += 1


class _SlowPool:
    """A pool whose graceful close completes, but not instantly."""

    def __init__(self, delay: float = 0.25) -> None:
        self._delay = delay
        self.close_calls = 0
        self.terminate_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        await asyncio.sleep(self._delay)

    def terminate(self) -> None:
        self.terminate_calls += 1


def _adapter_with_pool(pool: object) -> PostgreSQLAdapter:
    """Build a real PostgreSQLAdapter around ``pool`` without connecting."""
    adapter = PostgreSQLAdapter(
        DatabaseConfig(type=DatabaseType.POSTGRESQL, connection_string=PG_DSN)
    )
    adapter._pool = pool
    return adapter


# ---------------------------------------------------------------------------
# Tier 1 — the two halves of the fix, deterministic and infra-free
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
@pytest.mark.asyncio
async def test_disconnect_bounds_a_graceful_close_that_never_completes():
    """A wedged graceful close MUST NOT park the caller forever.

    PRE-FIX: ``await self._pool.close()`` is unbounded, so this test HANGS and
    is killed by the timeout marker. POST-FIX: the close is bounded, the
    driver's ``terminate()`` is the escalation, and ``disconnect()`` returns.

    The default ``close_timeout`` (5 s) is used deliberately rather than
    ``set_pool_defaults(close_timeout=1)``: that keyword is itself part of this
    fix, so calling it would make a pre-fix run fail with a ``TypeError`` about
    the signature INSTEAD of hanging — a different failure, and a much weaker
    demonstration than the hang this test exists to pin.
    """
    pool = _WedgedPool()
    adapter = _adapter_with_pool(pool)

    started = time.monotonic()
    await adapter.disconnect()
    elapsed = time.monotonic() - started

    assert pool.close_calls == 1, "the graceful close must still be attempted first"
    assert pool.terminate_calls == 1, (
        "an expired graceful close MUST escalate to the driver's forced "
        "terminate — otherwise the sockets leak instead of hanging"
    )
    assert elapsed < 20, (
        f"disconnect() took {elapsed:.1f}s against a 5s default close_timeout; "
        "the bound is not being applied"
    )
    assert adapter._pool is None, "the pool handle must be released"


@pytest.mark.timeout(30)
@pytest.mark.asyncio
async def test_concurrent_disconnect_drives_exactly_one_driver_close():
    """N concurrent ``disconnect()`` calls MUST drive ONE ``Pool.close()``.

    This is the root of #2079. Overlapping ``Pool.close()`` calls are what
    corrupt the asyncpg protocol state in the first place, so bounding the
    close without fixing the overlap would only paper over it.

    PRE-FIX: all 50 callers pass the ``if self._pool:`` guard and
    ``close_calls == 50``. POST-FIX: the first caller claims the handle and
    ``close_calls == 1``.
    """
    pool = _SlowPool(delay=0.25)
    adapter = _adapter_with_pool(pool)

    await asyncio.gather(*(adapter.disconnect() for _ in range(50)))

    assert pool.close_calls == 1, (
        f"{pool.close_calls} concurrent driver closes were started; claim-"
        "then-close is not in effect and the overlap that corrupts the "
        "asyncpg protocol state is still reachable"
    )
    assert pool.terminate_calls == 0, "a healthy close must not escalate"
    assert adapter._pool is None


@pytest.mark.timeout(30)
@pytest.mark.asyncio
async def test_losing_disconnect_waits_for_the_winner_to_finish():
    """``disconnect()`` stays a drain BARRIER for every caller, not just one.

    The bridge teardown in ``kailash.utils.loop_pool_registry`` closes the
    event loop as soon as its drain callables return, so a caller that returned
    while the real close was still in flight would resurrect the #1572
    "Unclosed connection" class. Single-flight MUST therefore mean "one close,
    N waiters" — never "one close, N early returns".
    """
    pool = _SlowPool(delay=0.5)
    adapter = _adapter_with_pool(pool)

    winner = asyncio.create_task(adapter.disconnect())
    await asyncio.sleep(0.05)  # let the winner claim the handle
    loser_started = time.monotonic()
    await adapter.disconnect()
    loser_elapsed = time.monotonic() - loser_started

    await winner
    assert pool.close_calls == 1
    assert loser_elapsed >= 0.2, (
        f"the losing caller returned after {loser_elapsed:.3f}s while the "
        "winner's close was still running — disconnect() is no longer a "
        "barrier and the bridge may close the loop underneath it (#1572)"
    )


@pytest.mark.timeout(30)
def test_idle_reaper_resolves_the_idle_clock_through_the_adapter():
    """The DPI-B3 idle reaper MUST be able to see a registered adapter's clock.

    ``_PROCESS_POOL_REGISTRY`` stores ADAPTERS, but ``is_idle()`` lives on
    ``EnterpriseConnectionPool``. The reaper tested ``hasattr(entry,
    "is_idle")`` directly, which is False for every adapter the registry can
    contain — so it walked the registry and skipped 100% of it. The reaper ran,
    reaped nothing, and reported nothing.
    """
    from kailash.nodes.data.async_sql import _idle_target

    class _Clock:
        def is_idle(self, now=None) -> bool:
            return True

    class _AdapterWithEnterprisePool:
        def __init__(self) -> None:
            self._enterprise_pool = _Clock()

    entry = _AdapterWithEnterprisePool()
    assert not hasattr(entry, "is_idle"), (
        "precondition: a registered adapter does NOT expose is_idle directly "
        "— that is exactly why the direct hasattr() check reaped nothing"
    )
    assert _idle_target(entry) is entry._enterprise_pool

    # A bare object with no reachable clock is still skipped, not crashed on.
    assert _idle_target(object()) is None

    # An object carrying the clock itself resolves to itself.
    clock = _Clock()
    assert _idle_target(clock) is clock


# ---------------------------------------------------------------------------
# Tier 2 — the original scenario against a real Postgres
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
@pytest.mark.requires_postgres
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _pg_reachable(PG_DSN), reason=f"Postgres unreachable at {PG_DSN}"
)
async def test_fifty_concurrent_disposals_against_real_postgres_complete():
    """The #2079 reproduction: 50 shared-adapter disposals must terminate.

    This is ``test_issue_697_pool_leak.py::
    test_pool_count_stays_bounded_under_lock_contention``'s teardown shape,
    isolated. Pre-fix it hung indefinitely against a real Postgres on Linux
    (killed at 120s by pytest-timeout); post-fix it completes in under a
    second.
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    set_pool_defaults(max_pool_count_per_process=10, idle_timeout=300)

    async def _one_query(i: int) -> None:
        node = AsyncSQLDatabaseNode(
            name=f"issue_2079_q_{i}",
            database_type="postgresql",
            connection_string=PG_DSN,
            query="SELECT 1 AS n",
            validate_queries=False,
        )
        try:
            await node.async_run()
        finally:
            # Every task disposes the SHARED adapter — the exact overlap.
            if node._adapter is not None:
                await node._adapter.disconnect()

    started = time.monotonic()
    await asyncio.gather(*(_one_query(i) for i in range(50)), return_exceptions=True)
    elapsed = time.monotonic() - started

    assert elapsed < 60, (
        f"50 concurrent disposals took {elapsed:.1f}s; pre-fix this never "
        "returned at all"
    )
    assert AsyncSQLDatabaseNode.pool_count() <= 10
