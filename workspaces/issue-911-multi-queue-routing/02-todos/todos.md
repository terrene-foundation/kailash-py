# Issue #911 /todos: multi-queue routing

> Phase 02 (`/todos`) deliverable. READ-ONLY — no production code edits, no branches, no PRs in this phase. Output is the human-gate input before `/implement`.

## Root-cause decisions (user-approved 2026-05-09)

Four root-cause decisions were surfaced from the open questions in `01-analyze/architecture-plan.md` § "Open questions for the human" plus the session-notes-line-5 sequencing claim. Each was approved by the user on 2026-05-09.

**RC1 — `**kwargs`removal scope: BROAD sweep across all`BaseRuntime` subclasses, OWNED BY #912 Shard 1.\*\*

#911 does NOT own the `**kwargs` removal anymore. #912 Shard 1 lands the broad sweep across `BaseRuntime` and every subclass (`LocalRuntime`, `AsyncLocalRuntime`, `DistributedRuntime`, `ParallelRuntime`, etc.) FIRST. #911 Shard 1 builds on the cleaned typed-kwargs surface and ADDS `queue=` as one more typed kwarg. This deletes the original "Shard 1 owns `**kwargs` removal" line from the `01-analyze/architecture-plan.md` § "Implementation sketch" Shard 1. Total LOC for #911 drops by ~50–80 LOC (the silent-drop removal on `DistributedRuntime.execute` is no longer in scope here; it lives in #912 Shard 1).

**RC2 — `kailash.errors` namespace: not applicable to #911.**

The proposed `kailash.errors` namespace consolidation is owned by #912 only. No new module is created for #911. #912 adds typed exceptions to `src/kailash/sdk_exceptions.py` per the existing module's conventions; no namespace migration affects #911.

**RC3 — PACT integration: not applicable to #911.**

PACT envelope integration (D/T/R clearance threading through queue dispatch) is in scope for #913 (admin API + governance) only, not for #911. The queue-routing primitive is governance-agnostic; PACT-aware routing is a #913 concern that consumes #911's primitives.

**RC4 — `pause`/`resume`/`update_cron` scheduler methods: not applicable to #911.**

The `WorkflowScheduler.pause(schedule_id)` / `resume(schedule_id)` / `update_cron(schedule_id, new_cron)` administrative surface is owned by #913 Shard 0 only, not #911. #911 only adds the `queue=` kwarg to the existing `schedule_*` methods; the administrative methods are out of scope.

## Dependency on #912 Shard 1

**#911 Shard 1 launches AFTER #912 Shard 1 merges.** This is the single load-bearing sequencing constraint.

Why this changes #911's plan:

- The `01-analyze/architecture-plan.md` § "Implementation sketch" Shard 1 originally bundled the `**kwargs` removal on `DistributedRuntime.execute` together with the helper module + queue-routing producer plumbing. Per RC1, the `**kwargs` removal is now #912 Shard 1's job (broad sweep across all `BaseRuntime` subclasses).
- `#912 Shard 1` lands a clean typed-kwarg surface on `DistributedRuntime.execute(workflow, parameters=None, *, soft_time_limit=None, time_limit=None)` with NO trailing `**kwargs`. #911 Shard 1 then ADDS `queue: Optional[str] = None` as one additional named kwarg to the same surface.
- `Worker.__init__` is also touched by #912 Shard 1 (typed-kwarg cleanup on Worker — this plan assumes #912's broad sweep covers Worker too; if #912 scopes narrower, the orchestrator MUST surface the gap at /implement launch per `specs-authority.md` MUST-5c amend-at-launch).
- Per `agents.md` § "Parallel-Worktree Package Ownership Coordination", `Worker.__init__` and `WorkflowScheduler.schedule_*` are SHARED collision points between #912 and #911. Option B wave 2 sequencing handles them: #912 Shard 1 lands first (wave 1), THEN #911 Shard 1 layers on top (wave 2). No simultaneous parallel work on these surfaces.

If #912 Shard 1 has not merged at #911 Shard 1 launch time, the orchestrator MUST stop and re-sequence per `coc-sync-landing.md` (wait for upstream merge to land cleanly before building on top).

## Default-queue back-compat invariant

The single most load-bearing invariant of this entire plan: `make_queue_key("default")` MUST return byte-for-byte the EXACT existing `_QUEUE_KEY` string `"kailash:tasks:pending"` — NOT `"kailash:tasks:pending:default"`. Non-default queues get the `:<name>` suffix (e.g. `make_queue_key("fast") == "kailash:tasks:pending:fast"`).

**Why this matters in plain language:** existing users have tasks already enqueued in production today on the Redis list `kailash:tasks:pending`. If `make_queue_key("default")` returns a different string, every in-flight task orphans on first deploy of the new code — same failure-mode class as a public-API removal without a deprecation cycle (`zero-tolerance.md` Rule 6a).

**Pinned by these regression tests (paths the implementer MUST author):**

1. `tests/regression/test_911_default_queue_byte_compat.py` — pins the legacy `_QUEUE_KEY = "kailash:tasks:pending"` constant. Asserts `make_queue_key("default")` returns this exact byte string. If a future refactor changes either side, this regression fires before any user is affected.
2. `tests/unit/runtime/test_queue_keys.py` — Tier-1 unit tests for the helper module. Includes positive byte-vector assertions for `default`, `fast`, `slow_queue`, `a-b-c`, AND negative `validate_queue_name` cases (control chars, colons, slashes, > 64 chars) per failure-point #8 in the analyze plan.

## Shard plan

Three shards, each within `autonomous-execution.md` § Per-Session Capacity Budget MUST Rule 1 (≤500 LOC load-bearing logic, ≤5–10 invariants, ≤3–4 call-graph hops, describable in 3 sentences).

### Shard 1 — Helper module + producer plumbing (lighter post-RC1)

**Value-anchor:** delivers the canonical Redis-list-key shape that producer + consumer (and any future Rust SDK port) MUST share so multi-queue routing can be byte-identical across SDKs — the user explicitly asked for queue routing in issue #911 acceptance criteria, and this shard is the foundation every other shard layers on. (Anchored in user-approved sequence per `.session-notes:5` → "#912, then #911 (multi-queue routing)" + `01-analyze/architecture-plan.md` § "Implementation sketch" Shard 1.)

**Files touched:**

- `src/kailash/runtime/_queue_keys.py` (NEW, ~80 LOC)
- `src/kailash/runtime/distributed.py` (TaskMessage + DistributedRuntime constructor + DistributedRuntime.execute, ~80 LOC delta — REDUCED from analyze plan's ~150 LOC because the `**kwargs` removal is no longer in #911's scope per RC1)
- `tests/unit/runtime/test_queue_keys.py` (NEW, ~80 LOC)
- `tests/unit/runtime/test_distributed_runtime_signature_invariant.py` (NEW, ~30 LOC — pins the post-#912 + post-#911 signature shape: `workflow, parameters, soft_time_limit, time_limit, queue` and NO `**kwargs`)

**Invariants (5):**

1. `make_queue_key("default")` byte-for-byte equals existing `_QUEUE_KEY = "kailash:tasks:pending"` (load-bearing back-compat).
2. `make_queue_key(name)` for any non-`"default"` name returns `f"{_QUEUE_KEY_BASE}:{name}"`.
3. `validate_queue_name` raises `ValueError` on the documented bad set (empty, > 64 chars, control chars, colons, slashes, newlines, null bytes) per failure-point #8.
4. `DistributedRuntime.execute(queue=...)` routes via the helper — no inline string formatting; helper is the single canonical key source.
5. `TaskMessage` gains `queue_name: str = "default"` as an additive non-frozen-dataclass default field; JSON serialize/deserialize round-trip preserves it for legacy messages too (default fills missing field).

**LOC estimate (load-bearing logic):** ~150 LOC (helper module + TaskMessage field + execute signature plumbing). Plus ~110 LOC tests. Well under 500 LOC budget.

**Tests required (Tier 1 + Tier 2 + regression):**

- Tier 1: `tests/unit/runtime/test_queue_keys.py` — byte-vector assertions for `default` / `fast` / `slow_queue` / `a-b-c` / `"x" * 64`; rejection assertions for empty / > 64 / control-chars / colons / slashes / newlines / nulls.
- Tier 1: `tests/unit/runtime/test_distributed_runtime_signature_invariant.py` — `inspect.signature(DistributedRuntime.execute).parameters` contains exactly `{"self", "workflow", "parameters", "soft_time_limit", "time_limit", "queue"}` and NO `VAR_KEYWORD` parameter (no `**kwargs`).
- **Regression:** `tests/regression/test_911_default_queue_byte_compat.py` — pins `_QUEUE_KEY = "kailash:tasks:pending"` AND `make_queue_key("default") == "kailash:tasks:pending"`. Loud failure on any future drift.

**Dependencies:** **MUST land AFTER #912 Shard 1** (the typed-kwargs surface). Without #912's prior merge, `DistributedRuntime.execute` still has `**kwargs` and #911's invariant 4 cannot be enforced.

**Worktree assignment:** Option B wave 2 — Shard 1 launches as a single worktree agent in wave 2, after #912 Shard 1 has landed in wave 1. Worktree path: `.claude/worktrees/issue-911-shard-1` per `worktree-isolation.md` MUST-1+6 (explicit branch name `feat/issue-911-shard-1-helper-producer`). Pre-flight merge-base check against `main` post-#912-merge per Rule 5.

**Same-class fix-immediately gaps within shard:** none anticipated for Shard 1 — the helper module is self-contained; the silent-drop `**kwargs` (the prior same-class gap) is moved to #912's shard per RC1. If reviewer surfaces a sibling "queue-format string drift" in `infrastructure/task_queue.py` (the SQL-backed sibling), `autonomous-execution.md` MUST Rule 4 obligates same-shard fix if within 300 LOC budget — likely yes; the SQL queue's `queue_name` column already exists and consumes the helper trivially.

### Shard 2 — Worker multi-queue dequeue loop

**Value-anchor:** delivers the "slow task does not block fast task pickup" acceptance criterion #3 from issue #911 — the user-stated reason for filing the issue — by replacing the single-queue dequeue loop with one asyncio task per queue and per-queue concurrency semaphores. Without Shard 2, multi-queue routing is half-built (producer ships to queues, consumer can't read from them in parallel). (Anchored in user-approved sequence per `.session-notes:5` + issue #911 acceptance criteria as the user-authored brief.)

**Files touched:**

- `src/kailash/runtime/distributed.py` (Worker class — `__init__`, `_dequeue_loop`, `_send_heartbeat`, `_execute_task`, ~250 LOC delta)
- `src/kailash/runtime/lifecycle_events.py` (TaskEvent additive `queue_name` field, ~3 LOC — split into Shard 3 if cleaner; included here because Worker populates it)
- `tests/integration/runtime/test_worker_multi_queue.py` (NEW, ~250 LOC, real Redis Tier 2)

**Invariants (8):**

1. `Worker(concurrency=N)` and `Worker(queues={"default": N})` are externally indistinguishable (legacy parity) — same Redis list key (default-queue back-compat byte-vector), same heartbeat shape minus the `queues` field.
2. Per-queue dequeue tasks are independent asyncio tasks (one per declared queue), NOT a serialized round-robin.
3. Per-queue semaphores enforce per-queue concurrency caps independently.
4. Per-queue `visibility_timeout` overrides via dict syntax `queues={"slow": {"concurrency": 2, "visibility_timeout": 1800}}` are honored (failure-point #4).
5. Mutually-exclusive `queue=<TaskQueue>` and `queues={...}` raise `ValueError` at construction (named-kwarg discipline; do NOT silently prefer one).
6. Slow-queue task does NOT block fast-queue dequeue (failure-point #3 / acceptance criterion 3).
7. Heartbeat JSON includes `queues={"fast": 8, "slow": 2}` per failure-point #7.
8. Lifecycle hooks (`on_task_*`) receive `event.queue_name` populated from `task.queue_name` (failure-point #6).

**LOC estimate (load-bearing logic):** ~450 LOC (Worker `__init__` rewrite + dequeue-loop fanout + heartbeat extension + lifecycle-event population). Plus ~250 LOC tests. Under 500 LOC budget; close to ceiling, justified by the per-queue feedback loop (real Redis Tier-2 multiplies capacity 3-5× per `autonomous-execution.md` MUST Rule 3).

**Tests required (Tier 2 with real Redis):**

- **Slow-queue does not block fast-queue (#911 acceptance criterion 3):** spawn `Worker(queues={"fast": 4, "slow": 1})`. Enqueue 1 slow task that sleeps 30s + 100 fast tasks. Assert all 100 fast tasks complete within 5 wall-seconds while the slow task is still processing.
- **Per-queue concurrency:** `Worker(queues={"fast": 2})` polls 5 fast-tasks; assert at most 2 are in `processing` state at any sample point.
- **Per-queue visibility timeout:** `Worker(queues={"slow": {"concurrency": 1, "visibility_timeout": 5}})` polls a 30-sec workflow; assert the same task gets re-delivered to a sibling worker after the 5s timeout.
- **Default queue back-compat (load-bearing):** `Worker(concurrency=N)` and a producer that previously enqueued against `_QUEUE_KEY = "kailash:tasks:pending"` interoperate byte-for-byte against `Worker(queues={"default": N})` — same Redis list key, same task processed.
- **Mutual-exclusion at construction:** `Worker(queue=tq, queues={"default": 1})` raises `ValueError`.

**Dependencies:** Shard 1 (helper module + TaskMessage.queue_name) MUST land first; Shard 2 cannot dequeue from per-queue keys without `make_queue_key`. #912 Shard 1's `Worker.__init__` typed-kwarg cleanup MUST also land first if it touches `Worker` (likely yes per RC1's broad sweep scope).

**Worktree assignment:** Option B wave 2 second slot. Worktree path: `.claude/worktrees/issue-911-shard-2` per `worktree-isolation.md` MUST-1+6 (branch `feat/issue-911-shard-2-worker-multi-queue`). Pre-flight merge-base check against `feat/issue-911-shard-1-helper-producer` post-merge.

**Same-class fix-immediately gaps within shard:** if reviewer surfaces a sibling "queue routing not threaded through `_send_heartbeat` despite registry needing it for failure-point #7" or "mutual-exclusion missing for the construction-via-factory path", both are same-bug-class (queue routing through Worker surface) and ≤80 LOC each — fix in same shard per `autonomous-execution.md` MUST Rule 4.

### Shard 3 — Scheduler dispatch composition + lifecycle event extension

**Value-anchor:** delivers queue-routing-as-scheduler-kwarg so cron/interval/once jobs can route to slow vs fast queues with deterministic persistence across scheduler restarts (failure-point #5), AND extends the `TaskEvent` payload with `queue_name` for per-queue alerting handlers — both are required for the user's stated need ("a single Worker process can dequeue from a `{queue_name: concurrency}` map" implies the scheduler can target those queues). (Anchored in user-approved sequence per `.session-notes:5` + issue #911 acceptance criteria.)

**Files touched:**

- `src/kailash/runtime/scheduler.py` (`schedule_cron` / `schedule_interval` / `schedule_once` signatures, `_compose_job_kwargs`, `_dispatch_to_queue`, ~120 LOC delta)
- `src/kailash/runtime/lifecycle_events.py` (`TaskEvent.queue_name` additive default-None field — done in Shard 2 if cleaner; finalised here if not)
- `tests/integration/runtime/test_scheduler_queue_routing.py` (NEW, ~150 LOC, real APScheduler + real Redis Tier 2)

**Invariants (5):**

1. `schedule_cron(..., queue="slow")` persists `queue` into APScheduler job kwargs via the `_KAILASH_QUEUE_KWARG = "_kailash_queue"` sentinel pattern (mirrors the existing `_kailash_retry_spec` pattern from #916).
2. Fire-time dispatch reads `queue` from persisted kwargs — deterministic across scheduler instances per failure-point #5 (`compute_task_id` does NOT change; queue is a separate axis hashed only via the persisted job kwargs).
3. Composing `queue=` with `dispatch_via=None` raises `ValueError` (queue routing requires a dispatcher; same shape as the existing `retry + dispatch_via` BLOCK at `scheduler.py:768-774`).
4. **`retry + queue` BLOCK (load-bearing):** `scheduler.schedule_cron(..., retry=RetrySpec(...), queue="slow")` raises `ValueError` with a message referencing both kwargs. RetrySpec is in-process only; queue is dispatcher-side; the pair is meaningless together.
5. `TaskEvent.queue_name` is populated end-to-end (scheduler → Task → TaskMessage → Worker → handler) for queue-dispatched jobs.

**LOC estimate (load-bearing logic):** ~250 LOC (schedule\_\* signature plumbing + `_compose_job_kwargs` + `_dispatch_to_queue` + the `retry + queue` BLOCK + TaskEvent field). Plus ~150 LOC tests.

**Tests required (Tier 2 with real Redis + real APScheduler):**

- **Queue persists across scheduler restart:** schedule a cron job with `queue="slow"`, kill the scheduler process, restart from the same SQLite job-store, verify the next fire dispatches to the `slow` queue (failure-point #5).
- **Compose with lifecycle hooks:** register `on_task_success(handler)`; enqueue via scheduler with `queue="slow"`; assert `handler` received `event.queue_name == "slow"` (failure-point #6).
- **`retry + queue` BLOCK regression (load-bearing):** `scheduler.schedule_cron(..., retry=RetrySpec(max_attempts=3), queue="slow")` raises `ValueError`. Assert error message references both `retry` and `queue` kwargs by name. Mirrors `tests/unit/runtime/scheduler/test_retry_dispatch_blocked.py` (existing pattern from #916 RetrySpec landing).

**Dependencies:** Shard 1 (helper) AND Shard 2 (Worker queue handling, since the scheduler dispatches into queues that Workers consume). Sequential: Shard 3 launches AFTER Shard 1 + Shard 2 merge.

**Worktree assignment:** Option B wave 3 (after Shard 1 + Shard 2 land). Worktree path: `.claude/worktrees/issue-911-shard-3` per `worktree-isolation.md` MUST-1+6 (branch `feat/issue-911-shard-3-scheduler-composition`). Pre-flight merge-base check against `main` post-Shard-1+2-merge.

**Same-class fix-immediately gaps within shard:** if reviewer surfaces sibling `pause + queue` / `resume + queue` interactions (RC4 — out of scope for #911 but the surface might demand thinking), defer to #913 Shard 0 per RC4 — those methods don't exist yet. If reviewer surfaces missing queue-name validation at the scheduler-side `schedule_*` entry points (failure-point #8 — should have called `validate_queue_name` from Shard 1 here too), that's same-bug-class and one-line fix; same-shard per Rule 4.

## Tier-2 test plan

Consolidated view of the integration tests across all three shards, with paths and assertions.

### Shard 1 tests

**`tests/unit/runtime/test_queue_keys.py`** (Tier 1)

- `make_queue_key("default") == "kailash:tasks:pending"` (load-bearing back-compat byte vector)
- `make_queue_key("fast") == "kailash:tasks:pending:fast"`
- `make_queue_key("slow") == "kailash:tasks:pending:slow"`
- `make_processing_key("default") == "kailash:tasks:processing"`
- `validate_queue_name` accepts: `"default"`, `"fast"`, `"slow_queue"`, `"a-b-c"`, `"x" * 64`
- `validate_queue_name` rejects: `""`, `"x" * 65`, `"with space"`, `"with:colon"`, `"with/slash"`, `"with\nnewline"`, `"with\x00null"`

**`tests/unit/runtime/test_distributed_runtime_signature_invariant.py`** (Tier 1, structural per `cross-sdk-inspection.md` Rule 3a)

- `inspect.signature(DistributedRuntime.execute)` contains exactly `{"self", "workflow", "parameters", "soft_time_limit", "time_limit", "queue"}` and NO `VAR_KEYWORD` parameter.
- Pins the surface against `**kwargs` regrowth.

**`tests/regression/test_911_default_queue_byte_compat.py`** (Regression — load-bearing)

- Pins `_QUEUE_KEY = "kailash:tasks:pending"` constant.
- Pins `make_queue_key("default") == "kailash:tasks:pending"`.
- Pins `make_queue_key("default") != "kailash:tasks:pending:default"` (the failure mode if the asymmetry is forgotten).

### Shard 2 tests

**`tests/integration/runtime/test_worker_multi_queue.py`** (Tier 2, real Redis)

- **Slow-queue does not block fast-queue (acceptance criterion 3):** spawn `Worker(queues={"fast": 4, "slow": 1})`; enqueue 1 slow-30s + 100 fast tasks; assert all 100 fast complete < 5s wall while slow still processing.
- **Per-queue concurrency:** `Worker(queues={"fast": 2})` against 5 fast tasks; assert ≤2 in `processing` at any sample.
- **Per-queue visibility timeout:** `Worker(queues={"slow": {"concurrency": 1, "visibility_timeout": 5}})` against a 30s task; assert re-delivery to sibling worker after 5s.
- **Default queue back-compat (load-bearing):** producer-side enqueue against legacy `_QUEUE_KEY = "kailash:tasks:pending"` interoperates with `Worker(queues={"default": N})` AND `Worker(concurrency=N)` (both shapes produce same Redis-list-key reads).
- **Mutual-exclusion at construction:** `Worker(queue=tq, queues={"default": 1})` raises `ValueError`.

### Shard 3 tests

**`tests/integration/runtime/test_scheduler_queue_routing.py`** (Tier 2, real APScheduler + Redis)

- **Queue persists across scheduler restart:** schedule with `queue="slow"`; kill + restart; verify next fire dispatches to `slow`.
- **Compose with lifecycle hooks:** `on_task_success(handler)` receives `event.queue_name == "slow"` for queue-dispatched job.
- **`retry + queue` BLOCK (load-bearing):** `scheduler.schedule_cron(..., retry=RetrySpec(...), queue="slow")` raises `ValueError`; assert error message references both kwargs.

### Test discipline

Per `rules/testing.md` (kailash-py): NO mocking in Tier 2/3. Tests use real Redis (`docker-compose.test.yml` infrastructure already in place per existing Tier 2 test conventions in `tests/integration/runtime/`). Tier 1 unit tests are pure-Python with no infrastructure.

## Cross-SDK alignment notes

**Descriptive only — kailash-rs is a sibling repo and cross-repo work is BLOCKED per `repo-scope-discipline.md`. No issue is filed against `kailash-rs` from this session.**

The Rust SDK (kailash-rs) exposes its own `DistributedRuntime` and `Worker` types. Cross-SDK alignment per `cross-sdk-inspection.md` Rule 3 (matching semantics, independent implementation):

- The canonical Redis key shape `kailash:tasks:pending[:queue_name]` MUST be IDENTICAL byte-for-byte across both SDKs so a Python-side producer can enqueue and a Rust-side worker can dequeue (and vice versa).
- The byte-vector regression test `tests/regression/test_911_default_queue_byte_compat.py` MUST be replicated as a Rust test pinning the same byte string. The Rust SDK's analog of `make_queue_key` MUST return the same byte string for the same input. Per `cross-sdk-inspection.md` Rule 4, the test vectors MUST be pinned in BOTH SDKs as raw byte strings, NOT abstract assertions.
- The `Worker(queues={...})` map shape is a Python idiom; the Rust equivalent (`HashMap<String, QueueSpec>` or a typed builder) is the same data model in Rust idiom.
- `TaskEvent.queue_name: Option<String>` mirrors the Python additive default-None field.

A Rust-side implementer reading the analyze + todos plans reproduces the surface in Rust idiom. The byte-shape contract on Redis is what this plan pins. Filing the cross-SDK tracking issue against `kailash-rs` (if needed) is the user's call from a kailash-rs session, not from this session.

## Open questions for human gate before /implement

These need a gate decision before `/implement` launches:

**Q1 — `lifecycle_events.py::TaskEvent.queue_name` placement: Shard 2 or Shard 3?**

Recommendation: **Shard 2.** Worker is the producer of `TaskEvent` (via `_execute_task`); the field is populated when the Worker reads `task.queue_name` from the dequeued message. Doing it in Shard 2 keeps the additive field with its populator. Shard 3 only validates the field is honored end-to-end via the integration test.

Implications: places ~3 LOC of `lifecycle_events.py` delta in Shard 2 instead of Shard 3 — Shard 2 stays under 500 LOC budget either way. Trade-off: if Shard 3 lands first (it won't given the dependency chain, but in theory), the field would already exist; doing it in Shard 2 is the natural place.

Cons: Shard 3's integration test depends on the field existing in Shard 2 — slight coupling, but Shard 3 already depends on Shard 2 per the plan.

**Q2 — `Worker(concurrency=N)` legacy-path forwarding: forward to `queues={"default": N}` (single canonical path) OR keep legacy single-queue branch separate?**

Recommendation: **forward to `queues={"default": N}`.** One canonical code path is structurally simpler and closes the parity invariant by construction (Shard 2 invariant 1 falls out of the design rather than needing test enforcement). Per `01-analyze/architecture-plan.md` § "Open questions" Q3 — the analyze plan also recommended forward.

Implications: simpler Worker code (~30 LOC less than the dual-path version), one fewer code branch to maintain, Shard 2 invariant 1 (legacy-parity) becomes structurally enforced rather than test-enforced.

Cons: a single `Worker(concurrency=N)` user who happened to inspect `worker._queues` (private attribute, but still) sees `{"default": N}` instead of `None` — minimal blast radius given underscore-prefixed attribute.

**Q3 — Per-queue back-pressure when all semaphores are saturated: stop polling Redis OR keep polling and immediately re-queue?**

Recommendation: **stop polling.** Matches celery's behaviour, keeps Redis cheap, prevents thrashing. Per `01-analyze/architecture-plan.md` § "Open questions" Q4.

Implications: Worker holds an asyncio condition variable per queue; the dequeue loop awaits the semaphore release before BLMOVE-polling Redis. Slightly more complex than the polling-and-requeue path but produces lower Redis QPS under load.

Cons: a saturated queue does not consume Redis network until a slot frees; transient mis-tuning (concurrency too low) is harder to diagnose because the "I'm saturated" state is silent. Mitigation: the heartbeat already records `active_tasks` and `concurrency`; saturation is `active_tasks >= concurrency` and IS dashboard-able from heartbeat data alone.

**Q4 — Should #911 Shard 3 land `pause`/`resume`/`update_cron` if the implementer is already touching `WorkflowScheduler.schedule_*`?**

Recommendation: **NO — keep RC4 boundary.** RC4 explicitly assigns the administrative methods to #913 Shard 0. Even though Shard 3 is touching the scheduler, the methods are out of scope per the user-approved RC. If the implementer surfaces an in-shard same-class gap (e.g., the queue-kwarg pattern at `schedule_*` could be reused by the missing `pause`/`resume`), file as a `#913` follow-up with a value-anchor citing the user's #913 brief — do NOT silently absorb into #911.

Implications: discipline boundary preserved; #913 lands cleanly with no overlap; #911 stays at three shards.

Cons: a future #913 implementer reads two cross-issue plans to land the admin surface — one extra read; minimal cost.

## Effort estimate

Per `autonomous-execution.md` § Per-Session Capacity Budget, effort is in **autonomous execution cycles** (sessions), not human-days. Each shard is one Opus session in a worktree.

- **Shard 1** (helper + producer plumbing, post-RC1 lighter scope): **~half a session** if the helper module is self-contained AND #912 Shard 1's typed-kwarg surface has already merged. Real-time feedback loop (Tier-1 unit tests on the helper module) per `autonomous-execution.md` MUST Rule 3 multiplies capacity 3-5×.
- **Shard 2** (Worker multi-queue dequeue loop): **~1 session** — highest-invariant shard in the plan (8 invariants + per-queue asyncio fanout + per-queue semaphores + per-queue visibility timeouts + lifecycle hooks). Real-Redis Tier-2 feedback loop multiplies capacity per Rule 3.
- **Shard 3** (scheduler composition + lifecycle event): **~1 session** — small LOC delta but high cross-rule invariant count (RetrySpec composition with `retry + queue` BLOCK, lifecycle hooks, persistence on restart).

**Total: ~2.5 sessions** (Shard 1 + Shard 2 + Shard 3, sequential due to shared `Worker.__init__` and `WorkflowScheduler.schedule_*` collision points with #912 already mitigated by Option B wave 2 sequencing).

Gate-level reviews (`reviewer` + `security-reviewer` per `agents.md` § Quality Gates) run as parallel background agents at the end of `/implement` and do NOT count toward shard sessions — they cost near-zero parent context.

If RC1 changes (e.g., #912 Shard 1's broad sweep does NOT cover `Worker.__init__`), the orchestrator MUST surface the gap at /implement launch per `specs-authority.md` MUST-5c amend-at-launch and EITHER add a typed-kwarg sub-shard to #911 Shard 2 (re-estimating to ~1.5 sessions) OR coordinate back to #912 to extend its sweep. Per `agents.md` § Parallel-Worktree Package Ownership Coordination, the version-owner / no-edit-coordination boundary is between #912 and #911 implementers — orchestrator gate before /implement.
