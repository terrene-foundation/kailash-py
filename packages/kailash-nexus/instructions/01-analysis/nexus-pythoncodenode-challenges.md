# PythonCodeNode Sandbox vs Nexus Workflows: Challenges & Proposed Improvements

**Date**: 2026-02-09
**Author**: Claude Code (on behalf of Example-Project team)
**Audience**: Kailash Nexus Development Team

## Executive Summary

During the consolidation of 40+ Nexus gateway modules (~380 workflows) into a unified instance, we discovered that **226+ workflows were broken at runtime** because they used `PythonCodeNode` to orchestrate async service calls. The PythonCodeNode sandbox blocks imports of application modules and `asyncio`, making it fundamentally incompatible with real-world Nexus use cases that need to call services, access databases, or use async patterns.

We built a workaround (`AsyncHandlerNode` + `make_handler_workflow()`), but the root cause is a **gap in the Nexus developer experience** that could be addressed at the framework level.

---

## The Problem

### What PythonCodeNode Is Designed For

PythonCodeNode runs user-provided code strings in a sandboxed environment with `SafeCodeChecker` (AST-based) and a module whitelist (`ALLOWED_MODULES` in `kailash/nodes/code/common.py`). This is appropriate for:

- Data transformations (JSON manipulation, string processing)
- Simple calculations
- Formatting/mapping between node outputs

### What Developers Actually Need in Nexus Workflows

Real Nexus gateway workflows need to:

1. **Import application modules**: `from example_project.services.contact_service import ContactService`
2. **Use async/await**: Services are async-first, database calls use `asyncpg`, etc.
3. **Access shared state**: Database connections, service singletons, configuration
4. **Call external libraries**: `asyncpg`, `httpx`, AI frameworks, etc.

### The Mismatch

When developers use the natural pattern of putting business logic in PythonCodeNode code strings, they hit:

```
SecurityError: Import of 'asyncio' is not allowed
SecurityError: Import of 'example_project.services' is not allowed
```

The sandbox's `ALLOWED_MODULES` whitelist (json, math, re, datetime, etc.) is too restrictive for service orchestration. This caused **every workflow in 25+ gateway files to return 500 errors** at runtime, despite passing syntax checks and registration.

### Why This Is Hard to Detect

- Workflows **register successfully** with Nexus (the code string is valid Python)
- The sandbox error only occurs at **execution time** when the code actually runs
- There's no validation step during `app.register()` that checks if the code's imports will be allowed
- Developers don't see the error until they actually call the workflow via API/CLI/MCP

---

## The Workaround We Built

### `AsyncHandlerNode` (extends `AsyncNode`)

A custom node that wraps an async Python function directly (no code strings, no sandbox):

```python
class AsyncHandlerNode(AsyncNode):
    def __init__(self, handler, params=None, **kwargs):
        self._handler = handler  # Set BEFORE super().__init__()
        self._params = params or {}
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return self._params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        sig = inspect.signature(self._handler)
        handler_params = set(sig.parameters.keys())
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in handler_params}
        result = await self._handler(**filtered_kwargs)
        return result if isinstance(result, dict) else {"result": result}
```

### `make_handler_workflow()` (auto-generates workflow from function signature)

```python
def make_handler_workflow(handler, node_id, input_mapping=None):
    sig = inspect.signature(handler)
    params = {}
    auto_mapping = {}
    for name, param in sig.parameters.items():
        ptype = _resolve_type(param.annotation)
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None
        params[name] = NodeParameter(
            name=name, type=ptype, required=not has_default, default=default
        )
        auto_mapping[name] = name

    workflow = WorkflowBuilder()
    node = AsyncHandlerNode(handler=handler, params=params)
    workflow.add_node_instance(node, node_id)
    workflow.add_workflow_inputs(node_id, input_mapping or auto_mapping)
    return workflow
```

### Usage (the developer experience we want)

```python
# Define handler as a normal async function - full Python, no sandbox
async def search_contacts_handler(
    search_text: str = "",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    service = ContactService()
    results = await service.search(search_text, page, page_size)
    return {"contacts": results, "count": len(results)}

# One line to create the workflow
def create_search_contacts_workflow():
    return make_handler_workflow(search_contacts_handler, "search_contacts")

# Register with Nexus
app.register("search_contacts", create_search_contacts_workflow().build())
```

---

## Challenges Encountered During the Fix

### 1. MRO Initialization Order (`AsyncNode` base class)

**Problem**: `AsyncNode.__init__()` triggers `_validate_config()` -> `get_parameters()` through the MRO chain (`EventEmitterMixin -> SecurityMixin -> PerformanceMixin -> LoggingMixin -> Node`). If instance attributes aren't set before `super().__init__()`, you get `AttributeError`.

**Fix**: Set `self._handler` and `self._params` BEFORE calling `super().__init__(**kwargs)`.

**Suggestion for Nexus team**: Consider making `get_parameters()` lazy (called on first access, not during `__init__`), or document this initialization order requirement prominently for custom node authors.

### 2. Input Injection with AsyncLocalRuntime

**Problem**: `LocalRuntime` doesn't properly inject workflow-level inputs into node `async_run(**kwargs)` when using `add_workflow_inputs()`. Inputs arrive as their default values, not the actual values passed to `execute()`.

**Fix**: Use `AsyncLocalRuntime` which Nexus uses internally. It correctly injects workflow inputs.

**Suggestion for Nexus team**: Document which runtime to use for testing workflows locally. The behavior difference between `LocalRuntime` and `AsyncLocalRuntime` for input injection is non-obvious.

### 3. Async-First Architecture Was Being Reduced to Sync

**Problem**: Initial approach was to wrap async handlers in `asyncio.run()` inside a sync `_run()` method of a regular `Node`. This defeats the purpose of Nexus's async-first architecture and creates thread-blocking issues.

**Fix**: Extend `AsyncNode` directly and use its `async_run()` method.

**Suggestion for Nexus team**: If Nexus provides a built-in "function handler" node (see proposal below), it should be async-native from the start.

### 4. No Built-in Way to Create Single-Function Workflows

**Problem**: The 90% use case for Nexus gateways is: "I have an async function, deploy it as a workflow." Today this requires:

- Creating a WorkflowBuilder
- Creating a custom node with `get_parameters()`
- Adding the node instance with `add_node_instance()`
- Mapping workflow inputs with `add_workflow_inputs()`

That's ~20 lines of boilerplate per workflow, multiplied by 380 workflows = massive boilerplate.

**Suggestion**: See proposal below.

---

## Proposed Improvements for Nexus

### Proposal 1: `app.handler()` Decorator (Highest Impact)

The most common Nexus pattern is deploying an async function as a workflow. Nexus should support this natively:

```python
app = Nexus(api_port=8000)

@app.handler("search_contacts")
async def search_contacts(
    search_text: str = "",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    service = ContactService()
    results = await service.search(search_text, page, page_size)
    return {"contacts": results, "count": len(results)}

app.start()
```

Under the hood, `@app.handler(name)` would:

1. Inspect the function signature (like our `make_handler_workflow()`)
2. Create an `AsyncHandlerNode` (or equivalent built-in node)
3. Build and register the workflow automatically

This is analogous to FastAPI's `@app.post("/search")` decorator pattern and would make Nexus dramatically easier to use for the common case.

### Proposal 2: `Nexus.register_handler()` (Non-decorator version)

For cases where decorators aren't practical (e.g., importing handlers from other modules):

```python
from my_app.handlers import search_contacts_handler

app = Nexus(api_port=8000)
app.register_handler("search_contacts", search_contacts_handler)
app.start()
```

### Proposal 3: Built-in `FunctionNode` or `HandlerNode`

Add a first-class node type to Kailash Core SDK that wraps an async function without sandboxing:

```python
from kailash.nodes import FunctionNode

node = FunctionNode(handler=my_async_function)
workflow.add_node_instance(node, "my_node")
```

This would be the building block for Proposals 1 and 2.

### Proposal 4: PythonCodeNode Sandbox Configuration

For cases where PythonCodeNode IS used, allow configuring the sandbox:

```python
# Option A: Per-node configuration
workflow.add_node("PythonCodeNode", "my_node", {
    "code": "...",
    "sandbox_mode": "trusted",  # or "restricted" (default)
})

# Option B: Per-Nexus-app configuration
app = Nexus(
    api_port=8000,
    python_code_allowed_modules=["asyncio", "asyncpg", "my_app.*"],
)
```

### Proposal 5: Registration-Time Validation

Add import validation during `app.register()` to catch sandbox issues early:

```python
# During workflow registration, if any PythonCodeNode is detected,
# parse its code string and check if imports will pass the sandbox.
# Raise a clear warning/error at registration time, not at execution time.
```

---

## Impact Summary

| Metric                   | Before                                        | After                                        |
| ------------------------ | --------------------------------------------- | -------------------------------------------- |
| Broken workflows         | 226+ (500 errors)                             | 0                                            |
| Boilerplate per workflow | ~50 lines (PythonCodeNode + code string)      | ~1 line (`make_handler_workflow()`)          |
| SQL injection risk       | High (f-string interpolation in code strings) | Low (parameterized queries in proper Python) |
| Async capability         | Blocked (sandbox blocks asyncio)              | Full async support                           |
| Code discoverability     | Low (logic hidden in code strings)            | High (normal Python functions)               |
| IDE support              | None (code strings are opaque)                | Full (type hints, autocomplete, linting)     |

---

## Files Created/Modified

- **Created**: `src/example_project/nodes/handler_node.py` - AsyncHandlerNode + make_handler_workflow utility
- **Modified**: 40+ gateway files in `src/example_project/gateways/nexus/` - all PythonCodeNode workflows replaced

## Recommendation Priority

1. **Proposal 1** (`@app.handler` decorator) - Highest impact, lowest effort, solves 90% of use cases
2. **Proposal 3** (Built-in FunctionNode) - Foundation for Proposal 1, useful for SDK users directly
3. **Proposal 5** (Registration-time validation) - Prevents silent failures
4. **Proposal 4** (Configurable sandbox) - For advanced use cases
5. **Proposal 2** (register_handler method) - Nice-to-have complement to Proposal 1
