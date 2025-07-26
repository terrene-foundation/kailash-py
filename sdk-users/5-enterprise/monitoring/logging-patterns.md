# Logging & Audit Patterns

*Structured logging and audit trail patterns for Kailash applications*

## 📝 Structured Logging Setup

### Basic Configuration
```python
from kailash.workflow.builder import WorkflowBuilder
import structlog
from kailash.logging import configure_logging

# Configure structured logging
configure_logging(
    level="INFO",
    format="json",
    include_fields=[
        "timestamp", "level", "logger", "message",
        "correlation_id", "user_id", "trace_id"
    ],
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ]
)

# Get logger
logger = structlog.get_logger()

```

### Workflow Logging
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "logged_processor", {})

# Context logging
logger.info(
    "processing_started",
    workflow_id=workflow_id,
    node_id="logged_processor",
    input_count=len(data),
    correlation_id=context.get("correlation_id"),
    user_id=context.get("user_id")
)

try:
    # Process data with progress logging
    processed = []
    for i, item in enumerate(data):
        if i % 100 == 0:  # Log progress every 100 items
            logger.debug(
                "processing_progress",
                completed=i,
                total=len(data),
                percent=round(i/len(data)*100, 2)
            )

        result = process_item(item)
        processed.append(result)

    logger.info(
        "processing_completed",
        items_processed=len(processed),
        success_rate=len([p for p in processed if p.get("success")]) / len(processed),
        duration_ms=elapsed_ms
    )

    result = {"data": processed}

except Exception as e:
    logger.error(
        "processing_failed",
        error_message=str(e),
        error_type=e.__class__.__name__,
        stack_trace=traceback.format_exc(),
        failed_item_index=i if 'i' in globals() else None
    )
    result = {"error": str(e)}
''',
    input_types={"data": list}
))

```

## 📊 Log Levels & Categories

### Log Levels
```python
from kailash.workflow.builder import WorkflowBuilder

# CRITICAL: System unusable
logger.critical(
    "database_connection_failed",
    error="Connection timeout",
    database_host="db.prod.com",
    timeout_seconds=30
)

# ERROR: Error conditions
logger.error(
    "api_request_failed",
    endpoint="/api/users",
    status_code=500,
    retry_attempt=3
)

# WARNING: Warning conditions
logger.warning(
    "rate_limit_approaching",
    current_rate=95,
    limit=100,
    window="1m"
)

# INFO: Informational messages
logger.info(
    "workflow_executed",
    workflow_id="wf-123",
    execution_time_ms=1250,
    status="success"
)

# DEBUG: Debug-level messages
logger.debug(
    "cache_lookup",
    cache_key="user:123",
    cache_hit=True,
    ttl_remaining=300
)

```

### Log Categories
```python
from kailash.workflow.builder import WorkflowBuilder
# Business events
business_logger = structlog.get_logger("business")
business_logger.info(
    "order_placed",
    order_id="ord-123",
    customer_id="cust-456",
    amount_cents=9999,
    product_ids=["prod-1", "prod-2"]
)

# Security events
security_logger = structlog.get_logger("security")
security_logger.warning(
    "failed_login_attempt",
    user_id="user-123",
    ip_address="192.168.1.100",
    user_agent="Mozilla/5.0...",
    attempt_count=3
)

# Performance events
perf_logger = structlog.get_logger("performance")
perf_logger.info(
    "slow_query_detected",
    query="SELECT * FROM large_table",
    duration_ms=2500,
    threshold_ms=1000
)

```

## 🔍 Audit Logging

### Comprehensive Audit Trail
```python
from kailash.workflow.builder import WorkflowBuilder
workflow.add_node("AuditLoggerNode", "audit_logger", {}))

# Custom audit logging
workflow.add_node("PythonCodeNode", "custom_audit", {})

# Record data access
audit.log_event(
    event_type="data_access",
    actor_id=user_id,
    resource_type="customer_data",
    resource_id=customer_id,
    action="read",
    timestamp=datetime.utcnow().isoformat(),
    metadata={
        "fields_accessed": ["name", "email", "phone"],
        "access_reason": "customer_support_inquiry",
        "session_id": session_id,
        "ip_address": request_ip
    }
)

# Record data modification
for item in modified_items:
    audit.log_event(
        event_type="data_modification",
        actor_id=user_id,
        resource_type="product",
        resource_id=item["id"],
        action="update",
        before_value=item["original"],
        after_value=item["modified"],
        change_reason="price_adjustment"
    )

result = {"audited": True, "events_logged": len(modified_items) + 1}
''',
    input_types={"user_id": str, "customer_id": str, "modified_items": list}
))

```

### Compliance Logging
```python
from kailash.workflow.builder import WorkflowBuilder

# GDPR compliance logging
workflow = WorkflowBuilder()

# SOX compliance logging
workflow = WorkflowBuilder()

```

## 📋 Log Enrichment

### Context Enrichment
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.logging import LogEnrichmentMiddleware

# Add context to all logs
enrichment = LogEnrichmentMiddleware([
    # Request context
    "correlation_id",
    "trace_id",
    "user_id",
    "session_id",

    # Environment context
    "environment",
    "region",
    "instance_id",
    "version",

    # Business context
    "tenant_id",
    "organization_id",
    "feature_flags"
])

# Apply to workflow
workflow.add_middleware(enrichment)

```

### Sensitive Data Filtering
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

```

## 📊 Log Aggregation

### Centralized Logging
```python
from kailash.workflow.builder import WorkflowBuilder

# Export to multiple destinations
workflow = WorkflowBuilder()

```

### Log Parsing & Analysis
```python
from kailash.workflow.builder import WorkflowBuilder

# Parse structured logs
workflow.add_node("LogParserNode", "log_parser", {}) (?P<level>\S+) (?P<method>\S+) (?P<path>\S+) (?P<status>\d+) (?P<duration>\d+)ms",
        "database_query": r"Query: (?P<query>.*) Duration: (?P<duration>\d+)ms Rows: (?P<rows>\d+)",
        "error_stack": r"(?P<error_type>\w+): (?P<message>.*) at (?P<location>.*)",
        "workflow_execution": r"Workflow (?P<workflow_id>\S+) (?P<status>\w+) in (?P<duration>\d+)ms",
        "node_processing": r"Node (?P<node_id>\S+) processed (?P<items>\d+) items"
    },
    extract_metrics=True,
    create_alerts=True,
    output_format="structured"
))

# Advanced log analysis
workflow.add_node("PythonCodeNode", "log_analyzer", {}),
    "by_level": Counter(log["level"] for log in parsed_logs),
    "by_service": Counter(log.get("service", "unknown") for log in parsed_logs),
    "error_patterns": Counter(),
    "performance_metrics": {
        "avg_response_time": 0,
        "slow_queries": [],
        "error_rate": 0
    }
}

# Extract performance metrics
response_times = []
for log in parsed_logs:
    if "duration" in log:
        duration = int(log["duration"])
        response_times.append(duration)

        # Flag slow operations
        if duration > 1000:  # > 1 second
            log_stats["performance_metrics"]["slow_queries"].append({
                "duration": duration,
                "query": log.get("query", log.get("path", "unknown")),
                "timestamp": log["timestamp"]
            })

if response_times:
    log_stats["performance_metrics"]["avg_response_time"] = sum(response_times) / len(response_times)

# Analyze error patterns
error_logs = [log for log in parsed_logs if log["level"] in ["ERROR", "CRITICAL"]]
for error_log in error_logs:
    error_type = error_log.get("error_type", "UnknownError")
    log_stats["error_patterns"][error_type] += 1

log_stats["performance_metrics"]["error_rate"] = len(error_logs) / len(parsed_logs) if parsed_logs else 0

# Generate insights
insights = []
if log_stats["performance_metrics"]["error_rate"] > 0.05:
    insights.append("High error rate detected (>5%)")
if log_stats["performance_metrics"]["avg_response_time"] > 500:
    insights.append("Slow average response time (>500ms)")
if len(log_stats["performance_metrics"]["slow_queries"]) > 10:
    insights.append(f"{len(log_stats['performance_metrics']['slow_queries'])} slow queries detected")

result = {
    "log_statistics": log_stats,
    "insights": insights,
    "analysis_timestamp": datetime.utcnow().isoformat()
}
''',
    input_types={"parsed_logs": list}
))

```

## 🔍 Log Search & Analysis

### Query Examples
```javascript
// Elasticsearch queries
{
  "query": {
    "bool": {
      "must": [
        {"term": {"level": "ERROR"}},
        {"range": {"@timestamp": {"gte": "now-1h"}}},
        {"exists": {"field": "user_id"}}
      ]
    }
  },
  "aggs": {
    "error_types": {
      "terms": {"field": "error_type"}
    }
  }
}

// Splunk search
index="kailash_logs" level=ERROR
| stats count by error_type
| sort -count

// CloudWatch Insights
fields @timestamp, level, message, error_type
| filter level = "ERROR"
| stats count() by error_type
| sort count desc
```

### Log-based Metrics
```python
from kailash.workflow.builder import WorkflowBuilder
# Extract metrics from logs
workflow.add_node("LogMetricsExtractorNode", "log_metrics_extractor", {})ms",
            "type": "histogram",
            "labels": ["method", "endpoint"],
            "buckets": [10, 50, 100, 500, 1000, 5000]
        },
        {
            "name": "error_count",
            "pattern": r"level:ERROR",
            "type": "counter",
            "labels": ["error_type", "service"]
        },
        {
            "name": "request_rate",
            "pattern": r"HTTP (?P<method>\w+) (?P<path>\S+)",
            "type": "counter",
            "labels": ["method", "path_pattern"]
        },
        {
            "name": "user_activity",
            "pattern": r"user_id:(?P<user_id>\w+)",
            "type": "gauge",
            "aggregation": "unique_count",
            "window": "5m"
        }
    ],
    export_interval=60,
    export_destinations=["prometheus", "cloudwatch"]
))

# Custom log-based metrics
workflow.add_node("PythonCodeNode", "custom_log_metrics", {}),
    "feature_usage": Counter(),
    "conversion_funnel": defaultdict(int)
}

# Process log entries
for entry in log_entries:
    message = entry.get("message", "")
    metadata = entry.get("metadata", {})

    # Order processing metrics
    if "order_completed" in message:
        business_metrics["orders_processed"] += 1
        business_metrics["revenue_total"] += metadata.get("amount", 0)
        business_metrics["unique_customers"].add(metadata.get("customer_id"))

    # Feature usage tracking
    if "feature_used" in message:
        feature_name = metadata.get("feature", "unknown")
        business_metrics["feature_usage"][feature_name] += 1

    # Conversion funnel tracking
    if "funnel_step" in message:
        step = metadata.get("step", "unknown")
        business_metrics["conversion_funnel"][step] += 1

# Calculate derived metrics
conversion_rate = 0
if business_metrics["conversion_funnel"]["landing"] > 0:
    conversion_rate = (business_metrics["conversion_funnel"]["purchase"] /
                      business_metrics["conversion_funnel"]["landing"]) * 100

avg_order_value = 0
if business_metrics["orders_processed"] > 0:
    avg_order_value = business_metrics["revenue_total"] / business_metrics["orders_processed"]

result = {
    "business_metrics": {
        "orders_processed": business_metrics["orders_processed"],
        "total_revenue": business_metrics["revenue_total"],
        "unique_customers": len(business_metrics["unique_customers"]),
        "avg_order_value": avg_order_value,
        "conversion_rate_percent": conversion_rate,
        "top_features": dict(business_metrics["feature_usage"].most_common(5))
    },
    "timestamp": datetime.utcnow().isoformat()
}
''',
    input_types={"log_entries": list}
))

```

## 🎯 Logging Best Practices

### 1. **Log Structure**
```python
from kailash.workflow.builder import WorkflowBuilder
# Good: Structured logging
logger.info(
    "user_login",
    user_id="123",
    ip_address="192.168.1.1",
    user_agent="Chrome/91.0",
    success=True,
    login_method="oauth"
)

# Bad: Unstructured logging
logger.info(f"User 123 logged in from 192.168.1.1 using Chrome")

```

### 2. **Log Levels**
```python
from kailash.workflow.builder import WorkflowBuilder
# Use appropriate levels
logger.debug("Cache miss for key: user:123")  # Development info
logger.info("User authenticated successfully")  # Normal operations
logger.warning("API rate limit at 90%")         # Potential issues
logger.error("Database connection failed")      # Error conditions
logger.critical("Service unavailable")          # Service down

```

### 3. **Performance Considerations**
```python
from kailash.workflow.builder import WorkflowBuilder
# Lazy evaluation for expensive operations
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Processing data: %s", expensive_serialize(data))

# Sample high-volume logs
if should_sample(rate=0.1):  # 10% sampling
    logger.debug("High volume debug message")

# Async logging for performance
async_logger = AsyncLogger(buffer_size=1000, flush_interval=5)

```

## 🔗 Next Steps

- [Metrics Patterns](metrics-patterns.md) - Metrics collection
- [Tracing Patterns](tracing-patterns.md) - Distributed tracing
- [Security Guide](../architecture/security-patterns.md) - Security logging
