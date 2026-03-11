# Understanding FastAPI Mount Behavior in Nexus

## Overview

When you register a workflow with Nexus, you may notice that workflow-specific endpoints don't appear in the main OpenAPI schema at `/openapi.json`. **This is intentional FastAPI behavior, not a bug.**

This guide explains:
- Why mounted routes don't appear in the main OpenAPI schema
- How to discover workflow endpoints
- What endpoints are available for each workflow
- Why this design benefits Nexus architecture

## Quick Answer

**TL;DR**: Nexus uses FastAPI's `.mount()` to create isolated sub-applications for each workflow. By design, mounted sub-applications have their own OpenAPI schemas that don't appear in the parent application's schema. Your workflows ARE accessible—you just need to know where to look.

---

## The Key Point

When FastAPI `.mount()` is used to attach a sub-application, two things happen:

1. ✅ **Routes ARE accessible** - You can make requests to mounted endpoints
2. ❌ **Routes do not appear in parent OpenAPI** - The parent's `/openapi.json` won't list them

This is **by design** in FastAPI, not a Nexus limitation.

### Example

```python
# When Nexus does this internally:
app.mount("/workflows/my_workflow", workflow_sub_app)

# You can access:
POST /workflows/my_workflow/execute        ✅ Works
GET  /workflows/my_workflow/workflow/info  ✅ Works
GET  /workflows/my_workflow/health         ✅ Works

# But /openapi.json won't show these routes
GET /openapi.json  # Won't include /workflows/my_workflow/* paths
```

---

## Why This Happens

FastAPI's mounting design supports **microservices architecture** where:
- Each mounted sub-application is completely independent
- Sub-applications have their own OpenAPI schemas
- The parent application doesn't need to know about sub-app internals
- Sub-applications can be updated without affecting the parent

This allows Nexus to:
- Dynamically register workflows at runtime
- Keep workflows isolated from each other
- Provide workflow-specific documentation
- Support independent workflow versioning

---

## How Nexus Uses Mounting in Practice

### Workflow Registration Flow

When you call `app.register("contact_search", workflow)`:

1. **Nexus creates a WorkflowAPI sub-application** for that workflow
2. **WorkflowAPI generates three standard endpoints**:
   - `POST /execute` - Execute the workflow
   - `GET /workflow/info` - Get workflow metadata
   - `GET /health` - Health check
3. **Nexus mounts the sub-app** at `/workflows/contact_search`
4. **Endpoints become accessible** at:
   - `POST /workflows/contact_search/execute`
   - `GET /workflows/contact_search/workflow/info`
   - `GET /workflows/contact_search/health`

### Why This Architecture?

**Benefits**:
- ✅ **Dynamic Registration** - Add workflows at runtime without restarting
- ✅ **Isolation** - One workflow's errors don't affect others
- ✅ **Scalability** - Each workflow can have its own resources
- ✅ **Modularity** - Workflows are self-contained units

**Trade-off**:
- ⚠️ **Discovery Challenge** - Main OpenAPI doesn't list workflow endpoints
- ✅ **Solution** - Use `/workflows` endpoint to discover registered workflows

---

## Discovering Workflow Endpoints

Since mounted routes don't appear in the main OpenAPI schema, use these methods to discover workflow endpoints:

### Method 1: List All Workflows

```bash
curl http://localhost:8000/workflows
```

Response:
```json
{
  "contact_search": {
    "type": "embedded",
    "description": "Search contacts by sector",
    "version": "1.0.0",
    "endpoints": [
      "/workflows/contact_search/execute",
      "/workflows/contact_search/workflow/info",
      "/workflows/contact_search/health"
    ]
  }
}
```

### Method 2: Check Registration Logs

When you register a workflow, Nexus logs all available endpoints:

```
✅ Workflow 'contact_search' registered successfully!
   📡 API Endpoints:
      • POST   http://localhost:8000/workflows/contact_search/execute
      • GET    http://localhost:8000/workflows/contact_search/workflow/info
      • GET    http://localhost:8000/workflows/contact_search/health
   🤖 MCP Tool: contact_search
   💻 CLI Command: nexus execute contact_search
```

**Tip**: Copy these URLs directly from the logs for testing!

### Method 3: Get Workflow Info

```bash
curl http://localhost:8000/workflows/contact_search/workflow/info
```

Returns workflow metadata including available endpoints, structure, and parameters.

---

## Standard Endpoint Pattern

Every registered workflow follows this consistent pattern:

| Method | Path | Description | Example |
|--------|------|-------------|---------|
| POST | `/workflows/{name}/execute` | Execute workflow with input parameters | `POST /workflows/contact_search/execute` |
| GET | `/workflows/{name}/workflow/info` | Get workflow metadata and structure | `GET /workflows/contact_search/workflow/info` |
| GET | `/workflows/{name}/health` | Check workflow health status | `GET /workflows/contact_search/health` |

### Usage Example

```python
import requests

BASE_URL = "http://localhost:8000"

# Execute workflow
response = requests.post(
    f"{BASE_URL}/workflows/contact_search/execute",
    json={"inputs": {"sector": "Technology", "limit": 50}}
)
print(response.json())

# Get workflow info
response = requests.get(
    f"{BASE_URL}/workflows/contact_search/workflow/info"
)
print(response.json())

# Health check
response = requests.get(
    f"{BASE_URL}/workflows/contact_search/health"
)
print(response.json())
```

---

## Common Errors and Solutions

### Error 1: 404 Not Found

**Symptom**:
```bash
$ curl http://localhost:8000/workflows/my_workflow
{"detail":"Not Found"}
```

**Cause**: Missing the `/execute` path

**Solution**: Add the endpoint path:
```bash
# ❌ Wrong - just the workflow path
curl http://localhost:8000/workflows/my_workflow

# ✅ Correct - with /execute endpoint
curl -X POST http://localhost:8000/workflows/my_workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {}}'
```

### Error 2: "Workflow Not Listed in OpenAPI"

**Symptom**: `/openapi.json` doesn't show workflow endpoints

**Cause**: This is normal FastAPI mount behavior (by design)

**Solution**: Use `/workflows` endpoint to discover workflows instead of relying on OpenAPI schema:
```bash
curl http://localhost:8000/workflows
```

### Error 3: "Can't Find Workflow Documentation"

**Symptom**: Looking for workflow-specific docs in main `/docs`

**Cause**: Each mounted workflow has its own documentation context

**Solution**: Access workflow info endpoint for metadata:
```bash
curl http://localhost:8000/workflows/my_workflow/workflow/info
```

Or use the main `/docs` endpoint which includes workflow discovery information.

---

## Further Reading

### FastAPI Official Documentation
- **[Sub Applications](https://fastapi.tiangolo.com/advanced/sub-applications/)** - FastAPI's mounting documentation
- **[OpenAPI Schemas](https://fastapi.tiangolo.com/how-to/extending-openapi/)** - Understanding OpenAPI generation

### Related Nexus Documentation
- **[Workflow Registration Guide](../user-guides/workflow-registration.md)** - How to register workflows
- **[Basic Usage Guide](../getting-started/basic-usage.md)** - Getting started with Nexus
- **[Multi-Channel Usage](../user-guides/multi-channel-usage.md)** - API, CLI, and MCP access

---

## Key Takeaways

1. ✅ **Mounted routes ARE accessible** - They work correctly
2. ❌ **Mounted routes DON'T appear in parent OpenAPI** - This is by design
3. 🔍 **Use `/workflows` to discover** - Lists all registered workflows
4. 📖 **Check registration logs** - Shows exact endpoint URLs
5. 🏗️ **Architecture benefit** - Enables dynamic, isolated workflows

### Why This Design is Good

FastAPI's mount pattern enables Nexus to:
- Register workflows dynamically at runtime
- Isolate workflow failures from affecting other workflows
- Support independent workflow lifecycle management
- Scale workflows independently
- Provide clean separation of concerns

The "missing" OpenAPI routes are actually an intentional design choice that makes Nexus more powerful and flexible.

---

## Testing Your Understanding

Try this quick test:

```bash
# 1. Start Nexus and register a workflow
# 2. Check main OpenAPI (won't show workflow routes)
curl http://localhost:8000/openapi.json | grep "/workflows/my_workflow"
# Result: Nothing found ✅ Expected

# 3. But the workflow IS accessible
curl -X POST http://localhost:8000/workflows/my_workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {}}'
# Result: Workflow executes ✅ Works!

# 4. Discover workflows the right way
curl http://localhost:8000/workflows
# Result: Shows my_workflow ✅ Discovery works!
```

If all three results match, you understand FastAPI mount behavior correctly!

---

**Last Updated**: 2025-10-08
**Related Issue**: FastAPI mount behavior clarification
**Status**: Complete
