# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric context objects passed to product functions.

``FabricContext`` is the primary interface that product functions receive.
It provides access to the Express API, registered sources (via
``SourceHandle``), and other products' cached results.

``PipelineContext`` extends ``FabricContext`` with a
``PipelineScopedExpress`` that deduplicates reads within a single
pipeline execution, guaranteeing snapshot consistency (layer-redteam F4).

``FabricContext.for_testing()`` creates a fully isolated context with
pre-loaded data for unit tests.

See TODO-10 in workspaces/data-fabric-engine/todos/active/02-products-and-pipeline.md.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "SourceHandle",
    "FabricContext",
    "PipelineScopedExpress",
    "PipelineContext",
]


# ---------------------------------------------------------------------------
# SourceHandle -- user-friendly wrapper around BaseSourceAdapter
# ---------------------------------------------------------------------------


class SourceHandle:
    """User-friendly wrapper around a ``BaseSourceAdapter``.

    Product functions access external sources via ``ctx.source("name")``,
    which returns a ``SourceHandle``. All data methods delegate to the
    adapter's circuit-breaker-protected ``safe_fetch`` /
    ``safe_detect_change`` methods, so product authors get transparent
    resilience without managing circuit breakers themselves.

    Attributes:
        name: Source name as registered with ``@db.source()``.
    """

    def __init__(self, adapter: BaseSourceAdapter) -> None:
        self._adapter = adapter

    # -- Data retrieval (circuit-breaker protected) -------------------------

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Fetch data from a single endpoint or path.

        Args:
            path: Resource path (e.g. ``"deals"`` for REST, table name
                for DB).
            params: Optional query parameters forwarded to the adapter.

        Returns:
            Parsed response data.
        """
        return await self._adapter.safe_fetch(path, params)

    async def fetch_all(
        self,
        path: str = "",
        page_size: int = 100,
        max_records: int = 100_000,
    ) -> List[Any]:
        """Auto-paginate and fetch all records with memory guard.

        Args:
            path: Resource path.
            page_size: Records per page.
            max_records: Maximum total records before raising.

        Returns:
            Flat list of all records across pages.
        """
        return await self._adapter.fetch_all(path, page_size, max_records)

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """Stream pages of data as an async iterator.

        Args:
            path: Resource path.
            page_size: Records per page.

        Yields:
            Lists of records, one per page.
        """
        async for page in self._adapter.fetch_pages(path, page_size):
            yield page

    async def read(self) -> Any:
        """Read the default resource (alias for ``fetch("")``)."""
        return await self._adapter.safe_fetch("")

    async def list(self, prefix: str = "", limit: int = 1000) -> List[Any]:
        """List available items/resources.

        Args:
            prefix: Filter prefix.
            limit: Maximum items to return.
        """
        return await self._adapter.list(prefix, limit)

    async def write(self, path: str, data: Any) -> Any:
        """Write data to the source.

        Args:
            path: Resource path.
            data: Data to write.

        Returns:
            Adapter-specific write result.

        Raises:
            NotImplementedError: If the source is read-only.
        """
        return await self._adapter.write(path, data)

    # -- Degradation helpers ------------------------------------------------

    def last_successful_data(self, path: str = "") -> Optional[Any]:
        """Return the last known good data for graceful degradation.

        When a source's circuit breaker is open, this returns the most
        recent successful fetch result (or ``None`` if there is none).
        """
        return self._adapter.last_successful_data(path)

    # -- Read-only properties -----------------------------------------------

    @property
    def name(self) -> str:
        """Source name as registered with ``@db.source()``."""
        return self._adapter.name

    @property
    def source_type(self) -> str:
        """Adapter database_type identifier (e.g. ``"rest"``, ``"file"``)."""
        return self._adapter.database_type

    @property
    def healthy(self) -> bool:
        """Whether the source is active and its circuit breaker is closed."""
        return self._adapter.healthy

    @property
    def last_change_detected(self) -> Optional[datetime]:
        """UTC timestamp of the last detected change, or ``None``."""
        return self._adapter.last_change_detected

    def __repr__(self) -> str:
        return (
            f"SourceHandle(name={self.name!r}, "
            f"type={self.source_type!r}, "
            f"healthy={self.healthy})"
        )


# ---------------------------------------------------------------------------
# FabricContext -- primary context passed to product functions
# ---------------------------------------------------------------------------


class FabricContext:
    """Context object passed to product functions.

    Provides access to:

    * **express** -- the ``DataFlowExpress`` instance for model CRUD.
    * **source(name)** -- a ``SourceHandle`` wrapping a registered source.
    * **product(name)** -- cached result of another product.
    * **tenant_id** -- the current tenant for multi-tenant products.

    Args:
        express: The ``DataFlowExpress`` instance (or compatible wrapper).
        sources: Mapping of source name to ``BaseSourceAdapter``.
        products_cache: Mapping of product name to its cached result.
        tenant_id: Optional tenant identifier for multi-tenant products.
    """

    def __init__(
        self,
        express: Any,
        sources: Dict[str, BaseSourceAdapter],
        products_cache: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ) -> None:
        self._express = express
        self._sources = sources
        self._products_cache = products_cache
        self._tenant_id = tenant_id

    @property
    def express(self) -> Any:
        """The ``DataFlowExpress`` instance for model CRUD operations."""
        return self._express

    @property
    def tenant_id(self) -> Optional[str]:
        """The current tenant identifier, or ``None``."""
        return self._tenant_id

    def source(self, name: str) -> SourceHandle:
        """Get a source handle by name.

        Args:
            name: Source name as registered with ``@db.source()``.

        Returns:
            A ``SourceHandle`` wrapping the adapter.

        Raises:
            KeyError: If no source with *name* is registered.
        """
        adapter = self._sources.get(name)
        if adapter is None:
            raise KeyError(
                f"Source '{name}' is not registered. "
                f"Available sources: {sorted(self._sources.keys())}"
            )
        return SourceHandle(adapter)

    def product(self, name: str) -> Any:
        """Read the cached result of another product.

        Args:
            name: Product name.

        Returns:
            The cached product data.

        Raises:
            KeyError: If the product has not been cached yet.
        """
        if name not in self._products_cache:
            raise KeyError(
                f"Product '{name}' has no cached result. "
                f"Ensure it is listed in depends_on and has been materialized. "
                f"Cached products: {sorted(self._products_cache.keys())}"
            )
        return self._products_cache[name]

    # -- Testing factory ----------------------------------------------------

    @classmethod
    def for_testing(
        cls,
        express_data: Optional[Dict[str, Any]] = None,
        source_data: Optional[Dict[str, Any]] = None,
        products_cache: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> FabricContext:
        """Create a test context with pre-loaded data and no real connections.

        This factory is designed for unit tests that validate product
        functions in isolation without requiring a running database or
        external services.

        Args:
            express_data: Mapping of ``"ModelName"`` to a list of row
                dicts that ``MockExpress`` should return.  Supports
                ``list``, ``read``, ``count`` operations.
            source_data: Mapping of source name to path-data pairs.
                Each value may be:

                * A dict mapping path strings to response data (for
                  sources with multiple endpoints).
                * Any other value, treated as the response for the
                  default path ``""``.

            products_cache: Pre-populated product cache.
            tenant_id: Optional tenant identifier.

        Returns:
            A ``FabricContext`` backed by mock implementations.
        """
        mock_express = _MockExpress(express_data or {})
        mock_sources: Dict[str, BaseSourceAdapter] = {}
        for src_name, paths_or_data in (source_data or {}).items():
            if isinstance(paths_or_data, dict):
                mock_sources[src_name] = _MockSourceAdapter(src_name, paths_or_data)
            else:
                mock_sources[src_name] = _MockSourceAdapter(
                    src_name, {"": paths_or_data}
                )

        return cls(
            express=mock_express,
            sources=mock_sources,
            products_cache=products_cache or {},
            tenant_id=tenant_id,
        )


# ---------------------------------------------------------------------------
# PipelineScopedExpress -- deduplicates reads within a pipeline run (F4)
# ---------------------------------------------------------------------------


class PipelineScopedExpress:
    """Wraps ``DataFlowExpress`` and deduplicates reads within a single
    pipeline execution.

    Read operations (``list``, ``read``, ``count``) are cached using a
    composite key ``"operation:model:filter_json"`` so that repeated
    queries within the same product function see a consistent snapshot.

    Write operations (``create``, ``update``, ``delete``, ``upsert``)
    are forwarded directly to the underlying express instance without
    caching.

    The read cache is scoped to a single pipeline run and must be
    discarded between runs.

    Design rationale: layer-redteam convergence F4.
    """

    def __init__(
        self,
        express: Any,
        read_cache: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialise the scoped wrapper.

        Args:
            express: The underlying ``DataFlowExpress`` instance.
            read_cache: Optional shared cache dict.  If ``None``, a
                fresh dict is created.  Passing an explicit dict allows
                the ``PipelineContext`` to inspect or clear the cache
                externally.
        """
        self._express = express
        self._read_cache: Dict[str, Any] = read_cache if read_cache is not None else {}

    # -- Read operations (cached) -------------------------------------------

    async def list(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """List records with pipeline-scoped caching.

        Args:
            model: Model name.
            filter: Optional filter dict.
            **kwargs: Additional kwargs forwarded to express.

        Returns:
            List of matching records.
        """
        key = _cache_key("list", model, filter)
        if key not in self._read_cache:
            self._read_cache[key] = await self._express.list(
                model, filter=filter, **kwargs
            )
        return self._read_cache[key]

    async def read(
        self,
        model: str,
        record_id: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Read a single record with pipeline-scoped caching.

        Args:
            model: Model name.
            record_id: Primary key value.
            **kwargs: Additional kwargs forwarded to express.

        Returns:
            The record dict.
        """
        key = _cache_key("read", model, {"id": record_id})
        if key not in self._read_cache:
            self._read_cache[key] = await self._express.read(model, record_id, **kwargs)
        return self._read_cache[key]

    async def count(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> int:
        """Count records with pipeline-scoped caching.

        Args:
            model: Model name.
            filter: Optional filter dict.
            **kwargs: Additional kwargs forwarded to express.

        Returns:
            Number of matching records.
        """
        key = _cache_key("count", model, filter)
        if key not in self._read_cache:
            self._read_cache[key] = await self._express.count(
                model, filter=filter, **kwargs
            )
        return self._read_cache[key]

    # -- Write operations (NOT cached, delegated directly) ------------------

    async def create(
        self, model: str, data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        """Create a record (not cached)."""
        return await self._express.create(model, data, **kwargs)

    async def update(
        self, model: str, record_id: str, data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        """Update a record (not cached)."""
        return await self._express.update(model, record_id, data, **kwargs)

    async def delete(self, model: str, record_id: str, **kwargs: Any) -> bool:
        """Delete a record (not cached)."""
        return await self._express.delete(model, record_id, **kwargs)

    async def upsert(
        self, model: str, data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        """Upsert a record (not cached)."""
        return await self._express.upsert(model, data, **kwargs)

    def clear_cache(self) -> None:
        """Discard all cached reads. Called between pipeline runs."""
        self._read_cache.clear()

    def __repr__(self) -> str:
        return f"PipelineScopedExpress(cached_keys={len(self._read_cache)})"


# ---------------------------------------------------------------------------
# PipelineContext -- FabricContext with pipeline-scoped read deduplication
# ---------------------------------------------------------------------------


class PipelineContext(FabricContext):
    """``FabricContext`` variant used during pipeline execution.

    Wraps the ``DataFlowExpress`` in a ``PipelineScopedExpress`` so that
    repeated reads within a single product function see the same data
    (snapshot consistency). The read cache is cleared between pipeline
    runs.

    Args:
        express: The underlying ``DataFlowExpress`` instance (unwrapped).
        sources: Mapping of source name to ``BaseSourceAdapter``.
        products_cache: Mapping of product name to its cached result.
        tenant_id: Optional tenant identifier.
    """

    def __init__(
        self,
        express: Any,
        sources: Dict[str, BaseSourceAdapter],
        products_cache: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ) -> None:
        self._pipeline_read_cache: Dict[str, Any] = {}
        self._scoped_express = PipelineScopedExpress(express, self._pipeline_read_cache)
        super().__init__(
            express=self._scoped_express,
            sources=sources,
            products_cache=products_cache,
            tenant_id=tenant_id,
        )

    @property
    def express(self) -> PipelineScopedExpress:
        """Pipeline-scoped express wrapper with read deduplication."""
        return self._scoped_express

    def clear_read_cache(self) -> None:
        """Discard all pipeline-scoped cached reads.

        Called by the ``PipelineExecutor`` between runs to ensure each
        pipeline execution starts with a clean snapshot.
        """
        self._pipeline_read_cache.clear()


# ---------------------------------------------------------------------------
# Cache key helper
# ---------------------------------------------------------------------------


def _cache_key(
    operation: str,
    model: str,
    filter_dict: Optional[Dict[str, Any]],
) -> str:
    """Build a deterministic cache key for a pipeline-scoped read.

    Format: ``"operation:model:json_of_filter"``
    """
    filter_json = json.dumps(filter_dict, sort_keys=True) if filter_dict else "{}"
    return f"{operation}:{model}:{filter_json}"


# ---------------------------------------------------------------------------
# Mock implementations for testing
# ---------------------------------------------------------------------------


class _MockExpress:
    """Minimal mock of ``DataFlowExpress`` for ``FabricContext.for_testing()``.

    Accepts a data dict keyed by model name, where each value is a list
    of row dicts.
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    async def list(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        rows = self._data.get(model, [])
        if filter:
            return [
                row for row in rows if all(row.get(k) == v for k, v in filter.items())
            ]
        return list(rows)

    async def read(
        self,
        model: str,
        record_id: str,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        for row in self._data.get(model, []):
            if isinstance(row, dict) and str(row.get("id")) == str(record_id):
                return row
        return None

    async def count(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> int:
        rows = await self.list(model, filter=filter)
        return len(rows)

    async def create(
        self, model: str, data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        self._data.setdefault(model, []).append(data)
        return data

    async def update(
        self, model: str, record_id: str, data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        return {"id": record_id, **data}

    async def delete(self, model: str, record_id: str, **kwargs: Any) -> bool:
        return True

    async def upsert(
        self, model: str, data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        return data


class _MockSourceAdapter(BaseSourceAdapter):
    """Minimal mock source adapter for ``FabricContext.for_testing()``.

    Stores path-to-data mappings and returns them on ``fetch``. The
    circuit breaker is always closed and no real connections are made.
    """

    def __init__(self, name: str, paths: Dict[str, Any]) -> None:
        super().__init__(name=name)
        self._paths = paths
        # Mark as active so SourceHandle.healthy returns True
        from dataflow.adapters.source_adapter import SourceState

        self._state = SourceState.ACTIVE
        self.is_connected = True

    @property
    def database_type(self) -> str:
        return "mock"

    async def _connect(self) -> None:
        pass  # No-op: mock adapter is always connected

    async def _disconnect(self) -> None:
        pass  # No-op: mock adapter has no resources to release

    async def detect_change(self) -> bool:
        return False

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        if path in self._paths:
            return self._paths[path]
        if "" in self._paths:
            return self._paths[""]
        raise KeyError(
            f"Mock source '{self.name}' has no data for path '{path}'. "
            f"Available paths: {sorted(self._paths.keys())}"
        )

    async def fetch_pages(  # type: ignore[override]
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        data = await self.fetch(path)
        if isinstance(data, list):
            for i in range(0, len(data), page_size):
                yield data[i : i + page_size]
        else:
            yield [data]
