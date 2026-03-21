# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
SQLite-based TrustStore implementation.

Provides a persistent implementation that stores trust chains in a local
SQLite database. Uses WAL mode for concurrent read performance and
``asyncio.to_thread()`` to avoid blocking the event loop.

Features:
- Single-file persistence (default: ``~/.eatp/trust.db``)
- WAL journal mode for concurrent readers
- Thread-safe via ``threading.local()`` per-thread connections
- Soft-delete support (marks inactive rather than removing)
- Filtering by authority_id and active_only
- Pagination support (limit/offset)
- Zero new dependencies (stdlib sqlite3 only)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from kailash.trust.chain import TrustLineageChain
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.chain_store import TrustStore, _chain_has_missing_reasoning

logger = logging.getLogger(__name__)

__all__ = ["SqliteTrustStore"]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trust_chains (
    agent_id TEXT PRIMARY KEY,
    chain_data TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    authority_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    expires_at TEXT
)
"""


class SqliteTrustStore(TrustStore):
    """
    SQLite-backed trust store for persistent local storage.

    Stores each :class:`TrustLineageChain` as a JSON blob inside a
    ``trust_chains`` table in a local SQLite database.

    Thread safety is achieved through :class:`threading.local` so each
    thread gets its own ``sqlite3.Connection``.  All public async methods
    delegate to :func:`asyncio.to_thread` so the event loop is never
    blocked.

    Example::

        store = SqliteTrustStore("/tmp/eatp/trust.db")
        await store.initialize()
        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the SQLite trust store.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ``~/.eatp/trust.db``.
        """
        if db_path is None:
            db_path = os.path.join(os.path.expanduser("~"), ".eatp", "trust.db")
        self._db_path = db_path
        self._initialized = False
        self._local = threading.local()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_initialized(self) -> None:
        """Raise RuntimeError if the store has not been initialized."""
        if not self._initialized:
            raise RuntimeError(
                "SqliteTrustStore is not initialized. Call await store.initialize() before performing operations."
            )

    def _get_connection(self) -> sqlite3.Connection:
        """
        Return a per-thread SQLite connection.

        Creates a new connection on the first call within each thread.
        Connections use WAL mode and return rows as ``sqlite3.Row`` for
        column-name access.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _serialize_chain(self, chain: TrustLineageChain) -> str:
        """
        Serialize a TrustLineageChain to a JSON string.

        Uses ``to_dict()`` as a base then patches in genesis.signature,
        capability signatures, and delegation signatures for round-trip
        fidelity (matching the FilesystemStore pattern).

        Args:
            chain: The chain to serialize.

        Returns:
            A JSON string suitable for storage.
        """
        data = chain.to_dict()

        # Patch in genesis.signature (not included by to_dict)
        data["genesis"]["signature"] = chain.genesis.signature

        # Patch in capability signatures (not included by to_dict)
        for i, cap in enumerate(chain.capabilities):
            data["capabilities"][i]["signature"] = cap.signature

        # Patch in delegation signatures (not included by to_dict for inline dicts)
        for i, deleg in enumerate(chain.delegations):
            data["delegations"][i]["signature"] = deleg.signature

        return json.dumps(data, default=str)

    def _deserialize_chain(self, chain_json: str) -> TrustLineageChain:
        """
        Deserialize a JSON string back to a TrustLineageChain.

        Args:
            chain_json: The JSON string from the ``chain_data`` column.

        Returns:
            A fully-reconstructed TrustLineageChain.
        """
        data = json.loads(chain_json)
        return TrustLineageChain.from_dict(data)

    # ------------------------------------------------------------------
    # Sync implementations (run via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _sync_initialize(self) -> None:
        """Create database directory, table, and enable WAL mode."""
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Set restrictive file permissions on POSIX (owner read/write only)
        if self._db_path != ":memory:":
            import stat

            db_file = Path(self._db_path)
            if not db_file.exists():
                db_file.touch(mode=0o600)
            else:
                try:
                    os.chmod(db_file, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass  # Windows or permission denied

        conn = self._get_connection()
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        self._initialized = True
        logger.info("SqliteTrustStore initialized at %s", self._db_path)

    def _sync_store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Store or overwrite a trust chain row."""
        self._require_initialized()
        agent_id = chain.genesis.agent_id
        authority_id = chain.genesis.authority_id
        now = datetime.now(timezone.utc).isoformat()
        chain_json = self._serialize_chain(chain)

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO trust_chains
                (agent_id, chain_data, active, authority_id,
                 created_at, updated_at, deleted_at, expires_at)
            VALUES (?, ?, 1, ?, ?, ?, NULL, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                chain_data = excluded.chain_data,
                active = 1,
                authority_id = excluded.authority_id,
                updated_at = excluded.updated_at,
                deleted_at = NULL,
                expires_at = excluded.expires_at
            """,
            (
                agent_id,
                chain_json,
                authority_id,
                now,
                now,
                expires_at.isoformat() if expires_at else None,
            ),
        )
        conn.commit()
        logger.debug("Stored chain for agent %s", agent_id)
        return agent_id

    def _sync_get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """Retrieve a chain by agent_id."""
        self._require_initialized()
        conn = self._get_connection()

        if include_inactive:
            cursor = conn.execute(
                "SELECT chain_data FROM trust_chains WHERE agent_id = ?",
                (agent_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT chain_data FROM trust_chains WHERE agent_id = ? AND active = 1",
                (agent_id,),
            )

        row = cursor.fetchone()
        if row is None:
            raise TrustChainNotFoundError(agent_id)

        return self._deserialize_chain(row["chain_data"])

    def _sync_update_chain(
        self,
        agent_id: str,
        chain: TrustLineageChain,
    ) -> None:
        """Update an existing chain, preserving created_at."""
        self._require_initialized()
        conn = self._get_connection()

        # Check existence first
        cursor = conn.execute(
            "SELECT agent_id FROM trust_chains WHERE agent_id = ?",
            (agent_id,),
        )
        if cursor.fetchone() is None:
            raise TrustChainNotFoundError(agent_id)

        now = datetime.now(timezone.utc).isoformat()
        chain_json = self._serialize_chain(chain)
        authority_id = chain.genesis.authority_id

        conn.execute(
            """
            UPDATE trust_chains
            SET chain_data = ?,
                authority_id = ?,
                updated_at = ?
            WHERE agent_id = ?
            """,
            (chain_json, authority_id, now, agent_id),
        )
        conn.commit()
        logger.debug("Updated chain for agent %s", agent_id)

    def _sync_delete_chain(
        self,
        agent_id: str,
        soft_delete: bool = True,
    ) -> None:
        """Soft-delete (mark inactive) or hard-delete (remove row)."""
        self._require_initialized()
        conn = self._get_connection()

        if soft_delete:
            # Check existence (any state)
            cursor = conn.execute(
                "SELECT agent_id FROM trust_chains WHERE agent_id = ?",
                (agent_id,),
            )
            if cursor.fetchone() is None:
                raise TrustChainNotFoundError(agent_id)

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE trust_chains
                SET active = 0, deleted_at = ?, updated_at = ?
                WHERE agent_id = ?
                """,
                (now, now, agent_id),
            )
            conn.commit()
            logger.debug("Soft-deleted chain for agent %s", agent_id)
        else:
            cursor = conn.execute(
                "SELECT agent_id FROM trust_chains WHERE agent_id = ?",
                (agent_id,),
            )
            if cursor.fetchone() is None:
                raise TrustChainNotFoundError(agent_id)

            conn.execute(
                "DELETE FROM trust_chains WHERE agent_id = ?",
                (agent_id,),
            )
            conn.commit()
            logger.debug("Hard-deleted chain for agent %s", agent_id)

    def _sync_list_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TrustLineageChain]:
        """List chains with filtering and pagination."""
        self._require_initialized()
        conn = self._get_connection()

        query = "SELECT chain_data FROM trust_chains WHERE 1=1"
        params: List[Any] = []

        if active_only:
            query += " AND active = 1"

        if authority_id is not None:
            query += " AND authority_id = ?"
            params.append(authority_id)

        query += " ORDER BY agent_id LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        return [self._deserialize_chain(row["chain_data"]) for row in rows]

    def _sync_count_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
    ) -> int:
        """Count chains with filtering."""
        self._require_initialized()
        conn = self._get_connection()

        query = "SELECT COUNT(*) as cnt FROM trust_chains WHERE 1=1"
        params: List[Any] = []

        if active_only:
            query += " AND active = 1"

        if authority_id is not None:
            query += " AND authority_id = ?"
            params.append(authority_id)

        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return row["cnt"]

    def _sync_close(self) -> None:
        """Close the per-thread connection if open."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        self._initialized = False
        logger.info("SqliteTrustStore closed")

    def _sync_get_chains_missing_reasoning(self) -> List[str]:
        """Return agent IDs whose chains have missing reasoning traces."""
        self._require_initialized()
        conn = self._get_connection()

        cursor = conn.execute(
            "SELECT agent_id, chain_data FROM trust_chains WHERE active = 1"
        )
        missing: List[str] = []
        for row in cursor.fetchall():
            chain = self._deserialize_chain(row["chain_data"])
            if _chain_has_missing_reasoning(chain):
                missing.append(row["agent_id"])
        return missing

    # ------------------------------------------------------------------
    # TrustStore ABC implementation (async wrappers)
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize the SQLite store: create directories, table, WAL mode."""
        await asyncio.to_thread(self._sync_initialize)

    async def store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Store a trust lineage chain.

        Args:
            chain: The TrustLineageChain to store.
            expires_at: Optional expiration datetime.

        Returns:
            The agent_id of the stored chain.
        """
        return await asyncio.to_thread(self._sync_store_chain, chain, expires_at)

    async def get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """
        Retrieve a trust lineage chain by agent_id.

        Args:
            agent_id: The agent ID to retrieve.
            include_inactive: If True, return soft-deleted chains as well.

        Returns:
            The TrustLineageChain for the agent.

        Raises:
            TrustChainNotFoundError: If the chain is not found.
            RuntimeError: If the store is not initialized.
        """
        return await asyncio.to_thread(self._sync_get_chain, agent_id, include_inactive)

    async def update_chain(
        self,
        agent_id: str,
        chain: TrustLineageChain,
    ) -> None:
        """
        Update an existing trust lineage chain.

        Preserves the original ``created_at`` timestamp.

        Args:
            agent_id: The agent ID to update.
            chain: The new TrustLineageChain data.

        Raises:
            TrustChainNotFoundError: If the chain is not found.
            RuntimeError: If the store is not initialized.
        """
        await asyncio.to_thread(self._sync_update_chain, agent_id, chain)

    async def delete_chain(
        self,
        agent_id: str,
        soft_delete: bool = True,
    ) -> None:
        """
        Delete a trust lineage chain.

        Soft delete marks the chain as inactive.
        Hard delete removes the row entirely.

        Args:
            agent_id: The agent ID to delete.
            soft_delete: If True, mark inactive; if False, remove the row.

        Raises:
            TrustChainNotFoundError: If the chain is not found.
            RuntimeError: If the store is not initialized.
        """
        await asyncio.to_thread(self._sync_delete_chain, agent_id, soft_delete)

    async def list_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TrustLineageChain]:
        """
        List trust lineage chains with filtering and pagination.

        Args:
            authority_id: Filter by authority ID (optional).
            active_only: If True, exclude soft-deleted chains.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of TrustLineageChain objects.

        Raises:
            RuntimeError: If the store is not initialized.
        """
        return await asyncio.to_thread(
            self._sync_list_chains, authority_id, active_only, limit, offset
        )

    async def count_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
    ) -> int:
        """
        Count trust lineage chains with filtering.

        Args:
            authority_id: Filter by authority ID (optional).
            active_only: If True, exclude soft-deleted chains.

        Returns:
            Number of matching chains.

        Raises:
            RuntimeError: If the store is not initialized.
        """
        return await asyncio.to_thread(
            self._sync_count_chains, authority_id, active_only
        )

    async def close(self) -> None:
        """Close the database connection and reset state."""
        await asyncio.to_thread(self._sync_close)

    async def get_chains_missing_reasoning(self) -> List[str]:
        """
        Return agent IDs whose chains have delegations or audit anchors
        without reasoning traces.

        Returns:
            List of agent_id strings for chains with missing reasoning.
        """
        return await asyncio.to_thread(self._sync_get_chains_missing_reasoning)
