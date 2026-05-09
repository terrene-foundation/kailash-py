---
skill: nexus-api-patterns
description: REST API usage patterns, endpoints, requests, and responses for Nexus workflows
priority: HIGH
tags: [nexus, api, rest, http, endpoints]
---

# Nexus API Patterns

## Auto-Generated Endpoints

Every registered workflow gets these endpoints automatically:

```bash
POST /workflows/{workflow_name}/execute   # Execute workflow
GET  /workflows/{workflow_name}/schema    # Get input/output schema
GET  /workflows                           # List all workflows
GET  /health                              # Health check
```

No additional configuration needed -- `app.register("name", workflow.build())` creates all of these.

## Custom Endpoints

Nexus supports registering API-only endpoints with path parameters, query parameters, and per-endpoint rate limiting. The exact API for custom endpoints (decorator vs imperative, method signatures) varies by SDK.

See language-specific variant for custom endpoint registration syntax.

## Request / Response Format

```json
// Request
{"inputs": {"param1": "value1"}, "session_id": "optional"}

// Success response
{"success": true, "result": {...}, "workflow_id": "wf-12345", "execution_time": 1.23}

// Error response
{"success": false, "error": {"type": "ValidationError", "message": "..."}}
```

## Authentication

```bash
curl -X POST http://localhost:8000/workflows/secure-workflow/execute \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"data": "value"}}'
```

Authentication is configured via the plugin system: `app.add_plugin(auth_plugin)`. See [nexus-auth-plugin](nexus-auth-plugin.md).

## Session Management

```bash
# Start session
curl -X POST http://localhost:8000/workflows/process/execute \
  -H "X-Session-ID: session-123" -d '{"inputs": {"step": 1}}'

# Continue same session
curl -X POST http://localhost:8000/workflows/process/execute \
  -H "X-Session-ID: session-123" -d '{"inputs": {"step": 2}}'
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
# {"status": "healthy", "version": "...", "uptime": 3600, "workflows": 5}
```

Metrics endpoint availability and format depend on monitoring configuration.

## API Versioning

```
app = Nexus(api_prefix="/api/v1")
# Endpoints: POST /api/v1/workflows/{name}/execute
```

## Batch Operations

Multiple workflows can be executed in a single request:

```bash
curl -X POST http://localhost:8000/workflows/batch \
  -d '{"workflows": [{"name": "wf1", "inputs": {...}}, {"name": "wf2", "inputs": {...}}]}'
```

## Testing API Endpoints

Test the auto-generated endpoints with standard HTTP clients:

```bash
# Test execution
curl -X POST http://localhost:8000/workflows/test-workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"param": "value"}}'

# Test 404
curl -X POST http://localhost:8000/workflows/nonexistent/execute

# Test health
curl http://localhost:8000/health
```

## Key Takeaways

- Every registered workflow gets REST endpoints automatically
- Standard request/response JSON format across all SDKs
- Session management via `X-Session-ID` header
- API versioning via `api_prefix` constructor parameter
- Custom endpoint registration is language-specific (see variant)

See language-specific variant for custom endpoint syntax, SSE streaming, client libraries, CORS configuration, and rate limiting details.
