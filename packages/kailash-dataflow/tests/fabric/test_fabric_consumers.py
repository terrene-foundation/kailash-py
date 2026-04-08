# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the Consumer Adapter Registry (PR 4C / #244).

Covers:
- ConsumerRegistry: register, list, transform, error handling
- ProductRegistration.consumers field
- FabricServingLayer: ?consumer= param, header, error paths
- End-to-end: product + consumer + serving integration

NO unittest.mock, NO @patch, NO MagicMock.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.consumers import ConsumerFn, ConsumerRegistry
from dataflow.fabric.products import ProductRegistration
from dataflow.fabric.serving import FabricServingLayer

# ---------------------------------------------------------------------------
# Consumer transform functions — real, pure functions (not mocks)
# ---------------------------------------------------------------------------


def to_maturity_report(data: dict) -> dict:
    """Transform canonical portfolio data into a maturity report view."""
    return {
        "maturity_score": data.get("score", 0),
        "assessed_at": data.get("date", ""),
        "summary": f"Score: {data.get('score', 0)}",
    }


def to_chat_summary(data: dict) -> dict:
    """Transform canonical data into a chat-friendly summary."""
    return {
        "text": f"Portfolio has {data.get('count', 0)} items, score {data.get('score', 0)}",
    }


def to_csv_export(data: dict) -> dict:
    """Transform canonical data into a CSV-friendly shape."""
    return {
        "headers": list(data.keys()),
        "rows": [list(data.values())],
    }


# ---------------------------------------------------------------------------
# Minimal pipeline stub — real object with get_cached behaviour
# ---------------------------------------------------------------------------


class InMemoryPipeline:
    """Minimal pipeline executor that stores cached data in memory.

    Not a mock — it is a concrete implementation with deterministic
    behaviour for testing the serving layer. Mirrors the async cache
    contract the real PipelineExecutor exposes post-Phase-5 so the
    serving layer's ``await self._pipeline.get_cached(...)`` path
    exercises the same code paths the real implementation would.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, tuple] = {}

    def put_cached(self, name: str, data: dict) -> None:
        """Store serialized product data for serving layer consumption.

        Uses msgpack when available (matching the serving layer's deserialization
        preference), falling back to JSON.
        """
        try:
            import msgpack

            data_bytes = msgpack.packb(data, use_bin_type=True)
        except ImportError:
            data_bytes = json.dumps(data).encode("utf-8")
        metadata = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_ms": 42,
        }
        self._cache[name] = (data_bytes, metadata)

    async def get_cached(
        self,
        name: str,
        params: Dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> Any:
        key = name if tenant_id is None else f"{tenant_id}:{name}"
        return self._cache.get(key)

    async def get_metadata(
        self,
        name: str,
        params: Dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> Any:
        key = name if tenant_id is None else f"{tenant_id}:{name}"
        cached = self._cache.get(key)
        if cached is None:
            return None
        _data_bytes, metadata = cached
        return dict(metadata)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ConsumerRegistry:
    return ConsumerRegistry()


@pytest.fixture
def pipeline() -> InMemoryPipeline:
    return InMemoryPipeline()


def _make_product(
    name: str,
    consumers: list[str] | None = None,
    mode: str = "materialized",
) -> ProductRegistration:
    """Create a ProductRegistration with sensible defaults for testing."""

    async def product_fn(ctx: Any) -> dict:
        return {"score": 85, "count": 10, "date": "2026-04-04"}

    return ProductRegistration(
        name=name,
        fn=product_fn,
        mode=ProductMode(mode),
        depends_on=["User"],
        staleness=StalenessPolicy(),
        consumers=consumers or [],
    )


# ===========================================================================
# 1. ConsumerRegistry unit tests
# ===========================================================================


class TestConsumerRegistry:
    """Tests for ConsumerRegistry: register, list, get, transform."""

    def test_register_and_list(self, registry: ConsumerRegistry) -> None:
        registry.register("maturity_report", to_maturity_report)
        assert "maturity_report" in registry.list_consumers()

    def test_register_multiple(self, registry: ConsumerRegistry) -> None:
        registry.register("report", to_maturity_report)
        registry.register("chat", to_chat_summary)
        registry.register("csv", to_csv_export)
        consumers = registry.list_consumers()
        assert len(consumers) == 3
        assert set(consumers) == {"report", "chat", "csv"}

    def test_get_returns_function(self, registry: ConsumerRegistry) -> None:
        registry.register("report", to_maturity_report)
        fn = registry.get("report")
        assert fn is to_maturity_report

    def test_get_unknown_returns_none(self, registry: ConsumerRegistry) -> None:
        assert registry.get("nonexistent") is None

    def test_list_empty(self, registry: ConsumerRegistry) -> None:
        assert registry.list_consumers() == []

    def test_transform_returns_correct_data(self, registry: ConsumerRegistry) -> None:
        registry.register("maturity_report", to_maturity_report)
        canonical = {"score": 85, "date": "2026-04-04", "count": 10}
        result = registry.transform("maturity_report", canonical)
        assert result == {
            "maturity_score": 85,
            "assessed_at": "2026-04-04",
            "summary": "Score: 85",
        }

    def test_transform_unknown_consumer_raises(
        self, registry: ConsumerRegistry
    ) -> None:
        with pytest.raises(ValueError, match="Unknown consumer: 'nonexistent'"):
            registry.transform("nonexistent", {"data": 1})

    def test_register_empty_name_raises(self, registry: ConsumerRegistry) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            registry.register("", to_maturity_report)

    def test_register_whitespace_name_raises(self, registry: ConsumerRegistry) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            registry.register("   ", to_maturity_report)

    def test_register_non_callable_raises(self, registry: ConsumerRegistry) -> None:
        with pytest.raises(ValueError, match="must be callable"):
            registry.register("bad", "not_a_function")  # type: ignore[arg-type]

    def test_register_overwrites_existing(self, registry: ConsumerRegistry) -> None:
        """Re-registering a consumer name replaces the function."""
        registry.register("report", to_maturity_report)
        registry.register("report", to_chat_summary)
        fn = registry.get("report")
        assert fn is to_chat_summary

    def test_transform_multiple_consumers_different_shapes(
        self, registry: ConsumerRegistry
    ) -> None:
        """Same canonical data produces different shapes per consumer."""
        registry.register("report", to_maturity_report)
        registry.register("chat", to_chat_summary)

        canonical = {"score": 90, "count": 5, "date": "2026-04-04"}

        report_result = registry.transform("report", canonical)
        chat_result = registry.transform("chat", canonical)

        assert "maturity_score" in report_result
        assert "text" in chat_result
        assert report_result != chat_result


# ===========================================================================
# 2. ProductRegistration.consumers field tests
# ===========================================================================


class TestProductConsumersField:
    """Tests for the consumers field on ProductRegistration."""

    def test_default_empty_list(self) -> None:
        product = _make_product("test")
        assert product.consumers == []

    def test_explicit_consumers(self) -> None:
        product = _make_product("test", consumers=["report", "chat"])
        assert product.consumers == ["report", "chat"]

    def test_consumers_field_is_list(self) -> None:
        product = _make_product("test", consumers=["a", "b", "c"])
        assert isinstance(product.consumers, list)
        assert len(product.consumers) == 3


# ===========================================================================
# 3. FabricServingLayer with consumer param tests
# ===========================================================================


class TestServingLayerConsumers:
    """Tests for the ?consumer= query parameter in the serving layer."""

    def _build_serving(
        self,
        pipeline: InMemoryPipeline,
        products: Dict[str, ProductRegistration],
        consumer_registry: ConsumerRegistry | None = None,
    ) -> FabricServingLayer:
        return FabricServingLayer(
            products=products,
            pipeline_executor=pipeline,
            consumer_registry=consumer_registry,
        )

    @pytest.mark.asyncio
    async def test_no_consumer_returns_canonical_data(
        self, pipeline: InMemoryPipeline
    ) -> None:
        """GET /fabric/portfolio without ?consumer= returns canonical data."""
        product = _make_product("portfolio", consumers=["report"])
        products = {"portfolio": product}
        pipeline.put_cached("portfolio", {"score": 85, "count": 10})

        serving = self._build_serving(pipeline, products)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler()
        assert result["_status"] == 200
        assert result["data"]["score"] == 85
        assert "X-Fabric-Consumer" not in result["_headers"]

    @pytest.mark.asyncio
    async def test_consumer_returns_transformed_data(
        self, pipeline: InMemoryPipeline, registry: ConsumerRegistry
    ) -> None:
        """GET /fabric/portfolio?consumer=report returns transformed data."""
        registry.register("report", to_maturity_report)
        product = _make_product("portfolio", consumers=["report"])
        products = {"portfolio": product}
        pipeline.put_cached(
            "portfolio", {"score": 85, "count": 10, "date": "2026-04-04"}
        )

        serving = self._build_serving(pipeline, products, registry)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler(consumer="report")
        assert result["_status"] == 200
        assert result["data"]["maturity_score"] == 85
        assert result["data"]["assessed_at"] == "2026-04-04"
        assert "score" not in result["data"]  # canonical key absent in view

    @pytest.mark.asyncio
    async def test_consumer_header_present(
        self, pipeline: InMemoryPipeline, registry: ConsumerRegistry
    ) -> None:
        """X-Fabric-Consumer header is set when a consumer is used."""
        registry.register("report", to_maturity_report)
        product = _make_product("portfolio", consumers=["report"])
        products = {"portfolio": product}
        pipeline.put_cached("portfolio", {"score": 85, "date": "2026-04-04"})

        serving = self._build_serving(pipeline, products, registry)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler(consumer="report")
        assert result["_headers"]["X-Fabric-Consumer"] == "report"

    @pytest.mark.asyncio
    async def test_unknown_consumer_returns_400(
        self, pipeline: InMemoryPipeline
    ) -> None:
        """Consumer not in product's consumers list returns 400.

        Security: error MUST NOT leak the registry list (see serving.py:194
        comment "don't leak registry list"). Just name the rejected consumer
        and the product, no enumeration of available options.
        """
        product = _make_product("portfolio", consumers=["report"])
        products = {"portfolio": product}
        pipeline.put_cached("portfolio", {"score": 85})

        serving = self._build_serving(pipeline, products)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler(consumer="nonexistent")
        assert result["_status"] == 400
        assert "nonexistent" in result["error"]
        assert "portfolio" in result["error"]
        # Security: must NOT enumerate available consumers
        assert "report" not in result["error"]

    @pytest.mark.asyncio
    async def test_consumer_not_in_product_list_returns_400(
        self, pipeline: InMemoryPipeline, registry: ConsumerRegistry
    ) -> None:
        """Consumer registered globally but not on this product returns 400."""
        registry.register("report", to_maturity_report)
        registry.register("chat", to_chat_summary)
        # Product only supports "report", not "chat"
        product = _make_product("portfolio", consumers=["report"])
        products = {"portfolio": product}
        pipeline.put_cached("portfolio", {"score": 85})

        serving = self._build_serving(pipeline, products, registry)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler(consumer="chat")
        assert result["_status"] == 400
        assert "chat" in result["error"]

    @pytest.mark.asyncio
    async def test_consumer_declared_but_not_registered_returns_400(
        self, pipeline: InMemoryPipeline
    ) -> None:
        """Product declares a consumer but no adapter function is registered."""
        product = _make_product("portfolio", consumers=["missing_adapter"])
        products = {"portfolio": product}
        pipeline.put_cached("portfolio", {"score": 85})

        serving = self._build_serving(pipeline, products)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler(consumer="missing_adapter")
        assert result["_status"] == 400
        assert "no adapter is registered" in result["error"]
        assert "missing_adapter" in result["error"]

    @pytest.mark.asyncio
    async def test_product_with_no_consumers_rejects_consumer_param(
        self, pipeline: InMemoryPipeline, registry: ConsumerRegistry
    ) -> None:
        """Product with empty consumers list rejects any ?consumer= param."""
        registry.register("report", to_maturity_report)
        product = _make_product("portfolio", consumers=[])
        products = {"portfolio": product}
        pipeline.put_cached("portfolio", {"score": 85})

        serving = self._build_serving(pipeline, products, registry)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        result = await handler(consumer="report")
        assert result["_status"] == 400

    @pytest.mark.asyncio
    async def test_multiple_consumers_same_product(
        self, pipeline: InMemoryPipeline, registry: ConsumerRegistry
    ) -> None:
        """Multiple consumers on the same product each return different shapes."""
        registry.register("report", to_maturity_report)
        registry.register("chat", to_chat_summary)
        product = _make_product("portfolio", consumers=["report", "chat"])
        products = {"portfolio": product}
        pipeline.put_cached(
            "portfolio", {"score": 85, "count": 10, "date": "2026-04-04"}
        )

        serving = self._build_serving(pipeline, products, registry)
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        report_result = await handler(consumer="report")
        assert report_result["_status"] == 200
        assert "maturity_score" in report_result["data"]

        chat_result = await handler(consumer="chat")
        assert chat_result["_status"] == 200
        assert "text" in chat_result["data"]

        # Different shapes
        assert report_result["data"] != chat_result["data"]


# ===========================================================================
# 4. End-to-end consumer flow tests
# ===========================================================================


class TestEndToEndConsumerFlow:
    """Full flow: register product with consumers, register functions, serve."""

    @pytest.mark.asyncio
    async def test_full_consumer_pipeline(self) -> None:
        """Register product, register consumers, cache data, serve with consumer."""
        # 1. Set up registry and register consumers
        consumer_registry = ConsumerRegistry()
        consumer_registry.register("report", to_maturity_report)
        consumer_registry.register("chat", to_chat_summary)

        # 2. Create product declaring both consumers
        product = _make_product("portfolio", consumers=["report", "chat"])
        products = {"portfolio": product}

        # 3. Set up pipeline with cached canonical data
        pipeline = InMemoryPipeline()
        pipeline.put_cached(
            "portfolio",
            {"score": 92, "count": 15, "date": "2026-04-04"},
        )

        # 4. Set up serving layer
        serving = FabricServingLayer(
            products=products,
            pipeline_executor=pipeline,
            consumer_registry=consumer_registry,
        )
        routes = serving.get_routes()
        handler = routes[0]["handler"]

        # 5. Canonical request (no consumer)
        canonical = await handler()
        assert canonical["_status"] == 200
        assert canonical["data"]["score"] == 92
        assert canonical["data"]["count"] == 15

        # 6. Report consumer
        report = await handler(consumer="report")
        assert report["_status"] == 200
        assert report["data"]["maturity_score"] == 92
        assert report["_headers"]["X-Fabric-Consumer"] == "report"

        # 7. Chat consumer
        chat = await handler(consumer="chat")
        assert chat["_status"] == 200
        assert "15 items" in chat["data"]["text"]
        assert chat["_headers"]["X-Fabric-Consumer"] == "chat"

        # 8. Unknown consumer on this product
        bad = await handler(consumer="csv")
        assert bad["_status"] == 400

    @pytest.mark.asyncio
    async def test_consumer_registry_shared_across_products(self) -> None:
        """Consumer registry is shared: one consumer can serve multiple products."""
        consumer_registry = ConsumerRegistry()
        consumer_registry.register("csv", to_csv_export)

        product_a = _make_product("alpha", consumers=["csv"])
        product_b = _make_product("beta", consumers=["csv"])
        products = {"alpha": product_a, "beta": product_b}

        pipeline = InMemoryPipeline()
        pipeline.put_cached("alpha", {"score": 10})
        pipeline.put_cached("beta", {"score": 20})

        serving = FabricServingLayer(
            products=products,
            pipeline_executor=pipeline,
            consumer_registry=consumer_registry,
        )
        routes = serving.get_routes()

        # Find handlers by path
        alpha_handler = None
        beta_handler = None
        for route in routes:
            if route["path"] == "/fabric/alpha":
                alpha_handler = route["handler"]
            elif route["path"] == "/fabric/beta":
                beta_handler = route["handler"]

        assert alpha_handler is not None
        assert beta_handler is not None

        alpha_result = await alpha_handler(consumer="csv")
        assert alpha_result["_status"] == 200
        assert alpha_result["data"]["rows"] == [[10]]

        beta_result = await beta_handler(consumer="csv")
        assert beta_result["_status"] == 200
        assert beta_result["data"]["rows"] == [[20]]
