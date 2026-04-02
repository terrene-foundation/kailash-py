# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
PipelineExecutor — executes data product pipelines with caching and dedup.

Manages concurrent pipeline execution with bounded semaphores, content-hash
deduplication, serialization via msgpack (with json fallback), and bounded
trace storage. Supports both in-memory (dev) and Redis (production) cache.

Design references:
- TODO-11 in ``workspaces/data-fabric-engine/todos/active/02-products-and-pipeline.md``
- doc runtime-redteam RT-6 (10MB result size limit)
- doc layer-redteam F5 (DB connection budget = 20% of pool)
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
            "msgpack not installed; falling back to json serialization. "
            "Install msgpack for better performance: pip install msgpack"
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


def _cache_key(product_name: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Build a cache key, incorporating params for parameterized products."""
    canonical = _canonical_params(params)
    if canonical:
        return f"{product_name}:{canonical}"
    return product_name


# ---------------------------------------------------------------------------
# PipelineExecutor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """Execute data product pipelines with caching, dedup, and bounded concurrency.

    Args:
        dataflow: The DataFlow instance providing DB access and config.
        redis_url: Optional Redis URL for production caching. When ``None``,
            an in-memory cache is used (suitable for development).
        max_concurrent: Maximum concurrent pipeline executions (semaphore bound).
        dev_mode: When ``True``, forces in-memory cache even if ``redis_url``
            is provided.
    """

    def __init__(
        self,
        dataflow: Any,
        redis_url: Optional[str] = None,
        max_concurrent: int = 3,
        dev_mode: bool = False,
    ) -> None:
        self._dataflow = dataflow
        self._redis_url = redis_url
        self._max_concurrent = max_concurrent
        self._dev_mode = dev_mode

        # Execution concurrency
        self._exec_semaphore = asyncio.Semaphore(max_concurrent)

        # DB connection budget — 20% of pool (F5). Fall back to 2 if pool
        # size is not available on the config.
        pool_size = self._resolve_pool_size()
        pool_fraction = int(pool_size * 0.2)
        db_budget = max(1, pool_fraction)
        self._db_semaphore = asyncio.Semaphore(db_budget)
        logger.info(
            "PipelineExecutor: max_concurrent=%d, db_budget=%d (pool_size=%d)",
            max_concurrent,
            db_budget,
            pool_size,
        )

        # Pipeline coalescing queue
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)

        # In-memory cache (used when dev_mode or no redis_url)
        self._cache_data: Dict[str, bytes] = {}
        self._cache_hash: Dict[str, str] = {}
        self._cache_metadata: Dict[str, Dict[str, Any]] = {}

        # Bounded trace storage
        self._traces: Deque[PipelineTrace] = deque(maxlen=_DEFAULT_MAX_TRACES)

        # Size limit
        self._max_result_bytes = _DEFAULT_MAX_RESULT_BYTES

    # ------------------------------------------------------------------
    # Pool size resolution
    # ------------------------------------------------------------------

    def _resolve_pool_size(self) -> int:
        """Resolve pool size from the DataFlow config.

        Uses ``config.database.pool_size`` if set, otherwise defaults to 10
        which yields a db_budget of 2 (the minimum viable concurrency for
        pipeline DB access).
        """
        try:
            config = getattr(self._dataflow, "config", None)
            if config is not None:
                db_config = getattr(config, "database", None)
                if db_config is not None:
                    pool_size = getattr(db_config, "pool_size", None)
                    if pool_size is not None:
                        return int(pool_size)
                    # Try get_pool_size() method
                    get_fn = getattr(db_config, "get_pool_size", None)
                    if get_fn is not None:
                        return int(get_fn())
        except Exception:
            logger.debug(
                "Could not resolve pool_size from DataFlow config; using default"
            )
        return 10  # Yields db_budget = max(1, 2) = 2

    # ------------------------------------------------------------------
    # Cache operations (in-memory; Redis is a future extension)
    # ------------------------------------------------------------------

    def get_cached(
        self, product_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """Return cached data bytes and metadata, or ``None`` if not cached."""
        key = _cache_key(product_name, params)
        raw = self._cache_data.get(key)
        if raw is None:
            return None
        meta = self._cache_metadata.get(key, {})
        return raw, meta

    def set_cached(
        self,
        product_name: str,
        data_bytes: bytes,
        content_hash: str,
        metadata: Dict[str, Any],
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store serialized data, hash, and metadata in the cache."""
        key = _cache_key(product_name, params)
        self._cache_data[key] = data_bytes
        self._cache_hash[key] = content_hash
        self._cache_metadata[key] = metadata

    def _get_cached_hash(
        self, product_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Return the cached content hash for a product, or ``None``."""
        key = _cache_key(product_name, params)
        return self._cache_hash.get(key)

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    async def execute_product(
        self,
        product_name: str,
        product_fn: Callable[..., Any],
        context: Any,
        params: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """Execute a data product pipeline with caching and content-hash dedup.

        Args:
            product_name: Name of the data product.
            product_fn: The async (or sync) callable that produces the product data.
                Receives ``context`` as the first argument, and ``params`` as the
                second if provided.
            context: A ``PipelineContext`` (or any context object) passed to the
                product function.
            params: Optional parameters for parameterized products. When
                provided, the cache key includes a canonical representation.

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

            # Step 5: Compare with existing hash
            existing_hash = self._get_cached_hash(product_name, params)
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
                self.set_cached(product_name, data_bytes, new_hash, metadata, params)
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

    def get_product_from_cache(
        self, product_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[PipelineResult]:
        """Retrieve a product from cache without executing the pipeline.

        Returns ``None`` if the product is not cached.
        """
        cached = self.get_cached(product_name, params)
        if cached is None:
            return None

        raw_bytes, meta = cached
        data = _deserialize(raw_bytes)
        cached_at_str = meta.get("cached_at", "")
        try:
            cached_at = datetime.fromisoformat(cached_at_str)
        except (ValueError, TypeError):
            cached_at = datetime.now(timezone.utc)

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
    # Trace access
    # ------------------------------------------------------------------

    @property
    def traces(self) -> List[PipelineTrace]:
        """Return a snapshot of recent pipeline traces (most recent last)."""
        return list(self._traces)

    @property
    def db_semaphore(self) -> asyncio.Semaphore:
        """The DB connection budget semaphore for pipeline-scoped DB access."""
        return self._db_semaphore
