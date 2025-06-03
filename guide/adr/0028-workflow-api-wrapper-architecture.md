# ADR-0028: Workflow API Wrapper Architecture

**Status:** Accepted
**Date:** 2025-06-03
**Decision Makers:** Development Team

## Context

Kailash workflows provide powerful data processing and AI capabilities, but they require programmatic execution through the SDK. Many use cases would benefit from exposing workflows as REST APIs for:

1. **External Integration**: Allow non-Python applications to execute workflows
2. **Microservice Architecture**: Deploy workflows as independent services
3. **Simplified Deployment**: No SDK installation required for clients
4. **Standard Protocols**: Use HTTP/REST for universal compatibility
5. **API Management**: Leverage existing API infrastructure (gateways, monitoring)

## Decision

We will implement a lean API wrapper system that can expose any Kailash workflow as a REST API with minimal configuration.

### Architecture Components

1. **WorkflowAPI Class**
   - Generic wrapper that works with any workflow
   - Built on FastAPI for production readiness
   - Supports sync, async, and streaming execution modes
   - Automatic OpenAPI documentation generation

2. **Specialized API Classes**
   - Domain-specific wrappers (e.g., HierarchicalRAGAPI)
   - Provide tailored endpoints for specific use cases
   - Inherit from WorkflowAPI for consistency

3. **Factory Pattern**
   - `create_workflow_api()` function for easy instantiation
   - Supports different API types through configuration
   - Extensible for future API types

### Key Features

1. **Minimal Configuration**
   ```python
   workflow = create_your_workflow()
   api = WorkflowAPI(workflow)
   api.run(port=8000)
   ```

2. **Standard REST Endpoints**
   - `POST /execute` - Execute workflow with inputs
   - `GET /workflow/info` - Get workflow metadata
   - `GET /status/{id}` - Check async execution status
   - `GET /health` - Health check endpoint

3. **Execution Modes**
   - **Sync**: Wait for completion (default)
   - **Async**: Return immediately with execution ID
   - **Stream**: Server-sent events for progress

4. **Extensibility**
   - Add custom endpoints via `api.app`
   - Integrate middleware (CORS, auth, etc.)
   - Custom request/response models

## Implementation Details

### Core API Wrapper

```python
class WorkflowAPI:
    def __init__(self, workflow: Union[WorkflowBuilder, Workflow], ...):
        self.workflow_graph = self._get_graph(workflow)
        self.runtime = LocalRuntime()
        self.app = FastAPI(...)
        self._setup_routes()
```

### Request/Response Models

```python
class WorkflowRequest(BaseModel):
    inputs: Dict[str, Any]
    config: Optional[Dict[str, Any]]
    mode: ExecutionMode = ExecutionMode.SYNC

class WorkflowResponse(BaseModel):
    outputs: Dict[str, Any]
    execution_time: float
    workflow_id: str
    version: str
```

### Specialized APIs

```python
class HierarchicalRAGAPI(WorkflowAPI):
    def _setup_rag_routes(self):
        # Add /documents and /query endpoints
        # Transform between RAG-specific and workflow formats
```

## Consequences

### Positive

1. **Easy Adoption**: Any workflow becomes an API in 3 lines of code
2. **Production Ready**: Built on FastAPI with automatic docs, validation
3. **Flexible Deployment**: Development server to production clusters
4. **Standard Interface**: REST/HTTP works with any client
5. **Maintains Separation**: Workflow logic stays independent of API concerns

### Negative

1. **Additional Dependency**: Requires FastAPI and uvicorn
2. **Network Overhead**: HTTP adds latency vs direct execution
3. **Serialization Limits**: Complex objects need JSON serialization
4. **State Management**: Workflows must be stateless between requests

### Neutral

1. **Security Considerations**: APIs need proper authentication/authorization
2. **Performance Trade-offs**: HTTP overhead vs deployment flexibility
3. **Monitoring Needs**: Requires API monitoring infrastructure

## Examples

### Simple Deployment

```python
from kailash.api.workflow_api import WorkflowAPI
from my_workflows import data_processing_workflow

api = WorkflowAPI(data_processing_workflow)
api.run(port=8000)
```

### Production Configuration

```python
api = WorkflowAPI(
    workflow,
    app_name="Data Processing API",
    version="2.0.0"
)

# Add authentication
from fastapi.security import HTTPBearer
security = HTTPBearer()

@api.app.post("/secure/execute", dependencies=[Depends(security)])
async def secure_execute(request: WorkflowRequest):
    return await execute_workflow(request)

# Production server
api.run(
    host="0.0.0.0",
    port=443,
    ssl_keyfile="key.pem",
    ssl_certfile="cert.pem",
    workers=4
)
```

### Client Usage

```bash
# Execute workflow
curl -X POST http://api.example.com/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"data": "process this"}}'

# Check workflow info
curl http://api.example.com/workflow/info
```

## Related ADRs

- ADR-0004: Workflow Representation (defines workflow structure)
- ADR-0005: Local Execution Strategy (runtime used by API)
- ADR-0015: API Integration Architecture (REST/HTTP nodes)
- ADR-0022: MCP Integration Architecture (potential MCP server mode)

## References

- FastAPI Documentation: https://fastapi.tiangolo.com/
- RESTful API Design: https://restfulapi.net/
- OpenAPI Specification: https://swagger.io/specification/
