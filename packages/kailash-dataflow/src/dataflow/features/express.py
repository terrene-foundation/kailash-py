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
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, Union

from dataflow.cache.auto_detection import CacheBackend
from dataflow.cache.key_generator import (
    CacheKeyGenerator,
    express_db_instance_fingerprint,
)
from dataflow.cache.memory_cache import InMemoryCache
from dataflow.classification.event_payload import format_record_id_for_event
from dataflow.core.agent_context import get_current_agent_id, get_current_clearance
from dataflow.core.exceptions import (
    DDLFailedError,
    TenantNaturalKeyCollisionError,
    format_tenant_natural_key_collision_message,
    is_pk_unique_violation,
    sanitize_db_error,
)
from dataflow.core.multi_tenancy import TenantRequiredError
from dataflow.core.protection import ProtectionViolation
from dataflow.core.tenant_context import get_current_tenant_id
from dataflow.observability.query_metrics import get_dataflow_query_metrics

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

        # Issue #1606 (the Rust SDK's #1713, v2->v3 cross-SDK lockstep):
        # resolve this DataFlow's credential-free database-instance fingerprint
        # and plumb it into the express keyspace so two DataFlow instances at
        # DIFFERENT databases sharing a process-wide cache backend (e.g. Redis)
        # never collide on the same express key (cross-DB cache bleed). The URL
        # lives on the structured config (``config.database.url``), NOT as a
        # ``database_url`` attribute on the DataFlow instance.
        _db_cfg = getattr(self._db, "config", None)
        _db_url = getattr(getattr(_db_cfg, "database", None), "url", None)
        express_db_instance = express_db_instance_fingerprint(_db_url)
        if express_db_instance is None:
            logger.warning(
                "express.cache.db_instance_disabled: no usable database "
                "identity from the DataFlow URL — cross-DB express cache "
                "isolation is INACTIVE on a shared cache backend; two DataFlow "
                "instances at different databases may read each other's cached "
                "express rows (#1606)",
                extra={"url_present": _db_url is not None},
            )
        # BP-049: plumb the DataFlow classification policy into the cache
        # key generator so classified PKs are hashed before serialisation
        # (issue #520). ``self._db`` holds the owning DataFlow instance.
        self._key_gen = CacheKeyGenerator(
            classification_policy=getattr(self._db, "_classification_policy", None),
            express_db_instance=express_db_instance,
        )

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
        """Execute operation with timing tracking.

        This is the single choke point every ``db.express`` CRUD call
        routes through (create/read/update/delete/list/find_one/count/
        upsert/upsert_advanced/bulk_create/bulk_update/bulk_delete/
        bulk_upsert -- see the call sites below), so it is also where
        the real ``dataflow_query_duration_seconds`` RED histogram is
        recorded (#1708 Wave 3; mirrors ``dataflow.fabric.metrics``).
        Recording happens in ``finally`` so a query that raises still
        contributes to the latency distribution.
        """
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
            model_name, _, op_name = operation.rpartition(".")
            get_dataflow_query_metrics().record_query(
                operation=op_name or operation,
                model=model_name,
                duration_s=elapsed / 1000.0,
            )

    # ========================================================================
    # Validation Helper (TSG-103)
    # ========================================================================

    async def _check_protection_if_enabled(
        self, model: str, operation: str, inputs: Dict[str, Any]
    ) -> None:
        """Express-layer write-protection pre-check (issue #1058 Shard 2).

        Fires the same ``protection_engine.check_operation(...)`` call
        that ``ProtectedNode.async_run`` runs inside the node, BUT BEFORE
        ``_validate_if_enabled`` / ``_trust_check_write`` / ``_create_node``.
        Closes the defense-in-depth gap where a blocked-write attacker
        could trigger field-validator side effects (custom validators may
        log, emit events, hit external services) before the protection
        block fired.

        Invariant I2 ("a blocked write never takes a connection") was
        already held by the inner check (validation is in-process, no DB
        connection acquired). This pre-check tightens the ordering so
        validation never runs on a blocked write either.

        Sentinel discipline (preserves spec invariant I1, single-check):
        after this method returns without raising, the caller MUST set
        ``node._express_protection_precheck_done = True`` on the
        freshly-created node before invoking ``node.async_run`` — the
        inner check in ``ProtectedNode.async_run`` honors that sentinel
        and skips the duplicate ``check_operation`` call (avoiding double
        ``auditor.log_allowed`` entries on the happy path).
        """
        protection_engine = getattr(self._db, "_protection_engine", None)
        if protection_engine is None:
            return
        connection_string = getattr(self._db, "database_url", None)
        # Context shape mirrors ProtectedNode.async_run (node_id / model_fields
        # are not yet available pre-construction; auditor handles missing keys).
        context = {"inputs": inputs}
        protection_engine.check_operation(
            operation=operation,
            model_name=model,
            connection_string=connection_string,
            context=context,
        )

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

        # BP-049 (#520): route classified-field validation errors through
        # the sanitiser so the caller-facing error surface never echoes a
        # classified field NAME or raw VALUE.
        policy = getattr(self._db, "_classification_policy", None)
        result = _validate_instance(proxy, policy=policy, model_name=model)
        if not result.valid:
            error_msgs = "; ".join(e.message for e in result.errors)
            from dataflow.exceptions import DataFlowError

            raise DataFlowError(f"Validation failed for {model}: {error_msgs}")

    # ========================================================================
    # Append-Only Mutation Guard (Issue #839)
    # ========================================================================

    def _check_append_only(self, model: str, operation: str) -> None:
        """Reject mutations on models declared ``@db.model(append_only=True)``.

        Issue #839: append-only models represent immutable event-log
        surfaces. ``update`` / ``delete`` / ``upsert`` /
        ``bulk_update`` / ``bulk_delete`` / ``bulk_upsert`` MUST raise
        :class:`AppendOnlyViolationError` BEFORE any SQL is issued and
        BEFORE any side effect (cache invalidation, event emit, trust
        record). The check fires at the express call site so callers
        get a typed, grep-able error referencing both the model and the
        operation they attempted.

        ``Create`` / ``BulkCreate`` / ``Read`` / ``List`` / ``Count``
        do NOT call this guard — they are permitted on append-only
        models by design.
        """
        model_info = self._db._models.get(model)
        if not isinstance(model_info, dict):
            return
        if not model_info.get("append_only", False):
            return
        from dataflow.exceptions import AppendOnlyViolationError

        op_human = operation.replace("_", " ").capitalize()
        raise AppendOnlyViolationError(
            f"{op_human} rejected on append-only model '{model}'. "
            f"Models declared with @db.model(append_only=True) only "
            f"accept Create / BulkCreate / Read / List / Count. "
            f"Remove `append_only=True` from the @db.model() decorator "
            f"to permit mutations. See issue #839."
        )

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
                # Issue #1552 (HIGH-1): the persisted trust-audit store
                # (query_wrapper.record_query_failure → result=f"failure:{error}")
                # is a broader-access surface than the DB. A single-record
                # create/update/delete/upsert that hits a UNIQUE violation funnels
                # its RAW driver exception here; sanitize the VALUE-bearing driver
                # error (PG DETAIL/Key, MySQL Duplicate entry) before it is persisted
                # in the clear. The re-raised exception (caller's own) is left raw
                # for local diagnosability, mirroring #1550.
                error=sanitize_db_error(str(error)),
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

    def _safe_record_id(self, model: str, id: Any) -> Optional[str]:
        """Return an event/log/audit-safe ``record_id`` for this model.

        Single-point filter for every PK value that leaves the Express
        write path into a log line, audit row, trust-plane event, or
        error-surface string. Classified string PKs come back as
        ``"sha256:XXXXXXXX"``; integers and unclassified strings pass
        through as ``str(value)``. Cross-SDK contract matches
        ``kailash-rs`` BP-048 / BP-049 so a PK hashed in Python and a
        PK hashed in Rust produce the same fingerprint for forensic
        correlation.

        Mandated by ``rules/event-payload-classification.md`` Rule 1 and
        ``rules/dataflow-classification.md``. See issue #520 (BP-049).
        """
        policy = getattr(self._db, "_classification_policy", None)
        return format_record_id_for_event(policy, model, id)

    def _safe_query_params(
        self, model: str, params: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Return a copy of ``params`` with classified PK values hashed.

        Audit / trust-plane paths take a dict of query parameters
        (``{"id": id}``, ``{"id": id, "fields": fields}``). This helper
        hashes the ``id`` slot when the model has a classified PK. Other
        keys are passed through unchanged; callers that need to redact
        classified field VALUES inside ``fields`` MUST do so through the
        classification masking helpers on the read path.

        Mandated by issue #520 (BP-049).
        """
        if params is None:
            return None
        if "id" not in params:
            return params
        safe = dict(params)
        safe["id"] = self._safe_record_id(model, params["id"])
        return safe

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

    def _tenant_pk_collision_context(
        self, model: str, error_text: str, force_collision: bool = False
    ) -> Optional[Tuple[str, str]]:
        """Return ``(tenant_id, table_name)`` iff ``error_text`` is a PK-unique
        violation on a ``multi_tenant`` model whose active tenant is bound and
        whose table is resolvable — the precondition BOTH the single-record and
        the bulk cross-tenant collision diagnostics share (issue #1526).
        Returns ``None`` (caller keeps the original error path) otherwise.

        ``force_collision`` (cross-tenant WRITE breach fix): the bulk path's
        tenant-scoped DO-UPDATE guard SUPPRESSES the offending row rather than
        letting the driver raise a PK-unique violation, so there is no driver
        message to match. When the guard already PROVED a cross-tenant collision
        (``cross_tenant_conflict`` in the bulk result), pass ``force_collision``
        to bypass ONLY the ``is_pk_unique_violation`` text gate — every other
        precondition (multi_tenant + bound tenant + tenant_id field + resolvable
        table) still holds.

        Zero-cost short-circuit for single-tenant models: the multi_tenant
        guard returns ``None`` before any string inspection. The model must
        carry the ``tenant_id`` column DataFlow injects for multi_tenant
        instances (defends against a non-tenant model on a multi_tenant
        DataFlow); an introspection failure means we cannot confirm the
        multi_tenant shape → classification does not apply and the caller
        re-raises / re-surfaces the ORIGINAL driver error (no hiding).
        """
        security = getattr(self._db.config, "security", None)
        if not (security and getattr(security, "multi_tenant", False) is True):
            return None
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return None
        model_fields: Any = None
        try:
            model_fields = self._db.get_model_fields(model)
        except Exception:
            # Introspection failed — cannot confirm the multi_tenant shape, so
            # decline (the caller keeps the ORIGINAL error path; nothing hidden).
            model_fields = None
        if not model_fields or "tenant_id" not in model_fields:
            return None
        # Resolve the table name for PK-column matching; if it cannot be
        # resolved, do not risk a false positive — keep the original path.
        class_to_table = getattr(self._db, "_class_name_to_table_name", None)
        table_name: Optional[str] = None
        if callable(class_to_table):
            try:
                table_name = class_to_table(model)
            except Exception:
                # Table-name resolution failed — decline rather than risk a
                # false-positive collision claim; the raw error path stands.
                table_name = None
        if not table_name:
            return None
        # The guard already proved the cross-tenant collision → skip the
        # driver-message match (there is no driver error to match).
        if not force_collision and not is_pk_unique_violation(error_text, table_name):
            return None
        return tenant_id, table_name

    async def _maybe_tenant_natural_key_collision(
        self,
        model: str,
        id_value: object,
        error_text: str,
        original_error: Optional[BaseException] = None,
    ) -> Optional[TenantNaturalKeyCollisionError]:
        """Return a :class:`TenantNaturalKeyCollisionError` iff ``error_text`` is
        a CROSS-TENANT PRIMARY-KEY collision on a ``multi_tenant`` model, else
        ``None`` (issue #1526).

        A ``multi_tenant=True`` model keeps a single-column ``id`` PK (NOT a
        composite ``(tenant_id, id)``), so the ``id`` is a globally-unique
        surrogate: two DIFFERENT tenants writing the same natural key collide on
        that PK. That is fail-closed and SAFE — no cross-tenant data leaks — but
        the raw driver message is opaque.

        A same-tenant duplicate (the current tenant re-inserting its OWN ``id``)
        produces the IDENTICAL PK-unique driver message, so the driver text alone
        cannot distinguish the two. To avoid over-broadening (converting an
        ordinary same-tenant duplicate into a misleading cross-tenant claim),
        this helper disambiguates WITHOUT reading the other tenant's row: a
        TENANT-SCOPED read for ``id_value`` returns a row IFF the CURRENT tenant
        already owns it (→ same-tenant duplicate → keep the ordinary path). If
        the read returns ``None`` while the PK provably exists (we are handling a
        PK-unique violation), the colliding row belongs to ANOTHER tenant → the
        actionable cross-tenant error. The disambiguation never reads or exposes
        the other tenant's data (``rules/tenant-isolation.md``,
        ``rules/security.md``); the returned error names ONLY the caller's own
        ``tenant_id`` + supplied ``id``.

        For every non-matching error it returns ``None`` so the caller keeps the
        original error path (no over-broadening, no silent normalization —
        zero-tolerance Rule 3). Zero-cost short-circuit for single-tenant models:
        the multi_tenant guard returns ``None`` before any string inspection.
        """
        ctx = self._tenant_pk_collision_context(model, error_text)
        if ctx is None:
            return None
        tenant_id, _table_name = ctx
        # Without the caller's id we cannot run the same-tenant disambiguation;
        # decline to convert rather than assert an unverifiable cross-tenant claim.
        if id_value is None:
            return None
        # Same-tenant duplicate vs cross-tenant collision. A tenant-scoped read
        # sees ONLY the current tenant's rows (QueryInterceptor), so a hit means
        # the current tenant already owns this id → ordinary duplicate.
        existing = await self.read(model, str(id_value), cache_ttl=0)
        if existing is not None:
            return None
        return TenantNaturalKeyCollisionError(
            model_name=model,
            tenant_id=tenant_id,
            colliding_id=id_value,
            original_error=original_error,
        )

    async def _maybe_bulk_tenant_natural_key_collision(
        self,
        model: str,
        records: List[Dict[str, Any]],
        error_text: str,
        force_collision: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Return an actionable cross-tenant collision DIAGNOSTIC (a dict, NEVER
        raised) iff a bulk write's ``error_text`` is a cross-tenant natural-key
        PK collision on a ``multi_tenant`` model, else ``None`` (issue #1526).

        The bulk paths (:meth:`bulk_create` / :meth:`bulk_upsert`) use
        partial-failure-dict semantics: they RETURN a failure dict, they do NOT
        raise. This helper mirrors the single-record
        :meth:`_maybe_tenant_natural_key_collision` disambiguation into that
        dict shape so a bulk collision surfaces the SAME actionable,
        tenant-scoped, no-cross-tenant-leak diagnostic the single path raises —
        WITHOUT converting the bulk contract to raise-on-first-error.

        Disambiguation (never reads another tenant's data):

        * The batch failed on a PK-unique violation, so NOTHING in the failing
          batch was inserted. A TENANT-SCOPED read (QueryInterceptor) of each
          caller-supplied ``id`` returns a row IFF the CURRENT tenant already
          owns it.
        * If the current tenant OWNS any supplied id, that id is a same-tenant
          duplicate that alone explains the PK-unique failure. Mirroring the
          single path's no-over-broadening discipline, the helper then DECLINES
          (returns ``None``) rather than assert an unverifiable cross-tenant
          claim about the remaining ids — the batch is atomic, so a not-owned
          id in the same batch may simply be a would-have-inserted-fine new id.
        * If the current tenant owns NONE of the supplied ids yet the batch
          still failed on a PK-unique violation, then at least one not-owned id
          provably collides with ANOTHER tenant's row. Those not-owned ids are
          the caller's OWN ids (no cross-tenant leak); the diagnostic names them
          with an at-least-one framing.

        Returns a dict ``{"error_type", "tenant_id", "colliding_ids",
        "message"}`` naming ONLY the caller's own tenant_id + supplied ids, or
        ``None`` to keep the raw failure-dict error path (no over-broadening, no
        silent normalization — zero-tolerance Rule 3). The ``message`` is built
        by the SAME shared builder the single-path exception uses, so the two
        surfaces never drift (``framework-first.md`` — no parallel hierarchy).
        """
        ctx = self._tenant_pk_collision_context(
            model, error_text, force_collision=force_collision
        )
        if ctx is None:
            return None
        tenant_id, _table_name = ctx
        if not records:
            return None
        # An INTRA-batch duplicate id is a caller-side duplicate that alone
        # explains a PK-unique failure — it is NOT a cross-tenant collision.
        # Decline (keep the raw error) rather than mislabel it: a tenant-scoped
        # read of the duplicated id returns None (nothing was inserted — the
        # batch failed), which would otherwise false-positive as cross-tenant.
        supplied_ids = [
            str(r.get("id"))
            for r in records
            if isinstance(r, dict) and r.get("id") is not None
        ]
        if len(supplied_ids) != len(set(supplied_ids)):
            return None
        # Partition the caller's OWN supplied ids into owned (same-tenant) vs
        # not-owned via TENANT-SCOPED reads. Never reads another tenant's data.
        candidate_ids: List[Any] = []
        seen: set = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            rid = record.get("id")
            if rid is None:
                continue
            key = str(rid)
            if key in seen:
                continue
            seen.add(key)
            existing = await self.read(model, key, cache_ttl=0)
            if existing is not None:
                # Current tenant already owns this id → the batch failure is
                # explained by a same-tenant duplicate. Decline to convert (no
                # over-broadening onto the remaining ids), exactly as the
                # single-record path declines a same-tenant duplicate.
                return None
            candidate_ids.append(rid)
        if not candidate_ids:
            # No caller-supplied id was resolvable → cannot attribute; keep the
            # raw failure-dict error path rather than assert an unverifiable
            # cross-tenant claim.
            return None
        return {
            "error_type": "TenantNaturalKeyCollisionError",
            "tenant_id": tenant_id,
            "colliding_ids": candidate_ids,
            "message": format_tenant_natural_key_collision_message(
                model, tenant_id, candidate_ids
            ),
        }

    async def _raise_for_failed_result(
        self,
        model: str,
        operation: str,
        result: Any,
        id_value: object = None,
    ) -> None:
        """Convert a dict-shaped node failure into a raised typed exception.

        Express documents create/update/delete/upsert as raise-on-failure
        (see read() at line 653 + the docstring at the top of this module).
        The underlying CRUD nodes in ``dataflow/core/nodes.py`` swallow
        exceptions in the auto-migration path and return
        ``{"success": False, "error": ...}`` for backward compatibility
        with WorkflowBuilder consumers. Without this helper, every
        Express call returns the failure dict instead of raising — which
        breaks the DPI-A 2.4.0 fail-fast contract for DDL failures
        (issue #759) and silently records a TRUST success while the
        underlying op failed.

        Single filter point at the express layer (mirroring
        ``rules/event-payload-classification.md`` Rule 1) is the only
        structural defense against drift across create/update/delete/
        upsert and any future mutation primitive.

        Classification:
          * If the engine recorded a DDL failure for ``model`` AND
            fail-fast mode is active, raise :class:`DDLFailedError` with
            the original statement preview attached.
          * Otherwise, raise a generic :class:`RuntimeError` carrying
            the node's error string so the caller still sees a typed
            exception rather than a success-shaped failure dict.

        warn-mode preserves the legacy log-and-continue path because
        ``_check_failed_ddl`` skips raising when
        ``_auto_migrate_warn`` is True; the dict-failure result then
        flows through the normal success path. See issue #759 acceptance
        criteria + ``test_failed_ddl_with_warn_mode_still_bounded``.
        """
        if not (isinstance(result, dict) and result.get("success") is False):
            return
        error_msg = result.get("error") or "operation failed"
        # Issue #1526: a multi_tenant write that collides on the natural-key PK
        # with another tenant's row surfaces here as a raw ``UNIQUE constraint
        # failed: <table>.id`` (SQLite) / ``<table>_pkey`` (PG) / ``for key
        # 'PRIMARY'`` (MySQL). Convert THAT specific case into an actionable,
        # caller-facing error naming the caller's own tenant_id + id and the
        # schema-per-tenant / UUID remediation. Narrow by construction (PK-only,
        # multi_tenant-only); every other failure keeps the DDL/RuntimeError
        # path below (no over-broadening, no silent normalization).
        collision = await self._maybe_tenant_natural_key_collision(
            model, id_value, str(error_msg)
        )
        if collision is not None:
            raise collision
        # Try the typed DDL classification first: the engine already
        # recorded the failed DDL via ``_record_failed_ddl`` upstream.
        # The engine records under TWO key shapes depending on the
        # call path:
        #   * single-model path (engine.py:2157, 8263) records under
        #     model class name (``DpiD2Child``)
        #   * bulk-DDL path (engine.py:7903, 7992, 8466) records under
        #     extracted SQL identifier (``dpi_d2_children``) because
        #     ``_extract_table_from_statement`` operates on raw DDL.
        # ``_check_failed_ddl`` matches by exact key so we MUST probe
        # both shapes; without the table-name fallback the bulk-DDL
        # failures (the common DPI-A path) silently fall through to
        # the generic RuntimeError and downstream callers expecting
        # ``DDLFailedError`` (issue #759 acceptance) miss it.
        check = getattr(self._db, "_check_failed_ddl", None)
        if callable(check):
            candidates = [model]
            class_to_table = getattr(self._db, "_class_name_to_table_name", None)
            if callable(class_to_table):
                try:
                    table_candidate = class_to_table(model)
                except Exception:
                    table_candidate = None
                if table_candidate and table_candidate not in candidates:
                    candidates.append(table_candidate)
            for candidate in candidates:
                try:
                    check(candidate)  # raises DDLFailedError when applicable
                except DDLFailedError:
                    raise
                except Exception:
                    # If the typed check itself fails for any reason, fall
                    # through to the generic raise — never swallow.
                    pass
        raise RuntimeError(
            f"express.{operation} failed for model {model!r}: {error_msg}"
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
            # Issue #1058 Shard 2: protection precheck fires BEFORE
            # _validate_if_enabled to prevent field-validator side
            # effects on blocked writes. See _check_protection_if_enabled
            # for the sentinel-discipline contract that preserves spec
            # invariant I1 (single check, no double-audit) end-to-end.
            await self._check_protection_if_enabled(model, "create", data)
            await self._validate_if_enabled(model, data)
            # Phase 5.11: trust access check before the write.
            plan = await self._trust_check_write(model, "create")
            try:
                node = self._create_node(model, "Create")
                # Sentinel honored by ProtectedNode.async_run to skip the
                # duplicate check_operation call on the Express path.
                node._express_protection_precheck_done = True
                result = await node.async_run(**data)
            except Exception as exc:
                # Issue #1526: if the CreateNode RAISES a PK-unique violation
                # (rather than returning a failure dict), convert the same
                # multi_tenant cross-tenant collision into the actionable typed
                # error before recording/re-raising. Non-collision errors keep
                # the raw path unchanged.
                collision = await self._maybe_tenant_natural_key_collision(
                    model,
                    data.get("id") if isinstance(data, dict) else None,
                    str(exc),
                    original_error=exc,
                )
                if collision is not None:
                    await self._trust_record_failure(
                        model, "create", plan, collision, query_params=data
                    )
                    raise collision from exc
                await self._trust_record_failure(
                    model, "create", plan, exc, query_params=data
                )
                raise

            # Issue #759 (DPI-A): the underlying CreateNode swallows
            # auto-migration / DDL failures and returns a failure dict
            # instead of raising. Convert that to a typed exception BEFORE
            # any side effect (cache invalidation, event emit, trust
            # success record) so failures propagate end-to-end through
            # the user-facing express API. See _raise_for_failed_result.
            if isinstance(result, dict) and result.get("success") is False:
                try:
                    await self._raise_for_failed_result(
                        model,
                        "create",
                        result,
                        id_value=data.get("id") if isinstance(data, dict) else None,
                    )
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

            # TSG-201: Emit write event. ``_emit_write_event`` routes
            # ``record_id`` through ``format_record_id_for_event``
            # internally (BP-048), so pass the raw PK — double-hashing
            # would break cross-SDK fingerprint correlation.
            if hasattr(self._db, "_emit_write_event"):
                raw_record_id = (
                    result.get("id") if result and isinstance(result, dict) else None
                )
                self._db._emit_write_event(model, "create", record_id=raw_record_id)

            await self._trust_record_success(
                model, "create", plan, rows_affected=1, query_params=data
            )
            # Issue #490: classification redaction MUST apply on the
            # mutation return path, same contract as read(). See
            # rules/dataflow-classification.md MUST Rule 1.
            return self._apply_classification_mask_record(model, result)

        return await self._execute_with_timing(f"{model}.create", _create())

    async def read(
        self,
        model: str,
        id: Union[str, int],
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Read a single record by ID.

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            cache_ttl: Optional cache TTL override
            include_deleted: For soft_delete models, when True a tombstoned
                row (non-null ``deleted_at``) is returned instead of treated
                as not-found (default: False). Part of the cache-key params so
                an include-deleted read never collides with a default read.

        Returns:
            Record or None if not found

        Example:
            user = await db.express.read("User", "user-123")
            tombstoned = await db.express.read("Doc", "doc-1", include_deleted=True)
        """
        effective_ttl = cache_ttl if cache_ttl is not None else self._default_cache_ttl

        # include_deleted is part of the cache-key params (distinct slot from a
        # default read) AND forwarded to the ReadNode tombstone check.
        cache_params = {"id": id, "include_deleted": include_deleted}

        # Check cache first
        cached_result = await self._cache_get(
            model, "read", cache_params, effective_ttl
        )
        if cached_result is not None:
            logger.debug("express.cache_hit_for_read", extra={"model": model, "id": id})
            return cached_result

        async def _read():
            # Phase 5.11: trust access check before the read.
            plan = await self._trust_check_read(model, {"id": id})
            try:
                node = self._create_node(model, "Read")
                result = await node.async_run(id=id, include_deleted=include_deleted)

                # Apply PII/column filter from the trust plan, if any.
                if plan is not None:
                    result = self._db._trust_executor.apply_result_filter(result, plan)

                # Phase 5.10: apply classification masking based on the
                # caller's clearance context.
                result = self._apply_classification_mask_record(model, result)

                # Cache result (TSG-104) — same key params as the get above.
                await self._cache_set(
                    model, "read", cache_params, result, effective_ttl
                )

                await self._trust_record_success(
                    model,
                    "read",
                    plan,
                    rows_affected=1 if result is not None else 0,
                    query_params=self._safe_query_params(model, {"id": id}),
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
                        extra={"model": model, "id": self._safe_record_id(model, id)},
                    )
                    await self._trust_record_success(
                        model,
                        "read",
                        plan,
                        rows_affected=0,
                        query_params=self._safe_query_params(model, {"id": id}),
                    )
                    return None
                # Re-raise other errors
                await self._trust_record_failure(
                    model,
                    "read",
                    plan,
                    e,
                    query_params=self._safe_query_params(model, {"id": id}),
                )
                raise

        return await self._execute_with_timing(f"{model}.read", _read())

    async def update(
        self, model: str, id: Union[str, int], fields: Dict[str, Any]
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
            self._check_append_only(model, "update")
            # Issue #1058 Shard 2: protection precheck fires BEFORE
            # _validate_if_enabled (see create() for the contract).
            await self._check_protection_if_enabled(
                model, "update", {"id": id, "fields": fields}
            )
            await self._validate_if_enabled(model, fields)
            # Phase 5.11: trust access check before the write.
            plan = await self._trust_check_write(model, "update")
            try:
                node = self._create_node(model, "Update")
                node._express_protection_precheck_done = True
                result = await node.async_run(filter={"id": id}, fields=fields)
            except Exception as exc:
                await self._trust_record_failure(
                    model,
                    "update",
                    plan,
                    exc,
                    query_params=self._safe_query_params(
                        model, {"id": id, "fields": fields}
                    ),
                )
                raise

            # Issue #759 (DPI-A): convert dict-shaped node failure into a
            # raised typed exception before any side effect. See
            # _raise_for_failed_result.
            if isinstance(result, dict) and result.get("success") is False:
                try:
                    await self._raise_for_failed_result(model, "update", result)
                except Exception as exc:
                    await self._trust_record_failure(
                        model,
                        "update",
                        plan,
                        exc,
                        query_params=self._safe_query_params(
                            model, {"id": id, "fields": fields}
                        ),
                    )
                    raise

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event. ``_emit_write_event`` hashes
            # classified PKs internally (BP-048) — pass raw ``id``.
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "update", record_id=id)

            await self._trust_record_success(
                model,
                "update",
                plan,
                rows_affected=1,
                query_params=self._safe_query_params(
                    model, {"id": id, "fields": fields}
                ),
            )
            # Issue #490: normalize the return to the full record shape
            # (same as read()) and apply read-path redaction. UpdateNode's
            # return is dialect-dependent (PostgreSQL UPDATE ... RETURNING
            # includes the row; SQLite returns metadata only), so read-back
            # is the only portable way to match the documented contract.
            # NOTE: redaction contract — read() applies
            # _apply_classification_mask_record. Do NOT inline a SELECT +
            # row_to_dict here without porting the redaction call, or
            # classified fields leak on every update response.
            # See rules/dataflow-classification.md MUST Rules 1 and 2.
            fresh = await self.read(model, id, cache_ttl=0)
            if isinstance(fresh, dict):
                return fresh
            return self._apply_classification_mask_record(model, result)

        return await self._execute_with_timing(f"{model}.update", _update())

    async def delete(self, model: str, id: Union[str, int]) -> bool:
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
            self._check_append_only(model, "delete")
            # Issue #1058 Shard 2: protection precheck fires BEFORE any
            # other side-effecting work (see create() for the contract).
            await self._check_protection_if_enabled(model, "delete", {"id": id})
            # Phase 5.11: trust access check before the write.
            plan = await self._trust_check_write(model, "delete")
            try:
                node = self._create_node(model, "Delete")
                node._express_protection_precheck_done = True
                result = await node.async_run(id=id)
            except Exception as exc:
                await self._trust_record_failure(
                    model,
                    "delete",
                    plan,
                    exc,
                    query_params=self._safe_query_params(model, {"id": id}),
                )
                raise

            # Issue #759 (DPI-A): convert dict-shaped node failure into a
            # raised typed exception before any side effect.
            if isinstance(result, dict) and result.get("success") is False:
                try:
                    await self._raise_for_failed_result(model, "delete", result)
                except Exception as exc:
                    await self._trust_record_failure(
                        model,
                        "delete",
                        plan,
                        exc,
                        query_params=self._safe_query_params(model, {"id": id}),
                    )
                    raise

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event. ``_emit_write_event`` hashes
            # classified PKs internally (BP-048) — pass raw ``id``.
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "delete", record_id=id)

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
                query_params=self._safe_query_params(model, {"id": id}),
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
        include_deleted: bool = False,
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
            include_deleted: For soft_delete models, when True bypass the
                ``deleted_at IS NULL`` auto-filter and return tombstoned rows
                too (default: False). Part of the cache-key params so an
                include-deleted result never collides with a default query.

        Returns:
            List of records

        Example:
            users = await db.express.list("User", filter={"status": "active"}, limit=50)
            all_incl_deleted = await db.express.list("Doc", include_deleted=True)
        """
        # include_deleted is placed INTO params so it (a) forwards to the
        # ListNode auto-filter and (b) becomes part of the cache key — a
        # False result MUST NOT be served to a True query (tenant-isolation.md
        # cache-key discipline applied to the soft-delete dimension).
        params = {
            "filter": filter or {},
            "limit": limit,
            "offset": offset,
            "include_deleted": include_deleted,
        }
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
        include_deleted: bool = False,
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
            include_deleted: For soft_delete models, when True bypass the
                ``deleted_at IS NULL`` auto-filter so a tombstoned row matched
                by this (non-PK) filter is returned instead of treated as
                not-found (default: False). Part of the cache-key params so an
                include-deleted lookup never collides with a default find_one
                (matching list/read/count).

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

            # Fetch a tombstoned row via a non-PK filter
            gone = await db.express.find_one(
                "Doc", filter={"slug": "archived"}, include_deleted=True
            )
        """
        # Validate filter is not empty - empty filter should use list()
        if not filter:
            raise ValueError(
                "find_one() requires a non-empty filter. "
                "For unfiltered queries, use list() with limit=1."
            )

        # include_deleted is placed INTO params so it (a) forwards to the
        # ListNode auto-filter and (b) becomes part of the cache key — a
        # False result MUST NOT be served to a True query (tenant-isolation.md
        # cache-key discipline applied to the soft-delete dimension), matching
        # list/read/count.
        params = {
            "filter": filter,
            "limit": 1,
            "offset": 0,
            "include_deleted": include_deleted,
        }
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
        include_deleted: bool = False,
    ) -> int:
        """
        Count records with optional filtering.

        Uses COUNT(*) query for optimal performance.

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            cache_ttl: Optional cache TTL override
            include_deleted: For soft_delete models, when True count tombstoned
                rows too (bypass the ``deleted_at IS NULL`` auto-filter;
                default: False). Part of the cache-key params so an
                include-deleted count never collides with a default count.

        Returns:
            Number of matching records

        Example:
            active_count = await db.express.count("User", filter={"status": "active"})
            total_incl_deleted = await db.express.count("Doc", include_deleted=True)
        """
        # include_deleted in params → forwarded to the CountNode auto-filter
        # AND part of the cache key (distinct slot from a default count).
        params = {"filter": filter or {}, "include_deleted": include_deleted}
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
            self._check_append_only(model, "upsert")
            # Issue #1058 Shard 2: protection precheck fires BEFORE
            # _validate_if_enabled (see create() for the contract).
            await self._check_protection_if_enabled(model, "upsert", data)
            await self._validate_if_enabled(model, data)
            node = self._create_node(model, "Upsert")
            node._express_protection_precheck_done = True

            # Simple upsert: use data as both create and update
            # Use id field for where clause by default
            where_fields = conflict_on or ["id"]
            where = {k: data[k] for k in where_fields if k in data}

            params = {"where": where, "create": data, "update": data}
            if conflict_on:
                params["conflict_on"] = conflict_on

            result = await node.async_run(**params)

            # Issue #759 (DPI-A): convert dict-shaped node failure into a
            # raised typed exception before any side effect.
            if isinstance(result, dict) and result.get("success") is False:
                await self._raise_for_failed_result(
                    model,
                    "upsert",
                    result,
                    id_value=data.get("id") if isinstance(data, dict) else None,
                )

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event. ``_emit_write_event`` hashes
            # classified PKs internally (BP-048) — pass raw PK.
            if hasattr(self._db, "_emit_write_event"):
                raw_record_id = (
                    data.get("id") if isinstance(data, dict) and "id" in data else None
                )
                self._db._emit_write_event(model, "upsert", record_id=raw_record_id)

            # Return the record directly for simpler API.
            # Issue #490: normalize the return to the full record shape
            # (same as read()) and apply read-path redaction. UpsertNode's
            # return is dialect-dependent (PostgreSQL ON CONFLICT ... RETURNING
            # includes the row; SQLite often returns metadata only), so
            # read-back is the only portable way to match the documented
            # contract.
            # NOTE: redaction contract — read() applies
            # _apply_classification_mask_record. Do NOT inline a SELECT +
            # row_to_dict here without porting the redaction call.
            # See rules/dataflow-classification.md MUST Rules 1 and 2.
            pk = data.get("id") if isinstance(data, dict) else None
            if pk is not None:
                fresh = await self.read(model, pk, cache_ttl=0)
                if isinstance(fresh, dict):
                    return fresh
            if isinstance(result, dict) and "record" in result:
                return self._apply_classification_mask_record(model, result["record"])
            return self._apply_classification_mask_record(model, result)

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
            self._check_append_only(model, "upsert")
            # Issue #1058 Shard 2: protection precheck (see create()).
            await self._check_protection_if_enabled(
                model, "upsert", {"where": where, "create": create, "update": update}
            )
            node = self._create_node(model, "Upsert")
            node._express_protection_precheck_done = True

            params = {"where": where, "create": create, "update": update or create}
            if conflict_on:
                params["conflict_on"] = conflict_on

            result = await node.async_run(**params)

            # Issue #759 (DPI-A): convert dict-shaped node failure into a
            # raised typed exception before any side effect.
            if isinstance(result, dict) and result.get("success") is False:
                _adv_id = None
                if isinstance(create, dict):
                    _adv_id = create.get("id")
                if _adv_id is None and isinstance(where, dict):
                    _adv_id = where.get("id")
                await self._raise_for_failed_result(
                    model, "upsert_advanced", result, id_value=_adv_id
                )

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event (upsert_advanced is also an upsert)
            # ``_emit_write_event`` hashes classified PKs internally
            # (BP-048) — pass raw PK.
            if hasattr(self._db, "_emit_write_event"):
                raw_record_id = (
                    create.get("id")
                    if isinstance(create, dict) and "id" in create
                    else None
                )
                self._db._emit_write_event(model, "upsert", record_id=raw_record_id)

            # Issue #490: mutation return MUST apply read-path redaction.
            # See rules/dataflow-classification.md MUST Rule 1. The top-level
            # shape is {"created", "action", "record"}; mask the nested
            # "record" dict when present, and also mask any top-level
            # classified column echoed on the envelope itself.
            if isinstance(result, dict):
                if "record" in result and isinstance(result["record"], dict):
                    result = {
                        **result,
                        "record": self._apply_classification_mask_record(
                            model, result["record"]
                        ),
                    }
                result = self._apply_classification_mask_record(model, result)
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
            # Issue #1058 Shard 2: protection precheck (see create()).
            # bulk_create has no _validate_if_enabled call today, but the
            # precheck still lands here so a blocked bulk_create raises
            # ProtectionViolation BEFORE _create_node / node.async_run.
            await self._check_protection_if_enabled(
                model, "bulk_create", {"data": records}
            )
            node = self._create_node(model, "BulkCreate")
            node._express_protection_precheck_done = True
            result = await node.async_run(data=records)

            # Model-scoped cache invalidation (TSG-104)
            await self._invalidate_model_cache(model)

            # TSG-201: Emit write event
            if hasattr(self._db, "_emit_write_event"):
                self._db._emit_write_event(model, "bulk_create", record_id=None)

            # Issue #1526: a multi_tenant bulk write that collides on the
            # natural-key PK with ANOTHER tenant's row surfaces here as a
            # whole-batch failure dict ({"success": False, "error": <sanitized
            # UNIQUE constraint>}). Enrich that failure dict with the SAME
            # actionable, tenant-scoped, no-cross-tenant-leak diagnostic the
            # single-record create path raises — WITHOUT converting the bulk
            # partial-failure-dict contract to raise-on-first-error.
            if isinstance(result, dict) and result.get("success") is False:
                collision = await self._maybe_bulk_tenant_natural_key_collision(
                    model, records, str(result.get("error") or "")
                )
                if collision is not None:
                    result["collision"] = collision
                    result["error"] = collision["message"]

            # Issue #373: WARN on partial failure (observability.md Rule 7)
            if isinstance(result, dict):
                failed = result.get("failed", 0) or result.get("failure_count", 0)
                total = result.get("total", len(records))
                # A batch that failed AS A WHOLE (e.g. a cross-tenant PK-unique
                # collision) reports success=False with processed<total rather
                # than a per-row failed count — still a partial failure that
                # MUST WARN (observability.md Rule 7).
                if not failed and result.get("success") is False:
                    processed = result.get("processed", 0) or 0
                    failed = max(total - processed, 1)
                if failed and failed > 0:
                    logger.warning(
                        "bulk_create.partial_failure",
                        extra={
                            "model": model,
                            "total": total,
                            "failed": failed,
                            "succeeded": total - failed,
                            "first_error": (
                                str(result.get("error"))
                                if result.get("error") is not None
                                else None
                            ),
                        },
                    )

            # Handle different result formats.
            # Issue #490: mutation return MUST apply read-path redaction.
            # See rules/dataflow-classification.md MUST Rule 1.
            if isinstance(result, list):
                return self._apply_classification_mask_rows(model, result)
            elif isinstance(result, dict) and "records" in result:
                return self._apply_classification_mask_rows(model, result["records"])
            elif isinstance(result, dict) and "items" in result:
                return self._apply_classification_mask_rows(model, result["items"])
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
            self._check_append_only(model, "bulk_update")
            # Issue #490 redaction contract: bulk_update delegates to
            # self.update(), which applies _apply_classification_mask_record
            # on its return. Do NOT inline a SELECT + row_to_dict here
            # without porting the redaction call, or classified fields leak
            # on every bulk_update response.
            # See rules/dataflow-classification.md MUST Rule 2.
            results = []
            failed_count = 0
            for record in records:
                record_id = record.get(key_field)
                if record_id is None:
                    failed_count += 1
                    continue
                fields = {k: v for k, v in record.items() if k != key_field}
                if not fields:
                    failed_count += 1
                    continue
                try:
                    updated = await self.update(model, str(record_id), fields)
                    results.append(updated)
                except ProtectionViolation:
                    # Issue #1050 / spec I5: a write-protection block is a
                    # HARD STOP, not a countable per-row data failure. The
                    # per-record `except Exception` below would otherwise
                    # swallow it into `failed_count`, returning an empty
                    # results list with NO exception — silently bypassing
                    # write-protection at the bulk_update Express surface
                    # (specs/dataflow-protection.md §2 path 1 + I5: "Express
                    # MUST surface it as an exception, not fold it into a
                    # result dict"). Re-raise so the violation propagates to
                    # the caller exactly as the sibling bulk_* surfaces
                    # (bulk_create/bulk_delete/bulk_upsert) already do (they
                    # call node.async_run once, so the protection raise
                    # propagates directly). Same hard-stop class as the
                    # _check_append_only / AppendOnlyViolationError guard
                    # that fires before this loop.
                    raise
                except Exception:
                    failed_count += 1

            # Issue #373: WARN on partial failure (observability.md Rule 6)
            if failed_count > 0:
                logger.warning(
                    "bulk_update.partial_failure",
                    extra={
                        "model": model,
                        "total": len(records),
                        "failed": failed_count,
                        "succeeded": len(results),
                    },
                )

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
            self._check_append_only(model, "bulk_delete")
            # Issue #1058 Shard 2: protection precheck (see create()).
            await self._check_protection_if_enabled(model, "bulk_delete", {"ids": ids})
            node = self._create_node(model, "BulkDelete")
            node._express_protection_precheck_done = True
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
        # Issue #839: append-only guard fires BEFORE conflict_on
        # validation so callers see the typed AppendOnlyViolationError
        # before any other work.
        self._check_append_only(model, "bulk_upsert")

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
            # Issue #857: defense-in-depth — redundant with the outer-body
            # guard at L1557. Kept so direct invocations of the inner
            # coroutine (callers that bypass the public `bulk_upsert`
            # entry point) also fail closed with AppendOnlyViolationError.
            # Removing this line would silently re-open the bypass.
            self._check_append_only(model, "bulk_upsert")
            # Issue #1058 Shard 2: protection precheck (see create()).
            await self._check_protection_if_enabled(
                model, "bulk_upsert", {"data": records}
            )
            node = self._create_node(model, "BulkUpsert")
            node._express_protection_precheck_done = True
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
            # Issue #490: mutation return MUST apply read-path redaction on
            # the records list. The scalar counts (created/updated/total)
            # are exempt per rules/dataflow-classification.md MUST Rule 4
            # (scalar aggregate carve-out).
            if isinstance(result, dict):
                raw_records = result.get("records", []) or []
                out: Dict[str, Any] = {
                    "records": self._apply_classification_mask_rows(model, raw_records),
                    "created": result.get("inserted", 0),
                    "updated": result.get("updated", 0),
                    "total": result.get("total", len(records)),
                }
                # Issue #1526: a whole-batch failure (e.g. a cross-tenant PK
                # collision) previously flattened into an empty-records dict
                # with NO error surfaced (silent-swallow — zero-tolerance Rule
                # 3). Preserve the failure signal and, when the failure is a
                # cross-tenant natural-key collision, enrich it with the SAME
                # actionable, tenant-scoped, no-cross-tenant-leak diagnostic the
                # single-record upsert path raises — WITHOUT converting the bulk
                # partial-failure-dict contract to raise-on-first-error.
                if result.get("success") is False:
                    raw_error = result.get("error")
                    out["success"] = False
                    # Cross-tenant WRITE breach fix: the tenant-scoped DO-UPDATE
                    # guard suppresses the offending row (no driver PK-unique
                    # message), so the collision helper is forced via the
                    # ``cross_tenant_conflict`` signal rather than a text match.
                    _forced = bool(result.get("cross_tenant_conflict"))
                    collision = await self._maybe_bulk_tenant_natural_key_collision(
                        model, records, str(raw_error or ""), force_collision=_forced
                    )
                    if collision is not None:
                        out["collision"] = collision
                        out["error"] = collision["message"]
                    elif raw_error is not None:
                        out["error"] = raw_error
                    # observability.md Rule 7: a bulk op with failed>0 MUST WARN.
                    processed = result.get("processed", 0) or 0
                    failed = max(out["total"] - processed, 1)
                    logger.warning(
                        "bulk_upsert.partial_failure",
                        extra={
                            "model": model,
                            "total": out["total"],
                            "failed": failed,
                            "succeeded": out["total"] - failed,
                            "first_error": (
                                str(out.get("error"))
                                if out.get("error") is not None
                                else None
                            ),
                        },
                    )
                return out
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
            # Version- AND db-instance-agnostic model-scoped clear. The
            # express keyspace bumped v2->v3 (#1606) and inserted a
            # db-instance segment directly after the version, so a
            # version-pinned prefix glob
            # (``{prefix}:{self._key_gen.version}:{model}:*``, pinned to the
            # generator's query-keyspace version "v2") no longer matches the
            # v3 express keys AND never matched tenant-scoped express keys
            # (``...:{tenant}:{model}:...``, model after tenant) — it would
            # silently clear 0 entries. Delegate to ``invalidate_model``,
            # whose ``:{model}:`` segment matcher is agnostic to the version
            # segment, the #1606 db-instance segment, AND the tenant segment
            # (``tenant-isolation.md`` §3a), mirroring ``_invalidate_model_cache``.
            return await self._cache_manager.invalidate_model(model)
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
                    except ProtectionViolation:
                        # Issue #1058 Shard 4 — same hard-stop class as the
                        # bulk_update propagation fix (Shard 1, ~line 1537).
                        # A write-protection block is NOT a per-row data
                        # failure to fold into the `errors` list; it MUST
                        # propagate so the caller learns the import is
                        # blocked (specs/dataflow-protection.md §2 path 1 +
                        # I5: "Express MUST surface it as an exception, not
                        # fold it into a result dict"). Re-raise BEFORE the
                        # generic `except Exception` swallow below.
                        raise
                    except Exception as exc:
                        # Issue #1552 (FIX 5, HIGH): import_file is a public API
                        # returning {"imported": int, "errors": [...]}; upsert()
                        # re-raises the RAW driver error (left raw for the caller
                        # per FIX 1), but rendering it into the RETURNED errors
                        # list is the #1552 returned-error leak surface on a live
                        # public path. Sanitize the VALUE-bearing driver error.
                        errors.append(
                            f"Upsert failed for record: {sanitize_db_error(str(exc))}"
                        )
            else:
                try:
                    await self.bulk_create(model_name, records)
                    imported = len(records)
                except ProtectionViolation:
                    # Issue #1058 Shard 4 — see commentary on the upsert
                    # branch above. Same I5 hard-stop discipline.
                    raise
                except Exception as exc:
                    # Issue #1552 (FIX 5, HIGH): same returned-`errors`-list leak
                    # surface as the upsert branch above — sanitize the driver error.
                    errors.append(f"Bulk create failed: {sanitize_db_error(str(exc))}")

        return {"imported": imported, "errors": errors}

    async def close_async(self) -> None:
        """Release Express-owned resources — the cache backend's executor.

        When the cache backend auto-detected to ``AsyncRedisCacheAdapter``
        (Redis reachable), it owns a ``ThreadPoolExecutor`` whose worker
        threads leak (``ResourceWarning`` at GC) unless explicitly closed.
        The in-memory fallback has no ``close_async``, so the getattr guard
        no-ops on that branch. Wired into :func:`DataFlow.close_async` so
        ``async with DataFlow(...)`` callers do not close it manually.
        Idempotent — ``AsyncRedisCacheAdapter.close_async`` guards double-close.
        """
        closer = getattr(self._cache_manager, "close_async", None)
        if callable(closer):
            await closer()

    def close(self) -> None:
        """Sync sibling of :func:`close_async` — release the cache backend's
        executor on a blocking teardown path (``DataFlow.close``). The
        in-memory fallback has no ``close``, so the getattr guard no-ops.
        Idempotent.
        """
        closer = getattr(self._cache_manager, "close", None)
        if callable(closer):
            closer()


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

        # Issue #1575 — explicit close path (mirrors SyncTransactionManager).
        # `_closed` lets `__del__` distinguish "user forgot to close"
        # (ResourceWarning) from "user closed correctly" (silent), and makes
        # `close()` idempotent.
        self._closed = False

        # Issue #1575 (Round-3) — track in-flight futures so a concurrent
        # `close()` can cancel them within bounded time instead of stranding the
        # caller on a no-timeout `future.result()` when the loop stops mid-call.
        self._pending: set = set()
        self._pending_lock = threading.Lock()

    def _discard_pending(self, future: Any) -> None:
        """Done-callback: drop a settled future from the in-flight set."""
        with self._pending_lock:
            self._pending.discard(future)

    def _run_sync(self, coro):
        """Run an async coroutine synchronously on the persistent event loop.

        Submits the coroutine to the background loop and blocks until it completes.
        This ensures all async operations share the same event loop, which is
        critical for database drivers like aiosqlite that bind connections to
        the loop they were created on.
        """
        # Issue #1575 (Round-3) — closed-guard BEFORE submit. If the owning loop
        # was torn down (or is being torn down) by close(), the coroutine can
        # never run. Close it (avoids the "coroutine was never awaited"
        # RuntimeWarning) and raise a TYPED error, not the opaque
        # `AttributeError: 'NoneType' object has no attribute
        # 'call_soon_threadsafe'` that `run_coroutine_threadsafe(coro, None)`
        # would raise (zero-tolerance.md Rule 3a). Mirrors SyncTransactionManager.
        #
        # Issue #1575 (Round-4) — serialize [closed-check + submit + track] under
        # _pending_lock so it strictly orders against close()'s [flip _closed +
        # snapshot _pending], which takes the SAME lock. Either this submits and
        # tracks the future BEFORE close flips _closed (→ close's snapshot sees it
        # and cancels it), or close flips _closed first (→ this raises). Neither
        # branch leaves an untracked future submitted onto a stopping loop — the
        # narrow submit-during-close hang window is closed.
        #
        # run_coroutine_threadsafe under the lock only SCHEDULES onto the loop; it
        # does not re-enter _pending_lock. The done-callback and future.result()
        # stay OUTSIDE the lock so a fast/cancelled future firing _discard_pending
        # (which takes _pending_lock) cannot deadlock against a held lock, and the
        # actual work is never serialized.
        with self._pending_lock:
            loop = self._loop
            if self._closed or loop is None:
                coro.close()
                raise RuntimeError(
                    "SyncExpress is closed — the DataFlow was closed via "
                    "db.close()/await db.close_async(); construct a fresh DataFlow "
                    "instance for further sync Express operations."
                )
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            self._pending.add(future)
        future.add_done_callback(self._discard_pending)
        return future.result()

    # --- Lifecycle (issue #1575) ---

    async def _drain_loop_resources(self) -> None:
        """Disconnect express-loop-bound resources — runs ON the BG loop.

        Submitted via ``run_coroutine_threadsafe`` by :meth:`close`, so every
        ``await`` here closes a resource bound to THIS persistent loop while it
        is still alive. The Express CRUD path caches ``AsyncSQLDatabaseNode``
        instances keyed by ``(node, loop_id)`` on the OWNING DataFlow; the node
        created for an Express call made through this sync surface is bound to
        this background loop. ``DataFlow.close()`` otherwise drains that cache
        via ``async_safe_run`` on a DIFFERENT (transient) loop, which cannot
        close a pool bound to this one — leaking the connection to GC
        (``RuntimeError: Event loop is closed`` / ``ResourceWarning: Unclosed
        connection``). Draining here, on the owning loop, is the fix.

        Best-effort by contract: guarded per resource, never raises, logs the
        exception TYPE only — never ``str(exc)`` / a DSN / a pool key
        (``rules/observability.md`` 6.3 + the loop_pool_registry discipline).
        """
        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:  # pragma: no cover — always running here
            return

        # (1) Disconnect cached AsyncSQLDatabaseNode adapters bound to THIS loop,
        #     then drop them from the owning cache so DataFlow.close() does not
        #     re-await them on a transient loop. Nodes bound to a DIFFERENT loop
        #     (or created loop-less, loop_id=None) that are NOT ours are left in
        #     place for the owner to drain.
        db = getattr(self._express, "_db", None)
        node_cache = getattr(db, "_async_sql_node_cache", None)
        if isinstance(node_cache, dict):
            for db_type, entry in list(node_cache.items()):
                try:
                    node, cached_loop_id = entry
                except (TypeError, ValueError):
                    continue
                if cached_loop_id is not None and cached_loop_id != loop_id:
                    continue  # bound to another loop; not this surface's to drain
                teardown = getattr(node, "cleanup", None) or getattr(
                    node, "close", None
                )
                if callable(teardown):
                    try:
                        await teardown()
                    except Exception as exc:  # noqa: BLE001 — teardown must not raise
                        logger.debug(
                            "express.sync.node_drain_failed",
                            extra={"error_type": type(exc).__name__},
                        )
                node_cache.pop(db_type, None)

        # (2) Close the Express cache backend if it holds loop-bound resources
        #     (AsyncRedisCacheAdapter.close_async); InMemoryCache holds none.
        cache = getattr(self._express, "_cache_manager", None)
        closer = getattr(cache, "close_async", None) or getattr(cache, "close", None)
        if callable(closer):
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.debug(
                    "express.sync.cache_close_failed",
                    extra={"error_type": type(exc).__name__},
                )

        # (3) Issue #1575 (Round-3): cancel every OTHER task still pending on
        #     this loop. An in-flight `_run_sync` coroutine submitted before
        #     `close()` runs as a task here; once the loop stops its
        #     ``run_coroutine_threadsafe`` future would never settle, hanging the
        #     caller's no-timeout ``future.result()`` FOREVER. Cancelling the
        #     task makes that future resolve with ``CancelledError`` (bounded)
        #     instead. Runs LAST, on the loop, so the drain above is unaffected.
        try:
            current = asyncio.current_task()
            for task in asyncio.all_tasks():
                if task is not current:
                    task.cancel()
        except RuntimeError:  # pragma: no cover — no running loop (unreachable here)
            pass

    def close(self) -> None:
        """Drain express-loop-bound pools, then stop the BG event-loop thread.

        Wired into :func:`DataFlow.close` / :func:`DataFlow.close_async` so
        ``with DataFlow(...)`` / ``async with`` callers do not need to invoke
        this manually. Idempotent — safe to call repeatedly.

        Order matters: DRAIN on the owning loop (while it is alive) BEFORE the
        loop stops, so aiosqlite/asyncpg connections created by Express through
        this sync surface close gracefully instead of stranding on a dead loop
        (issue #1575). Every step is guarded and logs the exception TYPE only.
        """
        if self._closed:
            return

        # Issue #1575 (Round-4) — flip _closed AND snapshot the in-flight futures
        # atomically under _pending_lock so this strictly orders against
        # _run_sync's guarded [check + submit + track] (same lock). A future
        # submitted+tracked before this flip IS in `pending` (→ cancelled below);
        # a submit racing in after this flip sees _closed and raises. Neither
        # leaves an untracked future stranded on a stopping loop — no hang window.
        with self._pending_lock:
            self._closed = True
            pending = list(self._pending)

        loop = self._loop
        thread = self._thread
        # Drop references so any after-close `_run_sync` observes the closed state
        # and raises the typed closed-error (never AttributeError via
        # run_coroutine_threadsafe(None), never a hang) — issue #1575 Round-3/4.
        self._loop = None
        self._thread = None

        # (a) Drain express-loop-bound resources ON the owning loop, bounded so
        #     a hung disconnect cannot block teardown forever. The drain's final
        #     step cancels every in-flight task on the loop so a slow call
        #     submitted before close() settles with CancelledError (bounded).
        if loop is not None and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._drain_loop_resources(), loop
                )
                future.result(timeout=5.0)
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.debug(
                    "express.sync.drain_failed",
                    extra={"error_type": type(exc).__name__},
                )

        # (a2) Cancel the in-flight futures snapshotted atomically above. On-loop
        #      task cancellation (drain step 3) covers coroutines already scheduled
        #      as tasks; this covers the narrow window where a future was submitted
        #      but its task had not yet been scheduled, so its caller's
        #      future.result() cannot hang past close.
        for pending_future in pending:
            pending_future.cancel()

        # (b) Stop the loop, (c) join the BG thread (bounded), (d) close the loop.
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                # Loop already stopped/destroyed — the closed flag prevents reuse.
                pass

        if thread is not None and thread.is_alive():
            # Bounded join — the loop stops near-instantly; a 5s ceiling
            # prevents a pathological hang from deadlocking teardown.
            thread.join(timeout=5.0)

        if loop is not None:
            try:
                loop.close()
            except RuntimeError:
                # Loop may already be closed by run_forever() shutdown —
                # the closed flag is the source of truth.
                pass

    def __del__(self, _warnings: Any = warnings) -> None:
        """Emit ``ResourceWarning`` if the BG thread was not stopped cleanly.

        Per ``rules/patterns.md`` § Async Resource Cleanup: emit warning, do
        nothing else. We do NOT call ``close`` here — touching the BG loop /
        thread (or any log-emitting path) from a finalizer is the deadlock
        pattern that rule documents. Real cleanup is the caller's via
        ``db.close()`` / ``await db.close_async()``.
        """
        if not getattr(self, "_closed", True):
            try:
                _warnings.warn(
                    f"{type(self).__name__} not closed; call "
                    f"db.close()/await db.close_async() to stop the BG "
                    f"event loop thread cleanly.",
                    ResourceWarning,
                    stacklevel=2,
                )
            except Exception:
                # Finalizer must not raise. Hooks/cleanup carve-out per
                # rules/zero-tolerance.md Rule 3.
                pass

    def _check_append_only(self, model: str, operation: str) -> None:
        """Sync delegate to :meth:`DataFlowExpress._check_append_only`.

        Issue #839: every sync mutation surface MUST raise
        ``AppendOnlyViolationError`` synchronously at the public-method
        boundary BEFORE submitting any coroutine to the background loop —
        otherwise the exception surfaces wrapped through
        ``asyncio.run_coroutine_threadsafe`` and obscures the documented
        contract. This delegate forwards to the async-class helper so both
        surfaces share a single enforcement point and a single grep target.
        """
        self._express._check_append_only(model, operation)

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
        id: Union[str, int],
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Read a single record by ID (sync).

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)
            include_deleted: For soft_delete models, return a tombstoned row
                instead of treating it as not-found (default: False).

        Returns:
            Record or None if not found
        """
        return self._run_sync(
            self._express.read(
                model,
                id,
                cache_ttl,
                use_primary=use_primary,
                include_deleted=include_deleted,
            )
        )

    def update(
        self, model: str, id: Union[str, int], fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a single record (sync).

        Args:
            model: Model name (e.g., "User")
            id: Record ID
            fields: Fields to update

        Returns:
            Updated record
        """
        # Issue #839: append-only guard fires synchronously at the public
        # surface so callers see the typed AppendOnlyViolationError before
        # any side effect (the inner async path checks it again as defense
        # in depth).
        self._check_append_only(model, "update")
        return self._run_sync(self._express.update(model, id, fields))

    def delete(self, model: str, id: Union[str, int]) -> bool:
        """Delete a single record (sync).

        Args:
            model: Model name (e.g., "User")
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        # Issue #839: append-only guard fires synchronously at the public
        # surface (defense in depth — async path also checks).
        self._check_append_only(model, "delete")
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
        include_deleted: bool = False,
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
            include_deleted: For soft_delete models, include tombstoned rows
                (bypass the deleted_at IS NULL auto-filter; default: False).

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
                include_deleted=include_deleted,
            )
        )

    def find_one(
        self,
        model: str,
        filter: Dict[str, Any],
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find a single record by filter criteria (sync).

        Args:
            model: Model name (e.g., "User")
            filter: MongoDB-style filter criteria (required, must not be empty)
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)
            include_deleted: For soft_delete models, when True return a
                tombstoned row matched by this (non-PK) filter instead of
                treating it as not-found (bypass the deleted_at IS NULL
                auto-filter; part of the cache key; default: False).

        Returns:
            Single record dict or None if not found
        """
        return self._run_sync(
            self._express.find_one(
                model,
                filter,
                cache_ttl,
                use_primary=use_primary,
                include_deleted=include_deleted,
            )
        )

    def count(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        cache_ttl: Optional[int] = None,
        use_primary: bool = False,  # TSG-105
        include_deleted: bool = False,
    ) -> int:
        """Count records with optional filtering (sync).

        Args:
            model: Model name (e.g., "User")
            filter: Optional MongoDB-style filter criteria
            cache_ttl: Optional cache TTL override
            use_primary: Force read from primary adapter (TSG-105)
            include_deleted: For soft_delete models, count tombstoned rows too
                (bypass the deleted_at IS NULL auto-filter; default: False).

        Returns:
            Number of matching records
        """
        return self._run_sync(
            self._express.count(
                model,
                filter,
                cache_ttl,
                use_primary=use_primary,
                include_deleted=include_deleted,
            )
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
        # Issue #839: append-only guard fires synchronously at the public
        # surface (defense in depth — async path also checks).
        self._check_append_only(model, "upsert")
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
        # Issue #839: upsert_advanced is treated as the upsert operation per
        # rules/zero-tolerance.md Rule 5 (consistent enforcement).
        self._check_append_only(model, "upsert")
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
        # Issue #839: append-only guard fires synchronously at the public
        # surface (defense in depth — async path also checks).
        self._check_append_only(model, "bulk_update")
        return self._run_sync(self._express.bulk_update(model, records, key_field))

    def bulk_delete(self, model: str, ids: List[str]) -> bool:
        """Delete multiple records by their IDs (sync).

        Args:
            model: Model name (e.g., "User")
            ids: List of record IDs to delete

        Returns:
            True if all deletions succeeded
        """
        # Issue #839: append-only guard fires synchronously at the public
        # surface (defense in depth — async path also checks).
        self._check_append_only(model, "bulk_delete")
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
        # Issue #839: append-only guard fires synchronously at the public
        # surface (defense in depth — async path also checks).
        self._check_append_only(model, "bulk_upsert")
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
