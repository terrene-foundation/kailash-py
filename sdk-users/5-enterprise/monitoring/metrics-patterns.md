# Metrics & Instrumentation Patterns

*Comprehensive guide to metrics collection and instrumentation*

## 📊 Metrics Types & Usage

### Counter Metrics
Cumulative values that only increase.

```python
from kailash.monitoring import Counter

# Request counter
request_counter = Counter(
    name="http_requests_total",
    description="Total HTTP requests",
    labels=["method", "endpoint", "status"]
)

# Increment counter
request_counter.labels(method="GET", endpoint="/api/users", status="200").inc()

# In workflow
workflow.add_node("PythonCodeNode", "counter_node", {})
errors_encountered = Counter("errors_total", labels=["error_type"])

for item in data:
    try:
        process_item(item)
        items_processed.inc()
    except ValidationError:
        errors_encountered.labels(error_type="validation").inc()
    except Exception as e:
        errors_encountered.labels(error_type="unknown").inc()

result = {"processed": items_processed.value}
''',
    input_types={"data": list}
))

```

### Gauge Metrics
Values that can go up or down.

```python
from kailash.monitoring import Gauge

# Current connections gauge
active_connections = Gauge(
    name="active_connections",
    description="Number of active connections"
)

# Queue depth gauge
queue_depth = Gauge(
    name="queue_depth",
    description="Current queue depth",
    labels=["queue_name"]
)

# In workflow
workflow.add_node("PythonCodeNode", "gauge_monitor", {})
cpu_usage = Gauge("cpu_usage_percent")
active_workers = Gauge("active_workers")

# Update gauges
import psutil
process = psutil.Process()

memory_usage.set(process.memory_info().rss)
cpu_usage.set(process.cpu_percent())
active_workers.set(get_active_worker_count())

# Track queue depths
for queue_name, queue in queues.items():
    queue_depth.labels(queue_name=queue_name).set(queue.qsize())

result = {
    "memory_mb": memory_usage.value / 1024 / 1024,
    "cpu_percent": cpu_usage.value
}
''',
    input_types={"queues": dict}
))

```

### Histogram Metrics
Track distributions of values.

```python
from kailash.monitoring import Histogram

# Response time histogram
response_time = Histogram(
    name="http_response_time_seconds",
    description="HTTP response times",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    labels=["endpoint"]
)

# In workflow
workflow.add_node("PythonCodeNode", "histogram_timer", {})

# Record size histogram
item_size = Histogram(
    "item_size_bytes",
    buckets=[100, 1000, 10000, 100000, 1000000]
)

results = []
for item in data:
    # Time the processing
    start = time.time()
    processed = process_item(item)
    duration = time.time() - start

    # Record metrics
    processing_time.observe(duration)
    item_size.observe(len(str(processed)))

    results.append(processed)

result = {
    "processed": results,
    "avg_time": processing_time.sum / processing_time.count,
    "p95_time": processing_time.quantile(0.95)
}
''',
    input_types={"data": list}
))

```

### Summary Metrics
Similar to histograms but calculate quantiles.

```python
from kailash.monitoring import Summary

# Request latency summary
latency_summary = Summary(
    name="request_latency_seconds",
    description="Request latency summary",
    max_age=600,  # 10 minute sliding window
    age_buckets=5,
    labels=["service"]
)

# Usage
with latency_summary.labels(service="api").time():
    # Code to measure
    response = make_api_call()

```

## 🎯 Instrumentation Patterns

### Method Instrumentation
```python
from kailash.monitoring import instrument

@instrument.counter("function_calls", labels=["function"])
@instrument.histogram("function_duration", labels=["function"])
def process_data(data):
    """Automatically instrumented function."""
    # Processing logic
    return processed_data

# Class instrumentation
@instrument.all_methods
class DataProcessor:
    @instrument.gauge("active_processors")
    def __init__(self):
        self.active = True

    @instrument.timer("processing_time")
    def process(self, data):
        return self._process_internal(data)

```

### Workflow Instrumentation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.monitoring import WorkflowMetrics

# Automatic workflow metrics
workflow = WorkflowBuilder()
runtime = LocalRuntime(enable_monitoring=True)

workflow.enable_metrics(
    export_interval=60,
    include_node_metrics=True,
    include_connection_metrics=True,
    include_resource_metrics=True
)

# Custom workflow metrics
workflow.add_metric(
    name="business_value_processed",
    type="counter",
    description="Total business value processed",
    unit="dollars",
    labels=["product_category", "region"]
)

# Node-level metrics
workflow.add_node("PythonCodeNode", "instrumented_processor", {})
processing_time = Histogram("node_processing_seconds", buckets=[0.1, 0.5, 1.0, 5.0])
active_tasks = Gauge("active_tasks_current")

# Process with metrics
start_time = time.time()
active_tasks.inc()

try:
    for item in data:
        process_item(item)
        processing_counter.labels(node_id="instrumented_processor").inc()

    duration = time.time() - start_time
    processing_time.observe(duration)

finally:
    active_tasks.dec()

result = {"processed": len(data), "duration": duration}
''',
    input_types={"data": list}
))

```

### Database Instrumentation
```python
from kailash.nodes.database import InstrumentedDatabaseNode

workflow = WorkflowBuilder()

workflow.add_node("InstrumentedDatabaseNode", "instrumented_db", {}))

# Custom database metrics
workflow.add_node("PythonCodeNode", "db_metrics_collector", {})
db_connections_total = Counter("db_connections_total")
query_duration = Histogram(
    "db_query_duration_seconds",
    buckets=[0.001, 0.01, 0.1, 1.0, 10.0],
    labels=["operation", "table"]
)

# Monitor connection pool
pool_stats = connection_pool.get_stats()
db_connections_active.set(pool_stats["active_connections"])

# Execute queries with timing
results = []
for query_info in queries:
    start_time = time.time()

    try:
        with connection_pool.getconn() as conn:
            db_connections_total.inc()
            cursor = conn.cursor()
            cursor.execute(query_info["sql"], query_info["params"])

            query_results = cursor.fetchall()
            results.append({
                "query_id": query_info["id"],
                "rows": len(query_results),
                "data": query_results
            })

    finally:
        duration = time.time() - start_time
        query_duration.labels(
            operation=query_info["operation"],
            table=query_info["table"]
        ).observe(duration)

        connection_pool.putconn(conn)

result = {"query_results": results, "pool_stats": pool_stats}
''',
    input_types={"queries": list}
))

```

## 📈 Advanced Metrics Patterns

### Business Metrics
```python
workflow.add_node("PythonCodeNode", "business_metrics", {})

conversion_rate = Gauge(
    "conversion_rate",
    description="Current conversion rate",
    labels=["funnel_stage"]
)

order_value = Histogram(
    "order_value_dollars",
    description="Order value distribution",
    buckets=[10, 50, 100, 500, 1000, 5000]
)

# Process business events
for event in events:
    if event["type"] == "purchase":
        # Track revenue
        revenue_counter.labels(
            product=event["product"],
            region=event["region"]
        ).inc(event["amount_cents"])

        # Track order value
        order_value.observe(event["amount_cents"] / 100)

    elif event["type"] == "conversion":
        # Update conversion rate
        conversion_rate.labels(
            funnel_stage=event["stage"]
        ).set(event["rate"])

result = {
    "total_revenue": revenue_counter.sum / 100,
    "avg_order_value": order_value.sum / order_value.count
}
''',
    input_types={"events": list}
))

```

### SLI/SLO Metrics
```python
from kailash.monitoring import SLICollector, SLOManager

# Service Level Indicators
sli_collector = SLICollector([
    {
        "name": "availability",
        "type": "ratio",
        "good_events": "http_requests{status!~'5..'}"    ,
        "total_events": "http_requests",
        "target": 0.999  # 99.9% availability
    },
    {
        "name": "latency",
        "type": "threshold",
        "metric": "http_request_duration_seconds",
        "threshold": 0.5,  # 500ms
        "percentile": 0.95,
        "target": 0.95  # 95% of requests under 500ms
    },
    {
        "name": "throughput",
        "type": "rate",
        "metric": "successful_requests_total",
        "window": "5m",
        "target": 100  # 100 requests/second minimum
    }
])

# SLO Management
slo_manager = SLOManager(
    slis=sli_collector,
    error_budget_windows={
        "1h": 0.1,    # 10% of monthly budget
        "6h": 0.5,    # 50% of monthly budget
        "30d": 1.0    # Full monthly budget
    },
    alert_burn_rates={
        "fast": 14.4,   # 2 hours to exhaustion
        "slow": 6.0     # 5 hours to exhaustion
    }
)

workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "slo_calculator", {})
        total_events = sum(metrics["total_events"])
        current_slis[sli_config["name"]] = good_events / total_events if total_events > 0 else 1.0

    elif sli_config["type"] == "threshold":
        response_times = metrics["response_times"]
        response_times.sort()
        p95_index = int(len(response_times) * 0.95)
        p95_latency = response_times[p95_index] if response_times else 0
        current_slis[sli_config["name"]] = 1.0 if p95_latency <= sli_config["threshold"] else 0.0

# Calculate error budget burn rate
time_window = timedelta(hours=1)
current_time = datetime.utcnow()
start_time = current_time - time_window

error_budget_consumed = {}
for sli_name, sli_value in current_slis.items():
    target = next(s["target"] for s in sli_configs if s["name"] == sli_name)
    error_rate = 1.0 - sli_value
    allowed_error_rate = 1.0 - target

    if allowed_error_rate > 0:
        burn_rate = error_rate / allowed_error_rate
        error_budget_consumed[sli_name] = burn_rate
    else:
        error_budget_consumed[sli_name] = 0.0

# SLO compliance status
slo_status = {
    "slis": current_slis,
    "error_budget_burn_rates": error_budget_consumed,
    "compliance": all(sli >= target for sli, target in
                     [(current_slis[s["name"]], s["target"]) for s in sli_configs]),
    "timestamp": current_time.isoformat()
}

result = {"slo_status": slo_status}
''',
    input_types={"sli_configs": list, "metrics": dict}
))

```

### Distributed Metrics
```python
from kailash.monitoring import MetricsPushGateway, MetricsEndpointNode

workflow = WorkflowBuilder()

# Push-based metrics aggregation
workflow.add_node("metrics_pusher", MetricsPushGateway(
    gateway_url="http://pushgateway:9091",
    job_name="kailash_worker",
    push_interval=30,
    instance_labels={
        "instance_id": "${INSTANCE_ID}",
        "region": "${AWS_REGION}",
        "environment": "production"
    }
))

# Or use pull-based aggregation
workflow.add_node("MetricsEndpointNode", "metrics_endpoint", {}))

# Cross-service metrics correlation
workflow.add_node("PythonCodeNode", "service_metrics_aggregator", {})
        response.raise_for_status()

        # Parse Prometheus metrics
        metrics_data = parse_prometheus_metrics(response.text)
        service_metrics.append({
            "service": extract_service_name(endpoint),
            "metrics": metrics_data,
            "status": "healthy"
        })

    except Exception as e:
        service_metrics.append({
            "service": extract_service_name(endpoint),
            "error": str(e),
            "status": "unhealthy"
        })

# Aggregate cross-service metrics
for service_data in service_metrics:
    if service_data["status"] == "healthy":
        metrics = service_data["metrics"]
        service_name = service_data["service"]

        aggregated_metrics["total_requests"] += metrics.get("http_requests_total", 0)
        aggregated_metrics["total_errors"] += metrics.get("http_errors_total", 0)
        aggregated_metrics["service_health"][service_name] = {
            "status": "healthy",
            "response_time": metrics.get("http_response_time_avg", 0),
            "last_check": datetime.utcnow().isoformat()
        }

# Calculate overall system health
overall_error_rate = (aggregated_metrics["total_errors"] /
                     aggregated_metrics["total_requests"]) if aggregated_metrics["total_requests"] > 0 else 0

healthy_services = len([s for s in aggregated_metrics["service_health"].values() if s["status"] == "healthy"])
total_services = len(service_endpoints)
system_availability = healthy_services / total_services

result = {
    "aggregated_metrics": aggregated_metrics,
    "system_health": {
        "availability": system_availability,
        "error_rate": overall_error_rate,
        "healthy_services": healthy_services,
        "total_services": total_services
    },
    "timestamp": datetime.utcnow().isoformat()
}
''',
    input_types={}
))

```

## 🔍 Metrics Queries

### Prometheus Queries
```promql
# Average response time by endpoint (5m window)
rate(http_response_time_seconds_sum[5m])
/ rate(http_response_time_seconds_count[5m])

# 95th percentile latency
histogram_quantile(0.95,
  rate(http_response_time_seconds_bucket[5m])
)

# Error rate percentage
100 * rate(errors_total[5m])
/ rate(requests_total[5m])

# Memory usage trend
predict_linear(memory_usage_bytes[1h], 3600)
```

### Grafana Dashboard JSON
```json
{
  "dashboard": {
    "title": "Kailash Application Metrics",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [{
          "expr": "rate(http_requests_total[5m])"
        }]
      },
      {
        "title": "Error Rate",
        "targets": [{
          "expr": "rate(errors_total[5m]) / rate(requests_total[5m])"
        }]
      },
      {
        "title": "P95 Latency",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(http_response_time_seconds_bucket[5m]))"
        }]
      }
    ]
  }
}
```

## 🎯 Best Practices

### 1. **Metric Naming**
```python
# Good metric names - follow Prometheus conventions
metric_names = {
    # Durations - always use seconds
    "workflow_execution_duration_seconds": "Time taken to execute workflow",
    "http_request_duration_seconds": "HTTP request processing time",
    "database_query_duration_seconds": "Database query execution time",

    # Totals - use _total suffix for counters
    "http_requests_total": "Total number of HTTP requests",
    "database_queries_total": "Total number of database queries",
    "errors_total": "Total number of errors",

    # Current values - use descriptive suffix
    "database_connections_active": "Currently active database connections",
    "queue_depth_items": "Number of items in queue",
    "memory_usage_bytes": "Memory usage in bytes",

    # Rates - calculated from totals
    "http_requests_per_second": "HTTP requests per second",
    "error_rate_percent": "Error rate as percentage"
}

# Bad examples to avoid
bad_examples = {
    "response_time": "Missing unit - should be response_time_seconds",
    "memory": "Too vague - should be memory_usage_bytes",
    "requests": "Missing _total suffix for counter",
    "db_conn": "Abbreviated - should be database_connections_active"
}

# Include units in names
unit_conventions = {
    "seconds": ["duration", "time", "latency"],
    "bytes": ["size", "usage", "memory"],
    "total": ["count", "requests", "errors"],
    "percent": ["rate", "ratio", "utilization"]
}

```

### 2. **Label Usage**
```python
# Good: Low cardinality labels
labels=["method", "status", "service"]  # ~10-100 combinations

# Bad: High cardinality labels
labels=["user_id", "session_id", "timestamp"]  # Millions of combinations

# Use buckets for high cardinality
age_buckets = ["0-18", "19-35", "36-50", "51+"]
labels=["age_bucket"]  # Instead of exact age

```

### 3. **Metric Granularity**
```python
# Balance between detail and overhead
METRIC_CONFIG = {
    "high_frequency": {  # Critical paths
        "interval": 1,
        "retention": "7d"
    },
    "medium_frequency": {  # Normal operations
        "interval": 10,
        "retention": "30d"
    },
    "low_frequency": {  # Background tasks
        "interval": 60,
        "retention": "90d"
    }
}

```

## 🔗 Next Steps

- [Logging Patterns](logging-patterns.md) - Structured logging
- [Tracing Patterns](tracing-patterns.md) - Distributed tracing
- [Alert Patterns](alert-patterns.md) - Alert configuration
