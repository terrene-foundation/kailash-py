# Nexus Workflow Registration

Register workflows for multi-channel deployment (API + CLI + MCP) via a single call.

## Registration Methods

| Method           | Use Case                  | Example                                  |
| ---------------- | ------------------------- | ---------------------------------------- |
| `@app.handler()` | Python functions (prefer) | `@app.handler("name")`                   |
| `app.register()` | WorkflowBuilder workflows | `app.register("name", workflow.build())` |

## Handler Registration (Preferred)

```python
from nexus import Nexus
app = Nexus()

@app.handler("greet", description="Greet a user")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}

@app.handler("search_users")
async def search_users(query: str, limit: int = 10) -> dict:
    from my_app.services import UserService
    return {"users": await UserService().search(query, limit)}

app.start()
```

Benefits: full Python access (no sandbox), auto parameter derivation from signature, async/sync, IDE support, docstrings as descriptions.

Non-decorator form:

```python
app.register_handler("process_order", process_order, description="Process an order")
```

See [nexus-handler-support](#) for complete handler documentation.

## WorkflowBuilder Registration (v1.1.0)

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://api.example.com/data", "method": "GET"
})

app.register("data-fetcher", workflow.build())
# Internally:
#   API  -> POST /workflows/data-fetcher/execute
#   CLI  -> nexus execute data-fetcher
#   MCP  -> tool workflow_data-fetcher
```

## Critical Rules

```python
# MUST call .build()
app.register("name", workflow.build())   # correct
app.register("name", workflow)           # WRONG - fails

# MUST use name-first parameter order
app.register(name, workflow.build())     # correct
app.register(workflow.build(), name)     # WRONG - reversed
```

**Metadata**: Not supported in v1.1.0. `register()` accepts only `(name, workflow)`.

## Auto-Discovery

File patterns discovered automatically:

- `workflows/*.py`, `*.workflow.py`, `workflow_*.py`, `*_workflow.py`

```python
# my_workflow.py -- export a `workflow` variable
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://httpbin.org/json", "method": "GET"
})
```

```python
app = Nexus(auto_discovery=True)   # default
app = Nexus(auto_discovery=False)  # recommended with DataFlow
```

## Dynamic Registration

### Runtime Discovery

```python
import os, importlib.util
from nexus import Nexus

app = Nexus()

def discover_and_register(directory="./workflows"):
    for filename in os.listdir(directory):
        if filename.endswith("_workflow.py"):
            name = filename[:-12]
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(directory, filename))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'workflow'):
                app.register(name, module.workflow.build())

discover_and_register()
```

### Configuration-Driven

```python
import yaml

def register_from_config(app, config_file="workflows.yaml"):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    for wf in config['workflows']:
        workflow = WorkflowBuilder()
        for node in wf['nodes']:
            workflow.add_node(node['type'], node['id'], node['parameters'])
        for conn in wf.get('connections', []):
            workflow.add_connection(conn['from_node'], "result",
                                   conn['to_node'], "input")
        app.register(wf['name'], workflow.build())
```

## Versioning

```python
class WorkflowVersionManager:
    def __init__(self, nexus_app):
        self.app = nexus_app
        self.versions = {}

    def register_version(self, name, workflow, version):
        versioned_name = f"{name}:v{version}"
        self.app.register(versioned_name, workflow.build())
        self.versions.setdefault(name, []).append(version)
        if version == max(self.versions[name]):
            self.app.register(f"{name}:latest", workflow.build())
            self.app.register(name, workflow.build())

    def rollback(self, name, target_version):
        wf = self.app.workflows.get(f"{name}:v{target_version}")
        if wf:
            self.app.register(name, wf.workflow)
            return True
        return False

# Usage
mgr = WorkflowVersionManager(app)
mgr.register_version("data-api", workflow_v1, "1.0.0")
mgr.register_version("data-api", workflow_v2, "2.0.0")
mgr.rollback("data-api", "1.0.0")
```

## Quick Reference

**Registration flow**: single `app.register()` or `@app.handler()` call exposes on all channels automatically. No ChannelManager needed.

**Common fixes**:

- Workflow not found -> ensure `.build()` is called
- Auto-discovery blocks with DataFlow -> use `auto_discovery=False`
- Parameters reversed -> name first, workflow second

**Best practices**:

1. Prefer `@app.handler()` over WorkflowBuilder for most cases
2. Always call `.build()` before registration
3. Use `auto_discovery=False` when integrating with DataFlow
4. Use versioned names (`name:v1.0.0`) for production deployments

## Related Skills

- [nexus-handler-support](#) - Complete handler documentation
- [nexus-dataflow-integration](#) - DataFlow workflow registration
- [nexus-production-deployment](#) - Production deployment patterns
- [nexus-troubleshooting](#) - Fix registration issues
