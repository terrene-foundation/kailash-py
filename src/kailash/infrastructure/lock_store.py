# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DistributedLock / Lease primitive with interchangeable backends.

A distributed lock lets N workers across N hosts agree that exactly one of
them holds a named resource for a bounded time (a *lease*).  The lease can be
lost mid-critical-section — a GC pause, a clock skew, a network partition, or
an expiry-then-steal by another worker — on **any** backend.  Mutual exclusion
by TTL alone is therefore NOT safe (the classic Kleppmann critique of
TTL-only locks).

The load-bearing safety mechanism is the **fencing token**: a strictly
monotonic per-key integer that ``acquire`` returns and that ``release`` /
``extend`` verify.  A correctly-built protected resource records the highest
fencing token it has observed and rejects any write carrying a token ``<=``
that high-water mark.  So even if two workers briefly believe they hold the
same lock, only the one with the higher token can mutate the resource — the
fence, not the TTL, provides correctness.

Fence-check pattern at the protected resource::

    lease = await lock.acquire("invoice-42", ttl_seconds=30)
    if lease is None:
        return  # contention — someone else holds it
    # ... do work ...
    # When writing to the protected resource, carry lease.fencing_token and
    # let the resource reject a token <= the highest it has seen:
    await resource.write(data, fencing_token=lease.fencing_token)
    await lock.release(lease)

Architecture (one seam, two backends behind it):

* :class:`Lease` — frozen value object: ``key``, ``owner`` (uuid4 hex,
  unique per acquire), ``fencing_token`` (int, strictly monotonic per key,
  never reset), ``expires_at`` (ISO-8601 UTC).
* :class:`LockBackend` — the abstract seam.  ``try_acquire`` returns a
  fencing token on success or ``None`` on contention; ``release`` / ``extend``
  verify ``owner`` + ``token``; ``reap_expired`` reclaims expired rows;
  ``close`` releases resources.
* :class:`DBLockBackend` — dialect-portable SQL backend via
  :class:`~kailash.db.connection.ConnectionManager` (SQLite at Level 0,
  PostgreSQL at Level 1+), mirroring
  :class:`~kailash.infrastructure.idempotency_store.DBIdempotencyStore`.
* :class:`RedisLockBackend` — single-instance Redis backend (lives in
  :mod:`kailash.infrastructure.lock_store_redis`, behind the ``[redis]``
  extra).
* :class:`DistributedLock` — backend-agnostic facade owning the
  ``acquire`` / ``release`` / ``extend`` API and the ``lease`` async
  contextmanager.

All SQL uses canonical ``?`` placeholders; ConnectionManager translates to
the target database dialect automatically.

Tables (``DBLockBackend``):

* ``kailash_locks`` — the live lock rows::

      key            TEXT PRIMARY KEY
      owner          TEXT NOT NULL
      fencing_token  BIGINT NOT NULL
      expires_at     TEXT NOT NULL          -- ISO-8601 UTC

* ``kailash_lock_fence`` — the per-key monotonic fence counter, kept distinct
  from ``kailash_locks`` so the token survives lock churn (release / expiry /
  steal) and is therefore **strictly increasing and never reset**::

      key    TEXT PRIMARY KEY
      token  BIGINT NOT NULL
"""

from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "Lease",
    "LockBackend",
    "DBLockBackend",
    "DistributedLock",
    "LockAcquireError",
]

# Table-name validation — table names cannot be parameterized in SQL, so a
# constructor-time allowlist is the only defense against injection through a
# dynamic table name (rules/infrastructure-sql.md § 6).
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Lease — the value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Lease:
    """An acquired distributed lock.

    Frozen value object: the database (or Redis) row is the canonical state;
    a ``Lease`` instance is an immutable snapshot of a successful acquire.

    Attributes
    ----------
    key:
        The logical resource name this lease covers.
    owner:
        A uuid4 hex string unique to THIS acquire.  ``release`` / ``extend``
        verify ``owner`` so a worker can never release or extend a lease it
        does not hold (e.g. one stolen after expiry).
    fencing_token:
        A strictly-monotonic-per-key integer.  Never reset — not across
        release, expiry, or steal.  This is the load-bearing safety value:
        the protected resource rejects any write whose token is ``<=`` the
        highest it has observed (see module docstring).
    expires_at:
        ISO-8601 UTC timestamp at which the lease becomes stealable.
    """

    key: str
    owner: str
    fencing_token: int
    expires_at: str


# ---------------------------------------------------------------------------
# LockBackend — the abstract seam
# ---------------------------------------------------------------------------
@runtime_checkable
class LockBackend(Protocol):
    """The interchangeable lock-backend contract.

    Implementations are backend-specific (SQL, Redis); the
    :class:`DistributedLock` facade depends only on this Protocol so a backend
    can be swapped without touching caller code.
    """

    async def try_acquire(
        self, key: str, owner: str, ttl_seconds: int
    ) -> Optional[int]:
        """Attempt to acquire ``key`` for ``owner`` for ``ttl_seconds``.

        Succeeds when the key is free OR the existing lease has expired
        (steal-if-expired).  On success returns the strictly-monotonic
        fencing token for this acquire; on contention returns ``None``.
        """
        ...

    async def release(self, key: str, owner: str, token: int) -> bool:
        """Release the lock for ``key`` iff held by ``owner`` at ``token``.

        Returns ``True`` if a matching row was deleted, ``False`` if the lease
        was already lost (different owner / token, or expired-and-stolen).
        """
        ...

    async def extend(self, key: str, owner: str, token: int, ttl_seconds: int) -> bool:
        """Extend the lease TTL iff still held by ``owner`` at ``token``.

        Returns ``True`` if the TTL was extended, ``False`` if the lease was
        already lost.
        """
        ...

    async def reap_expired(self, before: Optional[str] = None) -> int:
        """Delete expired lock rows; return the number reaped.

        ``before`` is an ISO-8601 UTC threshold (default: now).  The fence
        counter is intentionally NOT touched — reaping a lock must never
        reset its fencing token.
        """
        ...

    async def close(self) -> None:
        """Release any backend resources (does not close shared connections)."""
        ...


# ---------------------------------------------------------------------------
# DBLockBackend — dialect-portable SQL backend
# ---------------------------------------------------------------------------
class DBLockBackend:
    """SQL-backed :class:`LockBackend` via :class:`ConnectionManager`.

    Works on SQLite (Level 0) and PostgreSQL / MySQL (Level 1+).  Mirrors
    :class:`~kailash.infrastructure.idempotency_store.DBIdempotencyStore`:
    atomic claim-with-TTL, ``expires_at`` column, dialect-portable DDL via
    ``dialect.text_column(indexed=True)``, ``reap_expired`` analogous to
    ``cleanup``.

    Atomicity of acquire (steal-if-expired) is provided by a single
    ``conn.transaction()`` block — ``BEGIN IMMEDIATE`` serializes writers on
    SQLite, and the same SELECT-then-write inside one transaction is
    serializable on PostgreSQL / MySQL.  The fencing token is bumped in the
    SAME transaction via the companion ``kailash_lock_fence`` row, so it is
    strictly monotonic per key on every dialect — no reliance on
    RETURNING-on-conflict, which older SQLite lacks.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance (shared, owned by
        the caller / StoreFactory).
    table_name:
        Name of the live-locks table (default ``kailash_locks``).  Validated
        against ``[a-zA-Z_][a-zA-Z0-9_]*`` at construction time.
    fence_table_name:
        Name of the per-key fence-counter table (default
        ``kailash_lock_fence``).  Same validation.
    """

    def __init__(
        self,
        conn_manager: ConnectionManager,
        table_name: str = "kailash_locks",
        fence_table_name: str = "kailash_lock_fence",
        *,
        owns_connection: bool = False,
    ) -> None:
        if not _TABLE_NAME_RE.match(table_name):
            raise ValueError(f"Invalid table name: must match {_TABLE_NAME_RE.pattern}")
        if not _TABLE_NAME_RE.match(fence_table_name):
            raise ValueError(
                f"Invalid fence table name: must match {_TABLE_NAME_RE.pattern}"
            )
        self._conn = conn_manager
        self._table = table_name
        self._fence_table = fence_table_name
        self._initialized = False
        # When True, this backend owns the ConnectionManager (built privately
        # for a Level-0 lock store) and MUST close it on close().  When False
        # (the default), the ConnectionManager is shared via StoreFactory and
        # is owned by the caller — closing it here would break sibling stores.
        self._owns_connection = owns_connection

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the lock + fence tables and the expiry index if absent.

        Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, the dynamic
        table names route through ``dialect.quote_identifier()`` (validates +
        quotes) for the DDL interpolation.  Safe to call multiple times.
        """
        if self._initialized:
            return

        _tc = self._conn.dialect.text_column(indexed=True)
        quoted_locks = self._conn.dialect.quote_identifier(self._table)
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {quoted_locks} (
                key {_tc} PRIMARY KEY,
                owner TEXT NOT NULL,
                fencing_token BIGINT NOT NULL,
                expires_at {_tc} NOT NULL
            )
            """
        )
        await self._conn.create_index(
            f"idx_{self._table}_expires",
            self._table,
            "expires_at",
        )

        quoted_fence = self._conn.dialect.quote_identifier(self._fence_table)
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {quoted_fence} (
                key {_tc} PRIMARY KEY,
                token BIGINT NOT NULL
            )
            """
        )

        self._initialized = True
        logger.info(
            "DBLockBackend tables '%s' / '%s' initialized",
            self._table,
            self._fence_table,
        )

    async def close(self) -> None:
        """Release backend resources.

        When the backend was built with a SHARED ConnectionManager
        (``owns_connection=False``, the default), the connection is owned by
        the caller / StoreFactory and is NOT closed here — closing it would
        break sibling stores.  When the backend OWNS a private connection
        (``owns_connection=True``, the Level-0 lock-store path), that
        connection IS closed here so no aiosqlite worker thread is left
        running.
        """
        if self._owns_connection and self._conn is not None:
            await self._conn.close()
        logger.debug("DBLockBackend backend closed")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    async def _bump_fence(self, tx: Any, key: str) -> int:
        """Bump and return the per-key fence counter inside transaction ``tx``.

        The fence row lives in a separate table from the live lock so the
        token survives lock churn — it is strictly increasing and is NEVER
        reset on release / expiry / steal.  ``max(existing, 0) + 1`` is
        computed in Python and written back atomically within the caller's
        transaction (so two concurrent acquires of the same key cannot read
        the same value: the BEGIN IMMEDIATE / serializable transaction
        serializes them).
        """
        row = await tx.fetchone(
            f"SELECT token FROM {self._fence_table} WHERE key = ?",
            key,
        )
        if row is None:
            next_token = 1
            await tx.execute(
                f"INSERT INTO {self._fence_table} (key, token) VALUES (?, ?)",
                key,
                next_token,
            )
        else:
            next_token = int(row["token"]) + 1
            await tx.execute(
                f"UPDATE {self._fence_table} SET token = ? WHERE key = ?",
                next_token,
                key,
            )
        return next_token

    async def try_acquire(
        self, key: str, owner: str, ttl_seconds: int
    ) -> Optional[int]:
        """Acquire ``key`` for ``owner``, stealing an expired lease if present.

        Returns the new fencing token on success, ``None`` on contention.

        The whole operation runs in ONE transaction so the read of the
        current lock row, the fence bump, and the write of the new lock row
        are atomic — no TOCTOU race between checking expiry and writing.
        """
        now = _utcnow()
        now_iso = _iso(now)
        expires_at = _iso(now + timedelta(seconds=ttl_seconds))

        async with self._conn.transaction() as tx:
            existing = await tx.fetchone(
                f"SELECT owner, expires_at FROM {self._table} WHERE key = ?",
                key,
            )

            if existing is not None and existing["expires_at"] > now_iso:
                # Held and not yet expired — contention.
                return None

            token = await self._bump_fence(tx, key)

            if existing is None:
                await tx.execute(
                    f"INSERT INTO {self._table} "
                    "(key, owner, fencing_token, expires_at) VALUES (?, ?, ?, ?)",
                    key,
                    owner,
                    token,
                    expires_at,
                )
            else:
                # Steal the expired lease.
                await tx.execute(
                    f"UPDATE {self._table} SET owner = ?, fencing_token = ?, "
                    "expires_at = ? WHERE key = ?",
                    owner,
                    token,
                    expires_at,
                    key,
                )

        logger.debug(
            "lock.acquire key=%s owner=%s token=%d ttl=%ds",
            key,
            owner,
            token,
            ttl_seconds,
        )
        return token

    async def release(self, key: str, owner: str, token: int) -> bool:
        """Release the lock iff still held by ``owner`` at ``token``.

        Gated on ``key + owner + fencing_token`` so a stale lease (lost to
        expiry-then-steal) cannot release the new holder's lock.
        """
        async with self._conn.transaction() as tx:
            before = await tx.fetchone(
                f"SELECT 1 AS hit FROM {self._table} "
                "WHERE key = ? AND owner = ? AND fencing_token = ?",
                key,
                owner,
                token,
            )
            if before is None:
                logger.debug(
                    "lock.release.lost key=%s owner=%s token=%d", key, owner, token
                )
                return False
            await tx.execute(
                f"DELETE FROM {self._table} "
                "WHERE key = ? AND owner = ? AND fencing_token = ?",
                key,
                owner,
                token,
            )
        logger.debug("lock.release key=%s owner=%s token=%d", key, owner, token)
        return True

    async def extend(self, key: str, owner: str, token: int, ttl_seconds: int) -> bool:
        """Extend the lease TTL iff still held by ``owner`` at ``token``.

        Returns ``True`` if extended, ``False`` if the lease was already lost.
        """
        new_expires = _iso(_utcnow() + timedelta(seconds=ttl_seconds))
        async with self._conn.transaction() as tx:
            current = await tx.fetchone(
                f"SELECT 1 AS hit FROM {self._table} "
                "WHERE key = ? AND owner = ? AND fencing_token = ?",
                key,
                owner,
                token,
            )
            if current is None:
                logger.debug(
                    "lock.extend.lost key=%s owner=%s token=%d", key, owner, token
                )
                return False
            await tx.execute(
                f"UPDATE {self._table} SET expires_at = ? "
                "WHERE key = ? AND owner = ? AND fencing_token = ?",
                new_expires,
                key,
                owner,
                token,
            )
        logger.debug(
            "lock.extend key=%s owner=%s token=%d ttl=%ds",
            key,
            owner,
            token,
            ttl_seconds,
        )
        return True

    async def reap_expired(self, before: Optional[str] = None) -> int:
        """Delete expired lock rows; return the count reaped.

        Mirrors ``DBIdempotencyStore.cleanup``.  The companion fence rows are
        intentionally left intact so a reaped-then-reacquired key keeps a
        strictly-increasing token.
        """
        if before is None:
            before = _iso(_utcnow())

        # Count first so the return value is dialect-portable (asyncpg's
        # execute() returns a status string, not a rowcount int).
        rows = await self._conn.fetch(
            f"SELECT key FROM {self._table} WHERE expires_at < ?",
            before,
        )
        reaped = len(rows)
        if reaped:
            await self._conn.execute(
                f"DELETE FROM {self._table} WHERE expires_at < ?",
                before,
            )
            logger.info("lock.reap removed %d expired lock(s)", reaped)
        return reaped


# ---------------------------------------------------------------------------
# DistributedLock — the backend-agnostic facade
# ---------------------------------------------------------------------------
class DistributedLock:
    """Backend-agnostic distributed lock facade.

    Wraps any :class:`LockBackend` and owns the user-facing API:

    * :meth:`acquire` — non-blocking by default; optional bounded
      blocking-with-backoff via ``blocking=True`` + ``timeout``.
    * :meth:`release` / :meth:`extend` — verify owner + fencing token.
    * :meth:`lease` — an ``async with`` contextmanager that acquires on entry
      and ALWAYS releases on exit (normal OR exception).

    Parameters
    ----------
    backend:
        Any object satisfying the :class:`LockBackend` Protocol.
    default_ttl_seconds:
        TTL used by :meth:`lease` when none is passed (default 30).
    poll_interval:
        Initial backoff (seconds) for a blocking :meth:`acquire` (default
        0.05).  Backoff doubles each miss up to ``max_poll_interval``.
    max_poll_interval:
        Upper bound on the blocking-acquire backoff (default 1.0).
    """

    def __init__(
        self,
        backend: LockBackend,
        *,
        default_ttl_seconds: int = 30,
        poll_interval: float = 0.05,
        max_poll_interval: float = 1.0,
    ) -> None:
        self._backend = backend
        self._default_ttl = default_ttl_seconds
        self._poll_interval = poll_interval
        self._max_poll_interval = max_poll_interval

    @property
    def backend(self) -> LockBackend:
        """The wrapped backend (for advanced callers / introspection)."""
        return self._backend

    async def acquire(
        self,
        key: str,
        ttl_seconds: Optional[int] = None,
        *,
        blocking: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[Lease]:
        """Acquire ``key`` and return a :class:`Lease`, or ``None`` on failure.

        Each acquire mints a fresh ``owner`` (uuid4 hex) so the returned lease
        can be verified on release / extend.

        Parameters
        ----------
        key:
            The resource name to lock.
        ttl_seconds:
            Lease lifetime (default: ``default_ttl_seconds``).
        blocking:
            When ``False`` (default), return ``None`` immediately on
            contention.  When ``True``, poll with exponential backoff until
            the lock is acquired OR ``timeout`` elapses.
        timeout:
            Maximum seconds to block when ``blocking=True``.  ``None`` means
            block indefinitely.  Ignored when ``blocking=False``.

        Returns
        -------
        Lease or None
            The acquired lease, or ``None`` if contended (non-blocking) or
            the timeout elapsed (blocking).
        """
        import asyncio

        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        owner = uuid.uuid4().hex

        token = await self._backend.try_acquire(key, owner, ttl)
        if token is not None:
            return self._lease_from(key, owner, token, ttl)

        if not blocking:
            return None

        loop = asyncio.get_event_loop()
        deadline = None if timeout is None else loop.time() + timeout
        backoff = self._poll_interval
        while True:
            if deadline is not None and loop.time() >= deadline:
                return None
            # Sleep without overrunning the deadline.
            sleep_for = backoff
            if deadline is not None:
                sleep_for = min(sleep_for, max(0.0, deadline - loop.time()))
            await asyncio.sleep(sleep_for)

            # Fresh owner each retry: an earlier attempt never "owns" anything
            # since it returned None, but minting a new owner keeps every
            # successful acquire's owner unique.
            owner = uuid.uuid4().hex
            token = await self._backend.try_acquire(key, owner, ttl)
            if token is not None:
                return self._lease_from(key, owner, token, ttl)
            backoff = min(backoff * 2, self._max_poll_interval)

    def _lease_from(self, key: str, owner: str, token: int, ttl: int) -> Lease:
        expires_at = _iso(_utcnow() + timedelta(seconds=ttl))
        return Lease(key=key, owner=owner, fencing_token=token, expires_at=expires_at)

    async def release(self, lease: Lease) -> bool:
        """Release ``lease`` iff still held; return ``True`` on success."""
        return await self._backend.release(lease.key, lease.owner, lease.fencing_token)

    async def extend(
        self, lease: Lease, ttl_seconds: Optional[int] = None
    ) -> Optional[Lease]:
        """Extend ``lease`` and return a refreshed lease, or ``None`` if lost.

        The returned lease carries the SAME ``fencing_token`` — extending a
        held lease does not change the fence (it is the same critical
        section), only the ``expires_at``.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        ok = await self._backend.extend(
            lease.key, lease.owner, lease.fencing_token, ttl
        )
        if not ok:
            return None
        expires_at = _iso(_utcnow() + timedelta(seconds=ttl))
        return Lease(
            key=lease.key,
            owner=lease.owner,
            fencing_token=lease.fencing_token,
            expires_at=expires_at,
        )

    async def reap_expired(self, before: Optional[str] = None) -> int:
        """Reap expired locks via the backend; return the count."""
        return await self._backend.reap_expired(before)

    async def close(self) -> None:
        """Close the underlying backend."""
        await self._backend.close()

    @asynccontextmanager
    async def lease(
        self, key: str, ttl_seconds: Optional[int] = None
    ) -> AsyncIterator[Lease]:
        """Acquire ``key`` on entry and ALWAYS release on exit.

        The lock is released on BOTH normal exit AND exception — the ``try /
        finally`` guarantees the lease is never leaked even if the protected
        block raises.

        Usage::

            async with lock.lease("invoice-42", ttl_seconds=30) as held:
                await resource.write(data, fencing_token=held.fencing_token)

        Raises
        ------
        LockAcquireError
            If the lock cannot be acquired immediately (the contextmanager
            does not block — use :meth:`acquire` with ``blocking=True`` when
            blocking semantics are needed).
        """
        held = await self.acquire(key, ttl_seconds)
        if held is None:
            raise LockAcquireError(
                f"could not acquire lock for key {key!r} (contended)"
            )
        try:
            yield held
        finally:
            await self.release(held)


class LockAcquireError(RuntimeError):
    """Raised by :meth:`DistributedLock.lease` when the lock is contended."""
