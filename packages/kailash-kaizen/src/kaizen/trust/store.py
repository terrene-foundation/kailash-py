"""
Trust Store — thin adapter importing shared types from kailash.trust.

Shared types (TrustStore ABC, TransactionContext, InMemoryTrustStore) live in
``kailash.trust.chain_store`` / ``kailash.trust.chain_store.memory``.  This file re-exports them for
backwards compatibility and keeps the Kaizen-specific DataFlow-backed
``PostgresTrustStore`` which depends on ``kailash.runtime`` and ``dataflow``.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ---------- shared types (from kailash.trust) ----------
from kailash.trust.chain_store import TransactionContext, TrustStore  # noqa: F401
from kailash.trust.chain_store.memory import InMemoryTrustStore  # noqa: F401

from kaizen.trust.chain import TrustLineageChain
from kaizen.trust.exceptions import (
    TrustChainInvalidError,
    TrustChainNotFoundError,
    TrustStoreDatabaseError,
)


class PostgresTrustStore(TrustStore):
    """
    PostgreSQL-backed storage for EATP Trust Lineage Chains.

    This implementation uses DataFlow to automatically generate database
    operations from a model definition, with built-in caching for high
    performance.

    Performance Characteristics:
    - get_chain() with cache hit: <1ms
    - get_chain() with cache miss: ~5-10ms
    - store_chain(): ~5-10ms
    - list_chains() with pagination: ~10-20ms

    Example:
        >>> store = PostgresTrustStore()
        >>> await store.initialize()
        >>>
        >>> # Store a trust chain
        >>> await store.store_chain(trust_chain)
        >>>
        >>> # Retrieve with caching
        >>> chain = await store.get_chain("agent-123")
        >>>
        >>> # List with filtering
        >>> chains = await store.list_chains(
        ...     authority_id="org-456",
        ...     active_only=True,
        ...     limit=10
        ... )
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 300,  # 5 minutes default
        runtime: Optional[AsyncLocalRuntime] = None,
    ):
        """
        Initialize PostgresTrustStore.

        Args:
            database_url: PostgreSQL connection string (defaults to POSTGRES_URL env var)
            enable_cache: Enable caching for get operations (default: True)
            cache_ttl_seconds: Cache TTL in seconds (default: 300)
            runtime: Optional shared AsyncLocalRuntime (avoids pool leak)
        """
        self.database_url = database_url or os.getenv("POSTGRES_URL")
        if not self.database_url:
            raise TrustStoreDatabaseError(
                "No database URL provided. Set POSTGRES_URL environment variable "
                "or pass database_url parameter."
            )

        self.enable_cache = enable_cache
        self.cache_ttl_seconds = cache_ttl_seconds

        # Initialize DataFlow instance
        self.db = DataFlow(
            self.database_url,
            enable_caching=enable_cache,
            cache_ttl=cache_ttl_seconds,
        )

        # Define the TrustChain model using @db.model decorator
        # This automatically generates 11 workflow nodes:
        # TrustChain_Create, TrustChain_Read, TrustChain_Update,
        # TrustChain_Delete, TrustChain_List, TrustChain_Upsert,
        # TrustChain_Count, TrustChain_BulkCreate, TrustChain_BulkUpdate,
        # TrustChain_BulkDelete, TrustChain_BulkUpsert
        @self.db.model
        class TrustChain:
            """
            Database model for storing EATP Trust Lineage Chains.

            Uses JSONB for efficient storage of complex nested structures.
            Indexed fields enable fast filtering and querying.
            """

            id: str  # agent_id - primary lookup key
            chain_data: Dict[
                str, Any
            ]  # Serialized TrustLineageChain (JSONB in PostgreSQL)
            chain_hash: str  # Quick integrity verification
            authority_id: str  # For filtering by authority
            created_at: datetime  # Auto-managed by DataFlow
            updated_at: datetime  # Auto-managed by DataFlow
            is_active: bool = True  # Soft delete flag
            expires_at: Optional[datetime] = None  # Optional expiration

        # Store model class for later use
        self._TrustChain = TrustChain

        # Runtime for executing workflows
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self.runtime = AsyncLocalRuntime()
            self._owns_runtime = True

        # Track initialization state
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the trust store.

        This performs any necessary schema migrations and prepares
        the database for operations.

        Must be called before using the store.
        """
        if self._initialized:
            return

        # DataFlow automatically handles schema creation on first operation
        # No explicit initialization needed due to deferred schema operations
        self._initialized = True

    async def store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Store a trust lineage chain.

        If a chain with the same agent_id already exists, it will be updated.
        Uses the Upsert operation for atomic insert-or-update.

        Args:
            chain: The TrustLineageChain to store
            expires_at: Optional expiration datetime

        Returns:
            The agent_id of the stored chain

        Raises:
            TrustChainInvalidError: If chain validation fails
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Validate chain before storing
            if chain.is_expired():
                raise TrustChainInvalidError(
                    f"Cannot store expired trust chain for agent {chain.genesis.agent_id}"
                )

            # Serialize chain to dictionary
            chain_dict = chain.to_dict()

            # Build workflow using TrustChain_Upsert node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TrustChain_Upsert",
                "upsert_chain",
                {
                    "where": {"id": chain.genesis.agent_id},
                    "conflict_on": ["id"],  # Conflict detection on agent_id
                    "update": {
                        "chain_data": chain_dict,
                        "chain_hash": chain.hash(),
                        "is_active": True,
                    },
                    "create": {
                        "id": chain.genesis.agent_id,
                        "chain_data": chain_dict,
                        "chain_hash": chain.hash(),
                        "authority_id": chain.genesis.authority_id,
                        "is_active": True,
                        "expires_at": expires_at,
                    },
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Invalidate cache for this agent_id
            if self.enable_cache:
                await self._invalidate_cache(chain.genesis.agent_id)

            return chain.genesis.agent_id

        except Exception as e:
            if isinstance(e, (TrustChainInvalidError, TrustStoreDatabaseError)):
                raise
            raise TrustStoreDatabaseError(
                f"Failed to store trust chain for agent {chain.genesis.agent_id}: {str(e)}"
            ) from e

    async def get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """
        Retrieve a trust lineage chain by agent_id.

        Uses caching for <1ms performance on cache hits.

        Args:
            agent_id: The agent ID to retrieve
            include_inactive: Include soft-deleted chains (default: False)

        Returns:
            The TrustLineageChain for the agent

        Raises:
            TrustChainNotFoundError: If chain not found
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Build workflow using TrustChain_Read node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TrustChain_Read",
                "read_chain",
                {"id": agent_id},
            )

            # Execute workflow (DataFlow handles caching automatically)
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Access result using string-based pattern
            chain_record = results.get("read_chain", {}).get("result")

            if not chain_record:
                raise TrustChainNotFoundError(
                    f"Trust chain not found for agent: {agent_id}"
                )

            # Check soft delete flag
            if not include_inactive and not chain_record.get("is_active", True):
                raise TrustChainNotFoundError(
                    f"Trust chain not found for agent: {agent_id} (inactive)"
                )

            # Deserialize chain from JSONB
            chain_data = chain_record["chain_data"]
            return TrustLineageChain.from_dict(chain_data)

        except TrustChainNotFoundError:
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to retrieve trust chain for agent {agent_id}: {str(e)}"
            ) from e

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
            TrustChainInvalidError: If chain validation fails
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Validate chain before updating
            if chain.is_expired():
                raise TrustChainInvalidError(
                    f"Cannot update with expired trust chain for agent {agent_id}"
                )

            # Verify chain exists first
            await self.get_chain(agent_id)

            # Serialize chain to dictionary
            chain_dict = chain.to_dict()

            # Build workflow using TrustChain_Update node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TrustChain_Update",
                "update_chain",
                {
                    "filter": {"id": agent_id},
                    "fields": {
                        "chain_data": chain_dict,
                        "chain_hash": chain.hash(),
                    },
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Invalidate cache
            if self.enable_cache:
                await self._invalidate_cache(agent_id)

        except (TrustChainNotFoundError, TrustChainInvalidError):
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to update trust chain for agent {agent_id}: {str(e)}"
            ) from e

    async def delete_chain(
        self,
        agent_id: str,
        soft_delete: bool = True,
    ) -> None:
        """
        Delete a trust lineage chain.

        Args:
            agent_id: The agent ID to delete
            soft_delete: Use soft delete (set is_active=False) vs hard delete (default: True)

        Raises:
            TrustChainNotFoundError: If chain not found
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Verify chain exists first
            await self.get_chain(agent_id)

            workflow = WorkflowBuilder()

            if soft_delete:
                # Soft delete: Set is_active = False
                workflow.add_node(
                    "TrustChain_Update",
                    "soft_delete_chain",
                    {
                        "filter": {"id": agent_id},
                        "fields": {"is_active": False},
                    },
                )
            else:
                # Hard delete: Remove from database
                workflow.add_node(
                    "TrustChain_Delete",
                    "delete_chain",
                    {"id": agent_id},
                )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Invalidate cache
            if self.enable_cache:
                await self._invalidate_cache(agent_id)

        except TrustChainNotFoundError:
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to delete trust chain for agent {agent_id}: {str(e)}"
            ) from e

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
            active_only: Include only active chains (default: True)
            limit: Maximum number of results (default: 100)
            offset: Offset for pagination (default: 0)

        Returns:
            List of TrustLineageChain objects

        Raises:
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Build filter conditions
            filters = {}
            if authority_id:
                filters["authority_id"] = authority_id
            if active_only:
                filters["is_active"] = True

            # Build workflow using TrustChain_List node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TrustChain_List",
                "list_chains",
                {
                    "filter": filters if filters else {},
                    "limit": limit,
                    "offset": offset,
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Access results using string-based pattern
            records = results.get("list_chains", {}).get("records", [])

            # Deserialize chains from JSONB
            chains = []
            for record in records:
                chain_data = record["chain_data"]
                chains.append(TrustLineageChain.from_dict(chain_data))

            return chains

        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to list trust chains: {str(e)}"
            ) from e

    async def count_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
    ) -> int:
        """
        Count trust lineage chains with filtering.

        Args:
            authority_id: Filter by authority ID (optional)
            active_only: Include only active chains (default: True)

        Returns:
            Number of matching chains

        Raises:
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Build filter conditions
            filters = {}
            if authority_id:
                filters["authority_id"] = authority_id
            if active_only:
                filters["is_active"] = True

            # Build workflow using TrustChain_Count node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TrustChain_Count",
                "count_chains",
                {"filter": filters if filters else {}},
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Access count result
            return results.get("count_chains", {}).get("count", 0)

        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to count trust chains: {str(e)}"
            ) from e

    async def verify_chain_integrity(self, agent_id: str) -> bool:
        """
        Verify the integrity of a stored trust chain.

        Compares the stored chain_hash with a freshly computed hash
        to detect any tampering or corruption.

        Args:
            agent_id: The agent ID to verify

        Returns:
            True if integrity is verified, False otherwise

        Raises:
            TrustChainNotFoundError: If chain not found
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Retrieve chain from database
            chain = await self.get_chain(agent_id)

            # Read stored hash
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TrustChain_Read",
                "read_hash",
                {"id": agent_id},
            )

            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            stored_hash = (
                results.get("read_hash", {}).get("result", {}).get("chain_hash")
            )

            # Compare with freshly computed hash
            computed_hash = chain.hash()

            return stored_hash == computed_hash

        except TrustChainNotFoundError:
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to verify chain integrity for agent {agent_id}: {str(e)}"
            ) from e

    async def _invalidate_cache(self, agent_id: str) -> None:
        """
        Invalidate cache for a specific agent_id.

        This is called automatically after store/update/delete operations
        when caching is enabled.

        Args:
            agent_id: The agent ID to invalidate
        """
        # DataFlow handles cache invalidation automatically
        # This method is a placeholder for explicit invalidation if needed
        pass

    async def close(self) -> None:
        """
        Close database connections and cleanup resources.

        Should be called when shutting down the application.
        """
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()
            self.runtime = None

    def __del__(self):
        if getattr(self, "runtime", None) is not None:
            import warnings

            warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.runtime.release()
                self.runtime = None
            except Exception:
                pass
