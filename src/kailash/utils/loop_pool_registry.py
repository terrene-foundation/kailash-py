"""Per-loop connection-pool drain registry (issue #1572).

DataFlow's sync->async bridge (``dataflow.core.async_utils`` — the
``async_safe_run`` / ``_run_in_thread_pool`` path) runs coroutines on a
*transient* event loop that it creates, runs to completion, and closes.
When a coroutine run on such a loop creates an aiomysql / asyncpg
connection pool (a reachability probe in ``MySQLAdapter`` /
``PostgreSQLAdapter``, or the ``EnterpriseConnectionPool`` min-size
connections), the pool's transports are bound to that transient loop.
Once the loop is closed the transports belong to a dead loop and can
never be drained — surfacing at GC time as ``RuntimeError: Event loop
is closed`` and ``ResourceWarning: Unclosed connection`` from
``aiomysql``/``asyncpg`` finalizers, long after ``db.close_async()``
has (correctly) done everything it can.

This module lets the bridge drain those pools *while the transient loop
is still alive*. Pool-creation sites call
:func:`register_pool_drain_on_current_loop` with their pool's async
close method; the bridge calls :func:`drain_loop_pools` inside its
``finally`` block BEFORE cancelling tasks and closing the loop.

Design notes:

* Core kailash owns the marker attribute name
  (:data:`BRIDGE_LOOP_ATTR`) and the registry because ``dataflow`` ->
  ``kailash`` is the only legal import direction. A dataflow adapter
  pool registers DIRECTLY (its ``create_connection_pool`` calls
  :func:`register_pool_drain_on_current_loop`); a core
  :class:`EnterpriseConnectionPool` pool is covered TRANSITIVELY —
  ``EnterpriseConnectionPool.initialize()`` calls its inner
  ``PostgreSQLAdapter`` / ``MySQLAdapter`` ``connect()``, which is the
  registered site. Both therefore flow through this single registry.
* Registration is gated on the marker so pools created on a persistent
  application loop (FastAPI, Jupyter, a user's own ``asyncio.run``) are
  NEVER registered — the registry only ever holds entries for loops the
  bridge itself created and will drain-then-close. This prevents
  unbounded accumulation / a memory leak on long-lived app loops.
* The drain path is strictly best-effort: teardown must never raise.
"""

import asyncio
import logging
import threading
from typing import Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

# Marker attribute stamped by the bridge onto every transient loop it
# creates. Core OWNS this name so dataflow + core agree on the single
# discriminator that says "this loop is bridge-transient; drain its
# pools before close". ``getattr(loop, BRIDGE_LOOP_ATTR, False)``.
BRIDGE_LOOP_ATTR = "_kailash_transient_bridge_loop"

# Per-drain wall-clock bound. A hung/slow adapter ``disconnect()`` must NOT
# block the bridge forever — the pre-fix bare ``asyncio.run`` never awaited a
# pool close, so an unbounded drain would be a NEW hang surface. 5.0s matches
# the pool-lock timeout used by ``async_sql`` (#1572 redteam Round 1).
_DRAIN_TIMEOUT_SECONDS = 5.0

# id(loop) -> list of zero-arg async drain callables (bound pool-close
# methods). Keyed by id() because event loops are not hashable-by-value
# and we only ever look them up while the loop object is alive.
_registry: Dict[int, List[Callable[[], Awaitable[None]]]] = {}
_registry_lock = threading.Lock()


def register_pool_drain_on_current_loop(
    drain: Callable[[], Awaitable[None]],
) -> None:
    """Register ``drain`` to run when the CURRENT loop is torn down.

    Resolves the running loop; if there is no running loop this is a
    silent no-op (nothing to drain against). Registers ``drain`` ONLY
    when the running loop carries the :data:`BRIDGE_LOOP_ATTR` marker —
    i.e. it is a transient loop the bridge created and will drain via
    :func:`drain_loop_pools` before closing. Pools created on a
    persistent app loop are intentionally never registered, so the
    registry cannot accumulate entries on a long-lived loop.

    Args:
        drain: A zero-arg coroutine function that closes the pool (e.g.
            an adapter's bound ``disconnect`` / ``close_connection_pool``
            method). MUST be idempotent — it may be invoked once here and
            again by a later ``cleanup()``/``close_async()``.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — nothing to bind a drain against.
        return

    if not getattr(loop, BRIDGE_LOOP_ATTR, False):
        # Persistent app loop (FastAPI / Jupyter / user asyncio.run):
        # the caller owns teardown; never register (would leak entries).
        return

    with _registry_lock:
        _registry.setdefault(id(loop), []).append(drain)


async def drain_loop_pools(loop: asyncio.AbstractEventLoop) -> None:
    """Drain every pool registered against ``loop`` (best-effort).

    Pops the drain list for ``id(loop)`` under the lock, then awaits
    each drain callable. This runs inside the bridge's ``finally``
    block BEFORE task cancellation and loop close, so connections close
    gracefully while the loop is still alive.

    Best-effort by contract: each ``await drain()`` is bounded by
    :data:`_DRAIN_TIMEOUT_SECONDS` and guarded; on timeout or failure it
    logs at DEBUG and continues. This function NEVER raises — it is
    teardown, and a raise here would crash the bridge worker.

    Security: logs ONLY ``id(loop)`` and counts — never a pool key,
    DSN, connection string, or exception-embedded text (they may carry
    credentials, per ``rules/security.md`` § "No secrets in logs").
    """
    with _registry_lock:
        drains = _registry.pop(id(loop), None)

    if not drains:
        return

    logger.debug(
        "loop_pool_registry.drain.start",
        extra={"loop_id": id(loop), "pool_count": len(drains)},
    )

    drained = 0
    for drain in drains:
        try:
            # Bound each drain so a hung disconnect() can't block the bridge.
            await asyncio.wait_for(drain(), timeout=_DRAIN_TIMEOUT_SECONDS)
            drained += 1
        except asyncio.TimeoutError:
            # Drain exceeded the bound — abandon it and move on; teardown
            # must not hang. Log id(loop) only (no key/DSN).
            logger.debug(
                "loop_pool_registry.drain.timeout",
                extra={"loop_id": id(loop)},
            )
        except Exception as exc:  # noqa: BLE001 — teardown must not raise
            # Guarded per rules/zero-tolerance.md Rule 3 (acceptable
            # teardown except -> logger.debug, never a bare pass). Log the
            # exception TYPE only — never str(exc), which could embed a
            # credential-bearing DSN (rules/security.md, observability 6.3).
            logger.debug(
                "loop_pool_registry.drain.error",
                extra={"loop_id": id(loop), "error_type": type(exc).__name__},
            )

    logger.debug(
        "loop_pool_registry.drain.done",
        extra={"loop_id": id(loop), "drained": drained, "pool_count": len(drains)},
    )


__all__ = [
    "BRIDGE_LOOP_ATTR",
    "register_pool_drain_on_current_loop",
    "drain_loop_pools",
]
