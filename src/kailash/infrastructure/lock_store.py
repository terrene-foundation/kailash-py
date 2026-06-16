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

Table (``DBLockBackend``) — a SINGLE table, ``kailash_locks``::

      key            TEXT PRIMARY KEY
      owner          TEXT                   -- NULL when free (tombstone)
      fencing_token  BIGINT NOT NULL        -- survives release/expiry/steal
      expires_at     TEXT                   -- NULL when free

The lock row is **never deleted** — release / reap set ``owner`` and
``expires_at`` to ``NULL`` (a *tombstone*) while preserving ``fencing_token``.
Keeping one persistent row per key (instead of a separate fence table) is what
makes the acquire atomic: the row always exists once a key has been seen, so a
``SELECT ... FOR UPDATE`` inside the acquire transaction always finds and locks
it, serializing every concurrent acquirer of that key. The fence therefore
stays strictly increasing and is **never reset** across release / native
expiry / steal — exactly the load-bearing safety property a separate fence
table previously provided, now with a single-table atomic-acquire design.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Optional, Protocol, runtime_checkable

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
    ``expires_at`` column, dialect-portable DDL via
    ``dialect.text_column(indexed=True)``, ``reap_expired`` analogous to
    ``cleanup``.

    Atomicity of acquire (steal-if-expired) is provided by a
    ``SELECT ... FOR UPDATE`` row lock inside one ``conn.transaction()`` block.
    Because the single ``kailash_locks`` table keeps one **persistent row per
    key** (release / reap tombstone the row rather than deleting it), the row
    always exists by the time the acquire reads it, so the ``FOR UPDATE`` lock
    serializes every concurrent acquirer of that key — even an EXPIRED key two
    workers race to steal.  The contract "exactly one acquirer wins, the rest
    get ``None``" therefore holds on EVERY dialect regardless of transaction
    isolation level (asyncpg defaults to READ COMMITTED; ``FOR UPDATE``'s
    block-then-reread semantics make the check-then-steal atomic under it).
    SQLite emits no ``FOR UPDATE`` clause (``dialect.for_update()`` returns
    ``""``) because ``BEGIN IMMEDIATE`` already serializes writers.

    The fencing token lives in the same row and is bumped in the SAME
    transaction as the steal, so it is strictly monotonic per key on every
    dialect — and because the row is tombstoned (never deleted) on release /
    reap, the token survives lock churn and is **never reset**.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance (shared, owned by
        the caller / StoreFactory).
    table_name:
        Name of the locks table (default ``kailash_locks``).  Validated
        against ``[a-zA-Z_][a-zA-Z0-9_]*`` at construction time.
    """

    def __init__(
        self,
        conn_manager: ConnectionManager,
        table_name: str = "kailash_locks",
        *,
        owns_connection: bool = False,
    ) -> None:
        if not _TABLE_NAME_RE.match(table_name):
            raise ValueError(f"Invalid table name: must match {_TABLE_NAME_RE.pattern}")
        self._conn = conn_manager
        self._table = table_name
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
        """Create the locks table and the expiry index if absent.

        Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, the dynamic
        table name routes through ``dialect.quote_identifier()`` (validates +
        quotes) for the DDL interpolation.  Safe to call multiple times.

        ``owner`` and ``expires_at`` are NULLable: a free key is represented as
        a tombstone row (``owner IS NULL``) so the persistent ``fencing_token``
        survives release / reap.  Indexed text columns route through
        ``dialect.text_column(indexed=True)`` (``VARCHAR(255)`` on MySQL, which
        cannot index unbounded ``TEXT``).
        """
        if self._initialized:
            return

        _tc = self._conn.dialect.text_column(indexed=True)
        quoted_locks = self._conn.dialect.quote_identifier(self._table)
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {quoted_locks} (
                key {_tc} PRIMARY KEY,
                owner TEXT,
                fencing_token BIGINT NOT NULL,
                expires_at {_tc}
            )
            """
        )
        await self._conn.create_index(
            f"idx_{self._table}_expires",
            self._table,
            "expires_at",
        )

        self._initialized = True
        logger.info("DBLockBackend table '%s' initialized", self._table)

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
    async def try_acquire(
        self, key: str, owner: str, ttl_seconds: int
    ) -> Optional[int]:
        """Acquire ``key`` for ``owner``, stealing an expired lease if present.

        Returns the new fencing token on success, ``None`` on contention.

        Atomicity (the "exactly one winner, the rest get ``None``" contract,
        including the EXPIRED-key steal race two workers run concurrently) is
        provided by a ``SELECT ... FOR UPDATE`` row lock inside ONE
        transaction:

        1. ``INSERT ... ON CONFLICT DO NOTHING`` ensures a tombstone row
           exists for the key (atomic; idempotent).  This is what guarantees
           the ``SELECT ... FOR UPDATE`` in step 2 always has a row to lock.
        2. ``SELECT ... FOR UPDATE`` reads + row-locks the key.  A concurrent
           acquirer of the SAME key BLOCKS here until this transaction
           commits, then re-reads the committed row — so the expiry check in
           step 3 is serialized, not racy.
        3. If the lease is live (``owner IS NOT NULL`` AND ``expires_at`` in
           the future) → contention → return ``None``.
        4. Otherwise (free tombstone OR expired) → bump the fence, write the
           new owner + expiry → return the token.

        On SQLite ``dialect.for_update()`` is ``""``; ``BEGIN IMMEDIATE``
        (acquired by ``ConnectionManager.transaction()``) serializes writers,
        so the same single-winner guarantee holds with no per-row clause.
        """
        now = _utcnow()
        now_iso = _iso(now)
        expires_at = _iso(now + timedelta(seconds=ttl_seconds))
        for_update = self._conn.dialect.for_update()

        async with self._conn.transaction() as tx:
            # Step 1: ensure a row exists so the FOR UPDATE lock has a target.
            # insert_ignore() is atomic ON CONFLICT DO NOTHING (PG/SQLite) /
            # INSERT IGNORE (MySQL); the seed row is a free tombstone with
            # fencing_token = 0 so the first real acquire bumps it to 1.
            seed_sql = self._conn.dialect.insert_ignore(
                self._table,
                ["key", "owner", "fencing_token", "expires_at"],
                ["key"],
            )
            await tx.execute(seed_sql, key, None, 0, None)

            # Step 2: row-lock the key (blocks concurrent acquirers).
            select_sql = (
                f"SELECT owner, fencing_token, expires_at FROM {self._table} "
                "WHERE key = ?"
            )
            if for_update:
                select_sql += f" {for_update}"
            existing = await tx.fetchone(select_sql, key)

            # The seed in step 1 guarantees a row; the typed guard converts an
            # impossible-but-not-crash-safe None into an actionable error
            # rather than an opaque KeyError on existing["..."].
            if existing is None:  # pragma: no cover - row is seeded above
                raise LockAcquireError(
                    f"lock row for key {key!r} vanished after seed insert"
                )

            # Step 3: live lease held by someone → contention.
            if existing["owner"] is not None and (
                existing["expires_at"] is not None and existing["expires_at"] > now_iso
            ):
                return None

            # Step 4: free or expired → steal. Bump the persisted fence.
            token = int(existing["fencing_token"]) + 1
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

        The row is **tombstoned** (``owner`` / ``expires_at`` set to ``NULL``),
        NOT deleted — preserving ``fencing_token`` so the next acquire of this
        key gets a strictly-higher token.  The owner+token WHERE clause makes
        the gated UPDATE itself atomic, so no FOR UPDATE is needed here.
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
                f"UPDATE {self._table} SET owner = NULL, expires_at = NULL "
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

        "Lost" covers BOTH loss-via-steal (a newer acquirer tombstoned-then-
        re-stole the row, changing owner/token) AND loss-via-native-expiry (the
        lease's own ``expires_at`` lapsed without anyone stealing it — the row
        still carries this owner/token but is no longer live).  The
        ``expires_at > now`` predicate is what catches the native-expiry case:
        without it, a holder whose lease silently expired could extend a lock
        another worker is entitled to steal.
        """
        now_iso = _iso(_utcnow())
        new_expires = _iso(_utcnow() + timedelta(seconds=ttl_seconds))
        async with self._conn.transaction() as tx:
            current = await tx.fetchone(
                f"SELECT 1 AS hit FROM {self._table} "
                "WHERE key = ? AND owner = ? AND fencing_token = ? "
                "AND expires_at > ?",
                key,
                owner,
                token,
                now_iso,
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
        """Tombstone expired lock rows; return the count reaped.

        Mirrors ``DBIdempotencyStore.cleanup`` but does NOT delete: an expired
        row is **tombstoned** (``owner`` / ``expires_at`` set to ``NULL``) so
        the persisted ``fencing_token`` survives, keeping a reaped-then-
        reacquired key strictly-increasing.  Only rows that are still *claimed*
        (``owner IS NOT NULL``) AND past their TTL are reaped — an already-free
        tombstone (``expires_at IS NULL``) is left alone and never counted.
        """
        if before is None:
            before = _iso(_utcnow())

        # Count first so the return value is dialect-portable (asyncpg's
        # execute() returns a status string, not a rowcount int).
        rows = await self._conn.fetch(
            f"SELECT key FROM {self._table} "
            "WHERE owner IS NOT NULL AND expires_at < ?",
            before,
        )
        reaped = len(rows)
        if reaped:
            await self._conn.execute(
                f"UPDATE {self._table} SET owner = NULL, expires_at = NULL "
                "WHERE owner IS NOT NULL AND expires_at < ?",
                before,
            )
            logger.info("lock.reap tombstoned %d expired lock(s)", reaped)
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
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        owner = uuid.uuid4().hex

        token = await self._backend.try_acquire(key, owner, ttl)
        if token is not None:
            return self._lease_from(key, owner, token, ttl)

        if not blocking:
            return None

        # acquire() is always called from an async context; get_running_loop()
        # is the non-deprecated accessor (get_event_loop() warns on 3.12+).
        loop = asyncio.get_running_loop()
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
