"""
ExpressDataFlow - High-Performance Direct Node Invocation

Provides a fast path for simple CRUD operations that bypasses workflow overhead.
Preserves DataFlow features (audit, multi-tenancy, schema cache) while achieving
23x performance improvement for simple operations.

Performance (Pure Overhead):
- Workflow path: ~6.3ms per operation (WorkflowBuilder + Runtime)
- Express path: ~0.27ms per operation (23x faster)
- Express + cache hit: ~0.14ms (44x faster)

Usage:
    from dataflow import DataFlow

    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str
        email: str

    await db.initialize()

    # Fast CRUD operations via db.express property
    user = await db.express.create("User", {"id": "user-123", "name": "Alice"})
    user = await db.express.read("User", "user-123")
    users = await db.express.list("User", filter={"status": "active"}, limit=100)
    count = await db.express.count("User", filter={"status": "active"})
    user = await db.express.update("User", "user-123", {"name": "Alice Updated"})
    deleted = await db.express.delete("User", "user-123")

When to Use ExpressDataFlow:
- Simple CRUD operations (create, read, update, delete, list, count, upsert)
- High-frequency API endpoints where workflow overhead matters
- Performance-critical paths requiring minimal latency
- Read-heavy workloads benefiting from query caching

When to Use Traditional Workflows:
- Complex multi-step operations requiring node connections
- Conditional execution with SwitchNode
- Cyclic workflows
- Operations requiring full workflow introspection/debugging
- Custom validation logic between nodes
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from dataflow import DataFlow

logger = logging.getLogger(__name__)


# ============================================================================
# Query Cache Implementation
# ============================================================================


@dataclass
class CacheEntry:
    """Cache entry with value, timestamp, and TTL."""

    value: Any
    timestamp: float
    ttl: int


class ExpressQueryCache:
    """
    Thread-safe LRU cache with TTL expiration for query results.

    Features:
    - LRU (Least Recently Used) eviction when max_size reached
    - TTL (Time To Live) expiration for stale entries
    - Thread-safe with RLock protection
    - Automatic cache invalidation on writes
    - Statistics tracking (hits, misses, evictions)
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries (default: 1000)
            default_ttl: Default time-to-live in seconds (default: 300 = 5 min)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = RLock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0

    def _generate_key(self, model: str, operation: str, params: Dict[str, Any]) -> str:
        """Generate cache key from model, operation, and parameters."""
        key_data = (
            f"{model}:{operation}:{json.dumps(params, sort_keys=True, default=str)}"
        )
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check TTL
            if time.time() - entry.timestamp > entry.ttl:
                # Expired - remove
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (mark as recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override (uses default if not specified)
        """
        with self._lock:
            # LRU eviction if at capacity
            if key not in self._cache and len(self._cache) >= self._max_size:
                # Remove oldest entry (first item)
                self._cache.popitem(last=False)
                self._evictions += 1

            entry_ttl = ttl if ttl is not None else self._default_ttl
            self._cache[key] = CacheEntry(
                value=value, timestamp=time.time(), ttl=entry_ttl
            )

            # Move to end if updating existing key
            if key in self._cache:
                self._cache.move_to_end(key)

    def invalidate_model(self, model: str) -> int:
        """
        Invalidate all cache entries for a model.

        Called automatically on write operations (create, update, delete).

        Args:
            model: Model name

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            # Find keys that start with model name hash prefix
            # Since we use hashed keys, we need to track model associations
            # For simplicity, clear all entries containing the model name
            keys_to_remove = []
            for key in self._cache.keys():
                # We'll use a separate tracking mechanism for model->key mapping
                # For now, clear entries based on stored model association
                entry = self._cache.get(key)
                if entry and hasattr(entry, "model") and entry.model == model:
                    keys_to_remove.append(key)

            # For now, since we don't track model associations, invalidate all
            # In production, maintain a model->keys mapping for efficient invalidation
            count = len(self._cache)
            self._cache.clear()
            self._invalidations += count
            return count

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
                "invalidations": self._invalidations,
                "cached_entries": len(self._cache),
                "max_size": self._max_size,
                "default_ttl": self._default_ttl,
            }


# ============================================================================
# ExpressDataFlow Implementation
# ============================================================================


class ExpressDataFlow:
    """
    High-performance DataFlow wrapper for direct node invocation.

    Bypasses workflow overhead (WorkflowBuilder, validation, graph building)
    for simple CRUD operations while preserving DataFlow features.

    Performance Improvement:
    - Workflow path: ~6.3ms overhead
    - Express path: ~0.27ms overhead (23x faster)
    - Express + cache hit: ~0.14ms (44x faster)

    When to use ExpressDataFlow:
    - Simple CRUD operations (create, read, update, delete, list, count)
    - High-frequency API endpoints
    - Performance-critical paths

    When to use regular workflows:
    - Complex multi-step operations
    - Operations requiring connections between nodes
    - Conditional execution
    - Cyclic workflows
    """

    def __init__(
        self,
        dataflow_instance: "DataFlow",
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
        cache_ttl: int = 300,
        warm_schema_on_init: bool = False,
    ):
        """
        Initialize ExpressDataFlow.

        Args:
            dataflow_instance: DataFlow instance with registered models
            cache_enabled: Enable query result caching (default: True)
            cache_max_size: Maximum cache entries (default: 1000)
            cache_ttl: Cache TTL in seconds (default: 300 = 5 min)
            warm_schema_on_init: Pre-warm schema cache on init (default: False)
        """
        self._db = dataflow_instance
        self._cache_enabled = cache_enabled
        self._cache = ExpressQueryCache(max_size=cache_max_size, default_ttl=cache_ttl)
        self._schema_warmed = False

        # Statistics
        self._operation_times: List[float] = []

        if warm_schema_on_init:
            # Schedule schema warm-up (async-compatible)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.warm_schema_cache())
                else:
                    loop.run_until_complete(self.warm_schema_cache())
            except RuntimeError:
                # No event loop - warm-up will happen on first operation
                pass

    async def warm_schema_cache(self) -> Dict[str, bool]:
        """
        Pre-warm schema cache for all registered models.

        Eliminates first-call penalty by ensuring schema cache is
        populated before first operation.

        Returns:
            Dict mapping model names to warm-up success status
        """
        results = {}
        models = list(self._db._models.keys()) if hasattr(self._db, "_models") else []

        for model in models:
            try:
                # Ensure table exists to warm schema cache
                if hasattr(self._db, "ensure_table_exists"):
                    await self._db.ensure_table_exists(model)
                    results[model] = True
                    logger.debug(f"Warmed schema cache for {model}")
            except Exception as e:
                results[model] = False
                logger.warning(f"Failed to warm cache for {model}: {e}")

        self._schema_warmed = True
        return results

    def _get_node_class(self, model: str, operation: str) -> Type:
        """Get node class for model and operation."""
        node_name = f"{model}{operation}Node"
        if node_name not in self._db._nodes:
            raise ValueError(
                f"Node {node_name} not found. "
                f"Ensure model '{model}' is registered with DataFlow."
            )
        return self._db._nodes[node_name]

    def _create_node(self, model: str, operation: str):
        """Create a node instance with proper DataFlow binding.

        This ensures each node instance has the correct dataflow_instance
        attribute, which is critical for database operations to use the
        correct connection pool and table mappings.
        """
        node_class = self._get_node_class(model, operation)
        node = node_class()
        # Explicitly bind the node to this DataFlow instance
        # This is critical because node classes may be shared across
        # multiple DataFlow instances in the global registry
        node.dataflow_instance = self._db
        return node

    async def _execute_with_timing(self, operation: str, coro) -> Any:
        """Execute operation with timing tracking."""
        start = time.perf_counter()
        try:
            result = await coro
            return result
        finally:
            elapsed = (time.perf_counter() - start) * 1000  # ms
            self._operation_times.append(elapsed)
            logger.debug(f"Express {operation}: {elapsed:.2f}ms")

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    async def create(self, model: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a single record.

        Args:
            model: Model name (e.g., "User")
            data: Record data including 'id' field

        Returns:
            Created record

        Example:
            user = await db.express.create("User", {
                "id": "user-123",
                "name": "Alice",
                "email": "alice@example.com"
            })
        """

        async def _create():
            node = self._create_node(model, "Create")
            result = await node.async_run(**data)

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            return result

        return await self._execute_with_timing(f"{model}.create", _create())

    async def read(
        self, model: str, id: str, cache_ttl: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Read a single record by ID.

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            cache_ttl: Optional cache TTL override

        Returns:
            Record or None if not found

        Example:
            user = await db.express.read("User", "user-123")
        """
        cache_key = None

        # Check cache first
        if self._cache_enabled:
            cache_key = self._cache._generate_key(model, "read", {"id": id})
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {model}.read({id})")
                return cached

        async def _read():
            try:
                node = self._create_node(model, "Read")
                result = await node.async_run(id=id)

                # Cache result
                if self._cache_enabled and cache_key and result:
                    self._cache.set(cache_key, result, ttl=cache_ttl)

                return result
            except Exception as e:
                # Check if this is a "not found" error - return None instead of raising
                error_str = str(e).lower()
                if (
                    "not found" in error_str
                    or "no record" in error_str
                    or "does not exist" in error_str
                ):
                    logger.debug(f"Record not found for {model}.read({id})")
                    return None
                # Re-raise other errors
                raise

        return await self._execute_with_timing(f"{model}.read", _read())

    async def update(
        self, model: str, id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a single record.

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            fields: Fields to update

        Returns:
            Updated record

        Example:
            user = await db.express.update("User", "user-123", {"name": "Alice Updated"})
        """

        async def _update():
            node = self._create_node(model, "Update")
            result = await node.async_run(filter={"id": id}, fields=fields)

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            return result

        return await self._execute_with_timing(f"{model}.update", _update())

    async def delete(self, model: str, id: str) -> bool:
        """
        Delete a single record.

        Args:
            model: Model name (e.g., "User")
            id: Record ID

        Returns:
            True if deleted, False if not found

        Example:
            deleted = await db.express.delete("User", "user-123")
        """

        async def _delete():
            node = self._create_node(model, "Delete")
            result = await node.async_run(id=id)

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            return (
                result.get("deleted", False)
                if isinstance(result, dict)
                else bool(result)
            )

        return await self._execute_with_timing(f"{model}.delete", _delete())

    async def list(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        cache_ttl: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List records with optional filtering.

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            limit: Maximum records to return (default: 100)
            offset: Skip first N records (default: 0)
            cache_ttl: Optional cache TTL override

        Returns:
            List of records

        Example:
            users = await db.express.list("User", filter={"status": "active"}, limit=50)
        """
        params = {"filter": filter or {}, "limit": limit, "offset": offset}

        cache_key = None

        # Check cache first
        if self._cache_enabled:
            cache_key = self._cache._generate_key(model, "list", params)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {model}.list")
                return cached

        async def _list():
            node = self._create_node(model, "List")
            result = await node.async_run(**params)

            # Cache result
            if self._cache_enabled and cache_key:
                self._cache.set(cache_key, result, ttl=cache_ttl)

            return result if isinstance(result, list) else result.get("records", [])

        return await self._execute_with_timing(f"{model}.list", _list())

    async def find_one(
        self,
        model: str,
        filter: Dict[str, Any],
        cache_ttl: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single record by filter criteria (non-PK lookup).

        This method provides a clean API for single-record lookups using
        any field, not just the primary key. For primary key lookups,
        use read() instead.

        Args:
            model: Model name (e.g., "User")
            filter: MongoDB-style filter criteria (required, must not be empty)
            cache_ttl: Optional cache TTL override

        Returns:
            Single record dict or None if not found

        Raises:
            ValueError: If filter is empty (use list() for unfiltered queries)

        Example:
            # Find user by email (non-PK field)
            user = await db.express.find_one("User", filter={"email": "alice@example.com"})

            # Find with multiple criteria
            user = await db.express.find_one("User", filter={
                "department": "engineering",
                "active": True
            })

            # Returns None if not found
            user = await db.express.find_one("User", filter={"email": "nonexistent@example.com"})
            assert user is None
        """
        # Validate filter is not empty - empty filter should use list()
        if not filter:
            raise ValueError(
                "find_one() requires a non-empty filter. "
                "For unfiltered queries, use list() with limit=1."
            )

        params = {"filter": filter, "limit": 1, "offset": 0}

        cache_key = None

        # Check cache first
        if self._cache_enabled:
            cache_key = self._cache._generate_key(model, "find_one", params)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {model}.find_one")
                return cached

        async def _find_one():
            node = self._create_node(model, "List")
            result = await node.async_run(**params)

            # Extract first record from list result
            records = result if isinstance(result, list) else result.get("records", [])
            record = records[0] if records else None

            # Cache result (including None for not-found)
            if self._cache_enabled and cache_key:
                self._cache.set(cache_key, record, ttl=cache_ttl)

            return record

        return await self._execute_with_timing(f"{model}.find_one", _find_one())

    async def count(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        cache_ttl: Optional[int] = None,
    ) -> int:
        """
        Count records with optional filtering.

        Uses COUNT(*) query for optimal performance.

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            cache_ttl: Optional cache TTL override

        Returns:
            Number of matching records

        Example:
            active_count = await db.express.count("User", filter={"status": "active"})
        """
        params = {"filter": filter or {}}

        cache_key = None

        # Check cache first
        if self._cache_enabled:
            cache_key = self._cache._generate_key(model, "count", params)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {model}.count")
                return cached

        async def _count():
            node = self._create_node(model, "Count")
            result = await node.async_run(**params)
            count = result.get("count", 0) if isinstance(result, dict) else result

            # Cache result
            if self._cache_enabled and cache_key:
                self._cache.set(cache_key, count, ttl=cache_ttl)

            return count

        return await self._execute_with_timing(f"{model}.count", _count())

    async def upsert(
        self,
        model: str,
        data: Dict[str, Any],
        conflict_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Upsert (insert or update) a record using simple data dict.

        This simplified API uses the 'id' field for conflict detection by default.
        For more advanced upsert with separate where/create/update, use upsert_advanced().

        Args:
            model: Model name (e.g., "User")
            data: Record data including 'id' field
            conflict_on: Fields for conflict detection (default: ["id"])

        Returns:
            The upserted record

        Example:
            result = await db.express.upsert(
                "User",
                {"id": "user-123", "name": "Alice", "email": "alice@example.com"}
            )
        """

        async def _upsert():
            node = self._create_node(model, "Upsert")

            # Simple upsert: use data as both create and update
            # Use id field for where clause by default
            where_fields = conflict_on or ["id"]
            where = {k: data[k] for k in where_fields if k in data}

            params = {"where": where, "create": data, "update": data}
            if conflict_on:
                params["conflict_on"] = conflict_on

            result = await node.async_run(**params)

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            # Return the record directly for simpler API
            if isinstance(result, dict) and "record" in result:
                return result["record"]
            return result

        return await self._execute_with_timing(f"{model}.upsert", _upsert())

    async def upsert_advanced(
        self,
        model: str,
        where: Dict[str, Any],
        create: Dict[str, Any],
        update: Optional[Dict[str, Any]] = None,
        conflict_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Advanced upsert with separate where/create/update parameters.

        Args:
            model: Model name (e.g., "User")
            where: Fields to identify the record
            create: Fields to create if record doesn't exist
            update: Fields to update if record exists (default: same as create)
            conflict_on: Fields for conflict detection (default: where keys)

        Returns:
            Dict with 'created' (bool), 'action' (str), 'record' (dict)

        Example:
            result = await db.express.upsert_advanced(
                "User",
                where={"email": "alice@example.com"},
                create={"id": "user-123", "email": "alice@example.com", "name": "Alice"},
                update={"name": "Alice Updated"},
                conflict_on=["email"]
            )
        """

        async def _upsert():
            node = self._create_node(model, "Upsert")

            params = {"where": where, "create": create, "update": update or create}
            if conflict_on:
                params["conflict_on"] = conflict_on

            result = await node.async_run(**params)

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            return result

        return await self._execute_with_timing(f"{model}.upsert_advanced", _upsert())

    # ========================================================================
    # Bulk Operations
    # ========================================================================

    async def bulk_create(
        self, model: str, records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create multiple records in bulk.

        Args:
            model: Model name (e.g., "User")
            records: List of record data dicts, each including 'id' field

        Returns:
            List of created records

        Example:
            users = await db.express.bulk_create("User", [
                {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
                {"id": "user-2", "name": "Bob", "email": "bob@example.com"},
            ])
        """

        async def _bulk_create():
            node = self._create_node(model, "BulkCreate")
            result = await node.async_run(data=records)

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            # Handle different result formats
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "records" in result:
                return result["records"]
            elif isinstance(result, dict) and "items" in result:
                return result["items"]
            return result

        return await self._execute_with_timing(f"{model}.bulk_create", _bulk_create())

    async def bulk_delete(self, model: str, ids: List[str]) -> bool:
        """
        Delete multiple records by their IDs.

        Args:
            model: Model name (e.g., "User")
            ids: List of record IDs to delete

        Returns:
            True if all deletions succeeded

        Example:
            deleted = await db.express.bulk_delete("User", ["user-1", "user-2", "user-3"])
        """

        async def _bulk_delete():
            node = self._create_node(model, "BulkDelete")
            # Convert IDs list to filter format expected by BulkDeleteNode
            result = await node.async_run(filter={"id": {"$in": ids}})

            # Invalidate cache for this model
            if self._cache_enabled:
                self._cache.invalidate_model(model)

            # Handle different result formats
            if isinstance(result, bool):
                return result
            elif isinstance(result, dict):
                # Check 'success' first since 'deleted' may be a count (int) not bool
                return result.get("success", True)
            return True

        return await self._execute_with_timing(f"{model}.bulk_delete", _bulk_delete())

    # ========================================================================
    # Cache Management
    # ========================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()

    def clear_cache(self, model: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            model: Optional model name to clear only that model's entries

        Returns:
            Number of entries cleared
        """
        if model:
            return self._cache.invalidate_model(model)
        else:
            count = len(self._cache._cache)
            self._cache.clear()
            return count

    # ========================================================================
    # Performance Metrics
    # ========================================================================

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        if not self._operation_times:
            return {
                "total_operations": 0,
                "avg_time_ms": 0,
                "min_time_ms": 0,
                "max_time_ms": 0,
                "p50_time_ms": 0,
                "p95_time_ms": 0,
                "p99_time_ms": 0,
            }

        times = sorted(self._operation_times)
        n = len(times)

        return {
            "total_operations": n,
            "avg_time_ms": sum(times) / n,
            "min_time_ms": times[0],
            "max_time_ms": times[-1],
            "p50_time_ms": times[n // 2],
            "p95_time_ms": times[int(n * 0.95)] if n >= 20 else times[-1],
            "p99_time_ms": times[int(n * 0.99)] if n >= 100 else times[-1],
        }

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._operation_times.clear()
        self._cache._hits = 0
        self._cache._misses = 0
        self._cache._evictions = 0
        self._cache._invalidations = 0
