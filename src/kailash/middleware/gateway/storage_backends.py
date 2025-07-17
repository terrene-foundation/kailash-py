"""Storage backend implementations for middleware components."""

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

try:
    import redis.asyncio as redis
except ImportError:
    try:
        import aioredis as redis
    except ImportError:
        redis = None
import asyncpg


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save(self, key: str, data: bytes) -> None:
        """Save data to storage."""
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[bytes]:
        """Load data from storage."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete data from storage."""
        pass

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> List[str]:
        """List keys with optional prefix."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close storage connection."""
        pass


class RedisStorage(StorageBackend):
    """Redis-based storage backend."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        key_prefix: str = "kailash:",
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.key_prefix = key_prefix
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self._redis is None:
            self._redis = await redis.from_url(
                f"redis://{self.host}:{self.port}",
                db=self.db,
                password=self.password,
                decode_responses=False,
            )
        return self._redis

    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.key_prefix}{key}"

    async def save(self, key: str, data: bytes) -> None:
        """Save data to Redis."""
        redis = await self._get_redis()
        await redis.set(self._make_key(key), data)

    async def load(self, key: str) -> Optional[bytes]:
        """Load data from Redis."""
        redis = await self._get_redis()
        return await redis.get(self._make_key(key))

    async def delete(self, key: str) -> None:
        """Delete data from Redis."""
        redis = await self._get_redis()
        await redis.delete(self._make_key(key))

    async def list_keys(self, prefix: str = "") -> List[str]:
        """List keys with prefix."""
        redis = await self._get_redis()
        pattern = self._make_key(f"{prefix}*")
        keys = await redis.keys(pattern)

        # Remove prefix from keys
        prefix_len = len(self.key_prefix)
        return [key.decode()[prefix_len:] for key in keys]

    async def append(self, key: str, data: List[Dict[str, Any]]) -> None:
        """Append data to a Redis list."""
        redis = await self._get_redis()
        serialized_data = [json.dumps(item) for item in data]
        await redis.lpush(self._make_key(key), *serialized_data)

    async def get(self, key: str) -> List[Dict[str, Any]]:
        """Get data from Redis list."""
        redis = await self._get_redis()
        data = await redis.lrange(self._make_key(key), 0, -1)
        return [json.loads(item) for item in reversed(data)]

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class PostgreSQLStorage(StorageBackend):
    """PostgreSQL-based storage backend."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "kailash",
        username: str = "postgres",
        password: str = "",
        table_name: str = "storage",
    ):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.table_name = table_name
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get PostgreSQL connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
            )
            await self._ensure_table()
        return self._pool

    async def _ensure_table(self) -> None:
        """Ensure storage table exists."""
        pool = self._pool
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    key VARCHAR PRIMARY KEY,
                    data BYTEA NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
            )

    async def save(self, key: str, data: bytes) -> None:
        """Save data to PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self.table_name} (key, data, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                key,
                data,
            )

    async def load(self, key: str) -> Optional[bytes]:
        """Load data from PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT data FROM {self.table_name} WHERE key = $1", key
            )
            return row["data"] if row else None

    async def delete(self, key: str) -> None:
        """Delete data from PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {self.table_name} WHERE key = $1", key)

    async def list_keys(self, prefix: str = "") -> List[str]:
        """List keys with prefix."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT key FROM {self.table_name} WHERE key LIKE $1",
                f"{prefix}%",
            )
            return [row["key"] for row in rows]

    async def close(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None


class RedisEventStorage:
    """Redis-based event storage for EventStore."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        key_prefix: str = "events:",
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.key_prefix = key_prefix
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self._redis is None:
            self._redis = await redis.from_url(
                f"redis://{self.host}:{self.port}",
                db=self.db,
                password=self.password,
                decode_responses=False,
            )
        return self._redis

    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.key_prefix}{key}"

    async def append(self, key: str, events: List[Dict[str, Any]]) -> None:
        """Append events to Redis list."""
        redis = await self._get_redis()
        serialized_events = [json.dumps(event) for event in events]
        await redis.lpush(self._make_key(key), *serialized_events)

    async def get(self, key: str) -> List[Dict[str, Any]]:
        """Get events from Redis list."""
        redis = await self._get_redis()
        data = await redis.lrange(self._make_key(key), 0, -1)
        return [json.loads(item) for item in reversed(data)]

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class PostgreSQLEventStorage:
    """PostgreSQL-based event storage for EventStore."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "kailash",
        username: str = "postgres",
        password: str = "",
        table_name: str = "events",
    ):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.table_name = table_name
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get PostgreSQL connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
            )
            await self._ensure_table()
        return self._pool

    async def _ensure_table(self) -> None:
        """Ensure events table exists."""
        pool = self._pool
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id SERIAL PRIMARY KEY,
                    request_id VARCHAR NOT NULL,
                    event_id VARCHAR NOT NULL,
                    event_type VARCHAR NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    data JSONB,
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_request_id
                ON {self.table_name} (request_id)
            """
            )

    async def append(self, key: str, events: List[Dict[str, Any]]) -> None:
        """Append events to PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for event in events:
                await conn.execute(
                    f"""
                    INSERT INTO {self.table_name}
                    (request_id, event_id, event_type, sequence_number, timestamp, data, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    event["request_id"],
                    event["event_id"],
                    event["event_type"],
                    event["sequence_number"],
                    datetime.fromisoformat(event["timestamp"]),
                    json.dumps(event["data"]),
                    json.dumps(event["metadata"]),
                )

    async def get(self, key: str) -> List[Dict[str, Any]]:
        """Get events from PostgreSQL."""
        # Extract request_id from key (format: "events:request_id")
        request_id = key.split(":", 1)[1] if ":" in key else key

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT event_id, event_type, request_id, sequence_number,
                       timestamp, data, metadata
                FROM {self.table_name}
                WHERE request_id = $1
                ORDER BY sequence_number
                """,
                request_id,
            )

            events = []
            for row in rows:
                events.append(
                    {
                        "event_id": row["event_id"],
                        "event_type": row["event_type"],
                        "request_id": row["request_id"],
                        "sequence_number": row["sequence_number"],
                        "timestamp": row["timestamp"].isoformat(),
                        "data": json.loads(row["data"]) if row["data"] else {},
                        "metadata": (
                            json.loads(row["metadata"]) if row["metadata"] else {}
                        ),
                    }
                )

            return events

    async def close(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
