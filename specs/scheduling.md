# Scheduling Specification

Version: 2.9.0
Package: `kailash`
Status: Authoritative domain truth document
Scope: WorkflowScheduler, cron/interval/one-shot scheduling, APScheduler integration, SQLite job persistence, runtime integration, queue dispatch

This specification covers every public contract, parameter, return type, edge case, and constraint for the Kailash scheduling subsystem. It is the single source of truth for how workflows are scheduled for recurring and deferred execution.

---

## 1. Overview

The scheduling subsystem enables workflows to run on cron schedules, fixed intervals, or as one-shot deferred executions. It wraps APScheduler as an optional dependency, uses a SQLite job store for persistence across process restarts, and integrates with the Core SDK runtime for execution.

**Module**: `kailash.runtime.scheduler`
**Added in**: v0.13.0

**Public exports** (`__all__`):

- `WorkflowScheduler`
- `ScheduleInfo`
- `ScheduleType`

---

## 2. ScheduleType Enum

**Module**: `kailash.runtime.scheduler`
**Base class**: `str, Enum`

Identifies the trigger type for a scheduled execution.

| Value      | String       | Meaning                            |
| ---------- | ------------ | ---------------------------------- |
| `CRON`     | `"cron"`     | Runs on a cron expression schedule |
| `INTERVAL` | `"interval"` | Runs at a fixed time interval      |
| `ONCE`     | `"once"`     | Runs once at a specific datetime   |

Because `ScheduleType` inherits from `str`, it serializes directly to JSON without conversion.

---

## 3. ScheduleInfo Dataclass

**Module**: `kailash.runtime.scheduler`
**Decorator**: `@dataclass`

Container for metadata about a registered schedule. Returned by `list_schedules()` and stored internally by `WorkflowScheduler`.

### 3.1 Fields

| Field           | Type                 | Default             | Description                                                             |
| --------------- | -------------------- | ------------------- | ----------------------------------------------------------------------- |
| `schedule_id`   | `str`                | (required)          | Unique identifier, format `sched-{uuid_hex[:12]}`                       |
| `schedule_type` | `ScheduleType`       | (required)          | Trigger type (cron, interval, once)                                     |
| `workflow_name` | `str`                | `""`                | Optional human-readable label                                           |
| `trigger_args`  | `Dict[str, Any]`     | `{}`                | Trigger configuration snapshot (varies by type)                         |
| `created_at`    | `datetime`           | `datetime.now(UTC)` | When the schedule was registered                                        |
| `next_run_time` | `Optional[datetime]` | `None`              | Next expected execution time. `None` if paused or completed (one-shot)  |
| `enabled`       | `bool`               | `True`              | Whether the schedule is active. Updated dynamically by `list_schedules` |
| `kwargs`        | `Dict[str, Any]`     | `{}`                | Extra keyword arguments forwarded to the runtime on each execution      |

### 3.2 trigger_args by ScheduleType

| ScheduleType | trigger_args shape           | Example                                   |
| ------------ | ---------------------------- | ----------------------------------------- |
| `CRON`       | `{"cron_expression": str}`   | `{"cron_expression": "0 */6 * * *"}`      |
| `INTERVAL`   | `{"seconds": float}`         | `{"seconds": 300.0}`                      |
| `ONCE`       | `{"run_at": str}` (ISO 8601) | `{"run_at": "2026-04-01T12:00:00+00:00"}` |

---

## 4. WorkflowScheduler Class

**Module**: `kailash.runtime.scheduler`

### 4.1 Constructor

```python
WorkflowScheduler(
    job_store_path: Optional[str] = "kailash_schedules.db",
    runtime_factory: Optional[Callable] = None,
    timezone: str = "UTC",
    *,
    dispatch_via: Optional[Dispatcher] = None,
)
```

**Parameters**:

| Parameter         | Type                   | Default                  | Description                                                                                                                                                                                                                                                                   |
| ----------------- | ---------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `job_store_path`  | `Optional[str]`        | `"kailash_schedules.db"` | Path to the SQLite database for APScheduler job persistence. `None` uses in-memory store.                                                                                                                                                                                     |
| `runtime_factory` | `Optional[Callable]`   | `None`                   | Callable returning a runtime instance. Default creates a new `LocalRuntime()` per execution.                                                                                                                                                                                  |
| `timezone`        | `str`                  | `"UTC"`                  | Timezone string for cron expression evaluation.                                                                                                                                                                                                                               |
| `dispatch_via`    | `Optional[Dispatcher]` | `None`                   | Optional `kailash.runtime.dispatcher.Dispatcher`. When provided, every fired trigger enqueues a `Task` to the dispatcher instead of executing in-process. Default `None` preserves the existing in-process behavior. Keyword-only. See §10 "Queue Dispatch" for the contract. |

**Raises**:

- `ImportError` -- APScheduler is not installed. Message: `"APScheduler is required for WorkflowScheduler. Install it with: pip install 'kailash[scheduler]' or: pip install 'apscheduler>=3.10'"`

**Initialization sequence**:

1. Calls `_check_apscheduler()` to verify APScheduler availability. Raises `ImportError` if absent.
2. Imports `SQLAlchemyJobStore` and `AsyncIOScheduler` from APScheduler.
3. If `job_store_path` is not `None`:
   - Creates a `SQLAlchemyJobStore` backed by `sqlite:///{job_store_path}`.
   - On POSIX systems, sets the SQLite file permissions to `0o600` (owner read/write only). Logs a warning if `chmod` fails (does not raise).
4. Creates an `AsyncIOScheduler` with the configured job stores and timezone.
5. Sets `self._runtime_factory`, `self._schedules` (empty dict), `self._timezone`, and `self._dispatcher` (the `dispatch_via` arg or `None`).
6. Logs initialization at INFO level. Log line includes `dispatch=queue` when `dispatch_via` is provided, `dispatch=in_process` otherwise.

**Security contract**: The SQLite job store file is created with `0o600` permissions on POSIX systems, preventing other users from reading scheduled workflow configurations. On non-POSIX systems (Windows), the file is created with default permissions.

### 4.2 start()

```python
def start(self) -> None
```

Starts the underlying APScheduler. Must be called before any scheduled jobs will execute. Safe to call multiple times -- idempotent if already running.

**Contracts**:

- Checks `self._scheduler.running` before calling `start()`.
- Logs at INFO level on start.

### 4.3 shutdown()

```python
def shutdown(self, wait: bool = True) -> None
```

Shuts down the scheduler.

**Parameters**:

| Parameter | Type   | Default | Description                                              |
| --------- | ------ | ------- | -------------------------------------------------------- |
| `wait`    | `bool` | `True`  | If `True`, waits for currently running jobs to complete. |

**Contracts**:

- Only shuts down if `self._scheduler.running` is `True`.
- Logs shutdown with `wait` parameter.

### 4.4 schedule_cron()

```python
def schedule_cron(
    self,
    workflow_builder: Any,
    cron_expression: str,
    name: str = "",
    **kwargs: Any,
) -> str
```

Schedules a workflow to run on a cron schedule.

**Parameters**:

| Parameter          | Type  | Default | Description                                                              |
| ------------------ | ----- | ------- | ------------------------------------------------------------------------ |
| `workflow_builder` | `Any` | --      | A `WorkflowBuilder` instance. Called via `.build()` on each trigger.     |
| `cron_expression`  | `str` | --      | 5-field cron expression: `minute hour day_of_month month day_of_week`.   |
| `name`             | `str` | `""`    | Optional human-readable name for identification.                         |
| `**kwargs`         | `Any` | --      | Additional keyword arguments forwarded to the runtime on each execution. |

**Returns**: `str` -- The generated `schedule_id` (format: `sched-{uuid_hex[:12]}`).

**Raises**:

- `ValueError` -- Cron expression does not have exactly 5 whitespace-separated fields. Message includes the field count and the raw expression.

**Behavior**:

1. Generates a unique schedule ID via `_generate_schedule_id()`.
2. Splits the cron expression by whitespace and validates exactly 5 fields.
3. Creates a `CronTrigger.from_crontab(cron_expression, timezone=self._timezone)`.
4. Adds the job to the APScheduler with `replace_existing=True`.
5. Stores a `ScheduleInfo` in `self._schedules`.
6. Logs the registration at INFO level.

**Edge cases**:

- Leading/trailing whitespace in `cron_expression` is stripped before parsing.
- A 6-field or 7-field cron expression (with seconds or year) is rejected because the field count check expects exactly 5.
- The cron expression itself is validated by APScheduler's `CronTrigger.from_crontab`. Invalid field values (e.g., `99 * * * *`) raise APScheduler's validation errors, not `ValueError`.

### 4.5 schedule_interval()

```python
def schedule_interval(
    self,
    workflow_builder: Any,
    seconds: float,
    name: str = "",
    **kwargs: Any,
) -> str
```

Schedules a workflow to run at a fixed interval.

**Parameters**:

| Parameter          | Type    | Default | Description                                                          |
| ------------------ | ------- | ------- | -------------------------------------------------------------------- |
| `workflow_builder` | `Any`   | --      | A `WorkflowBuilder` instance.                                        |
| `seconds`          | `float` | --      | Interval in seconds between executions. Must be positive and finite. |
| `name`             | `str`   | `""`    | Optional human-readable name.                                        |
| `**kwargs`         | `Any`   | --      | Additional runtime keyword arguments.                                |

**Returns**: `str` -- The generated `schedule_id`.

**Raises**:

- `ValueError` -- `seconds` is not positive, not finite (`inf`, `nan`), or zero. Uses `math.isfinite()` for validation.

**Behavior**:

1. Validates `seconds` is positive and finite.
2. Generates a schedule ID.
3. Adds an interval-trigger job to APScheduler.
4. Stores `ScheduleInfo` with `trigger_args={"seconds": seconds}`.

**Edge cases**:

- `seconds=0` raises `ValueError`.
- `seconds=float('inf')` raises `ValueError`.
- `seconds=float('nan')` raises `ValueError`.
- Very small values (e.g., `0.001`) are accepted -- rate limiting is the caller's responsibility.

### 4.6 schedule_once()

```python
def schedule_once(
    self,
    workflow_builder: Any,
    run_at: datetime,
    name: str = "",
    **kwargs: Any,
) -> str
```

Schedules a workflow to run once at a specific time.

**Parameters**:

| Parameter          | Type       | Default | Description                                            |
| ------------------ | ---------- | ------- | ------------------------------------------------------ |
| `workflow_builder` | `Any`      | --      | A `WorkflowBuilder` instance.                          |
| `run_at`           | `datetime` | --      | The datetime at which to execute. Should be UTC-aware. |
| `name`             | `str`      | `""`    | Optional human-readable name.                          |
| `**kwargs`         | `Any`      | --      | Additional runtime keyword arguments.                  |

**Returns**: `str` -- The generated `schedule_id`.

**Behavior**:

1. Generates a schedule ID.
2. Adds a date-trigger job to APScheduler with `run_date=run_at`.
3. Stores `ScheduleInfo` with `trigger_args={"run_at": run_at.isoformat()}` and `next_run_time=run_at`.

**Edge cases**:

- `run_at` in the past: APScheduler handles this -- the job fires immediately if the scheduler is running. No validation is performed in the Kailash layer despite the docstring claiming `ValueError` for past dates.
- Timezone-naive `run_at`: APScheduler interprets it in the scheduler's configured timezone (default UTC).

### 4.7 cancel()

```python
def cancel(self, schedule_id: str) -> None
```

Cancels a scheduled workflow execution.

**Parameters**:

| Parameter     | Type  | Description                                 |
| ------------- | ----- | ------------------------------------------- |
| `schedule_id` | `str` | The ID returned by a `schedule_*()` method. |

**Raises**:

- `KeyError` -- `schedule_id` not found in `self._schedules`. Message: `"Schedule '{schedule_id}' not found"`.

**Behavior**:

1. Checks `self._schedules` for the ID. Raises `KeyError` if absent.
2. Calls `self._scheduler.remove_job(schedule_id)` to remove from APScheduler.
3. Deletes the entry from `self._schedules`.
4. Logs at INFO level.

**Edge case**: If the APScheduler job was already removed (e.g., one-shot completed), `remove_job` may raise `JobLookupError`. This is not caught -- it propagates to the caller.

### 4.8 list_schedules()

```python
def list_schedules(self) -> List[ScheduleInfo]
```

Lists all active schedules with refreshed `next_run_time` and `enabled` status.

**Returns**: `List[ScheduleInfo]` -- A copy of the current schedules list.

**Behavior**:

1. Iterates `self._schedules` and for each entry:
   - Calls `self._scheduler.get_job(schedule_id)`.
   - If the job exists: updates `next_run_time` from the job, sets `enabled = (next_run_time is not None)`.
   - If the job is gone (one-shot completed, or externally removed): sets `enabled = False`, `next_run_time = None`.
2. Returns `list(self._schedules.values())`.

**Contract**: The returned list shares references with the internal `_schedules` dict. Callers should treat `ScheduleInfo` objects as read-only snapshots.

### 4.9 \_execute_workflow() (internal)

```python
async def _execute_workflow(self, workflow_builder: Any, **kwargs: Any) -> None
```

The callback invoked by APScheduler on each trigger. This is an async method because `WorkflowScheduler` uses `AsyncIOScheduler`.

**Behavior**:

1. Generates a `run_id` (UUID4) for logging.
2. Calls `workflow_builder.build()` to produce a `Workflow` object.
3. Obtains a runtime via `self._get_runtime()`.
4. Calls `runtime.execute(workflow, **kwargs)`.
5. Logs completion with result count at INFO.
6. On exception: logs at EXCEPTION level and re-raises.

**Contract**: The `workflow_builder` is called `.build()` on every execution -- each trigger gets a fresh workflow instance. This prevents state leakage between runs.

### 4.10 \_get_runtime() (internal)

```python
def _get_runtime(self) -> Any
```

Returns a runtime instance for execution.

**Behavior**:

- If `self._runtime_factory` is set: calls `self._runtime_factory()`.
- Otherwise: imports and returns a new `LocalRuntime()` from `kailash.runtime.local`.

**Contract**: A new runtime is created for each execution. There is no runtime pooling or reuse.

### 4.11 \_generate_schedule_id() (static)

```python
@staticmethod
def _generate_schedule_id() -> str
```

Generates a unique schedule ID.

**Returns**: `str` -- Format: `sched-{uuid4_hex[:12]}`. Example: `sched-a1b2c3d4e5f6`.

---

## 5. APScheduler Graceful Degradation

APScheduler is an optional dependency. The module uses lazy import checking to support environments where it is not installed.

### 5.1 \_check_apscheduler()

```python
def _check_apscheduler() -> bool
```

Module-level function. Checks whether `apscheduler` can be imported.

**Behavior**:

- Uses a module-level global `_apscheduler_available: Optional[bool]` initialized to `None`.
- On first call: attempts `import apscheduler`. Caches the result.
- Subsequent calls return the cached value without re-importing.

**Contract**: Importing `kailash.runtime.scheduler` always succeeds, even without APScheduler. Only instantiating `WorkflowScheduler` raises `ImportError`. This allows code to conditionally check for scheduler support:

```python
from kailash.runtime.scheduler import WorkflowScheduler
try:
    scheduler = WorkflowScheduler()
except ImportError:
    # APScheduler not installed -- scheduling unavailable
    scheduler = None
```

### 5.2 Install paths

| Extra             | Command                            |
| ----------------- | ---------------------------------- |
| Kailash scheduler | `pip install 'kailash[scheduler]'` |
| Direct            | `pip install 'apscheduler>=3.10'`  |

---

## 6. SQLite Job Store Persistence

When `job_store_path` is not `None`, the scheduler uses APScheduler's `SQLAlchemyJobStore` backed by a SQLite database. This provides:

- **Persistence across restarts**: Jobs survive process shutdown and resume on the next `start()`.
- **File-level security**: On POSIX, permissions are set to `0o600` (owner-only).
- **Default path**: `kailash_schedules.db` in the current working directory.

When `job_store_path` is `None`, APScheduler uses its default in-memory job store. Jobs are lost on shutdown.

### 6.1 File permission behavior

```python
if os.name == "posix":
    db_abs = os.path.abspath(job_store_path)
    open(db_abs, "a").close()  # ensure file exists
    os.chmod(db_abs, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
```

- The file is touched (created if absent) before `chmod`.
- `OSError` during `chmod` is logged as a warning but does not prevent scheduler initialization.

---

## 7. Runtime Integration

### 7.1 Default runtime

Without a `runtime_factory`, the scheduler creates a new `LocalRuntime` for each execution. This is the synchronous runtime -- it blocks the APScheduler executor thread until the workflow completes.

### 7.2 Custom runtime factory

Callers can provide any callable that returns a runtime instance:

```python
from kailash.runtime.local_async import AsyncLocalRuntime

scheduler = WorkflowScheduler(
    runtime_factory=lambda: AsyncLocalRuntime()
)
```

The factory is called on every trigger -- no runtime reuse.

### 7.3 Execution model

`WorkflowScheduler` uses `AsyncIOScheduler`, which runs jobs as coroutines on the event loop. The `_execute_workflow` method is `async`. However, `runtime.execute()` (from `LocalRuntime`) is synchronous. This means:

- When using the default `LocalRuntime`, the synchronous `execute()` call blocks within the async callback. APScheduler handles this via its default thread pool executor.
- When using `AsyncLocalRuntime`, the caller should ensure the runtime's async methods are properly awaited.

---

## 8. Usage Patterns

### 8.1 Basic cron scheduling

```python
from kailash.runtime.scheduler import WorkflowScheduler
from kailash.workflow.builder import WorkflowBuilder

scheduler = WorkflowScheduler()
scheduler.start()

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})

# Every 6 hours
sid = scheduler.schedule_cron(workflow, "0 */6 * * *", name="data-import")

# Monday at 2:30 AM
sid2 = scheduler.schedule_cron(workflow, "30 2 * * 1", name="weekly-report")
```

### 8.2 Fixed interval

```python
# Every 5 minutes
sid = scheduler.schedule_interval(workflow, seconds=300, name="health-check")
```

### 8.3 One-shot deferred execution

```python
from datetime import datetime, UTC

run_at = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
sid = scheduler.schedule_once(workflow, run_at=run_at, name="year-end-report")
```

### 8.4 Lifecycle management

```python
# List all schedules
for info in scheduler.list_schedules():
    print(f"{info.schedule_id}: {info.schedule_type}, next={info.next_run_time}")

# Cancel a schedule
scheduler.cancel(sid)

# Graceful shutdown (waits for running jobs)
scheduler.shutdown(wait=True)

# Immediate shutdown (kills running jobs)
scheduler.shutdown(wait=False)
```

### 8.5 In-memory only (no persistence)

```python
scheduler = WorkflowScheduler(job_store_path=None)
```

---

## 9. Queue Dispatch

**Module**: `kailash.runtime.dispatcher` (ABC + helpers) + `kailash.infrastructure.task_queue` (SQL adapter)
**Added in**: v2.9.0

When `WorkflowScheduler` is constructed with `dispatch_via=<Dispatcher>`, every fired trigger enqueues a `Task` to the dispatcher in lieu of executing the workflow in-process. A separate worker pool polls the dispatcher and runs the workflow against its own runtime. This enables (a) multi-instance scheduler deployments where two scheduler processes can fire the same trigger and the second is silently deduped at the queue layer, and (b) worker-side resume from checkpoint when paired with a checkpoint store.

### 9.1 Dispatcher ABC

**Module**: `kailash.runtime.dispatcher`

```python
class Dispatcher(ABC):
    async def enqueue(self, task: Task) -> None: ...
    def poll(self, queue_name: str = "default") -> AsyncIterator[Task]: ...
    async def ack(self, task_id: str) -> None: ...
    async def nack(self, task_id: str, *, reason: str) -> None: ...
```

**Public exports** of `kailash.runtime.dispatcher` (`__all__`): `Dispatcher`, `Task`, `compute_task_id`.

The contract is intentionally minimal:

| Method    | Contract                                                                                                                                                                                                                                         |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `enqueue` | Idempotent on `task.task_id`. A duplicate enqueue with the same `task_id` MUST be a silent no-op (no exception). Non-duplicate failures (connectivity, serialization) propagate after a structured ERROR log.                                    |
| `poll`    | Returns an `AsyncIterator[Task]` that yields claimed tasks one at a time. Implementations atomically transition each task to `processing` status. When the queue is empty the iterator stops; long-polling callers re-invoke `poll()` in a loop. |
| `ack`     | Marks a task as completed. Idempotent (acking a completed task is a no-op).                                                                                                                                                                      |
| `nack`    | Marks a task as failed with a short reason. The dispatcher decides whether to requeue (transient failure) or dead-letter (max attempts exceeded) based on its own attempt counter. The reason MUST NOT contain secrets or PII.                   |

A subclass missing any of the four methods raises `TypeError` on instantiation per Python's `ABC` contract.

### 9.2 Task dataclass

```python
@dataclass
class Task:
    task_id: str
    schedule_id: str
    workflow_blob: bytes
    planned_fire_time: str            # ISO 8601 UTC
    queue_name: str = "default"
    kwargs: Dict[str, Any] = field(default_factory=dict)
```

| Field               | Description                                                                                                                                                                                                 |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task_id`           | Stable hash of `(schedule_id, planned_fire_time_iso)` produced by `compute_task_id`. 32-character lowercase hex (128 bits of collision resistance). Used as the queue's PRIMARY KEY for idempotent enqueue. |
| `schedule_id`       | The scheduler-assigned schedule identifier (e.g. `sched-abc123def456`).                                                                                                                                     |
| `workflow_blob`     | The serialized workflow (pickled `WorkflowBuilder.build()` output). Workers deserialize and execute.                                                                                                        |
| `planned_fire_time` | The trigger's intended fire time as an ISO 8601 string. The scheduler-computed fire instant — NOT wall-clock now() — so multi-instance double-fires produce the same `task_id`.                             |
| `queue_name`        | Logical queue for routing (default `"default"`).                                                                                                                                                            |
| `kwargs`            | Additional keyword arguments forwarded to `runtime.execute(...)` on the worker side.                                                                                                                        |

### 9.3 compute_task_id helper

```python
def compute_task_id(schedule_id: str, planned_fire_time: datetime) -> str:
    """Return SHA-256(schedule_id || planned_fire_time.isoformat())[:32]."""
```

Stability contract:

- Same `(schedule_id, planned_fire_time)` ALWAYS produces the same hex string.
- Changing either input flips the hash.
- The ISO 8601 representation preserves microsecond precision when present. Naive datetimes (no tzinfo) and aware datetimes in different timezones produce different `task_id`s — callers MUST be consistent about timezone awareness within a single schedule.

### 9.4 SQLTaskQueueDispatcher

**Module**: `kailash.infrastructure.task_queue`

Reference `Dispatcher` implementation backed by a SQL table managed by `kailash.db.connection.ConnectionManager`. PostgreSQL, MySQL 8.0+, and SQLite portable per `rules/infrastructure-sql.md` (uses `dialect.text_column`, `dialect.quote_identifier`, `for_update_skip_locked`, canonical `?` placeholders translated by `ConnectionManager.execute`).

```python
from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueueDispatcher
from kailash.runtime.scheduler import WorkflowScheduler

conn = ConnectionManager("postgresql://...")
await conn.initialize()

dispatcher = SQLTaskQueueDispatcher(conn)
await dispatcher.initialize()

scheduler = WorkflowScheduler(dispatch_via=dispatcher)
```

Schema (managed by the underlying `SQLTaskQueue`): `task_id PK, queue_name, payload, status, created_at, updated_at, attempts, max_attempts, visibility_timeout, worker_id, error`. The Task fields are encoded into the `payload` JSON (`schedule_id`, `workflow_blob_b64`, `planned_fire_time`, `kwargs`).

### 9.5 Idempotent enqueue contract

`SQLTaskQueueDispatcher.enqueue(task)` catches PRIMARY KEY / unique-constraint violations across asyncpg (`UniqueViolationError` / `TransactionIntegrityConstraintViolationError`), sqlite (`IntegrityError` whose message contains `UNIQUE` or `PRIMARY KEY`), and aiomysql (errno 1062) and treats them as silent no-ops with a DEBUG log line carrying the `task_id_hash` (8-char SHA-256 prefix). Multi-instance scheduler double-fire reduces to one row at the queue layer.

Non-PK failures log at ERROR with grep-able `schedule_id` + `task_id_hash` + reason, then propagate to the caller (which surfaces to APScheduler's misfire / retry policy).

### 9.6 Worker resume hint

Workers polling a `Dispatcher` SHOULD pass the received `task.task_id` as the `idempotency_key` argument to `runtime.execute(...)` when paired with a checkpoint store. This gives resume-from-checkpoint semantics on crash recovery — the worker that picks up a previously-running task sees the existing checkpoint and resumes from the last completed node. This contract is informational; nothing in the dispatcher enforces it (the binding is between the worker and the checkpoint-aware runtime).

### 9.7 In-process fallback semantics

When `dispatch_via=None` (the default), `WorkflowScheduler._execute_workflow` runs the workflow inline via the configured runtime — the existing v0.13.0 behavior. The dispatcher branch is a strict superset: setting `dispatch_via=` does not change anything else about the scheduler's API or storage.

### 9.8 Error log surface

Every enqueue failure (whether silently-skipped duplicate or genuinely-failed) generates exactly one structured log line:

| Outcome                   | Level | Fields                                                              |
| ------------------------- | ----- | ------------------------------------------------------------------- |
| Duplicate (silent skip)   | DEBUG | `task.enqueue.duplicate task_id_hash=… schedule_id=…`               |
| Non-duplicate failure     | ERROR | `task.enqueue.failed task_id_hash=… schedule_id=… reason=<ExcName>` |
| Successful enqueue        | INFO  | `scheduler.dispatch.enqueued schedule_id=… task_id_hash=…`          |
| Serialization failure     | ERROR | `scheduler.dispatch.serialize_failed schedule_id=… task_id_hash=…`  |
| Dispatch invocation start | INFO  | `scheduler.dispatch.start schedule_id=… task_id_hash=… run_id=…`    |

`task_id_hash` is the first 8 hex chars of `sha256(task_id)` per `rules/observability.md` Rule 8 (raw `task_id` reveals the schedule identifier and fire-time, which is schema-revealing for log aggregators).

### 9.9 planned_fire_time capture mechanism

`planned_fire_time` is captured at job-submission time via APScheduler's `EVENT_JOB_SUBMITTED` listener — NOT read from `job.next_run_time` at callback entry. The submission event fires BEFORE the job callback runs and exposes `event.scheduled_run_times: list[datetime]`, the actual trigger fire instants for the currently-firing job. The scheduler records the LAST element (the most recent fire — typically the only one; coalesce/misfire policies may produce several) keyed by `event.job_id`.

This mechanism is required because by the time the dispatch callback runs, APScheduler has already advanced `job.next_run_time` to the NEXT scheduled fire. Reading `job.next_run_time` from inside the callback would record a fire instant one interval ahead of truth on every cron/interval trigger.

The capture is symmetric: `EVENT_JOB_EXECUTED | EVENT_JOB_ERROR` listener clears the recorded entry once the job finishes. If `_planned_fire_time(schedule_id)` is invoked without a prior submit-event recording, it raises `RuntimeError` rather than falling back to `datetime.now(UTC)` — silent fallback would silently break multi-instance dedup (each scheduler instance would compute a different `task_id` for the same fire).

Stability across multi-instance schedulers: every instance receives the same `scheduled_run_times` from APScheduler for the same trigger fire, so `compute_task_id(schedule_id, fire_time)` produces the SAME `task_id` and the queue layer dedups via PRIMARY KEY.

---

## 10. Constraints and Limitations

1. **No async-native execution**: The default `_execute_workflow` calls `runtime.execute()` synchronously inside an async callback. For fully async execution, provide a custom `runtime_factory` with `AsyncLocalRuntime`.
2. **No built-in worker pool**: The scheduler enqueues to the dispatcher; the application is responsible for running worker processes that call `dispatcher.poll()` in a loop. The Kailash SDK supplies the dispatcher contract and the SQL-backed adapter; worker orchestration is left to the deploying application.
3. **No schedule modification**: There is no `update_schedule()` method. To change a schedule's trigger, cancel it and create a new one.
4. **No pause/resume**: Individual schedules cannot be paused. The entire scheduler can be shut down and restarted.
5. **Schedule ID format**: IDs are `sched-{12_hex_chars}`. Not configurable.
6. **No retry on failure**: If a scheduled execution fails (in-process or enqueue-side), it is logged but the scheduler does not retry. The next trigger fires normally. Worker-side retry on `nack` is the dispatcher implementation's responsibility (`SQLTaskQueueDispatcher` requeues until `max_attempts`, then dead-letters).
7. **APScheduler version**: Requires `apscheduler>=3.10`. APScheduler 4.x has a different API and is not supported.
