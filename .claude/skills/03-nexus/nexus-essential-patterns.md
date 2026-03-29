---
skill: nexus-essential-patterns
description: Essential code patterns for Nexus setup, handler registration, DataFlow integration, connections, and middleware
priority: HIGH
tags: [nexus, patterns, setup, handler, dataflow, middleware, configuration]
---

# Nexus Essential Patterns

Quick-reference code patterns for the most common Nexus operations.

## Basic Setup

```python
from nexus import Nexus
app = Nexus()
app.register("workflow_name", workflow.build())  # ALWAYS .build()
app.start()
```

## Handler Registration (Recommended)

Bypasses PythonCodeNode sandbox restrictions. Simpler syntax, automatic parameter derivation, multi-channel deployment from a single function.

```python
from nexus import Nexus

app = Nexus()

# Decorator pattern
@app.handler("greet", description="Greeting handler")
async def greet(name: str, greeting: str = "Hello") -> dict:
    """Direct async function as multi-channel workflow."""
    return {"message": f"{greeting}, {name}!"}

# Non-decorator pattern
async def process(data: dict) -> dict:
    return {"result": data}

app.register_handler("process", process)
app.start()
```

**Why Use Handlers?**

- Bypasses PythonCodeNode sandbox restrictions
- No import blocking (use any library)
- Automatic parameter derivation from function signature
- Multi-channel deployment (API/CLI/MCP) from single function

## DataFlow Integration (CRITICAL)

```python
# CORRECT: Fast, non-blocking
app = Nexus(auto_discovery=False)  # CRITICAL

db = DataFlow(
    database_url="postgresql://...",
    auto_migrate=True,  # default: Works in Docker/FastAPI
)
```

**WARNING**: Without `auto_discovery=False`, Nexus blocks on startup when DataFlow is present.

## API Input Access in PythonCodeNode

```python
# CORRECT: Use try/except in PythonCodeNode
workflow.add_node("PythonCodeNode", "prepare", {
    "code": """
try:
    sector = sector  # From API inputs
except NameError:
    sector = None
result = {'filters': {'sector': sector} if sector else {}}
"""
})

# WRONG: inputs.get() doesn't exist
```

## Connection Pattern

```python
# CORRECT: Explicit connections with dot notation
workflow.add_connection("prepare", "result.filters", "search", "filter")

# WRONG: Template syntax not supported
# "filter": "${prepare.result}"
```

## Middleware & Plugin API (v1.4.1)

```python
# Native middleware (Starlette-compatible)
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Include existing FastAPI routers
app.include_router(legacy_router, prefix="/legacy")

# Plugin protocol (NexusPluginProtocol)
app.add_plugin(auth_plugin)

# Preset system (one-line config)
app = Nexus(preset="saas", cors_origins=["https://app.example.com"])
```

## Configuration Quick Reference

| Use Case          | Config                                                        |
| ----------------- | ------------------------------------------------------------- |
| **With DataFlow** | `Nexus(auto_discovery=False)`                                 |
| **Standalone**    | `Nexus()`                                                     |
| **With Preset**   | `Nexus(preset="saas")`                                        |
| **With CORS**     | `Nexus(cors_origins=["..."], cors_allow_credentials=False)`   |
| **Full Features** | `Nexus(auto_discovery=False)` + `app.add_plugin(auth_plugin)` |

## Handler Support Details

### Core Components

**HandlerNode** (`kailash.nodes.handler`):

- Core SDK node that wraps async/sync functions
- Automatic parameter derivation from function signatures
- Type annotation mapping to NodeParameter entries
- Seamless WorkflowBuilder integration

**make_handler_workflow()** utility:

- Builds single-node workflow from handler function
- Configures workflow-level input mappings
- Returns ready-to-execute Workflow instance

**Registration-Time Validation** (`_validate_workflow_sandbox`):

- Detects PythonCodeNode/AsyncPythonCodeNode with blocked imports
- Emits warnings at registration time (not runtime)
- Helps developers migrate to handlers for restricted code

**Configurable Sandbox Mode**:

- `sandbox_mode="strict"`: Blocks restricted imports (default)
- `sandbox_mode="permissive"`: Allows all imports (test/dev only)
- Set via PythonCodeNode/AsyncPythonCodeNode parameter

### Key Files

- `tests/unit/nodes/test_handler_node.py` - 22 SDK unit tests

### Migration Note

**Type Mapping Limitation**: `_derive_params_from_signature()` maps complex generics (e.g., `List[dict]`) to `str`. Use plain `list` instead.

## MCP Transport

- **`receive_message()`**: MCP transport supports `receive_message()` for bidirectional communication in custom MCP transports

## Performance & Monitoring

- **SQLite CARE Audit Storage** (current): Nexus creates `AsyncLocalRuntime()` with `enable_monitoring=True` (default), so all workflow executions automatically get CARE audit persistence to SQLite WAL-mode database. Zero in-loop I/O (~35us/node overhead) with post-execution ACID flush.
