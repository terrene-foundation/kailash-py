# Kailash Core SDK — Node Architecture

Version: 2.8.5
Status: Authoritative domain truth document
Parent domain: Core SDK (split from `core-sdk.md` per specs-authority Rule 8)
Scope: Node abstract base, NodeParameter, NodeMetadata, NodeRegistry

Sibling files: `core-workflows.md` (builder + workflow), `core-runtime.md` (execution + cycles + resilience + errors), `core-servers.md` (server variants + gateway)

---

## 1. Node Architecture

### 1.1 Node (Abstract Base Class)

**Module**: `kailash.nodes.base`
**Import**: `from kailash import Node`

The abstract base class for all nodes in the Kailash system. Nodes are stateless processors of data. All configuration is provided at initialization; runtime inputs are validated against schemas; outputs must be JSON-serializable.

#### 1.1.1 Constructor

```python
class Node(ABC):
    def __init__(self, **kwargs)
```

**Parameters (via kwargs)**:

- `_node_id: str` -- Internal node identifier. Defaults to `self.__class__.__name__`. Uses underscore prefix to avoid collision with user parameters named `id`.
- `name: str` -- Display name for the node. Defaults to `self.__class__.__name__`.
- `description: str` -- Node description. Defaults to the class docstring.
- `version: str` -- Node version. Defaults to `"1.0.0"`.
- `author: str` -- Node author. Defaults to `""`.
- `tags: set[str]` -- Set of tags for discovery. Defaults to `set()`.
- `metadata: NodeMetadata | dict` -- If `NodeMetadata`, stored as internal metadata. If `dict`, treated as a user parameter and stored in `self.config["metadata"]`.
- Any additional kwargs matching `get_parameters()` definitions are stored in `self.config`.

**Initialization sequence**:

1. Sets `self._node_id` from `_node_id` kwarg or class name
2. Creates `self._node_metadata` (NodeMetadata) via type-based routing of `metadata` kwarg
3. Sets up `self.logger` as `logging.getLogger(f"kailash.nodes.{self._node_id}")`
4. Filters internal fields from kwargs to populate `self.config`
5. Initializes parameter resolution cache (LRU, configurable via `KAILASH_PARAM_CACHE_SIZE` env var, default 128)
6. Calls `self._validate_config()` to verify configuration against parameter definitions

**Raises**:

- `NodeConfigurationError` -- If configuration is invalid, metadata validation fails, or any initialization step fails

**Contracts**:

- Internal fields (`_node_id`, private underscore-prefixed fields, `NodeMetadata` objects) are never stored in `self.config`
- Fields like `name`, `description`, `version`, `author`, `tags` are treated as internal unless they appear in the node's `get_parameters()` return value -- in which case they are preserved in `self.config`
- The parameter cache is thread-safe (uses `threading.Lock` and `OrderedDict` for LRU)
- Cache can be disabled via `KAILASH_DISABLE_PARAM_CACHE=true` env var

#### 1.1.2 Properties

**`id: str` (property)**

- Getter: Returns `self._node_id`
- Setter: Sets `self._node_id` (backward compatibility for `graph.py` and other internal code)

**`metadata: NodeMetadata` (property)**

- Getter: Returns `self._node_metadata`
- Setter: Type-based routing:
  - `NodeMetadata` object --> sets `self._node_metadata`
  - `dict` or `None` --> sets `self.config["metadata"]`
  - Other types --> raises `TypeError`

#### 1.1.3 Abstract Methods

**`get_parameters(self) -> dict[str, NodeParameter]`**

- MUST be implemented by all concrete nodes
- Returns a dictionary mapping parameter names to `NodeParameter` definitions
- Used during initialization (`_validate_config`), runtime validation (`validate_inputs`), workflow connection validation, and export

**`run(self, **kwargs) -> dict[str, Any]`\*\*

- MUST be implemented by all concrete nodes
- Receives validated input parameters as keyword arguments
- MUST return a JSON-serializable dictionary
- MUST be stateless -- no side effects between runs
- Called by `execute()` which handles input validation, output validation, error wrapping, and timing

#### 1.1.4 Optional Methods

**`get_output_schema(self) -> dict[str, NodeParameter]`**

- Optional. Returns output parameter definitions for validation.
- Default: returns `{}` (no output schema validation)

#### 1.1.5 Workflow Context Methods

**`get_workflow_context(self, key: str, default: Any | None = None) -> Any`**

- Retrieves shared state from the workflow execution context
- Context is managed by the runtime; allows nodes to share data within a single execution

**`set_workflow_context(self, key: str, value: Any) -> None`**

- Stores shared state in the workflow execution context
- Other nodes in the same execution can retrieve this data

#### 1.1.6 Class-Level Configuration

- `_DEFAULT_CACHE_SIZE = 128` -- Default LRU cache size for parameter resolution
- `_SPECIAL_PARAMS = {"context", "config"}` -- Parameters excluded from cache key computation
- `_strict_unknown_params = False` -- When `True`, errors on unknown parameters instead of ignoring them
- `_env_cache: dict[str, str | None]` -- Class-level cache for environment variable lookups, cleared via `_clear_env_cache()`

### 1.2 NodeParameter

**Module**: `kailash.nodes.base`
**Import**: `from kailash import NodeParameter`
**Base**: `pydantic.BaseModel`

Defines the schema for a single node input or output parameter.

```python
class NodeParameter(BaseModel):
    name: str                           # Parameter name
    type: Any | None = None             # Expected Python type (e.g., str, int, dict)
    required: bool = True               # Whether parameter is required
    default: Any | None = None          # Default value for optional parameters
    description: str = ""               # Human-readable description

    # UI/validation extensions
    choices: list[Any] | None = None    # Valid choices for this parameter
    enum: list[Any] | None = None       # Enumerated values
    default_value: Any | None = None    # Alternative default value specification
    category: str = ""                  # Parameter category for grouping
    display_name: str = ""              # Human-readable display name
    icon: str = ""                      # Icon identifier for UI display

    # Port direction markers
    input: bool = False                 # Whether this is an input port
    output: bool = False                # Whether this is an output port

    # Auto-mapping capabilities
    auto_map_from: list[str] = []       # Alternative parameter names for auto-mapping
    auto_map_primary: bool = False      # Designate as primary input for automatic data routing
    workflow_alias: str = ""            # Preferred name in workflow connections
```

**Contracts**:

- When `required=True` and no `default` is provided, the parameter must be supplied at runtime
- `auto_map_from` enables flexible parameter resolution -- if the primary name is not found, alternatives are tried in order
- `auto_map_primary=True` designates this parameter as the primary receiver for incoming workflow data

### 1.3 NodeMetadata

**Module**: `kailash.nodes.base`
**Import**: `from kailash import NodeMetadata`
**Base**: `pydantic.BaseModel`

Stores descriptive information about a node used for discovery, version tracking, documentation, and export.

```python
class NodeMetadata(BaseModel):
    id: str = ""                                    # Node ID
    name: str                                       # Node name (required)
    description: str = ""                           # Node description
    version: str = "1.0.0"                          # Node version
    author: str = ""                                # Node author
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tags: set[str] = Field(default_factory=set)     # Tags for discovery
```

### 1.4 NodeRegistry

**Module**: `kailash.nodes.base`

Global registry for node type discovery. Nodes are registered via the `@register_node()` decorator.

- `NodeRegistry.get(node_type_name: str) -> type` -- Resolves a node type name to its class. Raises if not found.
- SDK nodes (registered via `@register_node()`) can be referenced by string name in `add_node()`
- Custom (unregistered) nodes MUST be referenced by class
