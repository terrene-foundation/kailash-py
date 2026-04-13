# Scheduling Specification

Version: 2.8.5
Package: `kailash`
Status: Authoritative domain truth document
Scope: WorkflowScheduler, cron/interval/one-shot scheduling, APScheduler integration, SQLite job persistence, runtime integration

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
)
```

**Parameters**:

| Parameter         | Type                 | Default                  | Description                                                                                  |
| ----------------- | -------------------- | ------------------------ | -------------------------------------------------------------------------------------------- |
| `job_store_path`  | `Optional[str]`      | `"kailash_schedules.db"` | Path to the SQLite database for APScheduler job persistence. `None` uses in-memory store.    |
| `runtime_factory` | `Optional[Callable]` | `None`                   | Callable returning a runtime instance. Default creates a new `LocalRuntime()` per execution. |
| `timezone`        | `str`                | `"UTC"`                  | Timezone string for cron expression evaluation.                                              |

**Raises**:

- `ImportError` -- APScheduler is not installed. Message: `"APScheduler is required for WorkflowScheduler. Install it with: pip install 'kailash[scheduler]' or: pip install 'apscheduler>=3.10'"`

**Initialization sequence**:

1. Calls `_check_apscheduler()` to verify APScheduler availability. Raises `ImportError` if absent.
2. Imports `SQLAlchemyJobStore` and `AsyncIOScheduler` from APScheduler.
3. If `job_store_path` is not `None`:
   - Creates a `SQLAlchemyJobStore` backed by `sqlite:///{job_store_path}`.
   - On POSIX systems, sets the SQLite file permissions to `0o600` (owner read/write only). Logs a warning if `chmod` fails (does not raise).
4. Creates an `AsyncIOScheduler` with the configured job stores and timezone.
5. Sets `self._runtime_factory`, `self._schedules` (empty dict), and `self._timezone`.
6. Logs initialization at INFO level.

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

## 9. Constraints and Limitations

1. **No async-native execution**: The default `_execute_workflow` calls `runtime.execute()` synchronously inside an async callback. For fully async execution, provide a custom `runtime_factory` with `AsyncLocalRuntime`.
2. **No distributed scheduling**: The scheduler is single-process. For distributed scheduling across multiple instances, use an external scheduler (Celery, Temporal) with Kailash workflows as tasks.
3. **No schedule modification**: There is no `update_schedule()` method. To change a schedule's trigger, cancel it and create a new one.
4. **No pause/resume**: Individual schedules cannot be paused. The entire scheduler can be shut down and restarted.
5. **Schedule ID format**: IDs are `sched-{12_hex_chars}`. Not configurable.
6. **No retry on failure**: If a scheduled execution fails, it is logged but not retried. The next trigger fires normally.
7. **APScheduler version**: Requires `apscheduler>=3.10`. APScheduler 4.x has a different API and is not supported.
