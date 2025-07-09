# Durable Gateway Guide

*Enterprise-grade gateway with persistence, circuit breakers, and automatic recovery*

## Overview

The Durable Gateway provides enterprise-grade reliability features including request persistence across restarts, automatic deduplication, event sourcing, circuit breaker protection, and connection pool management. These features ensure high availability and fault tolerance for production applications.

**NEW: Redesigned Server Architecture** - This guide now uses the updated `create_gateway()` function with redesigned server classes (`DurableWorkflowServer`) for improved naming and enterprise defaults.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Understanding of enterprise architecture patterns
- Familiarity with reliability engineering concepts

## Core Durability Features

### Durable Gateway Creation

The main gateway with comprehensive durability features using redesigned architecture.

```python
from kailash.servers.gateway import create_gateway
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager
from kailash.middleware.gateway.event_store import EventStore

# Initialize durable gateway with redesigned architecture
gateway = create_gateway(
    title="Production Durable Gateway",
    description="Enterprise gateway with persistence and reliability",
    server_type="durable",  # Uses DurableWorkflowServer

    # Persistence configuration
    checkpoint_manager=CheckpointManager(
        storage_type="tiered",  # memory -> disk -> cloud
        memory_limit_mb=512,
        disk_path="/var/lib/kailash/checkpoints",
        cloud_config={
            "provider": "s3",
            "bucket": "kailash-gateway-state",
            "region": "us-east-1"
        },
        compression_enabled=True,
        gc_interval_hours=24
    ),

    # Event sourcing
    event_store=EventStore(
        storage_path="/var/lib/kailash/events",
        buffer_size=1000,
        flush_interval_seconds=30,
        enable_projections=True
    ),

    # Durability features (enabled by default for durable server)
    enable_durability=True,
    enable_request_persistence=True,
    enable_deduplication=True,
    idempotency_window_minutes=60,

    # Performance settings
    max_workers=50,
    request_timeout_seconds=300,
    graceful_shutdown_timeout=30
)

# Start the gateway
gateway.run(host="0.0.0.0", port=8000)
```

### Request Persistence

Ensure requests survive gateway restarts with automatic checkpointing.

```python
# Configure request persistence
@gateway.route("/api/long-running-process", methods=["POST"])
async def long_running_process(request):
    """Handle long-running process with automatic persistence."""

    # Create checkpoint for request
    checkpoint_id = await gateway.create_checkpoint(
        request_id=request.headers.get("X-Request-ID"),
        data={
            "user_id": request.json.get("user_id"),
            "process_type": request.json.get("type"),
            "started_at": time.time(),
            "parameters": request.json
        }
    )

    try:
        # Process in stages with checkpoints
        results = []

        # Stage 1: Data preparation
        await gateway.update_checkpoint(checkpoint_id, {
            "stage": "data_preparation",
            "progress": 0.1
        })

        data = await prepare_data(request.json)

        # Stage 2: Processing
        await gateway.update_checkpoint(checkpoint_id, {
            "stage": "processing",
            "progress": 0.5,
            "intermediate_data": data.summary
        })

        for i, item in enumerate(data.items):
            result = await process_item(item)
            results.append(result)

            # Update progress every 10 items
            if (i + 1) % 10 == 0:
                await gateway.update_checkpoint(checkpoint_id, {
                    "progress": 0.5 + (0.4 * (i + 1) / len(data.items)),
                    "processed_count": i + 1
                })

        # Stage 3: Finalization
        await gateway.update_checkpoint(checkpoint_id, {
            "stage": "finalization",
            "progress": 0.9
        })

        final_result = await finalize_results(results)

        # Complete and cleanup checkpoint
        await gateway.complete_checkpoint(checkpoint_id, {
            "stage": "completed",
            "progress": 1.0,
            "result": final_result.summary
        })

        return {"success": True, "result": final_result}

    except Exception as e:
        # Mark checkpoint as failed
        await gateway.fail_checkpoint(checkpoint_id, {
            "error": str(e),
            "stage": "failed",
            "retry_count": getattr(request, "retry_count", 0)
        })
        raise

# Resume interrupted requests on startup
@gateway.on_startup
async def resume_interrupted_requests():
    """Resume any interrupted requests from checkpoints."""
    interrupted_checkpoints = await gateway.get_incomplete_checkpoints()

    for checkpoint in interrupted_checkpoints:
        if checkpoint.stage != "failed":
            # Resume from last checkpoint
            asyncio.create_task(resume_request_from_checkpoint(checkpoint))

async def resume_request_from_checkpoint(checkpoint):
    """Resume a request from its last checkpoint."""
    try:
        if checkpoint.stage == "data_preparation":
            # Resume from data preparation
            await continue_from_data_preparation(checkpoint)
        elif checkpoint.stage == "processing":
            # Resume from processing
            await continue_from_processing(checkpoint)
        elif checkpoint.stage == "finalization":
            # Resume from finalization
            await continue_from_finalization(checkpoint)

    except Exception as e:
        await gateway.fail_checkpoint(checkpoint.id, {"resume_error": str(e)})
```

## Request Deduplication

Prevent duplicate processing with intelligent request fingerprinting.

### Automatic Deduplication

```python
from kailash.middleware.gateway.deduplicator import RequestDeduplicator

# Configure deduplication
deduplicator = RequestDeduplicator(
    window_minutes=60,  # Detect duplicates within 1 hour
    max_cache_size=10000,
    storage_backend="redis",  # or "memory", "disk"
    redis_url="redis://localhost:6379/0"
)

gateway.add_middleware(deduplicator)

# Endpoint with automatic deduplication
@gateway.route("/api/payment", methods=["POST"])
async def process_payment(request):
    """Process payment with automatic deduplication."""

    # Deduplication happens automatically based on:
    # - Idempotency key (if provided)
    # - Request fingerprint (method + path + body hash)
    # - Client identification

    payment_data = request.json

    # If this is a duplicate request, return cached result
    # Otherwise, process normally
    result = await payment_processor.charge(
        amount=payment_data["amount"],
        currency=payment_data["currency"],
        payment_method=payment_data["payment_method"],
        customer_id=payment_data["customer_id"]
    )

    return {
        "payment_id": result.id,
        "status": result.status,
        "amount_charged": result.amount,
        "transaction_id": result.transaction_id
    }

# Manual idempotency key handling
@gateway.route("/api/order", methods=["POST"])
async def create_order(request):
    """Create order with manual idempotency control."""

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return {"error": "Idempotency-Key header required"}, 400

    # Check for existing result
    existing_result = await gateway.get_idempotent_result(idempotency_key)
    if existing_result:
        return existing_result

    # Process new order
    order_data = request.json
    order = await order_service.create_order(order_data)

    result = {
        "order_id": order.id,
        "status": order.status,
        "total": order.total,
        "created_at": order.created_at.isoformat()
    }

    # Cache result for future duplicate requests
    await gateway.store_idempotent_result(idempotency_key, result, ttl_minutes=60)

    return result
```

## Circuit Breaker Protection

Prevent cascading failures with automatic circuit breaker patterns.

### Circuit Breaker Configuration

```python
from kailash.core.resilience.circuit_breaker import ConnectionCircuitBreaker

# Configure circuit breakers for external dependencies
database_circuit_breaker = ConnectionCircuitBreaker(
    name="database_circuit_breaker",
    failure_threshold=5,        # Open after 5 failures
    timeout_seconds=60,         # Stay open for 60 seconds
    half_open_max_calls=3,      # Test with 3 calls in half-open state
    rolling_window_seconds=300, # Track failures over 5 minutes
    expected_errors=[
        "connection_timeout",
        "connection_refused",
        "database_unavailable"
    ]
)

api_circuit_breaker = ConnectionCircuitBreaker(
    name="external_api_circuit_breaker",
    failure_threshold=10,
    timeout_seconds=30,
    half_open_max_calls=2,
    rolling_window_seconds=180
)

# Add circuit breakers to gateway
gateway.add_circuit_breaker("database", database_circuit_breaker)
gateway.add_circuit_breaker("external_api", api_circuit_breaker)

# Use circuit breakers in endpoints
@gateway.route("/api/user-profile", methods=["GET"])
async def get_user_profile(request):
    """Get user profile with circuit breaker protection."""
    user_id = request.path_params["user_id"]

    try:
        # Database call with circuit breaker
        async with gateway.circuit_breaker("database"):
            user_data = await database.get_user(user_id)

        # External API call with circuit breaker
        async with gateway.circuit_breaker("external_api"):
            enrichment_data = await external_api.get_user_enrichment(user_id)

        return {
            "user": user_data,
            "enrichment": enrichment_data,
            "source": "live_data"
        }

    except CircuitBreakerOpenError as e:
        # Circuit breaker is open, return cached data
        cached_data = await cache.get_user_profile(user_id)
        if cached_data:
            return {
                "user": cached_data,
                "source": "cached_data",
                "circuit_breaker_open": True,
                "service": e.circuit_breaker_name
            }
        else:
            return {
                "error": "Service temporarily unavailable",
                "circuit_breaker_open": True,
                "service": e.circuit_breaker_name
            }, 503
```

### Circuit Breaker Monitoring

```python
# Monitor circuit breaker health
@gateway.route("/health/circuit-breakers", methods=["GET"])
async def circuit_breaker_health():
    """Get circuit breaker status."""
    status = {}

    for name, cb in gateway.circuit_breakers.items():
        status[name] = {
            "state": cb.state,  # CLOSED, OPEN, HALF_OPEN
            "failure_count": cb.failure_count,
            "failure_rate": cb.failure_rate,
            "last_failure": cb.last_failure_time,
            "next_attempt": cb.next_attempt_time if cb.state == "OPEN" else None
        }

    return {"circuit_breakers": status}

# Manual circuit breaker control
@gateway.route("/admin/circuit-breaker/{name}/reset", methods=["POST"])
async def reset_circuit_breaker(request):
    """Manually reset a circuit breaker."""
    name = request.path_params["name"]

    if name in gateway.circuit_breakers:
        gateway.circuit_breakers[name].reset()
        return {"message": f"Circuit breaker '{name}' reset successfully"}
    else:
        return {"error": f"Circuit breaker '{name}' not found"}, 404
```

## Connection Pool Management

Production-grade connection management with health monitoring.

### WorkflowConnectionPool

```python
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

# Initialize connection pool
connection_pool = WorkflowConnectionPool(
    name="main_connection_pool",

    # Pool configuration
    min_connections=5,
    max_connections=50,
    acquire_timeout=30.0,
    idle_timeout=300.0,
    max_lifetime=3600.0,

    # Health monitoring
    health_check_interval=60.0,
    max_failures_before_refresh=3,
    connection_validation_query="SELECT 1",

    # Performance optimization
    enable_pre_warming=True,
    pre_warm_patterns=[
        {"hour_range": (8, 18), "target_connections": 20},  # Business hours
        {"hour_range": (18, 8), "target_connections": 10}   # Off hours
    ],

    # Metrics and monitoring
    enable_metrics=True,
    metrics_collection_interval=30.0
)

# Database connection factory
async def create_database_connection():
    """Factory function for database connections."""
    return await asyncpg.connect(
        host="localhost",
        port=5432,
        user="app_user",
        password="secure_password",
        database="production_db",
        command_timeout=30
    )

# Register connection factory
connection_pool.register_factory("database", create_database_connection)

# Start connection pool
await connection_pool.start()

# Use connections in endpoints
@gateway.route("/api/analytics", methods=["GET"])
async def get_analytics(request):
    """Get analytics data using connection pool."""

    async with connection_pool.acquire("database") as conn:
        # Connection is automatically managed

        # Complex analytics query
        result = await conn.fetch("""
            SELECT
                date_trunc('day', created_at) as day,
                COUNT(*) as total_orders,
                SUM(amount) as total_revenue,
                AVG(amount) as avg_order_value
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY day
            ORDER BY day
        """)

        analytics_data = [
            {
                "date": row["day"].isoformat(),
                "orders": row["total_orders"],
                "revenue": float(row["total_revenue"]),
                "avg_value": float(row["avg_order_value"])
            }
            for row in result
        ]

    return {"analytics": analytics_data}

# Monitor connection pool health
@gateway.route("/health/connection-pool", methods=["GET"])
async def connection_pool_health():
    """Get connection pool status."""
    metrics = await connection_pool.get_metrics()

    return {
        "pool_status": {
            "active_connections": metrics["active_connections"],
            "idle_connections": metrics["idle_connections"],
            "total_connections": metrics["total_connections"],
            "max_connections": metrics["max_connections"]
        },
        "health_metrics": {
            "successful_acquisitions": metrics["successful_acquisitions"],
            "failed_acquisitions": metrics["failed_acquisitions"],
            "acquisition_timeouts": metrics["acquisition_timeouts"],
            "connection_errors": metrics["connection_errors"]
        },
        "performance_metrics": {
            "avg_acquisition_time_ms": metrics["avg_acquisition_time_ms"],
            "avg_connection_lifetime_seconds": metrics["avg_connection_lifetime_seconds"],
            "connections_created_total": metrics["connections_created_total"],
            "connections_closed_total": metrics["connections_closed_total"]
        }
    }
```

## Event Sourcing and Audit Trail

Complete request lifecycle tracking with event sourcing.

### Event Store Configuration

```python
from kailash.middleware.gateway.event_store import EventStore

# Configure event store
event_store = EventStore(
    storage_backend=None,  # Use default in-memory storage for example

    # Performance settings
    batch_size=1000,
    flush_interval_seconds=30
)

# Add event store to gateway
gateway.add_event_store(event_store)

# Custom event logging
@gateway.route("/api/sensitive-operation", methods=["POST"])
async def sensitive_operation(request):
    """Perform operation with detailed audit trail."""

    # Log request received
    await gateway.event_store.append("request_received", {
        "endpoint": "/api/sensitive-operation",
        "user_id": request.headers.get("X-User-ID"),
        "ip_address": request.client.host,
        "user_agent": request.headers.get("User-Agent"),
        "request_size": len(await request.body()),
        "timestamp": time.time()
    })

    try:
        # Log operation start
        await gateway.event_store.append("operation_started", {
            "operation_type": request.json.get("type"),
            "parameters": request.json,
            "user_id": request.headers.get("X-User-ID")
        })

        # Perform operation
        result = await perform_sensitive_operation(request.json)

        # Log operation success
        await gateway.event_store.append("operation_completed", {
            "operation_type": request.json.get("type"),
            "result_summary": result.summary,
            "user_id": request.headers.get("X-User-ID"),
            "execution_time_ms": result.execution_time
        })

        return {"success": True, "result": result.data}

    except Exception as e:
        # Log operation failure
        await gateway.event_store.append("operation_failed", {
            "operation_type": request.json.get("type"),
            "error": str(e),
            "error_type": type(e).__name__,
            "user_id": request.headers.get("X-User-ID"),
            "stack_trace": traceback.format_exc()
        })

        raise

# Query event history
@gateway.route("/admin/audit-trail", methods=["GET"])
async def get_audit_trail(request):
    """Get audit trail for investigation."""
    user_id = request.query_params.get("user_id")
    start_time = request.query_params.get("start_time")
    end_time = request.query_params.get("end_time")
    event_type = request.query_params.get("event_type")

    events = await event_store.get_events(
        filters={
            "user_id": user_id,
            "event_type": event_type,
            "timestamp_range": (start_time, end_time)
        },
        limit=1000,
        order_by="timestamp"
    )

    return {
        "events": events,
        "total_count": len(events),
        "query_filters": {
            "user_id": user_id,
            "event_type": event_type,
            "start_time": start_time,
            "end_time": end_time
        }
    }
```

## Production Configuration

### Complete Durable Gateway Setup

```python
# Production-ready durable gateway configuration
async def create_production_gateway():
    """Create production-configured durable gateway."""

    # Checkpoint manager with cloud backup
    checkpoint_manager = CheckpointManager(
        storage_type="tiered",
        memory_limit_mb=1024,
        disk_path="/var/lib/kailash/checkpoints",
        cloud_config={
            "provider": "s3",
            "bucket": "production-kailash-state",
            "region": "us-east-1",
            "encryption": True
        },
        compression_enabled=True,
        compression_threshold_mb=10,
        gc_interval_hours=6,
        backup_interval_hours=1
    )

    # Event store with archival
    event_store = EventStore(
        storage_path="/var/lib/kailash/events",
        buffer_size=5000,
        flush_interval_seconds=15,
        max_file_size_mb=500,
        enable_projections=True,
        projection_update_interval=30,
        retention_days=365,
        archive_path="/var/lib/kailash/archived_events",
        compression_enabled=True
    )

    # Request deduplicator with Redis
    deduplicator = RequestDeduplicator(
        window_minutes=120,
        max_cache_size=50000,
        storage_backend="redis",
        redis_url="redis://redis-cluster:6379/1",
        enable_clustering=True
    )

    # Connection pool
    connection_pool = WorkflowConnectionPool(
        name="production_pool",
        min_connections=10,
        max_connections=100,
        acquire_timeout=30.0,
        idle_timeout=600.0,
        max_lifetime=7200.0,
        health_check_interval=30.0,
        enable_pre_warming=True,
        enable_metrics=True
    )

    # Circuit breakers
    circuit_breakers = {
        "database": ConnectionCircuitBreaker(
            name="database_circuit_breaker",
            failure_threshold=5,
            timeout_seconds=60,
            half_open_max_calls=3
        ),
        "external_api": ConnectionCircuitBreaker(
            name="external_api_circuit_breaker",
            failure_threshold=10,
            timeout_seconds=30,
            half_open_max_calls=2
        ),
        "payment_processor": ConnectionCircuitBreaker(
            name="payment_circuit_breaker",
            failure_threshold=3,
            timeout_seconds=120,
            half_open_max_calls=1
        )
    }

    # Initialize gateway
    gateway = DurableAPIGateway(
        name="production_gateway",
        checkpoint_manager=checkpoint_manager,
        event_store=event_store,
        enable_request_persistence=True,
        enable_deduplication=True,
        idempotency_window_minutes=120,
        max_concurrent_requests=5000,
        request_timeout_seconds=300,
        graceful_shutdown_timeout=60,
        enable_metrics=True,
        metrics_namespace="kailash_gateway"
    )

    # Add middleware
    gateway.add_middleware(deduplicator)
    gateway.add_connection_pool(connection_pool)

    # Add circuit breakers
    for name, cb in circuit_breakers.items():
        gateway.add_circuit_breaker(name, cb)

    return gateway

# Start production gateway
if __name__ == "__main__":
    gateway = await create_production_gateway()
    await gateway.start()
```

## Best Practices

### 1. Checkpoint Strategy

```python
# Optimize checkpoint frequency based on operation criticality
class CheckpointStrategy:
    def __init__(self):
        self.strategies = {
            "financial": {"frequency": "every_step", "retention_days": 365},
            "analytics": {"frequency": "every_10_steps", "retention_days": 30},
            "reporting": {"frequency": "stage_boundaries", "retention_days": 90}
        }

    def get_checkpoint_config(self, operation_type):
        return self.strategies.get(operation_type, {
            "frequency": "stage_boundaries",
            "retention_days": 30
        })
```

### 2. Error Recovery

```python
# Implement comprehensive error recovery
async def error_recovery_handler(checkpoint, error):
    """Handle errors with intelligent recovery."""

    if error.is_retryable():
        if checkpoint.retry_count < 3:
            # Exponential backoff retry
            delay = 2 ** checkpoint.retry_count
            await asyncio.sleep(delay)
            return "retry"
        else:
            return "failed"
    else:
        # Non-retryable error
        return "failed"
```

### 3. Performance Monitoring

```python
# Monitor gateway performance
@gateway.middleware("performance_monitor")
async def performance_monitor(request, call_next):
    """Monitor request performance."""
    start_time = time.time()

    try:
        response = await call_next(request)
        success = True
    except Exception as e:
        success = False
        raise
    finally:
        duration = time.time() - start_time

        await gateway.record_metric("request_duration", duration, {
            "endpoint": request.url.path,
            "method": request.method,
            "success": success
        })
```

## Related Guides

**Prerequisites:**
- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Server setup
- [Enterprise Security Nodes Guide](28-enterprise-security-nodes-guide.md) - Security features

**Next Steps:**
- [Edge Computing Guide](30-edge-computing-guide.md) - Edge deployment
- [Cyclic Workflows Guide](31-cyclic-workflows-guide.md) - Workflow cycles

---

**Build production-ready gateways with enterprise durability and fault tolerance!**
