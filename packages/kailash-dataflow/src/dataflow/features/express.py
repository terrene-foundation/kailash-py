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
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union

from dataflow.cache.auto_detection import CacheBackend
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.memory_cache import InMemoryCache
from dataflow.core.agent_context import get_current_agent_id, get_current_clearance
from dataflow.core.multi_tenancy import TenantRequiredError
from dataflow.core.tenant_context import get_current_tenant_id

if TYPE_CHECKING:
    from dataflow import DataFlow

logger = logging.getLogger(__name__)


# ============================================================================
# ExpressDataFlow Implementation
# ============================================================================


class DataFlowExpress:
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
        redis_url: Optional[str] = None,
    ):
        """
        Initialize ExpressDataFlow.

        Args:
            dataflow_instance: DataFlow instance with registered models
            cache_enabled: Enable query result caching (default: True)
            cache_max_size: Maximum cache entries (default: 1000)
            cache_ttl: Cache TTL in seconds (default: 300 = 5 min).
                A value of ``0`` disables caching entirely.
            warm_schema_on_init: Pre-warm schema cache on init (default: False)
            redis_url: Redis connection URL. When provided (or when the
                ``REDIS_URL`` environment variable is set) and Redis is
                reachable, Redis is used as the cache backend.  Otherwise
                an in-memory LRU cache is used.
        """
        self._db = dataflow_instance
        self._default_cache_ttl = cache_ttl
        self._schema_warmed = False

        # Disable caching when TTL is 0 or cache_enabled is False
        self._cache_enabled = cache_enabled and cache_ttl > 0

        # --- Cache backend (TSG-104) ---
        # Resolve Redis URL: explicit param > env var > None
        effective_redis_url = redis_url or os.environ.get("REDIS_URL")

        if self._cache_enabled:
            self._cache_manager: Optional[Union[InMemoryCache, Any]] = (
                CacheBackend.auto_detect(
                    redis_url=effective_redis_url,
                    ttl=cache_ttl,
                    max_size=cache_max_size,
                )
            )
        else:
            self._cache_manager = None

        self._key_gen = CacheKeyGenerator()

        # Local hit/miss counters for Express-level stats
        self._cache_hits = 0
        self._cache_misses = 0

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
                    logger.debug(
                        "express.warmed_schema_cache_for", extra={"model": model}
                    )
            except Exception as e:
                results[model] = False
                logger.warning(
                    "express.failed_to_warm_cache_for",
                    extra={"model": model, "error": str(e)},
                )

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
            logger.debug(
                "express.express_ms", extra={"operation": operation, "elapsed": elapsed}
            )

    # ========================================================================
    # Validation Helper (TSG-103)
    # ========================================================================

    async def _validate_if_enabled(self, model: str, data: Dict[str, Any]) -> None:
        """Validate data against model field validators if enabled.

        Does nothing if ``validate_on_write`` is disabled or if the
        model has no ``__field_validators__``.

        Raises:
            DataFlowValidationError: If validation fails.
        """
        if not getattr(self._db, "_validate_on_write", True):
            return
        model_info = self._db._models.get(model)
        if model_info is None:
            return
        model_cls = (
            model_info.get("class") if isinstance(model_info, dict) else model_info
        )
        if model_cls is None:
            return
        validators = getattr(model_cls, "__field_validators__", [])
        if not validators:
            return

        from dataflow.validation.decorators import validate_model as _validate_instance
        from dataflow.validation.result import ValidationResult

        # Build a lightweight proxy with data as attributes
        class _Proxy:
            pass

        proxy = _Proxy()
        for k, v in data.items():
            setattr(proxy, k, v)
        _Proxy.__field_validators__ = validators

        result = _validate_instance(proxy)
        if not result.valid:
            error_msgs = "; ".join(e.message for e in result.errors)
            from dataflow.exceptions import DataFlowError

            raise DataFlowError(f"Validation failed for {model}: {error_msgs}")

    # ========================================================================
    # Trust-plane integration helpers (Phase 5.11)
    # ========================================================================

    def _trust_enabled(self) -> bool:
        """Return True when a trust executor is wired on the DataFlow instance.

        When this is False, every other ``_trust_*`` helper short-circuits
        and Express behaves identically to pre-trust DataFlow — no access
        checks, no audit recording, no per-call overhead.
        """
        return getattr(self._db, "_trust_executor", None) is not None

    def _trust_agent_id(self) -> Optional[str]:
        """Resolve the agent ID for the current query from context."""
        return get_current_agent_id()

    async def _trust_check_read(
        self, model: str, filter: Optional[Dict[str, Any]] = None
    ):
        """Run the trust access check for a read-shaped query.

        Returns the ``QueryAccessResult`` plan when trust is enabled, or
        ``None`` when trust is not wired (caller should bypass all trust
        logic in that case).
        """
        if not self._trust_enabled():
            return None
        executor = self._db._trust_executor
        return await executor.check_read_access(
            model_name=model,
            filter=filter or {},
            agent_id=self._trust_agent_id(),
            trust_context=None,
        )

    async def _trust_check_write(self, model: str, operation: str):
        """Run the trust access check for a write-shaped query."""
        if not self._trust_enabled():
            return None
        executor = self._db._trust_executor
        return await executor.check_write_access(
            model_name=model,
            operation=operation,
            agent_id=self._trust_agent_id(),
            trust_context=None,
        )

    async def _trust_record_success(
        self,
        model: str,
        operation: str,
        plan: Any,
        rows_affected: int,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a success audit event via the trust executor."""
        if plan is None or not self._trust_enabled():
            return
        executor = self._db._trust_executor
        try:
            await executor.record_query_success(
                model_name=model,
                operation=operation,
                plan=plan,
                agent_id=self._trust_agent_id(),
                trust_context=None,
                rows_affected=rows_affected,
                query_params=query_params,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "trust.audit.success_failed",
                extra={
                    "model": model,
                    "operation": operation,
                    "error": str(exc),
                },
            )

    async def _trust_record_failure(
        self,
        model: str,
        operation: str,
        plan: Any,
        error: BaseException,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failure audit event via the trust executor."""
        if not self._trust_enabled():
            return
        executor = self._db._trust_executor
        try:
            await executor.record_query_failure(
                model_name=model,
                operation=operation,
                plan=plan,
                agent_id=self._trust_agent_id(),
                trust_context=None,
                error=str(error),
                query_params=query_params,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "trust.audit.failure_failed",
                extra={
                    "model": model,
                    "operation": operation,
                    "error": str(exc),
                },
            )

    # ========================================================================
    # Classification masking helpers (Phase 5.10)
    # ========================================================================

    def _classify_enabled(self, model: str) -> bool:
        """Return True when the DataFlow instance has a policy with any
        classified fields for this model.

        Zero-cost short-circuit for the common case of a model with no
        ``@classify`` decorators: classification masking is skipped
        entirely and the read path behaves as pre-Phase-5.10 DataFlow.
        """
        policy = getattr(self._db, "_classification_policy", None)
        if policy is None:
            return False
        return bool(policy.get_model_fields(model))

    def _apply_classification_mask_record(self, model: str, record: Any) -> Any:
        """Apply classification masking to a single record if needed.

        The caller's clearance is resolved from the
        ``clearance_context`` ContextVar. When no clearance is set the
        masking routine treats the caller as ``PUBLIC`` (the most
        restrictive).
        """
        if not self._classify_enabled(model):
            return record
        clearance = get_current_clearance()
        return self._db._classification_policy.apply_masking_to_record(
            model, record, clearance
        )

    def _apply_classification_mask_rows(self, model: str, rows: Any) -> Any:
        """Apply classification masking to a list of records."""
        if not self._classify_enabled(model):
            return rows
        clearance = get_current_clearance()
        return self._db._classification_policy.apply_masking_to_rows(
            model, rows, clearance
        )

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
            await self._validate_if_enabled(model, data)
            # Phase 5.11: trust access check before the write.
            plan = await self._trust_check_write(model, "create")
            try:
                node = self._create_node(model, "Create")
                result = await node.async_run(**data)
            except Exception as exc:
                await self._trust_record_failure(
                    model, "create", plan, exc, query_params=data
                )
                raise

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # Issue #184 fix: SQLite INSERT doesn't return auto-generated fields
            # (created_at, updated_at, id). If the result is missing timestamps
            # that exist in the model, do a read-back to fetch the complete record.
            if (
                result
                and isinstance(result, dict)
                and result.get("success") is not False
            ):
                model_fields = self._db.get_model_fields(model)
                has_timestamps = (
                    "created_at" in model_fields or "updated_at" in model_fields
                )
                missing_timestamps = has_timestamps and (
                    "created_at" not in result or "updated_at" not in result
                )
                if missing_timestamps:
                    record_id = result.get("id") or data.get("id")
                    try:
                        if record_id is not None:
                            readback = await self.read(model, str(record_id))
                        else:
                            # No id available — find most recently created matching record
                            readback = await self.find_one(model, data)
                        if readback and isinstance(readback, dict):
                            result = {**result, **readback}
                    except Exception:
                        pass  # Best-effort read-back; original result still valid

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                record_id = (
                    str(result.get("id", ""))
                    if result and isinstance(result, dict)
                    else None
                )
                self._db._emit_write_event(model, "create", record_id=record_id)

            await self._trust_record_success(
                model, "create", plan, rows_affected=1, query_params=data
            )
            return result

        return await self._execute_with_timing(f"{model}.create", _create())

    async def read(
        self,
        model: str,
        id: str,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
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
        effective_ttl = cache_ttl if cache_ttl is not None else self._default_cache_ttl

        # Check cache first
        cached_result = await self._cache_get(model, "read", {"id": id}, effective_ttl)
        if cached_result is not None:
            logger.debug("express.cache_hit_for_read", extra={"model": model, "id": id})
            return cached_result

        async def _read():
            # Phase 5.11: trust access check before the read.
            plan = await self._trust_check_read(model, {"id": id})
            try:
                node = self._create_node(model, "Read")
                result = await node.async_run(id=id)

                # Apply PII/column filter from the trust plan, if any.
                if plan is not None:
                    result = self._db._trust_executor.apply_result_filter(result, plan)

                # Phase 5.10: apply classification masking based on the
                # caller's clearance context.
                result = self._apply_classification_mask_record(model, result)

                # Cache result (TSG-104)
                await self._cache_set(model, "read", {"id": id}, result, effective_ttl)

                await self._trust_record_success(
                    model,
                    "read",
                    plan,
                    rows_affected=1 if result is not None else 0,
                    query_params={"id": id},
                )
                return result
            except Exception as e:
                # Check if this is a "not found" error - return None instead of raising
                error_str = str(e).lower()
                if (
                    "not found" in error_str
                    or "no record" in error_str
                    or "does not exist" in error_str
                ):
                    logger.debug(
                        "express.record_not_found_for_read",
                        extra={"model": model, "id": id},
                    )
                    await self._trust_record_success(
                        model,
                        "read",
                        plan,
                        rows_affected=0,
                        query_params={"id": id},
                    )
                    return None
                # Re-raise other errors
                await self._trust_record_failure(
                    model, "read", plan, e, query_params={"id": id}
                )
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
            await self._validate_if_enabled(model, fields)
            # Phase 5.11: trust access check before the write.
            plan = await self._trust_check_write(model, "update")
            try:
                node = self._create_node(model, "Update")
                result = await node.async_run(filter={"id": id}, fields=fields)
            except Exception as exc:
                await self._trust_record_failure(
                    model,
                    "update",
                    plan,
                    exc,
                    query_params={"id": id, "fields": fields},
                )
                raise

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "update", record_id=str(id))

            await self._trust_record_success(
                model,
                "update",
                plan,
                rows_affected=1,
                query_params={"id": id, "fields": fields},
            )
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
            # Phase 5.11: trust access check before the write.
            plan = await self._trust_check_write(model, "delete")
            try:
                node = self._create_node(model, "Delete")
                result = await node.async_run(id=id)
            except Exception as exc:
                await self._trust_record_failure(
                    model, "delete", plan, exc, query_params={"id": id}
                )
                raise

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "delete", record_id=str(id))

            deleted = (
                result.get("deleted", False)
                if isinstance(result, dict)
                else bool(result)
            )
            await self._trust_record_success(
                model,
                "delete",
                plan,
                rows_affected=1 if deleted else 0,
                query_params={"id": id},
            )
            return deleted

        return await self._execute_with_timing(f"{model}.delete", _delete())

    async def list(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
    ) -> List[Dict[str, Any]]:
        """
        List records with optional filtering.

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            limit: Maximum records to return (default: 100)
            offset: Skip first N records (default: 0)
            order_by: Optional field name to sort by (e.g., "created_at" or "-created_at" for desc)
            cache_ttl: Optional cache TTL override

        Returns:
            List of records

        Example:
            users = await db.express.list("User", filter={"status": "active"}, limit=50)
        """
        params = {"filter": filter or {}, "limit": limit, "offset": offset}
        if order_by:
            params["order_by"] = order_by
        effective_ttl = cache_ttl if cache_ttl is not None else self._default_cache_ttl

        # Check cache first
        cached_result = await self._cache_get(model, "list", params, effective_ttl)
        if cached_result is not None:
            logger.debug("express.cache_hit_for_list", extra={"model": model})
            return cached_result

        async def _list():
            # Phase 5.11: trust access check before the read.
            plan = await self._trust_check_read(model, filter)
            try:
                effective_params = dict(params)
                if plan is not None:
                    # Merge constraint-derived filters into the query filter.
                    if plan.additional_filters:
                        merged_filter = dict(effective_params.get("filter") or {})
                        merged_filter.update(plan.additional_filters)
                        effective_params["filter"] = merged_filter
                    # Honour row_limit constraints by tightening the limit.
                    if plan.row_limit is not None:
                        current_limit = effective_params.get("limit", limit)
                        effective_params["limit"] = min(
                            int(current_limit), plan.row_limit
                        )
                node = self._create_node(model, "List")
                result = await node.async_run(**effective_params)
            except Exception as exc:
                await self._trust_record_failure(
                    model, "list", plan, exc, query_params=params
                )
                raise

            records = result if isinstance(result, list) else result.get("records", [])

            # Apply PII/column filter from the trust plan, if any.
            if plan is not None:
                records = self._db._trust_executor.apply_result_filter(records, plan)

            # Phase 5.10: apply classification masking based on the
            # caller's clearance context.
            records = self._apply_classification_mask_rows(model, records)

            # Cache result (TSG-104)
            await self._cache_set(model, "list", params, records, effective_ttl)

            await self._trust_record_success(
                model,
                "list",
                plan,
                rows_affected=len(records) if hasattr(records, "__len__") else 0,
                query_params=params,
            )
            return records

        return await self._execute_with_timing(f"{model}.list", _list())

    async def find_one(
        self,
        model: str,
        filter: Dict[str, Any],
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
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
        effective_ttl = cache_ttl if cache_ttl is not None else self._default_cache_ttl

        # Check cache first
        cached_result = await self._cache_get(model, "find_one", params, effective_ttl)
        if cached_result is not None:
            logger.debug("express.cache_hit_for_find_one", extra={"model": model})
            return cached_result

        async def _find_one():
            # Phase 5.11: trust access check (find_one is a read).
            plan = await self._trust_check_read(model, filter)
            try:
                effective_params = dict(params)
                if plan is not None and plan.additional_filters:
                    merged_filter = dict(effective_params.get("filter") or {})
                    merged_filter.update(plan.additional_filters)
                    effective_params["filter"] = merged_filter
                node = self._create_node(model, "List")
                result = await node.async_run(**effective_params)
            except Exception as exc:
                await self._trust_record_failure(
                    model, "find_one", plan, exc, query_params=params
                )
                raise

            # Extract first record from list result
            records = result if isinstance(result, list) else result.get("records", [])
            record = records[0] if records else None

            if plan is not None and record is not None:
                record = self._db._trust_executor.apply_result_filter(record, plan)

            # Phase 5.10: apply classification masking.
            if record is not None:
                record = self._apply_classification_mask_record(model, record)

            # Cache result (including None for not-found)
            await self._cache_set(model, "find_one", params, record, effective_ttl)

            await self._trust_record_success(
                model,
                "find_one",
                plan,
                rows_affected=1 if record is not None else 0,
                query_params=params,
            )
            return record

        return await self._execute_with_timing(f"{model}.find_one", _find_one())

    async def count(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
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
        effective_ttl = cache_ttl if cache_ttl is not None else self._default_cache_ttl

        # Check cache first
        cached_result = await self._cache_get(model, "count", params, effective_ttl)
        if cached_result is not None:
            logger.debug("express.cache_hit_for_count", extra={"model": model})
            return cached_result

        async def _count():
            # Phase 5.11: trust access check (count is a read).
            plan = await self._trust_check_read(model, filter)
            try:
                effective_params = dict(params)
                if plan is not None and plan.additional_filters:
                    merged_filter = dict(effective_params.get("filter") or {})
                    merged_filter.update(plan.additional_filters)
                    effective_params["filter"] = merged_filter
                node = self._create_node(model, "Count")
                result = await node.async_run(**effective_params)
            except Exception as exc:
                await self._trust_record_failure(
                    model, "count", plan, exc, query_params=params
                )
                raise
            count = result.get("count", 0) if isinstance(result, dict) else result

            # Cache result (TSG-104)
            await self._cache_set(model, "count", params, count, effective_ttl)

            await self._trust_record_success(
                model,
                "count",
                plan,
                rows_affected=int(count or 0),
                query_params=params,
            )
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
            await self._validate_if_enabled(model, data)
            node = self._create_node(model, "Upsert")

            # Simple upsert: use data as both create and update
            # Use id field for where clause by default
            where_fields = conflict_on or ["id"]
            where = {k: data[k] for k in where_fields if k in data}

            params = {"where": where, "create": data, "update": data}
            if conflict_on:
                params["conflict_on"] = conflict_on

            result = await node.async_run(**params)

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                record_id = (
                    str(data.get("id", ""))
                    if isinstance(data, dict) and "id" in data
                    else None
                )
                self._db._emit_write_event(model, "upsert", record_id=record_id)

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

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event (upsert_advanced is also an upsert)
            if hasattr(self._db, "_emit_write_event"):
                record_id = (
                    str(create.get("id", ""))
                    if isinstance(create, dict) and "id" in create
                    else None
                )
                self._db._emit_write_event(model, "upsert", record_id=record_id)

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

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "bulk_create", record_id=None)

            # Handle different result formats
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "records" in result:
                return result["records"]
            elif isinstance(result, dict) and "items" in result:
                return result["items"]
            return result

        return await self._execute_with_timing(f"{model}.bulk_create", _bulk_create())

    async def bulk_update(
        self, model: str, records: List[Dict[str, Any]], key_field: str = "id"
    ) -> List[Dict[str, Any]]:
        """
        Update multiple records in bulk.

        Each record dict must contain the key_field (default: "id") to identify
        which record to update. Remaining fields are the values to set.

        Args:
            model: Model name (e.g., "User")
            records: List of record dicts, each must include key_field
            key_field: Field used to identify records (default "id")

        Returns:
            List of updated records

        Example:
            updated = await db.express.bulk_update("User", [
                {"id": "user-1", "name": "Alice Updated"},
                {"id": "user-2", "name": "Bob Updated"},
            ])
        """

        async def _bulk_update():
            results = []
            for record in records:
                record_id = record.get(key_field)
                if record_id is None:
                    continue
                fields = {k: v for k, v in record.items() if k != key_field}
                if not fields:
                    continue
                updated = await self.update(model, str(record_id), fields)
                results.append(updated)

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "bulk_update", record_id=None)

            return results

        return await self._execute_with_timing(f"{model}.bulk_update", _bulk_update())

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

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "bulk_delete", record_id=None)

            # Handle different result formats
            if isinstance(result, bool):
                return result
            elif isinstance(result, dict):
                # Check 'success' first since 'deleted' may be a count (int) not bool
                return result.get("success", True)
            return True

        return await self._execute_with_timing(f"{model}.bulk_delete", _bulk_delete())

    async def bulk_upsert(
        self,
        model: str,
        records: List[Dict[str, Any]],
        conflict_on: Optional[List[str]] = None,
        batch_size: int = 1000,
    ) -> Dict[str, Any]:
        """Bulk upsert (insert-or-update) multiple records.

        Uses database-native ``INSERT ... ON CONFLICT`` for optimal
        performance.  Returns structured results with insert/update
        breakdown rather than a bare list.

        Args:
            model: Model name (e.g., "User")
            records: List of record data dicts
            conflict_on: Fields for conflict detection (default: ["id"]).
                Each field name is validated against the model schema.
            batch_size: Records processed per database batch (default 1000)

        Returns:
            ``{"records": [...], "created": int, "updated": int, "total": int}``

        Example:
            result = await db.express.bulk_upsert("User", [
                {"id": "u1", "name": "Alice", "email": "alice@example.com"},
                {"id": "u2", "name": "Bob", "email": "bob@example.com"},
            ], conflict_on=["id"])
            print(result["created"], result["updated"])
        """
        conflict_fields = conflict_on or ["id"]

        # Validate conflict_on fields against the model schema.
        try:
            known_fields = set(self._db.get_model_fields(model))
            unknown = [f for f in conflict_fields if f not in known_fields]
            if unknown:
                raise ValueError(
                    f"bulk_upsert: conflict_on fields {unknown} not found "
                    f"in model '{model}'. Known fields: {sorted(known_fields)}"
                )
        except AttributeError:
            pass  # get_model_fields not available — skip validation

        async def _bulk_upsert():
            node = self._create_node(model, "BulkUpsert")
            # BulkUpsertNode accepts conflict_columns in its config.
            node.conflict_columns = conflict_fields
            node.batch_size = batch_size
            result = await node.async_run(data=records)

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "bulk_upsert", record_id=None)

            # Return structured result with counts.
            if isinstance(result, dict):
                return {
                    "records": result.get("records", []),
                    "created": result.get("inserted", 0),
                    "updated": result.get("updated", 0),
                    "total": result.get("total", len(records)),
                }
            return {
                "records": result if isinstance(result, list) else [],
                "created": 0,
                "updated": 0,
                "total": len(records),
            }

        return await self._execute_with_timing(f"{model}.bulk_upsert", _bulk_upsert())

    # ========================================================================
    # Cache Helpers (TSG-104)
    # ========================================================================

    def _resolve_tenant_id(self) -> Optional[str]:
        """Return the tenant_id for cache partitioning, or ``None``.

        Enforces multi-tenant key isolation on every Express cache read
        and write. When the DataFlow instance is configured with
        ``multi_tenant=True``, the caller MUST have set a tenant via
        :class:`dataflow.core.tenant_context.TenantContextSwitch` (or
        the ContextVar bound by middleware) before invoking any Express
        method. A missing tenant is an invariant violation — falling
        back to a shared ``default`` namespace would leak data across
        tenants, so we raise.

        Returns:
            The current tenant_id when multi-tenant mode is on; ``None``
            in single-tenant mode.

        Raises:
            TenantRequiredError: If multi-tenant mode is on and no
                tenant is bound to the current async context.
        """
        config = getattr(self._db, "config", None)
        security = getattr(config, "security", None) if config is not None else None
        # ``is True`` (strict identity) rather than ``bool(...)`` so that
        # MagicMock-based test fixtures, which return a truthy Mock for
        # any attribute access, do not accidentally activate the
        # multi-tenant code path. Real SecurityConfig always stores a
        # plain bool.
        multi_tenant = getattr(security, "multi_tenant", False) is True
        if not multi_tenant:
            return None
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise TenantRequiredError(
                "DataFlow is configured with multi_tenant=True but no "
                "tenant_id is bound to the current context. Bind one via "
                "`db.tenant_context.switch(tenant_id)` / "
                "`aswitch(tenant_id)` before calling Express methods."
            )
        return tenant_id

    async def _cache_get(
        self,
        model: str,
        operation: str,
        params: Any,
        effective_ttl: int,
    ) -> Optional[Any]:
        """Return cached value or ``None``.  Increments hit/miss counters."""
        if not self._cache_enabled or not self._cache_manager or effective_ttl <= 0:
            return None
        tenant_id = self._resolve_tenant_id()
        cache_key = self._key_gen.generate_express_key(
            model, operation, params, tenant_id=tenant_id
        )
        cached = await self._cache_manager.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached
        self._cache_misses += 1
        return None

    async def _cache_set(
        self,
        model: str,
        operation: str,
        params: Any,
        value: Any,
        effective_ttl: int,
    ) -> None:
        """Store *value* in the cache if caching is active."""
        if (
            not self._cache_enabled
            or not self._cache_manager
            or effective_ttl <= 0
            or value is None
        ):
            return
        tenant_id = self._resolve_tenant_id()
        cache_key = self._key_gen.generate_express_key(
            model, operation, params, tenant_id=tenant_id
        )
        await self._cache_manager.set(cache_key, value, ttl=effective_ttl)

    async def _invalidate_model_cache(self, model: str) -> None:
        """Clear all cache entries scoped to *model*.

        Delegates to the cache backend's ``invalidate_model`` method so
        that key-format matching logic lives in exactly one place per
        backend (InMemoryCache or AsyncRedisCacheAdapter).

        In multi-tenant mode, invalidation is scoped to the current
        tenant so a write from tenant A cannot drop tenant B's cache
        entries. The backend's ``invalidate_model`` is expected to
        accept an optional ``tenant_id`` kwarg; backends that do not
        yet support it fall back to a model-wide invalidation (safe
        but over-aggressive).
        """
        if not self._cache_enabled or not self._cache_manager:
            return
        tenant_id = self._resolve_tenant_id()
        invalidate_fn = self._cache_manager.invalidate_model
        try:
            await invalidate_fn(model, tenant_id=tenant_id)
        except TypeError:
            # Backend predates tenant-scoped invalidation — fall back
            # to model-wide (conservative: drops the current tenant's
            # entries plus every other tenant's entries for this
            # model). Logged as a warning so the gap is visible.
            if tenant_id is not None:
                logger.warning(
                    "express.cache.invalidate_model.tenant_fallback",
                    extra={
                        "model": model,
                        "tenant_id": tenant_id,
                        "reason": (
                            "cache backend does not accept tenant_id kwarg; "
                            "falling back to model-wide invalidation"
                        ),
                    },
                )
            await invalidate_fn(model)

    # ========================================================================
    # Cache Management
    # ========================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics (sync convenience accessor).

        For full async stats including backend metrics, use
        :meth:`cache_stats`.
        """
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "backend": self._cache_backend_name(),
        }

    async def cache_stats(self) -> Dict[str, Any]:
        """Return cache statistics including backend metrics.

        Returns:
            ``{"hits": int, "misses": int, "size": int, "backend": str}``
        """
        size = 0
        if self._cache_manager is not None:
            if isinstance(self._cache_manager, InMemoryCache):
                size = len(self._cache_manager.cache)
            else:
                # For Redis-backed caches, size requires a server call
                try:
                    metrics = await self._cache_manager.get_metrics()
                    size = metrics.get("cached_entries", 0)
                except Exception:
                    pass
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": size,
            "backend": self._cache_backend_name(),
        }

    def _cache_backend_name(self) -> str:
        """Return a human-readable label for the active cache backend."""
        if not self._cache_enabled or self._cache_manager is None:
            return "disabled"
        if isinstance(self._cache_manager, InMemoryCache):
            return "in_memory"
        return "redis"

    async def clear_cache(self, model: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            model: Optional model name to clear only that model's entries

        Returns:
            Number of entries cleared
        """
        if self._cache_manager is None:
            return 0
        if model:
            return await self._cache_manager.clear_pattern(
                f"{self._key_gen.prefix}:{self._key_gen.version}:{model}:*"
            )
        else:
            if isinstance(self._cache_manager, InMemoryCache):
                count = len(self._cache_manager.cache)
                await self._cache_manager.clear()
                return count
            else:
                # Redis: clear all dataflow keys
                return await self._cache_manager.clear_pattern(
                    f"{self._key_gen.prefix}:*"
                )

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
        self._cache_hits = 0
        self._cache_misses = 0

    # ========================================================================
    # File Import (TSG-102)
    # ========================================================================

    async def import_file(
        self,
        model_name: str,
        file_path: str,
        column_mapping: Optional[Dict[str, Any]] = None,
        type_coercion: Optional[Dict[str, str]] = None,
        upsert: bool = True,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Import records from a file into a model.

        Reads the file via ``FileSourceNode``, then bulk-inserts or
        bulk-upserts into the model.

        Args:
            model_name: Target model name.
            file_path: Path to the input file.
            column_mapping: ``{source_col: target_col}`` renames.
            type_coercion: ``{field: type_name}`` coercions.
            upsert: Use BulkUpsert semantics (default ``True``).
            batch_size: Records per batch.
            **kwargs: Forwarded to ``FileSourceNode.async_run()``.

        Returns:
            ``{"imported": int, "errors": [...]}``
        """
        from dataflow.nodes.file_source import FileSourceNode

        node = FileSourceNode()
        result = await node.async_run(
            file_path=file_path,
            column_mapping=column_mapping,
            type_coercion=type_coercion,
            batch_size=batch_size,
            **kwargs,
        )

        records = result["records"]
        errors = list(result.get("errors", []))
        imported = 0

        if records:
            if upsert:
                for record in records:
                    try:
                        await self.upsert(model_name, record)
                        imported += 1
                    except Exception as exc:
                        errors.append(f"Upsert failed for record: {exc}")
            else:
                try:
                    await self.bulk_create(model_name, records)
                    imported = len(records)
                except Exception as exc:
                    errors.append(f"Bulk create failed: {exc}")

        return {"imported": imported, "errors": errors}


ExpressDataFlow = DataFlowExpress  # Deprecated alias


# ============================================================================
# SyncExpress — Synchronous Wrapper (Issue #187)
# ============================================================================


class SyncExpress:
    """Synchronous wrapper around DataFlowExpress for non-async contexts.

    Provides sync equivalents of all Express CRUD methods for use in CLI scripts,
    synchronous FastAPI handlers, pytest without asyncio, and other non-async code.

    Internally maintains a single persistent event loop in a background thread so
    that database connections (which are bound to an event loop) survive across
    multiple sync calls.

    Usage:
        from dataflow import DataFlow

        db = DataFlow("sqlite:///app.db")

        @db.model
        class User:
            id: str
            name: str

        # Synchronous CRUD via db.express_sync
        user = db.express_sync.create("User", {"id": "u1", "name": "Alice"})
        user = db.express_sync.read("User", "u1")
        users = db.express_sync.list("User", filter={"name": "Alice"})
        count = db.express_sync.count("User")
        db.express_sync.delete("User", "u1")
    """

    def __init__(self, express: DataFlowExpress):
        self._express = express
        # Persistent event loop in a background daemon thread.
        # All async operations are submitted to this loop so database connections
        # (bound to one event loop) remain valid across calls.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _run_sync(self, coro):
        """Run an async coroutine synchronously on the persistent event loop.

        Submits the coroutine to the background loop and blocks until it completes.
        This ensures all async operations share the same event loop, which is
        critical for database drivers like aiosqlite that bind connections to
        the loop they were created on.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    def create(self, model: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single record (sync).

        Args:
            model: Model name (e.g., "User")
            data: Record data including 'id' field

        Returns:
            Created record
        """
        return self._run_sync(self._express.create(model, data))

    def read(
        self,
        model: str,
        id: str,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
    ) -> Optional[Dict[str, Any]]:
        """Read a single record by ID (sync).

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)

        Returns:
            Record or None if not found
        """
        return self._run_sync(
            self._express.read(model, id, cache_ttl, use_primary=use_primary)
        )

    def update(self, model: str, id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update a single record (sync).

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            fields: Fields to update

        Returns:
            Updated record
        """
        return self._run_sync(self._express.update(model, id, fields))

    def delete(self, model: str, id: str) -> bool:
        """Delete a single record (sync).

        Args:
            model: Model name (e.g., "User")
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        return self._run_sync(self._express.delete(model, id))

    def list(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
    ) -> List[Dict[str, Any]]:
        """List records with optional filtering (sync).

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            limit: Maximum records to return (default: 100)
            offset: Skip first N records (default: 0)
            order_by: Optional field name to sort by (e.g., "created_at" or "-created_at" for desc)
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)

        Returns:
            List of records
        """
        return self._run_sync(
            self._express.list(
                model,
                filter,
                limit,
                offset,
                order_by,
                cache_ttl,
                use_primary=use_primary,
            )
        )

    def find_one(
        self,
        model: str,
        filter: Dict[str, Any],
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
    ) -> Optional[Dict[str, Any]]:
        """Find a single record by filter criteria (sync).

        Args:
            model: Model name (e.g., "User")
            filter: MongoDB-style filter criteria (required, must not be empty)
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)

        Returns:
            Single record dict or None if not found
        """
        return self._run_sync(
            self._express.find_one(model, filter, cache_ttl, use_primary=use_primary)
        )

    def count(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
    ) -> int:
        """Count records with optional filtering (sync).

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)

        Returns:
            Number of matching records
        """
        return self._run_sync(
            self._express.count(model, filter, cache_ttl, use_primary=use_primary)
        )

    def upsert(
        self,
        model: str,
        data: Dict[str, Any],
        conflict_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Upsert (insert or update) a record (sync).

        Args:
            model: Model name (e.g., "User")
            data: Record data including 'id' field
            conflict_on: Fields for conflict detection (default: ["id"])

        Returns:
            The upserted record
        """
        return self._run_sync(self._express.upsert(model, data, conflict_on))

    def upsert_advanced(
        self,
        model: str,
        where: Dict[str, Any],
        create: Dict[str, Any],
        update: Optional[Dict[str, Any]] = None,
        conflict_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Advanced upsert with separate where/create/update parameters (sync).

        Args:
            model: Model name (e.g., "User")
            where: Fields to identify the record
            create: Fields to create if record doesn't exist
            update: Fields to update if record exists (default: same as create)
            conflict_on: Fields for conflict detection (default: where keys)

        Returns:
            Dict with 'created' (bool), 'action' (str), 'record' (dict)
        """
        return self._run_sync(
            self._express.upsert_advanced(model, where, create, update, conflict_on)
        )

    # ========================================================================
    # Bulk Operations
    # ========================================================================

    def bulk_create(
        self, model: str, records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create multiple records in bulk (sync).

        Args:
            model: Model name (e.g., "User")
            records: List of record data dicts

        Returns:
            List of created records
        """
        return self._run_sync(self._express.bulk_create(model, records))

    def bulk_update(
        self,
        model: str,
        records: List[Dict[str, Any]],
        key_field: str = "id",
    ) -> List[Dict[str, Any]]:
        """Update multiple records in bulk (sync).

        Args:
            model: Model name (e.g., "User")
            records: List of record dicts, each must include key_field
            key_field: Field used to identify records (default "id")

        Returns:
            List of updated records
        """
        return self._run_sync(self._express.bulk_update(model, records, key_field))

    def bulk_delete(self, model: str, ids: List[str]) -> bool:
        """Delete multiple records by their IDs (sync).

        Args:
            model: Model name (e.g., "User")
            ids: List of record IDs to delete

        Returns:
            True if all deletions succeeded
        """
        return self._run_sync(self._express.bulk_delete(model, ids))

    def bulk_upsert(
        self,
        model: str,
        records: List[Dict[str, Any]],
        conflict_on: Optional[List[str]] = None,
        batch_size: int = 1000,
    ) -> Dict[str, Any]:
        """Bulk upsert (insert-or-update) multiple records (sync).

        Args:
            model: Model name (e.g., "User")
            records: List of record data dicts
            conflict_on: Fields for conflict detection (default: ["id"])
            batch_size: Records per database batch (default 1000)

        Returns:
            ``{"records": [...], "created": int, "updated": int, "total": int}``
        """
        return self._run_sync(
            self._express.bulk_upsert(model, records, conflict_on, batch_size)
        )

    # ========================================================================
    # Cache Management (TSG-104)
    # ========================================================================

    def cache_stats(self) -> Dict[str, Any]:
        """Return cache statistics (sync).

        Returns:
            ``{"hits": int, "misses": int, "size": int, "backend": str}``
        """
        return self._run_sync(self._express.cache_stats())

    def clear_cache(self, model: Optional[str] = None) -> int:
        """Clear cache entries (sync).

        Args:
            model: Optional model name to clear only that model's entries

        Returns:
            Number of entries cleared
        """
        return self._run_sync(self._express.clear_cache(model))

    # ========================================================================
    # File Import (TSG-102)
    # ========================================================================

    def import_file(
        self,
        model_name: str,
        file_path: str,
        column_mapping: Optional[Dict[str, Any]] = None,
        type_coercion: Optional[Dict[str, str]] = None,
        upsert: bool = True,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Import records from a file into a model (sync).

        Args:
            model_name: Target model name.
            file_path: Path to the input file.
            column_mapping: ``{source_col: target_col}`` renames.
            type_coercion: ``{field: type_name}`` coercions.
            upsert: Use BulkUpsert semantics (default ``True``).
            batch_size: Records per batch.
            **kwargs: Forwarded to ``FileSourceNode.async_run()``.

        Returns:
            ``{"imported": int, "errors": [...]}``
        """
        return self._run_sync(
            self._express.import_file(
                model_name,
                file_path,
                column_mapping,
                type_coercion,
                upsert,
                batch_size,
                **kwargs,
            )
        )
