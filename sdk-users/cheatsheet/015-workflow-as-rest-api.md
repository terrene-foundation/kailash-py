# Workflow as REST API

## Quick Start (Simple API)

For simple single-workflow APIs, use `WorkflowAPI`:

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.api.workflow_api import WorkflowAPI
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformerNode

# Create workflow
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode())
workflow.add_node("transformer", DataTransformerNode())
workflow.connect("reader", "transformer")

# Expose as REST API
api = WorkflowAPI(workflow)
api.run(port=8000)

# Endpoints created:
# POST /execute - Execute workflow
# GET /workflow/info - Get workflow metadata
# GET /health - Health check
# GET /docs - OpenAPI documentation

```

## Advanced Configuration

### Custom Routes
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

api = WorkflowAPI(
    workflow,
    prefix="/api/v1",
    title="Data Processing Service",
    version="1.0.0"
)

# Add custom endpoints
@api.get("/status/{run_id}")
async def get_status(run_id: str):
    return {"run_id": run_id, "status": "completed"}

@api.post("/batch")
async def process_batch(files: list):
    results = []
    for file in files:
        result, _ = api.execute({"reader": {"file_path": file}})
        results.append(result)
    return {"results": results}

```

### Authentication
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

api = WorkflowAPI(workflow, dependencies=[Depends(security)])

# All endpoints now require Bearer token

```

### Input Validation
```python
from pydantic import BaseModel, Field

class ExecuteRequest(BaseModel):
    file_path: str = Field(..., description="Path to CSV file")
    transform_config: dict = Field(default={}, description="Transform options")

    class Config:
        schema_extra = {
            "example": {
                "file_path": "data/sales.csv",
                "transform_config": {"normalize": True}
            }
        }

api = WorkflowAPI(workflow, request_model=ExecuteRequest)

```

## Production Patterns

### Async Execution
```python
# Enable async with background tasks
api = WorkflowAPI(
    workflow,
    async_mode=True,
    max_workers=10
)

# Returns immediately with run_id
# POST /execute -> {"run_id": "abc123", "status": "queued"}
# GET /status/abc123 -> {"status": "completed", "result": {...}}

```

### Rate Limiting
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
api = WorkflowAPI(workflow)

@api.post("/execute")
@limiter.limit("10/minute")
async def execute_limited(request: ExecuteRequest):
    return await api.execute_workflow(request)

```

### Error Handling
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

from fastapi import HTTPException

@api.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "type": "validation_error"}
    )

@api.exception_handler(Exception)
async def general_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "id": generate_error_id()}
    )

```

## Deployment Options

### Docker
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "api.py"]
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workflow-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: workflow-api
  template:
    metadata:
      labels:
        app: workflow-api
    spec:
      containers:
      - name: api
        image: workflow-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: WORKERS
          value: "4"
```

### AWS Lambda
```python
from mangum import Mangum

api = WorkflowAPI(workflow)
handler = Mangum(api.app)  # AWS Lambda handler

```

## Monitoring

```python
from prometheus_client import Counter, Histogram
import time

# Metrics
executions = Counter('workflow_executions_total', 'Total executions')
execution_time = Histogram('workflow_execution_seconds', 'Execution time')

@api.middleware("http")
async def add_metrics(request, call_next):
    start = time.time()
    response = await call_next(request)

    execution_time.observe(time.time() - start)
    if request.url.path == "/execute":
        executions.inc()

    return response

```

## Common Patterns

### Health Checks
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

@api.get("/health/detailed")
async def detailed_health():
    return {
        "status": "healthy",
workflow = Workflow("example", name="Example")
workflow.id,
workflow = Workflow("example", name="Example")
workflow.nodes),
        "uptime": get_uptime(),
        "memory_usage": get_memory_usage()
    }

```

### Webhook Integration
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

@api.post("/webhook/{source}")
async def webhook_handler(source: str, payload: dict):
    # Transform webhook data to workflow parameters
    params = transform_webhook_payload(source, payload)
    result, run_id = await api.execute_workflow(params)

    # Send result to callback URL if provided
    if callback_url := payload.get("callback_url"):
        await send_callback(callback_url, result)

    return {"run_id": run_id}

```

## Common Pitfalls

1. **No Input Validation**: Always validate inputs with Pydantic models
2. **Blocking Operations**: Use async_mode for long-running workflows
3. **Missing Error Handling**: Add exception handlers for production
4. **No Rate Limiting**: Protect API from abuse

## Enterprise Approach (Recommended)

For production applications with multiple workflows, real-time updates, and enterprise features, use the middleware gateway:

```python
from kailash.middleware import create_gateway

# Create full-featured gateway
gateway = create_gateway(
    title="My Enterprise API",
    cors_origins=["http://localhost:3000"],
    enable_auth=True
)

# Workflows are created dynamically via API
# Real-time updates via WebSocket/SSE
# Session-based multi-tenancy
# Built-in auth, monitoring, and more

gateway.run(port=8000)
```

See the [Middleware Migration Guide](../middleware/MIGRATION.md) for details on migrating from `WorkflowAPIGateway` to the new middleware approach.

## Next Steps
- [Middleware patterns](../middleware/README.md)
- [Production deployment](../enterprise/middleware-patterns.md)
- [Migration guide](../middleware/MIGRATION.md)
