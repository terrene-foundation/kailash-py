# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Agent Registry Store - Persistence layer for agent registry.

This module provides the storage interface and implementations for
persisting agent metadata in the registry.

Key Components:
- AgentRegistryStore: Abstract interface for registry storage
- PostgresAgentRegistryStore: PostgreSQL implementation with optimized indexes
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from kailash.trust.registry.exceptions import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
    RegistryStoreError,
)
from kailash.trust.registry.models import AgentMetadata, AgentStatus

logger = logging.getLogger(__name__)


class AgentRegistryStore(ABC):
    """
    Abstract interface for agent registry storage.

    This interface defines the contract for storing and retrieving
    agent metadata. Implementations can use different backends
    (PostgreSQL, SQLite, in-memory, etc.).

    All methods are async to support non-blocking I/O.
    """

    @abstractmethod
    async def register_agent(self, metadata: AgentMetadata) -> None:
        """
        Register a new agent in the registry.

        Args:
            metadata: Complete metadata for the agent to register.
                The agent_id must be unique.

        Raises:
            AgentAlreadyRegisteredError: If an agent with the same
                agent_id already exists in the registry.
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def update_agent(self, agent_id: str, metadata: AgentMetadata) -> None:
        """
        Update an existing agent's metadata.

        Args:
            agent_id: ID of the agent to update.
            metadata: New metadata to replace the existing metadata.
                The agent_id in metadata should match the agent_id parameter.

        Raises:
            AgentNotFoundError: If the agent doesn't exist.
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        """
        Retrieve an agent's metadata by ID.

        Args:
            agent_id: ID of the agent to retrieve.

        Returns:
            AgentMetadata if found, None otherwise.

        Raises:
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def delete_agent(self, agent_id: str) -> None:
        """
        Remove an agent from the registry.

        Args:
            agent_id: ID of the agent to remove.

        Raises:
            AgentNotFoundError: If the agent doesn't exist.
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def find_by_capability(self, capability: str) -> List[AgentMetadata]:
        """
        Find all agents with a specific capability.

        Args:
            capability: The capability to search for.

        Returns:
            List of agents that have the capability.
            Empty list if none found.

        Raises:
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def find_by_status(self, status: AgentStatus) -> List[AgentMetadata]:
        """
        Find all agents with a specific status.

        Args:
            status: The status to filter by.

        Returns:
            List of agents with the specified status.
            Empty list if none found.

        Raises:
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def list_all(self) -> List[AgentMetadata]:
        """
        Retrieve all registered agents.

        Returns:
            List of all agents in the registry.
            Empty list if registry is empty.

        Raises:
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def update_last_seen(self, agent_id: str, timestamp: datetime) -> None:
        """
        Update an agent's last_seen timestamp.

        This is a lightweight operation for heartbeat updates.

        Args:
            agent_id: ID of the agent to update.
            timestamp: New last_seen timestamp.

        Raises:
            AgentNotFoundError: If the agent doesn't exist.
            RegistryStoreError: If a database error occurs.
        """
        pass

    @abstractmethod
    async def update_status(self, agent_id: str, status: AgentStatus) -> None:
        """
        Update an agent's status.

        Args:
            agent_id: ID of the agent to update.
            status: New status value.

        Raises:
            AgentNotFoundError: If the agent doesn't exist.
            RegistryStoreError: If a database error occurs.
        """
        pass


class PostgresAgentRegistryStore(AgentRegistryStore):
    """
    PostgreSQL implementation of AgentRegistryStore.

    Uses JSONB columns for capabilities and constraints to enable
    efficient querying with GIN indexes.

    Schema:
        CREATE TABLE agent_registry (
            agent_id TEXT PRIMARY KEY,
            agent_type TEXT NOT NULL,
            capabilities JSONB NOT NULL,
            constraints JSONB NOT NULL,
            status TEXT NOT NULL,
            trust_chain_hash TEXT NOT NULL,
            registered_at TIMESTAMP NOT NULL,
            last_seen TIMESTAMP NOT NULL,
            metadata JSONB,
            endpoint TEXT,
            public_key TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_agent_capabilities ON agent_registry USING gin(capabilities);
        CREATE INDEX idx_agent_status ON agent_registry(status);
        CREATE INDEX idx_agent_type ON agent_registry(agent_type);
        CREATE INDEX idx_last_seen ON agent_registry(last_seen DESC);

    Example:
        >>> store = PostgresAgentRegistryStore(
        ...     connection_string="postgresql://user:pass@localhost/db"
        ... )
        >>> await store.initialize()
        >>> await store.register_agent(metadata)
    """

    # SQL for table creation
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS agent_registry (
        agent_id TEXT PRIMARY KEY,
        agent_type TEXT NOT NULL,
        capabilities JSONB NOT NULL,
        constraints JSONB NOT NULL,
        status TEXT NOT NULL,
        trust_chain_hash TEXT NOT NULL,
        registered_at TIMESTAMP NOT NULL,
        last_seen TIMESTAMP NOT NULL,
        metadata JSONB,
        endpoint TEXT,
        public_key TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """

    CREATE_INDEXES_SQL = """
    CREATE INDEX IF NOT EXISTS idx_agent_capabilities ON agent_registry USING gin(capabilities);
    CREATE INDEX IF NOT EXISTS idx_agent_status ON agent_registry(status);
    CREATE INDEX IF NOT EXISTS idx_agent_type ON agent_registry(agent_type);
    CREATE INDEX IF NOT EXISTS idx_last_seen ON agent_registry(last_seen DESC);
    CREATE INDEX IF NOT EXISTS idx_status_type ON agent_registry(status, agent_type);
    """

    def __init__(self, connection_string: str):
        """
        Initialize the PostgreSQL registry store.

        Args:
            connection_string: PostgreSQL connection string.
                Format: postgresql://user:password@host:port/database
        """
        self._connection_string = connection_string
        self._pool = None

    async def initialize(self) -> None:
        """
        Initialize the database connection pool and create tables.

        Call this method before using the store.

        Raises:
            RegistryStoreError: If database connection fails.
        """
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self._connection_string,
                min_size=2,
                max_size=10,
            )

            # Create tables and indexes
            async with self._pool.acquire() as conn:
                await conn.execute(self.CREATE_TABLE_SQL)
                await conn.execute(self.CREATE_INDEXES_SQL)

            logger.info("PostgresAgentRegistryStore initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize PostgresAgentRegistryStore: {e}")
            raise RegistryStoreError("initialize", f"Database initialization failed: {e}", e)

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgresAgentRegistryStore closed")

    async def register_agent(self, metadata: AgentMetadata) -> None:
        """Register a new agent in the registry."""
        if not self._pool:
            raise RegistryStoreError("register_agent", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_registry (
                        agent_id, agent_type, capabilities, constraints,
                        status, trust_chain_hash, registered_at, last_seen,
                        metadata, endpoint, public_key
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    metadata.agent_id,
                    metadata.agent_type,
                    json.dumps(metadata.capabilities),
                    json.dumps(metadata.constraints),
                    metadata.status.value,
                    metadata.trust_chain_hash,
                    metadata.registered_at,
                    metadata.last_seen,
                    json.dumps(metadata.metadata),
                    metadata.endpoint,
                    metadata.public_key,
                )

            logger.info(f"Registered agent: {metadata.agent_id}")

        except Exception as e:
            if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
                raise AgentAlreadyRegisteredError(metadata.agent_id)
            raise RegistryStoreError("register_agent", f"Failed to register agent: {e}", e)

    async def update_agent(self, agent_id: str, metadata: AgentMetadata) -> None:
        """Update an existing agent's metadata."""
        if not self._pool:
            raise RegistryStoreError("update_agent", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE agent_registry SET
                        agent_type = $2,
                        capabilities = $3,
                        constraints = $4,
                        status = $5,
                        trust_chain_hash = $6,
                        last_seen = $7,
                        metadata = $8,
                        endpoint = $9,
                        public_key = $10,
                        updated_at = NOW()
                    WHERE agent_id = $1
                    """,
                    agent_id,
                    metadata.agent_type,
                    json.dumps(metadata.capabilities),
                    json.dumps(metadata.constraints),
                    metadata.status.value,
                    metadata.trust_chain_hash,
                    metadata.last_seen,
                    json.dumps(metadata.metadata),
                    metadata.endpoint,
                    metadata.public_key,
                )

                if result == "UPDATE 0":
                    raise AgentNotFoundError(agent_id)

            logger.debug(f"Updated agent: {agent_id}")

        except AgentNotFoundError:
            raise
        except Exception as e:
            raise RegistryStoreError("update_agent", f"Failed to update agent: {e}", e)

    async def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        """Retrieve an agent's metadata by ID."""
        if not self._pool:
            raise RegistryStoreError("get_agent", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT agent_id, agent_type, capabilities, constraints,
                           status, trust_chain_hash, registered_at, last_seen,
                           metadata, endpoint, public_key
                    FROM agent_registry
                    WHERE agent_id = $1
                    """,
                    agent_id,
                )

                if not row:
                    return None

                return self._row_to_metadata(row)

        except Exception as e:
            raise RegistryStoreError("get_agent", f"Failed to get agent: {e}", e)

    async def delete_agent(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        if not self._pool:
            raise RegistryStoreError("delete_agent", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM agent_registry WHERE agent_id = $1",
                    agent_id,
                )

                if result == "DELETE 0":
                    raise AgentNotFoundError(agent_id)

            logger.info(f"Deleted agent: {agent_id}")

        except AgentNotFoundError:
            raise
        except Exception as e:
            raise RegistryStoreError("delete_agent", f"Failed to delete agent: {e}", e)

    async def find_by_capability(self, capability: str) -> List[AgentMetadata]:
        """Find all agents with a specific capability."""
        if not self._pool:
            raise RegistryStoreError("find_by_capability", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                # Use JSONB containment operator with GIN index
                rows = await conn.fetch(
                    """
                    SELECT agent_id, agent_type, capabilities, constraints,
                           status, trust_chain_hash, registered_at, last_seen,
                           metadata, endpoint, public_key
                    FROM agent_registry
                    WHERE capabilities @> $1::jsonb
                    ORDER BY last_seen DESC
                    """,
                    json.dumps([capability]),
                )

                return [self._row_to_metadata(row) for row in rows]

        except Exception as e:
            raise RegistryStoreError("find_by_capability", f"Failed to find by capability: {e}", e)

    async def find_by_status(self, status: AgentStatus) -> List[AgentMetadata]:
        """Find all agents with a specific status."""
        if not self._pool:
            raise RegistryStoreError("find_by_status", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT agent_id, agent_type, capabilities, constraints,
                           status, trust_chain_hash, registered_at, last_seen,
                           metadata, endpoint, public_key
                    FROM agent_registry
                    WHERE status = $1
                    ORDER BY last_seen DESC
                    """,
                    status.value,
                )

                return [self._row_to_metadata(row) for row in rows]

        except Exception as e:
            raise RegistryStoreError("find_by_status", f"Failed to find by status: {e}", e)

    async def list_all(self) -> List[AgentMetadata]:
        """Retrieve all registered agents."""
        if not self._pool:
            raise RegistryStoreError("list_all", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT agent_id, agent_type, capabilities, constraints,
                           status, trust_chain_hash, registered_at, last_seen,
                           metadata, endpoint, public_key
                    FROM agent_registry
                    ORDER BY registered_at DESC
                    """
                )

                return [self._row_to_metadata(row) for row in rows]

        except Exception as e:
            raise RegistryStoreError("list_all", f"Failed to list all agents: {e}", e)

    async def update_last_seen(self, agent_id: str, timestamp: datetime) -> None:
        """Update an agent's last_seen timestamp."""
        if not self._pool:
            raise RegistryStoreError("update_last_seen", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE agent_registry
                    SET last_seen = $2, updated_at = NOW()
                    WHERE agent_id = $1
                    """,
                    agent_id,
                    timestamp,
                )

                if result == "UPDATE 0":
                    raise AgentNotFoundError(agent_id)

        except AgentNotFoundError:
            raise
        except Exception as e:
            raise RegistryStoreError("update_last_seen", f"Failed to update last_seen: {e}", e)

    async def update_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update an agent's status."""
        if not self._pool:
            raise RegistryStoreError("update_status", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE agent_registry
                    SET status = $2, updated_at = NOW()
                    WHERE agent_id = $1
                    """,
                    agent_id,
                    status.value,
                )

                if result == "UPDATE 0":
                    raise AgentNotFoundError(agent_id)

            logger.info(f"Updated status for agent {agent_id}: {status.value}")

        except AgentNotFoundError:
            raise
        except Exception as e:
            raise RegistryStoreError("update_status", f"Failed to update status: {e}", e)

    async def find_by_capabilities(
        self,
        capabilities: List[str],
        match_all: bool = True,
    ) -> List[AgentMetadata]:
        """
        Find agents by multiple capabilities.

        Args:
            capabilities: List of capabilities to search for.
            match_all: If True, agent must have ALL capabilities.
                      If False, agent must have ANY capability.

        Returns:
            List of matching agents, sorted by last_seen.
        """
        if not self._pool:
            raise RegistryStoreError("find_by_capabilities", "Store not initialized")

        if not capabilities:
            return []

        try:
            async with self._pool.acquire() as conn:
                if match_all:
                    # Agent must have ALL capabilities
                    rows = await conn.fetch(
                        """
                        SELECT agent_id, agent_type, capabilities, constraints,
                               status, trust_chain_hash, registered_at, last_seen,
                               metadata, endpoint, public_key
                        FROM agent_registry
                        WHERE capabilities @> $1::jsonb
                        ORDER BY last_seen DESC
                        """,
                        json.dumps(capabilities),
                    )
                else:
                    # Agent must have ANY capability
                    # Build query with multiple containment checks
                    conditions = " OR ".join(["capabilities @> ${i + 1}::jsonb" for i in range(len(capabilities))])
                    query = f"""
                        SELECT agent_id, agent_type, capabilities, constraints,
                               status, trust_chain_hash, registered_at, last_seen,
                               metadata, endpoint, public_key
                        FROM agent_registry
                        WHERE {conditions}
                        ORDER BY last_seen DESC
                    """
                    params = [json.dumps([cap]) for cap in capabilities]
                    rows = await conn.fetch(query, *params)

                return [self._row_to_metadata(row) for row in rows]

        except Exception as e:
            raise RegistryStoreError("find_by_capabilities", f"Failed to find by capabilities: {e}", e)

    async def find_stale_agents(self, timeout_seconds: int) -> List[AgentMetadata]:
        """
        Find agents that haven't been seen recently.

        Args:
            timeout_seconds: Number of seconds without activity to consider stale.

        Returns:
            List of stale agents.
        """
        if not self._pool:
            raise RegistryStoreError("find_stale_agents", "Store not initialized")

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT agent_id, agent_type, capabilities, constraints,
                           status, trust_chain_hash, registered_at, last_seen,
                           metadata, endpoint, public_key
                    FROM agent_registry
                    WHERE status = 'ACTIVE'
                    AND last_seen < NOW() - INTERVAL '1 second' * $1
                    ORDER BY last_seen ASC
                    """,
                    timeout_seconds,
                )

                return [self._row_to_metadata(row) for row in rows]

        except Exception as e:
            raise RegistryStoreError("find_stale_agents", f"Failed to find stale agents: {e}", e)

    def _row_to_metadata(self, row) -> AgentMetadata:
        """Convert a database row to AgentMetadata."""
        return AgentMetadata(
            agent_id=row["agent_id"],
            agent_type=row["agent_type"],
            capabilities=(
                json.loads(row["capabilities"]) if isinstance(row["capabilities"], str) else row["capabilities"]
            ),
            constraints=(json.loads(row["constraints"]) if isinstance(row["constraints"], str) else row["constraints"]),
            status=AgentStatus(row["status"]),
            trust_chain_hash=row["trust_chain_hash"],
            registered_at=row["registered_at"],
            last_seen=row["last_seen"],
            metadata=(json.loads(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or {})),
            endpoint=row["endpoint"],
            public_key=row["public_key"],
        )


class InMemoryAgentRegistryStore(AgentRegistryStore):
    """
    In-memory implementation of AgentRegistryStore for testing.

    This implementation stores agents in a dictionary and is useful
    for unit tests where database access is not needed.
    """

    def __init__(self):
        self._agents: dict[str, AgentMetadata] = {}

    async def register_agent(self, metadata: AgentMetadata) -> None:
        if metadata.agent_id in self._agents:
            raise AgentAlreadyRegisteredError(metadata.agent_id)
        self._agents[metadata.agent_id] = metadata

    async def update_agent(self, agent_id: str, metadata: AgentMetadata) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        self._agents[agent_id] = metadata

    async def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        return self._agents.get(agent_id)

    async def delete_agent(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        del self._agents[agent_id]

    async def find_by_capability(self, capability: str) -> List[AgentMetadata]:
        return sorted(
            [a for a in self._agents.values() if capability in a.capabilities],
            key=lambda a: a.last_seen,
            reverse=True,
        )

    async def find_by_status(self, status: AgentStatus) -> List[AgentMetadata]:
        return sorted(
            [a for a in self._agents.values() if a.status == status],
            key=lambda a: a.last_seen,
            reverse=True,
        )

    async def list_all(self) -> List[AgentMetadata]:
        return sorted(
            list(self._agents.values()),
            key=lambda a: a.registered_at,
            reverse=True,
        )

    async def update_last_seen(self, agent_id: str, timestamp: datetime) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        agent = self._agents[agent_id]
        self._agents[agent_id] = AgentMetadata(
            agent_id=agent.agent_id,
            agent_type=agent.agent_type,
            capabilities=agent.capabilities,
            constraints=agent.constraints,
            status=agent.status,
            trust_chain_hash=agent.trust_chain_hash,
            registered_at=agent.registered_at,
            last_seen=timestamp,
            metadata=agent.metadata,
            endpoint=agent.endpoint,
            public_key=agent.public_key,
        )

    async def update_status(self, agent_id: str, status: AgentStatus) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        agent = self._agents[agent_id]
        self._agents[agent_id] = AgentMetadata(
            agent_id=agent.agent_id,
            agent_type=agent.agent_type,
            capabilities=agent.capabilities,
            constraints=agent.constraints,
            status=status,
            trust_chain_hash=agent.trust_chain_hash,
            registered_at=agent.registered_at,
            last_seen=agent.last_seen,
            metadata=agent.metadata,
            endpoint=agent.endpoint,
            public_key=agent.public_key,
        )

    async def find_by_capabilities(
        self,
        capabilities: List[str],
        match_all: bool = True,
    ) -> List[AgentMetadata]:
        def matches(agent: AgentMetadata) -> bool:
            if match_all:
                return all(cap in agent.capabilities for cap in capabilities)
            else:
                return any(cap in agent.capabilities for cap in capabilities)

        return sorted(
            [a for a in self._agents.values() if matches(a)],
            key=lambda a: a.last_seen,
            reverse=True,
        )

    async def find_stale_agents(self, timeout_seconds: int) -> List[AgentMetadata]:
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        return sorted(
            [a for a in self._agents.values() if a.status == AgentStatus.ACTIVE and a.last_seen < cutoff],
            key=lambda a: a.last_seen,
        )
