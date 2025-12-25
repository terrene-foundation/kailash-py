"""Query Result Caching for Database Nodes.

This module provides Redis-based caching for database query results
with TTL management and cache invalidation strategies.

Key Features:
- Redis-based query result caching
- Cache key generation from queries
- TTL management
- Cache invalidation strategies
- Support for different cache patterns
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import redis
from kailash.sdk_exceptions import NodeExecutionError
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class CachePattern(Enum):
    """Cache patterns for different use cases."""

    WRITE_THROUGH = "write_through"  # Update cache on write
    WRITE_BEHIND = "write_behind"  # Async cache updates
    CACHE_ASIDE = "cache_aside"  # Manual cache management
    REFRESH_AHEAD = "refresh_ahead"  # Proactive cache refresh


class CacheInvalidationStrategy(Enum):
    """Cache invalidation strategies."""

    TTL = "ttl"  # Time-based expiration
    MANUAL = "manual"  # Manual invalidation
    WRITE_THROUGH = "write_through"  # Invalidate on write
    PATTERN_BASED = "pattern_based"  # Invalidate by pattern
    EVENT_BASED = "event_based"  # Invalidate on events


class QueryCacheKey:
    """Generates cache keys for database queries."""

    def __init__(self, prefix: str = "kailash:query"):
        """Initialize cache key generator.

        Args:
            prefix: Prefix for cache keys
        """
        self.prefix = prefix

    def generate(
        self, query: str, parameters: List[Any], tenant_id: Optional[str] = None
    ) -> str:
        """Generate cache key for a query.

        Args:
            query: SQL query string
            parameters: Query parameters
            tenant_id: Optional tenant ID for multi-tenant caching

        Returns:
            Cache key string
        """
        # Create a consistent representation of the query and parameters
        query_data = {
            "query": query.strip(),
            "parameters": self._normalize_parameters(parameters),
            "tenant_id": tenant_id,
        }

        # Create hash of the query data
        query_json = json.dumps(query_data, sort_keys=True)
        query_hash = hashlib.sha256(query_json.encode()).hexdigest()[:16]

        # Build cache key
        key_parts = [self.prefix]
        if tenant_id:
            key_parts.append(f"tenant:{tenant_id}")
        key_parts.append(query_hash)

        return ":".join(key_parts)

    def generate_pattern(self, table_name: str, tenant_id: Optional[str] = None) -> str:
        """Generate cache key pattern for invalidation.

        Args:
            table_name: Database table name
            tenant_id: Optional tenant ID

        Returns:
            Cache key pattern
        """
        pattern_parts = [self.prefix]
        if tenant_id:
            pattern_parts.append(f"tenant:{tenant_id}")
        pattern_parts.append(f"table:{table_name}")
        pattern_parts.append("*")

        return ":".join(pattern_parts)

    def _normalize_parameters(self, parameters: List[Any]) -> List[Any]:
        """Normalize parameters for consistent hashing."""
        normalized = []
        for param in parameters:
            if isinstance(param, datetime):
                normalized.append(param.isoformat())
            elif isinstance(param, (dict, list)):
                normalized.append(json.dumps(param, sort_keys=True))
            else:
                normalized.append(param)
        return normalized


class QueryCache:
    """Redis-based query result cache."""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        default_ttl: int = 3600,
        cache_pattern: CachePattern = CachePattern.CACHE_ASIDE,
        invalidation_strategy: CacheInvalidationStrategy = CacheInvalidationStrategy.TTL,
        key_prefix: str = "kailash:query",
    ):
        """Initialize query cache.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Redis password (optional)
            default_ttl: Default TTL in seconds
            cache_pattern: Cache pattern to use
            invalidation_strategy: Cache invalidation strategy
            key_prefix: Prefix for cache keys
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password
        self.default_ttl = default_ttl
        self.cache_pattern = cache_pattern
        self.invalidation_strategy = invalidation_strategy

        self.key_generator = QueryCacheKey(key_prefix)
        self._redis: Optional[redis.Redis] = None

    def _get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self._redis is None:
            self._redis = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True,
            )
        return self._redis

    def get(
        self, query: str, parameters: List[Any], tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get cached query result.

        Args:
            query: SQL query string
            parameters: Query parameters
            tenant_id: Optional tenant ID

        Returns:
            Cached result or None if not found
        """
        try:
            redis_client = self._get_redis()
            cache_key = self.key_generator.generate(query, parameters, tenant_id)

            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for key: {cache_key}")
                return json.loads(cached_data)
            else:
                logger.debug(f"Cache miss for key: {cache_key}")
                return None

        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def set(
        self,
        query: str,
        parameters: List[Any],
        result: Dict[str, Any],
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set cached query result.

        Args:
            query: SQL query string
            parameters: Query parameters
            result: Query result to cache
            tenant_id: Optional tenant ID
            ttl: TTL in seconds (uses default if not specified)

        Returns:
            True if cached successfully, False otherwise
        """
        try:
            redis_client = self._get_redis()
            cache_key = self.key_generator.generate(query, parameters, tenant_id)

            # Prepare cache data
            cache_data = {
                "result": result,
                "cached_at": datetime.now().isoformat(),
                "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            }

            # Set with TTL
            actual_ttl = ttl or self.default_ttl
            success = redis_client.setex(cache_key, actual_ttl, json.dumps(cache_data))

            if success:
                logger.debug(f"Cache set for key: {cache_key} (TTL: {actual_ttl}s)")

                # Add to table-based index for pattern invalidation
                if (
                    self.invalidation_strategy
                    == CacheInvalidationStrategy.PATTERN_BASED
                ):
                    self._add_to_table_index(query, cache_key, tenant_id)

            return success

        except (RedisError, TypeError, ValueError) as e:
            logger.warning(f"Cache set error: {e}")
            return False

    def invalidate(
        self, query: str, parameters: List[Any], tenant_id: Optional[str] = None
    ) -> bool:
        """Invalidate specific cached query.

        Args:
            query: SQL query string
            parameters: Query parameters
            tenant_id: Optional tenant ID

        Returns:
            True if invalidated successfully, False otherwise
        """
        try:
            redis_client = self._get_redis()
            cache_key = self.key_generator.generate(query, parameters, tenant_id)

            deleted = redis_client.delete(cache_key)
            if deleted:
                logger.debug(f"Cache invalidated for key: {cache_key}")

            return deleted > 0

        except RedisError as e:
            logger.warning(f"Cache invalidation error: {e}")
            return False

    def invalidate_table(self, table_name: str, tenant_id: Optional[str] = None) -> int:
        """Invalidate all cached queries for a table.

        Args:
            table_name: Database table name
            tenant_id: Optional tenant ID

        Returns:
            Number of keys invalidated
        """
        try:
            redis_client = self._get_redis()

            if self.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED:
                # Use index-based invalidation for pattern-based strategy
                index_key = f"{self.key_generator.prefix}:index:table:{table_name}"
                if tenant_id:
                    index_key += f":tenant:{tenant_id}"

                keys = redis_client.smembers(index_key)
                if keys:
                    # Delete the actual cache keys
                    deleted = redis_client.delete(*keys)
                    # Also delete the index
                    redis_client.delete(index_key)
                    logger.debug(
                        f"Cache invalidated {deleted} keys for table: {table_name}"
                    )
                    return deleted
                else:
                    return 0
            else:
                # Use pattern-based invalidation for other strategies
                pattern = self.key_generator.generate_pattern(table_name, tenant_id)
                keys = redis_client.keys(pattern)
                if keys:
                    deleted = redis_client.delete(*keys)
                    logger.debug(
                        f"Cache invalidated {deleted} keys for table: {table_name}"
                    )
                    return deleted
                else:
                    return 0

        except RedisError as e:
            logger.warning(f"Cache table invalidation error: {e}")
            return 0

    def clear_all(self, tenant_id: Optional[str] = None) -> int:
        """Clear all cached queries for a tenant or globally.

        Args:
            tenant_id: Optional tenant ID (clears all if None)

        Returns:
            Number of keys cleared
        """
        try:
            redis_client = self._get_redis()

            if tenant_id:
                pattern = f"{self.key_generator.prefix}:tenant:{tenant_id}:*"
            else:
                pattern = f"{self.key_generator.prefix}:*"

            keys = redis_client.keys(pattern)
            if keys:
                deleted = redis_client.delete(*keys)
                logger.info(f"Cache cleared {deleted} keys for tenant: {tenant_id}")
                return deleted
            else:
                return 0

        except RedisError as e:
            logger.warning(f"Cache clear error: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            redis_client = self._get_redis()

            # Get Redis info
            info = redis_client.info()

            # Count our keys
            pattern = f"{self.key_generator.prefix}:*"
            keys = redis_client.keys(pattern)

            stats = {
                "total_keys": len(keys),
                "redis_memory_used": info.get("used_memory_human", "unknown"),
                "redis_connected_clients": info.get("connected_clients", 0),
                "redis_keyspace_hits": info.get("keyspace_hits", 0),
                "redis_keyspace_misses": info.get("keyspace_misses", 0),
                "cache_pattern": self.cache_pattern.value,
                "invalidation_strategy": self.invalidation_strategy.value,
                "default_ttl": self.default_ttl,
            }

            # Calculate hit rate
            hits = stats["redis_keyspace_hits"]
            misses = stats["redis_keyspace_misses"]
            if hits + misses > 0:
                stats["hit_rate"] = hits / (hits + misses)
            else:
                stats["hit_rate"] = 0.0

            return stats

        except RedisError as e:
            logger.warning(f"Cache stats error: {e}")
            return {"error": str(e), "total_keys": 0, "hit_rate": 0.0}

    def health_check(self) -> Dict[str, Any]:
        """Check cache health.

        Returns:
            Dictionary with health status
        """
        try:
            redis_client = self._get_redis()

            # Try to ping Redis
            pong = redis_client.ping()
            if pong:
                # Test basic operations
                test_key = f"{self.key_generator.prefix}:health_check"
                redis_client.setex(test_key, 10, "test")
                test_value = redis_client.get(test_key)
                redis_client.delete(test_key)

                return {
                    "status": "healthy",
                    "redis_ping": True,
                    "read_write_test": test_value == "test",
                    "connection": "active",
                }
            else:
                return {
                    "status": "unhealthy",
                    "redis_ping": False,
                    "error": "Redis ping failed",
                }

        except RedisError as e:
            return {"status": "unhealthy", "redis_ping": False, "error": str(e)}

    def _add_to_table_index(
        self, query: str, cache_key: str, tenant_id: Optional[str] = None
    ) -> None:
        """Add cache key to table-based index for pattern invalidation."""
        try:
            # Extract table name from query (simple heuristic)
            table_name = self._extract_table_name(query)
            if table_name:
                redis_client = self._get_redis()
                index_key = f"{self.key_generator.prefix}:index:table:{table_name}"
                if tenant_id:
                    index_key += f":tenant:{tenant_id}"

                redis_client.sadd(index_key, cache_key)
                redis_client.expire(
                    index_key, self.default_ttl * 2
                )  # Index lives longer

        except Exception as e:
            logger.warning(f"Failed to add to table index: {e}")

    def _extract_table_name(self, query: str) -> Optional[str]:
        """Extract table name from SQL query (simple heuristic)."""
        try:
            query_lower = query.lower().strip()

            # Handle SELECT queries
            if query_lower.startswith("select"):
                from_index = query_lower.find("from")
                if from_index != -1:
                    from_part = query_lower[from_index + 4 :].strip()
                    table_name = from_part.split()[0].strip()
                    return table_name

            # Handle INSERT queries
            elif query_lower.startswith("insert into"):
                into_part = query_lower[11:].strip()
                table_name = into_part.split()[0].strip()
                return table_name

            # Handle UPDATE queries
            elif query_lower.startswith("update"):
                update_part = query_lower[6:].strip()
                table_name = update_part.split()[0].strip()
                return table_name

            # Handle DELETE queries
            elif query_lower.startswith("delete from"):
                from_part = query_lower[11:].strip()
                table_name = from_part.split()[0].strip()
                return table_name

            return None

        except Exception:
            return None


# Factory function for creating query cache
def create_query_cache(config: Dict[str, Any] = None) -> QueryCache:
    """Create a query cache instance with configuration.

    Args:
        config: Configuration dictionary

    Returns:
        QueryCache instance
    """
    if config is None:
        config = {}

    return QueryCache(
        redis_host=config.get("redis_host", "localhost"),
        redis_port=config.get("redis_port", 6379),
        redis_db=config.get("redis_db", 0),
        redis_password=config.get("redis_password"),
        default_ttl=config.get("default_ttl", 3600),
        cache_pattern=CachePattern(config.get("cache_pattern", "cache_aside")),
        invalidation_strategy=CacheInvalidationStrategy(
            config.get("invalidation_strategy", "ttl")
        ),
        key_prefix=config.get("key_prefix", "kailash:query"),
    )
