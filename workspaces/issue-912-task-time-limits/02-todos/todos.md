# Issue #912 /todos: per-task soft/hard time limits

Phase: 02 (todos) — written 2026-05-09. Read-only phase. Awaits human gate.
Branch base: `main` @ `d5d84dbd` (post-#915 merge).
Architecture plan: `workspaces/issue-912-task-time-limits/01-analyze/architecture-plan.md`.

## Root-cause decisions (user-approved 2026-05-09)

The /analyze gate surfaced 4 root-cause questions. The user resolved all 4
before /todos. The decisions are baked in below; /implement does NOT re-debate
them. Restated verbatim from the approval message:

**RC1 — `**kwargs`removal scope: BROAD sweep across all`BaseRuntime`subclasses.** Grep`def execute(.\*\*\*kwargs)`across`src/kailash/runtime/`.
EVERY hit (LocalRuntime, AsyncLocalRuntime, DistributedRuntime, DockerRuntime,
etc.) gets typed kwargs in this issue's Shard 1. If sweep exceeds 500 LOC /
10 invariants, split into Shard 0 (BaseRuntime sweep, typing convention) +
Shard 1 (time-limit kwargs on cleaned surface). Per `cross-sdk-inspection.md`Rule 3a, EVERY runtime's typed signature gets a structural-invariant test
pinning the signature so a future refactor cannot silently re-grow`\*\*kwargs`.

**RC2 — `kailash.errors` namespace: NO new module, NO shim.** Add
`SoftTimeLimitExceeded` and `HardTimeLimitExceeded` directly to
`src/kailash/sdk_exceptions.py`. Do NOT create `src/kailash/errors.py`
re-export shim (`feedback_no_shims.md` blocks). The brief example will be
updated to `from kailash.sdk_exceptions import SoftTimeLimitExceeded`. The
rename `sdk_exceptions.py → errors.py` is a major-version-class change
deferred to a separate proposal (zero-tolerance.md Rule 6a + no-shim
conflict).

**RC3 — PACT integration: not applicable to #912.** (Used in #913 only.)

**RC4 — `pause`/`resume`/`update_cron` scheduler methods: not applicable to
#912.** (Owned by #913 Shard 0.)

## Broad-sweep grep results (RC1)

`grep -RnE 'def\s+execute\s*\([^)]*\*\*kwargs' src/kailash/runtime/` plus a
manual signature read of every `class *Runtime`. Production methods that
currently accept `**kwargs`:

| #   | Class                                       | File                                 | Line | Disposition under RC1                                                                                                              |
| --- | ------------------------------------------- | ------------------------------------ | ---- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `BaseRuntime.execute` (abstract)            | `src/kailash/runtime/base.py`        | 843  | Tighten abstract signature: `def execute(self, workflow, *, parameters=None, soft_time_limit=None, time_limit=None) -> Tuple`.     |
| 2   | `LocalRuntime.execute`                      | `src/kailash/runtime/local.py`       | 927  | Drop `**kwargs`; promote keyword-only typed kwargs (already partially keyword-only after `*,`). Add `soft_time_limit, time_limit`. |
| 3   | `AsyncLocalRuntime.execute` (sync override) | `src/kailash/runtime/async_local.py` | 707  | Drop `**kwargs`; mirror parent + `soft_time_limit, time_limit`.                                                                    |
| 4   | `DistributedRuntime.execute`                | `src/kailash/runtime/distributed.py` | 502  | Drop `**kwargs` (silent-drop offender per brief). Add `soft_time_limit, time_limit`. PRIMARY producer surface for #912.            |

Methods that DO NOT carry `**kwargs` (typed already — additive `*,
soft_time_limit, time_limit` only, no removal needed):

| Class                                      | File                                       | Line | Action                                                                          |
| ------------------------------------------ | ------------------------------------------ | ---- | ------------------------------------------------------------------------------- |
| `AsyncLocalRuntime.execute_workflow_async` | `src/kailash/runtime/async_local.py`       | 806  | Keyword-only typed already. Add `soft_time_limit, time_limit`.                  |
| `DockerRuntime.execute`                    | `src/kailash/runtime/docker.py`            | 565  | Add `soft_time_limit, time_limit` (additive; out-of-process timer enforcement). |
| `ParallelRuntime.execute` (async)          | `src/kailash/runtime/parallel.py`          | 66   | Add `soft_time_limit, time_limit`.                                              |
| `ParallelCyclicRuntime.execute`            | `src/kailash/runtime/parallel_cyclic.py`   | 62   | Add `soft_time_limit, time_limit`.                                              |
| `AccessControlledRuntime.execute`          | `src/kailash/runtime/access_controlled.py` | 129  | Add `soft_time_limit, time_limit` (forwards to inner runtime).                  |
| `DurableRuntime.execute` (async)           | `src/kailash/runtime/durable.py`           | 1281 | Add `soft_time_limit, time_limit`.                                              |

**Forwarding callsite (must update or signature drift):**

- `src/kailash/runtime/scheduler.py:858` — `runtime.execute(workflow, **kwargs)` inside the retry loop. Will need to pop `soft_time_limit`/`time_limit` from `kwargs` and pass them as named arguments (or restructure to call `_execute_with_time_limits` wrapper helper introduced in Shard 2).

**Sweep size estimate:**

- `**kwargs` removal: 4 production classes × ~3 LOC change each = ~12 LOC mechanical signature changes.
- Additive `soft_time_limit, time_limit` keyword-only kwargs across 10 execute methods: 10 × ~4 LOC = ~40 LOC mechanical.
- Signature-invariant tests (Rule 3a): 10 methods × ~10 LOC test = ~100 LOC test.
- Total signature-only surface ≈ 152 LOC. Well under the 500 LOC load-bearing budget.

**Conclusion:** Single Shard 1 is feasible. Shard 0 split NOT required. The
sweep is mechanical signature work, not load-bearing logic; per
`autonomous-execution.md` § Per-Session Capacity Budget Rule 2 ("size by
complexity, not LOC alone"), the invariant count for Shard 1 is dominated
by the time-limit wrapper logic in Shard 2, NOT the signature sweep.

## Shard plan

Five shards. Sequential dependencies: Shard 1 → Shard 2 → Shards 3 + 4
(parallel) → Shard 5. Shard 1 is the **signature-owner** for #912 per
`agents.md` § Parallel-Worktree Package Ownership Coordination — #911
(`queue=` kwarg) MUST wait for Shard 1 to merge.

---

### Shard 1 — Exception types + broad-sweep typed-kwargs cleanup

**Value-anchor:** Closes the silent-drop offender at
`distributed.py:502-544` per the user's 2026-05-09 approval ("RC1: BROAD
sweep across all BaseRuntime subclasses"); aligns the producer-side
execution surface with `zero-tolerance.md` Rule 3c so #911 (queue=) can
land on a cleaned signature without re-fighting the same battle. The user
brief at `gh issue view 912` is the load-bearing source: per-task
soft/hard time limits cannot land cleanly while every runtime advertises
`**kwargs` and silently drops everything; soft/hard timing is the
specific value, the signature cleanup is the structural prerequisite.

**Files touched:**

- `src/kailash/sdk_exceptions.py` — add `SoftTimeLimitExceeded`, `HardTimeLimitExceeded` (~20 LOC).
- `src/kailash/runtime/base.py` (line 843) — tighten abstract signature to keyword-only typed.
- `src/kailash/runtime/local.py` (line 927) — drop `**kwargs`; promote typed kwargs; add `soft_time_limit`, `time_limit` (placeholders accepted, not yet enforced — enforcement is Shard 2's helper).
- `src/kailash/runtime/async_local.py` (lines 707 + 806) — same treatment for both `execute` and `execute_workflow_async`.
- `src/kailash/runtime/distributed.py` (line 502) — drop `**kwargs`; add the two typed kwargs.
- `src/kailash/runtime/docker.py` (line 565) — additive only.
- `src/kailash/runtime/parallel.py` (line 66) — additive only.
- `src/kailash/runtime/parallel_cyclic.py` (line 62) — additive only.
- `src/kailash/runtime/access_controlled.py` (line 129) — additive only; forward to inner runtime.
- `src/kailash/runtime/durable.py` (line 1281) — additive only.
- `src/kailash/runtime/scheduler.py` (line 858) — pop `soft_time_limit`/`time_limit` from `kwargs` before forwarding (placeholder; enforcement lands Shard 3).

**Invariants (8):**

1. Every runtime's `execute(...)` signature lists `soft_time_limit` and `time_limit` as keyword-only `Optional[float]` defaulting to `None`.
2. No `**kwargs` survives in any `BaseRuntime` subclass after this shard (4 removals — Base/Local/Async/Distributed).
3. `SoftTimeLimitExceeded` and `HardTimeLimitExceeded` subclass `RuntimeException`; they live in `kailash.sdk_exceptions` (NO `kailash.errors` shim per RC2).
4. Both exceptions are exported in `sdk_exceptions.__all__`.
5. The placeholder kwargs are accepted but not yet wired (validation only — `if value is not None and value <= 0: raise ValueError`); enforcement is Shard 2's wrapper.
6. `scheduler.py:858` no longer forwards `**kwargs` blindly to `runtime.execute`; it explicitly threads `parameters` plus the two new kwargs (others raise `TypeError`).
7. The validation `soft_time_limit < time_limit` (when both set) lives in a single helper called from every entry point — no duplicated validation across 10 runtimes.
8. Cross-SDK alignment: keyword names match celery (`soft_time_limit`, `time_limit`); exception names match celery's `SoftTimeLimitExceeded`. NO Rust/cross-repo filing per `repo-scope-discipline.md`.

**LOC estimate:** ~60 LOC load-bearing (validation helper + scheduler `kwargs` un-forwarding) + ~120 LOC mechanical (signature additions across 10 methods + 2 exception classes). Net ~180 LOC. Well under 500.

**Tests required (Tier 2 + structural invariant):**

- `tests/regression/test_issue_912_signature_invariants.py` (NEW) — pin every runtime's typed signature; assert `**kwargs` absent on the 4 cleaned classes; assert `soft_time_limit`/`time_limit` accepted on all 10 methods. ~150 LOC.
- `tests/integration/test_runtime_signature_typed_kwargs.py` (NEW) — for each runtime, assert `runtime.execute(workflow, parameters={...}, soft_time_limit=2)` does not raise on signature; assert `runtime.execute(workflow, garbage_kwarg=1)` raises `TypeError`. ~80 LOC.
- `tests/unit/test_sdk_exceptions_time_limits.py` (NEW) — `SoftTimeLimitExceeded` / `HardTimeLimitExceeded` subclass `RuntimeException`; `__cause__` chaining preserved. ~40 LOC.

**Dependencies:** None. This shard owns the signature surface; everything downstream follows.

**Worktree assignment:** Wave 1 (Option B parallel plan). Branch `feat/issue-912-shard-1-typed-kwargs-sweep`. Worktree path `.claude/worktrees/issue-912-shard-1`. Pre-flight per `worktree-isolation.md` Rule 5 (merge-base = current `main` HEAD). Launches in parallel with `feat/issue-913-shard-0-scheduler-methods` (independent surface — scheduler `pause`/`resume`/`update_cron`).

**In-shard same-class fixes** (per `autonomous-execution.md` MUST Rule 4): if reviewer surfaces additional `**kwargs` carve-outs (e.g., a private `_execute_internal` helper) AND they fit the budget, fix in same shard.

---

### Shard 2 — `_time_limits.py` wrapper helper

**Value-anchor:** Soft/hard limit ENFORCEMENT (the actual user-asked-for
behavior in #912's body) requires a thread-/loop-safe wrapper that arms a
`CancellationToken` at the deadline. Without this helper, Shard 1's typed
kwargs are accepted but ignored — the same fake-dispatch failure-mode
class as `zero-tolerance.md` Rule 2 fake-dispatch evidence. The user's
brief explicitly requests "celery-style soft_time_limit (warn, raise a
catchable exception inside the running workflow)" — Shard 2 is what
makes that promise true.

**Files touched:**

- `src/kailash/runtime/_time_limits.py` (NEW) — wrapper helper module. Two callables:
  - `arm_time_limits(token, *, soft_time_limit, time_limit, grace_seconds) -> _Cancellable` (sync, uses `threading.Timer`).
  - `arm_time_limits_async(token, *, soft_time_limit, time_limit, grace_seconds) -> _Cancellable` (async, uses `asyncio.create_task` + `asyncio.sleep`).
  - `_TimeLimitClassifier` — converts `WorkflowCancelledError` raised by the runtime back into `SoftTimeLimitExceeded` / `HardTimeLimitExceeded` based on which deadline was reached first (compare `time.monotonic()` against stored deadlines).
  - `_validate_limits(soft, hard) -> None` — single source of validation (`> 0`, `soft < hard`); called from every runtime entry point.

**Invariants (5):**

1. Timer is **NEVER** signal-based (`signal.SIGALRM` BLOCKED — fails outside main thread, fails on Windows). Use `threading.Timer` (sync) / `asyncio.create_task` (async).
2. Timer arms at the call to `arm_time_limits()`, NOT at scheduler-registration time. This means re-fired jobs after restart get a fresh budget.
3. Disarm in `finally` block — both timers are explicitly cancelled when the wrapped block exits, regardless of success/failure.
4. The wrapper preserves cause chain: the runtime raises `WorkflowCancelledError`; the classifier wraps it as `SoftTimeLimitExceeded(...) from original`.
5. Hard-limit enforcement: after `time_limit + grace_seconds`, the wrapper raises `HardTimeLimitExceeded` UNCONDITIONALLY (does not wait for the runtime to observe the token — the grace window is the runtime's chance to wind down cleanly).

**LOC estimate:** ~150 LOC load-bearing (timer plumbing + classifier + validation). Net well under 500.

**Tests required:**

- `tests/integration/test_time_limits_wrapper.py` (NEW) — Tier 2 (real `LocalRuntime` + real `CancellationToken`):
  - `test_soft_limit_raises_after_deadline` — workflow sleeps 5s; soft=2s; assert `SoftTimeLimitExceeded` raised at ~2s.
  - `test_hard_limit_raises_after_grace` — workflow sleeps 5s; hard=2s, grace=1s; assert `HardTimeLimitExceeded` raised at ~3s.
  - `test_validation_rejects_negative` — `_validate_limits(soft=-1, hard=None)` raises `ValueError`.
  - `test_validation_rejects_soft_ge_hard` — `_validate_limits(soft=10, hard=5)` raises `ValueError`.
  - `test_async_wrapper_no_signal_fallback` — assert `arm_time_limits_async` works inside `asyncio.run()` (proves no signal usage).
  - `test_disarm_releases_timer_thread` — assert no zombie threads after exit.
  - ~200 LOC total.

**Dependencies:** Shard 1 (needs `SoftTimeLimitExceeded`/`HardTimeLimitExceeded` types).

**Worktree assignment:** Wave 2 (sequential after Shard 1 merges). Branch `feat/issue-912-shard-2-time-limits-wrapper`.

---

### Shard 3 — `WorkflowScheduler` plumbing

**Value-anchor:** In-process scheduler is the surface most kailash-py
users touch first (cron jobs, `schedule_interval`, `schedule_once`); the
brief's Acceptance Criterion #1 says soft/hard limits must work through
this surface AND interact correctly with the just-merged `RetrySpec`
(#910). Without this shard, scheduled jobs can be retry-controlled but
not time-limited — half a feature.

**Files touched:**

- `src/kailash/runtime/scheduler.py`:
  - Add `_TIME_LIMIT_KWARG = "_kailash_time_limits"` constant alongside `_RETRY_SPEC_KWARG` at line 71.
  - `_compose_job_kwargs` (line 744) — accept `soft_time_limit`/`time_limit` parameters; thread a tuple `(soft, hard)` under the internal key.
  - `_execute_workflow` (line 780) — pop the internal key; arm timers around `runtime.execute(...)` at line 858 inside the existing retry loop. Each retry attempt re-arms a fresh timer (no carry-over).
  - `schedule_cron` (line 499), `schedule_interval` (line 579), `schedule_once` (line 642) — accept the new keyword-only kwargs; call updated `_compose_job_kwargs`.
  - Optionally `WorkflowScheduler.__init__` accepts `default_soft_time_limit`/`default_time_limit` (per architecture-plan Open Question #1; recommendation: include for celery-symmetry; flag user-gated at /implement).

**Invariants (6):**

1. Signature parity across `schedule_cron`, `schedule_interval`, `schedule_once` (all three accept the same two new kwargs in the same position).
2. `RetrySpec` interaction: `SoftTimeLimitExceeded` is a normal exception in the retry classifier — `RetrySpec(retry_on=(SoftTimeLimitExceeded,))` retries; `RetrySpec(dont_retry_on=(SoftTimeLimitExceeded,))` does NOT.
3. Each retry attempt re-arms a fresh timer (NO carry-over from prior attempt's elapsed time).
4. Validation at scheduler-registration time, not at fire time (catches operator error before the job runs once).
5. `HardTimeLimitExceeded` propagates through APScheduler's job-error listener (per architecture-plan Open Question #3 recommendation: Option (a) — compose with RetrySpec, don't bypass).
6. Persistence: limits are persisted in APScheduler `kwargs=` dict (same pattern as `_RETRY_SPEC_KWARG`); replayed from jobstore on restart.

**LOC estimate:** ~180 LOC load-bearing (kwargs threading + retry-loop integration + 3 schedule\_\* methods).

**Tests required:**

- `tests/integration/test_scheduler_time_limits.py` (NEW):
  - `test_soft_time_limit_raises_in_workflow` — schedule workflow that sleeps 5s; soft=2s; assert `SoftTimeLimitExceeded` propagates via APScheduler error listener.
  - `test_hard_time_limit_raises_after_grace` — same workflow; hard=2s, grace=1s; assert `HardTimeLimitExceeded` at ~3s.
  - `test_soft_then_hard_propagation` — soft=2, hard=4; user code catches soft and continues sleeping; hard fires at 4+grace.
  - `test_retryspec_classifies_soft_as_retryable_on_demand` — `RetrySpec(retry_on=(SoftTimeLimitExceeded,), max_retries=2)` + `soft_time_limit=2`; assert workflow retried.
  - `test_retryspec_dontretry_on_soft_overrides` — `dont_retry_on=(SoftTimeLimitExceeded,)`; assert no retry.
  - `test_each_retry_arms_fresh_timer` — soft=2, max_retries=3; assert each attempt sees full 2s budget.
  - ~250 LOC total. Use established `tests/regression/test_scheduler_retry_primitives.py` `tmp_path` + tempfile counter pattern (PythonCodeNode sandbox blocks `tests.*` imports).

**Dependencies:** Shard 1 (typed kwargs), Shard 2 (wrapper helper). Once those land, Shard 3 + Shard 4 are independent (parallelizable).

**Worktree assignment:** Wave 3 (parallel with Shard 4). Branch `feat/issue-912-shard-3-scheduler-time-limits`.

---

### Shard 4 — `DistributedRuntime` + `Worker` plumbing

**Value-anchor:** Brief Acceptance Criterion #2 explicitly names
`DistributedRuntime.execute(...)` (producer side) and Acceptance Criterion
#2 names `Worker.__init__(default_soft_time_limit=, default_time_limit=)`

- "task is requeued on hard limit" (consumer side). Without this shard,
  soft/hard limits work in-process but break the moment a workflow is
  serialized to Redis. The wire-format addition is the highest-risk
  surface; this shard owns it.

**Files touched:**

- `src/kailash/runtime/distributed.py`:
  - `TaskMessage` dataclass — add `execution_limits: Optional[Dict[str, float]] = None` (`{"soft": 300.0, "hard": 600.0}` shape — single optional dict for forward-compat with workers running older SDK).
  - `TaskMessage.to_json` / `from_json` — serialize/deserialize the new field.
  - `DistributedRuntime.execute` (line 502) — already typed by Shard 1; populate `task.execution_limits` from the typed kwargs at enqueue time.
  - `Worker.__init__` (line 614) — add `default_soft_time_limit, default_time_limit, hard_time_limit_grace_seconds` keyword-only kwargs.
  - `Worker._execute_task` (line 839) — compute effective limits = per-task limits OR worker defaults; arm timers around `run_in_executor(_execute_workflow_sync)` at line 878; catch `HardTimeLimitExceeded`; treat as retryable failure (existing nack path requeues if `attempts < max_attempts`).
  - Lifecycle hook integration (#914 just merged): `on_task_retry` fires on hard-limit-with-attempts-remaining; `on_task_failure` fires on dead-letter.

**Invariants (7):**

1. Producer-side serializes limits onto `TaskMessage`, NOT the deadline timestamp (timer arms at dequeue, not enqueue — so queue wait doesn't burn budget).
2. Wire format: `execution_limits` is one optional dict, not two separate fields → workers running older SDK silently ignore unknown field (forward-compat).
3. Default fallback chain: per-task value (from `TaskMessage`) wins; falls through to `Worker(default_*)`; falls through to `None` (no limit). Same precedence as `TaskMessage.visibility_timeout` vs `TaskQueue.default_visibility_timeout`.
4. `HardTimeLimitExceeded` triggers requeue (NOT dead-letter) when `attempts < max_attempts`; dead-letter only after exhaustion.
5. Lifecycle hook `on_task_retry` fires on hard-limit-with-attempts-remaining (per #914 contract).
6. Lifecycle hook `on_task_failure` fires on the dead-letter after attempts exhausted.
7. Producer-side `runtime.execute(...)` no longer accepts arbitrary `**kwargs` (Shard 1 invariant 2 propagates); typed signature only.

**LOC estimate:** ~220 LOC load-bearing (TaskMessage wire format + Worker plumbing + lifecycle hook integration).

**Tests required:**

- `tests/integration/test_distributed_time_limits.py` (NEW; real Redis per existing `tests/integration/test_distributed_*` pattern):
  - `test_producer_time_limits_serialize_to_taskmessage` — enqueue with `soft_time_limit=300, time_limit=600`; dequeue raw via `TaskQueue.dequeue`; assert `task.execution_limits == {"soft": 300.0, "hard": 600.0}`.
  - `test_worker_arms_timers_at_dequeue_not_at_enqueue` — enqueue with `time_limit=2`; sleep 3s before starting worker; assert worker still gets full 2s budget (proves dequeue-side arming).
  - `test_hard_limit_triggers_requeue` — workflow sleeps 10s; `time_limit=2`, `max_attempts=3`; assert task processed by 2 workers before dead-lettering on attempt 3.
  - `test_worker_default_overridden_by_per_task` — `Worker(default_time_limit=10)`; enqueue with `time_limit=2`; effective is 2s.
  - `test_lifecycle_hooks_fire_on_hard_limit` — register `on_task_retry` + `on_task_failure`; assert `on_task_retry` fires on retries 1-2, `on_task_failure` fires on dead-letter at attempt 3.
  - `test_taskmessage_wire_format_forward_compat` — older-SDK-style `TaskMessage` JSON without `execution_limits` field deserializes cleanly with `execution_limits is None`.
  - ~280 LOC total.

**Dependencies:** Shard 1, Shard 2. Independent of Shard 3 (different surface). Parallelizable with Shard 3.

**Worktree assignment:** Wave 3 (parallel with Shard 3). Branch `feat/issue-912-shard-4-distributed-time-limits`.

---

### Shard 5 — Cross-cutting: docs, CHANGELOG, signature-invariant pin tests

**Value-anchor:** A user reading `gh issue view 912` for the feature
release notes needs (a) a CHANGELOG entry, (b) docstring on every public
surface, (c) a signature-invariant pin so the next refactor doesn't
regrow `**kwargs`. Without Shard 5, the feature is implemented but
discoverable only by reading the source.

**Files touched:**

- `CHANGELOG.md` — entry under next minor version: per-task soft/hard time limits, `**kwargs` removal scope, exception types, `Worker.__init__` defaults.
- Docstrings on every changed signature (Shards 1, 3, 4) — celery-style examples.
- `tests/regression/test_issue_912_signature_invariants.py` — finalize per-runtime signature pins (drafted in Shard 1; finalize after Shards 3+4 land).
- `docs/`-side: spec section if `specs/_index.md` references runtime execution surface (verify at /implement; SKIP if no relevant spec file exists).

**Invariants (4):**

1. Every public method touched by Shards 1-4 has an updated docstring including a `soft_time_limit` / `time_limit` example.
2. CHANGELOG entry follows the existing format (see #910 entry as template).
3. Signature-invariant test (Rule 3a) covers all 10 runtime `execute*` methods (NOT just the 4 cleaned ones).
4. Brief example code in `gh issue view 912` body is reflected accurately in the CHANGELOG migration note (`from kailash.sdk_exceptions import SoftTimeLimitExceeded`, NOT `from kailash.errors`).

**LOC estimate:** ~80 LOC docs/CHANGELOG + ~150 LOC tests = ~230 LOC. Mostly boilerplate; well under 500.

**Tests required:** Signature-invariant pin tests (mostly authored in Shard 1; finalize here).

**Dependencies:** Shards 1+2+3+4 must merge before Shard 5 ships (it's the cross-cutting closer).

**Worktree assignment:** Wave 4 (sequential after Shards 3+4 merge). Branch `feat/issue-912-shard-5-docs-and-pins`.

---

## Tier-2 test plan (consolidated)

| Test file                                                  | Shard | Asserts                                                                              |
| ---------------------------------------------------------- | ----- | ------------------------------------------------------------------------------------ |
| `tests/regression/test_issue_912_signature_invariants.py`  | 1, 5  | Every runtime's typed signature; no `**kwargs` on 4 cleaned classes.                 |
| `tests/integration/test_runtime_signature_typed_kwargs.py` | 1     | `runtime.execute(..., garbage_kwarg=1)` raises `TypeError` on each runtime.          |
| `tests/unit/test_sdk_exceptions_time_limits.py`            | 1     | `SoftTimeLimitExceeded` / `HardTimeLimitExceeded` subclass `RuntimeException`.       |
| `tests/integration/test_time_limits_wrapper.py`            | 2     | Helper raises soft / hard at correct deadlines; no signal usage; no zombie threads.  |
| `tests/integration/test_scheduler_time_limits.py`          | 3     | End-to-end scheduler path; RetrySpec interaction; per-attempt fresh timer.           |
| `tests/integration/test_distributed_time_limits.py`        | 4     | Wire format; producer-vs-worker timing; requeue on hard; lifecycle hook integration. |

All Tier-2 tests use real infrastructure per `rules/testing.md` Tier 2/3
NO-MOCKING contract (real `LocalRuntime`, real APScheduler in-memory job
store, real Redis for distributed tests, real `CancellationToken`).

## Cross-SDK alignment notes

Per `repo-scope-discipline.md` MUST NOT clauses, this section is
**descriptive only** — no filing recommendation, no cross-repo `gh`
invocation. The kailash-rs equivalent surface (when/if added) would mirror:

- `WorkerConfig { default_soft_time_limit: Option<Duration>, default_time_limit: Option<Duration>, hard_time_limit_grace: Duration }`.
- Producer-side / dequeue-side timing distinction matches Python.
- Exception names → enum variants: `WorkflowError::SoftTimeLimitExceeded`, `WorkflowError::HardTimeLimitExceeded`.
- Rust's `tokio::time::timeout` is the natural primitive (vs Python's `threading.Timer` / `asyncio.create_task`).

The structural-invariant test in Shard 1 (`test_distributed_runtime_execute_signature`)
is the local defense per `cross-sdk-inspection.md` Rule 3a — if a future
Python refactor regrows `**kwargs`, the test fails loudly and forces a
re-audit before merge.

## Open questions for human gate before /implement

The 4 RC questions are decided. Two genuinely-blocking implementation
questions remain. Recommendation given for each per
`recommendation-quality.md` MUST-1.

### Q1: Default behavior on `WorkflowScheduler.__init__` (architecture-plan Q1)

**Question:** Should `WorkflowScheduler.__init__` accept
`default_soft_time_limit` / `default_time_limit` symmetric to
`Worker.__init__`?

**Recommendation:** YES, include in Shard 3.

**Why:** Mirrors celery's `task_soft_time_limit` global + per-call override.
Cost is ~20 LOC. Symmetry matters because operators running the in-process
scheduler often run a Worker pool too, and asymmetric defaults are a sharp
edge ("why does my cron job time out at 600s but my queued job at 300s?").

**Cons:** Expands API surface by 2 kwargs on the scheduler constructor.
Tiny, but real.

**Alternative:** Worker-only, scheduler defaults to `None`. Cheaper
implementation, surprising semantics.

### Q2: `HardTimeLimitExceeded` disposition in scheduler retry loop (architecture-plan Q3)

**Question:** When `HardTimeLimitExceeded` fires inside
`WorkflowScheduler._execute_workflow`'s retry loop, should it (a)
propagate through APScheduler's job-error listener AND compose with
`RetrySpec` for retries, OR (b) be silently consumed and the next
scheduled instance fires normally?

**Recommendation:** Option (a) — compose with RetrySpec.

**Why:** `RetrySpec` is the typed retry primitive that just landed (#910);
hard-limit cleanly composes. Option (b) bypasses RetrySpec and creates a
hidden control-flow path, which is exactly the "fake-dispatch" failure
mode `zero-tolerance.md` Rule 2 blocks.

**Cons:** Operators who want celery's "hard kill = task dead, cron
continues" semantic must explicitly write
`RetrySpec(dont_retry_on=(HardTimeLimitExceeded,))`. Slightly more verbose
but more typed.

**Alternative:** Option (b). Compatible with celery defaults but bypasses
the retry primitive.

These two questions are not blocking architecturally — Shards 1, 2, 4 and
the test scaffolding can proceed regardless. They affect only the 6 LOC
of Shard 3 plumbing. If the user wants to defer Q1/Q2 to /implement, the
recommended-default decisions above land; the user can override during
/implement gate review.

## Effort estimate (autonomous execution cycles)

| Shard                                                               | Cycles            | Worktree wave                  | Notes                                                                   |
| ------------------------------------------------------------------- | ----------------- | ------------------------------ | ----------------------------------------------------------------------- |
| 1 — Exceptions + broad-sweep typed-kwargs                           | 0.4               | Wave 1 (parallel #913 Shard 0) | Mechanical signature work + 2 exception classes + scheduler kwarg-pop.  |
| 2 — `_time_limits.py` wrapper helper                                | 0.5               | Wave 2 (sequential)            | Load-bearing async/sync dispatch; careful grace-window edge cases.      |
| 3 — `WorkflowScheduler` plumbing                                    | 0.4               | Wave 3 (parallel S4)           | Mechanical extension of `_RETRY_SPEC_KWARG` pattern.                    |
| 4 — `DistributedRuntime` + `Worker` plumbing                        | 0.6               | Wave 3 (parallel S3)           | TaskMessage wire-format change is highest-risk surface.                 |
| 5 — Docs, CHANGELOG, signature pins                                 | 0.2               | Wave 4 (sequential)            | Cross-cutting closer.                                                   |
| /redteam round-1 (orphan + signature sweep)                         | 0.3               | Wave 5 (sequential)            | Per `agents.md` MUST gate.                                              |
| /redteam round-2 (closure parity if round-1 produces FORWARDED)     | 0.2               | Wave 5 (sequential)            | Bash+Read specialist required per `agents.md`.                          |
| /codify (rule extracts if BLOCKED-rationalization patterns surface) | 0.1               | Optional                       | Only if timer-thread alternative is rejected with new evidence.         |
| **Total**                                                           | **~2.7 sessions** |                                | Wall-clock with parallel worktrees ~1.7 sessions (Waves 1+2+3 overlap). |

Per `autonomous-execution.md` § 10x Throughput Multiplier: equivalent
human-team estimate would inflate this to ~30-50 human-days; the 10x
multiplier converts to ~3 days parallel autonomous, which is consistent
with the ~2.7-session estimate.

## Signature-owner declaration (per `agents.md` § Parallel-Worktree Package Ownership)

**Issue #912 owns:**

- The `BaseRuntime`-subclass `execute(...)` signature shape.
- The `*, soft_time_limit, time_limit` keyword-only kwarg slot ordering.
- The `Worker.__init__` `default_*_time_limit` + `hard_time_limit_grace_seconds` slot.
- `kailash.sdk_exceptions.SoftTimeLimitExceeded` / `HardTimeLimitExceeded`.

**Collision with #911 (multi-queue):** #911's brief proposes
`runtime.execute(workflow, queue: str = "default")`. That third typed
kwarg lands AFTER #912's two — slot ordering is
`*, soft_time_limit, time_limit, queue` (alphabetical-ish; matches
celery convention). #911 MUST wait for #912 Shard 1 to merge before
opening its PR; otherwise the two agents fight over the same signature
line and one set of edits silently loses.

**Collision with #913 (lifecycle hooks for scheduler):** #913 Shard 0
adds `pause`/`resume`/`update_cron` scheduler methods (RC4) — independent
surface. Parallel-launchable with #912 Shard 1 in Wave 1.

## Plan ready for human gate

Per `communication.md` § Approval Gates:

- Does this cover everything you described in the brief? (cleaned `**kwargs`, soft/hard time limits, RetrySpec interaction, Worker defaults, lifecycle-hook integration)
- Is anything here that you didn't ask for? (the docs/CHANGELOG shard is procedural, not user-asked — acceptable to skip if you'd rather it be batched into the release PR, but recommended to keep separate so the release-prep PR stays metadata-only per `git.md`)
- Is anything missing that you expected to see? (the architecture plan's Q1 "WorkflowScheduler defaults" and Q3 "HardTimeLimitExceeded disposition" are surfaced as Open Questions above with recommended defaults; if you want a different default, name it and Shard 3's slot fills accordingly)
