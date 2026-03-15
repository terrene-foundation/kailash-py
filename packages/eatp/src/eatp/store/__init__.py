# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Trust Store — ABC, TransactionContext, and filesystem utilities.

Provides the abstract interface for trust chain storage and
transactional context for atomic operations.

Architecture:
- TrustStore ABC defines the contract for all store implementations
- TransactionContext enables atomic multi-chain updates (CARE-008)
- Concrete implementations live in submodules (memory, filesystem, etc.)

Public utilities available via ``from eatp.store.filesystem import ...``:
- ``file_lock``: Cross-process file lock context manager (fcntl.flock)
- ``validate_id``: Path-traversal-safe identifier validation
"""

import copy
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from eatp.chain import TrustLineageChain
from eatp.exceptions import TrustChainNotFoundError


def _chain_has_missing_reasoning(chain: TrustLineageChain) -> bool:
    """
    Check if a trust chain has delegations or audit anchors missing reasoning traces.

    Returns True if at least one delegation or audit_trail entry lacks a
    reasoning_trace. Returns False if there are no delegations/audit_trail
    entries (nothing to be missing) or all have reasoning.

    Args:
        chain: The TrustLineageChain to check.

    Returns:
        True if any delegation or audit anchor is missing a reasoning trace.
    """
    has_items = False

    for delegation in chain.delegations:
        has_items = True
        if delegation.reasoning_trace is None:
            return True

    for anchor in chain.audit_anchors:
        has_items = True
        if anchor.reasoning_trace is None:
            return True

    return False


class TrustStore(ABC):
    """
    Abstract base class for EATP trust chain storage.

    Defines the interface that all trust store implementations must follow.
    Provides CRUD operations for TrustLineageChain objects with filtering
    and pagination support.

    Implementations:
    - InMemoryTrustStore: Fast in-memory storage for testing/development
    - FilesystemStore: Persistent JSON-file storage (``eatp.store.filesystem``)
    - SqliteTrustStore: Persistent SQLite storage (``eatp.store.sqlite``)
    - PostgresTrustStore: Production storage using DataFlow (in kailash-kaizen)
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the trust store."""
        ...

    @abstractmethod
    async def store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Store a trust lineage chain.

        Args:
            chain: The TrustLineageChain to store
            expires_at: Optional expiration datetime

        Returns:
            The agent_id of the stored chain
        """
        ...

    @abstractmethod
    async def get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """
        Retrieve a trust lineage chain by agent_id.

        Args:
            agent_id: The agent ID to retrieve
            include_inactive: Include inactive chains

        Returns:
            The TrustLineageChain for the agent

        Raises:
            TrustChainNotFoundError: If chain not found
        """
        ...

    @abstractmethod
    async def update_chain(
        self,
        agent_id: str,
        chain: TrustLineageChain,
    ) -> None:
        """
        Update an existing trust lineage chain.

        Args:
            agent_id: The agent ID to update
            chain: The new TrustLineageChain data

        Raises:
            TrustChainNotFoundError: If chain not found
        """
        ...

    @abstractmethod
    async def delete_chain(
        self,
        agent_id: str,
        soft_delete: bool = True,
    ) -> None:
        """
        Delete a trust lineage chain.

        Args:
            agent_id: The agent ID to delete
            soft_delete: Use soft delete vs hard delete

        Raises:
            TrustChainNotFoundError: If chain not found
        """
        ...

    @abstractmethod
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
            authority_id: Filter by authority ID (optional)
            active_only: Include only active chains
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of TrustLineageChain objects
        """
        ...

    @abstractmethod
    async def count_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
    ) -> int:
        """
        Count trust lineage chains with filtering.

        Args:
            authority_id: Filter by authority ID (optional)
            active_only: Include only active chains

        Returns:
            Number of matching chains
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close and cleanup resources."""
        ...

    async def get_chains_missing_reasoning(self) -> List[str]:
        """
        Return agent IDs whose chains have delegations or audit anchors
        without reasoning traces.

        This is a compliance query: "show all agents without complete
        reasoning traces". An agent is included if ANY of its delegations
        or audit_trail entries lack a reasoning_trace.

        Agents whose chains have no delegations AND no audit_trail entries
        are NOT included (there is nothing to be missing).

        Returns:
            List of agent_id strings for chains with missing reasoning.
        """
        chains = await self.list_chains(active_only=True, limit=100000)
        missing: List[str] = []
        for chain in chains:
            if _chain_has_missing_reasoning(chain):
                missing.append(chain.genesis.agent_id)
        return missing


class TransactionContext:
    """
    Transactional context for trust store operations.

    CARE-008: Provides atomic update guarantees for trust chain re-signing.
    Collects store operations and applies them atomically on commit.
    On rollback (exception or no commit), restores the original state.

    Example:
        >>> async with store.transaction() as tx:
        ...     await tx.update_chain("agent-1", chain1)
        ...     await tx.update_chain("agent-2", chain2)
        ...     await tx.commit()  # Both updates applied atomically

    If an exception occurs or commit() is not called, all changes are discarded.
    """

    def __init__(self, store: "InMemoryTrustStore"):
        """
        Initialize TransactionContext.

        Args:
            store: The InMemoryTrustStore instance to operate on
        """
        from eatp.store.memory import InMemoryTrustStore

        self._store = store
        self._pending_updates: List[Tuple[str, TrustLineageChain]] = []
        self._committed = False
        self._snapshot: Dict[str, TrustLineageChain] = {}
        self._entered = False

    async def __aenter__(self) -> "TransactionContext":
        """
        Enter the transaction context and take a snapshot of current state.

        Returns:
            Self for use in async with statement
        """
        # Take deep copy snapshot of current state for rollback
        self._snapshot = {k: copy.deepcopy(v) for k, v in self._store._chains.items()}
        self._entered = True
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """
        Exit the transaction context.

        On exception or if not committed, restores the original state (rollback).

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        if exc_type is not None or not self._committed:
            # Rollback: restore snapshot
            self._store._chains.clear()
            self._store._chains.update(self._snapshot)
        return False

    async def update_chain(self, agent_id: str, chain: TrustLineageChain) -> None:
        """
        Queue a chain update for atomic commit.

        The update is not applied immediately; it's stored in the pending list
        and applied when commit() is called.

        Args:
            agent_id: The agent ID for the chain
            chain: The updated TrustLineageChain
        """
        if not self._entered:
            raise RuntimeError("TransactionContext must be used with 'async with'")
        self._pending_updates.append((agent_id, chain))

    async def commit(self) -> None:
        """
        Commit all pending updates atomically.

        Applies all queued updates to the store. After commit, the transaction
        is marked as committed and rollback will not occur on exit.

        Raises:
            RuntimeError: If called outside of context manager
        """
        if not self._entered:
            raise RuntimeError("TransactionContext must be used with 'async with'")

        # Apply all pending updates
        for agent_id, chain in self._pending_updates:
            await self._store.store_chain(chain)

        self._committed = True

    @property
    def pending_count(self) -> int:
        """Return the number of pending updates."""
        return len(self._pending_updates)
