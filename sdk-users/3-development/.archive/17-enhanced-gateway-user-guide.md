# Enhanced Gateway User Guide

## Quick Start

The Enhanced Gateway makes it easy to build production workflows that use databases, APIs, and caches without worrying about connection management or credentials.

### 1. Basic Setup

```python
from kailash.api.gateway import EnhancedDurableAPIGateway, WorkflowRequest
from kailash.workflow import AsyncWorkflowBuilder

# Create gateway
gateway = EnhancedDurableAPIGateway()

# Build a simple workflow
workflow = (
    AsyncWorkflowBuilder("hello_db")
    .add_async_code("query", """
db = await get_resource("mydb")
async with db.acquire() as conn:
    result = await conn.fetchval("SELECT 'Hello from database!'")
    result = {"message": result}
""", required_resources=["mydb"])
    .build()
)

# Register it
gateway.register_workflow("hello_db", workflow)

# Execute with database resource
request = WorkflowRequest(
    resources={
        "mydb": {
            "type": "database",
            "config": {
                "host": "localhost",
                "port": 5432,
                "database": "test"
            },
            "credentials_ref": "db_creds"
        }
    }
)

response = await gateway.execute_workflow("hello_db", request)
print(response.result["query"]["message"])  # "Hello from database!"
```

### 2. Using the Client SDK

```python
from kailash.client import KailashClient

async with KailashClient("http://localhost:8000") as client:
    # Execute workflow with resource helpers
    result = await client.execute_workflow(
        "hello_db",
        parameters={},
        resources={
            "mydb": client.database(
                host="localhost",
                database="test",
                credentials_ref="db_creds"
            )
        }
    )

    print(result.result["query"]["message"])
```

## Common Use Cases

### 1. Data Pipeline (ETL)

Extract data from database, transform it, and load to cache:

```python
# Build ETL workflow
etl_workflow = (
    AsyncWorkflowBuilder("user_etl")
    # Extract from database
    .add_async_code("extract", """
db = await get_resource("source_db")
async with db.acquire() as conn:
    users = await conn.fetch('''
        SELECT id, name, email, created_at
        FROM users
        WHERE created_at > CURRENT_DATE - INTERVAL '7 days'
    ''')
    result = {"users": [dict(u) for u in users], "count": len(users)}
""", required_resources=["source_db"])

    # Transform data
    .add_async_code("transform", """
import json
from datetime import datetime

transformed = []
for user in users:
    transformed.append({
        "id": user["id"],
        "display_name": user["name"].title(),
        "email_domain": user["email"].split("@")[1],
        "days_active": (datetime.now() - user["created_at"]).days
    })

result = {"transformed_users": transformed}
""")

    # Load to cache
    .add_async_code("load", """
cache = await get_resource("cache")
import json

# Cache individual users
loaded = 0
for user in transformed_users:
    key = f"user:{user['id']}:profile"
    await cache.setex(key, 3600, json.dumps(user))
    loaded += 1

# Cache summary
summary = {
    "total_users": len(transformed_users),
    "domains": list(set(u["email_domain"] for u in transformed_users)),
    "updated_at": time.time()
}
await cache.setex("users:summary", 3600, json.dumps(summary))

result = {"loaded": loaded, "cache_keys": loaded + 1}
""", required_resources=["cache"])

    # Connect the pipeline
    .add_connection("extract", "users", "transform", "users")
    .add_connection("transform", "transformed_users", "load", "transformed_users")
    .build()
)

# Register workflow
gateway.register_workflow("user_etl", etl_workflow)

# Execute with resources
response = await gateway.execute_workflow(
    "user_etl",
    WorkflowRequest(
        resources={
            "source_db": {
                "type": "database",
                "config": {"host": "db.prod.com", "database": "users"},
                "credentials_ref": "prod_db"
            },
            "cache": {
                "type": "cache",
                "config": {"host": "cache.prod.com", "port": 6379}
            }
        }
    )
)

print(f"Loaded {response.result['load']['loaded']} users to cache")
```

### 2. API Aggregation

Fetch data from multiple APIs and combine results:

```python
# Build API aggregator
api_workflow = (
    AsyncWorkflowBuilder("dashboard_data")
    .add_async_code("fetch_all", """
http = await get_resource("http")
import asyncio

# Fetch from multiple endpoints concurrently
async def fetch_json(endpoint):
    try:
        response = await http.get(f"https://api.example.com{endpoint}")
        return await response.json()
    except Exception as e:
        return {"error": str(e), "endpoint": endpoint}

# Parallel fetching
results = await asyncio.gather(
    fetch_json("/users/stats"),
    fetch_json("/orders/today"),
    fetch_json("/products/popular"),
    fetch_json("/metrics/revenue")
)

result = {
    "user_stats": results[0],
    "today_orders": results[1],
    "popular_products": results[2],
    "revenue": results[3],
    "fetched_at": time.time()
}
""", required_resources=["http"])

    .add_async_code("build_dashboard", """
# Combine data for dashboard
dashboard = {
    "timestamp": time.time(),
    "metrics": {
        "active_users": user_stats.get("active_count", 0),
        "orders_today": today_orders.get("count", 0),
        "revenue_today": revenue.get("today", 0),
        "top_product": popular_products[0]["name"] if popular_products else "N/A"
    },
    "charts": {
        "user_growth": user_stats.get("growth_chart", []),
        "revenue_trend": revenue.get("trend", [])
    }
}

# Cache for 1 minute
cache = await get_resource("cache")
import json
await cache.setex("dashboard:latest", 60, json.dumps(dashboard))

result = {"dashboard": dashboard}
""", required_resources=["cache"])

    .add_connection("fetch_all", None, "build_dashboard", None)
    .build()
)

# Execute periodically
while True:
    response = await gateway.execute_workflow(
        "dashboard_data",
        WorkflowRequest(
            resources={
                "http": {
                    "type": "http_client",
                    "config": {"timeout": 10},
                    "credentials_ref": "api_key"
                },
                "cache": {
                    "type": "cache",
                    "config": {"host": "localhost", "port": 6379}
                }
            }
        )
    )

    if response.status == "completed":
        print(f"Dashboard updated: {response.result['build_dashboard']['dashboard']['metrics']}")

    await asyncio.sleep(60)  # Update every minute
```

### 3. Real-time Data Processing

Process streaming data with database lookups:

```python
# Build stream processor
stream_workflow = (
    AsyncWorkflowBuilder("process_events")
    .add_async_code("process_batch", """
db = await get_resource("db")
cache = await get_resource("cache")
import json

processed = []
for event in events:
    # Enrich event with database lookup
    async with db.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT name, tier FROM users WHERE id = $1",
            event["user_id"]
        )

    if user:
        # Check cache for user preferences
        prefs_key = f"user:{event['user_id']}:prefs"
        prefs_data = await cache.get(prefs_key)
        prefs = json.loads(prefs_data) if prefs_data else {}

        # Process based on user tier
        if user["tier"] == "premium":
            priority = "high"
            ttl = 7200  # 2 hours
        else:
            priority = "normal"
            ttl = 3600  # 1 hour

        enriched = {
            **event,
            "user_name": user["name"],
            "user_tier": user["tier"],
            "priority": priority,
            "preferences": prefs,
            "processed_at": time.time()
        }

        # Cache processed event
        event_key = f"event:{event['id']}:processed"
        await cache.setex(event_key, ttl, json.dumps(enriched))

        processed.append(enriched)

result = {
    "processed": processed,
    "count": len(processed),
    "high_priority": len([e for e in processed if e["priority"] == "high"])
}
""", required_resources=["db", "cache"])
    .build()
)

# Process event batches
async def process_event_stream(gateway, event_source):
    async for batch in event_source:
        request = WorkflowRequest(
            parameters={"events": batch},
            resources={
                "db": {"type": "database", "config": {...}},
                "cache": {"type": "cache", "config": {...}}
            }
        )

        response = await gateway.execute_workflow("process_events", request)

        if response.status == "completed":
            result = response.result["process_batch"]
            print(f"Processed {result['count']} events, {result['high_priority']} high priority")
```

### 4. Multi-Step Data Validation

Validate data across multiple sources:

```python
validation_workflow = (
    AsyncWorkflowBuilder("validate_order")
    # Check inventory
    .add_async_code("check_inventory", """
db = await get_resource("inventory_db")
async with db.acquire() as conn:
    inventory = await conn.fetch('''
        SELECT product_id, available_quantity
        FROM inventory
        WHERE product_id = ANY($1)
    ''', [item["product_id"] for item in order_items])

    inventory_map = {row["product_id"]: row["available_quantity"] for row in inventory}

    issues = []
    for item in order_items:
        available = inventory_map.get(item["product_id"], 0)
        if available < item["quantity"]:
            issues.append({
                "product_id": item["product_id"],
                "requested": item["quantity"],
                "available": available
            })

    result = {
        "valid": len(issues) == 0,
        "issues": issues
    }
""", required_resources=["inventory_db"])

    # Check customer credit
    .add_async_code("check_credit", """
if not valid:  # Skip if inventory check failed
    result = {"credit_check": "skipped", "reason": "inventory_issues"}
else:
    api = await get_resource("credit_api")

    # Call credit check API
    response = await api.post("/credit/check", json={
        "customer_id": customer_id,
        "amount": order_total
    })

    credit_result = await response.json()

    result = {
        "approved": credit_result["approved"],
        "credit_limit": credit_result["limit"],
        "available_credit": credit_result["available"]
    }
""", required_resources=["credit_api"])

    # Final validation
    .add_async_code("final_validation", """
validation_result = {
    "order_id": order_id,
    "valid": valid and approved,
    "checks": {
        "inventory": {"passed": valid, "issues": issues if not valid else []},
        "credit": {"passed": approved, "limit": credit_limit if 'credit_limit' in locals() else None}
    },
    "timestamp": time.time()
}

# Cache validation result
cache = await get_resource("cache")
import json
await cache.setex(
    f"order:{order_id}:validation",
    300,  # 5 minutes
    json.dumps(validation_result)
)

result = validation_result
""", required_resources=["cache"])

    # Connect steps
    .add_connection("check_inventory", None, "check_credit", None)
    .add_connection("check_credit", None, "final_validation", None)
    .build()
)
```

## Resource Patterns

### 1. Database Patterns

```python
# Connection pooling
db_resource = {
    "type": "database",
    "config": {
        "host": "db.example.com",
        "port": 5432,
        "database": "app",
        "min_size": 10,    # Minimum connections
        "max_size": 50,    # Maximum connections
        "timeout": 30,     # Query timeout
        "command_timeout": 60
    },
    "credentials_ref": "db_creds"
}

# Read replica for queries
read_db = {
    "type": "database",
    "config": {
        "host": "read-replica.example.com",
        "port": 5432,
        "database": "app",
        "server_settings": {
            "application_name": "kailash_reader"
        }
    },
    "credentials_ref": "db_creds_readonly"
}

# Using in workflow
.add_async_code("read_heavy_operation", """
# Use read replica for queries
read_db = await get_resource("read_db")
async with read_db.acquire() as conn:
    # Long running analytical query
    data = await conn.fetch('''
        SELECT category, COUNT(*), SUM(amount)
        FROM transactions
        WHERE created_at > CURRENT_DATE - INTERVAL '30 days'
        GROUP BY category
    ''')

# Use primary for writes
write_db = await get_resource("write_db")
async with write_db.acquire() as conn:
    # Insert summary
    await conn.execute('''
        INSERT INTO summaries (date, data)
        VALUES (CURRENT_DATE, $1)
    ''', json.dumps([dict(row) for row in data]))
""", required_resources=["read_db", "write_db"])
```

### 2. HTTP Client Patterns

```python
# Configured HTTP client
api_resource = {
    "type": "http_client",
    "config": {
        "base_url": "https://api.example.com",
        "timeout": 30,
        "headers": {
            "User-Agent": "KailashWorkflow/1.0",
            "Accept": "application/json"
        },
        "connection_limit": 100,
        "keepalive_timeout": 30
    },
    "credentials_ref": "api_token"  # Adds Authorization header
}

# Rate-limited client
.add_async_code("rate_limited_calls", """
api = await get_resource("api")
import asyncio

# Implement rate limiting
rate_limit = 10  # requests per second
interval = 1.0 / rate_limit

results = []
for item in items:
    start = time.time()

    # Make API call
    response = await api.get(f"/items/{item['id']}")
    data = await response.json()
    results.append(data)

    # Rate limit
    elapsed = time.time() - start
    if elapsed < interval:
        await asyncio.sleep(interval - elapsed)

result = {"processed": results}
""", required_resources=["api"])
```

### 3. Cache Patterns

```python
# Cache with namespacing
cache_resource = {
    "type": "cache",
    "config": {
        "host": "cache.example.com",
        "port": 6379,
        "db": 0,  # Use different DBs for isolation
        "decode_responses": True  # Auto-decode strings
    }
}

# Caching strategies
.add_async_code("smart_caching", """
cache = await get_resource("cache")
import json

# Check cache first
cache_key = f"report:{report_type}:{date}"
cached = await cache.get(cache_key)

if cached:
    report = json.loads(cached)
    report["from_cache"] = True
else:
    # Generate expensive report
    db = await get_resource("db")
    async with db.acquire() as conn:
        data = await conn.fetch(expensive_query)

    report = process_report_data(data)
    report["from_cache"] = False

    # Cache with appropriate TTL
    if report_type == "daily":
        ttl = 3600  # 1 hour
    elif report_type == "monthly":
        ttl = 86400  # 24 hours
    else:
        ttl = 300  # 5 minutes

    await cache.setex(cache_key, ttl, json.dumps(report))

result = report
""", required_resources=["cache", "db"])
```

## Security Best Practices

### 1. Credential Management

```python
# Store secrets securely
secret_manager = gateway.secret_manager

# Store different credential types
await secret_manager.store_secret(
    "db_creds",
    {"user": "app_user", "password": "secure_password"},
    encrypt=True
)

await secret_manager.store_secret(
    "api_keys",
    {
        "stripe": "sk_live_...",
        "sendgrid": "SG....",
        "twilio": "AC..."
    },
    encrypt=True
)

# Reference in resources
resources = {
    "payment_api": {
        "type": "http_client",
        "config": {"base_url": "https://api.stripe.com"},
        "credentials_ref": "api_keys"  # Gateway extracts 'stripe' key
    }
}
```

### 2. Input Validation

```python
.add_async_code("validate_inputs", """
# Validate user inputs
if not isinstance(user_id, int) or user_id <= 0:
    raise ValueError("Invalid user_id")

if not email or "@" not in email:
    raise ValueError("Invalid email")

# Sanitize for SQL (though parameterized queries are better)
safe_status = status if status in ["active", "pending", "inactive"] else "pending"

# Use parameterized queries
db = await get_resource("db")
async with db.acquire() as conn:
    user = await conn.fetchrow(
        "SELECT * FROM users WHERE id = $1 AND email = $2",
        user_id, email  # Safe from SQL injection
    )
""")
```

### 3. Resource Isolation

```python
# Use separate resources for different security contexts
resources = {
    "public_db": {
        "type": "database",
        "config": {"database": "public_data"},
        "credentials_ref": "public_db_creds"  # Read-only user
    },
    "admin_db": {
        "type": "database",
        "config": {"database": "admin_data"},
        "credentials_ref": "admin_db_creds"  # Admin user
    }
}

# Workflow uses appropriate resource
.add_async_code("public_query", """
# Only has access to public database
db = await get_resource("public_db")
# Cannot access admin_db here
""", required_resources=["public_db"])  # Explicitly limit access
```

## Error Handling

### 1. Graceful Degradation

```python
.add_async_code("fault_tolerant_processing", """
results = []
errors = []

for item in items:
    try:
        # Try primary processing
        db = await get_resource("db")
        async with db.acquire() as conn:
            processed = await conn.fetchrow(
                "SELECT * FROM process_item($1)",
                item["id"]
            )
        results.append({"id": item["id"], "status": "success", "data": dict(processed)})

    except asyncpg.PostgresError as e:
        # Database error - try cache fallback
        try:
            cache = await get_resource("cache")
            cached = await cache.get(f"item:{item['id']}")
            if cached:
                results.append({"id": item["id"], "status": "cached", "data": json.loads(cached)})
            else:
                errors.append({"id": item["id"], "error": "db_error", "message": str(e)})
        except Exception as cache_error:
            errors.append({"id": item["id"], "error": "total_failure", "message": str(cache_error)})

    except Exception as e:
        errors.append({"id": item["id"], "error": "unknown", "message": str(e)})

result = {
    "success_count": len(results),
    "error_count": len(errors),
    "results": results,
    "errors": errors
}
""", required_resources=["db", "cache"])
```

### 2. Retry Logic

```python
.add_async_code("retry_with_backoff", """
import asyncio

async def call_with_retry(func, max_retries=3, backoff=1.0):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = backoff * (2 ** attempt)  # Exponential backoff
            await asyncio.sleep(wait_time)

# Use with API calls
api = await get_resource("flaky_api")

async def make_call():
    response = await api.post("/process", json={"data": input_data})
    return await response.json()

try:
    result = await call_with_retry(make_call)
    result = {"status": "success", "data": result}
except Exception as e:
    result = {"status": "failed", "error": str(e)}
""", required_resources=["flaky_api"])
```

## Performance Tips

### 1. Batch Processing

```python
.add_async_code("batch_process", """
db = await get_resource("db")

# Process in batches instead of one-by-one
batch_size = 100
results = []

for i in range(0, len(items), batch_size):
    batch = items[i:i + batch_size]

    async with db.acquire() as conn:
        # Bulk insert
        await conn.executemany(
            "INSERT INTO processed (id, data) VALUES ($1, $2)",
            [(item["id"], json.dumps(item)) for item in batch]
        )

        # Bulk fetch
        ids = [item["id"] for item in batch]
        rows = await conn.fetch(
            "SELECT * FROM results WHERE id = ANY($1)",
            ids
        )
        results.extend([dict(row) for row in rows])

result = {"processed": len(results), "batches": (len(items) + batch_size - 1) // batch_size}
""")
```

### 2. Concurrent Operations

```python
.add_async_code("concurrent_processing", """
import asyncio

# Limit concurrency to avoid overwhelming resources
semaphore = asyncio.Semaphore(10)

async def process_one(item):
    async with semaphore:
        # Each gets its own connection from pool
        db = await get_resource("db")
        async with db.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM process_item($1)",
                item["id"]
            )
        return dict(result)

# Process all concurrently
results = await asyncio.gather(
    *[process_one(item) for item in items],
    return_exceptions=True
)

# Handle any errors
success = [r for r in results if not isinstance(r, Exception)]
errors = [r for r in results if isinstance(r, Exception)]

result = {
    "success": success,
    "errors": [str(e) for e in errors],
    "total": len(items)
}
""", required_resources=["db"])
```

### 3. Caching Strategy

```python
.add_async_code("tiered_caching", """
cache = await get_resource("cache")
db = await get_resource("db")

# Try L1 cache (local memory)
if hasattr(workflow_context, "_cache"):
    local_cache = workflow_context._cache
else:
    local_cache = workflow_context._cache = {}

cache_key = f"data:{data_id}"

# Check local cache first
if cache_key in local_cache:
    result = local_cache[cache_key]
    result["cache_hit"] = "L1"
else:
    # Try Redis cache
    cached = await cache.get(cache_key)
    if cached:
        result = json.loads(cached)
        result["cache_hit"] = "L2"
        local_cache[cache_key] = result  # Populate L1
    else:
        # Hit database
        async with db.acquire() as conn:
            data = await conn.fetchrow(
                "SELECT * FROM data WHERE id = $1",
                data_id
            )

        if data:
            result = dict(data)
            result["cache_hit"] = "miss"

            # Cache in both layers
            await cache.setex(cache_key, 3600, json.dumps(result))
            local_cache[cache_key] = result
        else:
            result = {"error": "not_found"}
""", required_resources=["cache", "db"])
```

## Monitoring and Debugging

### 1. Workflow Metrics

```python
.add_async_code("instrumented_step", """
import time
start_time = time.time()
step_metrics = {
    "start_time": start_time,
    "item_count": len(items)
}

try:
    # Do processing
    processed = await process_items(items)

    step_metrics.update({
        "success": True,
        "processed_count": len(processed),
        "duration": time.time() - start_time,
        "avg_time_per_item": (time.time() - start_time) / len(items) if items else 0
    })

except Exception as e:
    step_metrics.update({
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "duration": time.time() - start_time
    })
    raise

finally:
    # Log metrics
    logger.info(f"Step metrics: {json.dumps(step_metrics)}")

    # Store in cache for monitoring
    cache = await get_resource("cache")
    await cache.lpush(
        "workflow:metrics",
        json.dumps({
            "workflow": workflow_name,
            "step": "instrumented_step",
            "metrics": step_metrics,
            "timestamp": time.time()
        })
    )
    await cache.ltrim("workflow:metrics", 0, 1000)  # Keep last 1000

result = {"processed": processed, "metrics": step_metrics}
""")
```

### 2. Debug Mode

```python
# Enable debug mode for workflow
debug_workflow = (
    AsyncWorkflowBuilder("debug_example")
    .add_async_code("debug_step", """
# Check if debug mode is enabled
debug = context.get("debug", False)

if debug:
    # Log all inputs
    logger.debug(f"Inputs: {json.dumps(locals())}")

    # Log resource info
    db = await get_resource("db")
    logger.debug(f"DB pool size: {db.size}")
    logger.debug(f"DB pool free: {db.freesize}")

# Normal processing
result = await process_data()

if debug:
    # Log outputs
    logger.debug(f"Result: {json.dumps(result)}")

    # Add debug info to result
    result["_debug"] = {
        "execution_time": time.time() - start_time,
        "resource_stats": {
            "db_pool_size": db.size,
            "db_pool_free": db.freesize
        }
    }

return result
""")
    .build()
)

# Execute with debug enabled
response = await gateway.execute_workflow(
    "debug_example",
    WorkflowRequest(
        context={"debug": True},
        resources={...}
    )
)
```

## Advanced Examples

### 1. Event Sourcing Pattern

```python
event_workflow = (
    AsyncWorkflowBuilder("event_processor")
    .add_async_code("store_event", """
db = await get_resource("event_store")
import uuid

event_id = str(uuid.uuid4())
async with db.acquire() as conn:
    # Store event
    await conn.execute('''
        INSERT INTO events (id, aggregate_id, event_type, payload, created_at)
        VALUES ($1, $2, $3, $4, NOW())
    ''', event_id, aggregate_id, event_type, json.dumps(payload))

    # Update aggregate state
    await conn.execute('''
        INSERT INTO aggregate_states (id, state, version, updated_at)
        VALUES ($1, $2, 1, NOW())
        ON CONFLICT (id) DO UPDATE
        SET state = $2,
            version = aggregate_states.version + 1,
            updated_at = NOW()
    ''', aggregate_id, json.dumps(new_state))

result = {"event_id": event_id, "version": version + 1}
""", required_resources=["event_store"])
    .build()
)
```

### 2. Saga Pattern

```python
saga_workflow = (
    AsyncWorkflowBuilder("order_saga")
    # Start saga
    .add_async_code("reserve_inventory", """
db = await get_resource("inventory_db")
async with db.acquire() as conn:
    # Try to reserve inventory
    reserved = await conn.fetch('''
        UPDATE inventory
        SET reserved = reserved + $2
        WHERE product_id = $1 AND available >= $2
        RETURNING product_id
    ''', product_id, quantity)

    if not reserved:
        raise Exception("Insufficient inventory")

    result = {"reserved": True, "product_id": product_id}
""", required_resources=["inventory_db"])

    # Charge payment
    .add_async_code("charge_payment", """
if not reserved:
    result = {"skipped": True}
else:
    api = await get_resource("payment_api")
    response = await api.post("/charge", json={
        "customer": customer_id,
        "amount": amount,
        "idempotency_key": f"order_{order_id}"
    })

    charge = await response.json()
    if charge["status"] != "succeeded":
        # Compensate - unreserve inventory
        db = await get_resource("inventory_db")
        async with db.acquire() as conn:
            await conn.execute('''
                UPDATE inventory
                SET reserved = reserved - $2
                WHERE product_id = $1
            ''', product_id, quantity)

        raise Exception(f"Payment failed: {charge['error']}")

    result = {"charge_id": charge["id"], "paid": True}
""", required_resources=["payment_api", "inventory_db"])

    # Finalize order
    .add_async_code("create_order", """
if paid:
    db = await get_resource("order_db")
    async with db.acquire() as conn:
        order = await conn.fetchrow('''
            INSERT INTO orders (id, customer_id, product_id, quantity, charge_id, status)
            VALUES ($1, $2, $3, $4, $5, 'confirmed')
            RETURNING *
        ''', order_id, customer_id, product_id, quantity, charge_id)

    # Update inventory
    inv_db = await get_resource("inventory_db")
    async with inv_db.acquire() as conn:
        await conn.execute('''
            UPDATE inventory
            SET reserved = reserved - $2,
                available = available - $2
            WHERE product_id = $1
        ''', product_id, quantity)

    result = {"order": dict(order), "status": "completed"}
else:
    result = {"status": "failed", "reason": "payment_failed"}
""", required_resources=["order_db", "inventory_db"])

    .build()
)
```

## Troubleshooting

### Common Issues and Solutions

1. **"Resource not found" error**
   - Check resource name matches between workflow and request
   - Verify resource is included in WorkflowRequest
   - Ensure workflow has resource in `required_resources`

2. **"Connection pool exhausted"**
   - Increase pool size in resource config
   - Ensure using `async with` for connections
   - Check for connection leaks in code

3. **"Secret not found"**
   - Verify secret was stored with correct name
   - Check secret hasn't expired
   - Ensure using correct credentials_ref

4. **Slow workflow execution**
   - Use concurrent operations where possible
   - Implement caching for repeated queries
   - Check for N+1 query problems
   - Monitor resource pool usage

5. **Workflow timeouts**
   - Increase timeout in workflow metadata
   - Break large workflows into smaller pieces
   - Use batch processing for large datasets
   - Check for blocking operations

### Debug Checklist

- [ ] Enable debug logging for gateway
- [ ] Check workflow is registered correctly
- [ ] Verify all resources are defined
- [ ] Ensure credentials are stored
- [ ] Check network connectivity to resources
- [ ] Monitor resource pool statistics
- [ ] Review workflow execution logs
- [ ] Test resources independently
- [ ] Verify input data format
- [ ] Check error handling coverage

## Best Practices Summary

1. **Always use resource injection** - Never hardcode connections
2. **Handle errors gracefully** - Plan for partial failures
3. **Cache strategically** - Reduce database load
4. **Process in batches** - More efficient than one-by-one
5. **Use connection pools** - Reuse connections
6. **Secure credentials** - Use secret manager
7. **Monitor performance** - Add metrics and logging
8. **Test thoroughly** - Unit, integration, and load tests
9. **Document workflows** - Clear descriptions and requirements
10. **Version carefully** - Maintain backward compatibility
