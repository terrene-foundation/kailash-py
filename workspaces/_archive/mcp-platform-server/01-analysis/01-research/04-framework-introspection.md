# Framework Introspection Points

Research into what each Kailash framework exposes that the MCP platform server needs to introspect.

---

## Core SDK

### NodeRegistry (Singleton)

**Location**: `src/kailash/nodes/base.py:2119`

```python
class NodeRegistry:
    _instance = None
    _nodes: dict[str, type[Node]] = {}

    @classmethod
    def register(cls, node_class, alias=None): ...
    @classmethod
    def list_nodes(cls) -> list[str]: ...
    @classmethod
    def get(cls, name: str) -> type[Node]: ...
```

- Singleton pattern — access via `NodeRegistry()` or class methods
- Nodes self-register via `@register_node` decorator on import
- `list_nodes()` returns all registered node type names
- `get(name)` returns the node class for instantiation

**MCP introspection needs**:

- `core.list_node_types()` -> `NodeRegistry.list_nodes()` + get descriptions/parameters from each class
- `core.describe_node(type)` -> `NodeRegistry.get(type)` + inspect `get_parameters()`, docstring

**Challenge**: Nodes register on import. If a module hasn't been imported, its nodes won't be in the registry. The platform server may need to trigger `import kailash.nodes` to populate.

---

## DataFlow

### Model Registry

**Location**: `packages/kailash-dataflow/src/dataflow/core/model_registry.py`

- `ModelRegistry` class initialized with a `DataFlow` instance
- Tracks model definitions, fields, relationships
- Integrated with migration system

**But more importantly**: DataFlow uses the `@db.model` decorator pattern:

```python
@db.model
class User:
    id: int = field(primary_key=True)
    name: str
    email: str
```

The decorated models register themselves in DataFlow's internal model dict. Access:

```python
db = DataFlow(database_url)
# db._models or similar internal dict
# db.get_model(name)
```

**Key files for introspection**:

- `packages/kailash-dataflow/src/dataflow/core/engine.py` — main DataFlow engine, model registration
- `packages/kailash-dataflow/src/dataflow/__init__.py` — DataFlow class, `model` decorator
- `packages/kailash-dataflow/src/dataflow/core/nodes.py` — generated CRUD node names

**MCP introspection needs**:

- `dataflow.list_models()` -> iterate `db._models` or model registry
- `dataflow.describe_model(name)` -> field metadata, generated node names (`Create{Name}`, `Read{Name}`, etc.)
- `dataflow.query_schema()` -> DB connection status, dialect, migration state

**Challenge**: DataFlow requires a database URL to initialize. The MCP server introspects the PROJECT's models, not the platform server's. Need to discover the project's DataFlow configuration from `project_root`.

---

## Nexus

### Handler Registry

Nexus apps register handlers and channels:

```python
app = Nexus()
app.register(workflow)
app.add_handler(name, handler, method, path)
```

**Key files**:

- `packages/kailash-nexus/src/nexus/` — Nexus app, handler registration
- Channel system at `src/kailash/channels/` — channel types and configs

**MCP introspection needs**:

- `nexus.list_handlers()` -> iterate registered handlers with method, path, description
- `nexus.list_channels()` -> iterate configured channels (HTTP, CLI, MCP, WebSocket)
- `nexus.list_events()` -> event bus subscriptions

**Challenge**: Nexus app configuration is typically in-process. For static introspection, need to scan source files for handler registrations. Fallback: AST-based source scanning.

---

## Kaizen

### Agent Discovery

Two registry paths:

1. **Trust Registry** (`kaizen.trust.registry.AgentRegistry`): Central agent discovery with health monitoring
2. **Deploy Registry** (`kaizen.deploy.registry.LocalRegistry`): File-based at `~/.kaizen/registry/`
3. **Source scan**: Scan project's `agents/` directory for `BaseAgent` subclasses

**Key files**:

- `packages/kailash-kaizen/src/kaizen/trust/registry.py` — AgentRegistry, AgentRegistryStore
- `packages/kailash-kaizen/src/kaizen/deploy/registry.py` — LocalRegistry, file-based
- `packages/kailash-kaizen/src/kaizen/deploy/__init__.py` — `introspect_agent()` function

**MCP introspection needs**:

- `kaizen.list_agents()` -> scan for BaseAgent subclasses, Delegate instances
- `kaizen.describe_agent(name)` -> signature fields, tools, strategy, MCP servers

**Key function**: `introspect_agent(module, class_name)` — extracts runtime metadata from a Kaizen agent class without instantiating it. This is exactly what the MCP contributor needs.

---

## Trust / EATP

### TrustProject

**Location**: `src/kailash/trust/plane/project.py`

Already has an MCP server (`mcp_server.py`). The platform server's trust contributor reuses the same `TrustProject.load()` API.

**MCP introspection needs**:

- `trust.trust_status()` -> posture, session, decision count, constraint summary
- `trust.trust_envelope()` -> current constraint envelope

**Challenge**: None significant. Well-established API with FastMCP reference model.

---

## PACT

### GovernanceEngine

**Location**: `src/kailash/trust/pact/engine.py`

- Compiled org tree with D/T/R hierarchy
- Governance envelopes per role
- Thread-safe with `self._lock`

**MCP introspection needs**:

- `pact.org_tree()` -> compiled org hierarchy with envelopes
- `pact.verify_action(action)` -> governance decision

**Challenge**: PACT requires a compiled org tree. If the project hasn't configured PACT governance, the contributor should gracefully return "PACT not configured."

---

## Introspection Strategy Summary

| Framework | Primary Registry         | Fallback        | Init Required          |
| --------- | ------------------------ | --------------- | ---------------------- |
| Core SDK  | `NodeRegistry` singleton | Import trigger  | `import kailash.nodes` |
| DataFlow  | `DataFlow._models`       | Source scan     | Database URL           |
| Nexus     | `NexusApp` config        | AST source scan | App config             |
| Kaizen    | `introspect_agent()`     | Source scan     | None (static)          |
| Trust     | `TrustProject.load()`    | None            | Trust directory        |
| PACT      | `GovernanceEngine`       | None            | Compiled org           |

### Static vs Runtime Introspection

For the platform server to work as an MCP tool for Claude Code (which operates on source code), **static introspection is the primary mode**:

1. Scan `project_root` for DataFlow models via AST
2. Scan for Nexus handler registrations via AST
3. Scan for BaseAgent subclasses via AST
4. Read `pyproject.toml` for installed framework versions via `importlib.metadata`

Runtime introspection (instantiating DataFlow, starting Nexus) is only needed for Tier 3/4 tools and requires explicit configuration.
