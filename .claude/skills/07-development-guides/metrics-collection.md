# Metrics Collection

You are an expert in metrics collection and telemetry for Kailash SDK. Guide users through implementing comprehensive metrics, instrumentation, and monitoring.

## Core Responsibilities

### 1. Prometheus Metrics
```python
from prometheus_client import Counter, Histogram, Gauge, Summary

# Define metrics
workflow_executions = Counter(
    'workflow_executions_total',
    'Total workflow executions',
    ['workflow_id', 'status']
)

workflow_duration = Histogram(
    'workflow_duration_seconds',
    'Workflow execution duration',
    ['workflow_id']
)

active_workflows = Gauge(
    'active_workflows',
    'Currently executing workflows'
)

workflow_latency = Summary(
    'workflow_latency_seconds',
    'Workflow execution latency'
)
```

### 2. Instrumenting Workflows
```python
import time

workflow.add_node("PythonCodeNode", "instrumented", {
    "code": """
# Track execution
workflow_executions.labels(workflow_id=workflow_id, status='started').inc()
active_workflows.inc()

start_time = time.time()

try:
    # Execute workflow logic
    result = process_data(input_data)

    # Record success metrics
    duration = time.time() - start_time
    workflow_duration.labels(workflow_id=workflow_id).observe(duration)
    workflow_executions.labels(workflow_id=workflow_id, status='success').inc()

except Exception as e:
    # Record failure metrics
    workflow_executions.labels(workflow_id=workflow_id, status='failed').inc()
    raise

finally:
    active_workflows.dec()
"""
})
```

### 3. Metrics Endpoint
```python
from nexus import Nexus
from prometheus_client import make_asgi_app

app = Nexus(auto_discovery=False)

# Expose Prometheus metrics via a handler
@app.handler("health", description="Health check")
async def health() -> dict:
    return {"status": "healthy"}

# For Prometheus scraping, mount the ASGI app on the underlying server:
# metrics_app = make_asgi_app()
# app.include_router or middleware integration for /metrics
```

## When to Engage
- User asks about "metrics", "telemetry", "instrumentation", "collect metrics"
- User needs monitoring
- User wants Prometheus integration

## Integration with Other Skills
- Route to **monitoring-enterprise** for monitoring patterns
- Route to **production-deployment-guide** for deployment
