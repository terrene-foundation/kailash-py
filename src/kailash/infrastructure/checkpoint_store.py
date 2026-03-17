# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable Checkpoint Storage backend using ConnectionManager.

Implements the :class:`~kailash.middleware.gateway.checkpoint_manager.StorageBackend`
protocol with SQL storage.  All queries use canonical ``?`` placeholders;
:class:`~kailash.db.connection.ConnectionManager` translates to the target
database dialect automatically.

Table: ``kailash_checkpoints``

Schema::

    key         TEXT PRIMARY KEY
    data        BLOB NOT NULL
    size_bytes  INTEGER NOT NULL
    compressed  BOOLEAN NOT NULL DEFAULT 0
    created_at  TEXT NOT NULL          -- ISO-8601 UTC
    accessed_at TEXT NOT NULL          -- ISO-8601 UTC
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "DBCheckpointStore",
]


class DBCheckpointStore:
    """Database-backed checkpoint store implementing the StorageBackend protocol.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance.
    """

    TABLE_NAME = "kailash_checkpoints"

    def __init__(self, conn_manager: ConnectionManager) -> None:
        self._conn = conn_manager

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the checkpoints table if it does not exist."""
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                key TEXT PRIMARY KEY,
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                compressed BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                accessed_at TEXT NOT NULL
            )
            """
        )
        logger.info("Checkpoint table '%s' initialized", self.TABLE_NAME)

    async def close(self) -> None:
        """Release any resources held by the backend.

        The underlying ConnectionManager is NOT closed here — it is
        owned by the caller and may be shared with other stores.
        """
        logger.debug("Checkpoint store backend closed")

    # ------------------------------------------------------------------
    # Protocol: save / load / delete / list_keys
    # ------------------------------------------------------------------
    async def save(self, key: str, data: bytes) -> None:
        """Save binary *data* under *key*, overwriting if it already exists.

        Parameters
        ----------
        key:
            Unique checkpoint identifier.
        data:
            Raw bytes to store (may be pre-compressed).
        """
        now = datetime.now(timezone.utc).isoformat()
        size_bytes = len(data)

        # Simple heuristic: if the data starts with the gzip magic number,
        # mark it as compressed.
        compressed = data[:2] == b"\x1f\x8b" if len(data) >= 2 else False

        # Use INSERT OR REPLACE for upsert across all dialects that support it.
        # For full dialect portability via QueryDialect.upsert(), we would need
        # to add the method call, but INSERT OR REPLACE works on SQLite and
        # ON CONFLICT ... DO UPDATE works identically.  We use the
        # dialect-neutral approach here.
        existing = await self._conn.fetchone(
            f"SELECT key FROM {self.TABLE_NAME} WHERE key = ?",
            key,
        )

        if existing:
            await self._conn.execute(
                f"UPDATE {self.TABLE_NAME} "
                f"SET data = ?, size_bytes = ?, compressed = ?, accessed_at = ? "
                f"WHERE key = ?",
                data,
                size_bytes,
                compressed,
                now,
                key,
            )
        else:
            await self._conn.execute(
                f"INSERT INTO {self.TABLE_NAME} "
                f"(key, data, size_bytes, compressed, created_at, accessed_at) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                key,
                data,
                size_bytes,
                compressed,
                now,
                now,
            )

        logger.debug(
            "Saved checkpoint '%s' (%d bytes, compressed=%s)",
            key,
            size_bytes,
            compressed,
        )

    async def load(self, key: str) -> Optional[bytes]:
        """Load binary data for *key*, updating ``accessed_at``.

        Parameters
        ----------
        key:
            Checkpoint identifier.

        Returns
        -------
        bytes or None
            The stored data, or ``None`` if the key does not exist.
        """
        row = await self._conn.fetchone(
            f"SELECT data FROM {self.TABLE_NAME} WHERE key = ?",
            key,
        )

        if row is None:
            return None

        # Update accessed_at timestamp
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET accessed_at = ? WHERE key = ?",
            now,
            key,
        )

        return row["data"]

    async def delete(self, key: str) -> None:
        """Delete the checkpoint identified by *key*.

        No-op if the key does not exist.

        Parameters
        ----------
        key:
            Checkpoint identifier.
        """
        await self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE key = ?",
            key,
        )
        logger.debug("Deleted checkpoint '%s'", key)

    async def list_keys(self, prefix: str) -> List[str]:
        """List all checkpoint keys matching *prefix*.

        Parameters
        ----------
        prefix:
            Key prefix to filter on.  An empty string matches all keys.

        Returns
        -------
        list[str]
            Matching keys in alphabetical order.
        """
        like_pattern = f"{prefix}%"
        rows = await self._conn.fetch(
            f"SELECT key FROM {self.TABLE_NAME} " f"WHERE key LIKE ? ORDER BY key ASC",
            like_pattern,
        )
        return [row["key"] for row in rows]
