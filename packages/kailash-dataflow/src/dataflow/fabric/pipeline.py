# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
PipelineExecutor — executes data product pipelines with caching and dedup.

Manages concurrent pipeline execution with bounded semaphores, content-hash
deduplication, serialization via msgpack (with json fallback), and bounded
trace storage.

Cache storage is delegated to a :class:`FabricCacheBackend` (in-memory or
Redis-backed). The executor itself holds no per-product cache state — the
backend is the single source of truth. This replaces the three parallel
dicts (data/hash/metadata) the executor used before, eliminating an
entire class of "dicts drift" bugs documented in the
``workspaces/issue-354/`` analysis.

Backend selection rules:

* If a ``cache_backend`` is provided, it is used directly.
* If ``dev_mode=True``, force :class:`InMemoryFabricCacheBackend`. Logs
  a WARN if a ``redis_url`` was also provided so operators see why their
  Redis URL is being ignored.
* If neither a backend nor a ``redis_url`` is provided, default to
  :class:`InMemoryFabricCacheBackend`.
* If ``redis_url`` is provided **without** a ``cache_backend``, raise
  :class:`ValueError`. The shared Redis client lives on
  :class:`FabricRuntime` (so the cache, leader elector, and webhook
  receiver share one connection per replica); the executor must NOT
  construct its own client.

Tenant isolation:

* The executor itself does not know which products are
  ``multi_tenant=True``. Callers (FabricRuntime, FabricServingLayer)
  enforce the invariant by passing ``tenant_id``. The cache key always
  includes the tenant prefix when ``tenant_id`` is non-None.

Design references:
- TODO-11 in ``workspaces/data-fabric-engine/todos/active/02-products-and-pipeline.md``
- doc runtime-redteam RT-6 (10MB result size limit)
- doc layer-redteam F5 (DB connection budget = 20% of pool)
- ``workspaces/issue-354/02-plans/01-fix-plan.md`` Phases 4, 4a, 4b
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from dataflow.fabric.cache import (
    FabricCacheBackend,
    InMemoryFabricCacheBackend,
    _FabricCacheEntry,
    _mask_url,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PipelineExecutor",
    "PipelineResult",
    "PipelineTrace",
]

# ---------------------------------------------------------------------------
# Result and trace dataclasses
# ---------------------------------------------------------------------------

_DEFAULT_MAX_RESULT_BYTES = 10 * 1024 * 1024  # 10 MB (RT-6)
_DEFAULT_MAX_TRACES = 20


@dataclass(frozen=True)
class PipelineResult:
    """Immutable result of a single pipeline execution."""

    product_name: str
    data: Any
    content_hash: str
    cached_at: datetime
    duration_ms: float
    content_changed: bool
    from_cache: bool


@dataclass
class PipelineTrace:
    """Trace record for a single pipeline run."""

    run_id: str
    product_name: str
    triggered_by: str
    started_at: datetime
    duration_ms: float
    status: str  # "success" | "error" | "skipped"
    steps: List[Dict[str, Any]]
    cache_action: str  # "write" | "skip_unchanged" | "none"
    content_changed: bool


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize(data: Any) -> bytes:
    """Serialize data with msgpack (lazy import), falling back to json.

    When falling back to json, a warning is logged and the returned bytes
    are prefixed so callers can detect degradation if needed.
    """
    try:
        import msgpack  # type: ignore[import-untyped]

        return msgpack.packb(data, use_bin_type=True)
    except ImportError:
        logger.warning(
            "fabric.pipeline.msgpack_missing",
            extra={"fallback": "json"},
        )
        return json.dumps(data, sort_keys=True, default=str).encode("utf-8")


def _deserialize(raw: bytes) -> Any:
    """Deserialize data — try msgpack first, fall back to json."""
    try:
        import msgpack  # type: ignore[import-untyped]

        return msgpack.unpackb(raw, raw=False)
    except ImportError:
        return json.loads(raw.decode("utf-8"))


def _content_hash(data_bytes: bytes) -> str:
    """SHA-256 hex digest of serialized bytes."""
    return hashlib.sha256(data_bytes).hexdigest()


def _canonical_params(params: Optional[Dict[str, Any]]) -> str:
    """Deterministic string representation of params for cache keying."""
    if not params:
        return ""
    return json.dumps(params, sort_keys=True, default=str)


def _cache_key(
    product_name: str,
    params: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """Build a cache key, incorporating tenant and params.

    Shape:
    * No tenant, no params: ``product_name``
    * No tenant, with params: ``product_name:<canonical-params>``
    * With tenant, no params: ``<tenant_id>:product_name``
    * With tenant + params: ``<tenant_id>:product_name:<canonical-params>``

    Tenant isolation lives in the key prefix; the backend is opaque to
    tenants. Callers MUST pass ``tenant_id`` for ``multi_tenant=True``
    products — the executor does not enforce this directly because it
    does not know the product registration.
    """
    canonical = _canonical_params(params)
    if tenant_id is not None:
        if canonical:
            return f"{tenant_id}:{product_name}:{canonical}"
        return f"{tenant_id}:{product_name}"
    if canonical:
        return f"{product_name}:{canonical}"
    return product_name


# ---------------------------------------------------------------------------
# PipelineExecutor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """Execute data product pipelines with bounded concurrency, content-hash
    dedup, and a delegated cache backend.

    Args:
        dataflow: The DataFlow instance providing DB access and config.
        redis_url: Reserved for backend selection diagnostics. The
            executor never instantiates a Redis client itself; pass a
            constructed ``cache_backend`` from FabricRuntime instead.
        max_concurrent: Maximum concurrent pipeline executions
            (semaphore bound).
        dev_mode: When ``True``, forces in-memory cache and logs a WARN
            if a ``redis_url`` was also provided.
        cache_backend: Optional pre-built cache backend. When provided,
            ``redis_url`` and ``dev_mode`` are ignored for backend
            selection (the caller has already chosen).
        instance_name: Logical instance identifier for metrics and logs.
    """

    def __init__(
        self,
        dataflow: Any,
        redis_url: Optional[str] = None,
        max_concurrent: int = 3,
        dev_mode: bool = False,
        cache_backend: Optional[FabricCacheBackend] = None,
        instance_name: str = "default",
    ) -> None:
        self._dataflow = dataflow
        self._max_concurrent = max_concurrent
        self._instance_name = instance_name

        # Backend selection — see module docstring.
        self._cache: FabricCacheBackend = self._select_backend(
            cache_backend=cache_backend,
            redis_url=redis_url,
            dev_mode=dev_mode,
        )

        # Execution concurrency
        self._exec_semaphore = asyncio.Semaphore(max_concurrent)

        # DB connection budget — 20% of pool (F5). Falls back to 1 if pool
        # size is not available on the config.
        pool_size = self._resolve_pool_size()
        pool_fraction = int(pool_size * 0.2)
        db_budget = max(1, pool_fraction)
        self._db_semaphore = asyncio.Semaphore(db_budget)
        logger.debug(
            "fabric.pipeline.constructed",
            extra={
                "max_concurrent": max_concurrent,
                "db_budget": db_budget,
                "pool_size": pool_size,
                "instance_name": instance_name,
            },
        )

        # Bounded trace storage
        self._traces: Deque[PipelineTrace] = deque(maxlen=_DEFAULT_MAX_TRACES)

        # Size limit
        self._max_result_bytes = _DEFAULT_MAX_RESULT_BYTES

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    def _select_backend(
        self,
        cache_backend: Optional[FabricCacheBackend],
        redis_url: Optional[str],
        dev_mode: bool,
    ) -> FabricCacheBackend:
        if cache_backend is not None:
            logger.info(
                "fabric.cache.backend_selected",
                extra={
                    "backend": "injected",
                    "backend_class": type(cache_backend).__name__,
                    "dev_mode": dev_mode,
                    "instance_name": self._instance_name,
                },
            )
            return cache_backend

        if dev_mode:
            if redis_url:
                logger.warning(
                    "fabric.cache.dev_mode_overrides_redis_url",
                    extra={
                        "backend": "memory",
                        "redis_url_masked": _mask_url(redis_url),
                        "instance_name": self._instance_name,
                    },
                )
            backend: FabricCacheBackend = InMemoryFabricCacheBackend()
            logger.info(
                "fabric.cache.backend_selected",
                extra={
                    "backend": "memory",
                    "dev_mode": True,
                    "instance_name": self._instance_name,
                },
            )
            return backend

        if redis_url is None:
            backend = InMemoryFabricCacheBackend()
            logger.info(
                "fabric.cache.backend_selected",
                extra={
                    "backend": "memory",
                    "dev_mode": False,
                    "instance_name": self._instance_name,
                },
            )
            return backend

        # Redis URL provided but no backend wired — programmer error.
        # The shared client lives on FabricRuntime so cache + leader +
        # webhook receiver use ONE connection per replica.
        raise ValueError(
            "PipelineExecutor refuses to construct its own Redis client. "
            "Pass `cache_backend=RedisFabricCacheBackend(redis_client=...)` "
            "from FabricRuntime, which owns the shared client. "
            f"redis_url provided: {_mask_url(redis_url)}"
        )

    # ------------------------------------------------------------------
    # Pool size resolution
    # ------------------------------------------------------------------

    def _resolve_pool_size(self) -> int:
        """Resolve pool size from the DataFlow config.

        Uses ``DatabaseConfig.get_pool_size()`` as the single source of truth
        (dataflow-pool.md Rule 1). Falls back to get_pool_size() with default
        environment detection if the config path is unavailable.
        """
        try:
            config = getattr(self._dataflow, "config", None)
            if config is not None:
                db_config = getattr(config, "database", None)
                if db_config is not None:
                    # Canonical path: DatabaseConfig.get_pool_size()
                    get_fn = getattr(db_config, "get_pool_size", None)
                    if get_fn is not None:
                        env = getattr(config, "environment", "development")
                        return int(get_fn(env))
                    pool_size = getattr(db_config, "pool_size", None)
                    if pool_size is not None:
                        return int(pool_size)
        except Exception:
            logger.debug(
                "fabric.pipeline.pool_size_fallback",
                extra={"reason": "config_resolution_failed"},
            )
        # Fall back to DatabaseConfig canonical default
        try:
            from dataflow.core.config import DatabaseConfig

            return DatabaseConfig().get_pool_size("development")
        except Exception:
            return 5  # Minimal safe fallback — yields db_budget = max(1, 1) = 1

    # ------------------------------------------------------------------
    # Cache operations — delegate to FabricCacheBackend
    # ------------------------------------------------------------------

    async def get_cached(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """Return cached data bytes and metadata, or ``None`` if not cached.

        Returns the same ``(bytes, metadata_dict)`` shape the executor
        returned before the backend rewrite, so existing callers do not
        need to change.
        """
        key = _cache_key(product_name, params, tenant_id)
        entry = await self._cache.get(key)
        if entry is None:
            logger.debug(
                "fabric.cache.miss",
                extra={
                    "product": product_name,
                    "tenant_id": tenant_id,
                    "mode": "real",
                },
            )
            return None

        logger.debug(
            "fabric.cache.hit",
            extra={
                "product": product_name,
                "tenant_id": tenant_id,
                "mode": "cached",
            },
        )

        # Reconstruct the legacy metadata dict the callers expect.
        meta: Dict[str, Any] = dict(entry.metadata)
        meta.setdefault("cached_at", entry.cached_at.isoformat())
        meta.setdefault("content_hash", entry.content_hash)
        meta.setdefault("size_bytes", entry.size_bytes)
        meta.setdefault("schema_version", entry.schema_version)
        return entry.data_bytes, meta

    async def set_cached(
        self,
        product_name: str,
        data_bytes: bytes,
        content_hash: str,
        metadata: Dict[str, Any],
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        run_started_at: Optional[datetime] = None,
    ) -> bool:
        """Store serialized data, hash, and metadata in the cache.

        Returns ``True`` if the entry was written, ``False`` if the
        backend's CAS check refused the write (existing entry has a
        newer ``run_started_at``).
        """
        key = _cache_key(product_name, params, tenant_id)
        now = datetime.now(timezone.utc)
        cached_at_value = metadata.get("cached_at")
        cached_at = self._parse_iso(cached_at_value) or now
        entry = _FabricCacheEntry(
            product_name=product_name,
            tenant_id=tenant_id,
            data_bytes=data_bytes,
            content_hash=content_hash,
            metadata=metadata,
            cached_at=cached_at,
            run_started_at=run_started_at or now,
            size_bytes=len(data_bytes),
        )
        return await self._cache.set(key, entry)

    async def _get_cached_hash(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[str]:
        """Return the cached content hash for a product, or ``None``."""
        key = _cache_key(product_name, params, tenant_id)
        return await self._cache.get_hash(key)

    async def get_metadata(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fast path: return only the metadata fields without payload bytes."""
        key = _cache_key(product_name, params, tenant_id)
        return await self._cache.get_metadata(key)

    @staticmethod
    def _parse_iso(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    async def execute_product(
        self,
        product_name: str,
        product_fn: Callable[..., Any],
        context: Any,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> PipelineResult:
        """Execute a data product pipeline with caching and content-hash dedup.

        Args:
            product_name: Name of the data product.
            product_fn: The async (or sync) callable that produces the
                product data.
            context: A ``PipelineContext`` (or any context object).
            params: Optional parameters for parameterized products.
            tenant_id: Optional tenant identifier — required for
                ``multi_tenant=True`` products. The caller (FabricRuntime
                or FabricServingLayer) is responsible for raising
                :class:`FabricTenantRequiredError` when a multi-tenant
                product receives no tenant_id.

        Returns:
            A :class:`PipelineResult` with execution outcome and cache status.

        Raises:
            ValueError: If the serialized result exceeds the 10 MB limit.
        """
        run_id = uuid.uuid4().hex[:12]
        steps: List[Dict[str, Any]] = []
        started_at = datetime.now(timezone.utc)
        t0 = time.monotonic()

        async with self._exec_semaphore:
            # Step 1: Execute the product function
            step_start = time.monotonic()
            try:
                if asyncio.iscoroutinefunction(product_fn):
                    if params is not None:
                        raw_data = await product_fn(context, params)
                    else:
                        raw_data = await product_fn(context)
                else:
                    if params is not None:
                        raw_data = product_fn(context, params)
                    else:
                        raw_data = product_fn(context)
            except Exception:
                duration_ms = (time.monotonic() - t0) * 1000
                steps.append(
                    {
                        "name": "execute",
                        "duration_ms": (time.monotonic() - step_start) * 1000,
                        "status": "error",
                    }
                )
                trace = PipelineTrace(
                    run_id=run_id,
                    product_name=product_name,
                    triggered_by="execute_product",
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status="error",
                    steps=steps,
                    cache_action="none",
                    content_changed=False,
                )
                self._traces.append(trace)
                raise

            steps.append(
                {
                    "name": "execute",
                    "duration_ms": (time.monotonic() - step_start) * 1000,
                    "status": "success",
                }
            )

            # Step 2: Serialize
            step_start = time.monotonic()
            data_bytes = _serialize(raw_data)
            steps.append(
                {
                    "name": "serialize",
                    "duration_ms": (time.monotonic() - step_start) * 1000,
                    "bytes": len(data_bytes),
                }
            )

            # Step 3: Size check (RT-6)
            if len(data_bytes) > self._max_result_bytes:
                duration_ms = (time.monotonic() - t0) * 1000
                trace = PipelineTrace(
                    run_id=run_id,
                    product_name=product_name,
                    triggered_by="execute_product",
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status="error",
                    steps=steps,
                    cache_action="none",
                    content_changed=False,
                )
                self._traces.append(trace)
                raise ValueError(
                    f"Pipeline result for '{product_name}' exceeds maximum size: "
                    f"{len(data_bytes)} bytes > {self._max_result_bytes} bytes "
                    f"({self._max_result_bytes / (1024 * 1024):.0f} MB limit)"
                )

            # Step 4: Content hash
            step_start = time.monotonic()
            new_hash = _content_hash(data_bytes)
            steps.append(
                {
                    "name": "hash",
                    "duration_ms": (time.monotonic() - step_start) * 1000,
                    "hash": new_hash[:16],
                }
            )

            # Step 5: Compare with existing hash (dedup fast path)
            existing_hash = await self._get_cached_hash(product_name, params, tenant_id)
            content_changed = existing_hash != new_hash
            now = datetime.now(timezone.utc)

            if content_changed:
                # Step 6: Store new data and hash
                step_start = time.monotonic()
                metadata = {
                    "cached_at": now.isoformat(),
                    "pipeline_ms": (time.monotonic() - t0) * 1000,
                    "content_hash": new_hash,
                    "size_bytes": len(data_bytes),
                    "run_id": run_id,
                }
                await self.set_cached(
                    product_name,
                    data_bytes,
                    new_hash,
                    metadata,
                    params=params,
                    tenant_id=tenant_id,
                    run_started_at=started_at,
                )
                cache_action = "write"
                steps.append(
                    {
                        "name": "cache_write",
                        "duration_ms": (time.monotonic() - step_start) * 1000,
                    }
                )
            else:
                cache_action = "skip_unchanged"

            duration_ms = (time.monotonic() - t0) * 1000

            # Record trace
            trace = PipelineTrace(
                run_id=run_id,
                product_name=product_name,
                triggered_by="execute_product",
                started_at=started_at,
                duration_ms=duration_ms,
                status="success",
                steps=steps,
                cache_action=cache_action,
                content_changed=content_changed,
            )
            self._traces.append(trace)

            return PipelineResult(
                product_name=product_name,
                data=raw_data,
                content_hash=new_hash,
                cached_at=now,
                duration_ms=duration_ms,
                content_changed=content_changed,
                from_cache=False,
            )

    # ------------------------------------------------------------------
    # Cache retrieval (serve from cache without re-executing)
    # ------------------------------------------------------------------

    async def get_product_from_cache(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[PipelineResult]:
        """Retrieve a product from cache without executing the pipeline.

        Returns ``None`` if the product is not cached.
        """
        cached = await self.get_cached(product_name, params, tenant_id)
        if cached is None:
            return None

        raw_bytes, meta = cached
        data = _deserialize(raw_bytes)
        cached_at_value = meta.get("cached_at", "")
        cached_at = self._parse_iso(cached_at_value) or datetime.now(timezone.utc)

        return PipelineResult(
            product_name=product_name,
            data=data,
            content_hash=meta.get("content_hash", ""),
            cached_at=cached_at,
            duration_ms=0.0,
            content_changed=False,
            from_cache=True,
        )

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    async def invalidate(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Remove cached data for a specific product.

        Args:
            product_name: Name of the product to invalidate.
            params: Optional parameters (for parameterized products).
            tenant_id: Optional tenant scope.

        Returns:
            ``True`` if the cache entry existed and was removed, ``False``
            otherwise.
        """
        key = _cache_key(product_name, params, tenant_id)
        existed = await self._cache.get_hash(key) is not None
        await self._cache.invalidate(key)
        if existed:
            logger.debug(
                "fabric.cache.invalidated",
                extra={
                    "product": product_name,
                    "tenant_id": tenant_id,
                },
            )
        return existed

    async def invalidate_all(self) -> int:
        """Clear all cached product data.

        Returns ``-1`` because the in-memory backend used to return a
        count, but the Redis backend cannot reliably count keys without
        an extra round-trip. Callers that need a count must iterate.
        """
        await self._cache.invalidate_all()
        logger.debug("fabric.cache.invalidated_all")
        return -1

    # ------------------------------------------------------------------
    # Graceful drain
    # ------------------------------------------------------------------

    async def drain(self, timeout: float = 30.0) -> None:
        """Wait for in-flight pipeline executions to complete.

        Acquires all semaphore slots to ensure no executions are running,
        then releases them. If the timeout expires before all slots can
        be acquired, a warning is logged and the method returns.

        Args:
            timeout: Maximum seconds to wait for in-flight work to finish.
        """
        acquired = 0
        try:
            deadline = asyncio.get_event_loop().time() + timeout
            for _ in range(self._max_concurrent):
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning(
                        "fabric.pipeline.drain_timeout",
                        extra={
                            "timeout_s": timeout,
                            "acquired": acquired,
                            "max_concurrent": self._max_concurrent,
                        },
                    )
                    return
                try:
                    await asyncio.wait_for(
                        self._exec_semaphore.acquire(), timeout=remaining
                    )
                    acquired += 1
                except asyncio.TimeoutError:
                    logger.warning(
                        "fabric.pipeline.drain_timeout",
                        extra={
                            "timeout_s": timeout,
                            "acquired": acquired,
                            "max_concurrent": self._max_concurrent,
                        },
                    )
                    return
            logger.debug(
                "fabric.pipeline.drained",
                extra={"max_concurrent": self._max_concurrent},
            )
        finally:
            # Release all acquired slots so the semaphore returns to its
            # original state.
            for _ in range(acquired):
                self._exec_semaphore.release()

    # ------------------------------------------------------------------
    # Trace + property accessors
    # ------------------------------------------------------------------

    @property
    def traces(self) -> List[PipelineTrace]:
        """Return a snapshot of recent pipeline traces (most recent last)."""
        return list(self._traces)

    @property
    def db_semaphore(self) -> asyncio.Semaphore:
        """The DB connection budget semaphore for pipeline-scoped DB access."""
        return self._db_semaphore

    @property
    def cache_backend(self) -> FabricCacheBackend:
        """The cache backend in use (in-memory or Redis)."""
        return self._cache
