# Task Tracking

Task tracking is the substrate beneath visualization, reporting, and observability. Every node execution in every workflow flows through `TaskManager` → pluggable `StorageBackend`. The reference backends are `SQLiteStorage` (preferred, with WAL + PRAGMAs), `FileSystemStorage` (JSON files, primarily for debugging), and `DeferredStorageBackend` (in-memory with optional post-run flush).

Source of truth: `src/kailash/tracking/`

## Public exports (`src/kailash/tracking/__init__.py`)

```python
from kailash.tracking.manager import TaskManager
from kailash.tracking.metrics_collector import MetricsCollector, PerformanceMetrics
from kailash.tracking.models import TaskStatus

__all__ = ["TaskManager", "TaskStatus", "MetricsCollector", "PerformanceMetrics"]
```

Only four symbols are re-exported at the package level. `TaskRun`, `WorkflowRun`, `TaskMetrics`, `RunSummary`, `TaskSummary`, and the state-transition maps are available via `kailash.tracking.models`. Storage backends are under `kailash.tracking.storage.*`.

## Models (`src/kailash/tracking/models.py`)

### `TaskStatus` (Enum)

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
```

String-valued — `TaskStatus.PENDING == "pending"` holds.

### `VALID_TASK_TRANSITIONS`

Module-level dict declaring the task state machine:

```python
VALID_TASK_TRANSITIONS = {
    TaskStatus.PENDING: {
        TaskStatus.RUNNING,
        TaskStatus.SKIPPED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),   # Terminal
    TaskStatus.FAILED: set(),      # Terminal
    TaskStatus.SKIPPED: set(),     # Terminal
    TaskStatus.CANCELLED: set(),   # Terminal
}
```

- `PENDING` → `{RUNNING, SKIPPED, FAILED, CANCELLED}`
- `RUNNING` → `{COMPLETED, FAILED, CANCELLED}`
- `COMPLETED`, `FAILED`, `SKIPPED`, `CANCELLED` are terminal — no outbound transitions.

`TaskRun.update_status` enforces this state machine at runtime, raising `TaskStateError` on an invalid transition.

### `VALID_RUN_TRANSITIONS`

Module-level dict declaring the workflow-run state machine. Note that workflow runs use plain strings, not the `TaskStatus` enum:

```python
VALID_RUN_TRANSITIONS = {
    "pending":   {"running", "failed"},
    "running":   {"completed", "failed"},
    "completed": set(),  # Terminal
    "failed":    set(),  # Terminal
}
```

- `"pending"` → `{"running", "failed"}`
- `"running"` → `{"completed", "failed"}`
- `"completed"` and `"failed"` are terminal.

`WorkflowRun.update_status` enforces this at runtime, raising `TaskStateError` on an invalid transition. Note that the run state machine is stricter and smaller than the task state machine — runs do not have `skipped`, `cancelled`, or separate creation/running semantics (a run is constructed with `status="running"` by default).

### `TaskMetrics` (pydantic `BaseModel`)

```python
class TaskMetrics(BaseModel):
    """Metrics for task execution."""

    duration: float | None = 0.0
    memory_usage: float | None = 0.0          # Legacy field name
    memory_usage_mb: float | None = 0.0       # New field name
    cpu_usage: float | None = 0.0
    custom_metrics: dict[str, Any] = Field(default_factory=dict)
```

**Fields** (exactly as in source):

- `duration: float | None = 0.0` — execution time in seconds
- `memory_usage: float | None = 0.0` — legacy alias, kept for backward compatibility
- `memory_usage_mb: float | None = 0.0` — new field
- `cpu_usage: float | None = 0.0`
- `custom_metrics: dict[str, Any] = Field(default_factory=dict)`

There are NO `disk_io`, `network_io`, `io_read_bytes`, or `io_write_bytes` fields on `TaskMetrics`. I/O metrics are tracked separately in `PerformanceMetrics` (see the metrics collector section) and flow into `TaskMetrics.custom_metrics` via `PerformanceMetrics.to_task_metrics()`.

All numeric defaults are `0.0`, not `None`. The `| None` annotation exists to permit explicit `None` assignments (e.g., when a metric was not collected) but the default value is `0.0`.

**Constructor behavior:** The custom `__init__` unifies the two memory fields. If only one of `memory_usage` / `memory_usage_mb` is supplied, the other is set to the same value:

```python
def __init__(self, **data):
    if "memory_usage" in data and "memory_usage_mb" not in data:
        data["memory_usage_mb"] = data["memory_usage"]
    elif "memory_usage_mb" in data and "memory_usage" not in data:
        data["memory_usage"] = data["memory_usage_mb"]
    super().__init__(**data)
```

**Validation:** `validate_positive_metrics` is a pydantic field validator on `cpu_usage`, `memory_usage`, `memory_usage_mb`, and `duration`. It raises `ValueError("Metric values must be non-negative")` if any of these are negative (None is allowed — the check is `v is not None and v < 0`).

**Methods:**

- `to_dict() -> dict[str, Any]` — returns `self.model_dump()`.
- `from_dict(cls, data: dict[str, Any]) -> "TaskMetrics"` — returns `cls.model_validate(data)`.

### `TaskRun` (pydantic `BaseModel`)

```python
class TaskRun(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(default="test-run-id", description="Associated run ID")
    node_id: str = Field(..., description="Node ID in the workflow")
    node_type: str = Field(default="default-node-type", description="Type of node")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    completed_at: datetime | None = None         # Alias for ended_at
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    metrics: TaskMetrics | None = None
    dependencies: list[str] = Field(default_factory=list)
    parent_task_id: str | None = None
    retry_count: int = 0
```

**Fields:**

- `task_id: str` — defaults to a new uuid4.
- `run_id: str` — defaults to `"test-run-id"` for backward compatibility with legacy test fixtures (NOT the same as the run's actual id — callers should always supply this explicitly in production).
- `node_id: str` — required.
- `node_type: str` — defaults to `"default-node-type"` for backward compatibility.
- `status: TaskStatus` — defaults to `PENDING`.
- `started_at`, `ended_at`, `completed_at` — datetimes; `completed_at` is an alias field kept in sync with `ended_at` via `model_post_init` and a custom `__setattr__`.
- `created_at: datetime` — default is `datetime.now(UTC)` at field initialization time.
- `result: dict | None` — set by successful completion.
- `error: str | None` — set on failure.
- `metadata: dict = {}`.
- `input_data`, `output_data: dict | None = None`.
- `metrics: TaskMetrics | None = None`.
- `dependencies: list[str] = []`.
- `parent_task_id: str | None = None`.
- `retry_count: int = 0`.

**Validators:**

- `validate_required_string` — ensures `run_id`, `node_id`, `node_type` are non-empty (raises `ValueError(f"{field_name} cannot be empty")`).

**Sync behavior** (`model_post_init` + custom `__setattr__`):

- If `ended_at` is set, `completed_at` is set to the same value.
- If `completed_at` is set, `ended_at` is set to the same value.
- The two fields are kept interchangeable so callers that use either name see a consistent value.

**Lifecycle methods:**

- `start() -> None` — calls `update_status(TaskStatus.RUNNING)` and sets `started_at = datetime.now(UTC)`.
- `complete(output_data: dict | None = None) -> None` — sets `output_data` if provided, calls `update_status(TaskStatus.COMPLETED)`, sets `completed_at`.
- `fail(error_message: str) -> None` — sets `error`, calls `update_status(TaskStatus.FAILED)`, sets `completed_at`.
- `cancel(reason: str) -> None` — sets `error = reason`, calls `update_status(TaskStatus.CANCELLED)`, sets `completed_at`.
- `create_retry() -> "TaskRun"` — returns a new `TaskRun` with `status=PENDING`, incremented `retry_count`, same `node_id`/`node_type`/`run_id`/`input_data`/`dependencies`, and `parent_task_id = self.task_id`. Metadata is copied.

**Method: `update_status(status, result=None, error=None, ended_at=None, metadata=None)`**

```python
def update_status(
    self,
    status: TaskStatus,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    ended_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
```

**Parameters** (exactly as in source):

- `status: TaskStatus` — the new status to transition to. Required.
- `result: dict | None = None` — optional, applied to `self.result` when non-None.
- `error: str | None = None` — optional, applied to `self.error` when non-None.
- `ended_at: datetime | None = None` — optional, applied to `self.ended_at` when non-None. If not supplied AND the new status is one of `{COMPLETED, FAILED, SKIPPED}`, `ended_at` is auto-set to `datetime.now(UTC)`.
- `metadata: dict | None = None` — optional, merged into `self.metadata` via `dict.update` when non-None.

There are NO `output_data` or `metrics` parameters on `update_status`. `output_data` is set via `complete(output_data=...)` or by direct attribute assignment; `metrics` is set via direct assignment or `TaskManager.update_task_metrics()`.

**Behavior:**

1. Looks up `self.status` in `VALID_TASK_TRANSITIONS`. If the current status is not in the map, raises `TaskStateError(f"Unknown task status: {self.status}")`.
2. Looks up the valid outbound transitions. If `status` is not in that set AND `status != self.status`, raises `TaskStateError(f"Invalid state transition from {self.status} to {status}. Valid transitions: ...")`. Self-transitions (e.g. updating a RUNNING task to RUNNING with new metadata) are permitted.
3. Applies the new status.
4. Applies `result`, `error`, `ended_at`, `metadata` as described above.
5. If the new status is `RUNNING` AND `self.started_at is None`, sets `started_at = datetime.now(UTC)`.

**Utilities:**

- `duration` property — if `started_at` and `ended_at` both set, returns seconds elapsed; falls back to `completed_at` for backward compatibility; returns None otherwise.
- `get_duration() -> float | None` — non-property variant that only uses `started_at`/`ended_at`.
- `validate_state() -> None` — validates consistency (e.g. completed/failed tasks must have been started).
- `to_dict() -> dict` — serializes with ISO-formatted datetimes and nested metrics.
- `from_dict(data) -> TaskRun` — reconstructs from a dict.
- `__eq__` / `__hash__` — equality and hashing by `task_id`.

### `Task` (legacy alias)

`Task = TaskRun`. Kept for backward compatibility with older code.

### `WorkflowRun` (pydantic `BaseModel`)

```python
class WorkflowRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_name: str = Field(..., description="Name of the workflow")
    status: str = Field(default="running", description="Run status")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    tasks: list[str] = Field(default_factory=list, description="Task IDs")
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
```

**Validators:**

- `validate_workflow_name` — rejects empty string with `ValueError("Workflow name cannot be empty")`.
- `validate_status` — requires one of `{"pending", "running", "completed", "failed"}`.

**Method: `update_status(status: str, error: str | None = None) -> None`**

Enforces `VALID_RUN_TRANSITIONS`. Raises `TaskStateError` on unknown or invalid transitions. Sets `ended_at` automatically if transitioning to `"completed"` or `"failed"` and `ended_at is None`.

**Method: `add_task(task_id: str) -> None`**

Appends `task_id` to `self.tasks` if not already present. Raises `TaskException("Task ID cannot be empty")` on empty input.

**Utilities:**

- `get_duration() -> float | None`
- `to_dict() -> dict` — serializes with ISO-formatted datetimes.

### `TaskSummary` (pydantic `BaseModel`)

Summary view of a `TaskRun`. Fields: `task_id`, `node_id`, `node_type`, `status`, `duration`, `started_at` (str), `ended_at` (str), `error`.

Classmethod: `from_task_run(task: TaskRun) -> TaskSummary` — safely constructs from a `TaskRun`, raising `TaskException` on failure.

### `RunSummary` (pydantic `BaseModel`)

Summary view of a `WorkflowRun`. Fields: `run_id`, `workflow_name`, `status`, `duration`, `started_at` (str), `ended_at` (str), `task_count`, `completed_tasks`, `failed_tasks`, `error`.

Classmethod: `from_workflow_run(run: WorkflowRun, tasks: list[TaskRun]) -> RunSummary` — computes counts from the task list.

## `TaskManager` (`src/kailash/tracking/manager.py`)

```python
class TaskManager:
    def __init__(self, storage_backend: StorageBackend | None = None):
        try:
            self.storage: Any = storage_backend or SQLiteStorage()
            self.logger = logger
            self._runs: dict[str, WorkflowRun] = {}
            self._tasks: dict[str, TaskRun] = {}
        except Exception as e:
            raise TaskException(f"Failed to initialize task manager: {e}") from e
```

**Constructor parameters** (exactly as in source):

- `storage_backend: StorageBackend | None = None` — optional pluggable backend. Defaults to `SQLiteStorage()` (which defaults to `~/.kailash/tracking/tracking.db`) when None. `self.storage` is typed as `Any` internally so `TaskManager` can dispatch dynamically to backend-specific methods like `query_tasks`, `get_all_tasks`, `query_audit_events`, `upsert_search_attributes`, and `search_runs` via `hasattr` checks.

**State:**

- `self.storage: Any` — the backend
- `self.logger` — module logger
- `self._runs: dict[str, WorkflowRun]` — in-memory cache of runs (NOT `_run_cache`)
- `self._tasks: dict[str, TaskRun]` — in-memory cache of tasks (NOT `_task_cache`)

The cache attribute names are exactly `_runs` and `_tasks`. Any code referencing `_run_cache` or `_task_cache` is wrong.

### Run management

**Method: `create_run(workflow_name: str, metadata: dict | None = None) -> str`**

```python
def create_run(
    self,
    workflow_name: str,
    metadata: dict[str, Any] | None = None,
) -> str:
```

**Parameters** (exactly as in source):

- `workflow_name: str` — required. Raises `TaskException("Workflow name is required")` if empty.
- `metadata: dict | None = None` — optional; defaults to `{}` on the constructed `WorkflowRun`.

There are NO `workflow_id` or `parameters` parameters. `workflow_name` is the only identifying string. Parameters / inputs are stored per-task via `create_task(input_data=...)`, not per-run.

**Behavior:**

1. Validates `workflow_name` is non-empty (raises `TaskException`).
2. Constructs `WorkflowRun(workflow_name=workflow_name, metadata=metadata or {})`.
3. Caches the run in `self._runs[run.run_id]`.
4. Calls `self.storage.save_run(run)`. On storage failure, pops the run from the cache and re-raises as `StorageException`.
5. Returns `run.run_id`.

**Method: `update_run_status(run_id, status, error=None)`**

Loads the run from cache or storage, validates via `WorkflowRun.update_status`, persists, and re-raises state errors as `TaskStateError` with context.

### Task management

**Method: `create_task(node_id, input_data=None, metadata=None, run_id="test-run-id", node_type="default-node-type", dependencies=None, started_at=None)`**

```python
def create_task(
    self,
    node_id: str,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str = "test-run-id",
    node_type: str = "default-node-type",
    dependencies: list[str] | None = None,
    started_at: datetime | None = None,
) -> TaskRun:
```

The `run_id` and `node_type` defaults are legacy backward-compat placeholders for older tests — production code supplies them explicitly. Returns the constructed `TaskRun`. Persists via `self.storage.save_task(task)`; adds the task to its run via `run.add_task(task.task_id)` and re-saves the run if the run is cached.

**Method: `update_task_status(task_id, status, result=None, error=None, ended_at=None, metadata=None)`**

Loads the task (cache or storage), calls `task.update_status(...)`, persists. Signature matches `TaskRun.update_status` exactly.

**Method: `complete_task(task_id, output_data=None)`**

Calls `task.complete(output_data)` and persists. Also attaches a minimal `TaskMetrics(duration=task.duration or 0)` if no metrics had been set.

**Method: `fail_task(task_id, error_message)` / `cancel_task(task_id, reason)` / `retry_task(task_id)`**

Standard lifecycle operations. `retry_task` uses `TaskRun.create_retry()` and persists the new retry task.

**Method: `delete_task(task_id)`**

Removes from cache and calls `self.storage.delete_task(task_id)`.

### Queries and lookups

- `get_run(run_id) -> WorkflowRun | None` — cache-then-storage lookup.
- `get_task(task_id) -> TaskRun | None` — cache-then-storage lookup.
- `list_runs(workflow_name=None, status=None, limit=None) -> list[RunSummary]` — delegates to `self.storage.list_runs(workflow_name, status)`, then builds summaries by fetching tasks per run.
- `list_tasks(run_id, node_id=None, status=None) -> list[TaskSummary]` — raises `TaskException` if `run_id` is empty.
- `get_run_summary(run_id) -> RunSummary | None`
- `get_run_tasks(run_id) -> list[TaskRun]` — returns full `TaskRun` instances for a run, not summaries. Looks up each task id from `run.tasks` via `self.get_task(task_id)`.
- `get_tasks_by_status(status) -> list[TaskRun]` — uses `storage.query_tasks(status=...)` if available, else falls back to scanning `storage.get_all_tasks()`.
- `get_tasks_by_node(node_id) -> list[TaskRun]` — same pattern as above.
- `get_task_history(task_id) -> list[TaskRun]` — follows `parent_task_id` backward to the original task, then walks child tasks forward in order of `retry_count`.
- `get_tasks_by_timerange(start_time, end_time) -> list[TaskRun]` — queries by `created_at` range, handling timezone-aware comparisons.
- `get_task_statistics() -> dict[str, Any]` — returns `{"total_tasks", "by_status", "by_node"}`.
- `cleanup_old_tasks(days=30) -> int` — deletes tasks created more than `days` ago and returns the count.
- `get_running_tasks() -> list[TaskRun]` — `get_tasks_by_status(TaskStatus.RUNNING)`.
- `get_task_dependencies(task_id) -> list[TaskRun]` — returns task instances for each id in `task.dependencies`.
- `get_workflow_tasks(workflow_id) -> list[TaskRun]` — compatibility shim that currently returns all tasks via `storage.get_all_tasks()`.

### Metrics and search

- `update_task_metrics(task_id, metrics: TaskMetrics)` — assigns and persists.
- `save_task(task: TaskRun)` — convenience save. Adds the task id to its run's `run.tasks` list if needed.
- `set_search_attributes(run_id, attributes: dict[str, Any])` — uses `storage.upsert_search_attributes(run_id, attributes)` if supported; logs a warning otherwise.
- `search_runs(filters: dict, order_by: str = "created_at DESC", limit: int = 100, offset: int = 0) -> list[dict]` — uses `storage.search_runs(...)` if supported.
- `get_execution_audit_trail(run_id) -> list[dict]` — combines the workflow run record, all task records (with timing and duration), and audit events from the storage backend (if it supports `query_audit_events`) into a chronological list sorted by timestamp.
- `clear_cache()` — clears `_runs` and `_tasks` dicts.

## Metrics collector (`src/kailash/tracking/metrics_collector.py`)

### `PerformanceMetrics`

```python
@dataclass
class PerformanceMetrics:
    duration: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0          # Peak memory
    memory_delta_mb: float = 0.0    # Memory increase during execution
    io_read_bytes: int = 0
    io_write_bytes: int = 0
    io_read_count: int = 0
    io_write_count: int = 0
    thread_count: int = 1
    context_switches: int = 0
    custom: dict[str, Any] = field(default_factory=dict)
```

**Method: `to_task_metrics() -> dict[str, Any]`**

Converts to a `TaskMetrics`-compatible dict: `duration`, `memory_usage_mb`, `cpu_usage`, plus I/O, threading, and context-switch fields packed into `custom_metrics` alongside whatever was already in `self.custom`.

### `MetricsCollector`

```python
class MetricsCollector:
    def __init__(
        self,
        sampling_interval: float = 0.1,
        enable_resource_monitoring: bool = True,
    ):
```

**Parameters:**

- `sampling_interval: float = 0.1` — seconds between samples in the background monitoring thread.
- `enable_resource_monitoring: bool = True` — toggles psutil-based monitoring. When False, only duration is tracked and no background thread is spawned. When True but psutil is unavailable, emits a `warnings.warn` and falls back to duration-only.

**State:**

- `self.sampling_interval`
- `self._monitoring_enabled` — effective flag: `PSUTIL_AVAILABLE and enable_resource_monitoring`

**Method: `collect(node_id: str | None = None)` — context manager**

Yields a `MetricsContext` that calls `context.start()` on entry and `context.stop()` in `finally`. Usage:

```python
collector = MetricsCollector()
with collector.collect(node_id="my_node") as context:
    ...  # execute node code
metrics = context.result()
```

**Method: `async collect_async(coro, node_id: str | None = None) -> tuple[Any, PerformanceMetrics]`**

Wraps an async coroutine with metrics collection. Returns `(result, metrics)`.

### `MetricsContext`

```python
class MetricsContext:
    def __init__(
        self,
        node_id: str | None,
        sampling_interval: float,
        monitoring_enabled: bool,
    ):
```

Maintains start/stop timestamps, psutil process handle, initial I/O counters, peak memory, CPU samples collected by a background daemon thread. `start()` begins sampling, `stop()` signals the thread to stop. `result()` returns a `PerformanceMetrics` populated from the collected samples.

### `default_collector` and `collect_metrics` decorator

- `default_collector = MetricsCollector()` — module-level convenience instance.
- `collect_metrics(func=None, *, node_id=None)` — decorator. Works as `@collect_metrics` or `@collect_metrics(node_id="...")`. Dispatches to `default_collector.collect_async` for coroutines or `default_collector.collect` for sync functions. Returns `(result, metrics)` from the wrapped function.

## Storage backends (`src/kailash/tracking/storage/`)

### Abstract base: `StorageBackend` (`storage/base.py`)

Declares the abstract contract:

- `save_run(run: WorkflowRun) -> None`
- `load_run(run_id: str) -> WorkflowRun | None`
- `list_runs(workflow_name: str | None = None, status: str | None = None) -> list[WorkflowRun]`
- `save_task(task: TaskRun) -> None`
- `load_task(task_id: str) -> TaskRun | None`
- `list_tasks(run_id, node_id=None, status=None) -> list[TaskRun]`
- `clear() -> None`
- `export_run(run_id: str, output_path: str) -> None`
- `import_run(input_path: str) -> str`

Concrete backends may additionally implement (checked via `hasattr` by `TaskManager`):

- `get_all_tasks()` — returns all tasks regardless of run
- `query_tasks(**filters)` — filtered query
- `delete_task(task_id)` — hard delete
- `query_audit_events(trace_id)` — fetch audit events for a run
- `upsert_search_attributes(run_id, attributes)` — indexable run attributes
- `search_runs(filters, order_by, limit, offset)` — attribute-based search

### `SQLiteStorage` (`storage/database.py`)

```python
class SQLiteStorage(StorageBackend):
    SCHEMA_VERSION = 2

    def __init__(self, db_path: str | None = None):
```

**Constructor parameters:**

- `db_path: str | None = None` — file path or `sqlite://PATH` URL. Defaults to `~/.kailash/tracking/tracking.db` when None. The `sqlite://` prefix is stripped and `~` is expanded. Parent directories are created automatically.

**Connection setup:**

- Opens `sqlite3.connect(db_path, check_same_thread=False)` for cross-thread access.
- Sets `self._lock = threading.Lock()` for explicit serialization on top of `check_same_thread=False`.

**PRAGMAs applied in `_enable_optimizations()`:**

- `PRAGMA journal_mode=WAL` — WAL mode for concurrent reads/writes
- `PRAGMA busy_timeout=5000` — 5 second busy timeout
- `PRAGMA synchronous=NORMAL` — reduced sync overhead vs FULL
- `PRAGMA cache_size=-64000` — 64 MB cache (negative means KB)
- `PRAGMA temp_store=MEMORY` — in-memory temporary tables
- `PRAGMA foreign_keys=ON` — FK constraint enforcement
- `PRAGMA automatic_index=ON` — auto-create indexes where useful

**Schema version management:** A `schema_version` table tracks the applied version. Schema upgrades run in `_initialize_schema()` if the stored version is older than `SCHEMA_VERSION = 2`.

### `FileSystemStorage` (`storage/filesystem.py`)

```python
class FileSystemStorage(StorageBackend):
    def __init__(self, base_path: str | None = None):
```

**Constructor parameters:**

- `base_path: str | None = None` — directory root. Defaults to `~/.kailash/tracking`.

**Layout:**

- `{base_path}/runs/` — one JSON file per run (`{run_id}.json`)
- `{base_path}/tasks/` — one JSON file per task (`{task_id}.json`)
- `{base_path}/metrics/` — metrics JSON files
- `{base_path}/index.json` — auto-initialized index with `{"tasks": {}, "runs": {}}`

Primarily intended for debugging — SQLite is the preferred backend for production.

### `DeferredStorageBackend` (`storage/deferred.py`)

```python
class DeferredStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._tasks: dict[str, TaskRun] = {}
        self._audit_events: list = []
```

**Behavior:** Pure in-memory storage with zero I/O during workflow execution. All reads and writes operate on the in-memory dicts. After execution completes, the backend can optionally `flush_to_filesystem()` to persist final state to disk.

Designed for high-throughput bulk workloads where per-task disk writes would be a bottleneck. Used by `RuntimeAuditGenerator` via the `_audit_events` list to accumulate audit events for later flushing.

## Design Notes

- `TaskMetrics` has `duration`, `memory_usage` (legacy), `memory_usage_mb` (new), `cpu_usage`, and `custom_metrics`. There is no `disk_io` or `network_io` field — I/O metrics live in `PerformanceMetrics.custom` and reach `TaskMetrics` via `PerformanceMetrics.to_task_metrics()`'s `custom_metrics` payload.
- `TaskRun.update_status` does NOT accept `output_data` or `metrics` parameters. Use `TaskRun.complete(output_data=...)` for output and direct attribute assignment (or `TaskManager.update_task_metrics`) for metrics.
- `TaskManager.create_run` does NOT accept `workflow_id` or `parameters`. The only identity is `workflow_name`; per-task inputs are stored via `create_task(input_data=...)`.
- `TaskManager`'s internal caches are `self._runs` and `self._tasks` — there are no `_run_cache` or `_task_cache` attributes.
- `VALID_RUN_TRANSITIONS` is a real module-level constant in `models.py` with four states (`"pending"`, `"running"`, `"completed"`, `"failed"`). Run state transitions are enforced by `WorkflowRun.update_status`. The run state machine is smaller and uses plain strings, not the `TaskStatus` enum.
- `TaskManager` relies on `hasattr` checks for optional backend methods like `query_tasks`, `query_audit_events`, `upsert_search_attributes`, `search_runs`. Backends that do not implement these gracefully degrade to fallback logic that scans `get_all_tasks()`.
- Both `memory_usage` and `memory_usage_mb` are kept in sync by `TaskMetrics.__init__` — setting one sets the other. This is a compatibility shim and both fields report the same value at construction time.
