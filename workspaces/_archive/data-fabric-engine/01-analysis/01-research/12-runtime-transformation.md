# How DataFlow Actually Becomes a Fabric — The Runtime Transformation

## The Fundamental Change

DataFlow today is **request-driven**. Nothing runs until someone calls `db.express.read()` or a workflow executes. There are no background threads, no event loops, no daemon tasks (except one: `PoolMonitor` which polls connection pool stats every 10 seconds on a daemon thread).

The fabric makes DataFlow **event-driven**. After `db.start()`, background tasks continuously:

- Poll sources for changes
- Watch files for modifications
- Listen for webhooks
- Execute pipelines when changes are detected
- Update cache atomically
- Report health metrics

This is the biggest architectural change in DataFlow's history. It's not "adding features" — it's changing the execution model from pull to push.

---

## What Is Running After `db.start()`

### Before Fabric (current DataFlow)

```
DataFlow Process
├── Main thread (handles requests)
├── Pool monitor daemon thread (10s interval, checks connection utilization)
└── Nothing else running
```

### After `db.start()`

```
DataFlow Process
├── Main thread (handles requests, serves /fabric/* endpoints)
│
├── FabricRuntime (asyncio TaskGroup — managed lifecycle)
│   ├── LeaderElector          — heartbeat task (10s interval)
│   │                            Only the leader runs tasks below
│   │
│   ├── SourceManager          — manages all source connections
│   │   ├── source:crm         — RestSourceAdapter instance
│   │   ├── source:finance     — CloudSourceAdapter instance
│   │   └── source:config      — FileSourceAdapter instance
│   │
│   ├── ChangeDetector         — runs detection for all sources
│   │   ├── Poller:crm         — asyncio task, runs every poll_interval
│   │   ├── Poller:finance     — asyncio task, runs every poll_interval
│   │   └── Watcher:config     — watchdog observer (separate thread)
│   │
│   ├── WebhookReceiver        — HTTP endpoint listener for push sources
│   │   └── /webhooks/{name}   — validates signature, triggers pipeline
│   │
│   ├── PipelineExecutor       — runs product functions when sources change
│   │   ├── Semaphore(3)       — max 3 concurrent pipelines
│   │   ├── DebounceTimers     — per-product write debounce
│   │   └── Pipeline queue     — ordered by product dependency graph
│   │
│   ├── CacheManager           — wraps DataFlow's existing cache
│   │   ├── ProductCache       — product-level cache keys
│   │   └── MetadataStore      — freshness timestamps, pipeline traces
│   │
│   ├── Scheduler              — cron-based product refresh
│   │   └── CronTasks          — per-product cron schedules
│   │
│   └── HealthReporter         — extends DataFlow's existing HealthMonitor
│       ├── /fabric/_health    — source + product + cache health
│       ├── /fabric/_trace     — pipeline execution traces
│       └── Metrics exporter   — Prometheus counters/gauges
│
├── Pool monitor daemon thread (existing, unchanged)
└── Watchdog observer thread (new, for FileSource)
```

### The asyncio TaskGroup Pattern

The fabric runtime uses `asyncio.TaskGroup` (Python 3.11+) for structured concurrency. All background tasks are children of one group — when the group is cancelled (on `db.stop()`), all tasks are cleaned up.

```python
class FabricRuntime:
    async def start(self):
        """Start all fabric background tasks as a managed group."""
        self._task_group = asyncio.TaskGroup()

        # Enter the task group — tasks will be created inside it
        self._tg_context = await self._task_group.__aenter__()

        # Leader election (runs on all workers)
        self._tg_context.create_task(self._leader_heartbeat())

        if await self._is_leader():
            # Source polling tasks (leader only)
            for name, source in self._sources.items():
                if source.config.poll_interval:
                    self._tg_context.create_task(
                        self._poll_loop(name, source)
                    )
                if source.config.webhook:
                    # Webhook receiver is an endpoint, not a task
                    self._register_webhook_endpoint(name, source)

            # Cron scheduler (leader only)
            for name, product in self._products.items():
                if product.schedule:
                    self._tg_context.create_task(
                        self._cron_loop(name, product)
                    )

        # Pre-warm (leader only, blocks until complete)
        if await self._is_leader() and not self._dev_mode:
            await self._pre_warm_all()

        # Register serving endpoints (all workers)
        self._register_fabric_endpoints()

    async def stop(self):
        """Stop all fabric background tasks cleanly."""
        self._shutting_down = True

        # Wait for in-flight pipelines (max 30s)
        await asyncio.wait_for(
            self._pipeline_executor.drain(), timeout=30
        )

        # Cancel all background tasks
        await self._task_group.__aexit__(None, None, None)

        # Release leader lock
        await self._leader_elector.release()

        # Disconnect sources
        for source in self._sources.values():
            await source.adapter.disconnect()
```

---

## The Poll Loop — How Source Watching Actually Works

This is the core event loop of the fabric. One poll loop runs per source (on the leader worker only).

```python
async def _poll_loop(self, source_name: str, source: SourceRegistration):
    """Background task that polls a source for changes.

    Runs forever until cancelled. Sleeps for poll_interval between checks.
    """
    adapter = source.adapter

    while not self._shutting_down:
        try:
            # Phase 1: DETECT (cheap — no data transfer)
            changed = await adapter.detect_change()

            if changed:
                # Phase 2: Identify affected products
                affected = [
                    name for name, product in self._products.items()
                    if source_name in product.depends_on
                ]

                # Phase 3: Queue pipeline execution for each product
                for product_name in affected:
                    await self._pipeline_executor.enqueue(
                        product_name,
                        trigger=f"source_change:{source_name}",
                    )

            # Update source health metrics
            source.last_check = datetime.utcnow()
            source.consecutive_failures = 0
            source.state = "active"

        except Exception as e:
            source.consecutive_failures += 1
            source.last_error = str(e)

            # Circuit breaker
            if source.consecutive_failures >= source.config.circuit_breaker.failure_threshold:
                source.state = "paused"
                # Wait for probe interval, then try again
                await asyncio.sleep(source.config.circuit_breaker.probe_interval)
                continue

        # Sleep until next poll
        await asyncio.sleep(source.config.poll_interval)
```

### How `detect_change()` Works Per Source Type

**The performance budget**: Detection must complete in <100ms for the fabric to feel responsive. If detection takes 5 seconds, the effective refresh rate is poll_interval + 5 seconds.

| Source Type | Detection Method                                                   | Typical Latency | Network Cost              |
| ----------- | ------------------------------------------------------------------ | --------------- | ------------------------- |
| REST API    | `HEAD` request or `GET` with `If-None-Match` → 304 means no change | 50-200ms        | ~500 bytes (headers only) |
| File        | `os.stat(path).st_mtime` comparison                                | <1ms            | 0 (local)                 |
| Cloud (S3)  | `HEAD` object or `ListObjectsV2` with 1 result                     | 50-150ms        | ~1KB                      |
| Database    | `SELECT MAX(updated_at) FROM table`                                | 5-50ms          | ~100 bytes                |
| Stream      | N/A (continuous consumption, not polled)                           | 0               | Continuous                |

```python
class RestSourceAdapter(BaseSourceAdapter):
    async def detect_change(self) -> bool:
        """Send conditional GET. 304 = no change. 200 = changed."""
        headers = {}
        if self._last_etag:
            headers["If-None-Match"] = self._last_etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified

        async with self._client.stream("GET", self._detect_url, headers=headers) as resp:
            if resp.status_code == 304:
                return False  # No change — zero data transfer

            if resp.status_code == 200:
                # Store new ETag/Last-Modified for next check
                self._last_etag = resp.headers.get("ETag")
                self._last_modified = resp.headers.get("Last-Modified")
                return True

            raise SourceError(f"Unexpected status {resp.status_code}")

class FileSourceAdapter(BaseSourceAdapter):
    async def detect_change(self) -> bool:
        """Compare file mtime with last known."""
        stat = await asyncio.to_thread(os.stat, self.config.path)
        mtime = stat.st_mtime
        if mtime != self._last_mtime:
            self._last_mtime = mtime
            return True
        return False

    def start_watcher(self):
        """Start OS-level file watcher for instant notification."""
        from watchdog.observers import Observer
        handler = FabricFileHandler(callback=self._on_file_changed)
        self._observer = Observer()
        self._observer.schedule(handler, path=os.path.dirname(self.config.path))
        self._observer.start()  # Starts a daemon thread
```

---

## The Pipeline Executor — How Products Actually Refresh

When a source change is detected, the pipeline executor runs the product function and updates cache.

```python
class PipelineExecutor:
    def __init__(self, max_concurrent: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._debounce_timers: Dict[str, asyncio.TimerHandle] = {}
        self._traces: Dict[str, deque] = {}  # Per-product trace history (bounded)

    async def enqueue(self, product_name: str, trigger: str):
        """Enqueue a product for refresh. Debounced — multiple triggers within
        the debounce window are batched into one execution."""
        product = self._products[product_name]
        debounce_seconds = product.write_debounce.total_seconds()

        # Cancel existing debounce timer if any
        if product_name in self._debounce_timers:
            self._debounce_timers[product_name].cancel()

        # Set new debounce timer
        loop = asyncio.get_running_loop()
        self._debounce_timers[product_name] = loop.call_later(
            debounce_seconds,
            lambda: asyncio.ensure_future(
                self._execute(product_name, trigger)
            ),
        )

    async def _execute(self, product_name: str, trigger: str):
        """Execute a product pipeline. Semaphore-guarded for concurrency control."""
        async with self._semaphore:
            product = self._products[product_name]
            trace = PipelineTrace(
                product=product_name,
                trigger=trigger,
                started_at=datetime.utcnow(),
                steps=[],
            )

            try:
                # Build FabricContext for this execution
                ctx = FabricContext(
                    express=self._dataflow.express,
                    sources=self._source_handles,
                    products=self._product_cache,
                    tenant_id=None,  # Set per-request for multi-tenant
                )

                # Execute the product function
                if product.mode == "materialized":
                    result = await product.fn(ctx)
                    await self._update_cache(product_name, result, trace)

                elif product.mode == "parameterized":
                    # For parameterized: invalidate ALL cached parameter combos
                    # They'll be re-computed on next request
                    await self._invalidate_parameterized(product_name)

                trace.status = "success"
                trace.duration_ms = (datetime.utcnow() - trace.started_at).total_seconds() * 1000

            except Exception as e:
                trace.status = "failed"
                trace.error = str(e)
                logger.warning(f"Pipeline failed for {product_name}: {e}")
                # Cache keeps old data (atomic swap never happened)

            # Store trace (bounded deque, max 20 per product)
            if product_name not in self._traces:
                self._traces[product_name] = deque(maxlen=20)
            self._traces[product_name].append(trace)

    async def _update_cache(self, product_name: str, result: Any, trace: PipelineTrace):
        """Atomic cache update. Only writes if content actually changed."""
        # Serialize result
        serialized = json.dumps(result, default=str, sort_keys=True)
        content_hash = hashlib.sha256(serialized.encode()).hexdigest()

        # Compare with existing cache
        existing_hash = await self._cache.get(f"fabric:hash:{product_name}")

        if existing_hash == content_hash:
            trace.cache_action = "skip"  # Content unchanged
            return

        # Atomic swap: write new data + hash + metadata
        pipe = self._cache.pipeline()  # Redis pipeline for atomicity
        pipe.set(f"fabric:data:{product_name}", serialized)
        pipe.set(f"fabric:hash:{product_name}", content_hash)
        pipe.set(f"fabric:meta:{product_name}", json.dumps({
            "cached_at": datetime.utcnow().isoformat(),
            "pipeline_ms": trace.duration_ms,
            "trigger": trace.trigger,
            "content_hash": content_hash,
        }))
        await pipe.execute()

        trace.cache_action = "swap"
```

---

## The Serving Layer — How Endpoints Actually Work

When FE calls `GET /fabric/dashboard`, what happens?

```python
class FabricServingLayer:
    """Registers fabric endpoints with Nexus."""

    def register_endpoints(self, nexus: Any):
        """Register all product endpoints."""
        for name, product in self._products.items():
            # Read endpoint
            nexus.add_route(
                f"/fabric/{name}",
                method="GET",
                handler=self._make_read_handler(name, product),
            )

            # Write endpoint (if enabled)
            if self._enable_writes:
                nexus.add_route(
                    f"/fabric/{name}/write",
                    method="POST",
                    handler=self._make_write_handler(name),
                )

        # Observability endpoints
        nexus.add_route("/fabric/_health", method="GET", handler=self._health_handler)
        nexus.add_route("/fabric/_trace/{product}", method="GET", handler=self._trace_handler)

    def _make_read_handler(self, product_name: str, product: ProductRegistration):
        async def handler(request):
            # Auth check (if configured)
            if product.auth and product.auth.get("roles"):
                self._check_auth(request, product.auth["roles"])

            # Rate limit check
            if not self._rate_limiter.allow(request.client_ip, product_name):
                return Response(status_code=429, headers={"Retry-After": "60"})

            if product.mode == "materialized":
                return await self._serve_materialized(product_name, request)
            elif product.mode == "parameterized":
                return await self._serve_parameterized(product_name, product, request)
            elif product.mode == "virtual":
                return await self._serve_virtual(product_name, product, request)

        return handler

    async def _serve_materialized(self, product_name: str, request):
        """Serve a materialized product from cache."""
        # Read from cache
        data = await self._cache.get(f"fabric:data:{product_name}")
        meta = await self._cache.get(f"fabric:meta:{product_name}")

        if data is None:
            # Cold product — not in cache
            # Trigger pipeline (if not already running)
            await self._pipeline_executor.enqueue(product_name, trigger="cold_start")
            return Response(
                status_code=202,
                body=json.dumps({"status": "warming", "product": product_name}),
                headers={
                    "X-Fabric-Freshness": "cold",
                    "Retry-After": "5",
                },
            )

        # Parse metadata
        meta_dict = json.loads(meta) if meta else {}
        cached_at = datetime.fromisoformat(meta_dict.get("cached_at", ""))
        age_seconds = (datetime.utcnow() - cached_at).total_seconds()

        # Check staleness
        freshness = "fresh"
        if product_name in self._products:
            max_age = self._products[product_name].staleness.max_age
            if max_age and age_seconds > max_age.total_seconds():
                freshness = "stale"

        return Response(
            status_code=200,
            body=data,  # Raw JSON — clean, no envelope
            headers={
                "Content-Type": "application/json",
                "X-Fabric-Freshness": freshness,
                "X-Fabric-Age": str(int(age_seconds)),
                "X-Fabric-Cached-At": meta_dict.get("cached_at", ""),
                "X-Fabric-Pipeline-Ms": str(meta_dict.get("pipeline_ms", 0)),
                "X-Fabric-Mode": "materialized",
                "Cache-Control": "no-store",  # Don't let CDN/browser cache this
            },
        )

    async def _serve_parameterized(self, product_name: str, product, request):
        """Serve a parameterized product — cache key includes query params."""
        # Extract parameters from query string
        params = dict(request.query_params)

        # Validate and type-coerce parameters against function signature
        typed_params = self._coerce_params(product.fn, params)

        # Build cache key from canonical parameter serialization
        cache_key = self._build_param_cache_key(product_name, typed_params)

        # Try cache
        data = await self._cache.get(cache_key)
        if data:
            meta = await self._cache.get(f"{cache_key}:meta")
            # ... same freshness logic as materialized ...
            return Response(status_code=200, body=data, headers={...})

        # Cache miss — execute product function inline
        ctx = FabricContext(
            express=self._dataflow.express,
            sources=self._source_handles,
            products=self._product_cache,
            tenant_id=self._extract_tenant(request),
        )

        result = await product.fn(ctx, **typed_params)
        serialized = json.dumps(result, default=str, sort_keys=True)

        # Cache the result
        await self._cache.set(cache_key, serialized, ttl=product.staleness.max_age_seconds)
        await self._cache.set(f"{cache_key}:meta", json.dumps({
            "cached_at": datetime.utcnow().isoformat(),
            "params": typed_params,
        }))

        return Response(status_code=200, body=serialized, headers={
            "X-Fabric-Freshness": "fresh",
            "X-Fabric-Age": "0",
            "X-Fabric-Mode": "parameterized",
        })
```

---

## Performance Architecture

### Latency Budgets

| Operation                          | Target           | How                                           |
| ---------------------------------- | ---------------- | --------------------------------------------- |
| Materialized product read          | <5ms             | Redis GET, no computation                     |
| Parameterized product (cache hit)  | <10ms            | Redis GET with param key lookup               |
| Parameterized product (cache miss) | <500ms           | Execute product function inline               |
| Virtual product                    | Source-dependent | Pass-through, no caching                      |
| Change detection (per source)      | <100ms           | Conditional HTTP, file stat, or SQL           |
| Pipeline execution                 | <2s              | Product function + cache write                |
| Pre-warming (per product)          | <5s              | Source fetch + product function + cache write |
| Write pass-through                 | <50ms            | Express API or source adapter                 |
| Write → product refresh            | <3s              | Debounce (1s) + pipeline (2s)                 |

### Memory Budget

| Component                                 | Memory            | Notes                                         |
| ----------------------------------------- | ----------------- | --------------------------------------------- |
| FabricRuntime object                      | ~1KB              | Lightweight coordinator                       |
| Per-source adapter                        | ~5KB              | Connection state, circuit breaker, last ETags |
| Per-product registration                  | ~2KB              | Config, depends_on, staleness policy          |
| Pipeline traces (20 per product, bounded) | ~50KB per product | `deque(maxlen=20)`                            |
| In-memory cache (dev mode)                | Configurable      | Default: 1000 entries, ~10MB typical          |
| Redis cache (production)                  | External          | Not in-process                                |

For 10 sources and 20 products: ~1.2MB of fabric overhead in-process. Cache is external (Redis).

### Throughput

| Metric                         | Target                         | Bottleneck                    |
| ------------------------------ | ------------------------------ | ----------------------------- |
| Concurrent product reads       | 10,000+ req/s                  | Redis GET throughput          |
| Concurrent pipeline executions | 3 (configurable)               | Semaphore                     |
| Source poll checks             | 1 per poll_interval per source | Network latency               |
| Webhook processing             | 100 per second                 | Validation + pipeline enqueue |

---

## How It Compares to Competitors

### vs Hasura Event Triggers

Hasura fires webhooks on PostgreSQL triggers (per-row). Latency: 100-500ms from INSERT to webhook delivery.

**Fabric approach**: Poll-based for databases (`MAX(updated_at)` every 60s). Slower than Hasura for single-row changes, but simpler — no database trigger setup, no webhook endpoint to deploy. For most use cases (dashboard refresh, not real-time chat), 60s polling is sufficient.

**When the fabric is better**: Handles non-database sources (APIs, files, cloud) that Hasura cannot.

### vs Supabase Realtime

Supabase uses PostgreSQL logical replication (WAL). Latency: <100ms from INSERT to WebSocket push.

**Fabric approach**: Does not use WAL in v1 (deferred to v2). Uses polling instead. Slower for database changes but works across all source types.

**When the fabric is better**: Multi-source composition. Supabase Realtime only works for PostgreSQL tables.

### vs Denodo Smart Cache

Denodo materializes entire views into cache databases. Cache levels: full (materialized view), partial (specific columns), query (specific queries).

**Fabric approach**: Product-level materialization. Simpler than Denodo (one cache level per product mode), but more flexible (product function is arbitrary Python, not SQL views).

**When the fabric is better**: Denodo requires a separate caching database. Fabric uses Redis (already in most stacks). Denodo is Java infrastructure. Fabric is a Python library.

### vs Prefect/Dagster Orchestration

Modern data orchestrators have rich DAG visualization, retry policies, and observability dashboards.

**Fabric approach**: Simpler — no DAG definition needed. Products are functions, dependencies are declared. But no visual DAG editor, no complex retry trees, no multi-step pipeline chains.

**When the fabric is better**: Embedded in the application process. No separate orchestrator infrastructure. For "keep this data fresh" (the common case), the fabric is dramatically simpler than deploying Airflow/Prefect.

---

## The Transformation Summary

| Aspect                  | DataFlow Today                               | DataFlow + Fabric                                      |
| ----------------------- | -------------------------------------------- | ------------------------------------------------------ |
| **Execution model**     | Request-driven                               | Event-driven + request-driven                          |
| **Background tasks**    | 1 (pool monitor)                             | N (pollers, watchers, pipelines, scheduler)            |
| **Task management**     | None                                         | asyncio.TaskGroup (structured concurrency)             |
| **Cache usage**         | Lazy (on first query)                        | Eager (pre-warmed on startup)                          |
| **Cache invalidation**  | TTL-based                                    | Pipeline-driven (on source change)                     |
| **Endpoints**           | Manual (Nexus handlers or Gateway workflows) | Auto-generated from products                           |
| **Health monitoring**   | Database health only                         | Database + sources + products + cache + pipelines      |
| **Concurrency control** | Connection pool                              | Connection pool + pipeline semaphore + leader election |
| **Graceful shutdown**   | Close connections                            | Drain pipelines → release lock → close connections     |

The fabric doesn't replace DataFlow. It extends its execution model from "respond to requests" to "respond to requests AND react to source changes." Everything that exists today continues to work. The new event-driven layer runs alongside.
