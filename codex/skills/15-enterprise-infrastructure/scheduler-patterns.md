# Scheduler Patterns

You are an expert in Kailash's scheduling primitives — `WorkflowScheduler` (general-purpose cron / interval / one-shot) and `FabricScheduler` (DataFlow product-refresh cron). Guide users through engagement, migration from external cron, and the multi-instance hazards.

> Source: `src/kailash/runtime/scheduler.py` (`WorkflowScheduler`), the dataflow package (`src/dataflow/fabric/scheduler.py`) (`FabricScheduler`).

## When to Engage

Surface these primitives when the user describes any of:

- "Run this workflow every N minutes / on a cron schedule / nightly at 02:00"
- "Replace the cron daemon / external scheduler that triggers our pipelines"
- "Refresh this DataFlow product on a schedule" (`FabricScheduler` specifically)
- "Persist scheduled jobs across process restarts" (APScheduler SQLite jobstore is the answer)
- "One-shot delayed execution / run this workflow at a specific timestamp"

If the user is already grepping `kailash.runtime` for scheduling, the Primitive Inventory in the parent `SKILL.md` is the correct surface to point them at first.

## WorkflowScheduler — Recurring Workflow Execution

`WorkflowScheduler` wraps APScheduler's `AsyncIOScheduler` with a `SQLAlchemyJobStore` (SQLite by default) so schedules survive process restart. Owner-only file permissions (0o600) are set automatically on POSIX systems.

### Setup

```python
from kailash.runtime.scheduler import WorkflowScheduler

# Default: persistent jobstore at ./kailash_schedules.db, UTC timezone
scheduler = WorkflowScheduler()

# Custom: explicit path + timezone, optional runtime factory for shared pool reuse
scheduler = WorkflowScheduler(
    job_store_path="/var/lib/kailash/schedules.db",
    timezone="America/New_York",
    runtime_factory=lambda: shared_runtime,  # default: new LocalRuntime per execution
)
scheduler.start()  # idempotent — safe to call again
```

### Cron + Interval + One-Shot

```python
# DO — schedule via the dedicated method, capture the schedule_id
sid_cron = scheduler.schedule_cron(workflow, "0 22 * * *", name="nightly_etl")
sid_int  = scheduler.schedule_interval(workflow, seconds=60, name="poll_queue")
sid_once = scheduler.schedule_once(workflow, run_at=datetime(2026, 6, 1, 14, 0))

# Cancel by id
scheduler.cancel(sid_int)

# Graceful shutdown — wait for in-flight jobs, then stop the loop
scheduler.shutdown(wait=True)

# DO NOT — call APScheduler's add_job directly bypassing schedule_*
scheduler._scheduler.add_job(workflow, "cron", ...)  # private attribute
```

**Why:** `schedule_cron` validates the 5-field cron expression at registration time; bypassing it lets a malformed expression land in the jobstore and crash the scheduler loop on the first trigger.

### Cron Expression Contract

`schedule_cron` requires exactly 5 fields: `minute hour day_of_month month day_of_week`. APScheduler's `CronTrigger.from_crontab` parses; invalid expressions raise `ValueError` at registration, not at trigger time.

```python
# DO — 5 fields, validated synchronously at registration
sid = scheduler.schedule_cron(workflow, "30 2 * * 1")  # Mon 02:30

# DO NOT — 6-field "seconds" form (raises ValueError)
sid = scheduler.schedule_cron(workflow, "0 30 2 * * 1")  # 6 fields — rejected
```

**Why:** Failing fast at registration converts a runtime crash on the first trigger into a synchronous error the operator can fix before deployment.

### Interval Validation

`schedule_interval` rejects non-positive and non-finite values with `ValueError`.

```python
# DO — positive finite interval
scheduler.schedule_interval(workflow, seconds=300)

# DO NOT — zero, negative, or NaN intervals
scheduler.schedule_interval(workflow, seconds=0)            # ValueError
scheduler.schedule_interval(workflow, seconds=float("inf")) # ValueError
```

**Why:** APScheduler accepts these silently and the resulting job either fires in a tight loop (zero) or never fires (NaN); the validation closes both failure modes at the API surface.

## Migration From An External Cron Daemon

Replacing an external cron entry that invokes a Python entrypoint:

```python
# Before — host-level crontab line, fragile across hosts/timezones, no jobstore
# 0 22 * * * /usr/bin/python /opt/app/run_etl.py

# After — WorkflowScheduler in the application process
from kailash.runtime.scheduler import WorkflowScheduler
from kailash.workflow.builder import WorkflowBuilder

def build_etl_workflow() -> WorkflowBuilder:
    workflow = WorkflowBuilder()
    workflow.add_node("ExtractNode", "extract", {"source": "s3://bucket"})
    workflow.add_node("TransformNode", "transform", {})
    workflow.add_node("LoadNode", "load", {"target": "warehouse"})
    workflow.add_connection("extract", "data", "transform", "input")
    workflow.add_connection("transform", "data", "load", "input")
    return workflow

scheduler = WorkflowScheduler(job_store_path="/var/lib/kailash/schedules.db")
scheduler.start()
scheduler.schedule_cron(build_etl_workflow(), "0 22 * * *", name="nightly_etl")
```

The schedule survives application restart (jobstore persists); the host machine no longer carries scheduling state.

## FabricScheduler — DataFlow Product Refresh

`FabricScheduler` is DataFlow-specific: it filters registered products that declare a `schedule` attribute (cron expression) and runs one supervised `asyncio.Task` per product. A crash in one schedule loop does NOT affect siblings (RT-1 supervised pattern).

### When to Engage

Use `FabricScheduler` ONLY when working with `dataflow.fabric.runtime.FabricRuntime` and registered products that declare a `schedule` attribute. For any other recurring workflow, `WorkflowScheduler` is the correct primitive.

```python
# DO — wired into FabricRuntime via on_schedule callback
from dataflow.fabric.scheduler import FabricScheduler

scheduler = FabricScheduler(
    products=registered_products,         # Dict[str, ProductRegistration]
    on_schedule=runtime._on_source_change, # async callback, takes product_name
)
await scheduler.start()
# ...
await scheduler.stop()  # cancels all tasks, awaits clean shutdown

# DO NOT — use FabricScheduler for non-DataFlow workflows
scheduler = FabricScheduler(products={...}, on_schedule=lambda name: ...)  # wrong primitive
# Use WorkflowScheduler for general-purpose cron instead.
```

**Why:** `FabricScheduler.start()` lazy-imports `croniter` and raises `ImportError` if missing; the supervised-task pattern restarts crashed loops after `_RESTART_DELAY_SECONDS` (5s) but does NOT carry state across restarts. Misusing it for general workflows reinvents `WorkflowScheduler` without the jobstore.

## Multi-Instance Scheduler Hazards

Both schedulers are instance-local. Running two application instances each with `WorkflowScheduler(job_store_path="schedules.db")` pointing at the SAME jobstore means each instance triggers each schedule — every job fires twice.

```python
# DO — single-leader strategy: only the elected leader runs the scheduler
if app.is_leader():
    scheduler = WorkflowScheduler(job_store_path="/var/lib/kailash/schedules.db")
    scheduler.start()

# DO — queue-dispatch strategy: scheduler enqueues into SQLTaskQueue,
# any worker dequeues and executes (deduplication via task_id)
def enqueue_job(workflow_id: str):
    asyncio.create_task(queue.enqueue(payload={"workflow_id": workflow_id}))
scheduler.schedule_cron(enqueue_job, "0 22 * * *", workflow_id="etl")

# DO NOT — N replicas each running their own WorkflowScheduler against
# the same jobstore (or separate jobstores triggering the same workflow)
# kubectl scale deployment app --replicas=3   # every job now fires 3x
```

**Why:** APScheduler's jobstore stores trigger metadata, not exclusion locks. Two schedulers reading the same jobstore each compute "next trigger" identically and each fire the job. Single-leader OR queue-dispatch are the two correct dedup strategies; "everyone runs the scheduler and we hope" is BLOCKED.

In-flight integration work for multi-instance scheduling is tracked at the SDK's open multi-instance scheduler issue (single-leader election + jobstore lock).

## Test Tier Recommendation

Tier 2 (real APScheduler + real SQLite jobstore) is the appropriate test tier. Tier 1 unit tests against `WorkflowScheduler` mock `_scheduler` and prove only that the helper calls add_job; they do not prove the trigger fires or that the persisted state survives a fresh-process load.

## Related

- `task-queue-patterns.md` — dispatch strategy companion (scheduler enqueues, queue dequeues)
- `durability-patterns.md` — for workflows that must resume across process boundaries when triggered
- `progressive-infrastructure.md` — Level 0/1/2 model that determines whether the jobstore is local SQLite or shared
