# Nexus Handler Support

Handler support enables deploying Python functions directly as multi-channel workflows, bypassing the PythonCodeNode sandbox restrictions. This provides first-class support for the most common Nexus use case: "I have a Python function, deploy it as a workflow."

## Why Handler Support?

### The Problem with PythonCodeNode

PythonCodeNode executes code strings in a sandboxed environment with a restrictive module allowlist (`json`, `math`, `re`, `datetime`, etc.). This is appropriate for simple data transformations but fails for real-world service orchestration:

```python
# This will FAIL at runtime with SecurityError
workflow.add_node("PythonCodeNode", "call_service", {
    "code": """
import asyncio  # BLOCKED
from my_app.services import ContactService  # BLOCKED

service = ContactService()
result = await service.search(query)
"""
})
```

Developers discover this error only at **execution time**, not during registration.

### The Solution: Handler Support

Handler support lets you register Python functions directly:

```python
from nexus import Nexus

app = Nexus()

@app.handler("search_contacts")
async def search_contacts(query: str, page: int = 1) -> dict:
    # Full Python access - no sandbox restrictions
    from my_app.services import ContactService
    service = ContactService()
    results = await service.search(query, page)
    return {"contacts": results, "count": len(results)}

app.start()
```

The handler is automatically exposed on all channels:

- **API**: `POST /workflows/search_contacts/execute`
- **CLI**: `nexus execute search_contacts`
- **MCP**: Tool `workflow_search_contacts`

---

## Quick Start

### Decorator Pattern

```python
from nexus import Nexus

app = Nexus()

@app.handler("greet", description="Greet a user")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}

app.start()
```

### Non-Decorator Pattern

For handlers defined in other modules:

```python
from nexus import Nexus
from my_app.handlers import process_order

app = Nexus()
app.register_handler("process_order", process_order)
app.start()
```

---

## API Reference

### @app.handler() Decorator

```python
@app.handler(
    name: str,
    description: str = "",
    tags: Optional[List[str]] = None
)
```

**Parameters:**

- `name` (required): Workflow name for registration. Used in API paths, CLI commands, and MCP tool names.
- `description`: Optional description for documentation.
- `tags`: Optional tags for categorization.

**Behavior:**

- Returns the original function unchanged (can be called directly)
- Automatically registers the workflow on all channels
- Derives workflow parameters from function signature

**Example:**

```python
@app.handler("calculate", description="Calculate sum", tags=["math", "utils"])
async def calculate(a: int, b: int = 0) -> dict:
    return {"sum": a + b}

# Can still call the function directly
result = await calculate(5, 3)  # {"sum": 8}
```

### app.register_handler() Method

```python
app.register_handler(
    name: str,
    handler_func: Callable,
    description: str = "",
    tags: Optional[List[str]] = None,
    input_mapping: Optional[Dict[str, str]] = None
)
```

**Parameters:**

- `name` (required): Workflow name for registration.
- `handler_func` (required): The async or sync function to register.
- `description`: Optional description.
- `tags`: Optional tags for categorization.
- `input_mapping`: Optional mapping of workflow input names to handler parameter names.

**Raises:**

- `TypeError`: If `handler_func` is not callable.
- `ValueError`: If `name` is empty or whitespace-only.

**Example:**

```python
async def process_data(data: dict, threshold: float = 0.5) -> dict:
    filtered = {k: v for k, v in data.items() if v > threshold}
    return {"filtered": filtered}

app.register_handler(
    "process_data",
    process_data,
    description="Filter data by threshold"
)
```

---

## Parameter Type Mapping

Handler signatures are inspected to derive workflow parameters automatically.

### Supported Types

| Python Type   | NodeParameter Type | Example                  |
| ------------- | ------------------ | ------------------------ |
| `str`         | `str`              | `name: str`              |
| `int`         | `int`              | `count: int`             |
| `float`       | `float`            | `ratio: float`           |
| `bool`        | `bool`             | `enabled: bool`          |
| `dict`        | `dict`             | `data: dict`             |
| `list`        | `list`             | `items: list`            |
| `Optional[T]` | `T` (not required) | `title: Optional[str]`   |
| No annotation | `str`              | `x` (defaults to string) |

### Required vs Optional Parameters

```python
async def example(
    required_param: str,          # Required (no default)
    optional_param: int = 10,     # Optional (has default)
    nullable: Optional[str] = None  # Optional (Optional type)
) -> dict:
    pass
```

### Complex Types

Complex types (generics like `Dict[str, Any]`, `List[int]`, custom classes) fall back to `str` with a debug log:

```python
async def complex_handler(data: Dict[str, Any]) -> dict:
    # 'data' parameter will be typed as str
    pass
```

### Handlers with \*\*kwargs

Handlers accepting `**kwargs` receive all workflow inputs:

```python
async def flexible_handler(name: str, **extra) -> dict:
    # 'extra' will contain any additional inputs
    return {"name": name, "extra": extra}
```

---

## Core SDK: HandlerNode

For direct Core SDK usage without Nexus, use `HandlerNode` and `make_handler_workflow()`:

### HandlerNode

```python
from kailash.nodes.handler import HandlerNode

async def my_function(x: int, y: int = 0) -> dict:
    return {"sum": x + y}

node = HandlerNode(handler=my_function)
result = await node.async_run(x=5, y=3)  # {"sum": 8}
```

### make_handler_workflow()

```python
from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import AsyncLocalRuntime

async def greet(name: str) -> dict:
    return {"message": f"Hello, {name}!"}

workflow = make_handler_workflow(greet, "greeter")

runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(
    workflow,
    inputs={"name": "World"}
)
```

**Parameters:**

- `handler`: The async or sync function to wrap.
- `node_id`: The node ID within the workflow (default: `"handler"`).
- `input_mapping`: Optional mapping of workflow inputs to handler parameters.

---

## Configurable Sandbox Mode

For cases where you need to use PythonCodeNode with blocked imports, you can configure the sandbox mode:

### Per-Node Configuration

```python
from kailash.nodes.code.python import PythonCodeNode
from kailash.workflow.builder import WorkflowBuilder

# Bypass sandbox for this specific node
node = PythonCodeNode(
    name="trusted_code",
    code="""
import subprocess  # Normally blocked
result = subprocess.check_output(['ls', '-la'])
""",
    sandbox_mode="trusted"  # Disables import restrictions
)

builder = WorkflowBuilder()
builder.add_node_instance(node, "trusted")
```

### Security Warning

When using `sandbox_mode="trusted"`, a security warning is logged:

```
WARNING: PythonCodeNode 'trusted_code': sandbox_mode='trusted' disables
         import restrictions. Ensure the code source is trusted.
```

### Sandbox Modes

| Mode                     | Behavior                                                               |
| ------------------------ | ---------------------------------------------------------------------- |
| `"restricted"` (default) | Enforces module allowlist. Blocks `asyncio`, application modules, etc. |
| `"trusted"`              | Bypasses import checks. Full Python access.                            |

### When to Use Each

- **Use handlers** (`@app.handler`): Recommended for service orchestration, database access, async operations
- **Use `restricted` sandbox**: For user-provided code, untrusted input, data transformations
- **Use `trusted` sandbox**: For internal code that needs PythonCodeNode but requires blocked modules

---

## Registration-Time Validation

Nexus validates workflows at registration time and warns about potential sandbox issues:

```python
# When registering a workflow with PythonCodeNode...
app.register("my_workflow", workflow.build())

# If blocked imports are detected, you'll see:
# WARNING: Workflow 'my_workflow': PythonCodeNode node 'code_node' imports
#          'asyncio' which is not in the sandbox allowlist. This will fail
#          at execution time. Consider using @app.handler() to bypass the sandbox.
```

This early warning helps catch issues during development, not production.

---

## Handler Registry

Registered handlers are stored in `app._handler_registry` for introspection:

```python
app = Nexus()

@app.handler("greet", description="Greeting handler", tags=["api"])
async def greet(name: str) -> dict:
    return {"message": f"Hello, {name}!"}

# Inspect the registry
print(app._handler_registry)
# {
#     "greet": {
#         "handler": <function greet>,
#         "description": "Greeting handler",
#         "tags": ["api"],
#         "workflow": <Workflow object>
#     }
# }
```

---

## Migration Guide: PythonCodeNode to Handler

### Before (PythonCodeNode - often fails)

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": """
import asyncio  # BLOCKED!
from my_app.services import DataService  # BLOCKED!

service = DataService()
result = await service.process(data)
"""
})

app.register("process_data", workflow.build())
```

### After (Handler - recommended)

```python
from nexus import Nexus

app = Nexus()

@app.handler("process_data")
async def process_data(data: dict) -> dict:
    from my_app.services import DataService
    service = DataService()
    result = await service.process(data)
    return {"result": result}
```

### Conversion Checklist

1. Extract the code string into a proper Python function
2. Add type annotations to function parameters
3. Return a dictionary (or any value - non-dict returns are wrapped as `{"result": value}`)
4. Use `@app.handler()` decorator or `app.register_handler()`
5. Remove the old workflow registration

---

## Examples

### Database Operations

```python
@app.handler("get_user")
async def get_user(user_id: int) -> dict:
    from my_app.db import get_session
    from my_app.models import User

    async with get_session() as session:
        user = await session.get(User, user_id)
        return {"user": user.to_dict() if user else None}
```

### External API Calls

```python
@app.handler("fetch_weather")
async def fetch_weather(city: str) -> dict:
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.weather.com/{city}")
        return {"weather": response.json()}
```

### AI Integration

```python
@app.handler("generate_text")
async def generate_text(prompt: str, max_tokens: int = 100) -> dict:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return {"text": response.choices[0].message.content}
```

### Sync Handler (runs in executor)

```python
@app.handler("sync_operation")
def sync_operation(data: str) -> dict:
    # Sync functions are automatically run in a thread pool executor
    # to avoid blocking the event loop
    import time
    time.sleep(1)  # Simulating blocking operation
    return {"processed": data.upper()}
```

---

## Best Practices

1. **Use handlers for service orchestration**: They provide full Python access without sandbox restrictions.

2. **Add type annotations**: They are used to derive workflow parameters and provide better documentation.

3. **Return dictionaries**: While non-dict returns are wrapped, explicit dicts are cleaner.

4. **Use descriptive names**: The handler name becomes the API path, CLI command, and MCP tool name.

5. **Add descriptions**: They appear in API documentation and MCP tool descriptions.

6. **Keep handlers focused**: Each handler should do one thing well.

7. **Handle errors gracefully**: Exceptions propagate to the caller with appropriate error responses.

---

## Troubleshooting

### Handler Not Found

Ensure you've registered the handler before calling `app.start()`:

```python
app = Nexus()

@app.handler("greet")  # Registration happens here
async def greet(name: str) -> dict:
    return {"message": f"Hello, {name}!"}

app.start()  # Handlers must be registered before this
```

### Parameter Type Mismatch

If API inputs don't match expected types, add explicit type conversion:

```python
@app.handler("process")
async def process(count: int) -> dict:
    # API might send strings - add validation
    if isinstance(count, str):
        count = int(count)
    return {"doubled": count * 2}
```

### Async vs Sync Confusion

Both async and sync handlers work, but async is preferred for I/O operations:

```python
# Preferred for I/O
@app.handler("fetch")
async def fetch(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return {"data": response.json()}

# OK for CPU-bound or quick operations
@app.handler("calculate")
def calculate(x: int, y: int) -> dict:
    return {"sum": x + y}
```

---

## Related Documentation

- [Nexus Workflow Registration](../../../.claude/skills/03-nexus/nexus-workflow-registration.md) - Standard workflow registration
- [Nexus Handler Support Skill](../../../.claude/skills/03-nexus/nexus-handler-support.md) - Quick reference
- [Core SDK HandlerNode](../../../src/kailash/nodes/handler.py) - Source implementation
