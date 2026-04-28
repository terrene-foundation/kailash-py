# Framework Implementation Guide -- Tool Agent Support

> Framework-advisor analysis for the Tool Agent Support workspace.
> Covers all six deliverables (P1-P6), implementation order, cross-package dependency map, and risk register.

---

## Table of Contents

1. [P1: Agent Manifest](#p1-agent-manifest)
2. [P2: MCP Catalog Server](#p2-mcp-catalog-server)
3. [P3: Composite Validation](#p3-composite-validation)
4. [P4: DataFlow Aggregation](#p4-dataflow-aggregation)
5. [P5: EATP Posture State Machine](#p5-eatp-posture-state-machine)
6. [P6: Budget Tracking](#p6-budget-tracking)
7. [Implementation Order](#implementation-order)
8. [Cross-Package Dependency Map](#cross-package-dependency-map)
9. [Risk Register](#risk-register)

---

## P1: Agent Manifest

**Package**: kailash-kaizen

### Module Layout

```
packages/kailash-kaizen/src/kaizen/manifest/
    __init__.py
    agent.py         # AgentManifest dataclass, TOML/YAML parsing
    app.py           # ApplicationManifest (multi-agent composition)
    governance.py    # GovernancePolicy, constraints, posture requirements
    loader.py        # load_manifest(path) -> AgentManifest | ApplicationManifest
    errors.py        # ManifestError hierarchy (inherits from KaizenError)

packages/kailash-kaizen/src/kaizen/deploy/
    __init__.py
    introspect.py    # Introspect live agent -> AgentManifest (capabilities, schemas)
    client.py        # DeployClient: push manifest to CARE Platform API (local-first)
```

### Build On Existing Code

- **`kaizen/core/config.py`**: `KaizenConfig.from_file` already parses TOML via `tomllib`/`tomli`. Reuse this pattern for manifest loading.
- **`kaizen/core/type_introspector.py`**: Extracts JSON Schema from Python type annotations. Use for auto-generating input/output schemas from agent signatures.
- **`kaizen/agents/registry.py`**: `AgentRegistry` provides the backing store for agent metadata. Manifests register into this registry.

### Design Decisions

- **@dataclass (NOT Pydantic)** per ADR-1 from requirements analysis. Rationale: 263 dataclass vs 3 Pydantic usages in kaizen, EATP rules mandate @dataclass, and Pydantic carries a 1.8s import penalty.
- **HTTP client**: stdlib `urllib.request` for deploy client. No new dependencies.
- **TOML parsing**: `tomllib` (Python 3.11+) with `tomli` fallback (same pattern as `KaizenConfig.from_file`).

### Data Model

```python
@dataclass
class AgentManifest:
    name: str
    version: str
    description: str
    capabilities: list[str]
    input_schema: dict[str, Any]    # JSON Schema
    output_schema: dict[str, Any]   # JSON Schema
    governance: GovernancePolicy
    dependencies: list[str]         # Other agent names
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentManifest: ...
    @classmethod
    def from_file(cls, path: Path) -> AgentManifest: ...
```

### Testing Strategy

| Tier   | Scope                                                          | Infrastructure       |
| ------ | -------------------------------------------------------------- | -------------------- |
| Tier 1 | TOML/YAML parsing, schema validation, round-trip serialization | None                 |
| Tier 2 | Introspection against real agent classes                       | Real agent instances |
| Tier 3 | Deploy flow against local HTTP server                          | Local HTTP endpoint  |

---

## P2: MCP Catalog Server

**Package**: kailash-kaizen

### Module Layout

```
packages/kailash-kaizen/src/kaizen/mcp/catalog_server/
    __init__.py
    server.py                     # CatalogMCPServer (extends JSON-RPC pattern)
    tools/
        __init__.py
        discovery.py              # catalog_search, catalog_describe, catalog_schema, catalog_deps
        deployment.py             # deploy_agent, deploy_status
        application.py            # app_register, app_status
    resources/
        __init__.py
        agent_resources.py        # MCP resource endpoints for agent manifests
```

### Build On Existing Code

- **`eatp/mcp/server.py`**: JSON-RPC pattern (request/response envelope, tool registration, stdio transport). This is the protocol foundation.
- **`kaizen/mcp/builtin_server/server.py`**: `KaizenMCPServer` provides the kaizen-specific MCP server base. Extend this for catalog.
- **`kaizen/agents/registry.py`**: Backing store for agent metadata. Catalog queries resolve against this registry.

### Tool Inventory (8 tools, initial scope)

| Tool               | Category    | Description                               |
| ------------------ | ----------- | ----------------------------------------- |
| `catalog_search`   | Discovery   | Search agents by capability, name, or tag |
| `catalog_describe` | Discovery   | Full manifest for a specific agent        |
| `catalog_schema`   | Discovery   | Input/output JSON Schema for an agent     |
| `catalog_deps`     | Discovery   | Dependency graph for an agent             |
| `deploy_agent`     | Deployment  | Deploy agent from manifest                |
| `deploy_status`    | Deployment  | Check deployment status                   |
| `app_register`     | Application | Register multi-agent application          |
| `app_status`       | Application | Check application health                  |

> COC analysis identified potential scope of 18-22 SDK-layer tools. Start with 8 (P1 subset). Expansion is additive and can happen in later iterations.

### Testing Strategy

| Tier   | Scope                                                      | Infrastructure      |
| ------ | ---------------------------------------------------------- | ------------------- |
| Tier 1 | Tool handler functions (input validation, response format) | None                |
| Tier 2 | Full MCP server over stdio transport                       | MCP stdio transport |
| Tier 3 | Protocol compliance (JSON-RPC spec, error codes)           | Real MCP client     |

---

## P3: Composite Validation

**Package**: kailash-kaizen

### Module Layout

```
packages/kailash-kaizen/src/kaizen/composition/
    __init__.py
    dag_validator.py       # DAG cycle detection, connectivity, reachability
    schema_compat.py       # JSON Schema compatibility checking (input/output matching)
    cost_estimator.py      # Composite cost estimation from individual agent costs
    models.py              # ValidationResult, CompatibilityResult, CostEstimate
```

### Build On Existing Code

- **`kaizen/orchestration/core/patterns.py`**: Defines how agents are composed (sequential, parallel, supervisor-worker). Provides the agent format and composition topology.
- **`kaizen/core/type_introspector.py`**: JSON Schema extraction from type annotations. Used for schema compatibility checking.
- **`eatp/graph_validator.py`**: DFS-based cycle detection. Reference implementation for DAG validation algorithms.

### Data Model

```python
@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    dag_depth: int
    node_count: int

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationResult: ...

@dataclass
class CompatibilityResult:
    compatible: bool
    mismatches: list[SchemaMismatch]
    suggestions: list[str]

@dataclass
class CostEstimate:
    total_estimated_cost: Decimal
    per_agent_costs: dict[str, Decimal]
    confidence: float  # 0.0-1.0
```

### Testing Strategy

| Tier   | Scope                                        | Infrastructure     |
| ------ | -------------------------------------------- | ------------------ |
| Tier 1 | DAG algorithms, schema comparison, cost math | None               |
| Tier 2 | Real agent introspection + validation        | Real agent classes |

---

## P4: DataFlow Aggregation

**Package**: kailash-dataflow

### Module Layout

```
packages/kailash-dataflow/src/dataflow/query/
    __init__.py
    aggregation.py      # count_by, sum_by, aggregate (async functions)
    sql_builder.py      # SQL GROUP BY generation (database push-down)
    mongo_builder.py    # MongoDB aggregation pipeline generation
    models.py           # AggregationSpec, AggregationResult
```

### Build On Existing Code

- **`dataflow/nodes/aggregate_operations.py`**: `AggregateNode` exists and handles in-memory aggregation (~95% of the feature). This is Python-side aggregation on fetched data.
- **`dataflow/core/engine.py`**: DataFlow adapters (SQLite, PostgreSQL, MongoDB). The new query module generates SQL GROUP BY for database-level push-down, which is fundamentally different from the existing in-memory `AggregateNode`.

### Key Architectural Decision

The existing `AggregateNode` performs in-memory aggregation after fetching rows. The new query module generates SQL `GROUP BY` clauses for **database push-down** -- the aggregation happens in the database engine, not in Python. These coexist:

- `AggregateNode`: Use when data is already in-memory or when applying complex Python transforms.
- `query.aggregation`: Use when querying databases directly and want the database to do the heavy lifting.

### API Surface

```python
async def count_by(
    engine: DataFlowEngine,
    model: str,
    group_by: list[str],
    filters: dict[str, Any] | None = None,
) -> AggregationResult: ...

async def sum_by(
    engine: DataFlowEngine,
    model: str,
    field: str,
    group_by: list[str],
    filters: dict[str, Any] | None = None,
) -> AggregationResult: ...

async def aggregate(
    engine: DataFlowEngine,
    model: str,
    spec: AggregationSpec,
) -> AggregationResult: ...
```

### Testing Strategy

| Tier   | Scope                                            | Infrastructure               |
| ------ | ------------------------------------------------ | ---------------------------- |
| Tier 1 | SQL generation (string output), model validation | None                         |
| Tier 2 | Real SQLite database queries                     | SQLite (in-memory)           |
| Tier 3 | Full DataFlow lifecycle (engine + adapters)      | SQLite + optional PostgreSQL |

---

## P5: EATP Posture State Machine

**Package**: eatp

### Existing Code (90% complete)

`packages/eatp/src/eatp/postures.py` already contains:

- `PostureStateMachine` -- state machine with configurable transitions
- `TransitionGuard` -- guard conditions on transitions
- `PostureTransitionRequest` -- request to transition between postures
- `TransitionResult` -- result of a transition attempt
- `PostureAwareAgent` -- agent that tracks its posture

### What to Add

**Extend**: `packages/eatp/src/eatp/postures.py`

```python
@dataclass
class PostureEvidence:
    observation_count: int
    success_rate: float          # 0.0-1.0, math.isfinite validated
    time_at_current_posture_hours: float  # math.isfinite validated
    anomaly_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not math.isfinite(self.success_rate):
            raise ValueError("success_rate must be finite")
        if not math.isfinite(self.time_at_current_posture_hours):
            raise ValueError("time_at_current_posture_hours must be finite")

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostureEvidence: ...

@dataclass
class EvaluationResult:
    decision: str               # "promote", "demote", "hold"
    rationale: str
    suggested_posture: str | None
    confidence: float           # 0.0-1.0, math.isfinite validated
    evidence: PostureEvidence

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationResult: ...
```

**New file**: `packages/eatp/src/eatp/posture_store.py`

```python
class PostureStore(Protocol):
    """Protocol for posture persistence."""
    async def save_evaluation(self, agent_id: str, result: EvaluationResult) -> None: ...
    async def get_history(self, agent_id: str, limit: int = 100) -> list[EvaluationResult]: ...
    async def get_current_posture(self, agent_id: str) -> str | None: ...

class SQLitePostureStore:
    """SQLite-backed posture store."""
    # Parameterized SQL, validate_id on agent_id, 0o600 file permissions
    ...
```

### EATP Convention Compliance

- All types are `@dataclass` with `to_dict()` / `from_dict()`
- `math.isfinite()` on all float fields (`success_rate`, `time_at_current_posture_hours`, `confidence`)
- Bounded collections: evaluation history capped at `maxlen=10000`
- Parameterized SQL (`?` placeholders) in SQLitePostureStore
- `validate_id()` on all externally-sourced agent IDs
- SQLite file permissions `0o600` on POSIX

### Testing Strategy

| Tier   | Scope                                                                       | Infrastructure     |
| ------ | --------------------------------------------------------------------------- | ------------------ |
| Tier 1 | Evidence/EvaluationResult serialization, `math.isfinite` guards, validation | None               |
| Tier 2 | SQLite persistence (PostureStore read/write/history)                        | SQLite (in-memory) |
| Tier 3 | Full lifecycle (agent + state machine + store + evaluation)                 | SQLite             |

---

## P6: Budget Tracking

**Package**: kailash-kaizen

### Module Layout

```
packages/kailash-kaizen/src/kaizen/core/autonomy/budget/
    __init__.py
    tracker.py        # BudgetTracker class
    models.py         # BudgetCheckResult, BudgetTransaction
```

### Build On Existing Code

- **`kaizen/core/autonomy/permissions/budget_enforcer.py`**: Existing budget enforcement logic. Checks whether an action is within budget.
- **`kaizen/core/autonomy/hooks/builtin/cost_tracking_hook.py`**: Existing cost tracking hook. Records actual costs per action.

> **Value audit finding**: There are already two budget-related implementations. The brief asks for a `BudgetTracker` class. Recommendation: build `BudgetTracker` as the canonical, consolidated implementation. It should be the single source of truth, with `budget_enforcer` and `cost_tracking_hook` delegating to it rather than maintaining their own state.

### API Surface

```python
class BudgetTracker:
    """Thread-safe budget tracker with Decimal precision."""

    def __init__(self, total_budget: Decimal, *, max_log_entries: int = 10000):
        self._total = total_budget
        self._spent = Decimal("0")
        self._reserved = Decimal("0")
        self._lock = threading.Lock()
        self._transactions: deque[BudgetTransaction] = deque(maxlen=max_log_entries)

    def reserve(self, amount: Decimal) -> bool:
        """Reserve budget for a planned action. Returns False if insufficient."""
        ...

    def record(self, actual: Decimal, *, reservation_id: str | None = None) -> None:
        """Record actual spend. Releases reservation if provided."""
        ...

    def remaining(self) -> Decimal:
        """Available budget (total - spent - reserved)."""
        ...

    def check(self, estimated: Decimal) -> BudgetCheckResult:
        """Check if estimated cost fits within remaining budget."""
        ...
```

### Design Constraints

- **Decimal precision**: All monetary amounts use `Decimal`, never `float`.
- **Thread safety**: `threading.Lock` on all state mutations.
- **Bounded transaction log**: `deque(maxlen=10000)` per trust-plane security rules.
- **`math.isfinite`**: Not applicable (using `Decimal`, not `float`). However, validate that `Decimal` values are finite (not `Decimal('Infinity')` or `Decimal('NaN')`).

### Testing Strategy

| Tier   | Scope                                                                           | Infrastructure      |
| ------ | ------------------------------------------------------------------------------- | ------------------- |
| Tier 1 | Decimal precision, thread safety (10 concurrent threads), reservation lifecycle | None                |
| Tier 2 | Integration with `cost_tracking_hook` and `budget_enforcer`                     | Real hook instances |

---

## Implementation Order

### Wave 1 -- Week 1 (parallel, no cross-dependencies)

| Deliverable | Package          | Rationale                                                    |
| ----------- | ---------------- | ------------------------------------------------------------ |
| **P5**      | eatp             | 90% exists, smallest delta, standalone package               |
| **P4**      | kailash-dataflow | Standalone package, well-understood pattern (SQL generation) |
| **P6**      | kailash-kaizen   | Small scope, consolidation of existing code                  |

All three are independent: different packages, no shared new interfaces.

### Wave 2 -- Week 2 (parallel, foundation for P2)

| Deliverable | Package        | Rationale                                                           |
| ----------- | -------------- | ------------------------------------------------------------------- |
| **P1**      | kailash-kaizen | Foundation for P2 (manifests are the data model for catalog)        |
| **P3**      | kailash-kaizen | Provides validation for P2 (catalog needs to validate compositions) |

P1 and P3 are independent of each other but both feed into P2.

### Wave 3 -- Weeks 3-4 (depends on P1 + P3)

| Deliverable | Package        | Rationale                                                |
| ----------- | -------------- | -------------------------------------------------------- |
| **P2**      | kailash-kaizen | Largest scope, depends on P1 manifests and P3 validation |

P2 consumes P1 manifests as its data model and P3 validation for composition checks. Building it last ensures stable foundations.

### Dependency Graph

```
P5 (EATP posture) ─────────────────────────────────┐
P4 (DataFlow aggregation) ──────────────────────────┤
P6 (Budget tracking) ──────────────────────────────┤
                                                     │
P1 (Agent manifest) ──────┐                          │
P3 (Composite validation) ─┤                         │
                            ▼                        │
                     P2 (MCP catalog) ◄──────────────┘
                     (depends on P1, P3)
```

---

## Cross-Package Dependency Map

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│     eatp     │     │  kailash (core)  │     │ kailash-dataflow │
│              │     │                  │     │                  │
│  P5: posture │     │  (no changes)    │◄────│  P4: aggregation │
│  store/eval  │     │                  │     │                  │
└──────┬───────┘     └────────┬─────────┘     └──────────────────┘
       │                      │
       │ depends on           │ depends on
       ▼                      ▼
┌──────────────────────────────────────┐
│          kailash-kaizen              │
│                                      │
│  P1: manifest/  P3: composition/     │
│  P2: mcp/catalog_server/             │
│  P6: core/autonomy/budget/           │
└──────────────────────────────────────┘
```

**No new cross-package edges are introduced.** All existing dependency directions are preserved:

- `eatp`: standalone (P5 extends within the package)
- `kailash-dataflow` depends on `kailash` core (P4 adds within the package)
- `kailash-kaizen` depends on `kailash` core and `eatp` (P1, P2, P3, P6 all within kaizen)

---

## Risk Register

| #   | Risk                                                                                                | Severity | Mitigation                                                                                                                                                              | Status    |
| --- | --------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| R1  | **@dataclass vs Pydantic conflict** -- Some contributors may default to Pydantic for validation     | Medium   | Resolved per ADR-1: use @dataclass. 263 dataclass vs 3 Pydantic in kaizen, EATP rules mandate @dataclass, 1.8s Pydantic import penalty. Validation via `__post_init__`. | Resolved  |
| R2  | **MCP catalog scope creep** -- COC journal identified 40+ potential tools, brief specifies 8        | High     | Start with 8 tools (P1 subset). Architecture supports additive expansion. Review after Wave 3 delivery.                                                                 | Mitigated |
| R3  | **Budget fragmentation** -- `BudgetTracker` would be the 3rd budget implementation                  | Medium   | Build `BudgetTracker` as canonical consolidation point. `budget_enforcer` and `cost_tracking_hook` delegate to it. Document migration path.                             | Mitigated |
| R4  | **CARE Platform API dependency** -- P1 deploy and P2 catalog need remote API for full functionality | High     | Build local-first: all features work without remote API. Deploy client uses `urllib.request` with graceful fallback. Remote API is optional enhancement.                | Mitigated |
| R5  | **AggregateNode confusion** -- Existing in-memory `AggregateNode` vs new SQL push-down query module | Low      | Clear documentation: `AggregateNode` = in-memory post-fetch, `query.aggregation` = database push-down. Different use cases, coexist without conflict.                   | Mitigated |

---

## Summary

Six deliverables across three packages, delivered in three waves over 3-4 weeks. No new cross-package dependencies. Largest risks (scope creep, budget fragmentation, remote API dependency) are mitigated by local-first design and clear scope boundaries. All implementations use `@dataclass` per ADR-1 and follow existing SDK conventions.
