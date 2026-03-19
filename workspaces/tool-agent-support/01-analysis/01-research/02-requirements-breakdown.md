# Tool Agent Support -- Requirements Breakdown

## Executive Summary

- **Feature**: Tool agent capabilities for CARE Platform (six deliverables across four packages)
- **Complexity**: High (cross-package coordination, CARE/EATP/CO alignment, multiple new modules)
- **Risk Level**: Medium (significant existing code to build on, but ADR conflicts and package placement decisions required)
- **Estimated Effort**: 7 weeks total across P1-P6 (some parallelizable)

---

## Architecture Decision Records

### ADR-1: Pydantic vs Dataclass for Agent Manifests

**Status**: Proposed

**Context**: The product brief specifies "Pydantic model for `kaizen.toml` parsing" for `AgentManifest`. However, the EATP SDK rules (`.claude/rules/eatp.md`) mandate `@dataclass` with `to_dict()`/`from_dict()` for all data types. The kaizen package overwhelmingly uses `@dataclass` (263 occurrences vs 3 Pydantic imports, two of which are lazy-loaded for performance). Kaizen's `core/config.py` already uses `tomllib` with `@dataclass`-based `BaseAgentConfig`. The existing `AgentConfig`, `AgentRegistration`, `ExternalAgentBudget`, and all EATP types are `@dataclass`.

**Decision**: Use `@dataclass` with `to_dict()`/`from_dict()` for `AgentManifest`, `AppManifest`, and `GovernanceManifest`. Parse TOML with `tomllib` (Python 3.11+) falling back to `tomli`. Provide explicit validation in `__post_init__` rather than relying on Pydantic validators.

**Rationale**:

1. EATP rules are explicit: "@dataclass (NOT Pydantic)" -- this is a project-wide convention
2. 263 dataclass uses vs 3 Pydantic imports in kailash-kaizen -- overwhelming precedent
3. `kaizen.core.config` already demonstrates the TOML + dataclass pattern
4. Pydantic adds a 1.8s import delay (documented in `core/config.py` lazy import comment)
5. Manifest data is static configuration, not dynamic validation -- `__post_init__` is sufficient
6. Maintains consistency with `ExternalAgentBudget`, `AgentRegistration`, and all EATP types

**Consequences**:

- Positive: Consistent with entire codebase, no new dependency, faster imports
- Negative: Manual validation in `__post_init__` requires more code than Pydantic validators
- Mitigation: Extract shared validation helpers (e.g., `_validate_non_empty_string`, `_validate_risk_level`)

**Alternatives Considered**:

- Pydantic BaseModel: Rejected -- contradicts EATP rules, adds import latency, inconsistent with 263 dataclass usages
- attrs: Rejected -- not used anywhere in the codebase, adds dependency
- TypedDict: Rejected -- no `__post_init__` for validation, less ergonomic

---

### ADR-2: MCP Catalog Server Package Placement

**Status**: Proposed

**Context**: The brief says "Package: kailash-mcp", but `packages/kailash-mcp/` does not exist as a directory. MCP server implementation currently lives in three locations:

1. `src/kailash/mcp_server/` -- Core SDK's production MCP server (FastMCP-based, `MCPServer` class)
2. `packages/eatp/src/eatp/mcp/server.py` -- EATP trust operations MCP server (raw JSON-RPC over stdio)
3. `packages/kailash-nexus/src/nexus/mcp/server.py` -- Nexus MCP channel

The Core SDK MCP server at `src/kailash/mcp_server/server.py` is the most mature pattern: FastMCP-based, supports auth, metrics, caching, rate limiting, and multiple transports. The EATP MCP server uses raw JSON-RPC (no FastMCP dependency). The catalog server needs to interact with Kaizen agent registry and EATP trust operations.

**Decision**: Implement the MCP Catalog Server as a new module within the Core SDK's MCP server package at `src/kailash/mcp_server/catalog.py`, using the existing `MCPServer` base class. The catalog server extends the proven FastMCP pattern rather than creating a new package.

**Rationale**:

1. `kailash-mcp` package does not exist -- creating it adds package management overhead for one module
2. Core SDK's `MCPServer` already has auth, metrics, caching, transports -- the catalog server needs all of these
3. The catalog server wraps CARE Platform API calls -- it is an MCP tool layer, not a framework
4. Kaizen agent data and EATP trust data are accessed via imports, not package boundaries
5. The EATP MCP server (`eatp/mcp/server.py`) pattern shows how to build domain-specific MCP tools that coexist

**Consequences**:

- Positive: Reuses proven infrastructure, no new package to maintain, consistent patterns
- Negative: Adds kaizen/eatp as optional dependencies of core SDK MCP server
- Mitigation: Lazy imports for kaizen/eatp -- catalog tools only instantiate when called

**Alternatives Considered**:

- New `kailash-mcp` package: Rejected -- package does not exist, creates maintenance burden, duplicates MCP infra
- Inside `kailash-kaizen`: Rejected -- MCP server is infrastructure, not agent framework
- Inside `kailash-nexus`: Possible but nexus is multi-channel deployment, not tool catalog

---

### ADR-3: Budget Tracking Package Placement

**Status**: Proposed

**Context**: The brief says "Package: kailash-kaizen or kailash-dataflow". Existing budget/cost tracking is distributed across:

1. `kaizen.cost.tracker.CostTracker` -- Multi-modal API cost tracking (Ollama/OpenAI specific, float precision)
2. `kaizen.core.autonomy.permissions.budget_enforcer.BudgetEnforcer` -- Tool execution cost tracking (static methods, per-tool cost tables)
3. `kaizen.core.autonomy.hooks.builtin.cost_tracking_hook.CostTrackingHook` -- Hook that accumulates costs per agent/tool
4. `kaizen.trust.governance.budget_enforcer.ExternalAgentBudgetEnforcer` -- Multi-dimensional budget enforcement (async, DataFlow integration)
5. `eatp.governance.cost_estimator.ExternalAgentCostEstimator` -- Platform-based cost estimation

The brief's `BudgetTracker` has unique requirements: Decimal precision, `threading.Lock` for thread safety, `reserve()`/`record()` pattern for check-and-commit. This is closest to `ExternalAgentBudgetEnforcer` but simpler (single-dimension, no DataFlow dependency, synchronous).

**Decision**: Place `BudgetTracker` in `kaizen.governance.budget` as a lightweight, synchronous, thread-safe tracker. It complements the existing `ExternalAgentBudgetEnforcer` (async, multi-dimensional) and `BudgetEnforcer` (static, per-tool) without replacing either.

**Rationale**:

1. The brief's design (Decimal, Lock, reserve/record) is a governance concern, not a DataFlow concern
2. `kaizen.trust.governance` already contains budget_enforcer and cost_estimator
3. The new BudgetTracker serves application-level budgets (CARE's Operating Envelope concept)
4. DataFlow handles data operations, not budget accounting
5. Colocation with existing governance code enables future integration

**Consequences**:

- Positive: Clear separation (app-level budget vs tool-level cost vs multi-modal tracking)
- Negative: Third budget-related module in kaizen (alongside CostTracker and BudgetEnforcer)
- Mitigation: Document the three-tier budget architecture in module docstrings

**Alternatives Considered**:

- kailash-dataflow: Rejected -- BudgetTracker is governance, not data operations
- kaizen.cost: Would cluster with CostTracker, but CostTracker is provider-focused, not governance
- eatp.governance: Possible, but EATP is protocol-level; BudgetTracker is application-level

---

### ADR-4: DataFlow Aggregation API Surface

**Status**: Proposed

**Context**: The brief requests `count_by`, `sum_by`, `aggregate` as convenience functions. The existing `AggregateNode` (407 lines) already supports:

- Natural language expressions: "sum of amount", "count of users", "average price by region"
- GROUP BY via "by" keyword detection
- Filter expressions: "where status is active"
- Functions: sum, average, count, min, max, median, mode, std, variance
- Auto-detection of numeric fields

However, `AggregateNode` is an in-memory node -- it operates on pre-fetched Python lists, not database queries. The brief requires "Must work across PostgreSQL, SQLite, and MongoDB backends", implying SQL/MongoDB `GROUP BY` queries pushed to the database, not in-memory aggregation.

**Decision**: Create a new `dataflow.query` module with `count_by()`, `sum_by()`, and `aggregate()` functions that generate database-level aggregation queries. These complement (not replace) the existing `AggregateNode` which handles in-memory aggregation with NL parsing.

**Rationale**:

1. Database-level aggregation is fundamentally different from in-memory aggregation
2. `AggregateNode` pulls all data then aggregates in Python -- wrong for large datasets
3. `count_by()` should generate `SELECT field, COUNT(*) FROM table GROUP BY field`
4. Must support three backends with dialect-appropriate SQL (and MongoDB `$group`)
5. Follows DataFlow's existing adapter pattern (`SQLiteAdapter`, `PostgreSQLAdapter`, `MongoDBAdapter`)

**Consequences**:

- Positive: Real database aggregation, supports large datasets, dialect-portable
- Negative: New query module adds surface area; must handle three backends
- Mitigation: Use DataFlow's existing adapter infrastructure for dialect translation

**Alternatives Considered**:

- Extend AggregateNode: Rejected -- it is an in-memory node; database queries are a different abstraction
- Add to DataFlow engine: Possible but engine is already complex; standalone module is cleaner
- SQL-only (drop MongoDB): Rejected -- brief explicitly requires MongoDB support

---

### ADR-5: Posture State Machine -- What is New vs Already Exists

**Status**: Proposed

**Context**: The brief requests four types: `PostureStateMachine`, `TransitionGuard`, `PostureEvidence`, `EvaluationResult`. Examining `eatp/postures.py` (728 lines), the following already exist:

| Type                         | Exists? | Location                                      | Status                                                                      |
| ---------------------------- | ------- | --------------------------------------------- | --------------------------------------------------------------------------- |
| `PostureStateMachine`        | Yes     | `eatp.postures`                               | Complete -- 5-posture machine, guards, bounded history, emergency downgrade |
| `TransitionGuard`            | Yes     | `eatp.postures`                               | Complete -- name, check_fn, applies_to, reason_on_failure                   |
| `PostureTransitionRequest`   | Yes     | `eatp.postures`                               | Complete -- agent_id, from/to posture, reason, metadata                     |
| `TransitionResult`           | Yes     | `eatp.postures`                               | Complete -- success, blocked_by, to_dict()                                  |
| `PostureConstraints`         | Yes     | `eatp.postures`                               | Complete -- audit_required, allowed_capabilities                            |
| `TrustPostureMapper`         | Yes     | `eatp.postures`                               | Complete -- verification result to posture mapping                          |
| `PostureAwareAgent`          | Yes     | `eatp.posture_agent`                          | Complete -- wraps agents with posture-based execution                       |
| `PostureEvidence`            | No      | --                                            | Not implemented                                                             |
| `EvaluationResult` (posture) | Partial | `eatp.constraints.evaluator.EvaluationResult` | Exists but for constraint evaluation, not posture evaluation                |

What is genuinely missing:

1. `PostureEvidence` -- evidence record (observation count, success rate, time at current posture)
2. Posture-specific `EvaluationResult` -- structured result from posture evaluation (approved/denied/deferred)
3. Evidence-based transition logic -- `TransitionGuard` currently takes a lambda; it needs a guard that evaluates `PostureEvidence` against configurable thresholds

**Decision**: Add `PostureEvidence` and posture-specific `EvaluationResult` to `eatp.postures`. Add an `EvidenceBasedGuard` that uses `PostureEvidence` to make transition decisions. Do NOT duplicate or replace the existing `PostureStateMachine`, `TransitionGuard`, or `TransitionResult`.

**Rationale**:

1. 90% of the brief's P5 already exists and is production-quality (bounded history, emergency downgrade)
2. Only PostureEvidence and posture EvaluationResult are genuinely new types
3. The existing TransitionGuard's `check_fn: Callable` design accommodates evidence-based guards naturally
4. Renaming or restructuring existing types would break imports across kaizen and eatp

**Consequences**:

- Positive: Minimal new code, builds on proven foundation, no breaking changes
- Negative: Brief's naming (`eatp.posture.*`) implies a new submodule; we add to existing `eatp.postures`
- Mitigation: Add `eatp.postures.PostureEvidence` and re-export from `eatp.posture` alias if needed

---

## Functional Requirements by Deliverable

### P1: Agent Deployment Manifest

**Package**: `kailash-kaizen`
**Module**: `kaizen.manifest`
**Estimated Effort**: 1 week

#### REQ-P1-01: AgentManifest

```python
@dataclass
class AgentManifest:
    """Parsed representation of kaizen.toml."""

    # [agent] section
    name: str                        # Required, non-empty
    module: str                      # Required, dotted Python module path
    class_name: str                  # Required, valid Python identifier

    # [agent.metadata]
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    version: str = "0.1.0"          # semver format

    # [agent.capabilities]
    tools: list[str] = field(default_factory=list)
    supported_models: list[str] = field(default_factory=list)

    # [governance]
    governance: GovernanceManifest | None = None

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentManifest: ...

    @classmethod
    def from_toml(cls, path: str | Path) -> AgentManifest:
        """Parse kaizen.toml file. Raises FileNotFoundError, ValueError."""
        ...

    @classmethod
    def from_toml_string(cls, content: str) -> AgentManifest:
        """Parse TOML string content."""
        ...
```

**Input**: TOML file path or string content
**Output**: Validated `AgentManifest` instance
**Error Conditions**:

- `FileNotFoundError` if path does not exist
- `ValueError` if required fields missing (`name`, `module`, `class_name`)
- `ValueError` if `name` contains invalid characters (must match `^[a-zA-Z][a-zA-Z0-9_-]*$`)
- `ValueError` if `version` is not valid semver
  **Thread Safety**: Immutable after construction (no shared mutable state)
  **Serialization**: TOML (input), dict/JSON (output)

#### REQ-P1-02: AppManifest

```python
@dataclass
class AppManifest:
    """Parsed representation of app.toml for application registration."""

    name: str                        # Required, non-empty
    description: str = ""
    agents_requested: list[str] = field(default_factory=list)
    budget: float | None = None      # USD, must be finite and non-negative
    justification: str = ""
    owner: str = ""

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppManifest: ...

    @classmethod
    def from_toml(cls, path: str | Path) -> AppManifest: ...
```

**Error Conditions**:

- `ValueError` if `budget` is negative, NaN, or Inf (must use `math.isfinite()` per EATP rules)
- `ValueError` if `name` is empty

#### REQ-P1-03: GovernanceManifest

```python
@dataclass
class GovernanceManifest:
    """Governance metadata section from kaizen.toml [governance]."""

    purpose: str = ""
    risk_level: str = "low"          # Must be: "low", "medium", "high", "critical"
    data_access_needed: list[str] = field(default_factory=list)
    suggested_posture: str = "supervised"  # Must be valid TrustPosture value

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceManifest: ...
```

**Error Conditions**:

- `ValueError` if `risk_level` not in `{"low", "medium", "high", "critical"}`
- `ValueError` if `suggested_posture` not in `TrustPosture` values

#### REQ-P1-04: introspect_agent()

```python
def introspect_agent(
    module: str,
    class_name: str,
) -> dict[str, Any]:
    """
    Reads Agent class, extracts Signature/tools/A2A card/capabilities.

    Returns:
        dict with keys: name, module, class_name, signature, tools,
        capabilities, a2a_card_compatible, metadata

    Raises:
        ImportError: if module cannot be imported
        AttributeError: if class_name not found in module
        TypeError: if class is not a valid Kaizen agent
    """
```

**Input**: Dotted module path string, class name string
**Output**: Dict with extracted agent metadata (signature fields, tool names, capabilities)
**Business Logic**:

1. Import the module using `importlib.import_module(module)`
2. Get the class via `getattr(mod, class_name)`
3. Check if class inherits from `BaseAgent` or has Kaizen agent markers
4. Extract: `Signature` fields (InputField/OutputField), registered tools, A2A capabilities
5. Use existing `TypeIntrospector` for JSON schema generation from type annotations
   **Edge Cases**:

- Module has syntax errors (wrap ImportError)
- Class exists but is not an agent (TypeError with helpful message)
- Class has no signature (return empty signature section)
- Circular imports (catch and wrap)

#### REQ-P1-05: deploy()

```python
async def deploy(
    manifest: AgentManifest,
    target_url: str,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> DeployResult:
    """
    HTTP POST registration to CARE Platform API.

    Returns:
        DeployResult with status, agent_id, registration_url

    Raises:
        ConnectionError: if target_url unreachable
        ValueError: if manifest validation fails server-side
        PermissionError: if api_key is invalid
    """

@dataclass
class DeployResult:
    success: bool
    agent_id: str | None = None
    registration_url: str | None = None
    error: str | None = None
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]: ...
```

**Input**: Validated manifest, target URL, optional API key
**Output**: `DeployResult` with success status and registration details
**Business Logic**:

1. Validate manifest (call `manifest.to_dict()` to ensure serializable)
2. POST to `{target_url}/api/v1/agents/register` with JSON body
3. Include `Authorization: Bearer {api_key}` header if api_key provided
4. Handle HTTP errors: 401 -> PermissionError, 422 -> ValueError, 5xx -> ConnectionError
5. Parse response JSON into `DeployResult`
   **Security**: API key must come from environment variable or parameter, never hardcoded (per security rules). Use `httpx` or `aiohttp` for async HTTP.
   **Thread Safety**: Stateless function, safe for concurrent calls

---

### P2: MCP Catalog Server

**Package**: Core SDK (`src/kailash/mcp_server/catalog.py`)
**Estimated Effort**: 2 weeks

#### REQ-P2-01: catalog_search

```python
async def catalog_search(
    query: str,
    capabilities: list[str] | None = None,
    type: str | None = None,          # "tool_agent", "composite", "service"
    status: str | None = None,        # "active", "inactive", "deploying"
) -> list[dict[str, Any]]:
    """
    Search for agents in the catalog.

    Returns list of matching agent summaries with: name, description,
    capabilities, status, version.
    """
```

**Input**: Search query string, optional filters
**Output**: List of agent summary dicts (bounded: max 100 results)
**Business Logic**: Full-text search on agent name/description + capability filter + status filter. Uses Kaizen's `AgentRegistration` registry as data source.

#### REQ-P2-02: catalog_describe

```python
async def catalog_describe(agent_name: str) -> dict[str, Any]:
    """
    Get detailed description of a named agent.

    Returns full agent metadata: manifest, capabilities, tools,
    governance info, trust posture, version history.

    Raises:
        ValueError: if agent_name not found
    """
```

#### REQ-P2-03: catalog_schema

```python
async def catalog_schema(agent_name: str) -> dict[str, Any]:
    """
    Get input/output JSON Schema for an agent.

    Returns:
        dict with "input_schema" and "output_schema" keys,
        each containing valid JSON Schema.

    Raises:
        ValueError: if agent_name not found
    """
```

**Business Logic**: Uses `TypeIntrospector.type_to_json_schema()` to generate schemas from agent Signature fields.

#### REQ-P2-04: catalog_deps

```python
async def catalog_deps(agent_name: str) -> dict[str, Any]:
    """
    Get dependency graph for composite agents.

    Returns:
        dict with "dependencies" (list of agent names),
        "dependency_graph" (adjacency list), "is_composite" (bool)

    Raises:
        ValueError: if agent_name not found
    """
```

#### REQ-P2-05: deploy_agent

```python
async def deploy_agent(
    manifest_path_or_content: str,
) -> dict[str, Any]:
    """
    Deploy an agent from manifest.

    Accepts either a file path to kaizen.toml or inline TOML content.

    Returns:
        dict with "agent_id", "status", "deployment_url"
    """
```

**Business Logic**: Parse manifest (detect path vs content), validate, call `deploy()` from P1.

#### REQ-P2-06: deploy_status

```python
async def deploy_status(agent_name: str) -> dict[str, Any]:
    """
    Check deployment status of an agent.

    Returns:
        dict with "status" ("deploying", "active", "failed", "inactive"),
        "last_deployed", "health_check_url"
    """
```

#### REQ-P2-07: app_register

```python
async def app_register(
    name: str,
    description: str,
    agents_requested: list[str],
    budget: float,
    justification: str,
) -> dict[str, Any]:
    """
    Register an application requesting agent access.

    Returns:
        dict with "app_id", "status" ("pending_approval", "approved"),
        "requested_agents", "budget_allocated"
    """
```

**Business Logic**: Create `AppManifest`, validate budget (must be finite, non-negative), register with CARE Platform API.

#### REQ-P2-08: app_status

```python
async def app_status(app_name: str) -> dict[str, Any]:
    """
    Check application registration status.

    Returns:
        dict with "status", "approved_agents", "budget_remaining",
        "usage_summary"
    """
```

**MCP Server Registration Pattern** (all tools registered on a single `MCPServer` instance):

```python
class CatalogMCPServer:
    """MCP Catalog Server for tool agent discovery."""

    def __init__(
        self,
        name: str = "kailash-catalog",
        agent_registry: AgentRegistry | None = None,
        care_api_url: str | None = None,
        api_key: str | None = None,
    ):
        self._server = MCPServer(name=name)
        self._registry = agent_registry
        self._care_api_url = care_api_url
        self._api_key = api_key
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all catalog MCP tools."""
        # Register each tool with self._server.tool() decorator
        ...

    def run(self, transport: str = "stdio") -> None:
        """Start the MCP catalog server."""
        self._server.run(transport=transport)
```

---

### P3: Composite Agent Validation

**Package**: `kailash-kaizen`
**Module**: `kaizen.composition`
**Estimated Effort**: 1 week

#### REQ-P3-01: validate_dag

```python
@dataclass
class ValidationResult:
    """Result of DAG validation."""
    valid: bool
    cycles: list[list[str]] = field(default_factory=list)   # Detected cycles
    errors: list[str] = field(default_factory=list)          # Error messages
    warnings: list[str] = field(default_factory=list)        # Warning messages
    node_count: int = 0
    edge_count: int = 0

    def to_dict(self) -> dict[str, Any]: ...

def validate_dag(
    agents: list[dict[str, Any]],
) -> ValidationResult:
    """
    Validate that a composition of agents forms a valid DAG.

    Each agent dict has: {"name": str, "depends_on": list[str]}

    Checks:
    1. No cycles (Kahn's algorithm or DFS-based)
    2. All referenced dependencies exist
    3. No self-references
    4. Graph is connected (all nodes reachable from at least one root)

    Args:
        agents: List of agent definitions with dependency information

    Returns:
        ValidationResult with cycle details if invalid

    Raises:
        ValueError: if agents list is empty or contains invalid entries
    """
```

**Business Logic**:

1. Build adjacency list from `depends_on` fields
2. Validate all referenced names exist in agent list
3. Run topological sort (Kahn's algorithm) to detect cycles
4. If cycle detected, use DFS to identify exact cycle path(s)
5. Check connectivity -- warn if disconnected subgraphs exist

**Relationship to existing code**: `eatp.graph_validator.DelegationGraphValidator` provides cycle detection for delegation chains using DFS. The P3 validator serves a different domain (agent composition) but can reuse the algorithmic approach. However, P3 operates on `list[dict]` while EATP operates on `DelegationRecord`. Recommend implementing independently to avoid coupling agent composition to EATP internals.

#### REQ-P3-02: check_schema_compatibility

```python
@dataclass
class CompatibilityResult:
    """Result of schema compatibility check."""
    compatible: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)  # Required output fields missing in input
    type_mismatches: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]: ...

def check_schema_compatibility(
    output_schema: dict[str, Any],
    input_schema: dict[str, Any],
) -> CompatibilityResult:
    """
    Verify agent A output pipes to agent B input.

    Checks:
    1. All required input fields exist in output
    2. Field types are compatible (exact match or coercible)
    3. Nested object structures are compatible
    4. Array item types are compatible

    Args:
        output_schema: JSON Schema of producing agent's output
        input_schema: JSON Schema of consuming agent's input

    Returns:
        CompatibilityResult with detailed mismatch info
    """
```

**Business Logic**:

1. Extract `required` fields from input_schema
2. Check each required field exists in output_schema `properties`
3. Compare types: string->string (exact), int->float (coercible), etc.
4. Handle `anyOf`/`oneOf` schemas by checking if any variant is compatible
5. Recursively check nested `object` and `array` schemas

**Integration**: Uses `TypeIntrospector.type_to_json_schema()` output format as the schema contract.

#### REQ-P3-03: estimate_cost

```python
@dataclass
class CompositionCostEstimate:
    """Cost estimate for a composite agent execution."""
    total_estimated_cost: float        # USD
    per_agent_costs: dict[str, float]  # agent_name -> estimated cost
    confidence: str = "low"            # "low", "medium", "high"
    based_on_samples: int = 0          # Number of historical data points used
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]: ...

def estimate_cost(
    composition: list[dict[str, Any]],
    historical_data: dict[str, list[float]] | None = None,
) -> CompositionCostEstimate:
    """
    Cost projection from sub-agent history.

    Args:
        composition: List of agent definitions (same format as validate_dag)
        historical_data: Optional dict mapping agent_name to list of
                        historical execution costs (USD)

    Returns:
        CompositionCostEstimate with per-agent and total projections
    """
```

**Business Logic**:

1. For agents with historical data: use median cost \* 1.2 buffer (matches `ExternalAgentCostEstimator.COST_BUFFER`)
2. For agents without data: use `ExternalAgentCostEstimator` defaults
3. Sum per-agent costs for total
4. Confidence based on sample count: <5 -> "low", 5-20 -> "medium", >20 -> "high"
5. Warn if any agent has zero historical data

---

### P4: DataFlow Aggregation Query Patterns

**Package**: `kailash-dataflow`
**Module**: `dataflow.query`
**Estimated Effort**: 1 week

#### REQ-P4-01: count_by

```python
async def count_by(
    model: str,
    group_by_field: str,
    filter: dict[str, Any] | None = None,
    *,
    connection: Any = None,           # DataFlow connection/adapter
) -> dict[str, int]:
    """
    COUNT(*) GROUP BY query.

    Args:
        model: DataFlow model/table name
        group_by_field: Field to group by
        filter: Optional filter conditions (e.g., {"status": "active"})
        connection: DataFlow database connection

    Returns:
        Dict mapping group_by_field values to counts
        e.g., {"active": 42, "inactive": 8}

    Raises:
        ValueError: if model or group_by_field is empty
        ConnectionError: if database unreachable
    """
```

**SQL Generation (PostgreSQL/SQLite)**:

```sql
SELECT "group_by_field", COUNT(*) as count
FROM "model"
WHERE filter_conditions
GROUP BY "group_by_field"
```

**MongoDB Generation**:

```python
pipeline = [
    {"$match": filter_conditions},
    {"$group": {"_id": f"${group_by_field}", "count": {"$sum": 1}}}
]
```

**Security**: Table and column names must be validated with `_validate_identifier()` pattern per infrastructure-sql rules. Filter values must use parameterized queries.

#### REQ-P4-02: sum_by

```python
async def sum_by(
    model: str,
    sum_field: str,
    group_by_field: str,
    filter: dict[str, Any] | None = None,
    *,
    connection: Any = None,
) -> dict[str, float]:
    """
    SUM GROUP BY query.

    Args:
        model: DataFlow model/table name
        sum_field: Numeric field to sum
        group_by_field: Field to group by
        filter: Optional filter conditions
        connection: DataFlow database connection

    Returns:
        Dict mapping group_by_field values to sums
        e.g., {"electronics": 15000.50, "books": 2300.00}

    Raises:
        ValueError: if any field name is invalid
    """
```

#### REQ-P4-03: aggregate

```python
@dataclass
class AggregationSpec:
    """Specification for a single aggregation operation."""
    function: str         # "count", "sum", "avg", "min", "max"
    field: str | None = None  # None valid for "count"
    alias: str | None = None  # Output column name

    def to_dict(self) -> dict[str, Any]: ...

async def aggregate(
    model: str,
    aggregations: list[AggregationSpec],
    group_by: list[str] | None = None,
    filter: dict[str, Any] | None = None,
    having: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    *,
    connection: Any = None,
) -> list[dict[str, Any]]:
    """
    Generic multi-aggregation query.

    Args:
        model: DataFlow model/table name
        aggregations: List of aggregation specifications
        group_by: Optional list of fields to group by
        filter: WHERE conditions
        having: HAVING conditions (post-aggregation filter)
        order_by: ORDER BY field (prefix with "-" for DESC)
        limit: Maximum rows to return
        connection: DataFlow database connection

    Returns:
        List of result dicts with aggregation values

    Raises:
        ValueError: if aggregations list is empty
        ValueError: if function not in allowed set
    """
```

**Allowed aggregation functions**: `{"count", "sum", "avg", "min", "max"}` (whitelist -- no arbitrary SQL functions).

**SQL Generation Example**:

```sql
SELECT region,
       COUNT(*) as order_count,
       SUM(amount) as total_amount,
       AVG(amount) as avg_amount
FROM orders
WHERE status = ?
GROUP BY region
HAVING COUNT(*) > ?
ORDER BY total_amount DESC
LIMIT ?
```

**Security Requirements**:

- All identifier names (model, field, group*by) validated with `^[a-zA-Z*][a-zA-Z0-9_]\*$`
- All filter values use parameterized queries (`?` placeholder per infrastructure-sql rules)
- Aggregation functions whitelisted -- no user-provided SQL functions
- LIMIT must be bounded (default: 1000, max: 10000)

---

### P5: EATP Posture State Machine -- New Types

**Package**: `eatp`
**Module**: `eatp.postures` (additions to existing module)
**Estimated Effort**: 3-4 days (90% already exists)

#### REQ-P5-01: PostureEvidence (NEW)

```python
@dataclass
class PostureEvidence:
    """Evidence record for posture change justification.

    Captures quantitative metrics that support or oppose a posture transition.
    Used by evidence-based TransitionGuards to make automated decisions.
    """

    agent_id: str
    observation_count: int = 0           # Total observations in evaluation window
    success_count: int = 0               # Successful executions
    failure_count: int = 0               # Failed executions
    time_at_current_posture_seconds: float = 0.0  # Duration at current posture
    constraint_violations: int = 0       # Number of constraint violations
    escalation_count: int = 0            # Times escalated to higher posture
    last_failure_timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0-1.0). Returns 0.0 if no observations."""
        if self.observation_count == 0:
            return 0.0
        return self.success_count / self.observation_count

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostureEvidence: ...
```

**Validation** (`__post_init__`):

- `observation_count >= 0`, `success_count >= 0`, `failure_count >= 0`
- `success_count + failure_count <= observation_count`
- `time_at_current_posture_seconds >= 0` and `math.isfinite()` (per EATP rules)
- `constraint_violations >= 0`

#### REQ-P5-02: PostureEvaluationResult (NEW)

```python
@dataclass
class PostureEvaluationResult:
    """Structured result from posture evaluation.

    Distinct from eatp.constraints.evaluator.EvaluationResult which evaluates
    constraint dimensions. This evaluates posture transition readiness.
    """

    decision: str                     # "approved", "denied", "deferred"
    recommended_posture: TrustPosture
    current_posture: TrustPosture
    evidence: PostureEvidence
    rationale: str = ""
    confidence: float = 0.0           # 0.0-1.0
    conditions: list[str] = field(default_factory=list)  # Conditions for approval

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostureEvaluationResult: ...
```

**Validation**:

- `decision` must be in `{"approved", "denied", "deferred"}`
- `confidence` must be in [0.0, 1.0] and `math.isfinite()`

#### REQ-P5-03: EvidenceBasedGuard (NEW)

```python
@dataclass
class EvidenceThresholds:
    """Configurable thresholds for evidence-based posture evaluation."""

    min_observations: int = 10
    min_success_rate: float = 0.95
    min_time_at_posture_seconds: float = 86400.0  # 24 hours
    max_constraint_violations: int = 0
    max_recent_failures: int = 0

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceThresholds: ...

class EvidenceBasedGuard:
    """TransitionGuard that evaluates PostureEvidence against thresholds.

    Usage:
        guard = EvidenceBasedGuard(
            thresholds=EvidenceThresholds(min_observations=50, min_success_rate=0.98),
            evidence_provider=my_evidence_fn,
        )
        machine.add_guard(guard.as_transition_guard())
    """

    def __init__(
        self,
        thresholds: EvidenceThresholds,
        evidence_provider: Callable[[str], PostureEvidence],
        name: str = "evidence_based_guard",
    ): ...

    def evaluate(self, agent_id: str) -> PostureEvaluationResult: ...

    def as_transition_guard(self) -> TransitionGuard:
        """Convert to a TransitionGuard for use with PostureStateMachine."""
        ...
```

**Business Logic for `evaluate()`**:

1. Get evidence from `evidence_provider(agent_id)`
2. Check each threshold: observations >= min, success_rate >= min, time >= min, violations <= max
3. If all pass: decision="approved"
4. If any fail but evidence is promising: decision="deferred" with conditions
5. If critical threshold fails: decision="denied"
6. Confidence = (thresholds met / total thresholds)

---

### P6: Budget Tracking

**Package**: `kailash-kaizen`
**Module**: `kaizen.governance.budget`
**Estimated Effort**: 3-4 days

#### REQ-P6-01: BudgetTracker

```python
from decimal import Decimal
from threading import Lock

@dataclass
class BudgetTracker:
    """Thread-safe budget tracker with Decimal precision.

    Designed for application-level budget tracking in CARE Platform.
    Uses check-and-reserve pattern for safe concurrent access.

    Example:
        tracker = BudgetTracker(allocated=Decimal("100.00"))
        if tracker.reserve(Decimal("10.00")):
            result = execute_agent()
            tracker.record(actual_cost)
        remaining = tracker.remaining()
    """

    allocated: Decimal
    consumed: Decimal = Decimal("0")
    _reserved: Decimal = field(default=Decimal("0"), init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self):
        # Validate allocated is finite and non-negative
        # Convert float to Decimal if needed
        ...

    def reserve(self, amount: Decimal) -> bool:
        """
        Check-and-reserve budget atomically (thread-safe).

        Args:
            amount: Amount to reserve (must be positive and finite)

        Returns:
            True if reservation successful, False if insufficient budget
        """
        ...

    def record(self, actual_amount: Decimal) -> None:
        """
        Adjust consumed after provider response.
        Releases reservation and records actual cost.

        Args:
            actual_amount: Actual cost incurred (must be non-negative and finite)

        Raises:
            ValueError: if actual_amount is negative, NaN, or Inf
        """
        ...

    def release(self, reserved_amount: Decimal) -> None:
        """
        Release a reservation without recording consumption.
        Called when an operation is cancelled after reserve().

        Args:
            reserved_amount: Amount to release from reservation
        """
        ...

    def remaining(self) -> Decimal:
        """Current remaining budget (allocated - consumed - reserved)."""
        ...

    def check(self, estimated_cost: Decimal) -> dict[str, Any]:
        """
        Check if estimated cost fits within budget.

        Returns:
            {
                "allowed": bool,
                "remaining": Decimal,
                "consumed": Decimal,
                "reserved": Decimal,
                "allocated": Decimal,
                "utilization": float,  # 0.0-1.0
            }
        """
        ...

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BudgetTracker: ...
```

**Thread Safety**: All mutating methods (`reserve`, `record`, `release`) acquire `self._lock`. Read-only methods (`remaining`, `check`) also acquire lock for consistency.

**Validation** (`__post_init__` and method arguments):

- `allocated` must be non-negative and finite (`math.isfinite(float(allocated))`)
- `consumed` must be non-negative and finite
- `amount` in `reserve()` must be positive and finite
- `actual_amount` in `record()` must be non-negative and finite
- `consumed` can never exceed `allocated` (fail-closed: deny if would exceed)

**Decimal Precision**: All monetary values use `Decimal` to avoid floating-point errors. Constructor accepts both `Decimal` and `float` (converts internally).

---

## Non-Functional Requirements

### Performance Requirements

| Component                    | Metric     | Target                       | Rationale                                    |
| ---------------------------- | ---------- | ---------------------------- | -------------------------------------------- |
| AgentManifest.from_toml()    | Latency    | <10ms per file               | TOML parsing should be fast for CI/CD        |
| introspect_agent()           | Latency    | <200ms per agent             | Module import + reflection                   |
| catalog_search()             | Latency    | <50ms for in-memory registry | Most searches are local                      |
| validate_dag()               | Latency    | <10ms for 100-node graph     | DFS/BFS on small graphs                      |
| check_schema_compatibility() | Latency    | <5ms per schema pair         | JSON Schema comparison                       |
| count_by() / sum_by()        | Latency    | Database-dependent           | Must not add >5ms overhead beyond query time |
| BudgetTracker.reserve()      | Latency    | <1ms                         | Lock contention is the bottleneck            |
| BudgetTracker.reserve()      | Throughput | >10,000 ops/sec              | Python Lock is fast for uncontended case     |

### Memory Requirements

| Component                                | Bound          | Mechanism                                         |
| ---------------------------------------- | -------------- | ------------------------------------------------- |
| PostureStateMachine.\_transition_history | 10,000 entries | Trim oldest 10% at capacity (already implemented) |
| CatalogMCPServer agent cache             | 10,000 entries | LRU eviction                                      |
| BudgetTracker                            | O(1)           | No collections, just Decimal scalars              |
| validate_dag()                           | O(V + E)       | Graph only exists during validation call          |
| AggregationSpec list                     | Max 20         | Reject queries with >20 aggregations              |

### Security Requirements

| Component                 | Requirement               | Mechanism                                     |
| ------------------------- | ------------------------- | --------------------------------------------- |
| deploy() API key          | Must not be hardcoded     | Parameter or environment variable             |
| catalog_search            | Input validation on query | Length limit (500 chars), no SQL injection    |
| aggregate() identifiers   | SQL injection prevention  | `_validate_identifier()` on all field names   |
| aggregate() filter values | Parameterized queries     | `?` placeholders per infrastructure-sql rules |
| BudgetTracker amounts     | Finite number validation  | `math.isfinite()` per EATP rules              |
| GovernanceManifest        | Enum validation           | Whitelist for risk_level, suggested_posture   |
| MCP Catalog Server        | Auth required             | Reuse MCPServer auth infrastructure           |

### Backward Compatibility

| Component           | Constraint                                           |
| ------------------- | ---------------------------------------------------- |
| eatp.postures       | New types added, no existing types modified          |
| kaizen.cost.tracker | CostTracker unchanged, BudgetTracker is new module   |
| AggregateNode       | Unchanged, new query module is separate              |
| MCPServer           | CatalogMCPServer extends, does not modify base class |
| AgentRegistration   | Unchanged, manifest module is new                    |

---

## Acceptance Criteria

### P1: Agent Manifest

- [ ] **AC-P1-01**: `AgentManifest.from_toml("kaizen.toml")` parses the example TOML from the brief successfully
- [ ] **AC-P1-02**: `AgentManifest.from_toml("nonexistent.toml")` raises `FileNotFoundError`
- [ ] **AC-P1-03**: Missing `[agent].name` raises `ValueError` with message containing "name"
- [ ] **AC-P1-04**: `AgentManifest.to_dict()` produces JSON-serializable output
- [ ] **AC-P1-05**: `AgentManifest.from_dict(manifest.to_dict())` round-trips correctly
- [ ] **AC-P1-06**: `GovernanceManifest` with `risk_level="invalid"` raises `ValueError`
- [ ] **AC-P1-07**: `AppManifest` with `budget=float('nan')` raises `ValueError`
- [ ] **AC-P1-08**: `introspect_agent("kaizen.agents.specialized.react", "ReActAgent")` returns dict with signature fields
- [ ] **AC-P1-09**: `introspect_agent("nonexistent.module", "Cls")` raises `ImportError`
- [ ] **AC-P1-10**: `deploy()` with valid manifest and mock server returns `DeployResult(success=True)`
- [ ] **AC-P1-11**: `deploy()` with invalid API key returns `DeployResult(success=False, status_code=401)`

### P2: MCP Catalog Server

- [ ] **AC-P2-01**: `catalog_search(query="market")` returns list of matching agents
- [ ] **AC-P2-02**: `catalog_search(query="", capabilities=["risk_analysis"])` filters by capability
- [ ] **AC-P2-03**: `catalog_describe("nonexistent-agent")` raises ValueError
- [ ] **AC-P2-04**: `catalog_schema("known-agent")` returns valid JSON Schema with `input_schema` and `output_schema`
- [ ] **AC-P2-05**: `deploy_agent("/path/to/kaizen.toml")` parses and deploys successfully
- [ ] **AC-P2-06**: `deploy_agent("inline TOML content")` detects inline content and parses
- [ ] **AC-P2-07**: `app_register(budget=-1.0)` rejects with error (negative budget)
- [ ] **AC-P2-08**: MCP server starts on stdio transport and responds to `tools/list`
- [ ] **AC-P2-09**: MCP server responds to `tools/call` with `catalog_search` tool
- [ ] **AC-P2-10**: Search results bounded to max 100 items

### P3: Composite Agent Validation

- [ ] **AC-P3-01**: Linear DAG (A->B->C) returns `ValidationResult(valid=True)`
- [ ] **AC-P3-02**: Cycle (A->B->A) returns `ValidationResult(valid=False, cycles=[["A","B","A"]])`
- [ ] **AC-P3-03**: Self-reference (A->A) detected as cycle
- [ ] **AC-P3-04**: Missing dependency reference returns error in `ValidationResult.errors`
- [ ] **AC-P3-05**: Empty agents list raises `ValueError`
- [ ] **AC-P3-06**: Disconnected graph produces warning but `valid=True`
- [ ] **AC-P3-07**: Compatible schemas (string output -> string input) return `CompatibilityResult(compatible=True)`
- [ ] **AC-P3-08**: Incompatible schemas (int output -> list input) return `compatible=False` with type_mismatches
- [ ] **AC-P3-09**: Missing required field in output returns `compatible=False` with missing_fields
- [ ] **AC-P3-10**: `estimate_cost` with historical data uses median \* 1.2
- [ ] **AC-P3-11**: `estimate_cost` without data reports `confidence="low"`

### P4: DataFlow Aggregation

- [ ] **AC-P4-01**: `count_by("orders", "status")` generates correct SQL and returns `{"active": N, "inactive": M}`
- [ ] **AC-P4-02**: `sum_by("orders", "amount", "region")` returns per-region sums
- [ ] **AC-P4-03**: `aggregate()` with multiple specs generates multi-column SELECT
- [ ] **AC-P4-04**: Filter parameter generates parameterized WHERE clause (no SQL injection)
- [ ] **AC-P4-05**: Invalid table name (e.g., "users; DROP TABLE") raises `ValueError`
- [ ] **AC-P4-06**: Works with SQLite adapter
- [ ] **AC-P4-07**: Works with PostgreSQL adapter
- [ ] **AC-P4-08**: Works with MongoDB adapter (uses `$group` pipeline)
- [ ] **AC-P4-09**: LIMIT defaults to 1000, rejects > 10000
- [ ] **AC-P4-10**: HAVING clause generates correct SQL with parameterized values
- [ ] **AC-P4-11**: Empty result set returns empty list/dict (not error)

### P5: EATP Posture State Machine

- [ ] **AC-P5-01**: `PostureEvidence` with valid data creates successfully
- [ ] **AC-P5-02**: `PostureEvidence` with negative observation_count raises `ValueError`
- [ ] **AC-P5-03**: `PostureEvidence.success_rate` returns correct ratio
- [ ] **AC-P5-04**: `PostureEvidence.success_rate` returns 0.0 when observation_count is 0
- [ ] **AC-P5-05**: `PostureEvidence` with `time_at_current_posture=float('inf')` raises `ValueError`
- [ ] **AC-P5-06**: `PostureEvaluationResult.to_dict()` and `from_dict()` round-trip
- [ ] **AC-P5-07**: `EvidenceBasedGuard` approves when all thresholds met
- [ ] **AC-P5-08**: `EvidenceBasedGuard` denies when critical threshold fails
- [ ] **AC-P5-09**: `EvidenceBasedGuard` defers when evidence is insufficient but promising
- [ ] **AC-P5-10**: `EvidenceBasedGuard.as_transition_guard()` integrates with existing `PostureStateMachine`
- [ ] **AC-P5-11**: Existing `PostureStateMachine` tests still pass (no regression)

### P6: Budget Tracking

- [ ] **AC-P6-01**: `BudgetTracker(allocated=Decimal("100"))` initializes with zero consumed
- [ ] **AC-P6-02**: `reserve(Decimal("50"))` returns True when budget available
- [ ] **AC-P6-03**: `reserve(Decimal("150"))` returns False when exceeds remaining
- [ ] **AC-P6-04**: `record(Decimal("45"))` updates consumed and releases reservation
- [ ] **AC-P6-05**: `remaining()` returns `allocated - consumed - reserved`
- [ ] **AC-P6-06**: `check(Decimal("30"))` returns dict with `allowed=True` when within budget
- [ ] **AC-P6-07**: Thread-safe: 100 concurrent `reserve()` calls produce correct total
- [ ] **AC-P6-08**: `BudgetTracker(allocated=Decimal("-1"))` raises `ValueError`
- [ ] **AC-P6-09**: `record(Decimal("nan"))` raises `ValueError` (per EATP rules)
- [ ] **AC-P6-10**: `BudgetTracker.to_dict()` / `from_dict()` round-trip preserves Decimal precision
- [ ] **AC-P6-11**: `release()` correctly returns reserved amount to available

---

## Interface Contracts

### What Each Deliverable Exposes

```
P1 (kaizen.manifest) EXPOSES:
  - AgentManifest        -> consumed by P2 (deploy_agent), P3 (estimate_cost)
  - AppManifest          -> consumed by P2 (app_register)
  - GovernanceManifest   -> consumed by P5 (suggested_posture mapping)
  - introspect_agent()   -> consumed by P2 (catalog_describe, catalog_schema)
  - deploy()             -> consumed by P2 (deploy_agent)
  - DeployResult         -> consumed by P2

P2 (kailash mcp_server catalog) EXPOSES:
  - CatalogMCPServer     -> standalone MCP server entry point
  - catalog_search()     -> MCP tool
  - catalog_describe()   -> MCP tool
  - catalog_schema()     -> MCP tool
  - catalog_deps()       -> MCP tool
  - deploy_agent()       -> MCP tool
  - deploy_status()      -> MCP tool
  - app_register()       -> MCP tool
  - app_status()         -> MCP tool

P3 (kaizen.composition) EXPOSES:
  - validate_dag()         -> consumed by P2 (catalog_deps validation)
  - check_schema_compatibility() -> consumed by P2 (catalog_schema validation)
  - estimate_cost()        -> consumed by P2 (catalog_describe cost info)
  - ValidationResult       -> returned by validate_dag
  - CompatibilityResult    -> returned by check_schema_compatibility
  - CompositionCostEstimate -> returned by estimate_cost

P4 (dataflow.query) EXPOSES:
  - count_by()      -> standalone query function
  - sum_by()        -> standalone query function
  - aggregate()     -> standalone query function
  - AggregationSpec -> input to aggregate()

P5 (eatp.postures additions) EXPOSES:
  - PostureEvidence         -> consumed by P5 EvidenceBasedGuard, P1 GovernanceManifest
  - PostureEvaluationResult -> consumed by P5 EvidenceBasedGuard
  - EvidenceBasedGuard      -> consumed by PostureStateMachine.add_guard()
  - EvidenceThresholds      -> configuration for EvidenceBasedGuard

P6 (kaizen.governance.budget) EXPOSES:
  - BudgetTracker -> consumed by P2 (app_register budget tracking)
```

### What Each Deliverable Consumes

```
P1 CONSUMES:
  - tomllib / tomli (stdlib/PyPI)
  - kaizen.core.type_introspector.TypeIntrospector (for introspect_agent)
  - kaizen.agents.registry (for agent class lookup)
  - kaizen.signatures.core (for Signature field extraction)
  - httpx or aiohttp (for deploy HTTP POST)

P2 CONSUMES:
  - kailash.mcp_server.server.MCPServer (base MCP server)
  - P1: AgentManifest, AppManifest, introspect_agent(), deploy()
  - P3: validate_dag(), check_schema_compatibility(), estimate_cost()
  - kaizen.agents.registry.AgentRegistration (agent catalog data)

P3 CONSUMES:
  - eatp.governance.cost_estimator.ExternalAgentCostEstimator (fallback cost estimation)
  - kaizen.core.type_introspector.TypeIntrospector (schema generation)

P4 CONSUMES:
  - DataFlow adapter infrastructure (SQLite, PostgreSQL, MongoDB adapters)
  - Infrastructure SQL rules (_validate_identifier, parameterized queries)

P5 CONSUMES:
  - eatp.postures.TrustPosture (existing enum)
  - eatp.postures.PostureStateMachine (existing class)
  - eatp.postures.TransitionGuard (existing class)
  - eatp.postures.PostureTransitionRequest (existing class)

P6 CONSUMES:
  - decimal.Decimal (stdlib)
  - threading.Lock (stdlib)
  - math.isfinite (stdlib) -- per EATP rules
```

### Dependency Graph Between Deliverables

```
P5 (no cross-deliverable deps)
P6 (no cross-deliverable deps)
P4 (no cross-deliverable deps)
P1 depends on: nothing (but uses existing kaizen internals)
P3 depends on: nothing (uses existing eatp/kaizen internals)
P2 depends on: P1 (manifest parsing), P3 (validation utilities)
```

**Implementation Order**: P4, P5, P6 can be done in parallel. P1 and P3 can be done in parallel. P2 must wait for P1 and P3.

---

## Risk Assessment

### High Probability, High Impact (Critical)

1. **RISK-01: kailash-mcp package does not exist**
   - Impact: Cannot follow brief's package placement literally
   - Probability: Certain (verified via Glob)
   - Mitigation: ADR-2 resolves this -- use Core SDK's `mcp_server/` package
   - Prevention: Confirm with user before implementation

2. **RISK-02: Pydantic vs dataclass conflict**
   - Impact: Inconsistent codebase if wrong choice made
   - Probability: Certain (brief says Pydantic, rules say dataclass)
   - Mitigation: ADR-1 resolves this -- use dataclass per EATP rules
   - Prevention: Resolved by this analysis

### Medium Probability, High Impact (Monitor)

3. **RISK-03: DataFlow adapter compatibility**
   - Impact: P4 aggregation functions may need different SQL for each backend
   - Probability: Medium (MongoDB `$group` vs SQL GROUP BY are fundamentally different)
   - Mitigation: Abstract via adapter pattern; test with all three backends
   - Prevention: Write adapter-specific query generators from the start

4. **RISK-04: MCP Catalog Server auth integration**
   - Impact: Catalog server without auth is a security gap
   - Probability: Medium (MCPServer auth exists but catalog needs CARE Platform API auth too)
   - Mitigation: Reuse MCPServer's AuthProvider + add CARE Platform API key forwarding
   - Prevention: Design auth flow in P2 before implementation

### Medium Probability, Medium Impact (Monitor)

5. **RISK-05: introspect_agent() import side effects**
   - Impact: Importing user agent modules may trigger unexpected initialization
   - Probability: Medium (agent modules may have module-level side effects)
   - Mitigation: Use `importlib.import_module` with try/except; document that introspection imports the module
   - Prevention: Consider `importlib.util.find_spec` + `importlib.util.module_from_spec` for safer inspection

6. **RISK-06: BudgetTracker Decimal precision across serialization**
   - Impact: Decimal -> JSON -> Decimal may lose precision
   - Probability: Medium (JSON has no Decimal type)
   - Mitigation: Serialize as string in `to_dict()`, parse back from string in `from_dict()`
   - Prevention: Document serialization format explicitly

### Low Probability, Medium Impact (Accept)

7. **RISK-07: PostureEvidence backward compatibility**
   - Impact: Adding types to `eatp.postures.__all__` may surprise existing importers
   - Probability: Low (adding is backward-compatible)
   - Mitigation: New types are additive only

8. **RISK-08: Existing AggregateNode confusion with new query module**
   - Impact: Users may be confused about when to use AggregateNode vs `dataflow.query`
   - Probability: Low (different use cases: in-memory NL vs database queries)
   - Mitigation: Document distinction clearly in module docstrings

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1) -- Parallel

- **P4**: DataFlow aggregation query module (no cross-deps)
- **P5**: PostureEvidence + EvaluationResult + EvidenceBasedGuard (no cross-deps)
- **P6**: BudgetTracker (no cross-deps)

### Phase 2: Core (Weeks 2-3) -- Parallel

- **P1**: Agent Manifest (kaizen.toml parsing, introspection, deploy client)
- **P3**: Composite Agent Validation (DAG, schema compat, cost estimation)

### Phase 3: Integration (Weeks 4-5)

- **P2**: MCP Catalog Server (depends on P1 + P3)

### Phase 4: Polish (Weeks 6-7)

- Integration testing across all six deliverables
- Documentation and examples
- Security review per mandatory review rules

---

## Success Criteria

- [ ] All 66 acceptance criteria pass (11 per deliverable)
- [ ] Performance targets met (measured with benchmarks)
- [ ] Security review completed (no hardcoded secrets, parameterized queries, input validation)
- [ ] No regressions in existing test suites (eatp, kaizen, dataflow)
- [ ] All new types have `to_dict()`/`from_dict()` per EATP conventions
- [ ] All numeric fields validated with `math.isfinite()` per EATP rules
- [ ] All collections bounded per EATP rules
- [ ] Code review completed per agents.md Rule 1
- [ ] Thread safety tested for BudgetTracker (concurrent access tests)
- [ ] Three database backends tested for P4 (SQLite, PostgreSQL, MongoDB)
