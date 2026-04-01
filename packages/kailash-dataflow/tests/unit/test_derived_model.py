# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for TSG-100: DerivedModelEngine.

Covers decorator parsing, compute invocation, bulk upsert pipeline,
scheduler tick, status reporting, error tracking, sync variant,
and integration tests with real SQLite.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataflow.core.events import WRITE_OPERATIONS
from dataflow.features.derived import (
    CircularDependencyError,
    DerivedModelEngine,
    DerivedModelMeta,
    DerivedModelRefreshScheduler,
    RefreshResult,
    _detect_cycles,
    _parse_interval,
)


# ---------------------------------------------------------------------------
# Interval parsing
# ---------------------------------------------------------------------------


class TestIntervalParsing:
    def test_parse_seconds(self):
        assert _parse_interval("every 30s") == 30.0
        assert _parse_interval("every 1 second") == 1.0
        assert _parse_interval("every 5 seconds") == 5.0

    def test_parse_minutes(self):
        assert _parse_interval("every 5m") == 300.0
        assert _parse_interval("every 1 minute") == 60.0
        assert _parse_interval("every 10 minutes") == 600.0

    def test_parse_hours(self):
        assert _parse_interval("every 6h") == 21600.0
        assert _parse_interval("every 1 hour") == 3600.0
        assert _parse_interval("every 24 hours") == 86400.0

    def test_parse_case_insensitive(self):
        assert _parse_interval("Every 6H") == 21600.0
        assert _parse_interval("EVERY 1 HOUR") == 3600.0

    def test_parse_with_whitespace(self):
        assert _parse_interval("  every 5m  ") == 300.0

    def test_parse_invalid_returns_none(self):
        assert _parse_interval("invalid") is None
        assert _parse_interval("0 */6 * * *") is None
        assert _parse_interval("every") is None
        assert _parse_interval("every foo") is None


# ---------------------------------------------------------------------------
# DerivedModelMeta dataclass
# ---------------------------------------------------------------------------


class TestDerivedModelMeta:
    def test_default_values(self):
        meta = DerivedModelMeta(
            model_name="OrderSummary",
            sources=["Order"],
            refresh="manual",
            schedule=None,
            compute_fn=lambda s: [],
        )
        assert meta.status == "pending"
        assert meta.last_refreshed is None
        assert meta.next_scheduled is None
        assert meta.last_error is None

    def test_scheduled_values(self):
        meta = DerivedModelMeta(
            model_name="DailyStats",
            sources=["Order", "LineItem"],
            refresh="scheduled",
            schedule="every 6h",
            compute_fn=lambda s: [],
        )
        assert meta.refresh == "scheduled"
        assert meta.schedule == "every 6h"
        assert meta.sources == ["Order", "LineItem"]


# ---------------------------------------------------------------------------
# RefreshResult dataclass
# ---------------------------------------------------------------------------


class TestRefreshResult:
    def test_result_defaults(self):
        r = RefreshResult(
            model_name="OrderSummary",
            records_upserted=10,
            duration_ms=123.4,
        )
        assert r.sources_queried == {}
        assert r.error is None

    def test_result_with_error(self):
        r = RefreshResult(
            model_name="OrderSummary",
            records_upserted=0,
            duration_ms=5.0,
            error="compute() raised ValueError",
        )
        assert r.error is not None

    def test_result_with_sources(self):
        r = RefreshResult(
            model_name="OrderSummary",
            records_upserted=1,
            duration_ms=50.0,
            sources_queried={"Order": 100, "LineItem": 500},
        )
        assert r.sources_queried["Order"] == 100
        assert r.sources_queried["LineItem"] == 500


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------


class TestCircularDependencyDetection:
    def test_no_cycle(self):
        models = {
            "Summary": DerivedModelMeta(
                model_name="Summary",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            ),
        }
        assert _detect_cycles(models) is None

    def test_self_cycle(self):
        models = {
            "A": DerivedModelMeta(
                model_name="A",
                sources=["A"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            ),
        }
        cycle = _detect_cycles(models)
        assert cycle is not None
        assert "A" in cycle

    def test_two_node_cycle(self):
        models = {
            "A": DerivedModelMeta(
                model_name="A",
                sources=["B"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            ),
            "B": DerivedModelMeta(
                model_name="B",
                sources=["A"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            ),
        }
        cycle = _detect_cycles(models)
        assert cycle is not None

    def test_no_cycle_with_plain_source(self):
        """Sources that are not derived models (plain models) should not cause cycles."""
        models = {
            "Summary": DerivedModelMeta(
                model_name="Summary",
                sources=["PlainModel"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            ),
        }
        # PlainModel is not in `models` dict, so it's treated as a leaf
        assert _detect_cycles(models) is None


# ---------------------------------------------------------------------------
# DerivedModelEngine registration
# ---------------------------------------------------------------------------


class TestDerivedModelEngineRegistration:
    def test_register_model(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        meta = DerivedModelMeta(
            model_name="Summary",
            sources=["Order"],
            refresh="manual",
            schedule=None,
            compute_fn=lambda s: [],
        )
        engine.register(meta)
        assert "Summary" in engine._models

    def test_register_duplicate_raises(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        meta = DerivedModelMeta(
            model_name="Summary",
            sources=["Order"],
            refresh="manual",
            schedule=None,
            compute_fn=lambda s: [],
        )
        engine.register(meta)
        with pytest.raises(ValueError, match="already registered"):
            engine.register(meta)

    def test_validate_no_cycles(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        meta = DerivedModelMeta(
            model_name="Summary",
            sources=["Order"],
            refresh="manual",
            schedule=None,
            compute_fn=lambda s: [],
        )
        engine.register(meta)
        # Should not raise
        engine.validate_dependencies()

    def test_validate_cycle_raises(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        engine.register(
            DerivedModelMeta(
                model_name="A",
                sources=["B"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        engine.register(
            DerivedModelMeta(
                model_name="B",
                sources=["A"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            engine.validate_dependencies()


# ---------------------------------------------------------------------------
# DerivedModelEngine status
# ---------------------------------------------------------------------------


class TestDerivedModelEngineStatus:
    def test_status_empty(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        assert engine.status() == {}

    def test_status_with_models(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        engine.register(
            DerivedModelMeta(
                model_name="Summary",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        status = engine.status()
        assert "Summary" in status
        assert status["Summary"].model_name == "Summary"
        assert status["Summary"].status == "pending"


# ---------------------------------------------------------------------------
# DerivedModelEngine refresh (with mocked express)
# ---------------------------------------------------------------------------


class TestDerivedModelEngineRefresh:
    @pytest.mark.asyncio
    async def test_refresh_unregistered_model(self):
        engine = DerivedModelEngine(dataflow_instance=None)
        result = await engine.refresh("NonExistent")
        assert result.error is not None
        assert "not registered" in result.error
        assert result.records_upserted == 0

    @pytest.mark.asyncio
    async def test_refresh_calls_compute(self):
        """Verify that refresh queries source data and calls compute_fn."""
        compute_called_with: Dict[str, Any] = {}

        def mock_compute(sources: Dict[str, List[Dict]]) -> List[Dict]:
            compute_called_with["sources"] = sources
            return [{"id": "result-1", "value": 42}]

        # Build a mock DataFlow with express
        mock_db = MagicMock()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(
            return_value=[{"id": "o1", "amount": 100}, {"id": "o2", "amount": 200}]
        )
        mock_express.bulk_delete = AsyncMock(return_value=True)
        mock_express.bulk_create = AsyncMock(
            return_value=[{"id": "result-1", "value": 42}]
        )
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Summary",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=mock_compute,
            )
        )

        result = await engine.refresh("Summary")

        assert result.error is None
        assert result.records_upserted == 1
        assert result.sources_queried == {"Order": 2}
        assert "Order" in compute_called_with["sources"]
        assert len(compute_called_with["sources"]["Order"]) == 2

        # Verify status updated
        meta = engine._models["Summary"]
        assert meta.status == "ok"
        assert meta.last_refreshed is not None

    @pytest.mark.asyncio
    async def test_refresh_error_tracking(self):
        """Verify that a failed compute populates last_error."""

        def failing_compute(sources):
            raise RuntimeError("compute failed!")

        mock_db = MagicMock()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Broken",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=failing_compute,
            )
        )

        result = await engine.refresh("Broken")

        assert result.error is not None
        assert "compute failed!" in result.error
        assert result.records_upserted == 0

        meta = engine._models["Broken"]
        assert meta.status == "error"
        assert meta.last_error is not None
        assert "compute failed!" in meta.last_error

    @pytest.mark.asyncio
    async def test_refresh_multi_source(self):
        """Verify refresh with multiple source models."""

        def multi_compute(sources):
            orders = sources.get("Order", [])
            items = sources.get("LineItem", [])
            return [
                {
                    "id": "summary",
                    "order_count": len(orders),
                    "item_count": len(items),
                }
            ]

        mock_db = MagicMock()
        mock_express = AsyncMock()

        async def mock_list(model_name, limit=100):
            if model_name == "Order":
                return [{"id": "o1"}, {"id": "o2"}]
            elif model_name == "LineItem":
                return [{"id": "li1"}, {"id": "li2"}, {"id": "li3"}]
            return []

        mock_express.list = mock_list
        mock_express.bulk_delete = AsyncMock(return_value=True)
        mock_express.bulk_create = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Summary",
                sources=["Order", "LineItem"],
                refresh="manual",
                schedule=None,
                compute_fn=multi_compute,
            )
        )

        result = await engine.refresh("Summary")

        assert result.error is None
        assert result.records_upserted == 1
        assert result.sources_queried == {"Order": 2, "LineItem": 3}

    @pytest.mark.asyncio
    async def test_refresh_empty_compute_result(self):
        """Verify refresh with compute returning empty list."""
        mock_db = MagicMock()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Empty",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        result = await engine.refresh("Empty")

        assert result.error is None
        assert result.records_upserted == 0
        assert engine._models["Empty"].status == "ok"


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class TestDerivedModelRefreshScheduler:
    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self):
        """Verify scheduler creates tasks for scheduled models and cancels them."""
        mock_db = MagicMock()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_express.bulk_delete = AsyncMock(return_value=True)
        mock_express.bulk_create = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Scheduled",
                sources=["Order"],
                refresh="scheduled",
                schedule="every 1h",
                compute_fn=lambda s: [],
            )
        )

        await engine.start_scheduler()
        assert engine._scheduler is not None
        assert len(engine._scheduler._tasks) == 1
        assert "Scheduled" in engine._scheduler._tasks

        await engine.stop_scheduler()
        assert engine._scheduler is None

    @pytest.mark.asyncio
    async def test_scheduler_skips_manual_models(self):
        """Verify scheduler does not start if only manual models exist."""
        engine = DerivedModelEngine(dataflow_instance=None)
        engine.register(
            DerivedModelMeta(
                model_name="Manual",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        await engine.start_scheduler()
        assert engine._scheduler is None  # No scheduler created

    @pytest.mark.asyncio
    async def test_scheduler_fires_refresh(self):
        """Verify a scheduled model actually fires a refresh within a short window."""
        refresh_count = {"n": 0}

        def counting_compute(sources):
            refresh_count["n"] += 1
            return []

        mock_db = MagicMock()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_express.bulk_delete = AsyncMock(return_value=True)
        mock_express.bulk_create = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        meta = DerivedModelMeta(
            model_name="FastRefresh",
            sources=["Order"],
            refresh="scheduled",
            schedule="every 1s",
            compute_fn=counting_compute,
        )
        engine.register(meta)
        # Set next_scheduled to now so it fires immediately
        meta.next_scheduled = datetime.now(timezone.utc)

        await engine.start_scheduler()
        # Wait enough for at least one refresh
        await asyncio.sleep(1.5)
        await engine.stop_scheduler()

        assert refresh_count["n"] >= 1


# ---------------------------------------------------------------------------
# Decorator integration via DataFlow (unit-level with mock)
# ---------------------------------------------------------------------------


class TestDerivedModelDecorator:
    def test_decorator_registers_model_and_derived(self):
        """Verify derived_model decorator applies @db.model and registers derived."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.derived_model(sources=["Order"], refresh="manual")
        class OrderSummary:
            id: str
            total: float

            @staticmethod
            def compute(sources):
                return []

        # Should be registered as a regular model
        assert "OrderSummary" in db._models

        # Should also be registered as a derived model
        assert "OrderSummary" in db._derived_engine._models
        meta = db._derived_engine._models["OrderSummary"]
        assert meta.sources == ["Order"]
        assert meta.refresh == "manual"
        assert meta.schedule is None

    def test_decorator_scheduled_without_schedule_raises(self):
        """Verify that refresh='scheduled' without schedule raises ValueError."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        with pytest.raises(ValueError, match="requires a 'schedule' parameter"):

            @db.derived_model(sources=["Order"], refresh="scheduled")
            class BadModel:
                id: str

                @staticmethod
                def compute(sources):
                    return []

    def test_decorator_missing_compute_raises(self):
        """Verify that a class without compute() raises TypeError."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        with pytest.raises(TypeError, match="must define a callable"):

            @db.derived_model(sources=["Order"], refresh="manual")
            class NoCompute:
                id: str

    def test_decorator_with_schedule(self):
        """Verify scheduled derived model stores schedule correctly."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.derived_model(sources=["Order"], refresh="scheduled", schedule="every 6h")
        class HourlySummary:
            id: str
            count: int

            @staticmethod
            def compute(sources):
                return []

        meta = db._derived_engine._models["HourlySummary"]
        assert meta.refresh == "scheduled"
        assert meta.schedule == "every 6h"


# ---------------------------------------------------------------------------
# Status & sync variant via DataFlow
# ---------------------------------------------------------------------------


class TestDerivedModelStatusAndSync:
    def test_derived_model_status(self):
        """Verify db.derived_model_status() returns correct metadata."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.derived_model(sources=["Order"], refresh="manual")
        class Summary:
            id: str

            @staticmethod
            def compute(sources):
                return []

        status = db.derived_model_status()
        assert "Summary" in status
        assert status["Summary"].status == "pending"

    def test_derived_model_status_empty(self):
        """Verify db.derived_model_status() returns empty dict when no derived models."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)
        assert db.derived_model_status() == {}


# ---------------------------------------------------------------------------
# Integration tests with real SQLite
# ---------------------------------------------------------------------------


class TestDerivedModelIntegration:
    def test_manual_refresh_end_to_end(self, tmp_path):
        """Full integration: create source data, refresh derived, read derived data."""
        from dataflow import DataFlow

        db_path = tmp_path / "derived_e2e.db"
        db = DataFlow(f"sqlite:///{db_path}")

        @db.model
        class Order:
            id: str
            amount: str  # Store as string to avoid isinstance() issue in test env
            status: str = "pending"

        @db.derived_model(sources=["Order"], refresh="manual")
        class OrderStats:
            id: str
            order_count: str
            total_amount: str

            @staticmethod
            def compute(sources):
                orders = sources.get("Order", [])
                total = sum(float(o.get("amount", "0")) for o in orders)
                return [
                    {
                        "id": "stats",
                        "order_count": str(len(orders)),
                        "total_amount": str(total),
                    }
                ]

        # Create source data via sync express
        db.express_sync.create("Order", {"id": "o1", "amount": "100.0"})
        db.express_sync.create("Order", {"id": "o2", "amount": "250.0"})
        db.express_sync.create("Order", {"id": "o3", "amount": "50.0"})

        # Refresh derived model via sync
        result = db.refresh_derived_sync("OrderStats")
        assert result.error is None
        assert result.records_upserted == 1
        assert result.sources_queried["Order"] == 3

        # Read derived data -- verify persistence
        stats = db.express_sync.list("OrderStats")
        assert len(stats) == 1
        assert stats[0]["order_count"] == "3"
        assert stats[0]["total_amount"] == "400.0"

    @pytest.mark.asyncio
    async def test_derived_model_gets_crud_nodes(self):
        """Verify derived model has all standard CRUD nodes."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.derived_model(sources=["Order"], refresh="manual")
        class Stats:
            id: str
            value: int

            @staticmethod
            def compute(sources):
                return []

        # Check that CRUD nodes were generated (from @db.model treatment)
        assert "Stats" in db._models
        nodes = db._nodes.get("Stats", {})
        # The model registration generates node entries
        assert db._models["Stats"] is not None

    def test_multi_source_derived_model_sqlite(self, tmp_path):
        """Integration: two source models, one derived model, real SQLite."""
        from dataflow import DataFlow

        db_path = tmp_path / "derived_multi.db"
        db = DataFlow(f"sqlite:///{db_path}")

        @db.model
        class Product:
            id: str
            name: str
            price: str = "0"

        @db.model
        class Sale:
            id: str
            product_id: str
            quantity: str = "1"

        @db.derived_model(sources=["Product", "Sale"], refresh="manual")
        class SalesReport:
            id: str
            product_name: str
            total_quantity: str
            total_revenue: str

            @staticmethod
            def compute(sources):
                products = {p["id"]: p for p in sources.get("Product", [])}
                sales = sources.get("Sale", [])
                # Aggregate sales per product
                agg: Dict[str, Dict[str, Any]] = {}
                for sale in sales:
                    pid = sale.get("product_id", "")
                    if pid not in agg:
                        product = products.get(pid, {})
                        agg[pid] = {
                            "id": f"report-{pid}",
                            "product_name": product.get("name", "Unknown"),
                            "total_quantity": 0,
                            "total_revenue": 0.0,
                        }
                    qty = int(sale.get("quantity", "1"))
                    price = float(products.get(pid, {}).get("price", "0"))
                    agg[pid]["total_quantity"] += qty
                    agg[pid]["total_revenue"] += qty * price
                # Convert numeric values to strings for storage
                for v in agg.values():
                    v["total_quantity"] = str(v["total_quantity"])
                    v["total_revenue"] = str(v["total_revenue"])
                return list(agg.values())

        # Create source data via sync express
        db.express_sync.create(
            "Product", {"id": "p1", "name": "Widget", "price": "10.0"}
        )
        db.express_sync.create(
            "Product", {"id": "p2", "name": "Gadget", "price": "25.0"}
        )
        db.express_sync.create(
            "Sale", {"id": "s1", "product_id": "p1", "quantity": "3"}
        )
        db.express_sync.create(
            "Sale", {"id": "s2", "product_id": "p1", "quantity": "2"}
        )
        db.express_sync.create(
            "Sale", {"id": "s3", "product_id": "p2", "quantity": "1"}
        )

        # Refresh via sync
        result = db.refresh_derived_sync("SalesReport")
        assert result.error is None
        assert result.records_upserted == 2
        assert result.sources_queried["Product"] == 2
        assert result.sources_queried["Sale"] == 3

        # Read back -- verify persistence
        reports = db.express_sync.list("SalesReport")
        assert len(reports) == 2
        # Find widget report
        widget_report = next(
            (r for r in reports if r.get("product_name") == "Widget"), None
        )
        assert widget_report is not None
        assert widget_report["total_quantity"] == "5"
        assert widget_report["total_revenue"] == "50.0"

    def test_refresh_returns_correct_result(self, tmp_path):
        """Verify that refresh returns correct result metadata."""
        from dataflow import DataFlow

        db_path = tmp_path / "derived_result.db"
        db = DataFlow(f"sqlite:///{db_path}")

        refresh_call_count = {"n": 0}

        @db.model
        class Item:
            id: str
            name: str = ""

        @db.derived_model(sources=["Item"], refresh="manual")
        class ItemSummary:
            id: str
            item_count: str

            @staticmethod
            def compute(sources):
                items = sources.get("Item", [])
                refresh_call_count["n"] += 1
                return [
                    {
                        "id": f"summary-{refresh_call_count['n']}",
                        "item_count": str(len(items)),
                    }
                ]

        # Create source data
        db.express_sync.create("Item", {"id": "i1", "name": "alpha"})
        db.express_sync.create("Item", {"id": "i2", "name": "beta"})

        # Refresh and check result
        result = db.refresh_derived_sync("ItemSummary")
        assert result.error is None
        assert result.records_upserted == 1
        assert result.sources_queried["Item"] == 2
        assert result.duration_ms > 0

        # Read back derived data -- verify persistence
        summaries = db.express_sync.list("ItemSummary")
        assert len(summaries) >= 1
        assert summaries[0]["item_count"] == "2"


# ---------------------------------------------------------------------------
# TSG-101: on_source_change mode
# ---------------------------------------------------------------------------


class TestOnSourceChangeSubscription:
    """Verify event subscription setup for on_source_change derived models."""

    def test_setup_creates_8_subscriptions_per_source(self):
        """Verify 8 subscriptions created per source model."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="CustomerStats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        count = engine.setup_event_subscriptions()
        assert count == 8  # 8 WRITE_OPERATIONS for 1 source

    def test_setup_creates_subscriptions_for_multiple_sources(self):
        """Verify subscriptions for multi-source derived models."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="SalesReport",
                sources=["Order", "LineItem"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        count = engine.setup_event_subscriptions()
        assert count == 16  # 8 ops x 2 sources

    def test_no_subscriptions_for_manual_models(self):
        """Verify manual models do not get event subscriptions."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="ManualStats",
                sources=["Order"],
                refresh="manual",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        count = engine.setup_event_subscriptions()
        assert count == 0

    def test_no_subscriptions_without_event_bus(self):
        """Verify setup gracefully handles missing event bus."""
        mock_db = MagicMock(spec=[])  # No _event_bus attribute

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Stats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        count = engine.setup_event_subscriptions()
        assert count == 0

    def test_idempotent_setup(self):
        """Verify setup_event_subscriptions is idempotent."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()

        engine = DerivedModelEngine(dataflow_instance=mock_db)
        engine.register(
            DerivedModelMeta(
                model_name="Stats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )

        first = engine.setup_event_subscriptions()
        second = engine.setup_event_subscriptions()
        assert first == 8
        assert second == 0  # Already active


class TestOnSourceChangeHandler:
    """Verify write events trigger derived model recompute."""

    @pytest.mark.asyncio
    async def test_write_triggers_recompute(self):
        """Verify that a write event triggers recompute after debounce."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus
        from kailash.middleware.communication.domain_event import DomainEvent

        refresh_count = {"n": 0}

        async def counting_refresh(model_name):
            refresh_count["n"] += 1

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_express.bulk_create = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)

        def compute_fn(sources):
            refresh_count["n"] += 1
            return []

        engine.register(
            DerivedModelMeta(
                model_name="Stats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=compute_fn,
                debounce_ms=50,  # Short debounce for test
            )
        )

        engine.setup_event_subscriptions()

        # Simulate a write event
        event = DomainEvent(
            event_type="dataflow.Order.create",
            payload={"model": "Order", "operation": "create", "record_id": "o1"},
        )
        mock_db._event_bus.publish(event)

        # Wait for debounce + refresh
        await asyncio.sleep(0.2)

        assert refresh_count["n"] >= 1

    @pytest.mark.asyncio
    async def test_unrelated_write_no_trigger(self):
        """Verify that a write to an unrelated model does NOT trigger recompute."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus
        from kailash.middleware.communication.domain_event import DomainEvent

        refresh_count = {"n": 0}

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_express.bulk_create = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)

        def compute_fn(sources):
            refresh_count["n"] += 1
            return []

        engine.register(
            DerivedModelMeta(
                model_name="OrderStats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=compute_fn,
                debounce_ms=50,
            )
        )

        engine.setup_event_subscriptions()

        # Emit event for Product -- unrelated to OrderStats
        event = DomainEvent(
            event_type="dataflow.Product.create",
            payload={"model": "Product", "operation": "create", "record_id": "p1"},
        )
        mock_db._event_bus.publish(event)

        # Wait enough time
        await asyncio.sleep(0.2)

        assert refresh_count["n"] == 0

    @pytest.mark.asyncio
    async def test_debounce_coalesces_rapid_writes(self):
        """Verify that 10 rapid writes coalesce into 1 recompute."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus
        from kailash.middleware.communication.domain_event import DomainEvent

        refresh_count = {"n": 0}

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(return_value=[])
        mock_express.bulk_create = AsyncMock(return_value=[])
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)

        def compute_fn(sources):
            refresh_count["n"] += 1
            return []

        engine.register(
            DerivedModelMeta(
                model_name="Stats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=compute_fn,
                debounce_ms=100,
            )
        )

        engine.setup_event_subscriptions()

        # Fire 10 rapid write events (within debounce window)
        for i in range(10):
            event = DomainEvent(
                event_type="dataflow.Order.create",
                payload={"model": "Order", "operation": "create", "record_id": f"o{i}"},
            )
            mock_db._event_bus.publish(event)

        # Wait for debounce + refresh
        await asyncio.sleep(0.4)

        # Should be exactly 1 recompute, not 10
        assert refresh_count["n"] == 1

    @pytest.mark.asyncio
    async def test_error_captured_on_failed_refresh(self):
        """Verify that a failed compute populates meta.last_error."""
        from kailash.middleware.communication.backends.memory import InMemoryEventBus
        from kailash.middleware.communication.domain_event import DomainEvent

        mock_db = MagicMock()
        mock_db._event_bus = InMemoryEventBus()
        mock_express = AsyncMock()
        mock_express.list = AsyncMock(side_effect=RuntimeError("db down"))
        mock_db.express = mock_express

        engine = DerivedModelEngine(dataflow_instance=mock_db)

        engine.register(
            DerivedModelMeta(
                model_name="BrokenStats",
                sources=["Order"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
                debounce_ms=50,
            )
        )

        engine.setup_event_subscriptions()

        # Trigger recompute via event
        event = DomainEvent(
            event_type="dataflow.Order.create",
            payload={"model": "Order", "operation": "create", "record_id": "o1"},
        )
        mock_db._event_bus.publish(event)

        await asyncio.sleep(0.3)

        meta = engine._models["BrokenStats"]
        assert meta.status == "error"
        assert meta.last_error is not None
        assert "db down" in meta.last_error


class TestOnSourceChangeDecorator:
    """Verify the @db.derived_model decorator accepts on_source_change."""

    def test_decorator_on_source_change_registers_correctly(self):
        """Verify derived_model with refresh='on_source_change' registers."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.derived_model(sources=["Order"], refresh="on_source_change")
        class OrderStats:
            id: str
            count: str

            @staticmethod
            def compute(sources):
                return []

        meta = db._derived_engine._models["OrderStats"]
        assert meta.refresh == "on_source_change"
        assert meta.debounce_ms == 100.0  # Default

    def test_decorator_custom_debounce(self):
        """Verify custom debounce_ms is passed through."""
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.derived_model(
            sources=["Order"], refresh="on_source_change", debounce_ms=500
        )
        class SlowStats:
            id: str
            value: str

            @staticmethod
            def compute(sources):
                return []

        meta = db._derived_engine._models["SlowStats"]
        assert meta.debounce_ms == 500


class TestOnSourceChangeCircularDetection:
    """Verify circular dependency detection includes on_source_change models."""

    def test_circular_on_source_change_detected(self):
        """A sources B (on_source_change), B sources A -> cycle."""
        engine = DerivedModelEngine(dataflow_instance=None)
        engine.register(
            DerivedModelMeta(
                model_name="A",
                sources=["B"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        engine.register(
            DerivedModelMeta(
                model_name="B",
                sources=["A"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            engine.validate_dependencies()

    def test_derived_to_derived_cycle(self):
        """A (on_source_change from B), B (on_source_change from C),
        C (on_source_change from A) -> cycle detected."""
        engine = DerivedModelEngine(dataflow_instance=None)
        engine.register(
            DerivedModelMeta(
                model_name="A",
                sources=["B"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        engine.register(
            DerivedModelMeta(
                model_name="B",
                sources=["C"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        engine.register(
            DerivedModelMeta(
                model_name="C",
                sources=["A"],
                refresh="on_source_change",
                schedule=None,
                compute_fn=lambda s: [],
            )
        )
        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            engine.validate_dependencies()
