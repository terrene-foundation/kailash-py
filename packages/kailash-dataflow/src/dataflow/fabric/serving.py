# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric Serving Layer — auto-generated REST endpoints for products.

For each registered product, generates:
- GET /fabric/{product_name} — serve cached data with fabric headers
- POST /fabric/{target}/write — write pass-through (when enable_writes=True)
- GET /fabric/_batch?products=a,b,c — batch product read

Response body is CLEAN JSON — exactly what the product function returned.
Fabric metadata is in response headers (doc 04, Resolution 1).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from dataflow.fabric.context import PipelineContext
from dataflow.fabric.consumers import ConsumerRegistry
from dataflow.fabric.products import ProductRegistration

logger = logging.getLogger(__name__)

__all__ = ["FabricServingLayer"]

# Fabric response headers (doc 04, lines 12-49)
_HEADER_FRESHNESS = "X-Fabric-Freshness"
_HEADER_AGE = "X-Fabric-Age"
_HEADER_CACHED_AT = "X-Fabric-Cached-At"
_HEADER_PIPELINE_MS = "X-Fabric-Pipeline-Ms"
_HEADER_MODE = "X-Fabric-Mode"
_HEADER_CONSISTENCY = "X-Fabric-Consistency"
_HEADER_WRITE_TARGET = "X-Fabric-Write-Target"
_HEADER_PRODUCTS_REFRESHING = "X-Fabric-Products-Refreshing"
_HEADER_CONSUMER = "X-Fabric-Consumer"

# Filter operator allowlist (TODO-35)
ALLOWED_OPERATORS = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}

# Parameter validation constraints (security: HIGH from red team)
_MAX_CONSUMER_LENGTH = 255
_CONSUMER_PATTERN = __import__("re").compile(r"^[a-zA-Z0-9_-]+$")
_VALID_REFRESH_VALUES = {"true", "false"}


def _validate_consumer_param(value: Any) -> str | None:
    """Validate the consumer query parameter. Returns error message or None."""
    if not isinstance(value, str):
        return "consumer must be a string"
    if len(value) > _MAX_CONSUMER_LENGTH:
        return f"consumer name exceeds maximum length of {_MAX_CONSUMER_LENGTH}"
    if not value:
        return "consumer name must not be empty"
    if not _CONSUMER_PATTERN.match(value):
        return "consumer name must contain only alphanumeric characters, hyphens, and underscores"
    return None


def _validate_refresh_param(value: Any) -> str | None:
    """Validate the refresh query parameter. Returns error message or None."""
    if not isinstance(value, str):
        return "refresh must be a string"
    if value.lower() not in _VALID_REFRESH_VALUES:
        return "refresh must be 'true' or 'false'"
    return None


def validate_filter(filter_dict: dict) -> dict:
    """Validate and sanitize filter operators. Raises ValueError on disallowed operators."""
    for key, value in filter_dict.items():
        if isinstance(value, dict):
            for op in value:
                if op.startswith("$") and op not in ALLOWED_OPERATORS:
                    raise ValueError(f"Disallowed filter operator: {op}")
    return filter_dict


class FabricServingLayer:
    """Auto-generates REST endpoint handlers from registered products.

    This class produces handler functions that can be registered with Nexus
    or any ASGI framework. It does NOT import Nexus directly — it produces
    framework-agnostic handler callables.
    """

    def __init__(
        self,
        products: Dict[str, ProductRegistration],
        pipeline_executor: Any,
        express: Any = None,
        sources: Dict[str, Any] = None,
        enable_writes: bool = False,
        on_product_refresh: Optional[Callable] = None,
        consumer_registry: Optional[ConsumerRegistry] = None,
    ) -> None:
        self._products = products
        self._pipeline = pipeline_executor
        self._express = express
        self._sources = sources or {}
        self._enable_writes = enable_writes
        self._on_product_refresh = on_product_refresh
        self._consumer_registry = consumer_registry or ConsumerRegistry()

    def get_routes(self) -> List[Dict[str, Any]]:
        """Generate route definitions for all products.

        Returns a list of dicts with: method, path, handler, metadata.
        These can be registered with Nexus or FastAPI.
        """
        routes: List[Dict[str, Any]] = []

        for name, product in self._products.items():
            # GET /fabric/{product_name}
            routes.append(
                {
                    "method": "GET",
                    "path": f"/fabric/{name}",
                    "handler": self._make_product_handler(name, product),
                    "metadata": {
                        "product": name,
                        "mode": product.mode.value,
                        "auth": product.auth,
                    },
                }
            )

        # Batch endpoint
        routes.append(
            {
                "method": "GET",
                "path": "/fabric/_batch",
                "handler": self._make_batch_handler(),
                "metadata": {"type": "batch"},
            }
        )

        # Write endpoints (if enabled)
        if self._enable_writes:
            # Collect writable targets (models and sources)
            writable_targets = set()
            if self._express is not None:
                writable_targets.update(self._products.keys())
            for src_name, src_info in self._sources.items():
                adapter = src_info.get("adapter")
                if adapter and adapter.supports_feature("write"):
                    writable_targets.add(src_name)

            for target in writable_targets:
                routes.append(
                    {
                        "method": "POST",
                        "path": f"/fabric/{target}/write",
                        "handler": self._make_write_handler(target),
                        "metadata": {"type": "write", "target": target},
                    }
                )

        return routes

    def _make_product_handler(
        self, name: str, product: ProductRegistration
    ) -> Callable:
        """Create a handler for GET /fabric/{name}."""

        async def handler(request: Any = None, **kwargs: Any) -> Dict[str, Any]:
            # Parse query params for parameterized products
            params = kwargs if kwargs else {}
            if request and hasattr(request, "query_params"):
                params = dict(request.query_params)

            # Validate and parse refresh flag — ?refresh=true bypasses cache
            raw_refresh = params.pop("refresh", "false")
            refresh_error = _validate_refresh_param(raw_refresh)
            if refresh_error:
                return {"_status": 400, "error": refresh_error}
            refresh = isinstance(raw_refresh, str) and raw_refresh.lower() == "true"

            # Validate and extract consumer param
            consumer_name = params.pop("consumer", None)
            if consumer_name is not None:
                consumer_error = _validate_consumer_param(consumer_name)
                if consumer_error:
                    return {"_status": 400, "error": consumer_error}
                # Check product supports this consumer (don't leak registry list)
                if consumer_name not in product.consumers:
                    return {
                        "_status": 400,
                        "error": (
                            f"Consumer '{consumer_name}' is not available "
                            f"for product '{name}'."
                        ),
                    }
                if self._consumer_registry.get(consumer_name) is None:
                    return {
                        "_status": 400,
                        "error": (
                            f"Consumer '{consumer_name}' is declared on product "
                            f"'{name}' but no adapter is registered."
                        ),
                    }

            # Build cache key
            if product.mode.value == "parameterized" and params:
                # Validate filter params
                if "filter" in params:
                    try:
                        filter_dict = (
                            json.loads(params["filter"])
                            if isinstance(params["filter"], str)
                            else params["filter"]
                        )
                        validate_filter(filter_dict)
                        params["filter"] = filter_dict
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.debug("Invalid filter parameter: %s", e)
                        return {
                            "_status": 400,
                            "error": "Invalid filter parameter",
                        }

                # Clamp limit
                if "limit" in params:
                    try:
                        limit = int(params["limit"])
                        max_limit = product.rate_limit.max_unique_params
                        params["limit"] = min(limit, max_limit)
                    except (ValueError, TypeError):
                        return {
                            "_status": 400,
                            "error": "limit must be a positive integer",
                        }

            # Refresh: bypass cache and execute fresh
            if refresh:
                try:
                    source_adapters = {
                        src_name: src_info["adapter"]
                        for src_name, src_info in self._sources.items()
                        if "adapter" in src_info
                    }
                    ctx = PipelineContext(
                        express=self._express,
                        sources=source_adapters,
                        products_cache={},
                    )
                    result = await self._pipeline.execute_product(
                        product_name=name,
                        product_fn=product.fn,
                        context=ctx,
                        params=params if params else None,
                    )
                    return {
                        "_status": 200,
                        "_headers": {
                            _HEADER_FRESHNESS: "fresh",
                            _HEADER_PIPELINE_MS: str(int(result.duration_ms)),
                            _HEADER_MODE: product.mode.value,
                        },
                        "data": result.data,
                    }
                except Exception as e:
                    logger.error(
                        "Refresh execution failed for product '%s': %s", name, e
                    )
                    return {
                        "_status": 500,
                        "error": "Product refresh failed",
                    }

            # Try to get cached data
            cached = self._pipeline.get_cached(name)

            if cached is not None:
                data_bytes, metadata = cached
                # Deserialize
                try:
                    import msgpack

                    data = msgpack.unpackb(data_bytes, raw=False)
                except ImportError:
                    data = json.loads(data_bytes.decode("utf-8"))

                # Apply consumer transform if requested
                if consumer_name is not None:
                    data = self._consumer_registry.transform(consumer_name, data)

                cached_at = metadata.get("cached_at", "")
                pipeline_ms = metadata.get("pipeline_ms", 0)
                age_seconds = 0
                if cached_at:
                    try:
                        cached_dt = datetime.fromisoformat(cached_at)
                        age_seconds = int(
                            (datetime.now(timezone.utc) - cached_dt).total_seconds()
                        )
                    except (ValueError, TypeError):
                        pass

                # Check staleness
                max_age = product.staleness.max_age.total_seconds()
                freshness = "fresh" if age_seconds <= max_age else "stale"

                headers = {
                    _HEADER_FRESHNESS: freshness,
                    _HEADER_AGE: str(age_seconds),
                    _HEADER_CACHED_AT: cached_at,
                    _HEADER_PIPELINE_MS: str(int(pipeline_ms)),
                    _HEADER_MODE: product.mode.value,
                }
                if consumer_name is not None:
                    headers[_HEADER_CONSUMER] = consumer_name

                return {
                    "_status": 200,
                    "_headers": headers,
                    "data": data,
                }

            # Cold product — no cache yet
            if product.mode.value == "materialized":
                return {
                    "_status": 202,
                    "_headers": {
                        _HEADER_FRESHNESS: "cold",
                        "Retry-After": "5",
                    },
                    "data": {"status": "warming", "product": name},
                }

            # Virtual products execute inline — they never cache (#245)
            if product.mode.value == "virtual":
                source_adapters = {
                    n: info["adapter"]
                    for n, info in self._sources.items()
                    if isinstance(info, dict) and "adapter" in info
                }
                ctx = PipelineContext(
                    express=self._express,
                    sources=source_adapters,
                    products_cache={},
                )
                result = await self._pipeline.execute_product(name, product.fn, ctx)
                return {
                    "_status": 200,
                    "_headers": {
                        _HEADER_FRESHNESS: "fresh",
                        _HEADER_MODE: "virtual",
                    },
                    "data": result.data,
                }

            # Parameterized with no cache — return empty
            return {
                "_status": 200,
                "_headers": {
                    _HEADER_FRESHNESS: "cold",
                    _HEADER_MODE: product.mode.value,
                },
                "data": None,
            }

        handler.__name__ = f"fabric_get_{name}"
        return handler

    def _make_batch_handler(self) -> Callable:
        """Create handler for GET /fabric/_batch?products=a,b,c."""

        async def handler(request: Any = None, **kwargs: Any) -> Dict[str, Any]:
            product_names_str = kwargs.get("products", "")
            if request and hasattr(request, "query_params"):
                product_names_str = request.query_params.get("products", "")

            if not product_names_str:
                return {"_status": 400, "error": "products parameter required"}

            product_names = [
                n.strip() for n in product_names_str.split(",") if n.strip()
            ]
            if len(product_names) > 50:
                return {
                    "_status": 400,
                    "error": "Maximum 50 products per batch request",
                }
            results: Dict[str, Any] = {}
            overall_freshness = "fresh"

            for name in product_names:
                if name not in self._products:
                    results[name] = {"error": f"Product '{name}' not found"}
                    continue

                product = self._products[name]
                cached = self._pipeline.get_cached(name)
                if cached is not None:
                    data_bytes, metadata = cached
                    try:
                        import msgpack

                        data = msgpack.unpackb(data_bytes, raw=False)
                    except ImportError:
                        data = json.loads(data_bytes.decode("utf-8"))
                    results[name] = {
                        "data": data,
                        "cached_at": metadata.get("cached_at", ""),
                    }
                elif product.mode.value == "virtual":
                    # Virtual products execute inline — never cached (#245)
                    source_adapters = {
                        n: info["adapter"]
                        for n, info in self._sources.items()
                        if isinstance(info, dict) and "adapter" in info
                    }
                    ctx = PipelineContext(
                        express=self._express,
                        sources=source_adapters,
                        products_cache={},
                    )
                    pipe_result = await self._pipeline.execute_product(
                        name, product.fn, ctx
                    )
                    results[name] = {
                        "data": pipe_result.data,
                        "status": "fresh",
                    }
                else:
                    results[name] = {"data": None, "status": "cold"}
                    overall_freshness = "stale"

            return {
                "_status": 200,
                "_headers": {_HEADER_FRESHNESS: overall_freshness},
                "data": results,
            }

        handler.__name__ = "fabric_batch"
        return handler

    def _make_write_handler(self, target: str) -> Callable:
        """Create handler for POST /fabric/{target}/write."""

        async def handler(request: Any = None, **kwargs: Any) -> Dict[str, Any]:
            body = kwargs
            if request and hasattr(request, "json"):
                body = await request.json()

            operation = body.get("operation", "create")
            data = body.get("data")

            if not data:
                return {"_status": 400, "error": "data field required"}

            try:
                # Route write to correct target
                if self._express is not None and target in self._products:
                    # Model write via Express
                    if operation == "create":
                        result = await self._express.create(target, data)
                    elif operation == "update":
                        record_id = body.get("id")
                        if not record_id:
                            return {"_status": 400, "error": "id required for update"}
                        result = await self._express.update(target, record_id, data)
                    elif operation == "delete":
                        record_id = body.get("id")
                        if not record_id:
                            return {"_status": 400, "error": "id required for delete"}
                        result = await self._express.delete(target, record_id)
                    else:
                        return {
                            "_status": 400,
                            "error": f"Unknown operation: {operation}",
                        }
                elif target in self._sources:
                    # Source write
                    adapter = self._sources[target].get("adapter")
                    if adapter:
                        path = body.get("path", "")
                        result = await adapter.write(path, data)
                    else:
                        return {
                            "_status": 404,
                            "error": f"Source '{target}' has no adapter",
                        }
                else:
                    return {
                        "_status": 404,
                        "error": f"Write target '{target}' not found",
                    }

                # Trigger product refresh for affected products
                refreshing = []
                for pname, product in self._products.items():
                    if target in product.depends_on:
                        refreshing.append(pname)
                        if self._on_product_refresh:
                            await self._on_product_refresh(pname)

                return {
                    "_status": 200,
                    "_headers": {
                        _HEADER_WRITE_TARGET: target,
                        _HEADER_PRODUCTS_REFRESHING: ",".join(refreshing),
                    },
                    "data": result,
                }

            except Exception as e:
                logger.error("Write to '%s' failed: %s", target, e)
                return {"_status": 500, "error": "Write operation failed"}

        handler.__name__ = f"fabric_write_{target}"
        return handler
