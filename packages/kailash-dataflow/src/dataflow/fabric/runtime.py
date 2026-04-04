# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
FabricRuntime — the main orchestrator started by ``db.start()``.

Startup sequence:
1. Initialize DataFlow (ensure DB connected)
2. Connect all registered sources (parallel)
3. Elect leader
4. Pre-warm all materialized products (leader only)
5. Start change detection poll loops (leader only)
6. Register fabric endpoints (all workers)

Shutdown (``db.stop()``):
1. Stop accepting webhook deliveries
2. Wait for in-flight pipelines (timeout 30s)
3. Cancel all supervised tasks
4. Release leader lock
5. Disconnect sources
6. Flush metrics

Supervised task management uses individual asyncio.Tasks, NOT TaskGroup
(doc runtime-redteam RT-1).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from dataflow.fabric.change_detector import ChangeDetector
from dataflow.fabric.consumers import ConsumerFn, ConsumerRegistry
from dataflow.fabric.context import FabricContext, PipelineContext
from dataflow.fabric.leader import LeaderElector
from dataflow.fabric.pipeline import PipelineExecutor
from dataflow.fabric.products import ProductRegistration
from dataflow.fabric.serving import FabricServingLayer
from dataflow.fabric.webhooks import WebhookReceiver

logger = logging.getLogger(__name__)

__all__ = ["FabricRuntime"]

_DEFAULT_SHUTDOWN_TIMEOUT = 30  # seconds


class FabricRuntime:
    """Main fabric orchestrator — ties together all fabric subsystems.

    Created and started by ``DataFlow.start()``. Manages the lifecycle of:
    - Source connections
    - Leader election
    - Change detection poll loops
    - Pipeline execution
    - Serving layer (endpoint registration)
    - Webhook receiver
    - Event bus subscription
    """

    def __init__(
        self,
        dataflow: Any,
        sources: Dict[str, Dict[str, Any]],
        products: Dict[str, ProductRegistration],
        fail_fast: bool = True,
        dev_mode: bool = False,
        redis_url: Optional[str] = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        enable_writes: bool = False,
        tenant_extractor: Optional[Callable] = None,
        nexus: Optional[Any] = None,
    ) -> None:
        self._dataflow = dataflow
        self._sources = sources
        self._products = products
        self._fail_fast = fail_fast
        self._dev_mode = dev_mode
        self._redis_url = redis_url
        self._host = host
        self._port = port
        self._enable_writes = enable_writes
        self._tenant_extractor = tenant_extractor
        self._nexus = nexus

        # Consumer adapter registry
        self._consumer_registry = ConsumerRegistry()

        # Validate parameter combinations (TODO-38)
        self._validate_params()

        # Subsystems (initialized during start)
        self._pipeline: Optional[PipelineExecutor] = None
        self._change_detector: Optional[ChangeDetector] = None
        self._leader: Optional[LeaderElector] = None
        self._serving: Optional[FabricServingLayer] = None
        self._webhook_receiver: Optional[WebhookReceiver] = None
        self._tasks: List[asyncio.Task[None]] = []
        self._shutting_down = False
        self._started = False
        self._started_at: Optional[datetime] = None
        self._health_manager: Optional[Any] = None

    def _validate_params(self) -> None:
        """Validate parameter combinations at startup (TODO-38)."""
        # multi_tenant=True without tenant_extractor → error
        for name, product in self._products.items():
            if product.multi_tenant and self._tenant_extractor is None:
                raise ValueError(
                    f"Product '{name}' has multi_tenant=True but no "
                    f"tenant_extractor was provided to db.start(). "
                    f"Pass tenant_extractor=lambda req: req.headers['X-Tenant-Id']"
                )

        # enable_writes without auth → warning
        if self._enable_writes and self._nexus is None:
            logger.warning(
                "enable_writes=True without Nexus auth middleware — "
                "write endpoints will be unauthenticated"
            )

        # host=0.0.0.0 without auth → warning
        if self._host == "0.0.0.0" and self._nexus is None:
            logger.warning(
                "Binding to 0.0.0.0 without auth middleware — "
                "fabric endpoints will be publicly accessible"
            )

    async def start(self, prewarm: bool = True) -> None:
        """Start the fabric runtime.

        This is called by ``db.start()`` and orchestrates the full startup
        sequence.

        Args:
            prewarm: Whether to pre-warm materialized products on startup.
                Defaults to ``True``. When ``False``, the first request for
                each product returns a 202 (warming) response. Independent
                of ``dev_mode`` — pre-warming runs serially in dev mode and
                in parallel otherwise.
        """
        if self._started:
            logger.warning("FabricRuntime already started")
            return

        self._shutting_down = False
        self._started_at = datetime.now(timezone.utc)

        # 1. Ensure DataFlow is initialized
        if hasattr(self._dataflow, "initialize"):
            await self._dataflow.initialize()

        # 2. Connect all registered sources (parallel)
        await self._connect_sources()

        # 3. Initialize pipeline executor
        self._pipeline = PipelineExecutor(
            dataflow=self._dataflow,
            redis_url=self._redis_url,
            dev_mode=self._dev_mode,
        )

        # 4. Elect leader
        self._leader = LeaderElector(
            redis_url=self._redis_url,
            dev_mode=self._dev_mode,
        )
        await self._leader.try_elect()
        await self._leader.start_heartbeat()

        # 5. Pre-warm materialized products (leader only)
        if self._leader.is_leader and prewarm:
            if self._dev_mode:
                await self._prewarm_products_serial()
            else:
                await self._prewarm_products()

        # 6. Start change detection (leader only)
        #    Extract adapter objects from source info dicts (#253).
        #    ChangeDetector expects Dict[str, BaseSourceAdapter], but
        #    self._sources is Dict[str, Dict[str, Any]].
        if self._leader.is_leader:
            adapters = {
                n: info["adapter"]
                for n, info in self._sources.items()
                if isinstance(info, dict) and "adapter" in info
            }
            self._change_detector = ChangeDetector(
                sources=adapters,
                products=self._products,
                pipeline_executor=self._pipeline,
                dev_mode=self._dev_mode,
            )
            self._change_detector.set_on_change(self._on_source_change_with_trigger)
            await self._change_detector.start()

        # 7. Set up webhook receiver (all workers — RT-2)
        self._webhook_receiver = WebhookReceiver(
            sources=self._sources,
            on_webhook_event=self._on_source_change,
        )

        # 8. Set up serving layer (all workers)
        self._serving = FabricServingLayer(
            products=self._products,
            pipeline_executor=self._pipeline,
            express=getattr(self._dataflow, "_express_dataflow", None),
            sources=self._sources,
            enable_writes=self._enable_writes,
            on_product_refresh=self._on_source_change,
            consumer_registry=self._consumer_registry,
        )

        # 9. Subscribe to DataFlow event bus for model writes (TODO-18)
        self._subscribe_to_events()

        self._started = True
        logger.debug(
            "FabricRuntime started (leader=%s, sources=%d, products=%d, dev=%s)",
            self._leader.is_leader,
            len(self._sources),
            len(self._products),
            self._dev_mode,
        )

    async def stop(self) -> None:
        """Graceful shutdown of the fabric runtime."""
        if not self._started:
            return

        self._shutting_down = True
        logger.debug("FabricRuntime shutting down...")

        # 1. Stop accepting webhook deliveries (handled by shutting_down flag)

        # 2. Wait for in-flight pipelines (timeout)
        if self._pipeline is not None:
            try:
                await asyncio.wait_for(
                    self._pipeline.drain(),
                    timeout=_DEFAULT_SHUTDOWN_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Pipeline drain timed out after %ds", _DEFAULT_SHUTDOWN_TIMEOUT
                )
            except AttributeError:
                pass  # drain() not implemented in basic pipeline

        # 3. Cancel all supervised tasks
        if self._change_detector is not None:
            await self._change_detector.stop()

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # 4. Release leader lock
        if self._leader is not None:
            await self._leader.release()

        # 5. Disconnect sources
        for name, source_info in self._sources.items():
            adapter = source_info.get("adapter")
            if adapter and adapter.is_connected:
                try:
                    await adapter.disconnect()
                except Exception:
                    logger.exception("Failed to disconnect source '%s'", name)

        self._started = False
        logger.debug("FabricRuntime stopped")

    async def _connect_sources(self) -> None:
        """Connect all sources in parallel."""
        tasks = []
        for name, source_info in self._sources.items():
            adapter = source_info.get("adapter")
            if adapter:
                tasks.append(self._connect_source(name, adapter))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    name = list(self._sources.keys())[i]
                    if self._fail_fast:
                        raise ConnectionError(
                            f"Failed to connect source '{name}': {result}"
                        ) from result
                    logger.warning("Skipping unhealthy source '%s': %s", name, result)

    async def _connect_source(self, name: str, adapter: Any) -> None:
        """Connect a single source with error handling."""
        try:
            await adapter.connect()
            logger.debug("Connected source '%s'", name)
        except Exception as e:
            logger.error("Source '%s' connection failed: %s", name, e)
            raise

    async def _prewarm_products(self) -> None:
        """Pre-warm all materialized products by running their pipelines."""
        materialized = [
            (name, product)
            for name, product in self._products.items()
            if product.mode.value == "materialized"
        ]

        if not materialized:
            return

        logger.debug("Pre-warming %d materialized products", len(materialized))

        for name, product in materialized:
            try:
                # Build context for this product
                source_adapters = {
                    n: info["adapter"]
                    for n, info in self._sources.items()
                    if "adapter" in info
                }
                ctx = PipelineContext(
                    express=getattr(self._dataflow, "_express_dataflow", None),
                    sources=source_adapters,
                    products_cache=self._get_products_cache(),
                )
                await self._pipeline.execute_product(
                    product_name=name,
                    product_fn=product.fn,
                    context=ctx,
                )
                logger.debug("Pre-warmed product '%s'", name)
            except Exception:
                logger.exception("Failed to pre-warm product '%s'", name)

    async def _prewarm_products_serial(self) -> None:
        """Pre-warm all materialized products one at a time (dev mode).

        Identical to ``_prewarm_products`` but executes products serially
        to reduce resource usage during development. This avoids parallel
        database connections and CPU spikes that are unnecessary in a
        single-developer environment.
        """
        materialized = [
            (name, product)
            for name, product in self._products.items()
            if product.mode.value == "materialized"
        ]

        if not materialized:
            return

        logger.debug(
            "Pre-warming %d materialized products (serial, dev_mode)",
            len(materialized),
        )

        for name, product in materialized:
            try:
                source_adapters = {
                    n: info["adapter"]
                    for n, info in self._sources.items()
                    if "adapter" in info
                }
                ctx = PipelineContext(
                    express=getattr(self._dataflow, "_express_dataflow", None),
                    sources=source_adapters,
                    products_cache=self._get_products_cache(),
                )
                await self._pipeline.execute_product(
                    product_name=name,
                    product_fn=product.fn,
                    context=ctx,
                )
                logger.debug("Pre-warmed product '%s' (serial)", name)
            except Exception:
                logger.exception("Failed to pre-warm product '%s'", name)

    async def _on_source_change_with_trigger(
        self, product_name: str, triggered_by: str = ""
    ) -> None:
        """Callback from ChangeDetector (2-arg: product_name, triggered_by)."""
        await self._on_source_change(product_name)

    async def _on_source_change(self, product_name: str) -> None:
        """Callback when a source change triggers a product refresh."""
        if self._shutting_down or self._pipeline is None:
            return

        product = self._products.get(product_name)
        if product is None:
            return

        try:
            source_adapters = {
                n: info["adapter"]
                for n, info in self._sources.items()
                if "adapter" in info
            }
            ctx = PipelineContext(
                express=getattr(self._dataflow, "_express_dataflow", None),
                sources=source_adapters,
                products_cache=self._get_products_cache(),
            )
            await self._pipeline.execute_product(
                product_name=product_name,
                product_fn=product.fn,
                context=ctx,
            )
        except Exception:
            logger.exception("Pipeline execution failed for product '%s'", product_name)

    def _subscribe_to_events(self) -> None:
        """Subscribe to DataFlow event bus for write notifications (TODO-18).

        When a model write fires, identify all products with that model in
        depends_on and enqueue debounced pipeline refresh.
        """
        if not hasattr(self._dataflow, "on"):
            return

        events = [
            "model.created",
            "model.updated",
            "model.deleted",
            "model.bulk_created",
            "model.bulk_deleted",
        ]

        for event_name in events:
            try:
                self._dataflow.on(event_name, self._on_model_write)
            except Exception:
                logger.debug("Could not subscribe to event '%s'", event_name)

    async def _on_model_write(self, event_data: Any = None) -> None:
        """Handle model write events from the DataFlow event bus."""
        if self._shutting_down:
            return

        # Extract model name from event data
        model_name = None
        if isinstance(event_data, dict):
            model_name = event_data.get("model") or event_data.get("model_name")
        elif isinstance(event_data, str):
            model_name = event_data

        if not model_name:
            return

        # Find affected products
        for pname, product in self._products.items():
            if model_name in product.depends_on:
                await self._on_source_change(pname)

    def _get_products_cache(self) -> Dict[str, Any]:
        """Build a products cache dict from pipeline cached data."""
        cache: Dict[str, Any] = {}
        if self._pipeline is None:
            return cache

        for name in self._products:
            cached = self._pipeline.get_cached(name)
            if cached is not None:
                data_bytes, metadata = cached
                try:
                    import msgpack

                    cache[name] = msgpack.unpackb(data_bytes, raw=False)
                except ImportError:
                    import json

                    cache[name] = json.loads(data_bytes.decode("utf-8"))

        return cache

    # ------------------------------------------------------------------
    # Public API (db.fabric.*)
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Programmatic fabric status (TODO-25)."""
        return {
            "started": self._started,
            "leader": self._leader.is_leader if self._leader else False,
            "leader_id": self._leader.leader_id if self._leader else None,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "sources": {
                name: {
                    "state": (
                        info["adapter"].state.value if "adapter" in info else "unknown"
                    ),
                    "healthy": info["adapter"].healthy if "adapter" in info else False,
                }
                for name, info in self._sources.items()
            },
            "products": list(self._products.keys()),
            "dev_mode": self._dev_mode,
        }

    def source_health(self, name: str) -> Dict[str, Any]:
        """Get health info for a specific source."""
        source_info = self._sources.get(name)
        if source_info is None:
            raise KeyError(f"Source '{name}' not found")
        adapter = source_info.get("adapter")
        if adapter is None:
            return {"name": name, "healthy": False, "state": "no_adapter"}
        return {
            "name": name,
            "healthy": adapter.healthy,
            "state": adapter.state.value,
            "circuit_breaker": adapter.circuit_breaker.state.value,
            "last_change": (
                adapter.last_change_detected.isoformat()
                if adapter.last_change_detected
                else None
            ),
        }

    def product_info(self, name: str) -> Dict[str, Any]:
        """Get info for a specific product."""
        product = self._products.get(name)
        if product is None:
            raise KeyError(f"Product '{name}' not found")

        cached = self._pipeline.get_cached(name) if self._pipeline else None
        return {
            "name": name,
            "mode": product.mode.value,
            "depends_on": product.depends_on,
            "cached": cached is not None,
            "cached_at": cached[1].get("cached_at") if cached else None,
        }

    def invalidate(
        self, product_name: str, params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Invalidate cached data for a specific product.

        Args:
            product_name: Name of the product to invalidate.
            params: Optional parameters (for parameterized products).

        Returns:
            ``True`` if the cache entry existed and was removed.
        """
        if self._pipeline is None:
            return False
        return self._pipeline.invalidate(product_name, params)

    def invalidate_all(self) -> int:
        """Invalidate all cached product data.

        Returns:
            The number of cache entries that were cleared.
        """
        if self._pipeline is None:
            return 0
        return self._pipeline.invalidate_all()

    def last_trace(self, name: str) -> Dict[str, Any]:
        """Get the last pipeline trace for a product."""
        if self._health_manager is None:
            from dataflow.fabric.health import FabricHealthManager

            self._health_manager = FabricHealthManager(
                self._sources, self._products, self._pipeline, self._started_at
            )
        return self._health_manager.get_trace(name)

    def register_consumer(self, name: str, fn: ConsumerFn) -> None:
        """Register a consumer adapter function.

        Consumer functions are pure data transforms: canonical product
        data in, consumer-specific view out. They are applied by the
        serving layer when the ``?consumer=`` query parameter is present.

        Args:
            name: Unique consumer identifier.
            fn: Pure function ``(dict) -> dict``.
        """
        self._consumer_registry.register(name, fn)

    @property
    def consumer_registry(self) -> ConsumerRegistry:
        """Return the consumer adapter registry."""
        return self._consumer_registry

    @property
    def serving(self) -> Optional[FabricServingLayer]:
        return self._serving

    @property
    def webhook_receiver(self) -> Optional[WebhookReceiver]:
        return self._webhook_receiver

    @property
    def pipeline(self) -> Optional[PipelineExecutor]:
        return self._pipeline

    @property
    def is_leader(self) -> bool:
        return self._leader.is_leader if self._leader else False

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Generate MCP tool definitions for all registered products.

        Returns a list of MCP-compatible tool definition dicts that can be
        registered with a kailash-mcp server or any MCP-compatible runtime.
        """
        from dataflow.fabric.mcp_integration import generate_mcp_tools

        return generate_mcp_tools(self._products)
