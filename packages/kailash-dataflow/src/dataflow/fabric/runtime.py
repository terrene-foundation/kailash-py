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
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from dataflow.fabric.cache import (
    FabricCacheBackend,
    FabricTenantRequiredError,
    InMemoryFabricCacheBackend,
    RedisFabricCacheBackend,
    _mask_url,
)
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


def _resolve_instance_name(explicit: Optional[str]) -> str:
    """Resolve the fabric instance name with env-var fallback.

    Used as the Redis key prefix segment so two FabricRuntime processes
    can share a Redis instance without colliding. The default value
    ``"default"`` is sufficient for single-instance deployments; the
    env var ``FABRIC_INSTANCE_NAME`` lets operators set it per replica
    set.
    """
    if explicit:
        return explicit
    return os.environ.get("FABRIC_INSTANCE_NAME", "default")


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
        instance_name: Optional[str] = None,
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
        self._instance_name = _resolve_instance_name(instance_name)

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
        self._cache_backend: Optional[FabricCacheBackend] = None
        self._redis_client: Optional[Any] = None
        self._tasks: List[asyncio.Task[None]] = []
        self._shutting_down = False
        self._started = False
        self._started_at: Optional[datetime] = None
        self._health_manager: Optional[Any] = None
        # Phase 5.8: track registered Nexus routes for graceful shutdown.
        self._registered_nexus_routes: List[Dict[str, Any]] = []

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

        # 1. Ensure DataFlow is initialized (with timeout to prevent hung startup)
        if hasattr(self._dataflow, "initialize"):
            try:
                await asyncio.wait_for(
                    self._dataflow.initialize(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "FabricRuntime: database initialization timed out after 30s"
                )
                raise ConnectionError(
                    "Database initialization timed out after 30s"
                ) from None

        # 2. Connect all registered sources (parallel)
        await self._connect_sources()

        # 3. Resolve shared Redis client (one per replica) and build the
        # cache backend. The same client is reused for the leader elector
        # and the webhook receiver below so cache + leader + webhook all
        # share a single connection per replica.
        self._cache_backend = await self._build_cache_backend()

        # 4. Initialize pipeline executor with the chosen backend.
        self._pipeline = PipelineExecutor(
            dataflow=self._dataflow,
            cache_backend=self._cache_backend,
            dev_mode=self._dev_mode,
            instance_name=self._instance_name,
        )

        # 5. Elect leader. When we have a shared Redis client, hand it
        # to a RedisLeaderBackend so the leader does not open a second
        # Redis connection per replica.
        leader_backend = None
        if self._redis_client is not None:
            leader_backend = self._build_redis_leader_backend(self._redis_client)
        self._leader = LeaderElector(
            backend=leader_backend,
            redis_url=self._redis_url if leader_backend is None else None,
            dev_mode=self._dev_mode,
        )
        await self._leader.try_elect()
        await self._leader.start_heartbeat()

        # 6. Pre-warm materialized products (leader only)
        # In dev mode we always run serially. In production with a
        # shared cache, _prewarm_products consults the cache backend
        # via get_metadata before re-executing — this is the
        # leader-side warm-cache-on-election path that prevents the
        # impact-verse rolling-deploy regression where every new
        # leader re-ran the full prewarm serially.
        if self._leader.is_leader and prewarm:
            if self._dev_mode:
                await self._prewarm_products_serial()
            else:
                await self._prewarm_products()

        # 7. Start change detection (leader only)
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

        # 8. Set up webhook receiver (all workers — RT-2). Pass the
        # shared Redis client so the nonce dedup set is cross-replica
        # when Redis is configured.
        self._webhook_receiver = WebhookReceiver(
            sources=self._sources,
            on_webhook_event=self._on_source_change,
            redis_client=self._redis_client,
        )

        # 9. Set up serving layer (all workers). Forward the
        # tenant_extractor so per-request tenant_id reaches the cache
        # key construction (red-team amendment A).
        self._serving = FabricServingLayer(
            products=self._products,
            pipeline_executor=self._pipeline,
            express=getattr(self._dataflow, "_express_dataflow", None),
            sources=self._sources,
            enable_writes=self._enable_writes,
            on_product_refresh=self._on_source_change,
            consumer_registry=self._consumer_registry,
            tenant_extractor=self._tenant_extractor,
        )

        # 9. Subscribe to DataFlow event bus for model writes (TODO-18)
        self._subscribe_to_events()

        # 10. Phase 5.8: Register fabric endpoints with Nexus when one was
        # supplied via ``db.start(nexus=...)``. When no Nexus is bound, the
        # fabric runtime is "background only" — handlers exist on the
        # subsystems but are not exposed over HTTP, and a loud warning is
        # logged so operators are not surprised by 404s.
        self._register_with_nexus()

        self._started = True
        logger.info(
            "fabric.runtime.started",
            extra={
                "leader": self._leader.is_leader,
                "sources": len(self._sources),
                "products": len(self._products),
                "dev_mode": self._dev_mode,
                "instance_name": self._instance_name,
                "redis_url_masked": _mask_url(self._redis_url),
                "nexus_routes": len(self._registered_nexus_routes),
            },
        )

    # ------------------------------------------------------------------
    # Nexus registration (Phase 5.8)
    # ------------------------------------------------------------------

    def _register_with_nexus(self) -> None:
        """Wire the fabric subsystem handlers into the bound Nexus.

        Called from :meth:`start` after every subsystem has been
        initialised. When no ``nexus`` was supplied to ``__init__``,
        the runtime stays in "background only" mode and a warning is
        logged.

        The wiring covers, in order:

        * **Serving routes** — every dict returned by
          :meth:`FabricServingLayer.get_routes` (one per product, plus
          ``/fabric/_batch`` and any write endpoints when
          ``enable_writes=True``).
        * **Health endpoint** — ``GET /fabric/_health`` from a
          :class:`FabricHealthManager` instance, instantiated here if
          one wasn't already created lazily by :meth:`last_trace`.
        * **Trace endpoint** — ``GET /fabric/_trace/{product}`` from
          the same health manager.
        * **Webhook endpoint** — ``POST /fabric/webhook/{source_name}``
          wrapping :meth:`WebhookReceiver.handle_webhook` so each
          webhook source has a single canonical URL.
        """
        if self._nexus is None:
            logger.warning(
                "fabric.nexus.absent: FabricRuntime started without a Nexus "
                "instance — fabric endpoints are NOT exposed over HTTP. Pass "
                "nexus=Nexus(...) to db.start() to enable.",
                extra={"products": len(self._products)},
            )
            return

        from dataflow.fabric.nexus_adapter import (
            fabric_handler_to_fastapi,
            register_route_dicts,
        )

        registered: List[Dict[str, Any]] = []

        # Serving — products + batch + (optional) writes.
        if self._serving is not None:
            try:
                registered.extend(
                    register_route_dicts(self._nexus, self._serving.get_routes())
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "fabric.nexus.serving.failed", extra={"error": str(exc)}
                )

        # Health + trace — instantiate the manager if it wasn't lazy
        # built by ``last_trace`` already.
        try:
            from dataflow.fabric.health import FabricHealthManager

            if self._health_manager is None:
                self._health_manager = FabricHealthManager(
                    self._sources,
                    self._products,
                    self._pipeline,
                    self._started_at,
                )
            health_route = self._health_manager.get_health_handler()
            trace_route = self._health_manager.get_trace_handler()
            registered.extend(
                register_route_dicts(self._nexus, [health_route, trace_route])
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("fabric.nexus.health.failed", extra={"error": str(exc)})

        # Webhook — wrap handle_webhook so each source maps to a path.
        if self._webhook_receiver is not None:
            try:
                webhook_route = self._make_webhook_route()
                registered.append(register_route_dicts(self._nexus, [webhook_route])[0])
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "fabric.nexus.webhook.failed", extra={"error": str(exc)}
                )

        self._registered_nexus_routes = registered
        logger.info(
            "fabric.nexus.registered",
            extra={"count": len(registered)},
        )

    def _make_webhook_route(self) -> Dict[str, Any]:
        """Build a fabric-style route dict that exposes the webhook
        receiver as ``POST /fabric/webhook/{source_name}``.

        The handler reads the raw request body, copies request headers
        into a plain dict, and delegates to
        :meth:`WebhookReceiver.handle_webhook`. The receiver returns a
        plain dict (``{"accepted": bool, "reason": str}``) which the
        adapter wraps in a JSONResponse via the ``_status`` convention.
        """
        receiver = self._webhook_receiver

        async def handler(source_name: str = "", request: Any = None) -> Dict[str, Any]:
            if not source_name:
                return {"_status": 400, "error": "source_name path parameter required"}
            if request is None:
                return {"_status": 500, "error": "request object required"}
            body = await request.body()
            headers = {k.lower(): v for k, v in request.headers.items()}
            result = await receiver.handle_webhook(
                source_name=source_name,
                headers=headers,
                body=body,
            )
            status = 200 if result.get("accepted") else 400
            return {"_status": status, **result}

        handler.__name__ = "fabric_webhook"
        return {
            "method": "POST",
            "path": "/fabric/webhook/{source_name}",
            "handler": handler,
            "metadata": {"type": "webhook"},
        }

    # ------------------------------------------------------------------
    # Shared Redis client + cache backend builders
    # ------------------------------------------------------------------

    async def _get_or_create_redis_client(self) -> Optional[Any]:
        """Lazily build the shared Redis client for this replica.

        Returns ``None`` when no ``redis_url`` was supplied or when
        ``dev_mode=True`` forces in-memory backends. The same client
        instance is returned to the cache backend, leader elector, and
        webhook receiver so a single replica holds exactly one Redis
        connection across all fabric subsystems.
        """
        if self._redis_client is not None:
            return self._redis_client
        if self._dev_mode or not self._redis_url:
            return None
        try:
            import redis.asyncio as aioredis
        except ImportError as exc:
            raise ImportError(
                "redis[asyncio] is required when redis_url is set. "
                "Install with: pip install redis"
            ) from exc

        client = aioredis.from_url(
            self._redis_url,
            decode_responses=False,
            health_check_interval=30,
        )
        self._redis_client = client
        logger.info(
            "fabric.redis_client.created",
            extra={
                "redis_url_masked": _mask_url(self._redis_url),
                "instance_name": self._instance_name,
                "decode_responses": False,
                "health_check_interval": 30,
            },
        )
        return client

    async def _build_cache_backend(self) -> FabricCacheBackend:
        """Choose the cache backend for this replica.

        Mirrors the selection rules in :class:`PipelineExecutor` but
        uses the shared Redis client when available.
        """
        if self._dev_mode:
            if self._redis_url:
                logger.warning(
                    "fabric.cache.dev_mode_overrides_redis_url",
                    extra={
                        "backend": "memory",
                        "redis_url_masked": _mask_url(self._redis_url),
                        "instance_name": self._instance_name,
                    },
                )
            return InMemoryFabricCacheBackend()

        client = await self._get_or_create_redis_client()
        if client is None:
            return InMemoryFabricCacheBackend()
        return RedisFabricCacheBackend(
            redis_client=client,
            key_prefix="fabric",
            instance_name=self._instance_name,
            redis_url_for_logging=self._redis_url,
        )

    def _build_redis_leader_backend(self, redis_client: Any) -> Any:
        """Wrap an existing Redis client in a LeaderBackend.

        We deliberately do NOT call ``LeaderElector(redis_url=...)`` when
        the runtime already owns a client — that path opens a second
        Redis connection per replica. Instead we construct a thin
        ``RedisLeaderBackend`` from the existing client.
        """
        from dataflow.fabric.leader import RedisLeaderBackend

        backend = RedisLeaderBackend.__new__(RedisLeaderBackend)
        backend._redis_url = self._redis_url or ""
        backend._client = redis_client
        return backend

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
                    logger.exception(
                        "fabric.source.disconnect_failed",
                        extra={"source": name},
                    )

        # 6. Close the cache backend (no-op for in-memory; Redis backend
        # leaves the shared client to us so we close it next).
        if self._cache_backend is not None:
            try:
                await self._cache_backend.close()
            except Exception:
                logger.exception("fabric.cache.close_failed")

        # 7. Close the shared Redis client (cache + leader + webhook
        # all referenced this single client).
        if self._redis_client is not None:
            try:
                aclose = getattr(self._redis_client, "aclose", None)
                if aclose is not None:
                    await aclose()
                else:
                    close = getattr(self._redis_client, "close", None)
                    if close is not None:
                        result = close()
                        if asyncio.iscoroutine(result):
                            await result
            except Exception:
                logger.exception(
                    "fabric.redis_client.close_failed",
                    extra={"redis_url_masked": _mask_url(self._redis_url)},
                )
            self._redis_client = None

        self._started = False
        logger.info(
            "fabric.runtime.stopped",
            extra={"instance_name": self._instance_name},
        )

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
        """Pre-warm all materialized products with leader-side warm-cache.

        For each materialized product, the leader first checks the cache
        backend's metadata (cheap HMGET on Redis, dict lookup on memory).
        If a cached entry exists AND ``cached_at + staleness.max_age``
        is still in the future, the leader records ``cache_action=
        warm_skipped`` and does NOT re-execute the pipeline.

        This is the impact-verse regression guard: when a leader dies
        during a rolling deploy and a new leader elects, the new leader
        reads the still-fresh entries the old leader wrote and only
        re-executes products whose cache is missing or stale.
        """
        pipeline = self._pipeline
        if pipeline is None:
            # start() builds the pipeline before calling _prewarm_products;
            # this guard satisfies type checkers and raises loudly if the
            # invariant is ever violated.
            raise RuntimeError(
                "FabricRuntime._prewarm_products called before pipeline init"
            )

        materialized = [
            (name, product)
            for name, product in self._products.items()
            if product.mode.value == "materialized"
        ]

        if not materialized:
            return

        skipped = 0
        executed = 0
        now_utc = datetime.now(timezone.utc)

        for name, product in materialized:
            # Multi-tenant products cannot be pre-warmed without a tenant.
            # Skip them — the first per-tenant request will populate the
            # cache lazily.
            if product.multi_tenant:
                logger.debug(
                    "fabric.prewarm.multi_tenant_skipped",
                    extra={"product": name, "reason": "no_system_tenant"},
                )
                continue

            try:
                metadata = await pipeline.get_metadata(name)
            except Exception:
                logger.exception(
                    "fabric.prewarm.metadata_lookup_failed",
                    extra={"product": name},
                )
                metadata = None

            if metadata is not None:
                cached_at = metadata.get("cached_at")
                if isinstance(cached_at, datetime):
                    age = (now_utc - cached_at).total_seconds()
                    max_age = product.staleness.max_age.total_seconds()
                    if age <= max_age:
                        skipped += 1
                        logger.info(
                            "fabric.prewarm.warm_skipped",
                            extra={
                                "product": name,
                                "age_seconds": int(age),
                                "max_age_seconds": int(max_age),
                                "cache_action": "warm_skipped",
                            },
                        )
                        continue

            try:
                source_adapters = {
                    n: info["adapter"]
                    for n, info in self._sources.items()
                    if "adapter" in info
                }
                ctx = PipelineContext(
                    express=getattr(self._dataflow, "_express_dataflow", None),
                    sources=source_adapters,
                    products_cache=await self._get_products_cache(),
                )
                await pipeline.execute_product(
                    product_name=name,
                    product_fn=product.fn,
                    context=ctx,
                )
                executed += 1
                logger.debug(
                    "fabric.prewarm.executed",
                    extra={"product": name},
                )
            except Exception:
                logger.exception(
                    "fabric.prewarm.failed",
                    extra={"product": name},
                )

        logger.info(
            "fabric.prewarm.complete",
            extra={
                "prewarm_skipped": skipped,
                "prewarm_executed": executed,
                "total_products": len(materialized),
                "instance_name": self._instance_name,
            },
        )

    async def _prewarm_products_serial(self) -> None:
        """Pre-warm all materialized products one at a time (dev mode).

        Identical to ``_prewarm_products`` but executes products serially
        to reduce resource usage during development. This avoids parallel
        database connections and CPU spikes that are unnecessary in a
        single-developer environment.
        """
        pipeline = self._pipeline
        if pipeline is None:
            raise RuntimeError(
                "FabricRuntime._prewarm_products_serial called before " "pipeline init"
            )

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
                    products_cache=await self._get_products_cache(),
                )
                await pipeline.execute_product(
                    product_name=name,
                    product_fn=product.fn,
                    context=ctx,
                )
                logger.debug(
                    "fabric.prewarm.serial_executed",
                    extra={"product": name},
                )
            except Exception:
                logger.exception(
                    "fabric.prewarm.serial_failed",
                    extra={"product": name},
                )

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

        # Multi-tenant products require a tenant_id we cannot supply
        # from a source-change callback (the source change applies to
        # all tenants). Skip refresh; per-request fabric serving will
        # populate the cache lazily.
        if product.multi_tenant:
            logger.debug(
                "fabric.refresh.multi_tenant_skipped",
                extra={"product": product_name},
            )
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
                products_cache=await self._get_products_cache(),
            )
            await self._pipeline.execute_product(
                product_name=product_name,
                product_fn=product.fn,
                context=ctx,
            )
        except Exception:
            logger.exception(
                "fabric.refresh.failed",
                extra={"product": product_name},
            )

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

    async def _get_products_cache(
        self, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build a products cache dict from pipeline cached data.

        Multi-tenant products are skipped when ``tenant_id`` is None
        because we cannot pick a tenant for them. When ``tenant_id``
        is supplied, multi-tenant products use that tenant's view.
        """
        cache: Dict[str, Any] = {}
        if self._pipeline is None:
            return cache

        for name, product in self._products.items():
            if product.multi_tenant and tenant_id is None:
                # Cannot pick a tenant for the upstream-product cache
                # without a request context. Leave it absent.
                continue
            effective_tenant = tenant_id if product.multi_tenant else None
            cached = await self._pipeline.get_cached(name, tenant_id=effective_tenant)
            if cached is not None:
                data_bytes, _metadata = cached
                try:
                    import msgpack

                    cache[name] = msgpack.unpackb(data_bytes, raw=False)
                except ImportError:
                    import json as _json

                    cache[name] = _json.loads(data_bytes.decode("utf-8"))

        return cache

    async def get_cached_product(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Any]:
        """Retrieve a cached product result without executing the pipeline.

        Called by ProductInvokeNode to read fabric products from within
        workflows.

        Args:
            product_name: Name of the registered product.
            params: Optional parameters for parameterized products.
            tenant_id: Optional tenant scope. Required when the product
                was declared ``multi_tenant=True``.

        Returns:
            The cached product data, or None if not cached.

        Raises:
            FabricTenantRequiredError: When the product is multi_tenant
                but no tenant_id was supplied.
        """
        if self._pipeline is None:
            return None
        product = self._products.get(product_name)
        if product is not None and product.multi_tenant and tenant_id is None:
            raise FabricTenantRequiredError(
                f"Product '{product_name}' is multi_tenant=True; "
                f"caller must pass tenant_id."
            )
        result = await self._pipeline.get_product_from_cache(
            product_name, params, tenant_id
        )
        if result is None:
            return None
        return result.data if hasattr(result, "data") else result

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

    async def product_info(
        self, name: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get info for a specific product.

        Uses the cache backend's metadata fast path so this call does
        not transfer payload bytes from Redis (HMGET, not HGETALL).

        Multi-tenant products require an explicit ``tenant_id``;
        without it the call raises :class:`FabricTenantRequiredError`.

        BREAKING CHANGE in 2.0: this method is now async to support
        the Redis-backed cache. Wrap callers in ``await`` or
        ``asyncio.run()``.
        """
        product = self._products.get(name)
        if product is None:
            raise KeyError(f"Product '{name}' not found")

        if product.multi_tenant and tenant_id is None:
            raise FabricTenantRequiredError(
                f"Product '{name}' is multi_tenant=True; product_info() "
                f"requires an explicit tenant_id."
            )

        meta = None
        if self._pipeline is not None:
            meta = await self._pipeline.get_metadata(name, tenant_id=tenant_id)

        cached_at_value = meta.get("cached_at") if meta else None
        cached_at_iso: Optional[str] = None
        if isinstance(cached_at_value, datetime):
            cached_at_iso = cached_at_value.isoformat()
        elif isinstance(cached_at_value, str):
            cached_at_iso = cached_at_value

        return {
            "name": name,
            "mode": product.mode.value,
            "depends_on": product.depends_on,
            "cached": meta is not None,
            "cached_at": cached_at_iso,
            "tenant_id": tenant_id,
        }

    async def invalidate(
        self,
        product_name: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Invalidate cached data for a specific product.

        BREAKING CHANGE in 2.0: now async — wrap callers in ``await``.
        """
        if self._pipeline is None:
            return False
        product = self._products.get(product_name)
        if product is not None and product.multi_tenant and tenant_id is None:
            raise FabricTenantRequiredError(
                f"Product '{product_name}' is multi_tenant=True; "
                f"invalidate() requires an explicit tenant_id."
            )
        return await self._pipeline.invalidate(product_name, params, tenant_id)

    async def invalidate_all(self) -> int:
        """Invalidate all cached product data.

        BREAKING CHANGE in 2.0: now async. The return value is no
        longer a count — Redis cannot reliably count keys without an
        extra round-trip — and the method returns ``-1`` on completion.
        """
        if self._pipeline is None:
            return 0
        return await self._pipeline.invalidate_all()

    def last_trace(self, name: str) -> Dict[str, Any]:
        """Get the last pipeline trace for a product."""
        from dataflow.fabric.health import FabricHealthManager

        if self._health_manager is None:
            self._health_manager = FabricHealthManager(
                self._sources, self._products, self._pipeline, self._started_at
            )
        manager: FabricHealthManager = self._health_manager
        return manager.get_trace(name)

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
