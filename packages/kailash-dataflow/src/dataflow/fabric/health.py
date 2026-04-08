# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric Health & Trace endpoints.

GET /fabric/_health — overall fabric health (sources, products, cache, pipelines).
GET /fabric/_trace/{product} — last 20 pipeline runs for a product.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dataflow.fabric.config import ProductMode

logger = logging.getLogger(__name__)

__all__ = ["FabricHealthManager"]

# Sanitize error messages — no connection strings, credentials, or full stacks
_CREDENTIAL_PATTERNS = [
    re.compile(r"postgresql://[^@]+@"),
    re.compile(r"redis://[^@]+@"),
    re.compile(r"password[=:]\S+", re.IGNORECASE),
    re.compile(r"token[=:]\S+", re.IGNORECASE),
    re.compile(r"secret[=:]\S+", re.IGNORECASE),
]


def _sanitize_error(error: Optional[str]) -> Optional[str]:
    """Remove credentials and connection strings from error messages."""
    if error is None:
        return None
    sanitized = error
    for pattern in _CREDENTIAL_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    # Truncate stack traces — keep only first line
    if "\n" in sanitized:
        sanitized = sanitized.split("\n")[0]
    return sanitized[:500]  # Hard cap


def _as_datetime(value: Any) -> Optional[datetime]:
    """Coerce a cache metadata ``cached_at`` value into a timezone-aware datetime.

    Accepts ``datetime`` (returned as-is, aware if already aware) or an
    ISO-8601 string. Returns ``None`` on unrecognised input.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


class FabricHealthManager:
    """Manages health checks and trace storage for the fabric runtime."""

    def __init__(
        self,
        sources: Dict[str, Dict[str, Any]],
        products: Dict[str, Any],
        pipeline: Any,
        started_at: Optional[datetime] = None,
    ) -> None:
        self._sources = sources
        self._products = products
        self._pipeline = pipeline
        self._started_at = started_at or datetime.now(timezone.utc)

    async def get_health(self) -> Dict[str, Any]:
        """Build the /fabric/_health response.

        Uses the cache backend's metadata fast path (HMGET on Redis,
        dict lookup on memory) so the health endpoint never transfers
        product payload bytes. Multi-tenant products are reported as
        ``cold`` because the system-level health probe has no tenant
        context to resolve them.

        BREAKING CHANGE in 2.0: this method is now async.
        """
        uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        # Source health
        source_health: Dict[str, Any] = {}
        for name, info in self._sources.items():
            adapter = info.get("adapter")
            if adapter:
                source_health[name] = {
                    "healthy": adapter.healthy,
                    "state": adapter.state.value,
                    "circuit_breaker": adapter.circuit_breaker.state.value,
                    "consecutive_failures": adapter.circuit_breaker.failure_count,
                    "last_change_detected": (
                        adapter.last_change_detected.isoformat()
                        if adapter.last_change_detected
                        else None
                    ),
                    "last_error": _sanitize_error(adapter.circuit_breaker.last_error),
                }

        # Product health — use the cache backend's metadata fast path.
        # Multi-tenant products are reported cold; per-tenant health
        # checks would need a separate /fabric/_health endpoint that
        # accepts a tenant filter.
        #
        # Parameterized products (gh#358) are reported by aggregating
        # metadata across every param combination via scan_prefix. The
        # bare-name metadata lookup would always miss because the keys
        # include the canonical params JSON, so parameterized products
        # previously all reported ``cold`` regardless of cache state.
        product_health: Dict[str, Any] = {}
        now_utc = datetime.now(timezone.utc)
        for name, product in self._products.items():
            if getattr(product, "multi_tenant", False) or self._pipeline is None:
                product_health[name] = {
                    "freshness": "cold",
                    "age_seconds": None,
                    "cached_at": None,
                }
                continue

            product_mode = getattr(product, "mode", None)
            is_parameterized = product_mode == ProductMode.PARAMETERIZED

            metadata: Optional[Dict[str, Any]] = None
            param_combinations_cached: Optional[int] = None

            if is_parameterized:
                # Scan every cached entry for this product and aggregate
                # the freshest one. Report the count of cached param
                # combinations so operators can see breadth, not just
                # freshness of the single newest entry.
                try:
                    metadata_entries = await self._pipeline.scan_product_metadata(name)
                except Exception:
                    logger.exception(
                        "fabric.health.scan_prefix_failed",
                        extra={"product": name},
                    )
                    metadata_entries = []

                param_combinations_cached = len(metadata_entries)
                if metadata_entries:
                    # Pick the entry with the newest cached_at.
                    metadata = max(
                        metadata_entries,
                        key=lambda entry: _as_datetime(entry.get("cached_at"))
                        or datetime.min.replace(tzinfo=timezone.utc),
                    )
            else:
                try:
                    metadata = await self._pipeline.get_metadata(name)
                except Exception:
                    logger.exception(
                        "fabric.health.metadata_lookup_failed",
                        extra={"product": name},
                    )
                    metadata = None

            if metadata is None:
                cold_entry: Dict[str, Any] = {
                    "freshness": "cold",
                    "age_seconds": None,
                    "cached_at": None,
                }
                if is_parameterized:
                    cold_entry["param_combinations_cached"] = (
                        param_combinations_cached or 0
                    )
                product_health[name] = cold_entry
                continue

            cached_at_value = metadata.get("cached_at")
            cached_at_iso = ""
            age = 0
            if isinstance(cached_at_value, datetime):
                cached_at_iso = cached_at_value.isoformat()
                age = int((now_utc - cached_at_value).total_seconds())
            elif isinstance(cached_at_value, str) and cached_at_value:
                try:
                    dt = datetime.fromisoformat(cached_at_value)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    cached_at_iso = dt.isoformat()
                    age = int((now_utc - dt).total_seconds())
                except (ValueError, TypeError):
                    cached_at_iso = cached_at_value

            entry: Dict[str, Any] = {
                "freshness": (
                    "fresh"
                    if age <= product.staleness.max_age.total_seconds()
                    else "stale"
                ),
                "age_seconds": age,
                "cached_at": cached_at_iso,
                "pipeline_ms": metadata.get("pipeline_ms", 0),
            }
            if is_parameterized:
                entry["param_combinations_cached"] = param_combinations_cached or 0
            product_health[name] = entry

        # Pipeline stats
        pipeline_stats = {}
        if self._pipeline and hasattr(self._pipeline, "_traces"):
            all_traces = []
            if isinstance(self._pipeline._traces, dict):
                for traces in self._pipeline._traces.values():
                    all_traces.extend(traces)
            total = len(all_traces)
            successful = sum(1 for t in all_traces if t.get("status") == "success")
            failed = total - successful
            durations = [
                t.get("duration_ms", 0) for t in all_traces if t.get("duration_ms")
            ]
            avg_duration = sum(durations) / len(durations) if durations else 0
            pipeline_stats = {
                "total_runs": total,
                "successful": successful,
                "failed": failed,
                "avg_duration_ms": round(avg_duration, 1),
            }

        # Overall status
        all_sources_healthy = all(
            info.get("adapter", None) is None or info["adapter"].healthy
            for info in self._sources.values()
        )
        any_products_stale = any(
            p.get("freshness") == "stale" for p in product_health.values()
        )

        if not all_sources_healthy:
            status = (
                "degraded"
                if any(
                    info.get("adapter") and info["adapter"].healthy
                    for info in self._sources.values()
                )
                else "unhealthy"
            )
        elif any_products_stale:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "uptime_seconds": round(uptime, 1),
            "sources": source_health,
            "products": product_health,
            "pipelines": pipeline_stats,
        }

    def get_trace(self, product_name: str) -> Dict[str, Any]:
        """Build the /fabric/_trace/{product} response.

        Returns the last 20 pipeline runs for a product. Error messages
        are sanitized to prevent credential leakage.
        """
        if product_name not in self._products:
            return {"error": f"Product '{product_name}' not found"}

        traces: List[Dict[str, Any]] = []
        if self._pipeline and hasattr(self._pipeline, "_traces"):
            raw_traces = self._pipeline._traces
            if isinstance(raw_traces, dict):
                product_traces = raw_traces.get(product_name, [])
            elif isinstance(raw_traces, deque):
                product_traces = [
                    t for t in raw_traces if t.get("product_name") == product_name
                ]
            else:
                product_traces = []

            for trace in product_traces:
                sanitized = dict(trace)
                if "error" in sanitized:
                    sanitized["error"] = _sanitize_error(sanitized["error"])
                # Sanitize step errors
                for step in sanitized.get("steps", []):
                    if "error" in step:
                        step["error"] = _sanitize_error(step["error"])
                traces.append(sanitized)

        return {
            "product": product_name,
            "trace_count": len(traces),
            "traces": traces[-20:],  # Last 20
        }

    def get_health_handler(self) -> Dict[str, Any]:
        """Route definition for GET /fabric/_health."""

        async def handler(**_kwargs: Any) -> Dict[str, Any]:
            return {
                "_status": 200,
                "data": await self.get_health(),
            }

        handler.__name__ = "fabric_health"
        return {
            "method": "GET",
            "path": "/fabric/_health",
            "handler": handler,
            "metadata": {"type": "health", "auth": {"roles": ["admin"]}},
        }

    def get_trace_handler(self) -> Dict[str, Any]:
        """Route definition for GET /fabric/_trace/{product}."""

        async def handler(product: str = "", **_kwargs: Any) -> Dict[str, Any]:
            if not product:
                return {"_status": 400, "error": "product parameter required"}
            return {
                "_status": 200,
                "data": self.get_trace(product),
            }

        handler.__name__ = "fabric_trace"
        return {
            "method": "GET",
            "path": "/fabric/_trace/{product}",
            "handler": handler,
            "metadata": {"type": "trace", "auth": {"roles": ["admin"]}},
        }
