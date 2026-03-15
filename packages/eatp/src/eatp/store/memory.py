# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
In-memory TrustStore implementation.

Provides a real implementation that stores trust chains in memory
instead of requiring PostgreSQL. Supports transactional operations
for atomic chain re-signing (CARE-008).

Features:
- Fast in-memory storage
- Soft-delete support (moves chains to _inactive instead of removing)
- Transaction support with rollback
- Compatible with TrustStore ABC interface
- No external dependencies
"""

from datetime import datetime
from typing import Dict, List, Optional

from eatp.chain import TrustLineageChain
from eatp.exceptions import TrustChainNotFoundError
from eatp.store import TransactionContext, TrustStore


class InMemoryTrustStore(TrustStore):
    """
    In-memory trust store for testing and development.

    Provides a real implementation that stores trust chains in memory
    instead of requiring PostgreSQL. Supports transactional operations
    for atomic chain re-signing (CARE-008).

    Features:
    - Fast in-memory storage
    - Transaction support with rollback
    - Compatible with TrustStore interface
    - No external dependencies

    Example:
        >>> store = InMemoryTrustStore()
        >>> await store.initialize()
        >>>
        >>> # Store a chain
        >>> await store.store_chain(chain)
        >>>
        >>> # Transactional updates
        >>> async with store.transaction() as tx:
        ...     await tx.update_chain("agent-1", updated_chain)
        ...     await tx.commit()
    """

    def __init__(self):
        """Initialize the in-memory trust store."""
        self._chains: Dict[str, TrustLineageChain] = {}
        self._inactive: Dict[str, TrustLineageChain] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the trust store."""
        self._initialized = True

    async def store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Store a trust lineage chain.

        Args:
            chain: The TrustLineageChain to store
            expires_at: Optional expiration datetime (not used in memory store)

        Returns:
            The agent_id of the stored chain
        """
        agent_id = chain.genesis.agent_id
        self._chains[agent_id] = chain
        return agent_id

    async def get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """
        Retrieve a trust lineage chain by agent_id.

        Args:
            agent_id: The agent ID to retrieve
            include_inactive: If True, also search inactive (soft-deleted) chains

        Returns:
            The TrustLineageChain for the agent

        Raises:
            TrustChainNotFoundError: If chain not found in active chains
                (and not in inactive chains when include_inactive=True)
        """
        chain = self._chains.get(agent_id)
        if chain is not None:
            return chain

        if include_inactive:
            chain = self._inactive.get(agent_id)
            if chain is not None:
                return chain

        raise TrustChainNotFoundError(agent_id)

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
        if agent_id not in self._chains:
            raise TrustChainNotFoundError(agent_id)
        self._chains[agent_id] = chain

    async def delete_chain(
        self,
        agent_id: str,
        soft_delete: bool = True,
    ) -> None:
        """
        Delete a trust lineage chain.

        If soft_delete=True (default), moves the chain from _chains to
        _inactive, preserving the data for later retrieval with
        include_inactive=True.

        If soft_delete=False, permanently removes the chain from both
        _chains and _inactive.

        Args:
            agent_id: The agent ID to delete
            soft_delete: If True, move to _inactive; if False, hard-delete
                from both _chains and _inactive

        Raises:
            TrustChainNotFoundError: If chain not found in _chains
                (for soft_delete=True) or in both _chains and _inactive
                (for soft_delete=False)
        """
        if soft_delete:
            if agent_id not in self._chains:
                raise TrustChainNotFoundError(agent_id)
            chain = self._chains.pop(agent_id)
            self._inactive[agent_id] = chain
        else:
            # Hard delete: remove from both _chains and _inactive
            found = False
            if agent_id in self._chains:
                del self._chains[agent_id]
                found = True
            if agent_id in self._inactive:
                del self._inactive[agent_id]
                found = True
            if not found:
                raise TrustChainNotFoundError(agent_id)

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
            active_only: If True (default), only return active chains.
                If False, include inactive (soft-deleted) chains too.
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of TrustLineageChain objects
        """
        chains = list(self._chains.values())

        if not active_only:
            chains = chains + list(self._inactive.values())

        # Filter by authority if specified
        if authority_id is not None:
            chains = [c for c in chains if c.genesis.authority_id == authority_id]

        # Apply pagination
        return chains[offset : offset + limit]

    async def count_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
    ) -> int:
        """
        Count trust lineage chains with filtering.

        Args:
            authority_id: Filter by authority ID (optional)
            active_only: If True (default), only count active chains.
                If False, include inactive (soft-deleted) chains too.

        Returns:
            Number of matching chains
        """
        all_chains = list(self._chains.values())
        if not active_only:
            all_chains = all_chains + list(self._inactive.values())

        if authority_id is not None:
            return len(
                [c for c in all_chains if c.genesis.authority_id == authority_id]
            )
        return len(all_chains)

    def transaction(self) -> TransactionContext:
        """
        Create a new transaction context for atomic operations.

        CARE-008: Use this for atomic chain re-signing during key rotation.
        All updates within the transaction are applied atomically on commit,
        or rolled back on exception/no commit.

        Returns:
            TransactionContext for use with async with

        Example:
            >>> async with store.transaction() as tx:
            ...     await tx.update_chain("agent-1", chain1)
            ...     await tx.update_chain("agent-2", chain2)
            ...     await tx.commit()
        """
        return TransactionContext(self)

    async def get_chains_missing_reasoning(self) -> List[str]:
        """Return agent IDs whose chains have delegations or audit anchors missing reasoning traces."""
        missing = []
        for agent_id, chain in self._chains.items():
            has_items = False
            has_missing = False
            for delegation in chain.delegations:
                has_items = True
                if delegation.reasoning_trace is None:
                    has_missing = True
                    break
            if not has_missing:
                for anchor in chain.audit_anchors:
                    has_items = True
                    if anchor.reasoning_trace is None:
                        has_missing = True
                        break
            if has_items and has_missing:
                missing.append(agent_id)
        return missing

    async def close(self) -> None:
        """Close and cleanup resources."""
        self._chains.clear()
        self._inactive.clear()
