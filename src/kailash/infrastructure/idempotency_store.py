# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable IdempotencyStore backend using ConnectionManager.

Provides persistent storage for idempotency keys with TTL-based expiry.
Implements a claim-then-store pattern for safe concurrent request handling:

1. ``try_claim(key, fingerprint)`` -- atomically claim a key
2. Process the request
3. ``store_result(key, ...)`` -- store the actual response
4. On failure: ``release_claim(key)`` -- allow retry

All queries use canonical ``?`` placeholders;
:class:`~kailash.db.connection.ConnectionManager` translates to the target
database dialect automatically.

Table: ``kailash_idempotency``

Schema::

    idempotency_key TEXT PRIMARY KEY
    fingerprint     TEXT NOT NULL
    response_data   TEXT NOT NULL          -- JSON
    status_code     INTEGER NOT NULL
    headers         TEXT DEFAULT '{}'      -- JSON
    created_at      TEXT NOT NULL          -- ISO-8601 UTC
    expires_at      TEXT NOT NULL          -- ISO-8601 UTC
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "DBIdempotencyStore",
]


class DBIdempotencyStore:
    """Database-backed idempotency store with TTL-based expiry.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance.
    """

    TABLE_NAME = "kailash_idempotency"

    def __init__(self, conn_manager: ConnectionManager) -> None:
        self._conn = conn_manager

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the idempotency table and indices if they do not exist.

        Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, the
        table name is quoted via ``dialect.quote_identifier()`` for
        the DDL interpolation.
        """
        quoted_table = self._conn.dialect.quote_identifier(self.TABLE_NAME)
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {quoted_table} (
                idempotency_key {self._conn.dialect.text_column(indexed=True)} PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                response_data TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                headers VARCHAR(4096) NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL,
                expires_at {self._conn.dialect.text_column(indexed=True)} NOT NULL
            )
            """
        )
        await self._conn.create_index(
            "idx_idempotency_expires",
            self.TABLE_NAME,
            "expires_at",
        )
        logger.info("IdempotencyStore table '%s' initialized", self.TABLE_NAME)

    async def close(self) -> None:
        """Release any resources held by the backend.

        The underlying ConnectionManager is NOT closed here -- it is
        owned by the caller and may be shared with other stores.
        """
        logger.debug("IdempotencyStore backend closed")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve an idempotency entry by key, respecting TTL.

        Parameters
        ----------
        key:
            The idempotency key to look up.

        Returns
        -------
        dict or None
            The stored entry as a dict, or None if not found or expired.
        """
        now = datetime.now(timezone.utc).isoformat()
        row = await self._conn.fetchone(
            f"SELECT * FROM {self.TABLE_NAME} "
            f"WHERE idempotency_key = ? AND expires_at > ?",
            key,
            now,
        )
        return dict(row) if row else None

    async def set(
        self,
        key: str,
        fingerprint: str,
        response_data: Any,
        status_code: int,
        headers: Dict[str, str],
        ttl_seconds: int,
    ) -> None:
        """Store an idempotency entry with TTL.

        Uses INSERT OR IGNORE so the first writer wins -- subsequent
        calls with the same key are silently ignored.

        Parameters
        ----------
        key:
            The idempotency key.
        fingerprint:
            Request fingerprint for conflict detection.
        response_data:
            Response data to store (will be JSON-serialized).
        status_code:
            HTTP status code of the response.
        headers:
            Response headers dict (will be JSON-serialized).
        ttl_seconds:
            Time-to-live in seconds from now.
        """
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        response_json = json.dumps(response_data)
        headers_json = json.dumps(headers)

        _cols = [
            "idempotency_key",
            "fingerprint",
            "response_data",
            "status_code",
            "headers",
            "created_at",
            "expires_at",
        ]
        sql = self._conn.dialect.insert_ignore(
            self.TABLE_NAME, _cols, ["idempotency_key"]
        )
        await self._conn.execute(
            sql,
            key,
            fingerprint,
            response_json,
            status_code,
            headers_json,
            created_at,
            expires_at,
        )
        logger.debug("Idempotency set: key=%s ttl=%ds", key, ttl_seconds)

    async def try_claim(self, key: str, fingerprint: str) -> bool:
        """Atomically claim an idempotency key.

        Inserts a placeholder row with ``status_code=0`` and empty response.
        Returns True if the claim succeeded (key was not already taken),
        False if the key already exists.

        Parameters
        ----------
        key:
            The idempotency key to claim.
        fingerprint:
            Request fingerprint.

        Returns
        -------
        bool
            True if the key was successfully claimed, False if already exists.
        """
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        # Claims get a generous TTL (5 minutes) to allow processing time
        expires_at = (now + timedelta(minutes=5)).isoformat()

        _cols = [
            "idempotency_key",
            "fingerprint",
            "response_data",
            "status_code",
            "headers",
            "created_at",
            "expires_at",
        ]
        sql = self._conn.dialect.insert_ignore(
            self.TABLE_NAME, _cols, ["idempotency_key"]
        )

        # Atomic claim: INSERT IGNORE then verify fingerprint in one txn
        async with self._conn.transaction() as tx:
            await tx.execute(
                sql,
                key,
                fingerprint,
                "{}",  # Empty placeholder response
                0,  # status_code=0 indicates a claim in progress
                "{}",
                created_at,
                expires_at,
            )

            # Verify the claim succeeded by checking the fingerprint
            row = await tx.fetchone(
                f"SELECT fingerprint FROM {self.TABLE_NAME} WHERE idempotency_key = ?",
                key,
            )

        if row is not None and row["fingerprint"] == fingerprint:
            logger.debug("Idempotency claimed: key=%s", key)
            return True

        logger.debug("Idempotency claim failed (already exists): key=%s", key)
        return False

    async def store_result(
        self,
        key: str,
        response_data: Any,
        status_code: int,
        headers: Dict[str, str],
    ) -> None:
        """Update a claimed entry with the actual response data.

        Parameters
        ----------
        key:
            The idempotency key (must have been claimed via try_claim).
        response_data:
            The actual response data (will be JSON-serialized).
        status_code:
            HTTP status code of the response.
        headers:
            Response headers dict (will be JSON-serialized).
        """
        response_json = json.dumps(response_data)
        headers_json = json.dumps(headers)

        await self._conn.execute(
            f"UPDATE {self.TABLE_NAME} "
            f"SET response_data = ?, status_code = ?, headers = ? "
            f"WHERE idempotency_key = ?",
            response_json,
            status_code,
            headers_json,
            key,
        )
        logger.debug("Idempotency result stored: key=%s status=%d", key, status_code)

    async def release_claim(self, key: str) -> None:
        """Release a claimed key by deleting it, allowing retry.

        Parameters
        ----------
        key:
            The idempotency key to release.
        """
        await self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE idempotency_key = ?",
            key,
        )
        logger.debug("Idempotency claim released: key=%s", key)

    async def cleanup(self, before: Optional[str] = None) -> None:
        """Delete expired idempotency entries.

        Parameters
        ----------
        before:
            ISO-8601 timestamp threshold. Entries with ``expires_at < before``
            are deleted. If None, uses the current UTC time.
        """
        if before is None:
            before = datetime.now(timezone.utc).isoformat()

        await self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE expires_at < ?",
            before,
        )
        logger.info("Idempotency cleanup: removed entries expired before %s", before)
