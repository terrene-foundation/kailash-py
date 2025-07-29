# REST API Integration Patterns

**Complete guide to REST API workflows** - From simple API calls to complex enterprise integrations using proper Kailash nodes.

## 📋 Pattern Overview

REST API workflows enable:
- **Data Integration**: Sync data between systems via HTTP APIs
- **Service Orchestration**: Coordinate multiple microservices
- **Real-time Updates**: Push/pull data updates via API endpoints
- **Third-party Integration**: Connect with external services and platforms
- **Event-driven Processing**: Webhook handling and API-triggered workflows

## 🚀 Quick Start Examples

### 30-Second API Integration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# API integration workflow using proper Kailash nodes
workflow = WorkflowBuilder()

# Rate-limited API client
workflow.add_node("HTTPRequestNode", "api_client", {
    "url": "https://api.example.com/v1/products",
    "method": "GET",
    "headers": {"Authorization": "Bearer YOUR_TOKEN"},
    "retry_attempts": 3,
    "timeout": 30
})

# Process API response
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Simple response processing
response_data = parameters.get('response_data', {})
if isinstance(response_data, dict) and response_data.get("status") == "success":
    products = response_data.get("data", {}).get("products", [])
    result = {
        "products": products,
        "total_count": len(products),
        "processed_at": "2024-01-01T00:00:00Z"
    }
else:
    result = {"products": [], "total_count": 0, "error": "API call failed"}
"""
})
workflow.add_connection("api_client", "result", "processor", "response_data")

# Save results
workflow.add_node("JSONWriterNode", "writer", {
    "file_path": "api_results.json"
})
workflow.add_connection("processor", "result", "writer", "data")

# Execute the workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### Enterprise API Integration with Full Error Handling
```python
# All nodes are accessed via string-based API - no direct imports needed

# Enterprise-grade API workflow
workflow = WorkflowBuilder()

# Circuit breaker for API reliability
workflow.add_node("CircuitBreakerNode", "circuit_breaker", {
    "failure_threshold": 5,
    "recovery_timeout": 60,
    "half_open_max_calls": 3
})

# Primary API with rate limiting
workflow.add_node("HTTPRequestNode", "primary_api", {
    "url": "https://api.primary.com/endpoint",
    "method": "GET",
    "retry_attempts": 3,
    max_retries=3,
    timeout=30,
    backoff_factor=2.0
)

# Fallback API for resilience
workflow.add_node("HTTPRequestNode", "fallback_api", {
    "url": "https://api.backup.com/endpoint",
    "method": "GET",
    "retry_attempts": 2,
    "timeout": 15
})

# Response validation and routing
workflow.add_node("PythonCodeNode", "validator", {
    "code":
        """
# Comprehensive response validation
import json
from datetime import datetime

validation_result = {
    "valid": False,
    "errors": [],
    "warnings": [],
    "data": None,
    "metadata": {
        "validated_at": datetime.now().isoformat(),
        "source": "primary_api"
    }
}

# Check response structure
if not isinstance(data, dict):
    validation_result["errors"].append("Response is not a valid JSON object")
elif "status" not in data:
    validation_result["errors"].append("Missing required 'status' field")
elif data.get("status") not in ["success", "partial_success"]:
    validation_result["errors"].append(f"Invalid status: {data.get('status')}")
else:
    # Validate data payload
    payload = data.get("data", {})
    if not isinstance(payload, dict):
        validation_result["errors"].append("Data payload is not a dictionary")
    elif "items" not in payload:
        validation_result["warnings"].append("No items found in response")
        validation_result["data"] = {"items": [], "total": 0}
        validation_result["valid"] = True
    else:
        # Validate items structure
        items = payload.get("items", [])
        validated_items = []

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                validation_result["warnings"].append(f"Item {i} is not a dictionary")
                continue

            # Required fields validation
            required_fields = ["id", "name", "status"]
            missing_fields = [f for f in required_fields if f not in item]
            if missing_fields:
                validation_result["warnings"].append(f"Item {i} missing fields: {missing_fields}")

            # Data type validation
            if "id" in item and not isinstance(item["id"], (int, str)):
                validation_result["warnings"].append(f"Item {i} has invalid id type")

            validated_items.append(item)

        validation_result["data"] = {
            "items": validated_items,
            "total": len(validated_items),
            "original_total": len(items)
        }
        validation_result["valid"] = len(validation_result["errors"]) == 0

result = validation_result
"""
})

# Route based on validation results
workflow.add_node("SwitchNode", "router", {
    "condition": "result.valid == True"
})

# Success path: Process valid data
workflow.add_node("PythonCodeNode", "success_processor", {
    "code":
        """
# Process validated data
items = data.get("data", {}).get("items", [])
metadata = data.get("metadata", {})

# Enrich items with processing metadata
enriched_items = []
for item in items:
    enriched_item = dict(item)
    enriched_item.update({
        "processed_at": metadata.get("validated_at"),
        "source": metadata.get("source", "unknown"),
        "validation_status": "passed"
    })

    # Add computed fields
    if "price" in item and "quantity" in item:
        enriched_item["total_value"] = item["price"] * item.get("quantity", 0)

    enriched_items.append(enriched_item)

# Generate summary statistics
summary = {
    "total_items": len(enriched_items),
    "avg_price": sum(item.get("price", 0) for item in enriched_items) / len(enriched_items) if enriched_items else 0,
    "categories": list(set(item.get("category", "unknown") for item in enriched_items)),
    "processing_metadata": metadata
}

result = {
    "processed_items": enriched_items,
    "summary": summary,
    "status": "success"
}
"""
    ]
)

# Error path: Handle failures and retry logic
workflow.add_node("PythonCodeNode", "error_handler", {
    "code":
        """
# Handle validation errors and prepare for fallback
errors = data.get("errors", [])
warnings = data.get("warnings", [])

# Determine if errors are recoverable
recoverable_errors = [
    "timeout", "rate_limit", "server_error", "network_error"
]

error_types = []
for error in errors:
    if any(recoverable in error.lower() for recoverable in recoverable_errors):
        error_types.append("recoverable")
    else:
        error_types.append("permanent")

retry_recommendation = "recoverable" in error_types

result = {
    "should_retry": retry_recommendation,
    "error_summary": {
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "recoverable": error_types.count("recoverable"),
        "permanent": error_types.count("permanent")
    },
    "fallback_required": not retry_recommendation,
    "original_data": data
}
"""
})

# Connect the workflow
workflow.add_connection("circuit_breaker", "result", "primary_api", "input")
workflow.add_connection("primary_api", "validator", "response", "data")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Success path
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping

# Error path
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping

# Database storage for successful results
workflow.add_node("DatabaseWriterNode", "db_writer", {
    "connection_string": "${DATABASE_URL}",
    "table_name": "api_results",
    "batch_size": 100
})
workflow.add_connection("success_processor", "result", "db_writer", "records")

# CSV backup for all results
workflow.add_node("CSVWriterNode", "csv_backup", {
    "file_path": "data/api_backup.csv",
    "include_headers": True
})

# Merge successful and error results for backup
workflow.add_node("MergeNode", "result_merger", {})
workflow.add_connection("success_processor", "result_merger", "result", "data1")
workflow.add_connection("error_handler", "result_merger", "result", "data2")
workflow.add_connection("result_merger", "csv_backup", "merged_data", "data")

```

## 🔄 Authentication Patterns

### OAuth2 Authentication Flow
```python
from kailash.nodes.api import OAuth2Node

workflow = WorkflowBuilder()

# OAuth2 authentication
auth = OAuth2Node(
    id="oauth",
    token_url="https://api.example.com/oauth/token",
    client_id="${OAUTH_CLIENT_ID}",
    client_secret="${OAUTH_CLIENT_SECRET}"
)
workflow.add_node("oauth", auth)

# Authenticated API request
workflow.add_node("HTTPRequestNode", "api_request", {
    "method": "GET",
    "url": "https://api.example.com/protected-data"
})
workflow.add_connection("oauth", "access_token", "api_request", "auth_token")

```

### API Key Authentication
```python
from kailash.nodes.api import APIKeyNode

# API key authentication
workflow.add_node("APIKeyNode", "api_key", {
    "api_key": "${API_KEY}",
    "header_name": "X-API-Key"
})

# Use with HTTP request
workflow.add_node("HTTPRequestNode", "request", {
    "method": "GET",
    "url": "https://api.example.com/data"
})
workflow.add_connection("api_key", "headers", "request", "auth_headers")

```

## 📊 Data Processing Patterns

### API Response Transformation
```python
# Extract and transform API data
data_extractor = DataTransformer(
    id="extractor",
    transformations=[
        """
# Extract relevant data from API response
if isinstance(data, dict) and "data" in data:
    items = data["data"]
    processed_items = []

    for item in items:
        processed_items.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "price": item.get("price", 0),
            "available": item.get("stock", 0) > 0
        })

    result = {
        "items": processed_items,
        "count": len(processed_items)
    }
else:
    result = {"items": [], "count": 0, "error": "Invalid response format"}
"""
    ]
)

```

### Advanced Data Aggregation and Analytics
```python
# Complex data aggregation from multiple API endpoints
aggregator = DataTransformer(
    id="data_aggregator",
    transformations=[
        """
# Advanced analytics on aggregated API data
import json
from datetime import datetime, timedelta
from collections import defaultdict

# Combine data from multiple sources
primary_data = data.get("primary_api_data", {})
secondary_data = data.get("secondary_api_data", {})
tertiary_data = data.get("analytics_data", {})

# Initialize analytics structure
analytics = {
    "time_series": defaultdict(list),
    "geographic": defaultdict(dict),
    "categorical": defaultdict(int),
    "performance_metrics": {},
    "anomalies": [],
    "recommendations": []
}

# Process primary data for time series analysis
if "transactions" in primary_data:
    transactions = primary_data["transactions"]

    # Group by time periods
    hourly_data = defaultdict(lambda: {"count": 0, "volume": 0, "value": 0})
    daily_data = defaultdict(lambda: {"count": 0, "volume": 0, "value": 0})

    for txn in transactions:
        timestamp = txn.get("timestamp", "")
        if timestamp:
            # Parse timestamp and group by hour/day
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                hour_key = dt.strftime("%Y-%m-%d %H:00")
                day_key = dt.strftime("%Y-%m-%d")

                amount = float(txn.get("amount", 0))
                volume = int(txn.get("quantity", 1))

                hourly_data[hour_key]["count"] += 1
                hourly_data[hour_key]["volume"] += volume
                hourly_data[hour_key]["value"] += amount

                daily_data[day_key]["count"] += 1
                daily_data[day_key]["volume"] += volume
                daily_data[day_key]["value"] += amount

            except Exception as e:
                analytics["anomalies"].append(f"Invalid timestamp: {timestamp}")

    analytics["time_series"]["hourly"] = dict(hourly_data)
    analytics["time_series"]["daily"] = dict(daily_data)

# Process geographic data
if "user_locations" in secondary_data:
    locations = secondary_data["user_locations"]

    for location in locations:
        country = location.get("country", "Unknown")
        region = location.get("region", "Unknown")
        user_count = int(location.get("user_count", 0))
        revenue = float(location.get("revenue", 0))

        if country not in analytics["geographic"]:
            analytics["geographic"][country] = {
                "regions": defaultdict(dict),
                "total_users": 0,
                "total_revenue": 0
            }

        analytics["geographic"][country]["total_users"] += user_count
        analytics["geographic"][country]["total_revenue"] += revenue
        analytics["geographic"][country]["regions"][region] = {
            "users": user_count,
            "revenue": revenue,
            "avg_revenue_per_user": revenue / user_count if user_count > 0 else 0
        }

# Category analysis
if "product_categories" in tertiary_data:
    categories = tertiary_data["product_categories"]

    for category in categories:
        cat_name = category.get("name", "Unknown")
        cat_sales = int(category.get("sales", 0))
        cat_revenue = float(category.get("revenue", 0))

        analytics["categorical"][cat_name] = {
            "sales": cat_sales,
            "revenue": cat_revenue,
            "avg_order_value": cat_revenue / cat_sales if cat_sales > 0 else 0
        }

# Performance metrics calculation
total_transactions = sum(d["count"] for d in daily_data.values())
total_revenue = sum(d["value"] for d in daily_data.values())
total_volume = sum(d["volume"] for d in daily_data.values())

analytics["performance_metrics"] = {
    "total_transactions": total_transactions,
    "total_revenue": total_revenue,
    "total_volume": total_volume,
    "avg_transaction_value": total_revenue / total_transactions if total_transactions > 0 else 0,
    "avg_transaction_volume": total_volume / total_transactions if total_transactions > 0 else 0,
    "data_sources_processed": len([k for k in [primary_data, secondary_data, tertiary_data] if k]),
    "processing_timestamp": datetime.now().isoformat()
}

# Anomaly detection
if total_transactions > 0:
    daily_values = [d["value"] for d in daily_data.values()]
    if daily_values:
        avg_daily = sum(daily_values) / len(daily_values)
        max_daily = max(daily_values)
        min_daily = min(daily_values)

        # Flag anomalies (simple threshold-based)
        if max_daily > avg_daily * 2:
            analytics["anomalies"].append(f"High revenue day detected: ${max_daily:.2f} vs avg ${avg_daily:.2f}")

        if min_daily < avg_daily * 0.3:
            analytics["anomalies"].append(f"Low revenue day detected: ${min_daily:.2f} vs avg ${avg_daily:.2f}")

# Generate recommendations
if analytics["performance_metrics"]["total_transactions"] > 100:
    top_countries = sorted(analytics["geographic"].items(),
                          key=lambda x: x[1]["total_revenue"], reverse=True)[:3]

    analytics["recommendations"].extend([
        f"Focus marketing on top revenue countries: {', '.join([c[0] for c in top_countries])}",
        "Consider expanding operations in high-performing regions",
        "Monitor anomaly patterns for revenue optimization"
    ])

# Top categories by revenue
if analytics["categorical"]:
    top_categories = sorted(analytics["categorical"].items(),
                           key=lambda x: x[1]["revenue"], reverse=True)[:5]

    analytics["recommendations"].append(
        f"Prioritize inventory for top categories: {', '.join([c[0] for c in top_categories])}"
    )

result = analytics
"""
    ]
)

```

### Error Handling and Validation
```python
# Validate API responses
validator = DataTransformer(
    id="validator",
    transformations=[
        """
# Validate API response structure
errors = []
warnings = []

if not isinstance(data, dict):
    errors.append("Response is not a valid JSON object")
elif "status" not in data:
    errors.append("Missing status field")
elif data.get("status") != "success":
    errors.append(f"API returned error status: {data.get('status')}")

if "data" not in data:
    warnings.append("Missing data field")

result = {
    "valid": len(errors) == 0,
    "errors": errors,
    "warnings": warnings,
    "data": data if len(errors) == 0 else None
}
"""
    ]
)

```

### Real-time Data Streaming Integration
```python
from kailash.nodes.data import StreamingDataNode, QueueNode

# Streaming API integration for real-time data
streaming_workflow = WorkflowBuilder()

# Streaming data source
streaming_workflow.add_node("StreamingDataNode", "stream_source", {
    "stream_type": "websocket",
    "connection_url": "wss://api.example.com/stream",
    "buffer_size": 1000,
    "flush_interval": 5  # seconds
})

# Real-time data processor
streaming_workflow.add_node("DataTransformer", "stream_processor", {
    "transformations": [
        """
# Process streaming data in real-time
import json
from datetime import datetime

processed_events = []
for event in data.get("events", []):
    # Parse and enrich each streaming event
    processed_event = {
        "id": event.get("id"),
        "type": event.get("type"),
        "timestamp": event.get("timestamp"),
        "processed_at": datetime.now().isoformat(),
        "payload": event.get("data", {}),

        # Add computed fields
        "severity": "high" if event.get("priority", 0) > 8 else "medium" if event.get("priority", 0) > 5 else "low",
        "category": event.get("type", "unknown").split(".")[0],  # Extract main category
        "source_ip": event.get("metadata", {}).get("source_ip", "unknown"),

        # Event enrichment
        "enriched_data": {
            "user_agent": event.get("metadata", {}).get("user_agent", ""),
            "geo_location": event.get("metadata", {}).get("geo", {}),
            "session_id": event.get("session_id", ""),
            "correlation_id": event.get("correlation_id", "")
        }
    }

    # Add business logic enrichment
    if processed_event["type"] == "purchase":
        amount = float(event.get("data", {}).get("amount", 0))
        processed_event["revenue_impact"] = "high" if amount > 100 else "medium" if amount > 50 else "low"

    processed_events.append(processed_event)

# Aggregate streaming metrics
metrics = {
    "total_events": len(processed_events),
    "event_types": {},
    "severity_distribution": {"high": 0, "medium": 0, "low": 0},
    "processing_stats": {
        "batch_size": len(processed_events),
        "processing_time": datetime.now().isoformat(),
        "avg_payload_size": sum(len(str(e.get("payload", {}))) for e in processed_events) / len(processed_events) if processed_events else 0
    }
}

for event in processed_events:
    event_type = event.get("type", "unknown")
    severity = event.get("severity", "low")

    metrics["event_types"][event_type] = metrics["event_types"].get(event_type, 0) + 1
    metrics["severity_distribution"][severity] += 1

result = {
    "events": processed_events,
    "metrics": metrics,
    "status": "processed"
}
"""
    ]
})

# Queue for buffering high-volume streams
streaming_workflow.add_node("QueueNode", "event_queue", {
    "queue_type": "redis",
    "max_size": 10000,
    "batch_size": 100
})

# Connect streaming pipeline
streaming_workflow.add_connection("stream_source", "stream_processor", "stream_data", "data")
streaming_workflow.add_connection("stream_processor", "event_queue", "result", "items")

```

## 🔗 GraphQL Integration

### GraphQL Query Execution
```python
from kailash.nodes.api import GraphQLClientNode

# GraphQL client
workflow.add_node("GraphQLClientNode", "graphql", {
    "endpoint": "https://api.example.com/graphql"
})

# Execute with parameters
runtime.execute(workflow.build(), parameters={
    "graphql": {
        "query": """
            query GetUser($id: ID!) {
                user(id: $id) {
                    id
                    name
                    email
                    posts {
                        title
                        content
                    }
                }
            }
        """,
        "variables": {"id": "123"},
        "headers": {"Authorization": "Bearer ${TOKEN}"}
    }
})

```

## 🚀 Production Patterns

### Webhook Handler
```python
from kailash.nodes.api import WebhookReceiverNode

# Webhook receiver
workflow.add_node("WebhookReceiverNode", "webhook", {
    "port": 8080,
    "path": "/webhook"
})

# Process webhook payload
workflow.add_node("DataTransformer", "webhook_processor", {
    "transformations": [
        """
# Process incoming webhook
payload = data.get("payload", {})
headers = data.get("headers", {})

# Extract event type
event_type = payload.get("type", "unknown")
event_data = payload.get("data", {})

result = {
    "event_type": event_type,
    "event_data": event_data,
    "received_at": "2024-01-01T00:00:00Z",
    "source_ip": headers.get("x-forwarded-for", "unknown")
}
"""
    ]
})
workflow.add_connection("webhook", "request", "webhook_processor", "data")

```

### Batch API Processing
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Process multiple API calls
workflow.add_node("DataTransformer", "batch_processor", {
    "transformations": [
        """
# Prepare batch API requests
batch_requests = []
items = data.get("items", [])

for item in items:
    batch_requests.append({
        "url": f"/api/items/{item['id']}",
        "method": "GET",
        "item_id": item["id"]
    })

result = {"requests": batch_requests, "total": len(batch_requests)}
"""
    ]
})

# Execute batch with rate limiting
workflow.add_node("RateLimitedAPINode", "batch_api", {
    "requests_per_minute": 120,  # Higher limit for batch processing
    "max_retries": 2
})

```

## ⚡ Performance Optimization

### Connection Pooling
```python
# Use connection pooling for high-throughput APIs
workflow.add_node("HTTPRequestNode", "pooled_client", {
    "connection_pool_size": 10,
    "keep_alive": True
})

```

### Response Caching
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Cache API responses
workflow.add_node("RateLimitedAPINode", "cached_api", {
    "cache_responses": True,
    "cache_ttl": 300  # 5 minutes
})

```

## 🔗 Best Practices

### Performance
- **Use RateLimitedAPINode**: Built-in rate limiting and retry logic
- **Connection Pooling**: Reuse connections for multiple requests
- **Async Operations**: Use AsyncHTTPRequestNode for concurrent calls
- **Response Caching**: Cache responses where appropriate

### Security
- **Environment Variables**: Store API keys in environment variables
- **Token Refresh**: Use OAuth2Node for automatic token refresh
- **Request Validation**: Validate all incoming API requests
- **Error Handling**: Never expose internal errors in API responses

### Reliability
- **Retry Logic**: Built into RateLimitedAPINode
- **Circuit Breakers**: Implement circuit breaker patterns
- **Timeout Handling**: Set appropriate timeouts
- **Monitoring**: Log all API calls and responses

## ⚠️ Common Mistakes to Avoid

### Don't Use PythonCodeNode for HTTP Calls
```python
# WRONG: Manual HTTP implementation
# api_node = PythonCodeNode(code="response = requests.get('https://api.example.com')")  # DON'T DO THIS

# CORRECT: Use HTTPRequestNode or RateLimitedAPINode
workflow.add_node("HTTPRequestNode", "api_node", {
    "method": "GET",
    "url": "https://api.example.com"
})

```

### Don't Implement Rate Limiting Manually
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# WRONG: Manual rate limiting
# rate_limiter = PythonCodeNode(code="time.sleep(1); requests.get(url)")  # DON'T DO THIS

# CORRECT: Use RateLimitedAPINode
workflow.add_node("RateLimitedAPINode", "rate_limiter", {
    "requests_per_minute": 60
})

```

### Don't Hardcode API Keys
```python
# WRONG: Hardcoded credentials
# api_call = HTTPRequestNode(headers={"Authorization": "Bearer sk-123456"})  # DON'T DO THIS

# CORRECT: Use environment variables
workflow.add_node("HTTPRequestNode", "api_call", {
    "headers": {"Authorization": "Bearer ${API_TOKEN}"}
})

```

---

*These REST API patterns use the correct Kailash nodes for reliable, scalable API integrations. Always prefer specialized API nodes over manual implementations.*
