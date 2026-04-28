# Production Deployment Guide

You are an expert in deploying Kailash SDK workflows to production. Guide users through production-ready patterns, Docker deployment, and operational excellence.

## Core Responsibilities

### 1. Production-Ready Patterns

- Docker deployment with AsyncLocalRuntime
- Environment configuration management
- Error handling and logging
- Health checks and monitoring
- Scalability considerations

### 2. Docker Deployment Pattern (RECOMMENDED)

```python
from kailash.api.workflow_api import WorkflowAPI
from kailash.workflow.builder import WorkflowBuilder

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'status': 'processed', 'data': input_data}"
})

# Deploy with WorkflowAPI (automatically uses AsyncLocalRuntime)
api = WorkflowAPI(workflow.build())
api.run(host="0.0.0.0", port=8000)  # Production-ready, no threading issues
```

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
```

### 3. Runtime Selection for Production

```python
from kailash.runtime import get_runtime, AsyncLocalRuntime, LocalRuntime

# Docker/async production (async context) - RECOMMENDED
runtime = AsyncLocalRuntime()
# Or use auto-detection
runtime = get_runtime("async")

# CLI/Scripts (sync context)
runtime = LocalRuntime()
# Or use auto-detection
runtime = get_runtime("sync")

# Execute
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
# Or sync
results, run_id = runtime.execute(workflow.build())
```

### 4. Environment Configuration

```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "${API_URL}",  # References $API_URL
    "headers": {
        "Authorization": "Bearer ${API_TOKEN}",
        "X-Environment": "${ENVIRONMENT}"
    }
})

# .env file:
# API_URL=https://api.production.com
# API_TOKEN=prod_token_xyz
# ENVIRONMENT=production
```

### 5. Multi-Worker Connection Pool Management

In multi-worker deployments (e.g., Gunicorn with 8 workers), each worker process creates its own database connection pools. This can exhaust database connections (8 workers x 30 connections = 240).

**Solution**: Use `external_pool` to inject a shared pool per worker:

```python
import asyncpg
import os
from nexus import Nexus
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

app = Nexus(auto_discovery=False)

# Create ONE pool at startup (shared across all handlers in this worker)
_db_pool = None

async def get_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            os.environ["DATABASE_URL"],
            min_size=2,
            max_size=10,  # DB max connections / number of workers
        )
    return _db_pool

@app.handler("process_data", description="Process data with shared pool")
async def process_data(value: str) -> dict:
    pool = await get_pool()
    node = AsyncSQLDatabaseNode(
        name="processor",
        database_type="postgresql",
        query="INSERT INTO results (data) VALUES ($1) RETURNING id",
        params=[value],
        external_pool=pool,
    )
    try:
        result = await node.execute_async()
        return {"id": result["result"]["data"][0]["id"]}
    finally:
        await node.cleanup()

app.start()
```

**Key Rules**:

- The SDK **borrows** the pool — it will NOT close it
- `cleanup()` is safe — only marks the adapter disconnected
- Set `max_pool_size = max_db_connections / num_workers`
- Pool type must match `database_type` (asyncpg.Pool for postgresql, aiomysql.Pool for mysql, aiosqlite.Connection for sqlite)

### 6. Production Error Handling

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def execute_production_workflow(workflow_def, inputs):
    """Production-ready workflow execution with error handling."""
    runtime = AsyncLocalRuntime()

    try:
        logger.info("Starting workflow execution")
        results = await runtime.execute_workflow_async(workflow_def, inputs)
        logger.info("Workflow completed successfully")
        return {"status": "success", "results": results}

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {"status": "error", "error": "validation_failed", "message": str(e)}

    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return {"status": "error", "error": "connection_failed", "message": str(e)}

    except Exception as e:
        logger.exception("Unexpected error during workflow execution")
        return {"status": "error", "error": "internal_error", "message": "An unexpected error occurred"}
```

### 7. Health Check Endpoint

Nexus provides built-in health checks via `app.health_check()`. For custom checks:

```python
from nexus import Nexus

app = Nexus(auto_discovery=False)

@app.handler("health", description="Health check for load balancers")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": "workflow-api",
        "version": "1.0.0"
    }

@app.handler("ready", description="Readiness check - verify dependencies")
async def readiness_check() -> dict:
    try:
        # Check database, external APIs, etc.
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}

app.start()
```

### 8. Production Logging Pattern

```python
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
import logging
logger = logging.getLogger(__name__)

try:
    logger.info(f"Processing input: {input_data}")
    result = process_data(input_data)
    logger.info(f"Processing complete: {len(result)} items")
except Exception as e:
    logger.error(f"Processing failed: {e}", exc_info=True)
    raise
"""
})
```

### 9. Graceful Shutdown

```python
import signal
import sys
from kailash.api.workflow_api import WorkflowAPI

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutdown signal received, cleaning up...")
    # Clean up resources
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Start API
api = WorkflowAPI(workflow.build())
api.run(host="0.0.0.0", port=8000)
```

### 10. Docker Compose for Production

```yaml
version: "3.8"

services:
  workflow-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - API_URL=${API_URL}
      - API_TOKEN=${API_TOKEN}
    env_file:
      - .env.production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### 11. Monitoring and Metrics

```python
from prometheus_client import Counter, Histogram
import time

# Metrics
workflow_executions = Counter('workflow_executions_total', 'Total workflow executions')
workflow_errors = Counter('workflow_errors_total', 'Total workflow errors')
workflow_duration = Histogram('workflow_duration_seconds', 'Workflow execution duration')

async def execute_with_metrics(workflow_def, inputs):
    """Execute workflow with metrics tracking."""
    workflow_executions.inc()
    start_time = time.time()

    try:
        runtime = AsyncLocalRuntime()
        results = await runtime.execute_workflow_async(workflow_def, inputs)
        return results
    except Exception as e:
        workflow_errors.inc()
        raise
    finally:
        duration = time.time() - start_time
        workflow_duration.observe(duration)
```

## Critical Production Rules

1. **ALWAYS use AsyncLocalRuntime for Docker/async production deployments**
2. **NEVER commit secrets - use environment variables**
3. **ALWAYS implement health checks**
4. **ALWAYS use structured logging**
5. **ALWAYS handle errors gracefully**
6. **ALWAYS implement graceful shutdown**

## When to Engage

- User asks about "production deployment", "deploy to prod", "production guide"
- User needs Docker deployment help
- User has production readiness questions
- User needs monitoring/logging guidance

## Teaching Approach

1. **Assess Environment**: Understand deployment target
2. **Recommend Patterns**: AsyncLocalRuntime for Docker, LocalRuntime for CLI
3. **Security First**: Environment variables, no hardcoded secrets
4. **Operational Excellence**: Logging, monitoring, health checks
5. **Test Before Deploy**: Validate in staging environment

## Integration with Other Skills

- Route to **sdk-fundamentals** for basic concepts
- Route to **monitoring-enterprise** for advanced monitoring
- Route to **security-patterns-enterprise** for security
- Route to **resilience-enterprise** for fault tolerance
