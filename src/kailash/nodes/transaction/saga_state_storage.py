"""Saga State Storage implementations for persistence and recovery.

Provides different storage backends for saga state persistence including
in-memory, Redis, and database storage options.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SagaStateStorage(ABC):
    """Abstract base class for saga state storage implementations."""

    @abstractmethod
    async def save_state(self, saga_id: str, state_data: Dict[str, Any]) -> bool:
        """Save saga state."""
        pass

    @abstractmethod
    async def load_state(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """Load saga state."""
        pass

    @abstractmethod
    async def delete_state(self, saga_id: str) -> bool:
        """Delete saga state."""
        pass

    @abstractmethod
    async def list_sagas(
        self, filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """List saga IDs matching criteria."""
        pass


class InMemoryStateStorage(SagaStateStorage):
    """In-memory saga state storage for development and testing."""

    def __init__(self):
        self._storage: Dict[str, Dict[str, Any]] = {}

    async def save_state(self, saga_id: str, state_data: Dict[str, Any]) -> bool:
        """Save saga state to memory."""
        try:
            self._storage[saga_id] = state_data
            return True
        except Exception as e:
            logger.error(f"Failed to save state for saga {saga_id}: {e}")
            return False

    async def load_state(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """Load saga state from memory."""
        return self._storage.get(saga_id)

    async def delete_state(self, saga_id: str) -> bool:
        """Delete saga state from memory."""
        if saga_id in self._storage:
            del self._storage[saga_id]
            return True
        return False

    async def list_sagas(
        self, filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """List saga IDs in memory."""
        if not filter_criteria:
            return list(self._storage.keys())

        # Simple filtering
        result = []
        for saga_id, state in self._storage.items():
            match = True
            for key, value in filter_criteria.items():
                if state.get(key) != value:
                    match = False
                    break
            if match:
                result.append(saga_id)
        return result


class RedisStateStorage(SagaStateStorage):
    """Redis-based saga state storage for distributed systems."""

    def __init__(self, redis_client: Any, key_prefix: str = "saga:state:"):
        """Initialize Redis storage.

        Args:
            redis_client: Redis client instance (can be sync or async)
            key_prefix: Prefix for Redis keys
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        # Detect if client is async by checking for execute method or common async methods
        self.is_async_client = hasattr(redis_client, "execute") or hasattr(
            redis_client, "aset"
        )

    async def save_state(self, saga_id: str, state_data: Dict[str, Any]) -> bool:
        """Save saga state to Redis."""
        try:
            key = f"{self.key_prefix}{saga_id}"

            # Add metadata
            state_data["_last_updated"] = datetime.now(UTC).isoformat()

            # Serialize to JSON
            json_data = json.dumps(state_data)

            if self.is_async_client:
                # Use async Redis client
                if state_data.get("state") in ["completed", "compensated"]:
                    await self.redis.setex(key, 604800, json_data)  # 7 days
                else:
                    await self.redis.set(key, json_data)

                # Add to saga index
                await self.redis.sadd(f"{self.key_prefix}index", saga_id)

                # Add to state-specific index
                state = state_data.get("state", "unknown")
                await self.redis.sadd(f"{self.key_prefix}state:{state}", saga_id)
            else:
                # Use sync Redis client
                if state_data.get("state") in ["completed", "compensated"]:
                    self.redis.setex(key, 604800, json_data)  # 7 days
                else:
                    self.redis.set(key, json_data)

                # Add to saga index
                self.redis.sadd(f"{self.key_prefix}index", saga_id)

                # Add to state-specific index
                state = state_data.get("state", "unknown")
                self.redis.sadd(f"{self.key_prefix}state:{state}", saga_id)

            return True

        except Exception as e:
            logger.error(f"Failed to save state to Redis for saga {saga_id}: {e}")
            return False

    async def load_state(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """Load saga state from Redis."""
        try:
            key = f"{self.key_prefix}{saga_id}"

            if self.is_async_client:
                json_data = await self.redis.get(key)
            else:
                json_data = self.redis.get(key)

            if json_data:
                return json.loads(json_data)
            return None

        except Exception as e:
            logger.error(f"Failed to load state from Redis for saga {saga_id}: {e}")
            return None

    async def delete_state(self, saga_id: str) -> bool:
        """Delete saga state from Redis."""
        try:
            key = f"{self.key_prefix}{saga_id}"

            # Get current state for index cleanup
            state_data = await self.load_state(saga_id)

            # Delete the state
            if self.is_async_client:
                deleted = await self.redis.delete(key) > 0
            else:
                deleted = self.redis.delete(key) > 0

            if deleted:
                # Remove from indexes
                if self.is_async_client:
                    await self.redis.srem(f"{self.key_prefix}index", saga_id)

                    if state_data:
                        state = state_data.get("state", "unknown")
                        await self.redis.srem(
                            f"{self.key_prefix}state:{state}", saga_id
                        )
                else:
                    self.redis.srem(f"{self.key_prefix}index", saga_id)

                    if state_data:
                        state = state_data.get("state", "unknown")
                        self.redis.srem(f"{self.key_prefix}state:{state}", saga_id)

            return deleted

        except Exception as e:
            logger.error(f"Failed to delete state from Redis for saga {saga_id}: {e}")
            return False

    async def list_sagas(
        self, filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """List saga IDs from Redis."""
        try:
            if not filter_criteria:
                # Return all saga IDs
                if self.is_async_client:
                    saga_ids = await self.redis.smembers(f"{self.key_prefix}index")
                else:
                    saga_ids = self.redis.smembers(f"{self.key_prefix}index")
                return list(saga_ids)

            # Filter by state if specified
            if "state" in filter_criteria:
                state = filter_criteria["state"]
                if self.is_async_client:
                    saga_ids = await self.redis.smembers(
                        f"{self.key_prefix}state:{state}"
                    )
                else:
                    saga_ids = self.redis.smembers(f"{self.key_prefix}state:{state}")
                return list(saga_ids)

            # For other criteria, load and filter
            if self.is_async_client:
                all_saga_ids = await self.redis.smembers(f"{self.key_prefix}index")
            else:
                all_saga_ids = self.redis.smembers(f"{self.key_prefix}index")

            result = []

            for saga_id in all_saga_ids:
                state_data = await self.load_state(saga_id)
                if state_data:
                    match = True
                    for key, value in filter_criteria.items():
                        if state_data.get(key) != value:
                            match = False
                            break
                    if match:
                        result.append(saga_id)

            return result

        except Exception as e:
            logger.error(f"Failed to list sagas from Redis: {e}")
            return []


class DatabaseStateStorage(SagaStateStorage):
    """Database-based saga state storage for persistent storage."""

    def __init__(self, db_pool: Any, table_name: str = "saga_states"):
        """Initialize database storage.

        Args:
            db_pool: Database connection pool
            table_name: Name of the table for saga states
        """
        self.db_pool = db_pool
        self.table_name = table_name
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Ensure the saga states table exists."""
        # Table creation is handled externally in tests
        # In production, this would use proper database migrations
        pass

    async def save_state(self, saga_id: str, state_data: Dict[str, Any]) -> bool:
        """Save saga state to database."""
        try:
            async with self.db_pool.acquire() as conn:
                # PostgreSQL example with JSONB
                query = f"""
                INSERT INTO {self.table_name}
                    (saga_id, saga_name, state, state_data, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (saga_id)
                DO UPDATE SET
                    saga_name = EXCLUDED.saga_name,
                    state = EXCLUDED.state,
                    state_data = EXCLUDED.state_data,
                    updated_at = EXCLUDED.updated_at
                """

                await conn.execute(
                    query,
                    saga_id,
                    state_data.get("saga_name", ""),
                    state_data.get("state", ""),
                    json.dumps(state_data),
                    datetime.now(UTC),
                )

                return True

        except Exception as e:
            logger.error(f"Failed to save state to database for saga {saga_id}: {e}")
            return False

    async def load_state(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """Load saga state from database."""
        try:
            async with self.db_pool.acquire() as conn:
                query = f"""
                SELECT state_data
                FROM {self.table_name}
                WHERE saga_id = $1
                """

                row = await conn.fetchrow(query, saga_id)

                if row:
                    return json.loads(row["state_data"])
                return None

        except Exception as e:
            logger.error(f"Failed to load state from database for saga {saga_id}: {e}")
            return None

    async def delete_state(self, saga_id: str) -> bool:
        """Delete saga state from database."""
        try:
            async with self.db_pool.acquire() as conn:
                query = f"DELETE FROM {self.table_name} WHERE saga_id = $1"
                result = await conn.execute(query, saga_id)

                # Check if any rows were deleted
                return result.split()[-1] != "0"

        except Exception as e:
            logger.error(
                f"Failed to delete state from database for saga {saga_id}: {e}"
            )
            return False

    async def list_sagas(
        self, filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """List saga IDs from database."""
        try:
            async with self.db_pool.acquire() as conn:
                if not filter_criteria:
                    query = f"SELECT saga_id FROM {self.table_name}"
                    rows = await conn.fetch(query)
                else:
                    # Build WHERE clause
                    conditions = []
                    params = []
                    param_count = 0

                    for key, value in filter_criteria.items():
                        param_count += 1
                        if key in ["state", "saga_name"]:
                            conditions.append(f"{key} = ${param_count}")
                            params.append(value)
                        else:
                            # For other fields, use JSONB query
                            conditions.append(f"state_data->'{key}' = ${param_count}")
                            params.append(json.dumps(value))

                    where_clause = " AND ".join(conditions)
                    query = (
                        f"SELECT saga_id FROM {self.table_name} WHERE {where_clause}"
                    )
                    rows = await conn.fetch(query, *params)

                return [row["saga_id"] for row in rows]

        except Exception as e:
            logger.error(f"Failed to list sagas from database: {e}")
            return []


class StorageFactory:
    """Factory for creating saga state storage instances."""

    @staticmethod
    def create_storage(storage_type: str, **kwargs) -> SagaStateStorage:
        """Create a storage instance based on type.

        Args:
            storage_type: Type of storage ("memory", "redis", "database")
            **kwargs: Additional arguments for storage initialization

        Returns:
            SagaStateStorage instance
        """
        if storage_type == "memory":
            return InMemoryStateStorage()
        elif storage_type == "redis":
            redis_client = kwargs.get("redis_client")
            if not redis_client:
                raise ValueError("redis_client is required for Redis storage")
            return RedisStateStorage(
                redis_client, kwargs.get("key_prefix", "saga:state:")
            )
        elif storage_type == "database":
            db_pool = kwargs.get("db_pool")
            if not db_pool:
                raise ValueError("db_pool is required for database storage")
            return DatabaseStateStorage(
                db_pool,
                kwargs.get("saga_table_name", kwargs.get("table_name", "saga_states")),
            )
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
