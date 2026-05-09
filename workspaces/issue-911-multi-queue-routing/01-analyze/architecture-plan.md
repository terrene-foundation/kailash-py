# Issue #911: multi-queue routing in WorkflowScheduler

> Phase 01 (`/analyze`) deliverable. Read-only — no code edits, no PRs, no issues filed.

## Brief summary

Issue #911 (`feat(distributed): multi-queue routing in DistributedRuntime + Worker`) asks for first-class multi-queue routing primitives in the distributed runtime so a single `DistributedRuntime` instance can route different workflows to different logical queues (`fast`, `slow`, `analysis`), and a single `Worker` process can dequeue from a `{queue_name: concurrency}` map with per-queue concurrency limits — equivalent to celery's `-Q queue1,queue2 -c 4` semantics.

Today the producer side (`DistributedRuntime`) has no queue parameter, the consumer side (`Worker`) consumes a single TaskQueue, and `TaskQueue.__init__` takes a single `queue_key` (Redis list name) per instance. The `Task` dataclass at `src/kailash/runtime/dispatcher.py:127` and the SQL-backed `SQLTaskQueue` at `src/kailash/infrastructure/task_queue.py:143` already carry a `queue_name: str = "default"` field — i.e. partial multi-queue scaffolding exists at the queue-payload layer but is NOT plumbed through the producer/consumer surfaces in `runtime/distributed.py`. The work for #911 is to extend the producer + consumer + Redis `TaskQueue` to honor `queue_name`, compose with the lifecycle hooks landed in #915 and the `RetrySpec` retry primitive landed in #916, and preserve the current single-queue default so the change is non-breaking.

## Brief corrections

The user-supplied prompt asserted that issue **#912 is a "signature cleanup" of `DistributedRuntime.execute(workflow, parameters=None, **kwargs)`** that #911 should layer on top of. That framing is **incorrect\*\*. Verified:

| Brief claim                                                                      | Verdict | Evidence                                                                                                                                                                                                                                                                 |
| -------------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| "#912 replaces `**kwargs` with explicit typed kwargs"                            | FALSE   | `gh issue view 912` — issue #912 is `feat(runtime): per-task soft/hard time limits in Worker + WorkflowScheduler`. It proposes adding `soft_time_limit=N, time_limit=M` kwargs, NOT cleaning up the existing `**kwargs`.                                                 |
| "`DistributedRuntime.execute` at `distributed.py:480-520` silently drops kwargs" | TRUE    | `src/kailash/runtime/distributed.py:502-544` — `def execute(self, workflow, parameters=None, **kwargs)` accepts `**kwargs` and never reads them after the signature. This IS a silent-drop bug per `zero-tolerance.md` Rule 3c, but it is NOT the subject of issue #912. |
| "TaskQueue.**init** takes a single `queue_key`"                                  | TRUE    | `src/kailash/runtime/distributed.py:178` — `queue_key: str = _QUEUE_KEY`. One Redis list per `TaskQueue` instance.                                                                                                                                                       |
| "Worker dequeues from one queue"                                                 | TRUE    | `src/kailash/runtime/distributed.py:625` — `self._queue = queue or TaskQueue(...)`. Single queue reference, no multi-queue map.                                                                                                                                          |
| "DistributedRuntime has no `queue_name` parameter today"                         | TRUE    | `src/kailash/runtime/distributed.py:474-490` — constructor has no `queue_name`/`queue` routing param, only a single optional `TaskQueue`.                                                                                                                                |
| "`Task` dataclass has no concept of queue name today"                            | FALSE   | `src/kailash/runtime/dispatcher.py:127` — `queue_name: str = "default"` already exists. The scheduler-side dispatcher path already plumbs queue_name; only the Redis-side `TaskQueue` + `DistributedRuntime` + `Worker` are missing the wiring.                          |
| "SQLTaskQueue has no concept of queue name today"                                | FALSE   | `src/kailash/infrastructure/task_queue.py:143,243,332` — `queue_name` is a column on the `task_queue` table and a parameter on `enqueue()` / `dequeue()` / `requeue_stale()` / `get_stats()` / `purge_completed()`.                                                      |

**Implication for the plan**: the user's framing of "#911 reuses #912's cleaned signature" cannot be honored as-stated because #912 is not a signature-cleanup workstream. The `**kwargs` silent-drop bug at `distributed.py:502-544` IS real and IS a `zero-tolerance.md` Rule 3c violation, but it is in-scope for #911 itself: the queue routing surface this plan introduces is the moment to convert `**kwargs` into the named, consumed kwargs the surface advertises. This plan therefore (a) treats `queue_name=` as the first explicit named kwarg added to the surface and (b) preserves the existing `parameters=` shape but converts the dangling `**kwargs` into a documented forwarding boundary — see § "API surface" below.

## Upstream dependency on #912

There is no upstream dependency on #912 for issue #911. #912 is **per-task soft/hard time limits** on a different axis (task duration, not task routing). The two issues compose orthogonally: a producer can supply BOTH `queue_name="slow"` AND `soft_time_limit=300` independently. If #912 lands first, the queue-routing surface MUST accept `soft_time_limit=` / `time_limit=` as forwardable kwargs without overloading their semantics. If #912 lands later, this plan's named-kwarg discipline (every accepted kwarg has a consumer) MUST extend to `soft_time_limit=` / `time_limit=` then.

The actual upstream dependencies for #911 are:

1. **#915 — lifecycle hooks** (already merged, `feat(scheduler): /redteam round-2 — observability + ctx-manager (#910)` 2026-05-09 commit `dc182dcc`). The new `Worker.on_task_*` registries at `src/kailash/runtime/distributed.py:640-644` (`_hooks_prerun`, `_hooks_postrun`, `_hooks_success`, `_hooks_retry`, `_hooks_failure`) MUST receive the queue name in the `TaskEvent` payload so handlers can route to per-queue alerting (e.g. dashboard `slow_queue_failure_rate`).
2. **#916 — retry primitives** (already merged, `feat(scheduler): per-job retry primitives via RetrySpec (#910)` commit `3bd3445e`). The `RetrySpec` dataclass at `src/kailash/runtime/scheduler.py:74-210` and the in-process retry loop at `_execute_workflow:838-925` are scheduler-internal — `RetrySpec` is BLOCKED from queue-dispatch path today (`scheduler.py:768-774`). #911's queue routing MUST NOT silently re-route this BLOCK; the dispatcher-side retry contract remains the dispatcher's domain.

## Failure-point analysis

Numbered failure points; each is `condition → consequence → mitigation`. Drives the test plan.

### 1. Queue selection determinism

**Condition.** Producer calls `runtime.execute(wf, queue="fast")`. The producer SDK and the Worker MUST both agree on a canonical Redis-list key (`kailash:tasks:pending:fast` vs `kailash:tasks:fast` vs `fast`) — drift between producer and consumer silently strands tasks on a queue no Worker dequeues from.

**Consequence.** Tasks enqueued forever pending; users see "queued" status in `get_result()` indefinitely and assume worker exhaustion. The masking-helper-failure-on-success class (`observability.md` Rule 6.1) at the routing layer.

**Mitigation.** Single canonical helper `_make_queue_key(queue_name) -> str` co-located in `runtime/distributed.py` AND `infrastructure/task_queue.py` (or, preferably, exported once from a new helper module so both producer + consumer import the same function — same structural defense as `kailash.utils.url_credentials` in `security.md` § "Credential Decode Helpers"). Tier 2 round-trip test: producer enqueues with `queue_name="fast"`, consumer dequeues from a `Worker(queues={"fast": 1})` and asserts the task is the same one. Structural invariant test: `_make_queue_key("fast")` returns the byte-for-byte expected string `kailash:tasks:pending:fast` (pin the format).

### 2. Default queue compatibility (single-queue users today)

**Condition.** Existing users have `DistributedRuntime(redis_url=...)` and `Worker(redis_url=...)` running in production today. The shipped Redis list key is `_QUEUE_KEY = "kailash:tasks:pending"` (`distributed.py:56`).

**Consequence.** A naive change to `kailash:tasks:pending:default` orphans every in-flight task already enqueued under the old key. Same failure-mode class as `zero-tolerance.md` Rule 6a public-API removal without deprecation cycle.

**Mitigation.** The "default" queue MUST resolve to the EXACT existing `_QUEUE_KEY` string (`kailash:tasks:pending`) — i.e. `_make_queue_key("default")` returns `"kailash:tasks:pending"`, NOT `"kailash:tasks:pending:default"`. Non-default queues get the suffix: `_make_queue_key("fast")` returns `"kailash:tasks:pending:fast"`. Pin this asymmetry in the structural invariant test. Cross-SDK note: kailash-rs MUST adopt the same asymmetry per `cross-sdk-inspection.md` Rule 4 (byte-pin vectors).

### 3. Queue-priority inversion / starvation

**Condition.** `Worker(queues={"fast": 8, "slow": 2})` polls multiple queues. The dequeue loop picks queues in some order. If the loop is naive ("for queue in queues: try dequeue"), a slow-queue task that's polled FIRST under a `BLMOVE timeout=2` blocks the worker for 2s before the fast-queue is even consulted — under load, fast-queue tasks accumulate.

**Consequence.** "Multi-queue worker" silently behaves as a sequential N-queue serializer. The advertised "slow task does not block fast task pickup" acceptance criterion in #911 fails. Same class as `zero-tolerance.md` Rule 2 fake-dispatch (the dispatcher accepts queue names but no branch in the dispatcher fires them in parallel).

**Mitigation.** Per-queue independent dequeue tasks: a `Worker` with `queues={"fast": 8, "slow": 2}` spawns ONE asyncio dequeue-loop task per queue, each with its own concurrency semaphore sized to the per-queue concurrency. Polling is `BLMOVE` per-queue in parallel, NOT a serialized round-robin. Tier 2 test: enqueue 1 slow-task that sleeps 30s + 100 fast-tasks; assert `fast` tasks complete with median latency < 1s and the slow-task completes around 30s.

### 4. Per-queue concurrency budget vs visibility timeout

**Condition.** A queue declared with `concurrency=2` and `visibility_timeout=300` (default) holds at most 2 tasks claimed per worker. If a third producer enqueues, the third task waits — which is correct. But if a worker holds a task longer than `visibility_timeout` (legitimate slow-queue work > 5 min), Redis re-delivers the same task to a sibling worker.

**Consequence.** Slow-queue users get duplicate execution silently. Dashboards show 2× completion count.

**Mitigation.** `Worker(queues=...)` MUST accept per-queue `visibility_timeout` overrides via the dict syntax `queues={"slow": {"concurrency": 2, "visibility_timeout": 1800}, "fast": 8}` — bare int means "concurrency only, default visibility_timeout". Document this in the `queues=` parameter docstring with a code example. Tier 2 test: slow queue with `visibility_timeout=10` against a 30-sec workflow observes re-delivery; same test with `visibility_timeout=60` observes single delivery.

### 5. Queue persistence on resume / multi-instance scheduler dedup

**Condition.** A scheduler dispatches a job at planned-fire-time T to queue `slow`. The scheduler crashes; a second scheduler instance fires the same job at T+ε. Per `scheduler.py:780-832`, both scheduler instances compute the same `task_id = compute_task_id(schedule_id, planned_fire_time)`. Today the dispatch path is queue-agnostic; tomorrow with #911, the SECOND fire might pick a different queue if the scheduler's queue-resolver depends on instance-local state.

**Consequence.** Same task_id ends up on TWO queues, defeating queue-layer dedup. `Task.queue_name` is currently part of the dataclass but NOT part of `compute_task_id` (`dispatcher.py:45-78`). Consequence: queue routing must be a deterministic function of (schedule_id) AND must be persisted with the schedule, NOT computed at fire time from a mutable scheduler-local table.

**Mitigation.** `WorkflowScheduler.schedule_*` accepts `queue=` at schedule-registration time; the value is persisted into APScheduler's job-store kwargs alongside `_kailash_retry_spec`. Fire-time dispatch reads `queue` from the persisted kwargs — every scheduler instance computing for the same `schedule_id` resolves to the SAME queue. `compute_task_id` does NOT change (only `(schedule_id, planned_fire_time)` is hashed) — this is correct because two schedulers MUST agree on the queue too, which they do via persisted job kwargs. Tier 2 test: schedule a job with `queue="slow"`, verify APScheduler-stored kwargs include the queue, simulate scheduler restart, verify the resumed schedule still dispatches to `slow`.

### 6. Lifecycle-event correlation across queues

**Condition.** Worker handlers registered via `on_task_success(handler)` (`distributed.py:700`) receive a `TaskEvent` dataclass. Today `TaskEvent` carries `task_id`, `workflow_name`, `attempt`, `worker_id`, `elapsed_ms`, `exception` (`lifecycle_events.py:36-63`). It does NOT carry `queue_name`.

**Consequence.** A handler that wants to alert "slow queue failure rate > X" cannot tell which queue the failed task came from. Operators add a side-channel grep on `task_id` against an external table — institutional debt.

**Mitigation.** Add `queue_name: Optional[str] = None` to `TaskEvent` (`frozen=True` dataclass — additive only, default None preserves serialization). Worker `_execute_task` populates `queue_name` from `task.queue_name` (already on the `Task` dataclass at `dispatcher.py:127`) OR from the TaskMessage queue origin (need to add the field on `TaskMessage` at `distributed.py:64-99`). Tier 2 test: handler registered via `on_task_success` receives `event.queue_name == "slow"` for a task enqueued to `slow`.

### 7. Worker registry observability per queue

**Condition.** Today `_WORKER_SET_KEY = "kailash:workers"` (`distributed.py:61`) is a flat set. With multi-queue, an operator wants to know "how many workers are polling `slow`?".

**Consequence.** No way to dashboard per-queue worker capacity. Falls under `observability.md` § Mandatory Log Points 4 (state transitions, config loads MUST log which file/env var was used) — multi-queue worker registration without queue tags is invisible.

**Mitigation.** `_send_heartbeat` at `distributed.py:1020-1038` already records `worker_id`, `timestamp`, `active_tasks`, `concurrency`. Extend the heartbeat JSON to include `queues: {"fast": 8, "slow": 2}` (the per-queue concurrency map). Add a `get_status()` per-queue breakdown. Log line `worker.start` MUST emit at INFO with `queues=...` per `observability.md` Rule 4.

### 8. Queue name validation (injection / control-character safety)

**Condition.** `queue_name` ends up as a substring of a Redis list key (`kailash:tasks:pending:<queue_name>`) AND as a column value in `SQLTaskQueue` (`infrastructure/task_queue.py:243` — `VARCHAR DEFAULT 'default'`). A malicious or accidental queue name like `"fast\nDROP TABLE"` or `"fast:other_user_queue"` is structurally able to leak into the key namespace.

**Consequence.** Redis key collision / namespace squatting. Same failure-mode class as `dataflow-identifier-safety.md` (uncited but conceptually identical) — declared identifier strings MUST be sanitized at the validation gate.

**Mitigation.** A typed validator: `_validate_queue_name(name: str) -> str` raises `ValueError` if name doesn't match `^[a-zA-Z0-9_-]{1,64}$`. Called once at every entry point: `runtime.execute(queue=)`, `Worker(queues=)`, `scheduler.schedule_*(queue=)`. Tier 1 unit test enumerates passing + rejecting cases (control chars, colons, slashes, empty, > 64 chars).

### 9. Missing-queue / typo soft-fail behaviour

**Condition.** Producer calls `runtime.execute(wf, queue="fasst")` (typo). No worker is polling `fasst`.

**Consequence.** Task sits forever; user sees "queued" status. Mirrors failure point 1 but the cause is producer-side, not framework-side.

**Mitigation.** Producer-side: enqueue ALWAYS succeeds — Redis enqueue cannot validate worker presence atomically. But the producer MUST log `runtime.execute.start` at INFO with `queue=fasst, run_id=...` per `observability.md` Rule 1 so the user can grep their own logs. Worker-side: `Worker.start()` logs `worker.queues_registered queue_names=[...]` so the deployment topology is greppable. Documented operator workflow: `runtime.get_queue_status(queue="fasst")` returns `{"pending": N, "processing": 0, "workers": 0}` — `workers: 0` is the missing-queue tell.

### 10. Cross-SDK alignment (kailash-rs)

**Condition.** Per `cross-sdk-inspection.md` Rule 1, every issue found / fixed in one SDK MUST inspect the other. Multi-queue routing is a cross-cutting infrastructure primitive, not a Python idiom.

**Consequence.** If kailash-rs ships its own `DistributedRuntime` with a different queue-key format (`kailash::tasks::fast` vs `kailash:tasks:pending:fast`), users running both SDKs against the same Redis cannot share queues; cross-language dashboards drift.

**Mitigation.** This plan documents the canonical `_make_queue_key` shape (point 2 above). Per `cross-sdk-inspection.md` Rule 4, when the Rust SDK ships its equivalent, it MUST consume the SAME helper output and pin ≥3 byte-vectors against the Python output. Descriptive only in this plan — NO filing recommendation per repo-scope-discipline (we are in `kailash-py`, not orchestrating `kailash-rs`).

## API surface

Defaults preserve current single-queue semantics across every entry point. New named kwargs only.

### Producer: `DistributedRuntime`

```python
class DistributedRuntime(BaseRuntime):
    def __init__(
        self,
        redis_url: str = "",
        queue: Optional[TaskQueue] = None,
        visibility_timeout: int = 300,
        result_ttl: int = 3600,
        *,
        default_queue: str = "default",  # NEW: producer default for unqualified .execute() calls
        **kwargs,
    ): ...

    def execute(
        self,
        workflow: Workflow,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        queue: Optional[str] = None,  # NEW: routes to this queue; None → self._default_queue
    ) -> Tuple[Dict[str, Any], str]: ...
    # NOTE: existing `**kwargs` REMOVED — every kwarg this surface accepts must be
    # consumed (per zero-tolerance.md Rule 3c). If/when issue #912 lands soft_time_limit/
    # time_limit, those become explicit named kwargs the same way.
```

### Consumer: `Worker`

```python
QueueSpec = Union[int, Mapping[str, Any]]  # bare int = concurrency; mapping = full per-queue config

class Worker:
    def __init__(
        self,
        redis_url: str = "",
        queue: Optional[TaskQueue] = None,  # legacy single-queue path; mutually exclusive with queues=
        concurrency: int = 1,
        heartbeat_interval: int = 30,
        dead_worker_timeout: int = 90,
        worker_id: Optional[str] = None,
        runtime_factory: Optional[Callable] = None,
        *,
        queues: Optional[Mapping[str, QueueSpec]] = None,  # NEW: {"fast": 8, "slow": {"concurrency": 2, "visibility_timeout": 1800}}
    ): ...
```

Defaults preserve today's behavior: `Worker(redis_url=..., concurrency=N)` resolves to `queues={"default": N}` internally. Mutual-exclusion: passing BOTH `queue=<TaskQueue>` AND `queues=...` raises `ValueError` at construction (named-kwarg discipline; do NOT silently prefer one).

### Scheduler integration: `WorkflowScheduler.schedule_*`

```python
def schedule_cron(
    self, workflow_builder, cron_expression, name="",
    *, retry: Optional[RetrySpec] = None,
    queue: Optional[str] = None,  # NEW: persisted into job kwargs alongside _kailash_retry_spec
    **kwargs,
) -> str: ...
```

The internal `_compose_job_kwargs` at `scheduler.py:743-778` extends to thread `queue` via a sibling sentinel `_KAILASH_QUEUE_KWARG = "_kailash_queue"`. At fire-time, `_dispatch_to_queue` (`scheduler.py:1018-1104`) constructs a `Task(queue_name=queue or "default", ...)` — the existing `Task.queue_name` field at `dispatcher.py:127` is finally honored on the producer side. Composes with `RetrySpec` exactly as `RetrySpec` composes today: `RetrySpec` is in-process only and remains BLOCKED on `dispatch_via=` per `scheduler.py:768-774`; `queue=` is queue-dispatch only. The two are orthogonal.

### Lifecycle event payload extension

```python
@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    workflow_name: Optional[str]
    attempt: int
    max_attempts: int
    worker_id: str
    elapsed_ms: Optional[float] = None
    exception: Optional[BaseException] = None
    timestamp: float = field(default_factory=time.time)
    queue_name: Optional[str] = None  # NEW: routes lifecycle events to per-queue alerters
```

Additive default-None field on a frozen dataclass — backward compatible for every handler that destructures `event.task_id` etc.

### Helper module: `kailash.runtime._queue_keys`

```python
# NEW FILE: src/kailash/runtime/_queue_keys.py
_DEFAULT_QUEUE = "default"
_QUEUE_KEY_BASE = "kailash:tasks:pending"
_PROCESSING_KEY_BASE = "kailash:tasks:processing"

def make_queue_key(queue_name: str) -> str:
    """Producer/consumer-shared canonical Redis-list-key shape.

    Default queue resolves to the legacy unsuffixed key for back-compat
    (per failure-point #2). Named queues append `:<name>`.
    """
    validate_queue_name(queue_name)
    if queue_name == _DEFAULT_QUEUE:
        return _QUEUE_KEY_BASE  # "kailash:tasks:pending" — the existing live key
    return f"{_QUEUE_KEY_BASE}:{queue_name}"

def make_processing_key(queue_name: str) -> str: ...
def validate_queue_name(name: str) -> None: ...  # raises on invalid
```

`distributed.py` MUST import + use this helper (no inline string format); same for any future Rust SDK port (cross-SDK byte-shape parity per `cross-sdk-inspection.md` Rule 4).

## Implementation sketch

Sized per `autonomous-execution.md` Per-Session Capacity Budget. Three shards, each ≤ 500 LOC load-bearing logic, each ≤ 5–10 invariants, each describable in 3 sentences.

### Shard 1 — Helper module + producer plumbing (~300 LOC, 5 invariants)

**Files**: `src/kailash/runtime/_queue_keys.py` (new, ~80 LOC), `src/kailash/runtime/distributed.py` (TaskQueue + DistributedRuntime, ~150 LOC delta), `tests/unit/runtime/test_queue_keys.py` (new, ~80 LOC).

**Invariants**: (1) `make_queue_key("default")` byte-for-byte equals existing `_QUEUE_KEY`. (2) `validate_queue_name` rejects the documented bad set. (3) `DistributedRuntime.execute(queue=...)` routes via the helper. (4) `**kwargs` removed from `execute` signature; `queue=` is the single new explicit kwarg. (5) `TaskMessage` gains a `queue_name: str = "default"` field, additive on a non-frozen dataclass with default — JSON round-trip preserves it.

**Sentence**: "Add the canonical key helper, plumb queue name through TaskMessage and DistributedRuntime.execute, and remove the silent-drop `**kwargs`."

### Shard 2 — Worker multi-queue dequeue loop (~450 LOC, 8 invariants)

**Files**: `src/kailash/runtime/distributed.py` (Worker class, ~250 LOC delta), `tests/integration/runtime/test_worker_multi_queue.py` (new, ~200 LOC). Real Redis Tier 2.

**Invariants**: (1) `Worker(concurrency=N)` and `Worker(queues={"default": N})` are externally indistinguishable (legacy parity). (2) Per-queue dequeue tasks are independent asyncio tasks. (3) Per-queue semaphores enforce per-queue concurrency. (4) Per-queue visibility-timeout overrides honored. (5) Mutually-exclusive `queue=` and `queues=` raise at construction. (6) Slow-queue task MUST NOT block fast-queue dequeue (the acceptance-criteria #3 from issue #911). (7) Heartbeat JSON includes `queues={...}`. (8) Lifecycle hooks receive `event.queue_name`.

**Sentence**: "Replace the single-queue dequeue loop with one asyncio task per declared queue, each with its own semaphore and visibility timeout, and thread `queue_name` through every lifecycle event."

### Shard 3 — Scheduler dispatch composition + lifecycle event extension (~250 LOC, 5 invariants)

**Files**: `src/kailash/runtime/scheduler.py` (`schedule_cron/interval/once` + `_compose_job_kwargs` + `_dispatch_to_queue`, ~120 LOC delta), `src/kailash/runtime/lifecycle_events.py` (TaskEvent additive field, ~5 LOC), `tests/integration/runtime/test_scheduler_queue_routing.py` (new, ~150 LOC).

**Invariants**: (1) `schedule_cron(..., queue=)` persists queue into APScheduler job kwargs. (2) Fire-time dispatch reads queue from persisted kwargs (deterministic across scheduler instances per failure-point #5). (3) Composing `queue=` with `dispatch_via=None` raises `ValueError` (queue routing requires a dispatcher). (4) Composing `queue=` with `retry=RetrySpec(...)` raises `ValueError` (retry is in-process; queue is dispatcher-side; the pair is meaningless together — same shape as the existing `retry + dispatch_via` BLOCK at `scheduler.py:768-774`). (5) `TaskEvent.queue_name` is populated end-to-end through Worker → handler.

**Sentence**: "Persist queue routing as a scheduler kwarg via the same _kailash_\*\_kwarg sentinel pattern as retry, dispatch via the existing Task(queue_name=) field, and extend the lifecycle event payload."

**Total**: ~1,000 LOC across 3 shards, ~500 of which is tests. Within the 3-shard / single-session capacity per `autonomous-execution.md` Rule 1. Each shard has an executable feedback loop (pytest tier-2 with real Redis), so each may use up to 3–5× the base budget per Rule 3.

## Test plan

### Tier 1 (unit)

- `tests/unit/runtime/test_queue_keys.py`
  - `make_queue_key("default") == "kailash:tasks:pending"` (byte-pin for back-compat)
  - `make_queue_key("fast") == "kailash:tasks:pending:fast"`
  - `make_queue_key("slow") == "kailash:tasks:pending:slow"`
  - `make_processing_key("default") == "kailash:tasks:processing"`
  - `validate_queue_name` accepts: `"default"`, `"fast"`, `"slow_queue"`, `"a-b-c"`, `"x" * 64`
  - `validate_queue_name` rejects: `""`, `"x" * 65`, `"with space"`, `"with:colon"`, `"with/slash"`, `"with\nnewline"`, `"with\x00null"`

- `tests/unit/runtime/test_distributed_runtime_signature_invariant.py` (new structural invariant per `cross-sdk-inspection.md` Rule 3a)
  - `inspect.signature(DistributedRuntime.execute).parameters` contains `workflow, parameters, queue` and NO `**kwargs` — pin the surface so future refactors can't regrow the silent-drop.

### Tier 2 (integration, real Redis)

- `tests/integration/runtime/test_worker_multi_queue.py`
  - **Slow-queue does not block fast-queue (#911 acceptance criterion 3).** Spawn `Worker(queues={"fast": 4, "slow": 1})`. Enqueue 1 slow task that sleeps 30s + 100 fast tasks. Assert all 100 fast tasks complete within 5 wall-seconds while the slow task is still processing.
  - **Per-queue concurrency.** `Worker(queues={"fast": 2})` polls 5 fast-tasks; assert at most 2 are in `processing` state at any sample point.
  - **Per-queue visibility timeout.** `Worker(queues={"slow": {"concurrency": 1, "visibility_timeout": 5}})` polls a 30-sec workflow; assert the same task gets re-delivered to a sibling worker after the 5s timeout.
  - **Default queue back-compat.** `Worker(concurrency=N)` and a producer that previously ran against `_QUEUE_KEY = "kailash:tasks:pending"` interoperate byte-for-byte against `Worker(queues={"default": N})` — same Redis list key.
  - **Mutual-exclusion at construction.** `Worker(queue=tq, queues={"default": 1})` raises `ValueError`.

- `tests/integration/runtime/test_scheduler_queue_routing.py`
  - **Queue persists across scheduler restart.** Schedule a cron job with `queue="slow"`, kill the scheduler, restart from the same SQLite job-store, verify the next fire dispatches to the `slow` queue.
  - **Compose with lifecycle hooks.** Register `on_task_success(handler)`; enqueue via scheduler with `queue="slow"`; assert `handler` received `event.queue_name == "slow"`.
  - **Compose with retry: BLOCKED.** `scheduler.schedule_cron(..., retry=RetrySpec(...), queue="slow")` raises `ValueError` (the existing `retry + dispatch_via` BLOCK extends to `retry + queue`).

- `tests/integration/runtime/test_distributed_runtime_queue_kwarg.py`
  - Producer enqueue with `queue="fast"` arrives on `Worker(queues={"fast": 1})`.
  - Producer enqueue with default queue arrives on `Worker(concurrency=1)` (legacy).
  - Producer enqueue with unknown queue (no worker polling it) sits pending; `runtime.get_queue_status(queue="unknown")` returns `pending=1, workers=0`.

### Regression

- `tests/regression/test_911_default_queue_byte_compat.py` — pin the EXISTING `_QUEUE_KEY = "kailash:tasks:pending"` constant. If a future refactor changes the legacy key, every existing user's in-flight tasks orphan; this regression test loudly fails first.

## Cross-SDK alignment

Descriptive only — kailash-rs is a sibling repo and cross-repo work is BLOCKED per `repo-scope-discipline.md`.

The Rust SDK exposes its own `DistributedRuntime` and `Worker` types. Cross-SDK alignment per `cross-sdk-inspection.md` Rule 3 (EATP D6: matching semantics, independent implementation):

- The canonical Redis key shape `kailash:tasks:pending[:queue_name]` MUST be IDENTICAL byte-for-byte across both SDKs so a Python-side producer can enqueue and a Rust-side worker can dequeue (and vice versa). Per `cross-sdk-inspection.md` Rule 4, the test vectors (`make_queue_key("default")`, `make_queue_key("fast")`, `make_queue_key("a-b-c")`) MUST be pinned in both SDKs as raw byte strings, not abstract assertions.
- The `Worker(queues={...})` map shape is a Python idiom; the Rust equivalent (`HashMap<String, QueueSpec>` or a typed builder) is the same data model in Rust idiom.
- Lifecycle event extension `TaskEvent.queue_name: Option<String>` mirrors the Python additive default-None field.

A Rust-side implementer reading this plan reproduces the surface in Rust idiom; the byte-shape contract on Redis is what this plan pins. **No issue is filed against `kailash-rs` from this repo's session.**

## Open questions for the human

These need a gate decision before `/todos`:

1. **Helper module location.** New file `src/kailash/runtime/_queue_keys.py` or absorb into `src/kailash/utils/`? The helper is one tiny module either way; `runtime/` keeps it co-located with the consumer, `utils/` keeps it cross-package available. Recommendation: `runtime/` — both producer and consumer live in `runtime/`.
2. **`**kwargs`removal scope.** This plan removes`**kwargs`from`DistributedRuntime.execute`to close`zero-tolerance.md`Rule 3c silent-drop. The same`**kwargs`exists on`BaseRuntime.execute` (`runtime/base.py`) and other runtime subclasses. Should this plan close ALL silent-drop kwargs across `runtime/`(broader scope, +200 LOC, +1 shard), or scope strictly to`DistributedRuntime`? Recommendation: scope strictly — sibling-site sweep is a separate workstream that deserves its own analysis.
3. **`queues=` default-queue alias.** Should `Worker(concurrency=N)` ALWAYS forward to `queues={"default": N}` internally (single canonical code path), or keep the legacy single-queue branch as a separate code path? Recommendation: forward — one code path is structurally simpler and closes the parity invariant by construction.
4. **Per-queue-concurrency pre-emption.** When ALL queues' semaphores are saturated, should the worker stop polling Redis (back-pressure) or keep polling and immediately re-queue? Recommendation: stop polling — keeps Redis cheap and matches celery's behaviour.
5. **#912 sequencing**. If the human authoritatively wants #912 (soft/hard time limits) landed BEFORE #911, then #911's plan adds `soft_time_limit=` / `time_limit=` as named kwargs on `DistributedRuntime.execute` in the same shard rather than in #912's standalone shard. If #912 lands after #911, neither shard changes. Recommendation: human decides which lands first; this plan is correct under either ordering.

## Effort estimate

Per `autonomous-execution.md`, effort is in **autonomous execution cycles** (sessions), not human-days.

- **Shard 1** (helper + producer): 1 session, ~half-session if Shard 2 follows in parallel.
- **Shard 2** (Worker multi-queue): 1 session — this is the highest-invariant shard (per-queue tasks + per-queue semaphores + per-queue visibility timeouts + lifecycle events). Real-Redis tier-2 feedback loop multiplies capacity per Rule 3.
- **Shard 3** (scheduler composition): 1 session — small LOC delta but high cross-rule invariant count (RetrySpec composition, lifecycle hooks, persistence on resume).

**Total: 3 sessions** (one per shard). Sequential because Shard 2 + 3 both depend on Shard 1's helper module + `TaskMessage.queue_name` field. Worktree isolation NOT required (no Cargo lock contention; Python editable install) but recommended per `agents.md` MUST: Worktree Agents Commit Incremental Progress so each shard's progress is durable.

If the human elects to also fold #912 (soft/hard time limits) into the same plan, add **+1 session** (Shard 4). If the human elects to sweep the broader `**kwargs` silent-drop across all `BaseRuntime` subclasses, add **+1 session** (Shard 5).

Gate-level reviews (`reviewer` + `security-reviewer` per `agents.md` § Quality Gates) run as parallel background agents at the end of `/implement` and do NOT count toward shard sessions — they cost near-zero parent context.
