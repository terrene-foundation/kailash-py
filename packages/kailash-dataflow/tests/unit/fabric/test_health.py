# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for FabricHealthManager (TODO-19, TODO-20)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.health import FabricHealthManager, _sanitize_error
from dataflow.fabric.products import ProductRegistration


def _make_product(name: str = "dashboard") -> ProductRegistration:
    async def _fn(ctx):
        return {}

    return ProductRegistration(
        name=name,
        fn=_fn,
        mode=ProductMode.MATERIALIZED,
        depends_on=["User"],
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
    )


class _MockPipeline:
    """Mock pipeline that mirrors the real ``PipelineExecutor`` async
    surface used by :class:`FabricHealthManager`. Both ``get_cached``
    and ``get_metadata`` are async; the metadata fast path is what the
    health endpoint actually invokes (TODO-5.5 Phase 5 wiring).
    """

    def __init__(self, cache=None, metadata=None):
        self._cache = cache or {}
        self._metadata = metadata or {}
        self._traces = {}

    async def get_cached(self, name, params=None, tenant_id=None):
        return self._cache.get(name)

    async def get_metadata(self, name, params=None, tenant_id=None):
        return self._metadata.get(name)

    async def scan_product_metadata(self, name):
        # Health manager only invokes this for parameterized products;
        # the unit tests cover materialized products only, so an empty
        # list is the correct response.
        return []


class _MockAdapter:
    class _state:
        value = "active"

    class circuit_breaker:
        state = type("S", (), {"value": "closed"})()
        failure_count = 0
        last_error = None

    state = _state()
    healthy = True
    last_change_detected = None


class TestHealthManager:
    @pytest.mark.asyncio
    async def test_healthy_status(self):
        sources = {"crm": {"adapter": _MockAdapter()}}
        products = {"dashboard": _make_product()}
        mgr = FabricHealthManager(sources, products, _MockPipeline())
        health = await mgr.get_health()
        assert health["status"] == "healthy"
        assert "uptime_seconds" in health
        assert "crm" in health["sources"]

    @pytest.mark.asyncio
    async def test_cold_product(self):
        products = {"dashboard": _make_product()}
        mgr = FabricHealthManager({}, products, _MockPipeline())
        health = await mgr.get_health()
        assert health["products"]["dashboard"]["freshness"] == "cold"

    @pytest.mark.asyncio
    async def test_cached_product(self):
        meta = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_ms": 50,
        }
        products = {"dashboard": _make_product()}
        mgr = FabricHealthManager(
            {}, products, _MockPipeline(metadata={"dashboard": meta})
        )
        health = await mgr.get_health()
        assert health["products"]["dashboard"]["freshness"] == "fresh"


class TestTraceEndpoint:
    def test_unknown_product(self):
        mgr = FabricHealthManager({}, {}, _MockPipeline())
        result = mgr.get_trace("nonexistent")
        assert "error" in result

    def test_empty_traces(self):
        products = {"dashboard": _make_product()}
        mgr = FabricHealthManager({}, products, _MockPipeline())
        result = mgr.get_trace("dashboard")
        assert result["trace_count"] == 0


class TestSanitizeError:
    def test_removes_pg_credentials(self):
        err = "Connection failed: postgresql://user:pass@host/db"
        sanitized = _sanitize_error(err)
        assert "pass" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_removes_redis_credentials(self):
        err = "redis://admin:secret123@cache.example.com"
        sanitized = _sanitize_error(err)
        assert "secret123" not in sanitized

    def test_truncates_stacktrace(self):
        err = "Error line\nTraceback line 1\nTraceback line 2"
        sanitized = _sanitize_error(err)
        assert "\n" not in sanitized
        assert "Error line" in sanitized

    def test_none_passes_through(self):
        assert _sanitize_error(None) is None

    def test_caps_length(self):
        err = "x" * 1000
        assert len(_sanitize_error(err)) <= 500
