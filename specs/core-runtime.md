# Kailash Core SDK — Runtime Execution, Cycles, Resilience, Errors

Version: 2.8.5
Status: Authoritative domain truth document
Parent domain: Core SDK (split from `core-sdk.md` per specs-authority Rule 8)
Scope: LocalRuntime, AsyncLocalRuntime, DistributedRuntime, runtime factory, return contract, cycle/loop support, resilience patterns (retry/circuit breaker/DLQ/fallback), error handling, usage patterns, key invariants

Sibling files: `core-nodes.md` (node architecture), `core-workflows.md` (builder + workflow + validation), `core-servers.md` (server variants + gateway)

---

## 4. Runtime Execution

### 4.1 LocalRuntime (Synchronous)

**Module**: `kailash.runtime.local`
**Import**: `from kailash import LocalRuntime`
**Inherits**: `BaseRuntime`, `CycleExecutionMixin`, `ValidationMixin`, `ConditionalExecutionMixin`

The primary runtime for synchronous workflow execution.

#### 4.1.1 Constructor

```python
class LocalRuntime:
    def __init__(
        self,
        debug: bool = False,
        enable_cycles: bool = True,
        enable_async: bool = True,
        max_concurrency: int = 10,
        user_context: Any | None = None,
        enable_monitoring: bool = True,
        enable_security: bool = False,
        enable_audit: bool = False,
        resource_limits: dict[str, Any] | None = None,
        secret_provider: Any | None = None,
        connection_validation: str = "warn",
        conditional_execution: str = "route_data",
        content_aware_success_detection: bool = True,
        persistent_mode: bool = False,
        enable_connection_sharing: bool = True,
        max_concurrent_workflows: int = 10,
        connection_pool_size: int = 20,
        enable_enterprise_monitoring: bool = False,
        enable_health_monitoring: bool = False,
        enable_resource_coordination: bool = True,
        circuit_breaker_config: dict | None = None,
        retry_policy_config: dict | None = None,
        connection_pool_config: dict | None = None,
        trust_context: Any | None = None,
        trust_verifier: Any | None = None,
        trust_verification_mode: str = "disabled",
        audit_generator: Any | None = None,
        audit_log_to_stdout: bool = False,
        enable_resource_limits: bool = False,
    )
```

**Key parameters**:

- `debug` -- Enable debug logging
- `enable_cycles` -- Enable cyclic workflow support
- `enable_async` -- Enable async execution for `AsyncNode` instances
- `max_concurrency` -- Maximum concurrent async operations
- `connection_validation` -- `"off"` (no validation), `"warn"` (log warnings, default), `"strict"` (raise errors)
- `conditional_execution` -- `"route_data"` (all nodes execute, data routing only, default) or `"skip_branches"` (skip unreachable branches)
- `content_aware_success_detection` -- When `True` (default), checks return value content for `{"success": false}` patterns
- `persistent_mode` -- For long-running applications; enables connection pool sharing
- `trust_verification_mode` -- `"disabled"` (default), `"warn"`, `"strict"`

#### 4.1.2 execute

```python
def execute(
    self,
    workflow: Workflow,
    task_manager: TaskManager | None = None,
    parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    cancellation_token: CancellationToken | None = None,
    search_attributes: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], str | None]
```

Execute a workflow synchronously.

**Parameters**:

- `workflow` -- A `Workflow` instance (from `builder.build()`)
- `task_manager` -- Optional `TaskManager` for tracking node execution states
- `parameters` -- Optional parameter overrides. Can be `dict[str, dict[str, Any]]` (per-node: `{"node_id": {"param": value}}`) or `dict[str, Any]` (flat, injected into root nodes)
- `cancellation_token` -- Optional token to request mid-execution cancellation
- `search_attributes` -- Optional typed key-value pairs for indexing/querying workflow runs

**Returns**: `tuple[dict[str, Any], str | None]`

- Element 0: Results dictionary mapping `node_id -> node_output_dict`
- Element 1: Run ID string (e.g., `"run_1712345678000"`) or `None`

**Raises**:

- `RuntimeExecutionError` -- General execution failure
- `WorkflowValidationError` -- If the workflow is structurally invalid
- `WorkflowCancelledError` -- If execution was cancelled via the cancellation token
- `PermissionError` -- If access control denies execution (when `enable_security=True`)
- `WorkflowExecutionError` -- If trust verification denies execution

**Execution lifecycle**:

1. Emits `DeprecationWarning` if not using context manager or explicit `close()`
2. Gets effective trust context (if configured)
3. If an event loop is already running: falls back to synchronous execution (`_execute_sync`)
4. If no event loop: creates/reuses a persistent event loop and runs async execution (`_execute_async`) via `loop.run_until_complete()`
5. After execution: clears credential store for BYOK hardening

**Resource management patterns**:

```python
# Pattern 1 - Context Manager (Recommended)
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())

# Pattern 2 - Explicit Close
runtime = LocalRuntime()
try:
    results, run_id = runtime.execute(workflow.build())
finally:
    runtime.close()
```

**Persistent event loop**: The runtime maintains a persistent event loop across multiple `execute()` calls. This is critical for `AsyncSQLDatabaseNode` and other async components -- connection pools remain valid across executions.

#### 4.1.3 execute_async

```python
async def execute_async(
    self,
    workflow: Workflow,
    task_manager: TaskManager | None = None,
    parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    cancellation_token: CancellationToken | None = None,
    execution_tracker: ExecutionTracker | None = None,
    search_attributes: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]
```

Async variant of `execute()`. Same return type and semantics.

**Additional parameter**:

- `execution_tracker` -- When provided, completed nodes are skipped and their cached outputs are replayed. New completions are recorded for checkpoint capture.

### 4.2 AsyncLocalRuntime

**Module**: `kailash.runtime.async_local`
**Import**: `from kailash.runtime import AsyncLocalRuntime`
**Inherits**: `LocalRuntime`

Async-first runtime extending LocalRuntime with concurrent execution, workflow optimization, and integrated resource management.

#### 4.2.1 execute (override)

```python
def execute(
    self,
    workflow,
    task_manager=None,
    parameters=None,
    cancellation_token=None,
    search_attributes=None,
    **kwargs,
) -> tuple[dict[str, Any], str | None]
```

**Docker-safe override**: Prevents the parent's threading-based execution that causes Docker file descriptor issues. Uses `asyncio.run()` for pure async execution.

**Raises**: `RuntimeError` if called from an async context (directs user to `execute_workflow_async` instead)

#### 4.2.2 execute_workflow_async

```python
async def execute_workflow_async(
    self,
    workflow,
    inputs: dict[str, Any],
    context: ExecutionContext | None = None,
) -> tuple[dict[str, Any], str]
```

Primary async execution method with production safeguards.

**Parameters**:

- `inputs` -- Input data for the workflow (flat dict)
- `context` -- Optional `ExecutionContext` with resource registry

**Returns**: `tuple[dict[str, Any], str]` -- `(results_dict, run_id)`

**Features**:

- Timeout protection (configurable via `execution_timeout`)
- Connection lifecycle management
- Task cancellation on timeout
- Cleanup guarantees via `ExecutionContext`
- Trust verification before execution (if configured)

**Raises**:

- `asyncio.TimeoutError` -- If execution exceeds configured timeout
- `WorkflowExecutionError` -- General execution failure or trust denial

#### 4.2.3 ExecutionContext

```python
class ExecutionContext:
    def __init__(self, resource_registry: ResourceRegistry | None = None)
```

Context passed through async workflow execution providing:

- `variables: dict[str, Any]` -- Shared variables accessible to all nodes
- `metrics: ExecutionMetrics` -- Collected execution metrics
- `connections: dict[str, Any]` -- Managed database connections
- Resource access via `get_resource(name: str)`
- Connection lifecycle management via `acquire_connections()` / `release_connections()`
- Task cancellation via `cancel_all_tasks()`

#### 4.2.4 ExecutionPlan

Workflow analysis result for optimized execution:

- `async_nodes: set[str]` -- Nodes that support async execution
- `sync_nodes: set[str]` -- Nodes requiring synchronous execution
- `execution_levels: list[ExecutionLevel]` -- Nodes grouped by dependency level for concurrent execution
- `is_fully_async: bool` -- Whether all nodes are async
- `can_parallelize: bool` -- Whether multiple nodes can execute concurrently

### 4.3 DistributedRuntime

**Module**: `kailash.runtime.distributed`
**Import**: `from kailash.runtime import DistributedRuntime`
**Inherits**: `BaseRuntime`

Distributed runtime using Redis-backed task queue for horizontal scaling.

#### 4.3.1 Architecture

- **TaskQueue**: Redis-backed queue with reliable delivery (BLMOVE pattern), visibility timeouts (default 300s), and automatic dead-letter handling. Max 3 attempts per task.
- **DistributedRuntime**: Enqueues workflows to the task queue instead of executing locally. `execute()` returns `{"status": "queued", "run_id": run_id}` immediately.
- **Worker**: Dequeue loop with configurable concurrency, heartbeat monitoring, and dead worker detection.

**Configuration**: Set `KAILASH_REDIS_URL` environment variable or pass `redis_url` to constructors.

```python
# Submit
runtime = DistributedRuntime(redis_url="redis://localhost:6379/0")
results, run_id = runtime.execute(workflow)
# results = {"status": "queued", "run_id": "..."}

# Worker
worker = Worker(redis_url="redis://localhost:6379/0", concurrency=4)
await worker.start()  # Blocks, processing tasks
```

### 4.4 get_runtime Factory

**Module**: `kailash.runtime`
**Import**: `from kailash.runtime import get_runtime`

```python
def get_runtime(
    context: str | None = None,
    **kwargs,
) -> AsyncLocalRuntime | LocalRuntime
```

Auto-detects runtime context when `context=None` (default). Checks for a running event loop to decide between async and sync.

- `context="async"` -- Returns `AsyncLocalRuntime(**kwargs)`
- `context="sync"` -- Returns `LocalRuntime(**kwargs)`
- `context=None` -- Auto-detects based on `asyncio.get_running_loop()`

### 4.5 Return Structure Contract

ALL runtime `execute()` methods return `tuple[dict[str, Any], str | None]`:

- **Element 0**: Dictionary mapping `node_id` (string) to that node's output dictionary. Each node's output is the return value of its `run()` method.
- **Element 1**: Run ID string or `None`. Format is typically `f"run_{int(time.time() * 1000)}"`.

This contract is invariant across `LocalRuntime.execute()`, `LocalRuntime.execute_async()`, `AsyncLocalRuntime.execute()`, `AsyncLocalRuntime.execute_async()`, and `AsyncLocalRuntime.execute_workflow_async()`.

---

## 5. Cycle / Loop Support

### 5.1 CycleBuilder (Fluent API)

**Module**: `kailash.workflow.cycle_builder`

Entry point: `workflow.create_cycle(cycle_id: str | None = None)` returns a `CycleBuilder`.

```python
# Full fluent chain
workflow.create_cycle("optimization") \
    .connect("processor", "evaluator", {"result": "input_data"}) \
    .max_iterations(100) \
    .converge_when("quality > 0.95") \
    .timeout(300) \
    .memory_limit(1024) \
    .when("needs_optimization") \
    .nested_in("outer_cycle") \
    .build()
```

#### 5.1.1 Methods

**`connect(source_node, target_node, mapping=None) -> CycleBuilder`**

- Configures which nodes form the cycle back-edge
- Validates both nodes exist in the workflow
- Raises `CycleConnectionError` if nodes not found (includes available nodes list)

**`max_iterations(iterations: int) -> CycleBuilder`**

- Hard safety limit on cycle execution
- Must be positive. Raises `CycleConfigurationError` if not.
- Recommended: 10-100 for quick convergence, 100-1000 for complex optimization

**`converge_when(condition: str) -> CycleBuilder`**

- Python expression evaluated against node outputs each iteration
- When expression evaluates to `True`, cycle terminates early
- Blocks dangerous patterns: `import`, `exec(`, `eval(`, `__`
- Raises `CycleConfigurationError` if condition is empty or contains unsafe patterns
- Examples: `"error < 0.01"`, `"quality > 0.95"`, `"abs(improvement) < 0.001"`

**`timeout(seconds: float) -> CycleBuilder`**

- Time-based safety limit in seconds. Must be positive.
- Recommended: 30-3600 seconds

**`memory_limit(mb: int) -> CycleBuilder`**

- Memory usage limit in megabytes. Must be positive.
- Recommended: 100-10000 MB

**`when(condition: str) -> CycleBuilder`**

- Conditional cycle execution -- cycle only runs when condition is met
- Evaluated before each iteration

**`nested_in(parent_cycle_id: str) -> CycleBuilder`**

- Makes this cycle nested within another cycle for hierarchical optimization

**`build() -> None`**

- Validates configuration and creates the cyclic connection in the workflow
- Requires: source and target nodes configured (via `connect()`)
- Requires: at least one termination condition (`max_iterations`, `converge_when`, or `timeout`)
- Raises `CycleConfigurationError` if incomplete

### 5.2 Convergence Conditions

**Module**: `kailash.workflow.convergence`

#### 5.2.1 ConvergenceCondition (ABC)

```python
class ConvergenceCondition(ABC):
    @abstractmethod
    def evaluate(self, results: dict[str, Any], cycle_state: CycleState) -> bool:
        """Return True if cycle should TERMINATE, False to continue."""
```

#### 5.2.2 ExpressionCondition

Evaluates a Python expression string against a context containing:

- `results` -- Current iteration results dict
- `iteration` -- Current iteration number
- `history` -- List of previous iteration results
- `elapsed_time` -- Time since cycle start
- All node result values at top level (if identifier-safe)
- Scalar values extracted from nested result dicts
- Safe builtins: `abs`, `min`, `max`, `sum`, `len`, `all`, `any`

**On evaluation error**: Terminates cycle for safety (returns `True`).

#### 5.2.3 CallbackCondition

Wraps a `Callable[[dict, CycleState], bool]` for complex convergence logic.

#### 5.2.4 MaxIterationsCondition

Simple counter: terminates when `cycle_state.iteration >= max_iterations`.

### 5.3 Cyclic Execution

The `CyclicWorkflowExecutor` handles actual cycle execution:

1. Separates DAG edges from cycle edges
2. Executes DAG portion in topological order
3. For each cycle group: iterates the cycle nodes, checking convergence/max_iterations/timeout after each iteration
4. Multi-node cycles (A -> B -> C -> A where only C -> A is marked cyclic) are detected via strongly connected component analysis

---

## 6. Resilience Patterns

### 6.1 WorkflowResilience

**Module**: `kailash.workflow.resilience`

Mixin class adding resilience features to workflows.

#### 6.1.1 RetryPolicy

```python
@dataclass
class RetryPolicy:
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0        # seconds
    max_delay: float = 60.0        # seconds
    retry_on: list[type] = [Exception]
```

**RetryStrategy enum**: `IMMEDIATE` (0 delay), `LINEAR` (base _ attempt), `EXPONENTIAL` (base _ 2^(attempt-1)), `FIBONACCI` (base \* fib(attempt))

**`calculate_delay(attempt: int) -> float`**: Returns delay capped at `max_delay`.

#### 6.1.2 configure_retry

```python
def configure_retry(
    self,
    node_id: str,
    max_retries: int = 3,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_on: list[type] | None = None,
)
```

Configures retry policy for a specific node.

#### 6.1.3 CircuitBreakerConfig

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5       # Failures before opening
    success_threshold: int = 2       # Successes needed to close
    timeout: float = 60.0            # Seconds before half-open attempt
```

**States**: `closed` (normal), `open` (failing, requests blocked), `half-open` (testing recovery)

**State transitions**:

- `closed -> open`: When `failures >= failure_threshold`
- `open -> half-open`: When `timeout` seconds have elapsed since last failure
- `half-open -> closed`: When `successes >= success_threshold`
- `half-open -> open`: On any failure

#### 6.1.4 configure_circuit_breaker

```python
def configure_circuit_breaker(
    self,
    node_id: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: float = 60.0,
)
```

#### 6.1.5 Fallback Nodes

```python
def add_fallback(self, primary_node_id: str, fallback_node_id: str)
```

When the primary node fails (after retry exhaustion), the runtime attempts execution on the fallback node(s) in order.

#### 6.1.6 Dead Letter Queue (DLQ)

**Module**: `kailash.workflow.dlq`

`PersistentDLQ` -- SQLite-backed dead letter queue with crash-safe storage.

**Configuration**:

- Path: `KAILASH_DLQ_PATH` env var, or system temp directory, or explicit `dlq_path` parameter
- Bounded capacity: `MAX_DLQ_ITEMS = 10,000` (oldest evicted on overflow)
- Exponential backoff for retries: `DEFAULT_BASE_DELAY = 60.0` seconds, jitter factor 0.25
- Max 3 retries per item by default
- File permissions: `0o600` on POSIX
- Thread-safe via `threading.Lock`

**DLQItem statuses**: `pending`, `retrying`, `succeeded`, `permanent_failure`

**Access**:

- `get_dead_letter_queue() -> list[dict]` -- Get all failed executions
- `clear_dead_letter_queue()` -- Clear after manual processing
- `get_resilience_metrics() -> dict` -- Node metrics, circuit breaker states, DLQ stats, retry policies

#### 6.1.7 Exception Allowlist for Retry Config

The runtime uses a safe exception allowlist (not `eval()`) to resolve exception class names in retry configurations. Supported: `ValueError`, `TypeError`, `KeyError`, `IndexError`, `AttributeError`, `RuntimeError`, `IOError`, `OSError`, `TimeoutError`, `ConnectionError`, `FileNotFoundError`, `PermissionError`, `NotImplementedError`, `StopIteration`, `ArithmeticError`, `OverflowError`, `ZeroDivisionError`, `LookupError`, `UnicodeError`, `ConnectionResetError`, `ConnectionRefusedError`, `BrokenPipeError`.

---

## 7. Error Handling

### 7.1 Exception Hierarchy

All SDK exceptions inherit from `KailashException(Exception)`.

```
KailashException
 +-- NodeException
 |    +-- NodeValidationError      # Input/output validation failure
 |    +-- NodeExecutionError       # Node run() failure
 |    +-- NodeConfigurationError   # Invalid node configuration
 |    +-- SafetyViolationError     # Safety constraint violation
 |    +-- CodeExecutionError       # PythonCodeNode execution failure
 |
 +-- WorkflowException
 |    +-- WorkflowValidationError  # Structural validation failure
 |    +-- WorkflowExecutionError   # Workflow-level execution failure
 |    |    +-- WorkflowCancelledError  # Execution cancelled via token
 |    +-- CyclicDependencyError    # Unintended cycle detected
 |    +-- ConnectionError          # Invalid connection (NOT builtin)
 |    +-- CycleConfigurationError  # Invalid cycle parameters
 |    +-- KailashWorkflowException # Legacy alias
 |
 +-- RuntimeException
 |    +-- RuntimeExecutionError    # Runtime-level execution failure
 |    +-- ResourceLimitExceededError # Memory/CPU/connection limit hit
 |    +-- CircuitBreakerOpenError  # Circuit breaker is open
 |    +-- RetryExhaustedException  # All retries exhausted
 |
 +-- TaskException
 |    +-- TaskStateError           # Invalid task state transition
 |
 +-- StorageException
 |    +-- KailashStorageError      # Storage operation failure
 |
 +-- ExportException               # Workflow export failure
 +-- ImportException               # Workflow import failure
 +-- ConfigurationException
 |    +-- KailashConfigError       # Configuration error
 +-- ManifestError                 # Manifest validation error
 +-- CLIException                  # CLI operation error
 +-- VisualizationError            # Visualization generation error
 +-- TemplateError                 # Template processing error
 +-- KailashNotFoundException      # Resource not found
```

### 7.2 What Callers Should Catch

**Basic workflow execution**:

```python
try:
    results, run_id = runtime.execute(workflow.build())
except WorkflowValidationError:
    # Structural issue: missing connections, invalid parameters, build failure
except RuntimeExecutionError:
    # Execution failed: node error, resource exhaustion, timeout
except WorkflowCancelledError:
    # Execution was cancelled via CancellationToken
```

**With enterprise features**:

```python
except ResourceLimitExceededError:
    # Memory, CPU, or connection limit exceeded
except CircuitBreakerOpenError:
    # Circuit breaker tripped on a node
except RetryExhaustedException:
    # All retry attempts failed
except PermissionError:
    # Access control denied execution
```

### 7.3 Content-Aware Success Detection

When `content_aware_success_detection=True` (default), the runtime inspects node return values:

- If result is a dict with `"success": False`, the runtime treats this as a failure
- Error details extracted from `result.get("error", "Operation failed")`
- `ContentAwareExecutionError` is raised with `node_id` and `failure_data` attached
- Non-dict results, empty dicts, and dicts without `"success"` key default to success

---

## 12. Usage Patterns

### 12.1 Canonical Workflow Execution

```python
from kailash import WorkflowBuilder, LocalRuntime

# Build
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {"url": "https://api.example.com/data"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_connection("fetch", "data", "process", "data")

# Execute
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())
```

### 12.2 Async Execution (Docker/FastAPI)

```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={"key": "value"},
)
```

### 12.3 Cyclic Workflow

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "optimize", {"code": "..."})
workflow.add_node("PythonCodeNode", "evaluate", {"code": "..."})
workflow.add_connection("optimize", "result", "evaluate", "data")

# Build the workflow first, then add cycle
built = workflow.build()
built.create_cycle("quality_loop") \
    .connect("evaluate", "optimize", {"feedback": "input"}) \
    .max_iterations(50) \
    .converge_when("quality > 0.95") \
    .timeout(300) \
    .build()

with LocalRuntime(enable_cycles=True) as runtime:
    results, run_id = runtime.execute(built)
```

---

## 13. Key Invariants

1. **Return structure**: Every runtime `execute` variant returns `tuple[dict[str, Any], str | None]`. No exceptions.
2. **build() before execute()**: A `Workflow` (from `builder.build()`) is the only valid input to runtime execution methods. Passing a `WorkflowBuilder` is a usage error.
3. **Node IDs are strings**: Node IDs MUST be string literals, not variables or f-strings. Dynamic IDs break workflow graph analysis, checkpoint recovery, and debugging.
4. **4-parameter add_node order**: `add_node("NodeType", "node_id", {"param": value})` is the preferred pattern.
5. **Nodes are stateless**: All configuration is provided at initialization. Runtime inputs come via `run()` kwargs. No mutable state between executions.
6. **Sensitive key redaction**: `NodeInstance.model_dump()` redacts `api_key`, `api_secret`, `base_url`, `token`, `password`, `credential`, `auth`, `secret`.
7. **Cycle safety**: Every cycle must have at least one termination condition. The CycleBuilder API enforces this at `build()` time.
8. **Convergence fail-safe**: When convergence expression evaluation fails, the cycle terminates (returns `True`) for safety.
9. **DLQ bounded capacity**: The persistent dead letter queue is capped at 10,000 items. Oldest items are evicted on overflow.
10. **Resource cleanup**: `LocalRuntime` uses a persistent event loop; callers MUST use context manager or explicit `close()` to release resources.
