---
skill: nexus-api-patterns
description: REST API usage patterns, endpoints, requests, and responses for Nexus workflows
priority: HIGH
tags: [nexus, api, rest, http, endpoints]
---

# Nexus API Patterns

## Auto-Generated Endpoints

Every registered workflow gets these automatically:

```bash
POST /workflows/{workflow_name}/execute   # Execute workflow
GET  /workflows/{workflow_name}/schema    # Get input/output schema
GET  /workflows                           # List all workflows
GET  /health                              # Health check
GET  /docs                                # OpenAPI docs
```

## Custom Endpoints

```python
from nexus import Nexus
from nexus.http import Request

app = Nexus()

@app.endpoint("/api/conversations/{conversation_id}", methods=["GET"], rate_limit=50)
async def get_conversation(conversation_id: str):
    return await app._execute_workflow("chat_workflow", {"id": conversation_id})

@app.endpoint("/api/search")
async def search(q: str, limit: int = 10, offset: int = 0):
    return await app._execute_workflow("search_workflow", {"query": q, "limit": limit, "offset": offset})

@app.endpoint("/api/messages/{msg_id}", methods=["GET", "PUT", "DELETE"])
async def manage_message(msg_id: str, request: Request):
    if request.method == "GET":
        return await app._execute_workflow("get_message", {"id": msg_id})
    elif request.method == "PUT":
        body = await request.json()
        return await app._execute_workflow("update_message", {"id": msg_id, **body})
    elif request.method == "DELETE":
        return await app._execute_workflow("delete_message", {"id": msg_id})
```

Key features (v1.1.0): path params, query params with type coercion, per-endpoint rate limiting (default 100/min), input size limits (10MB), HTTP methods GET/POST/PUT/DELETE/PATCH.

## Request / Response Format

```json
// Request
{"inputs": {"param1": "value1"}, "session_id": "optional", "context": {"user_id": "user123"}}

// Success response
{"success": true, "result": {...}, "workflow_id": "wf-12345", "execution_time": 1.23}

// Error response
{"success": false, "error": {"type": "ValidationError", "message": "...", "details": {...}}}
```

## API Configuration

```python
app = Nexus(api_port=8000, api_host="0.0.0.0", enable_docs=True, enable_cors=True)
app.api.response_compression = True
app.api.request_timeout = 30
app.api.max_concurrent_requests = 100
```

## Authentication

```bash
curl -X POST http://localhost:8000/workflows/secure-workflow/execute \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"data": "value"}}'
```

## Session Management

```bash
curl -X POST http://localhost:8000/workflows/process/execute \
  -H "X-Session-ID: session-123" -d '{"inputs": {"step": 1}}'

# Continue same session
curl -X POST http://localhost:8000/workflows/process/execute \
  -H "X-Session-ID: session-123" -d '{"inputs": {"step": 2}}'
```

## SSE Streaming

```python
# Python client
import httpx
with httpx.stream("POST", "http://localhost:8000/execute",
                  json={"inputs": {}, "mode": "stream"}) as response:
    for line in response.iter_lines():
        if line.startswith('data:'):
            data = json.loads(line[5:])
```

```javascript
// Browser client
const es = new EventSource("/workflows/chat/execute?mode=stream");
es.addEventListener("start", (e) =>
  console.log("Started:", JSON.parse(e.data).workflow_id),
);
es.addEventListener("complete", (e) =>
  console.log("Result:", JSON.parse(e.data).result),
);
es.addEventListener("error", (e) =>
  console.error("Error:", JSON.parse(e.data).error),
);
```

Event types: `start`, `complete`, `error`, `keepalive`.

## Batch Operations

```bash
curl -X POST http://localhost:8000/workflows/batch \
  -d '{"workflows": [{"name": "wf1", "inputs": {...}}, {"name": "wf2", "inputs": {...}}]}'
```

## Python Clients

```python
# Sync client
import requests

class NexusClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    def execute_workflow(self, name, inputs, session_id=None):
        headers = {"Content-Type": "application/json"}
        if session_id:
            headers["X-Session-ID"] = session_id
        response = self.session.post(f"{self.base_url}/workflows/{name}/execute",
            json={"inputs": inputs}, headers=headers)
        response.raise_for_status()
        return response.json()

# Async client
import aiohttp, asyncio

class AsyncNexusClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    async def execute_workflow(self, name, inputs):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/workflows/{name}/execute",
                json={"inputs": inputs}) as response:
                return await response.json()

    async def execute_many(self, workflows):
        return await asyncio.gather(*[self.execute_workflow(w["name"], w["inputs"]) for w in workflows])
```

## Rate Limiting & CORS

```python
app = Nexus(rate_limit=1000, rate_limit_burst=100)

app.api.cors_enabled = True
app.api.cors_origins = ["https://example.com"]
app.api.cors_methods = ["GET", "POST"]
app.api.cors_credentials = True
```

## Error Status Codes

| Code | Meaning             |
| ---- | ------------------- |
| 200  | Success             |
| 400  | Invalid input       |
| 401  | Unauthorized        |
| 404  | Workflow not found  |
| 429  | Rate limit exceeded |
| 500  | Execution failed    |
| 503  | Server overloaded   |

## Health & Metrics

```bash
curl http://localhost:8000/health
# {"status": "healthy", "version": "1.0.0", "uptime": 3600, "workflows": 5}

curl http://localhost:8000/metrics  # Prometheus format
```

## Testing API Endpoints

```python
import pytest
import requests

class TestNexusAPI:
    base_url = "http://localhost:8000"

    def test_workflow_execution(self):
        response = requests.post(f"{self.base_url}/workflows/test-workflow/execute",
            json={"inputs": {"param": "value"}})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result" in data

    def test_workflow_not_found(self):
        response = requests.post(f"{self.base_url}/workflows/nonexistent/execute",
            json={"inputs": {}})
        assert response.status_code == 404

    def test_invalid_input(self):
        response = requests.post(f"{self.base_url}/workflows/test-workflow/execute",
            json={"inputs": {"wrong_param": "value"}})
        assert response.status_code == 400

    def test_health_check(self):
        response = requests.get(f"{self.base_url}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

## API Versioning

```python
app = Nexus(api_prefix="/api/v1")
# Endpoints: POST /api/v1/workflows/{name}/execute
```
