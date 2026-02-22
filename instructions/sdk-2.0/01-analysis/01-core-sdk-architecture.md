# Core SDK Architecture Analysis

## 1. Overview

The Kailash Python SDK (v0.11.0) is a workflow automation framework built on a container-node
architecture. It comprises ~233K LOC across 407 Python files in `src/kailash/`. The SDK provides
a DAG-based workflow engine with 110+ built-in node types, sync/async runtimes, multi-channel
deployment, MCP integration, and enterprise features (RBAC, audit, trust).

## 2. Module Structure (`src/kailash/`)

### 2.1 Core Modules

| Module        | Files                | Purpose                                               |
| ------------- | -------------------- | ----------------------------------------------------- |
| `workflow/`   | 25 files             | Workflow graph, builder, validation, cyclic execution |
| `runtime/`    | 22+ files            | Execution engines (sync, async), mixins, validation   |
| `nodes/`      | 142 files (~97K LOC) | Node implementations across 15 categories             |
| `channels/`   | 6 files              | Multi-channel deployment (API, CLI, MCP)              |
| `gateway/`    | 5 files              | API gateway, resource resolution                      |
| `mcp_server/` | 14 files             | MCP protocol server/client implementation             |
| `resources/`  | 5 files              | Resource registry, factory, health checks             |
| `middleware/` | varies               | Auth, CORS, rate limiting middleware                  |
| `edge/`       | 10+ files            | Edge computing, compliance, discovery                 |
| `servers/`    | varies               | Gateway server implementations                        |

### 2.2 Supporting Modules

| Module              | Purpose                         |
| ------------------- | ------------------------------- |
| `access_control/`   | RBAC, ABAC access control       |
| `tracking/`         | Task manager, metrics collector |
| `config/`           | Configuration management        |
| `security.py`       | Security utilities              |
| `sdk_exceptions.py` | Exception hierarchy             |
| `adapters/`         | External service adapters       |
| `integrations/`     | Third-party integrations        |
| `monitoring/`       | Performance monitoring          |
| `visualization/`    | Workflow visualization          |

## 3. Inheritance Hierarchy

### 3.1 Node Hierarchy

```
ABC
 +-- Node (base.py:131, 2457 LOC)
      |   - Abstract base: get_parameters(), run()
      |   - Config management, parameter validation
      |   - Caching (OrderedDict LRU), metadata
      |
      +-- AsyncNode (base_async.py:22, 502 LOC)
      |    |   - Inherits: EventEmitterMixin, SecurityMixin,
      |    |     PerformanceMixin, LoggingMixin, Node
      |    |   - Adds: execute_async(), async lifecycle
      |    |
      |    +-- DataFlow nodes (bulk_create, bulk_update, etc.)
      |    +-- Kaizen AI nodes (llm_agent, embedding_generator)
      |    +-- Transaction nodes (saga_coordinator, 2PC)
      |
      +-- Category-specific nodes (142 files total):
           +-- nodes/ai/ - AI/ML nodes
           +-- nodes/api/ - HTTP, REST nodes
           +-- nodes/auth/ - Authentication nodes
           +-- nodes/code/ - Python, shell execution nodes
           +-- nodes/data/ - SQL, CSV, JSON nodes
           +-- nodes/logic/ - Conditional, switch, loop nodes
           +-- nodes/transform/ - Data transformation nodes
           +-- nodes/security/ - Threat detection, encryption
           +-- nodes/monitoring/ - Metrics, alerting nodes
           +-- nodes/enterprise/ - Governance, compliance
           +-- nodes/transaction/ - Distributed transactions
           +-- nodes/edge/ - Edge computing nodes
           +-- nodes/cache/ - Caching nodes
           +-- nodes/system/ - System utility nodes
           +-- nodes/validation/ - Input validation nodes
```

### 3.2 Runtime Hierarchy

```
ABC
 +-- BaseRuntime (base.py:93, 900 LOC)
      |   - 29 configuration parameters
      |   - Trust integration (CARE-015/016/017)
      |   - Audit generation (CARE-018)
      |   - Resource limits, secret provider
      |   - Persistent mode support
      |
      +-- Mixins (runtime/mixins/):
      |    +-- CycleExecutionMixin - Cyclic workflow delegation
      |    +-- ValidationMixin - 5 validation methods
      |    +-- ConditionalExecutionMixin - Branch skipping, switch nodes
      |    +-- ParameterHandlingMixin - (unused by LocalRuntime)
      |
      +-- LocalRuntime (local.py:~line 100, 4643 LOC)
      |    |   - Inherits: BaseRuntime + all 3 active mixins
      |    |   - Sync execute() + async _execute_async()
      |    |   - WorkflowParameterInjector (not mixin)
      |    |   - Connection validation, error formatting
      |    |   - Enterprise features: security, audit, monitoring
      |    |   - Content-aware success detection
      |    |   - Persistent event loop management
      |    |
      |    +-- AsyncLocalRuntime (async_local.py, 1465 LOC)
      |         - Extends LocalRuntime (not BaseRuntime directly)
      |         - WorkflowAnalyzer: async/sync node classification
      |         - ExecutionPlan: level-based parallelism
      |         - ThreadPoolExecutor for sync nodes
      |         - Semaphore-based concurrency control
      |         - ResourceRegistry integration
```

### 3.3 Workflow Classes

```
WorkflowBuilder (builder.py, 1307 LOC)
  |   - add_node(): 3 patterns (current, legacy, alternative)
  |   - connect(): Node connections with contracts
  |   - build() -> Workflow
  |   - Parameter validation, edge infrastructure
  |
  +-- builds -> Workflow (graph.py:81, 1456 LOC)
       |   - Uses networkx.DiGraph for DAG
       |   - NodeInstance, Connection, CyclicConnection (Pydantic)
       |   - Node instance storage (_node_instances dict)
       |   - Import/export (JSON, YAML)
       |   - Validation, cycle detection
       |
       +-- CyclicWorkflowExecutor (cyclic_runner.py, 1638 LOC)
            - Handles workflows with intentional cycles
            - Convergence checking, iteration limits
            - Cycle state management
```

## 4. Data Flow: Builder to Results

The canonical execution path is:

```
WorkflowBuilder          Workflow              Runtime              Results
+-------------+      +-----------+      +----------------+     +--------+
| add_node()  | ---> | graph     | ---> | execute()      | --> | dict   |
| connect()   | build| (DiGraph) | exec | _execute_async | --> | run_id |
| set_param() | ---> | nodes{}   | ---> | _execute_sync  |     |        |
+-------------+      +-----------+      +----------------+     +--------+
```

### 4.1 Step-by-Step

1. **Builder Phase** (`WorkflowBuilder.add_node`):
   - Pattern detection (string type, class ref, or instance) at `builder.py:200-312`
   - Node stored in `self.nodes` dict with type, config, optional class ref
   - `connect()` creates connection entries in `self.connections` list

2. **Build Phase** (`WorkflowBuilder.build`):
   - Creates `Workflow` object with networkx DiGraph at `graph.py:122`
   - Resolves node types via `NodeRegistry.get()` at `graph.py:218`
   - Creates node instances via `_create_node_instance()` at `graph.py:131-194`
   - Adds edges to DiGraph for connections

3. **Execution Phase** (`LocalRuntime.execute`):
   - Entry at `local.py:681`
   - Checks for running event loop; if none, uses persistent loop at `local.py:794`
   - Calls `_execute_async()` at `local.py:1293`
   - Resource limit enforcement at `local.py:1329-1377`
   - Security check (RBAC) at `local.py:1380-1381`
   - Parameter processing via `_process_workflow_parameters()` at `local.py:1395`
   - Workflow validation at `local.py:1400`
   - Cycle detection: if cycles, delegate to `CycleExecutionMixin` at `local.py:1434`
   - Conditional execution detection at `local.py:1439`

4. **Node Execution Loop** (`_execute_workflow_async`):
   - Topological sort via `nx.topological_sort()` at `local.py:1669`
   - Sequential iteration over execution order at `local.py:1692`
   - Input preparation via `_prepare_node_inputs()` at `local.py:1750`
   - Trust verification per node (CARE-039) at `local.py:1817`
   - Async/sync dispatch: `execute_async()` vs `execute()` at `local.py:1827-1832`
   - Metrics collection via `MetricsCollector` at `local.py:1798`
   - Result storage in `results` and `node_outputs` dicts at `local.py:1838-1839`

5. **Result Collection**:
   - Returns `(results_dict, run_id)` tuple
   - Both LocalRuntime and AsyncLocalRuntime return identical structure

## 5. Execution Model

### 5.1 LocalRuntime: Sequential with Async Support

LocalRuntime executes nodes **sequentially** in topological order. Even though it has async
support (for nodes with `execute_async`), the nodes are awaited one at a time in the main loop.
No parallelism occurs at the node level in LocalRuntime.

The persistent event loop pattern (`_ensure_event_loop()`) maintains a single thread-owned
event loop across multiple `execute()` calls, allowing connection pools to survive across
workflow invocations.

### 5.2 AsyncLocalRuntime: Level-Based Parallelism

AsyncLocalRuntime adds true parallelism through:

1. **WorkflowAnalyzer**: Classifies nodes as async vs sync
2. **ExecutionPlan**: Groups nodes into levels based on dependencies
3. **Level-based execution**: Nodes in the same level run concurrently
4. **Semaphore control**: Limits max concurrent executions
5. **ThreadPoolExecutor**: Runs sync nodes in thread pool without blocking

### 5.3 Cyclic Execution

Workflows with intentional cycles are handled by `CyclicWorkflowExecutor`:

- Detects cycles in the DiGraph
- Executes cycle groups iteratively
- Checks convergence conditions
- Enforces iteration limits and timeouts

## 6. Key Classes and Responsibilities

### 6.1 NodeRegistry (`nodes/base.py`)

Global singleton registry mapping node type names to classes. Populated via `@register_node`
decorator. Used by `Workflow.add_node()` to resolve string type names to classes.

### 6.2 NodeParameter (`nodes/base.py:78`)

Pydantic model defining node input/output schemas. Features auto-mapping (`auto_map_from`,
`auto_map_primary`, `workflow_alias`) for flexible parameter resolution across connections.

### 6.3 ConnectionContract (`workflow/contracts.py`)

Defines type contracts between connected nodes. Validated at build time and optionally at
runtime (connection_validation modes: off, warn, strict).

### 6.4 WorkflowParameterInjector (`runtime/parameter_injector.py`)

Enterprise parameter handling for LocalRuntime. Manages parameter scoping, injection, and
override precedence. Not implemented as a mixin (architectural boundary).

### 6.5 ResourceRegistry (`resources/registry.py`)

Singleton registry for shared resources (database connections, API clients, etc.). Used by
AsyncLocalRuntime for resource lifecycle management across workflows.

### 6.6 TaskManager (`tracking/`)

Tracks workflow and node execution state. Creates runs, tasks, and records metrics.

## 7. External Dependencies

### 7.1 Heavy Dependencies

| Dependency           | Usage                                                 | Rust Replacement Candidate |
| -------------------- | ----------------------------------------------------- | -------------------------- |
| `networkx` (>=2.7)   | DAG data structure, topological sort, cycle detection | YES - core candidate       |
| `pydantic` (>=1.9)   | Data validation, node/connection models               | Partial - FFI structs      |
| `psutil` (>=7.0)     | Resource monitoring (CPU, memory)                     | YES - sysinfo crate        |
| `sqlalchemy` (>=2.0) | Database abstraction (DataFlow)                       | NO - stays in Python       |
| `fastapi` (>=0.115)  | API server (Nexus, Gateway)                           | NO - stays in Python       |
| `mcp[cli]` (>=1.23)  | MCP protocol implementation                           | NO - stays in Python       |

### 7.2 networkx Usage Analysis

networkx is the most critical dependency for SDK 2.0 migration:

- `workflow/graph.py:122` - `nx.DiGraph()` for workflow graph
- `runtime/local.py:1669` - `nx.topological_sort()` for execution order
- `runtime/local.py:46` - Direct nx import in runtime
- `workflow/cycle_analyzer.py` - Cycle detection algorithms
- `runtime/async_local.py:27` - Level computation for parallelism

This is the primary candidate for Rust replacement: a custom DAG data structure with
topological sort, cycle detection, and level computation implemented in Rust.

## 8. Code Complexity Metrics

| Component       | LOC    | Files | Complexity Assessment                     |
| --------------- | ------ | ----- | ----------------------------------------- |
| Node system     | 97,327 | 142   | High - many node types, deep inheritance  |
| Runtime engine  | ~7,000 | 22+   | Very High - execution, validation, mixins |
| Workflow system | ~7,000 | 25    | Medium - DAG ops, serialization           |
| Channels        | ~2,000 | 6     | Low - thin wrappers                       |
| MCP Server      | ~5,000 | 14    | Medium - protocol handling                |
| Gateway         | ~3,000 | 5     | Medium - routing, security                |
| Edge            | ~5,000 | 10+   | Medium - distributed ops                  |
| Resources       | ~1,500 | 5     | Low - registry pattern                    |

## 9. Architecture Patterns

### 9.1 Registry Pattern

Used for NodeRegistry, ResourceRegistry, contract registry. Enables string-based lookup
and late binding.

### 9.2 Builder Pattern

WorkflowBuilder provides fluent API for workflow construction with validation.

### 9.3 Mixin Pattern

Runtime capabilities composed via mixins (CycleExecution, Validation, ConditionalExecution).
Nodes use similar pattern (SecurityMixin, PerformanceMixin, LoggingMixin, EventEmitterMixin).

### 9.4 Strategy Pattern

Execution strategies in AsyncLocalRuntime (pure async, mixed, sync-only).
Conditional execution strategies (route_data, skip_branches).

### 9.5 Observer/Event Pattern

EventEmitterMixin on AsyncNode enables monitoring without coupling.

## 10. Implications for SDK 2.0

### 10.1 What Moves to Rust

- DAG data structure (replace networkx DiGraph) - `workflow/graph.py`
- Topological sort algorithm - `runtime/local.py:1669`
- Cycle detection and analysis - `workflow/cycle_analyzer.py`
- Resource lifecycle management - `resources/registry.py`
- Workflow validation - `workflow/validation.py`
- Trust chain verification - `runtime/trust/`

### 10.2 What Stays in Python

- All 142 node implementation files (domain-specific logic)
- All framework layers (DataFlow, Nexus, Kaizen)
- MCP protocol handling
- Channel implementations
- Enterprise middleware
- User-facing APIs (WorkflowBuilder, runtime constructors)

### 10.3 FFI Boundary

The Rust core will expose a C-compatible FFI boundary. Python will use PyO3 bindings.
Key FFI crossing points:

- Workflow creation and node registration
- Connection establishment
- Execution orchestration (Rust schedules, Python executes nodes via callback)
- Result collection
- Validation queries
