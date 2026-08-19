---
name: mcp-platform-map
description: "platform_map() output schema, connection detection, framework detection, debugging. Use when asking 'platform map', 'project introspection', 'cross-framework connections', 'mcp detection', or 'platform_map output'."
---

# MCP Platform Map

Deep reference for the `platform.platform_map` tool -- the single-call project overview that aggregates discovery from all framework contributors.

> **Skill Metadata**
> Category: `mcp`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-platform-overview`](mcp-platform-overview.md), [`mcp-tool-catalog`](mcp-tool-catalog.md)
> Related Subagents: `mcp-platform-specialist` (detection debugging, custom connections)

## What platform_map Returns

A single JSON response with every discoverable artifact in the project and the connections between them.

```json
{
  "project": {
    "name": "my-app",
    "root": "/path/to/project",
    "python_version": "3.12",
    "kailash_version": "2.5.0"
  },
  "frameworks": {
    "core": { "installed": true, "version": "2.5.0" },
    "dataflow": { "installed": true, "version": "1.3.0" },
    "nexus": { "installed": true, "version": "0.8.0" },
    "kaizen": { "installed": false },
    "pact": { "installed": false },
    "trust": { "installed": true, "version": "2.5.0" },
    "ml": { "installed": false },
    "align": { "installed": false }
  },
  "models": [
    { "name": "User", "fields_count": 5, "file": "models/user.py" },
    { "name": "Product", "fields_count": 8, "file": "models/product.py" }
  ],
  "handlers": [
    {
      "name": "create_user",
      "method": "POST",
      "path": "/api/users",
      "file": "handlers/users.py"
    },
    {
      "name": "list_products",
      "method": "GET",
      "path": "/api/products",
      "file": "handlers/products.py"
    }
  ],
  "agents": [
    { "name": "SupportAgent", "type": "class", "file": "agents/support.py" }
  ],
  "channels": [],
  "connections": [
    {
      "from": "User",
      "to": "create_user",
      "type": "model_to_handler",
      "via": "CreateUser"
    },
    {
      "from": "Product",
      "to": "list_products",
      "type": "model_to_handler",
      "via": "ListProduct"
    },
    { "from": "SupportAgent", "to": "web_search", "type": "agent_to_tool" }
  ],
  "trust": {
    "installed": true,
    "trust_dir_exists": true,
    "trust_dir": "/path/to/project/trust-plane"
  },
  "scan_metadata": {
    "method": "ast_static",
    "frameworks_scanned": ["dataflow", "nexus", "kaizen"],
    "total_files_scanned": 42,
    "scan_duration_ms": 150,
    "limitations": [
      "Cross-framework connections detected via deterministic naming only",
      "Custom node names in handlers not detected as model connections",
      "Dynamic model/handler/agent registration not detected",
      "External packages not scanned"
    ]
  }
}
```

## Output Schema Reference

### `project` -- Project Metadata

| Field             | Type           | Source                                         |
| ----------------- | -------------- | ---------------------------------------------- |
| `name`            | string         | `pyproject.toml` name field, or directory name |
| `root`            | string         | Absolute path to project root                  |
| `python_version`  | string         | Running Python interpreter version             |
| `kailash_version` | string or null | `kailash` package version from pip metadata    |

### `frameworks` -- Installed Framework Detection

Detection uses `importlib.metadata.version()` to check pip package installation.

| Key        | Package Checked    | Notes                                            |
| ---------- | ------------------ | ------------------------------------------------ |
| `core`     | `kailash`          | Always installed (platform server depends on it) |
| `dataflow` | `kailash-dataflow` | Enables `dataflow.*` tools                       |
| `nexus`    | `kailash-nexus`    | Enables `nexus.*` tools                          |
| `kaizen`   | `kailash-kaizen`   | Enables `kaizen.*` tools                         |
| `pact`     | `kailash-pact`     | Enables `pact.*` tools                           |
| `trust`    | `kailash`          | Part of core, always available                   |
| `ml`       | `kailash-ml`       | No MCP contributor yet                           |
| `align`    | `kailash-align`    | No MCP contributor yet                           |

Each framework entry has:

- `installed: bool` -- whether the pip package is available
- `version: string` -- version string (only when installed)

### `models` -- DataFlow Models

Discovered by AST scanning for `@db.model` decorated classes.

| Field          | Type   | Description                     |
| -------------- | ------ | ------------------------------- |
| `name`         | string | Class name (e.g., `"User"`)     |
| `fields_count` | int    | Number of annotated fields      |
| `file`         | string | Relative path from project root |

### `handlers` -- Nexus Handlers

Discovered by AST scanning for `@handler` decorators and `add_handler()` calls.

| Field    | Type           | Description                      |
| -------- | -------------- | -------------------------------- |
| `name`   | string         | Function name or registered name |
| `method` | string or null | HTTP method (GET, POST, etc.)    |
| `path`   | string or null | URL path (/api/users, etc.)      |
| `file`   | string         | Relative path from project root  |

### `agents` -- Kaizen Agents

Discovered by AST scanning for `BaseAgent` subclasses and `Delegate` instantiations.

| Field  | Type   | Description                                      |
| ------ | ------ | ------------------------------------------------ |
| `name` | string | Class name or variable name                      |
| `type` | string | `"class"` (BaseAgent) or `"delegate"` (Delegate) |
| `file` | string | Relative path from project root                  |

### `connections` -- Cross-Framework Links

The most valuable part of platform_map. Three connection types are detected:

#### `model_to_handler`

A Nexus handler uses a DataFlow model's auto-generated CRUD nodes.

```json
{
  "from": "User",
  "to": "create_user",
  "type": "model_to_handler",
  "via": "CreateUser"
}
```

**Detection logic**: For each model `X`, check if any handler file contains the strings `CreateX`, `ReadX`, `UpdateX`, `DeleteX`, `ListX`, `UpsertX`, or `CountX`.

**Why naming-based?** DataFlow auto-generates node types with deterministic names (`Create{ModelName}`, `Read{ModelName}`, etc.). If a handler file references these names, it almost certainly uses that model.

#### `model_to_agent`

A Kaizen agent uses a DataFlow model's auto-generated nodes.

```json
{
  "from": "User",
  "to": "SupportAgent",
  "type": "model_to_agent",
  "via": "CreateUser"
}
```

**Detection logic**: Same as model_to_handler, but scanning agent files.

#### `agent_to_tool`

An agent has registered tools in its class definition.

```json
{ "from": "SupportAgent", "to": "web_search", "type": "agent_to_tool" }
```

**Detection logic**: Extracts the `tools = [...]` list from the agent's class body.

### `trust` -- Trust Plane Status

| Field              | Type   | Description                          |
| ------------------ | ------ | ------------------------------------ |
| `installed`        | bool   | Whether trust-plane directory exists |
| `trust_dir_exists` | bool   | Whether the directory is present     |
| `trust_dir`        | string | Absolute path (only when exists)     |

### `scan_metadata` -- How Results Were Obtained

Every tool response includes this metadata so the consumer knows what to trust.

| Field                 | Type         | Description                            |
| --------------------- | ------------ | -------------------------------------- |
| `method`              | string       | Always `"ast_static"` for platform_map |
| `frameworks_scanned`  | list[string] | Which frameworks contributed data      |
| `total_files_scanned` | int          | Total Python files processed           |
| `scan_duration_ms`    | int          | Wall clock time for the full scan      |
| `limitations`         | list[string] | Known detection gaps                   |

## Using platform_map for Project Introspection

### First Orientation

When entering a new project, call `platform.platform_map` first. It answers:

- **What frameworks does this project use?** Check `frameworks` for installed packages.
- **What are the main data models?** Check `models` for `@db.model` classes.
- **What API endpoints exist?** Check `handlers` for Nexus routes.
- **What AI agents are defined?** Check `agents` for BaseAgent/Delegate instances.
- **How do they connect?** Check `connections` for cross-framework links.

### Discovering the Data Layer

```
platform_map.models → for each model → dataflow.describe_model(model_name)
```

Start with the model list from platform_map, then drill into specific models for field-level detail.

### Tracing a Request Path

```
Handler → via connection.model_to_handler → Model → via connection.model_to_agent → Agent
```

Follow connection chains to understand how a user request flows through the system.

## Debugging Detection Failures

### Models Not Detected

**Cause**: Class does not use `@db.model` decorator.

```python
# Detected:
@db.model
class User:
    id: int = field(primary_key=True)
    name: str

# NOT detected (no decorator):
class User(Base):
    __tablename__ = "users"
```

**Fix**: Use the `@db.model` decorator pattern. The scanner looks for `@<anything>.model` decorators.

### Handlers Not Detected

**Cause**: Handler uses an unrecognized registration pattern.

```python
# Detected:
@handler(method="POST", path="/api/users")
async def create_user(request): ...

# Detected:
app.add_handler("create_user", "POST", "/api/users")

# NOT detected (dynamic):
for name, config in handler_configs.items():
    app.add_handler(name, **config)
```

**Fix**: Use decorator or explicit `add_handler` calls with literal arguments.

### Agents Not Detected

**Cause**: Agent uses custom base class without "Agent" in the name.

```python
# Detected:
class SupportAgent(BaseAgent): ...

# Detected (heuristic: class name contains "Agent"):
class SupportAgent(CustomBase): ...

# NOT detected:
class SupportHelper(CustomBase): ...
```

**Fix**: Either inherit from `BaseAgent` or include "Agent" in the class name.

### Connections Not Detected

**Cause**: Custom node names that don't follow the `Create{Model}` pattern.

```python
# Detected (deterministic naming):
workflow.add_node("CreateUser", "create", {...})

# NOT detected (custom alias):
workflow.add_node("CreateUser", "user_creation_step", {...})
# This IS detected -- the tool name "CreateUser" is what matters,
# not the node ID.

# NOT detected (dynamic):
node_type = f"Create{model_name}"
workflow.add_node(node_type, "create", {...})
```

**Fix**: Use DataFlow's auto-generated node type names directly in handler/agent code.

## MCP Resource Alternative

The same data is available as an MCP resource:

```
kailash://platform-map
```

Resources provide the same data but through the MCP resource protocol. Useful for clients that prefer resource subscriptions over tool calls.

## Quick Tips

- Call `platform.platform_map` once per session for project orientation
- The `connections` array is the highest-value output -- it shows how the project fits together
- Empty results usually mean wrong `project_root` -- check the `scan_metadata.total_files_scanned` count
- If `scan_duration_ms` is high (>1000ms), the project may have large non-source directories that need exclusion
- `frameworks_scanned` tells you which contributor modules loaded successfully

## When to Escalate to Subagent

Use `mcp-platform-specialist` when:

- Detection heuristics are missing artifacts that should be found
- Implementing custom connection detection logic
- Optimizing scan performance for large monorepos
- Extending platform_map with custom framework data

<!-- Trigger Keywords: platform map, project introspection, cross-framework connections, mcp detection, platform_map output, project overview, framework detection, connection detection -->
