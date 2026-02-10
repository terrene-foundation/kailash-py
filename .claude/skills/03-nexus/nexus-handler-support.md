---
skill: nexus-handler-support
description: Register Python functions as multi-channel workflows using @app.handler() decorator or register_handler() method
priority: HIGH
tags: [nexus, handler, workflow, decorator, function]
---

# Nexus Handler Support

Register Python functions directly as multi-channel workflows, bypassing PythonCodeNode sandbox restrictions.

## When to Use

- Service orchestration (database, external APIs)
- Async operations (requires `asyncio`)
- Application module imports
- Full Python access without sandbox

## Quick Reference

### Decorator Pattern

```python
from nexus import Nexus

app = Nexus()

@app.handler("greet")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}

app.start()
```

### Non-Decorator Pattern

```python
from my_app.handlers import process_order

app = Nexus()
app.register_handler("process_order", process_order)
app.start()
```

## API

### @app.handler() Decorator

```python
@app.handler(
    name: str,                      # Required: workflow name
    description: str = "",          # Optional: documentation
    tags: Optional[List[str]] = None  # Optional: categorization
)
```

### app.register_handler() Method

```python
app.register_handler(
    name: str,                      # Required: workflow name
    handler_func: Callable,         # Required: function to register
    description: str = "",          # Optional: documentation
    tags: Optional[List[str]] = None,  # Optional: categorization
    input_mapping: Optional[Dict[str, str]] = None  # Optional: param mapping
)
```

## Parameter Type Mapping

| Python Type            | Workflow Type | Required         |
| ---------------------- | ------------- | ---------------- |
| `str`                  | `str`         | Yes (no default) |
| `int`                  | `int`         | Yes (no default) |
| `float`                | `float`       | Yes (no default) |
| `bool`                 | `bool`        | Yes (no default) |
| `dict`                 | `dict`        | Yes (no default) |
| `list`                 | `list`        | Yes (no default) |
| `Optional[T]`          | `T`           | No               |
| Parameter with default | Any           | No               |
| No annotation          | `str`         | Varies           |

## Core SDK: HandlerNode

For direct Core SDK usage without Nexus:

```python
from kailash.nodes.handler import HandlerNode, make_handler_workflow
from kailash.runtime import AsyncLocalRuntime

async def my_function(x: int) -> dict:
    return {"doubled": x * 2}

# Option 1: Use HandlerNode directly
node = HandlerNode(handler=my_function)

# Option 2: Build a complete workflow
workflow = make_handler_workflow(my_function, "handler")
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(
    workflow, inputs={"x": 5}
)
```

## Sandbox Mode Configuration

For PythonCodeNode with blocked imports:

```python
from kailash.nodes.code.python import PythonCodeNode

# Bypass sandbox restrictions
node = PythonCodeNode(
    name="trusted_node",
    code="import subprocess\nresult = subprocess.run(['ls'])",
    sandbox_mode="trusted"  # Default: "restricted"
)
```

| Mode           | Behavior                            |
| -------------- | ----------------------------------- |
| `"restricted"` | Enforces module allowlist (default) |
| `"trusted"`    | Bypasses import checks              |

## Common Patterns

### Database Operations

```python
@app.handler("get_user")
async def get_user(user_id: int) -> dict:
    from my_app.db import get_session
    async with get_session() as session:
        user = await session.get(User, user_id)
        return {"user": user.to_dict() if user else None}
```

### External API Calls

```python
@app.handler("fetch_data")
async def fetch_data(url: str) -> dict:
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return {"data": response.json()}
```

### Sync Handlers (run in executor)

```python
@app.handler("sync_operation")
def sync_operation(data: str) -> dict:
    # Automatically runs in thread pool executor
    return {"processed": data.upper()}
```

## Migration: PythonCodeNode to Handler

### Before (fails at runtime)

```python
workflow.add_node("PythonCodeNode", "process", {
    "code": "import asyncio\nfrom my_app import Service\n..."
})
app.register("process", workflow.build())
```

### After (works)

```python
@app.handler("process")
async def process(data: dict) -> dict:
    from my_app import Service
    return await Service().process(data)
```

## Handler Registry

Introspect registered handlers:

```python
# Access handler metadata
print(app._handler_registry)
# {
#     "greet": {
#         "handler": <function>,
#         "description": "...",
#         "tags": [...],
#         "workflow": <Workflow>
#     }
# }
```

## Registration-Time Validation

Nexus warns at registration time if PythonCodeNode uses blocked imports:

```
WARNING: Workflow 'my_workflow': PythonCodeNode node 'code_node' imports
         'asyncio' which is not in the sandbox allowlist.
         Consider using @app.handler() to bypass the sandbox.
```

## Best Practices

1. **Use handlers for service orchestration** - they provide full Python access
2. **Add type annotations** - used for parameter derivation
3. **Return dictionaries** - non-dict returns are wrapped as `{"result": value}`
4. **Use async functions for I/O** - sync functions run in executor
5. **Add descriptions** - appear in API docs and MCP tools

## Related Skills

- [nexus-workflow-registration](#) - All registration patterns
- [nexus-quickstart](#) - Basic Nexus setup
- [nexus-dataflow-integration](#) - DataFlow integration

## Migration Documentation

For comprehensive migration from legacy PythonCodeNode workflows to handlers:

- `apps/kailash-nexus/docs/migration/handler-migration-guide.md` - 5 migration patterns, 6-phase checklist, "When NOT to Migrate" guidance
- `apps/kailash-nexus/docs/migration/real-project-patterns.md` - 8 real-world patterns from 3 production projects (382K LOC)

### Key Migration Insight

HandlerNode's `_derive_params_from_signature()` maps complex generic types (e.g., `List[dict]`) to `str`. Use plain `list` annotation instead:

```python
# ❌ WRONG: List[dict] maps to str
async def create_order(items: List[dict]) -> dict: ...

# ✅ CORRECT: list maps to list
async def create_order(items: list) -> dict: ...
```

## Full Documentation

- `apps/kailash-nexus/docs/handler-support.md` - Complete handler guide
- `apps/kailash-nexus/docs/migration/handler-migration-guide.md` - Migration guide (5 patterns)
- `apps/kailash-nexus/docs/migration/real-project-patterns.md` - Real project patterns (8 patterns)
- `src/kailash/nodes/handler.py` - HandlerNode implementation
