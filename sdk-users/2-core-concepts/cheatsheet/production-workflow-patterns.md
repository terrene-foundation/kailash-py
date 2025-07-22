# Production Workflow Patterns - Quick Reference

*Copy-paste patterns for production-ready workflows*

## 🔄 **Resilient API Orchestration**

```python
# Multiple APIs with circuit breakers and fallbacks
workflow = (
    AsyncWorkflowBuilder("resilient_api_workflow")
    .add_pattern(
        AsyncPatterns.retry(
            max_attempts=3,
            backoff_factor=2.0,
            exceptions=[httpx.TimeoutException, httpx.NetworkError]
        )
    )
    .add_pattern(
        AsyncPatterns.circuit_breaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_requests=3
        )
    )
    .add_async_code(
        "fetch_primary_api",
        """
import httpx
async with httpx.AsyncClient(timeout=30) as client:
    response = await client.get("https://api.primary.com/data")
    result = response.json() if response.status_code == 200 else None
""",
        error_handler=ErrorHandler.fallback("fetch_backup_api")
    )
    .add_async_code(
        "fetch_backup_api",
        """
# Fallback to backup API
result = {"source": "backup", "data": "default_data"}
"""
    )
    .build()
)
```

## 📊 **ETL Pipeline with Data Validation**

```python
# Production ETL with quality checks
workflow = (
    AsyncWorkflowBuilder("etl_pipeline")
    .add_node(
        AsyncSQLDatabaseNode,
        "extract_data",
        query="""
            WITH quality_metrics AS (
                SELECT
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT customer_id) as unique_customers,
                    SUM(CASE WHEN email IS NULL THEN 1 ELSE 0 END) as missing_emails
                FROM customers
                WHERE created_at >= NOW() - INTERVAL '1 day'
            )
            SELECT * FROM quality_metrics
        """,
        database_config=db_config
    )
    .add_async_code(
        "validate_quality",
        """
metrics = extract_data['data'][0]
quality_score = 100.0

# Deduct points for data issues
if metrics['missing_emails'] > metrics['total_rows'] * 0.05:
    quality_score -= 20

result = {
    'quality_score': quality_score,
    'proceed': quality_score >= 70,
    'metrics': metrics
}
"""
    )
    .add_node(
        SwitchNode,
        "quality_router",
        condition_path="validate_quality.proceed",
        routes={
            True: "transform_data",
            False: "alert_quality_issues"
        }
    )
    .add_connections([
        ("extract_data", "data", "validate_quality", "extract_data"),
        ("validate_quality", "result", "quality_router", "input")
    ])
    .build()
)
```

## 🚀 **High-Performance Batch Processing**

```python
# Process 10K+ records with memory management
workflow = (
    AsyncWorkflowBuilder("batch_processor")
    .add_async_code(
        "batch_processor",
        """
import gc
import asyncio
from typing import List, Dict

BATCH_SIZE = 100
results = []

# Process in batches to control memory
db = await get_resource("postgres_db")
cache = await get_resource("redis_cache")

async with db.acquire() as conn:
    # Use server-side cursor for large datasets
    async with conn.transaction():
        async for batch in conn.cursor(
            "SELECT * FROM large_table",
            prefetch=BATCH_SIZE
        ):
            # Process batch
            batch_results = []
            for row in batch:
                processed = {
                    'id': row['id'],
                    'processed_value': row['value'] * 2.5,
                    'timestamp': datetime.now()
                }
                batch_results.append(processed)

            # Cache results
            cache_key = f"batch_{len(results)}"
            await cache.setex(
                cache_key,
                3600,
                json.dumps(batch_results)
            )

            results.extend(batch_results)

            # Force garbage collection every 10 batches
            if len(results) % (BATCH_SIZE * 10) == 0:
                gc.collect()

result = {
    'total_processed': len(results),
    'batches': len(results) // BATCH_SIZE,
    'sample': results[:5]
}
"""
    )
    .build()
)
```

## 🔄 **Workflow Checkpointing and Recovery**

```python
# Checkpoint-enabled workflow for long-running processes
checkpoint_config = {
    "storage_backend": "disk",
    "checkpoint_interval": 2,  # Every 2 nodes
    "retention_hours": 24,
    "compress": True
}

workflow = (
    AsyncWorkflowBuilder("recoverable_workflow")
    .with_checkpointing(checkpoint_config)
    .add_async_code(
        "stage_1",
        """
# Long-running stage 1
await asyncio.sleep(5)
result = {"stage": 1, "data": "processed"}
"""
    )
    .add_checkpoint("stage_1_complete")
    .add_async_code(
        "stage_2",
        """
# Stage 2 - might fail
if random.random() < 0.3:  # 30% failure rate
    raise Exception("Simulated failure")
result = {"stage": 2, "data": "processed"}
"""
    )
    .add_checkpoint("stage_2_complete")
    .build()
)

# Recovery pattern
async def run_with_recovery(workflow, runtime, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            # Try to recover from checkpoint
            checkpoint = await runtime.load_latest_checkpoint(workflow.id)
            if checkpoint:
                print(f"Recovering from checkpoint: {checkpoint.name}")
                result = await runtime.execute_workflow(
                    workflow,
                    checkpoint=checkpoint
                )
            else:
                result = await runtime.execute_workflow(workflow)
            return result
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## 📈 **Real-Time Analytics Pipeline**

```python
# Stream processing with aggregations
workflow = (
    AsyncWorkflowBuilder("realtime_analytics")
    .add_pattern(
        AsyncPatterns.rate_limit(
            max_requests=100,
            time_window=60  # 100 requests per minute
        )
    )
    .add_async_code(
        "stream_processor",
        """
# Connect to event stream
events = []
window_size = 60  # 1-minute windows

cache = await get_resource("redis_cache")

# Get current window data
window_key = f"analytics_window_{int(time.time() // window_size)}"
window_data = await cache.get(window_key)
if window_data:
    current_window = json.loads(window_data)
else:
    current_window = {
        "count": 0,
        "sum": 0,
        "max": float('-inf'),
        "min": float('inf')
    }

# Process new events
for event in input_events:
    value = event.get("value", 0)
    current_window["count"] += 1
    current_window["sum"] += value
    current_window["max"] = max(current_window["max"], value)
    current_window["min"] = min(current_window["min"], value)

# Update window in cache
await cache.setex(
    window_key,
    window_size * 2,  # Keep for 2 windows
    json.dumps(current_window)
)

# Calculate metrics
result = {
    "window_start": int(time.time() // window_size) * window_size,
    "metrics": {
        "count": current_window["count"],
        "average": current_window["sum"] / current_window["count"] if current_window["count"] > 0 else 0,
        "max": current_window["max"],
        "min": current_window["min"]
    }
}
"""
    )
    .add_async_code(
        "anomaly_detection",
        """
# Simple anomaly detection using z-score
metrics = stream_processor["metrics"]
historical_avg = 50.0  # Would come from historical data
historical_std = 10.0

z_score = abs(metrics["average"] - historical_avg) / historical_std
is_anomaly = z_score > 3  # 3 standard deviations

result = {
    "is_anomaly": is_anomaly,
    "z_score": z_score,
    "severity": "high" if z_score > 5 else "medium" if z_score > 3 else "low"
}
"""
    )
    .build()
)
```

## 🤖 **ML Pipeline with Feature Engineering**

```python
# Production ML pipeline with caching
workflow = (
    AsyncWorkflowBuilder("ml_pipeline")
    .add_async_code(
        "feature_engineering",
        """
import numpy as np

# Extract features from raw data
features = []
for record in input_data:
    feature_vector = [
        record.get("age", 0) / 100.0,  # Normalize age
        1 if record.get("gender") == "M" else 0,
        len(record.get("purchase_history", [])) / 100.0,
        record.get("total_spent", 0) / 10000.0,
        record.get("days_since_last_purchase", 365) / 365.0
    ]
    features.append(feature_vector)

result = {
    "features": np.array(features).tolist(),
    "shape": (len(features), len(features[0]) if features else 0)
}
"""
    )
    .add_node(
        EmbeddingGeneratorNode,
        "generate_embeddings",
        model="text-embedding-ada-002",
        batch_size=100,
        cache_embeddings=True
    )
    .add_async_code(
        "cluster_customers",
        """
from sklearn.cluster import KMeans
import numpy as np

# Simple k-means clustering
X = np.array(features)
n_clusters = min(5, len(X))  # Max 5 clusters

if len(X) > n_clusters:
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    clusters = kmeans.fit_predict(X)

    result = {
        "clusters": clusters.tolist(),
        "centroids": kmeans.cluster_centers_.tolist(),
        "inertia": kmeans.inertia_
    }
else:
    result = {
        "clusters": list(range(len(X))),
        "message": "Too few samples for clustering"
    }
"""
    )
    .add_async_code(
        "cache_results",
        """
cache = await get_resource("redis_cache")

# Cache clustering results with TTL
cache_key = f"ml_clusters_{datetime.now().strftime('%Y%m%d_%H')}"
await cache.setex(
    cache_key,
    3600,  # 1 hour TTL
    json.dumps({
        "clusters": cluster_customers["clusters"],
        "generated_at": datetime.now().isoformat(),
        "sample_size": len(features)
    })
)

result = {"cached_key": cache_key}
"""
    )
    .build()
)
```

## 📊 **Report Generation with Templates**

```python
# Multi-format report generation
workflow = (
    AsyncWorkflowBuilder("report_generator")
    .add_async_code(
        "gather_data",
        """
# Collect data from multiple sources
db = await get_resource("postgres_db")

async with db.acquire() as conn:
    # KPIs
    kpis = await conn.fetchrow('''
        SELECT
            COUNT(DISTINCT customer_id) as total_customers,
            SUM(revenue) as total_revenue,
            AVG(order_value) as avg_order_value
        FROM orders
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    ''')

    # Top products
    top_products = await conn.fetch('''
        SELECT product_name, SUM(quantity) as units_sold
        FROM order_items
        WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY product_name
        ORDER BY units_sold DESC
        LIMIT 10
    ''')

result = {
    "kpis": dict(kpis),
    "top_products": [dict(row) for row in top_products],
    "report_date": datetime.now().isoformat()
}
"""
    )
    .add_node(
        LLMAgentNode,
        "generate_summary",
        prompt="""Generate an executive summary based on the following data:

KPIs: {kpis}
Top Products: {top_products}

Provide insights and recommendations in 3-5 bullet points.""",
        model="gpt-4",
        temperature=0.3
    )
    .add_async_code(
        "format_report",
        """
# Generate multiple report formats
report_data = {
    "title": "Monthly Business Report",
    "date": gather_data["report_date"],
    "kpis": gather_data["kpis"],
    "products": gather_data["top_products"],
    "summary": generate_summary["content"]
}

# HTML format
html_report = f'''
<html>
<body>
    <h1>{report_data["title"]}</h1>
    <p>Generated on: {report_data["date"]}</p>

    <h2>Key Metrics</h2>
    <ul>
        <li>Total Customers: {report_data["kpis"]["total_customers"]:,}</li>
        <li>Total Revenue: ${report_data["kpis"]["total_revenue"]:,.2f}</li>
        <li>Average Order Value: ${report_data["kpis"]["avg_order_value"]:.2f}</li>
    </ul>

    <h2>Executive Summary</h2>
    <p>{report_data["summary"]}</p>
</body>
</html>
'''

# JSON format for API consumption
json_report = json.dumps(report_data, indent=2)

result = {
    "html": html_report,
    "json": json_report,
    "formats": ["html", "json"]
}
"""
    )
    .build()
)
```
