# Issue #912: per-task soft/hard time limits

## Brief summary

Issue #912 asks for celery-style `soft_time_limit` (warn, raise a catchable
exception inside the running workflow) and `time_limit` (hard kill, requeue)
primitives at two execution surfaces: `DistributedRuntime.execute(...)` (the
producer side) and `Worker._execute_workflow_sync(...)` (the consumer side).
The brief comment on the issue notes #912 is a sibling of #910 (RetrySpec) —
both are per-task execution-control primitives — and asks for the two
primitives to interact correctly: when a task hits a soft limit and the
runtime raises `SoftTimeLimitExceeded`, the retry classifier MUST treat it as
retryable (or not) per the producer's `RetrySpec.retry_on` decision, not via
a hidden hard-coded branch.

In addition, the brief implicitly asks (per the session-notes line 10 + the
`zero-tolerance.md` Rule 3c framing) to replace
`DistributedRuntime.execute(workflow, parameters=None, **kwargs)` — which
silently drops every kwarg today — with explicit typed kwargs. The first two
new typed kwargs are `soft_time_limit` and `time_limit`; #911 (multi-queue)
will reuse the cleaned signature in its turn.

## Brief corrections

Re-grep / re-verification of every factual claim in the issue body and its
sibling references against `2210f724` (current `main`):

| Brief claim                                                                              | Verdict                                                                                                                                                                                                                                                                                            | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DistributedRuntime.execute(workflow, parameters=None, **kwargs)` silently drops kwargs. | TRUE.                                                                                                                                                                                                                                                                                              | `src/kailash/runtime/distributed.py:502-544` — body uses only `workflow` and `parameters`; `**kwargs` is captured but never read in the function body.                                                                                                                                                                                                                                                                                                                                                                                                     |
| `Worker._execute_workflow_sync` is the worker-side execution path.                       | TRUE.                                                                                                                                                                                                                                                                                              | `src/kailash/runtime/distributed.py:977-996` — sync helper that builds and executes the workflow in a thread-pool executor.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `WorkflowScheduler` job-execution path is the in-process retry loop.                     | TRUE.                                                                                                                                                                                                                                                                                              | `src/kailash/runtime/scheduler.py:780-957` — `_execute_workflow` retry loop wraps `runtime.execute(workflow, **kwargs)` at line 858.                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Brief refers to `Worker._execute_workflow_sync` (not `_execute_task`).                   | TRUE.                                                                                                                                                                                                                                                                                              | The synthetic blocking call is at `distributed.py:880`; `_execute_task` (line 839) is the `asyncio.Task` body that wraps it. The wrap point for hard kills (cancellation of the asyncio task) is `_execute_task`; the wrap point for soft limits (raising INSIDE the workflow thread) is around `_execute_workflow_sync`. Both wrap points exist; the brief named one.                                                                                                                                                                                     |
| Soft-limit exception type lives at `kailash.errors.SoftTimeLimitExceeded`.               | PARTIALLY UNCLEAR. The repo does NOT currently expose a `kailash.errors` namespace (`grep -rn "from kailash.errors" src/` returns zero hits). The canonical exception home is `kailash.sdk_exceptions` (e.g. `WorkflowCancelledError` at `sdk_exceptions.py:406`, `RuntimeException` at line 185). | `src/kailash/sdk_exceptions.py:185,406`. The decision is whether to (a) add `SoftTimeLimitExceeded` + `HardTimeLimitExceeded` to `sdk_exceptions.py` and re-export under a NEW `kailash.errors` shim that lazy-imports from `sdk_exceptions`, or (b) just add them to `sdk_exceptions.py` and adjust the brief's import path. The plan below picks (a) with a `kailash.errors` namespace re-exporting from `sdk_exceptions.py` so the brief's example code works verbatim AND the module-discovery surface stays aligned with the existing exception home. |
| #910 (RetrySpec) and #914 (lifecycle hooks) just merged.                                 | TRUE.                                                                                                                                                                                                                                                                                              | `git log --oneline -3 origin/main` shows `dc182dcc` (#910 round-2), `23565d7b` (#910 round-1), `3bd3445e` (#910 main), and PR #915 (#914) merged immediately prior.                                                                                                                                                                                                                                                                                                                                                                                        |
| `_execute_workflow` is the same wrap point #912 touches as #910/#914.                    | TRUE.                                                                                                                                                                                                                                                                                              | The retry loop body at `scheduler.py:838-925` is exactly where the soft/hard timer needs to wrap each attempt. Collision risk against #916 was called out in `.session-notes:18-20` and is now resolved (#916 merged).                                                                                                                                                                                                                                                                                                                                     |
| Existing `CancellationToken` handles cooperative cancellation between nodes.             | TRUE.                                                                                                                                                                                                                                                                                              | `src/kailash/runtime/cancellation.py:31-135` — token is checked between node executions; the existing `WorkflowCancelledError` path is the natural model the soft-limit path should imitate (cooperative raise inside the runtime).                                                                                                                                                                                                                                                                                                                        |
| #911 reuses #912's signature cleanup.                                                    | TRUE per session-notes line 6.                                                                                                                                                                                                                                                                     | #911's brief (`gh issue view 911`) proposes `DistributedRuntime.execute(workflow, queue: str = "default")`. That third typed kwarg is exactly the next item after `soft_time_limit` / `time_limit` on the signature.                                                                                                                                                                                                                                                                                                                                       |

No FALSE claims; one UNCLEAR (exception module path) resolved into the plan.

## Failure-point analysis

1. **Timeout-during-retry interaction.** Condition: a scheduled job has
   `RetrySpec(max_retries=3)` AND `soft_time_limit=300`. Attempt 1 raises
   `SoftTimeLimitExceeded` at t=300s. Consequence (today, naive
   implementation): the retry classifier doesn't know about the new
   exception type; either every soft-limit raise becomes a retry (defeating
   `dont_retry_on`), or none do (defeating `retry_on=(SoftTimeLimitExceeded,)`).
   Mitigation: `SoftTimeLimitExceeded` MUST be a normal `Exception` subclass
   that `RetrySpec.is_retryable()` evaluates symmetrically to any other
   exception. Operators who want "soft-limit triggers retry" pass
   `retry_on=(SoftTimeLimitExceeded, ConnectionError)`; operators who want
   "soft-limit means give up" pass
   `dont_retry_on=(SoftTimeLimitExceeded,)`. Per `zero-tolerance.md` Rule 3c
   the new kwargs MUST be consumed in every branch they reach.

2. **Hard-limit cancellation vs `CancellationToken` semantics.** Condition:
   a hard limit fires while the workflow is mid-node. Consequence:
   APScheduler runs in a single process; cancelling the asyncio task that
   owns the runtime call may leave node-side resources (DB connections, file
   handles) in an inconsistent state. Mitigation: hard limit MUST go through
   the existing `CancellationToken` path — set the token, give the runtime a
   small grace window (config: `hard_time_limit_grace_seconds`, default 5s)
   to observe the cancellation between nodes, then raise
   `HardTimeLimitExceeded` from the wrapper. NEVER `SIGTERM` the worker
   process from in-process scheduler — only the queue path's worker
   `Worker._execute_task` may take that route (and only by setting
   `task.attempts < task.max_attempts` so the requeue path activates), per
   the brief's "task is requeued and a fresh worker picks it up" line. The
   wrapper MUST propagate `WorkflowCancelledError` cause-chain into
   `HardTimeLimitExceeded` so triage gets both layers.

3. **Async vs sync runtime divergence.** Condition: scheduler runs against a
   `LocalRuntime` (sync `runtime.execute(...)` at `scheduler.py:858`) vs an
   `AsyncLocalRuntime` (`await runtime.execute_workflow_async(...)`).
   Consequence: a soft-limit timer that uses `signal.SIGALRM` works in main
   thread sync code only — fails for the worker's executor-thread sync path
   AND for every async-runtime path. Mitigation: the timer MUST be
   thread-/loop-safe, NOT signal-based. Implementation: a background
   `asyncio.create_task` (async path) OR a `threading.Timer` (sync path) that
   calls `cancellation_token.cancel(reason="soft_time_limit_exceeded")` at
   the deadline. The runtime's existing inter-node `token.check()` raises
   `WorkflowCancelledError`; the scheduler wrapper catches it and re-raises
   as `SoftTimeLimitExceeded` with the original as `__cause__`. Same
   plumbing for hard limit + `HardTimeLimitExceeded`. Per
   `patterns.md` § "Paired Public Surface" the `soft_time_limit`/`time_limit`
   kwargs MUST be accepted at every entry point that reaches the wrap
   (sync + async + queue) — no "sync supported, async coming later" split.

4. **Persistence on resume — hard limits across restart.** Condition: the
   scheduler is using `SQLiteJobStore`; the process crashes mid-soft-limit
   timer. Consequence: on resume, the timer is gone; the workflow runs
   without time limits even though the schedule was registered with them.
   Mitigation: timer state is in-memory and rebuilt at fire time, not at
   schedule time. The `soft_time_limit` / `time_limit` values themselves are
   persisted as part of the APScheduler `kwargs=` dict (same pattern as
   `_RETRY_SPEC_KWARG` for #910 — see `scheduler.py:71` and the
   `_compose_job_kwargs` helper at `scheduler.py:744-778`). When APScheduler
   re-fires a missed job after restart, the kwargs are replayed from the
   jobstore and the timer is freshly armed. No durable timer infra needed.

5. **Cross-SDK alignment with kailash-rs.** Condition: kailash-rs already
   has or will have an equivalent `Worker` + scheduler surface. Consequence:
   if the Python SDK adds `soft_time_limit` and the Rust SDK adds
   `soft_timeout_secs`, cross-SDK forensic correlation breaks (different
   field names + different exception type names). Mitigation: keyword names
   in this plan match celery (`soft_time_limit`, `time_limit`) which is the
   industry standard, and the exception names follow celery's
   `SoftTimeLimitExceeded` precedent. Cross-SDK alignment work is descriptive
   only per `repo-scope-discipline.md` — no filing recommendation in this
   session. (See § Cross-SDK alignment below.)

6. **Soft-limit firing inside a non-yielding C extension.** Condition: a
   `PythonCodeNode` runs a tight numpy loop or a `time.sleep(3600)` (the
   brief's repro). Consequence: the inter-node `token.check()` is never
   reached; the soft limit timer fires, sets the token, but the workflow
   doesn't observe it until the current node returns. Mitigation:
   `SoftTimeLimitExceeded` IS the cooperative half — the brief explicitly
   says "catchable exception in the running workflow" — so a node that never
   yields control simply does not see the soft limit until it exits.
   `time_limit` (hard) is the backstop; at hard-limit deadline +
   `hard_time_limit_grace_seconds` the wrapper raises
   `HardTimeLimitExceeded` regardless of node yield state. This is
   functionally equivalent to celery's "soft = cooperative, hard = process
   kill" semantics translated to Python's coop-cancel idiom. Document the
   limitation in the docstring.

7. **`DistributedRuntime.execute` enqueues — the timer is enforced where?**
   Condition: producer side calls
   `runtime.execute(wf, soft_time_limit=300, time_limit=600)`; the workflow
   gets serialized + enqueued to Redis; a worker dequeues it 30 minutes
   later. Consequence: if the timer started at producer side, the budget is
   already blown by the time the worker picks it up. Mitigation: the producer
   serializes the LIMITS into the `TaskMessage.parameters` (or a new
   dedicated `TaskMessage.execution_limits` field) — NOT the deadline
   timestamp. The worker's `_execute_task` arms the timer at dequeue time so
   the budget covers execution wall-clock, not queue-wait wall-clock. (Celery
   does the same: `time_limit` is per-execution, not per-submission.)
   Additive new field on `TaskMessage` keeps the JSON wire format
   forward-compatible — workers running an older SDK ignore the field.

8. **Worker-default vs producer-override semantics.** Condition: the brief's
   acceptance criterion #2 says "`Worker` constructor accepts default soft /
   hard limits applied to all dequeued tasks unless overridden by the
   producer." Consequence: the precedence rule MUST be unambiguous —
   per-task value (from `TaskMessage`) wins; falls through to
   `Worker(default_soft_time_limit=, default_time_limit=)`; falls through to
   `None` (no limit). Implementation: `Worker.__init__` adds
   `default_soft_time_limit`, `default_time_limit`,
   `hard_time_limit_grace_seconds` kwargs; `_execute_task` reads the
   per-task value first and falls back to the default. Same precedence
   pattern as `TaskMessage.visibility_timeout` vs
   `TaskQueue.default_visibility_timeout` at `distributed.py:223-224`.

9. **Signal-based fallback BLOCKED.** Condition: a future agent considers
   wrapping `_execute_workflow_sync` with `signal.SIGALRM` or
   `multiprocessing.Process(target=..., timeout=...)`. Consequence: SIGALRM
   only works on the main thread on Unix; multiprocessing-Process double-pays
   the workflow construction cost AND breaks `LocalRuntime`'s shared state.
   Mitigation: the implementation MUST use `CancellationToken` +
   `threading.Timer` / `asyncio.create_task`. Document this in the
   implementation comment (BLOCKED rationalization) so a future Round-2
   /redteam doesn't reopen.

10. **Soft-limit and hard-limit interaction.** Condition: operator passes
    `soft_time_limit=600`, `time_limit=300` (hard < soft, nonsensical).
    Consequence (today, naive): both timers fire; the order of raising is
    ambiguous. Mitigation: the wrapper validates at entry — if
    `time_limit is not None and soft_time_limit is not None and
soft_time_limit >= time_limit`, raise `ValueError` with a typed message.
    Same validation pattern as `RetrySpec.__post_init__` at
    `scheduler.py:140-181`.

## API surface

### New typed kwargs

`DistributedRuntime.execute` (currently the silent-drop offender at
`distributed.py:502-544`):

```python
def execute(
    self,
    workflow: Workflow,
    parameters: Optional[Dict[str, Any]] = None,
    *,
    soft_time_limit: Optional[float] = None,  # seconds; None = no soft limit
    time_limit: Optional[float] = None,        # seconds; None = no hard limit
) -> Tuple[Dict[str, Any], str]:
```

The `**kwargs` is removed. Callers that were passing arbitrary kwargs (today
silently dropped) get a `TypeError` — this is the desired
`zero-tolerance.md` Rule 3c outcome. #911's `queue=` kwarg lands on top of
this signature in the next workstream.

`Worker.__init__` (currently at `distributed.py:614-644`):

```python
def __init__(
    self,
    redis_url: str = "",
    queue: Optional[TaskQueue] = None,
    concurrency: int = 1,
    heartbeat_interval: int = 30,
    dead_worker_timeout: int = 90,
    worker_id: Optional[str] = None,
    runtime_factory: Optional[Callable] = None,
    *,
    default_soft_time_limit: Optional[float] = None,
    default_time_limit: Optional[float] = None,
    hard_time_limit_grace_seconds: float = 5.0,
):
```

`WorkflowScheduler.schedule_cron` / `schedule_interval` / `schedule_once`
(currently at `scheduler.py:499`, `579`, `642`) — additive `*,
soft_time_limit: Optional[float] = None, time_limit: Optional[float] = None`
on each, plumbed through `_compose_job_kwargs` next to `_RETRY_SPEC_KWARG`
into `_execute_workflow`.

### New exceptions

In `kailash/sdk_exceptions.py`:

```python
class SoftTimeLimitExceeded(RuntimeException):
    """Raised inside a running workflow when soft_time_limit elapses.
    Catchable by user code; allows graceful wind-down before hard limit."""

class HardTimeLimitExceeded(RuntimeException):
    """Raised by the runtime wrapper when time_limit elapses. The runtime
    has already cancelled the workflow via CancellationToken; this is the
    final propagating exception. NOT catchable by node-level user code."""
```

In a NEW `kailash/errors.py` module (re-export shim per `framework-first.md`
§ "Drive The Data, Not The Dispatch" — keep one canonical home, expose at
the convenient path the brief expects):

```python
from kailash.sdk_exceptions import (
    SoftTimeLimitExceeded,
    HardTimeLimitExceeded,
    WorkflowCancelledError,  # for triage parity
)

__all__ = [
    "SoftTimeLimitExceeded",
    "HardTimeLimitExceeded",
    "WorkflowCancelledError",
]
```

This honors `orphan-detection.md` Rule 6 (every public module-scope import
appears in `__all__`) and `dependencies.md` § "Declared = Imported".

### Soft vs hard semantics

| Aspect      | Soft (`soft_time_limit`)                                                                                                                                                                                                                     | Hard (`time_limit`)                                                                                                                                                                                                                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mechanism   | Background `threading.Timer` (sync) / `asyncio.create_task` (async) sets `CancellationToken`. Runtime observes between nodes and raises. Wrapper catches `WorkflowCancelledError` and re-raises as `SoftTimeLimitExceeded` with `__cause__`. | Same mechanism + a `hard_time_limit_grace_seconds` (default 5s) wait. After grace, wrapper raises `HardTimeLimitExceeded` UNCONDITIONALLY (does not wait for the runtime to observe the token). Worker-path: `Worker._execute_task` interprets `HardTimeLimitExceeded` as "requeue if attempts remain" per the brief. |
| User-facing | Catchable; user code may `try/except SoftTimeLimitExceeded:` and clean up.                                                                                                                                                                   | Effectively non-catchable inside node code (the wrapper raises after the runtime call returns). Surfaces to `Worker._execute_task` for requeue OR to `WorkflowScheduler._execute_workflow` for retry-classifier.                                                                                                      |
| Default     | `None` (no limit)                                                                                                                                                                                                                            | `None` (no limit)                                                                                                                                                                                                                                                                                                     |
| Validation  | Must be `> 0` and `< time_limit` if both set.                                                                                                                                                                                                | Must be `> 0`.                                                                                                                                                                                                                                                                                                        |

### Default behavior

`None` means "no limit"; the brief gives no guidance on a workspace-wide
default and `autonomous-execution.md` per-session-budget reasoning suggests
zero default to avoid surprising existing schedules. Operators opt in.

## Implementation sketch

Surface area + sequencing:

1. **Shard 1 — exceptions + errors namespace** (boilerplate, ~40 LOC, 1
   invariant: `kailash.errors` re-export resolves; same kind as `__all__`).
   - `src/kailash/sdk_exceptions.py`: add `SoftTimeLimitExceeded`,
     `HardTimeLimitExceeded` subclassing `RuntimeException`.
   - `src/kailash/errors.py`: NEW file, re-exports.
   - Update top-level `src/kailash/__init__.py` if it currently re-exports
     from `sdk_exceptions` (verify).

2. **Shard 2 — `_execute_with_time_limits` wrapper helper** (load-bearing,
   ~120 LOC, 5 invariants: token cancel, async/sync dispatch, grace period,
   exception type mapping, no-signal-based path). Lives in a new
   `src/kailash/runtime/_time_limits.py`. Two callables:
   - `def arm_time_limits(token, *, soft_time_limit, time_limit, grace) -> Cancellable`
     — sync path; returns an object whose `.disarm()` cancels both timers
     in the `finally` block.
   - `async def arm_time_limits_async(token, *, soft_time_limit, time_limit, grace) -> Cancellable`
     — async path; uses `asyncio.create_task` of `asyncio.sleep`.
     Both share a `_TimeLimitClassifier(soft_deadline, hard_deadline) -> Type[Exception]`
     that converts a `WorkflowCancelledError` raised by the runtime back into
     `SoftTimeLimitExceeded` / `HardTimeLimitExceeded` based on which deadline
     was reached first (compare `time.monotonic()` against stored deadlines).

3. **Shard 3 — `WorkflowScheduler` plumbing** (load-bearing, ~150 LOC, 6
   invariants: signature parity across 3 schedule\_\* methods, kwargs threading
   per `_RETRY_SPEC_KWARG` precedent, in-process retry-loop interaction with
   exception classifier, queue-dispatch path forwards the limits to
   `Task.kwargs`, retry-classifier sees soft-limit as a normal exception,
   validation at entry).
   - `_TIME_LIMIT_KWARG = "_kailash_time_limits"` constant alongside
     `_RETRY_SPEC_KWARG` at `scheduler.py:71`.
   - `_compose_job_kwargs` (line 744) gains `soft_time_limit` /
     `time_limit` parameters; threads a tuple `(soft, hard)` under the
     internal key.
   - `_execute_workflow` (line 780) pops the internal key, arms timers
     around `runtime.execute(...)` at line 858 inside the existing retry
     loop. Each retry attempt re-arms a fresh timer (no carry-over).
   - `schedule_cron`, `schedule_interval`, `schedule_once` accept the new
     kwargs and call the updated `_compose_job_kwargs`.

4. **Shard 4 — `DistributedRuntime` + `Worker` plumbing** (load-bearing,
   ~180 LOC, 7 invariants: producer-side sets execution_limits on
   `TaskMessage`, wire format JSON forward-compat,
   `Worker._execute_task` arms timers at dequeue, default fallback chain,
   `HardTimeLimitExceeded` triggers requeue not dead-letter, lifecycle hook
   `on_task_retry` fires on hard-limit-with-attempts-remaining,
   `on_task_failure` fires on dead-letter).
   - `TaskMessage` gains `execution_limits: Optional[Dict[str, float]] =
None` (`{"soft": 300.0, "hard": 600.0}` shape — dict so the wire
     format is one new optional field rather than two). `to_json` /
     `from_json` updates accordingly.
   - `DistributedRuntime.execute` typed-kwargs signature (signature
     replacement, see § API surface).
   - `Worker.__init__` adds the three new kwargs.
   - `Worker._execute_task` (line 839) computes effective limits =
     per-task limits OR worker defaults, arms timers around the
     `run_in_executor(_execute_workflow_sync)` call at line 878, catches
     `HardTimeLimitExceeded`, treats it as a retryable failure (existing
     `nack` path requeues if `attempts < max_attempts`).

5. **Shard 5 — tests** (Tier 2 integration + structural invariant; ~250
   LOC; tests sub-package-local). See § Test plan.

Total: ~740 LOC across 4 production files + 2 new files (errors.py,
\_time_limits.py) + 5 test files. Per `autonomous-execution.md` § Per-Session
Capacity Budget, each shard fits the ≤500 LOC / ≤5–10 invariants /
≤3–4 call-graph hops bound. No shard exceeds the budget.

## Test plan

Tier 2 integration (real APScheduler in-memory job store + real
`LocalRuntime`; per `testing.md` Tier 2 contract; per
`facade-manager-detection.md` Rule 1 Manager-shape Tier-2 wiring):

1. **`tests/integration/test_scheduler_time_limits.py`**
   - `test_soft_time_limit_raises_in_workflow`: schedule a workflow whose
     PythonCodeNode sleeps 5s; `soft_time_limit=2`; assert
     `SoftTimeLimitExceeded` propagates out of `_execute_workflow` (caught
     via the APScheduler error listener — same wiring as RetrySpec tests at
     `tests/regression/test_scheduler_retry_primitives.py`).
   - `test_hard_time_limit_raises_after_grace`: same workflow,
     `time_limit=2`, `hard_time_limit_grace_seconds=1`; assert
     `HardTimeLimitExceeded` raised at ~3s wall-clock.
   - `test_soft_then_hard_propagation`: `soft_time_limit=2, time_limit=4`;
     assert soft fires first; if user catches it and continues sleeping,
     hard fires at 4+grace.
   - `test_retryspec_classifies_soft_as_retryable_on_demand`: combine
     `retry=RetrySpec(retry_on=(SoftTimeLimitExceeded,), max_retries=2)`
     with `soft_time_limit=2`; assert the workflow is retried on soft
     limit, NOT on hard.
   - `test_retryspec_dontretry_on_soft_overrides`: same but
     `dont_retry_on=(SoftTimeLimitExceeded,)`; assert no retry.

2. **`tests/integration/test_distributed_time_limits.py`** (real Redis
   per the existing `tests/integration/test_distributed_*` pattern):
   - `test_producer_time_limits_serialize_to_taskmessage`: enqueue with
     `soft_time_limit=300, time_limit=600`; dequeue raw via
     `TaskQueue.dequeue`; assert `task.execution_limits ==
{"soft": 300.0, "hard": 600.0}`.
   - `test_worker_arms_timers_at_dequeue_not_at_enqueue`: enqueue with
     `time_limit=2`; sleep 3s before starting the worker; assert the worker
     still gets the full 2s budget (NOT 0s, which would prove producer-side
     timing).
   - `test_hard_limit_triggers_requeue`: workflow that sleeps 10s;
     `time_limit=2`, `max_attempts=3`; assert task is processed by 2
     workers (consumed twice from the queue) before dead-lettering on
     attempt 3.
   - `test_worker_default_overridden_by_per_task`: `Worker(default_time_limit=10)`;
     enqueue with `time_limit=2`; assert effective limit is 2s, not 10s.
   - `test_lifecycle_hooks_fire_on_hard_limit`: register
     `on_task_retry` + `on_task_failure`; assert `on_task_retry` fires on
     hard-limit retries 1-2, `on_task_failure` fires on the dead-letter
     after attempt 3 (proves cross-feature interaction with #914).

3. **`tests/regression/test_issue_912_signature_invariants.py`**
   (per `cross-sdk-inspection.md` Rule 3a — pin the signature so a future
   refactor cannot silently re-introduce `**kwargs`):

   ```python
   def test_distributed_runtime_execute_signature():
       """Pin DistributedRuntime.execute(...) typed kwargs surface.
       If this fails, the cross-SDK kailash-rs equivalent surface MUST be
       re-audited per cross-sdk-inspection.md Rule 3a."""
       import inspect
       from kailash.runtime.distributed import DistributedRuntime
       sig = inspect.signature(DistributedRuntime.execute)
       params = list(sig.parameters.values())
       names = [p.name for p in params]
       assert names == [
           "self", "workflow", "parameters",
           "soft_time_limit", "time_limit",
       ], f"signature drifted: {sig}"
       # No VAR_KEYWORD (the **kwargs that #912 removes)
       assert not any(
           p.kind is inspect.Parameter.VAR_KEYWORD for p in params
       ), f"DistributedRuntime.execute regrew **kwargs: {sig}"

   def test_worker_init_default_time_limit_kwargs():
       """Pin Worker default_*_time_limit + grace kwargs."""
       import inspect
       from kailash.runtime.distributed import Worker
       sig = inspect.signature(Worker.__init__)
       names = list(sig.parameters)
       for required in (
           "default_soft_time_limit", "default_time_limit",
           "hard_time_limit_grace_seconds",
       ):
           assert required in names, (
               f"Worker.__init__ missing {required}: {sig}"
           )

   def test_kailash_errors_namespace_exposes_soft_and_hard():
       """The brief documents kailash.errors.SoftTimeLimitExceeded as
       the public import path. Pin it so a future move back to
       sdk_exceptions does not break user code."""
       from kailash.errors import (
           SoftTimeLimitExceeded, HardTimeLimitExceeded,
       )
       from kailash.sdk_exceptions import RuntimeException
       assert issubclass(SoftTimeLimitExceeded, RuntimeException)
       assert issubclass(HardTimeLimitExceeded, RuntimeException)
   ```

All Tier-2 tests use the established
`tests/regression/test_scheduler_retry_primitives.py` `tmp_path` + tempfile
counter pattern (per `.session-notes:25` — `PythonCodeNode` sandbox blocks
`tests.*` imports).

## Cross-SDK alignment

`kailash-rs` has its own scheduler + worker surface. The cross-SDK
equivalent of #912 would be:

- An `enum DiagnosticKind` style typed result for soft vs hard timeout
  (Rust's structural exhaustiveness guards the dispatch in a way Python
  lacks per `zero-tolerance.md` Rule 2 fake-dispatch evidence).
- A `WorkerConfig { default_soft_time_limit: Option<Duration>,
default_time_limit: Option<Duration>, hard_time_limit_grace: Duration }`.
- The same producer-side / dequeue-side timing distinction (#7 above);
  Rust's `tokio::time::timeout` is the natural primitive.
- Exception names: Rust does not use exceptions; the surface is
  `Result<_, WorkflowError>` with `WorkflowError::SoftTimeLimitExceeded`
  and `WorkflowError::HardTimeLimitExceeded` variants for symmetry.

Per `repo-scope-discipline.md`, this is descriptive-only. NO filing
recommendation; if the user wants the cross-SDK issue filed, they open
Claude Code in `kailash-rs` and decide there. Per
`cross-sdk-inspection.md` Rule 3a, the structural-invariant test in
§ Test plan #3 is the local defense — if a future Python refactor grows
the signature toward a Rust-shape `**kwargs` accept-all, the test fails
loudly and forces a re-audit.

## Open questions for the human

These need a gate before `/todos`:

1. **Default behavior on workspace-wide level.** Should
   `default_soft_time_limit` / `default_time_limit` be configurable at
   `WorkflowScheduler.__init__` AND at `Worker.__init__`, or only at the
   `Worker`? The brief specifies `Worker`; adding the scheduler symmetry
   is cheap (~20 LOC) but expands the API surface. Recommendation: add at
   both (mirrors celery's `task_soft_time_limit` global + per-task
   override). Cost: 0 sessions either way, structural-only.

2. **`kailash.errors` namespace.** The brief documents the import path as
   `kailash.errors.SoftTimeLimitExceeded`. The plan creates a new
   `kailash/errors.py` re-export module pointing to `sdk_exceptions.py`.
   Alternative: keep callers on `kailash.sdk_exceptions` (one canonical
   path; no namespace duplication). Recommendation: create
   `kailash.errors` because (a) the brief's example code uses it, (b)
   `errors` is the more discoverable name, (c) the re-export shim
   (~10 LOC) keeps `sdk_exceptions.py` as the single home. Cost: 0
   sessions; one extra file.

3. **Hard-limit behavior in `WorkflowScheduler` (not `Worker`).** The
   brief's repro is a `DistributedRuntime` example — there the requeue
   semantics are clean (the worker's `_execute_task` nack path). For the
   in-process scheduler path (`scheduler.py:_execute_workflow`), there
   IS no requeue — the job is registered, fires on schedule, retries via
   `RetrySpec` if configured. Question: should `HardTimeLimitExceeded` in
   the scheduler path (a) propagate through APScheduler's job-error
   listener (matching today's exception path; user opts into RetrySpec
   for retries) or (b) silently consume the exception and fire the next
   scheduled instance (matching celery's hard-kill-on-task-but-job-keeps-running
   semantic for cron)? Recommendation: (a). Rationale: `RetrySpec`
   already exists and is the typed retry primitive; HardTimeLimitExceeded
   should compose with it cleanly, not bypass it. Cost: 0 sessions; a
   docstring decision.

4. **Soft-limit timer cost.** A `threading.Timer` per attempt costs ~one
   thread; for high-throughput workers (concurrency=64), 64 Timer threads
   feels heavy. Alternative: one `asyncio` background task per worker
   that scans for elapsed deadlines on a tick. Recommendation: timer per
   task is fine for v1 (matches celery's per-task sigalrm); revisit if
   profiling shows thread contention. Cost: deferred optimization, no
   /todos impact.

## Effort estimate

Per `autonomous-execution.md` § Autonomous Execution Cycles:

| Shard                                                                       | Cycles            | Notes                                                                                              |
| --------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------- |
| 1 (exceptions + namespace)                                                  | 0.1               | Boilerplate; can land in same shard as #2.                                                         |
| 2 (`_time_limits.py` wrapper)                                               | 0.5               | Load-bearing async/sync dispatch; needs careful test of grace-window edge cases.                   |
| 3 (`WorkflowScheduler` plumbing)                                            | 0.4               | Mechanical extension of the existing `_RETRY_SPEC_KWARG` pattern.                                  |
| 4 (`DistributedRuntime` + `Worker` plumbing)                                | 0.6               | Wire-format change on `TaskMessage` is the highest-risk surface; requires forward-compat thinking. |
| 5 (tests Tier 2 + invariant)                                                | 0.4               | Pattern-matched on existing scheduler-retry + lifecycle-hook tests.                                |
| /redteam round-1 (orphan + facade-manager + signature sweeps)               | 0.3               | Per agents.md MUST gate.                                                                           |
| /redteam round-2 (closure parity if round-1 produces FORWARDED rows)        | 0.2               | Bash+Read specialist required per agents.md.                                                       |
| /codify (rule extracts if any new BLOCKED-rationalization patterns surface) | 0.1               | Only if the timer-thread alternative is rejected with new evidence.                                |
| **Total**                                                                   | **~2.5 sessions** | Well under the 10x-throughput equivalent of "33–50 human-days = 3–5 days parallel".                |

Single autonomous session can complete shards 1+2+3 (in-process scheduler
path); a follow-up session completes shards 4+5 + redteam. Parallelization
is possible (shards 3 and 4 are independent given the wrapper helper from
shard 2 lands first), reducing wall-clock to ~1.5 sessions if
worktree-isolated per `agents.md` § "Worktree Isolation".

The plan stays inside the `~500 LOC load-bearing / ≤5–10 invariants`
budget per shard. No shard requires sub-shard splitting.
