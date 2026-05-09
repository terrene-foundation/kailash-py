# Issue #913: admin API for WorkflowScheduler

## Brief summary

Issue #913 asks for a runtime administration surface over `kailash.runtime.scheduler.WorkflowScheduler`. Today, schedules are created in code (`scheduler.schedule_cron(workflow, "0 6 * * *")`) and persisted via APScheduler's SQLAlchemy job store; ops cannot list, pause, resume, edit cron expressions, or delete schedules without redeploying the scheduler process. Celery + django-celery-beat sets the comparison: a `PeriodicTask` row is editable in Django admin, the beat process picks up changes on the next reload tick. The brief asks for the same operational property in Kailash.

The deliverable is a `WorkflowScheduler.AdminAPI` exposed through the Kailash framework stack:
operations to list / enable / disable / update cron / delete schedules; transports HTTP + CLI + MCP via Nexus's multi-channel `@app.handler`; authentication via Nexus's JWT/auth surface; authorization via PACT envelopes (or Nexus AuthGuard role checks where PACT is not deployed); a Tier 2 integration test that exercises the full edit → next-fire path; and an optional migration helper from `django-celery-beat`'s `PeriodicTask` table.

## Brief corrections

The brief's claims were verified against the current source. The most material correction is on the schedule-mutation surface:

| Claim                                                                                                                    | Verdict                                      | Citation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| "`WorkflowScheduler` uses APScheduler's `SQLAlchemyJobStore` with a SQLite backend"                                      | TRUE                                         | `src/kailash/runtime/scheduler.py:404, 416` (`from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore` ... `SQLAlchemyJobStore(url=f"sqlite:///{job_store_path}")`)                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| "Job definitions are process-internal: ops cannot add, remove, or modify schedules at runtime through any admin surface" | PARTIALLY TRUE                               | The Python API surface (`schedule_cron` / `schedule_interval` / `schedule_once` / `cancel` / `list_schedules`) at `src/kailash/runtime/scheduler.py:499, 579, 642, 703, 725` lets you add/remove/list at runtime IN-PROCESS. There is NO modify-cron path (`modify_schedule` / `pause` / `resume` / `update_cron` are not implemented). There is NO HTTP / CLI / MCP exposure of any of these methods. The brief's framing is correct from an ops-surface perspective; from an in-process programmatic perspective, three of the five operations exist (list, add, cancel) but two are missing entirely (pause/resume, update-cron). |
| "Celery's `django-celery-beat` provides this via Django admin: a `PeriodicTask` row is editable in the UI"               | TRUE (industry context, no citation in repo) | descriptive only                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| "Optional integration with Nexus so the admin surface ships as a framework-native panel"                                 | FRAMEWORK-VERIFIED                           | Nexus `@app.handler` at `packages/kailash-nexus/src/nexus/core.py:2738` exposes a function across HTTP + CLI + MCP simultaneously; this IS the multi-channel surface the brief calls for.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| "Auth split: Nexus owns authentication … PACT owns authorization"                                                        | TRUE (rule-anchored)                         | `rules/framework-first.md` § ABSOLUTE table; `packages/kailash-nexus/src/nexus/auth/guards.py:90, 117, 239` provides `AuthGuard.RequireRole` / `RequirePermission`; `packages/kailash-pact/src/pact/engine.py` provides `GovernanceEngine` for envelope-based authz.                                                                                                                                                                                                                                                                                                                                                                 |

Brief corrections to record in `/todos`:

- The plan MUST add `pause`, `resume`, and `update_cron` to the in-process `WorkflowScheduler` surface BEFORE wiring them through Nexus. The brief implicitly assumes these exist; they do not.
- APScheduler natively supports `pause_job(id)` / `resume_job(id)` / `reschedule_job(id, trigger=...)`, so the in-process additions are thin facades; they do NOT require a new persistence layer.

## Framework choice: Nexus

Per `rules/framework-first.md` § ABSOLUTE Work-Domain → Framework Binding:

> **HTTP API, REST, gateway, middleware, login, sessions, websockets** → MANDATORY framework: **Nexus**
> **MCP servers, tools, resources, transports, exposing APIs as LLM tools** → MANDATORY framework: **MCP**

Nexus's `@app.handler` decorator (`packages/kailash-nexus/src/nexus/core.py:2738`) is the canonical Kailash way to expose ONE function across HTTP + CLI + MCP at once. Raw FastAPI / Flask / aiohttp is BLOCKED.

The admin API surface MUST be expressed as Nexus handlers:

- Each admin operation (list, get, pause, resume, update_cron, delete, stats) is one `@app.handler("scheduler.admin.<op>", guard=...)` registration.
- HTTP transport publishes them at `/api/scheduler/admin/<op>` per Nexus's standard handler route layout.
- CLI transport exposes them as `nexus scheduler admin <op>` subcommands automatically (Nexus's CLI channel mirrors handler names).
- MCP transport exposes them as MCP tools so an agent can `pause_schedule(schedule_id="sched-abc")` through any MCP client.

PACT enters at the authorization layer (see § Auth + governance below). The scheduler surface itself (the in-process `pause` / `resume` / `update_cron` additions) is NOT a Nexus concern — it lives in `src/kailash/runtime/scheduler.py` and is plain Python.

## Failure-point analysis

1. **Unauthenticated admin endpoints** — Condition: any of the admin handlers ships without `guard=` and Nexus is started without `enable_auth=True`. Consequence: anyone reachable on the API port can pause every production schedule. Mitigation: every admin handler MUST take a non-`None` `guard=AuthGuard.RequirePermission("scheduler:admin")` (or RBAC-equivalent), AND the integration test MUST construct Nexus with `enable_auth=True` and assert 401/403 on missing/insufficient credentials. Per `rules/security.md` § Multi-Site Kwarg Plumbing — every handler in the same PR.

2. **Authenticated-but-unauthorized mutation** — Condition: a user with a valid JWT but no `scheduler:admin` permission calls `scheduler.admin.update_cron`. Consequence: the user can rewrite cron expressions across tenants. Mitigation: PACT envelope check via the GovernanceEngine for mutating ops (pause / resume / update_cron / delete); read ops (list / get / stats) require only `scheduler:read`. Per `rules/framework-first.md` auth-split, Nexus AuthGuard handles role/permission strings; PACT handles structured envelope/clearance evaluation if the deployment uses governed agents.

3. **Schedule mutation racing with in-flight fires** — Condition: ops calls `update_cron(sched-X, "0 7 * * *")` while `_execute_workflow(sched-X)` is mid-flight on the previous trigger. APScheduler reschedules the job's trigger, but the in-flight fire continues to completion. Consequence: the operator believes the new cron took effect immediately; in reality the in-flight fire still runs to completion under the OLD planned_fire_time. This is correct APScheduler behavior but is a footgun for the operator. Mitigation: every admin mutation handler returns the schedule's `next_run_time` AFTER the mutation so the operator can see the new effective time; the response body MUST also include `in_flight_run_ids` (any run_ids currently executing that schedule's previous trigger). The lifecycle event hooks from #914 (`_hooks_job_success` / `_hooks_job_error`, `lifecycle_events.py:JobEvent`) are the structural source for "is the schedule currently firing".

4. **Idempotency of mutating commands** — Condition: a network retry causes `pause(sched-X)` to fire twice; OR a deploy-time replay causes `delete(sched-X)` to be called against a schedule that was already deleted. Consequence: opaque APScheduler exceptions (`JobLookupError`, `JobIdAlreadyExists`) propagate as HTTP 500 INTERNAL_ERROR per `rules/nexus-http-status-convention.md` Rule 1 — but this is a CLIENT semantic error, not a server bug. Mitigation: every admin handler MUST treat "already in target state" as success (pause-already-paused → 200 with `state: "paused"`), and "schedule not found" as 404 with `code: "SCHEDULE_NOT_FOUND"` (per the frozen NexusError taxonomy at `nexus-http-status-convention.md` Rule 1, this requires either `HandlerNotFound` reuse OR a new variant `SCHEDULE_NOT_FOUND` added to the SDK error type in the same PR per `nexus-http-status-convention.md` MUST NOT § "Add a new NexusError variant without updating both status_code() and error_code()…"). Decision: add new variant `ScheduleNotFound → 404 SCHEDULE_NOT_FOUND` in the same PR.

5. **Audit trail gap on admin actions** — Condition: an operator pauses a critical revenue-driving schedule and the action is not recorded. Consequence: a few hours later, ops asks "who paused billing.weekly_invoice?" and there is no answer. Mitigation: every mutating admin handler MUST emit a structured INFO log line per `rules/observability.md` § 4 (state transitions / auth events) with `actor_user_id`, `action`, `schedule_id`, `before_state`, `after_state`, AND emit a PACT audit envelope when PACT is configured. Read ops emit DEBUG only.

6. **Multi-instance scheduler drift** — Condition: two scheduler instances share the same SQLAlchemy job store; ops pauses a schedule via the admin API on instance A; instance B's in-memory `_schedules` dict still says enabled. Consequence: when instance B's APScheduler reloads from job store, it sees the paused state — but `list_schedules()` on instance B returns stale `enabled=True` until reload. Mitigation: `list_schedules()` already re-reads `next_run_time` from APScheduler at call time (`scheduler.py:732-739`); the admin API MUST always read state through `scheduler.list_schedules()` / `scheduler._scheduler.get_job()` — NEVER return cached `_schedules` dict directly. Document this explicitly in the handler docstrings.

7. **Cron-expression validation drift** — Condition: ops PUT a cron expression like `"0 6 * * 1-5,7"` (5-field with comma+range). Consequence: APScheduler's `CronTrigger.from_crontab` may accept it, may reject it; operator sees opaque `ValueError`. Mitigation: the `update_cron` handler MUST validate via `CronTrigger.from_crontab(expr, timezone=tz)` BEFORE writing, mirror the existing 5-field check in `schedule_cron` (`scheduler.py:542-547`), and on failure return `400 INVALID_INPUT` with the original cron string in the error message. Per `nexus-http-status-convention.md` § 5, `ValueError` from a Nexus handler maps to `400 INVALID_INPUT`.

8. **Job-store SQLite write lock contention** — Condition: a high-frequency admin caller (dashboard polling `list_schedules` every 1s) competes with the scheduler's own job-store writes. Consequence: SQLite `database is locked` errors surface intermittently. Mitigation: `list_schedules()` only reads; APScheduler's job store is WAL-mode (per `scheduler.py:_secure_init_sqlite_jobstore` lines 297-302), so reads do not block writes. The admin API SHOULD cache `list_schedules()` results for ≤2s on the read path; mutations MUST always write through. This is an optimization, not a correctness fix.

9. **Lifecycle-event hook leak via admin actions** — Condition: a user-registered `on_job_success` hook (#914) calls back into the admin API to delete the schedule that just fired. Consequence: APScheduler's listener machinery is mid-iteration; calling `cancel()` from inside a listener can corrupt the listener list. Mitigation: the admin handlers' delete operation MUST schedule the actual `_scheduler.remove_job()` call via `asyncio.get_running_loop().call_soon(...)` when invoked from within an APScheduler listener context. Detection: use `inspect.stack()` to check whether `_on_job_lifecycle_event` is on the stack; if so, defer. This is a defensive measure — most use cases will not trigger it.

10. **Migration helper assumptions about Django ORM** — Condition: a user with `django-celery-beat`-style schedules wants the migration helper. Consequence: pulling Django + django-celery-beat into the scheduler package would violate `rules/dependencies.md` (heavy optional dep). Mitigation: the migration helper takes a list of dicts (the user's caller serializes their `PeriodicTask` rows via Django, then passes the dicts to `migrate_from_celery_beat([{name, cron, enabled, kwargs}, ...])`). Kailash imports nothing Django-specific. Document the conversion shape in the helper's docstring.

## API surface

### Admin operations (each = one `@app.handler` registration)

| Operation                       | Handler name                               | Read/Write | Returns                                                                     |
| ------------------------------- | ------------------------------------------ | ---------- | --------------------------------------------------------------------------- |
| List all schedules              | `scheduler.admin.list`                     | R          | `list[ScheduleInfoDTO]`                                                     |
| Get one schedule                | `scheduler.admin.get`                      | R          | `ScheduleInfoDTO`                                                           |
| Pause a schedule                | `scheduler.admin.pause`                    | W          | `{schedule_id, state, next_run_time}`                                       |
| Resume a schedule               | `scheduler.admin.resume`                   | W          | `{schedule_id, state, next_run_time}`                                       |
| Update cron expression          | `scheduler.admin.update_cron`              | W          | `{schedule_id, cron_expression, next_run_time}`                             |
| Delete a schedule               | `scheduler.admin.delete`                   | W          | `{schedule_id, deleted: true}`                                              |
| Scheduler stats                 | `scheduler.admin.stats`                    | R          | `{total, enabled, paused, types: {cron, interval, once}, fire_times_count}` |
| Recent fires (lifecycle stream) | `scheduler.admin.recent_fires`             | R          | `list[JobEventDTO]` (last N events from #914 hooks)                         |
| Migration helper                | `scheduler.admin.migrate_from_celery_beat` | W          | `{imported: N, errors: [...]}`                                              |

`ScheduleInfoDTO` mirrors `ScheduleInfo` (`scheduler.py:326`) but JSON-serializable: `schedule_id`, `schedule_type` (str), `workflow_name`, `trigger_args` (dict), `created_at` (ISO string), `next_run_time` (ISO string or null), `enabled` (bool), `kwargs` (dict, with `_kailash_retry_spec` redacted), `retry_spec` (dict or null — `RetrySpec.__dict__` minus exception types, with `retry_on_names` / `dont_retry_on_names` for class names).

### Transports

Per Nexus's design (`packages/kailash-nexus/src/nexus/core.py:2738`):

- **HTTP**: `POST /api/handlers/scheduler.admin.<op>` with JSON body `{schedule_id, ...}`; `GET` for read ops.
- **CLI**: `nexus call scheduler.admin.list` / `nexus call scheduler.admin.pause --schedule-id=sched-abc`. Nexus's CLI channel auto-derives flag names from handler signatures.
- **MCP**: each handler is exposed as an MCP tool. Agents call `scheduler.admin.list({})` and receive structured output.

### In-process scheduler additions (load-bearing for the handlers)

Three new methods on `WorkflowScheduler` that the handlers wrap:

```python
def pause(self, schedule_id: str) -> ScheduleInfo: ...
def resume(self, schedule_id: str) -> ScheduleInfo: ...
def update_cron(self, schedule_id: str, cron_expression: str) -> ScheduleInfo: ...
```

Each delegates to APScheduler:

- `pause` → `self._scheduler.pause_job(schedule_id)`; updates `_schedules[id].enabled = False`.
- `resume` → `self._scheduler.resume_job(schedule_id)`.
- `update_cron` → validate 5-field, build new `CronTrigger`, call `self._scheduler.reschedule_job(schedule_id, trigger=new_trigger)`; refresh `_schedules[id].trigger_args` AND emit a state-transition log line per `observability.md` § 4.

A typed `ScheduleNotFoundError` (KeyError subclass + new `NexusError.ScheduleNotFound`) is raised when `schedule_id` is unknown. Per `rules/zero-tolerance.md` Rule 3a typed-delegate-guard pattern.

## Auth + governance

### Authentication (Nexus owns)

- The Nexus instance hosting these handlers MUST be constructed with `enable_auth=True` (forced when `NEXUS_ENV=production` per `nexus/core.py:351`).
- JWT middleware (`nexus.auth.jwt.JWTMiddleware`) populates `request.state.user` with an `AuthenticatedUser` carrying `roles` and `permissions`.
- The migration deprecation note at `nexus/auth/__init__.py:19-23` says auth is moving to `kailash.trust.auth`; the plan SHOULD prefer `kailash.trust.auth` imports if available at implementation time.

### Authorization (PACT or AuthGuard)

Two-layer authz:

1. **Per-handler AuthGuard (always present)** — every mutating handler is registered with `guard=AuthGuard.RequirePermission("scheduler:admin")`; read handlers with `guard=AuthGuard.RequirePermission("scheduler:read")`. AuthGuard fires before the handler runs (per `nexus/core.py:2832` — `_wrap_with_guard` wraps the handler before workflow construction so all transports get the guard).

2. **Optional PACT envelope (when configured)** — when PACT's `GovernanceEngine` is registered as a Nexus middleware, mutating handlers ALSO check the operator's envelope clearance for the `scheduler:write` action. PACT integration is opt-in: if the user has not installed `kailash-pact`, the admin API still works with AuthGuard alone.

### Audit trail

- Every mutating handler call emits a structured INFO log line via `kailash.observability.logger` with fields `actor_user_id` (from `request.state.user.user_id`), `actor_roles`, `action` (= handler name), `schedule_id`, `before_state` (snapshot of pre-mutation `ScheduleInfo`), `after_state` (post-mutation snapshot), `correlation_id` (per `observability.md` Rule 2).
- When PACT is configured, the SAME mutation also writes a PACT audit envelope through `pact.engine.GovernanceEngine.audit(...)`.
- Read handlers emit DEBUG only (no audit row per `observability.md` Rule 8 — schema-revealing field names).

## Implementation sketch

The work splits into 4 shards, each within the per-session capacity budget (`autonomous-execution.md` § Per-Session Capacity Budget: ≤500 LOC load-bearing, ≤5–10 invariants, ≤3–4 call-graph hops, describable in ≤3 sentences):

### Shard 1 — In-process scheduler additions (~250 LOC, 5 invariants)

**Files**:

- `src/kailash/runtime/scheduler.py` — add `pause()`, `resume()`, `update_cron()`, `stats()`, `recent_fires()`; add `ScheduleNotFoundError` typed exception.
- `tests/unit/runtime/test_scheduler_admin_methods.py` — Tier 1 unit tests for each method against an in-memory job store.

**Invariants**: (1) APScheduler delegation correctness; (2) `_schedules` dict stays in sync with APScheduler state; (3) `KeyError`/`JobLookupError` translates to typed `ScheduleNotFoundError`; (4) idempotency (pause-already-paused returns success); (5) cron validation matches the existing 5-field check at `scheduler.py:542-547`.

**Sentence form**: "Add three idempotent admin methods (pause/resume/update_cron), one stats method, and one recent_fires method to `WorkflowScheduler`, with typed exceptions and APScheduler delegation."

### Shard 2 — Nexus admin handler module (~300 LOC, 7 invariants)

**Files**:

- `src/kailash/runtime/scheduler_admin.py` (new) — `register_admin_handlers(app: Nexus, scheduler: WorkflowScheduler)` function that registers all handlers on the supplied Nexus app.
- `src/kailash/runtime/_admin_dto.py` (new) — `ScheduleInfoDTO`, `JobEventDTO` JSON-serializable dataclasses + `from_schedule_info(...)` / `from_job_event(...)` converters.
- `tests/integration/test_scheduler_admin_handlers.py` — Tier 2 test against real Nexus + real WorkflowScheduler + real APScheduler + temp SQLite.

**Invariants**: (1) every handler has a non-None `guard=`; (2) NexusError taxonomy preserved (404 for unknown schedule, 400 for invalid cron, 500 only for our bugs); (3) DTO redaction strips `_kailash_retry_spec` from kwargs; (4) DTO never leaks exception types as repr strings (use `__name__` instead); (5) every mutation logs at INFO with audit fields; (6) every mutation returns post-mutation state via `list_schedules()` (NOT cached `_schedules`); (7) HTTP/CLI/MCP all reach the same handler.

**Sentence form**: "Register Nexus handlers for nine admin operations under `scheduler.admin.*`, each guarded by AuthGuard, returning JSON DTOs, with structured audit logging."

### Shard 3 — NexusError variant + migration helper (~200 LOC, 4 invariants)

**Files**:

- `src/kailash/nexus_errors.py` (or wherever `NexusError` lives) — add `ScheduleNotFound` variant with `status_code() → 404` and `error_code() → "SCHEDULE_NOT_FOUND"`.
- `src/kailash/runtime/scheduler_admin.py` — wire the variant to the handler error path.
- `src/kailash/runtime/scheduler_migrate.py` (new) — `migrate_from_celery_beat(scheduler, periodic_tasks: list[dict]) -> dict` helper.
- `tests/unit/test_nexus_error_schedule_not_found.py` + `tests/integration/test_celery_beat_migration.py`.

**Invariants**: (1) variant addition follows `nexus-http-status-convention.md` MUST NOT (both `status_code()` AND `error_code()` updated in same commit); (2) migration helper depends on zero Django imports; (3) migration helper supports CRON-only PeriodicTasks in v1 (interval/clocked deferred to v2); (4) migration is idempotent — re-running with the same tasks does not duplicate.

**Sentence form**: "Add `SCHEDULE_NOT_FOUND` to the NexusError taxonomy and write a Django-free migration helper that converts a list of celery-beat-shaped dicts into Kailash schedules."

### Shard 4 — Documentation + cross-channel parity tests (~150 LOC, 3 invariants)

**Files**:

- `packages/kailash-nexus/docs/scheduler-admin.md` (new) — usage docs.
- `tests/integration/test_scheduler_admin_cross_channel.py` — same operation through HTTP, CLI, and MCP returns byte-equivalent DTO shape.
- `tests/regression/test_scheduler_admin_loc_invariants.py` — per `rules/refactor-invariants.md` (the new module's LOC ceiling).

**Invariants**: (1) HTTP/CLI/MCP return identical DTOs; (2) docs reference real handler names + status codes from the frozen `nexus-http-status-convention.md` table; (3) module sizes stay under their declared ceilings.

**Sentence form**: "Document the admin API and add a cross-channel parity test that exercises the same handler through every transport."

### Total estimate

- ~900 LOC across 4 shards, sharded by `/todos`, plan to land in 4 PRs (one per shard) so each PR stays under the 500-LOC load-bearing threshold.
- Shards 1, 3, 4 have executable feedback loops (unit + integration tests). Shard 2 has the heaviest invariant load — it is exactly at the budget cap and SHOULD NOT be expanded mid-session.

## Test plan

### Tier 2 integration tests (real Nexus, real APScheduler, real SQLite)

Per `rules/testing.md` Tier 2 (NO mocking) and `rules/orphan-detection.md` Rule 2 (every wired manager has a Tier 2 test). Per `rules/facade-manager-detection.md` Rule 2 the test file is named `test_scheduler_admin_handlers_wiring.py`.

1. **`test_admin_list_returns_all_schedules`** — Construct `WorkflowScheduler` against a temp SQLite, schedule three workflows (cron + interval + once), construct Nexus with `enable_auth=False` (test mode), register admin handlers, call `scheduler.admin.list` over HTTP — assert all three appear with correct types and `next_run_time`.
2. **`test_admin_pause_then_resume_changes_next_run_time`** — Schedule a cron at `"*/5 * * * *"`, capture `next_run_time`, call `scheduler.admin.pause`, assert `enabled=False` AND `next_run_time=None`; call `scheduler.admin.resume`, assert `enabled=True` AND new `next_run_time` is in the future.
3. **`test_admin_update_cron_changes_next_fire`** — Schedule at `"0 6 * * *"` (06:00 daily), call `update_cron(sched, "0 7 * * *")`, assert `next_run_time` advanced to the 07:00 slot. This is the brief's literal acceptance criterion.
4. **`test_admin_delete_removes_schedule`** — Delete a schedule, assert subsequent `list` excludes it AND APScheduler's `get_job(id)` returns None.
5. **`test_admin_unknown_schedule_returns_404`** — Call any operation with `schedule_id="sched-nonexistent"`, assert HTTP 404 + body `{"error": "...", "code": "SCHEDULE_NOT_FOUND"}`.
6. **`test_admin_invalid_cron_returns_400`** — Call `update_cron` with `"not a cron"`, assert HTTP 400 + body `{"error": "...", "code": "INVALID_INPUT"}`.
7. **`test_admin_idempotent_pause`** — Pause twice; assert second call returns 200 with same DTO.
8. **`test_admin_stats_reflects_state`** — Schedule N items; call `stats`; assert counts match.
9. **`test_admin_recent_fires_returns_lifecycle_events`** — Register handlers, fire schedules, call `recent_fires`; assert `JobEventDTO` shape matches #914's `JobEvent`.
10. **`test_admin_cross_channel_parity`** (Shard 4) — Call `list` over HTTP, CLI invocation, and MCP tool invocation; assert all three return byte-equivalent DTO JSON.

### Auth tests (with `enable_auth=True`)

1. **`test_admin_unauthenticated_returns_401`** — Construct Nexus with `enable_auth=True`, call admin handler with no JWT; assert 401.
2. **`test_admin_insufficient_permission_returns_403`** — JWT carries `permissions=["scheduler:read"]`; call mutating handler; assert 403.
3. **`test_admin_read_with_read_permission_succeeds`** — JWT carries `permissions=["scheduler:read"]`; call `scheduler.admin.list`; assert 200.
4. **`test_admin_admin_permission_passes_all_handlers`** — JWT carries `permissions=["scheduler:admin"]`; assert all nine handlers return 200.

### RBAC tests (PACT-integrated path, optional fixture)

When `kailash-pact` is installed, an additional fixture constructs `GovernanceEngine` and asserts that envelope clearance gates fire for mutating ops. These tests are skipped when PACT is absent (per `rules/dependencies.md` § Foundation-Only Dependencies; PACT is an optional sibling package).

### Tier 1 unit tests

Per shard 1 — unit tests against in-memory APScheduler for `pause`, `resume`, `update_cron`, `stats`, `recent_fires`, and `ScheduleNotFoundError` typed exception.

### Audit log assertion test

Per `observability.md` Rule 5 — a test that captures stdlib `logging` output during a mutation and asserts the structured fields (`actor_user_id`, `action`, `before_state`, `after_state`, `correlation_id`).

## Cross-SDK alignment

Per `rules/cross-sdk-inspection.md` Rule 1 — kailash-rs (Rust SDK) ALSO has a workflow scheduler surface. The Rust scheduler's admin API would be the symmetric feature. The Rust SDK lives in `esperie/kailash-rs` and is OUT OF SCOPE for this kailash-py session per `rules/repo-scope-discipline.md`. This plan does NOT recommend filing a kailash-rs issue from this session — that decision belongs to the user when they next open Claude Code in `kailash-rs`. Descriptive only:

- The Rust SDK's equivalent surface would expose `Scheduler::pause(id)` / `resume(id)` / `update_cron(id, expr)` plus an Axum handler module that is the Rust analog of Shard 2.
- The Rust SDK has no APScheduler — its scheduler is a native implementation, so the in-process admin methods would touch its internal job store directly rather than delegating.
- Cross-SDK semantic parity (per `rules/cross-sdk-inspection.md` Rule 3 EATP D6) requires that the JSON DTO shape returned by HTTP handlers be byte-equivalent across both SDKs. The DTOs defined in Shard 2 should be authored with this in mind so the Rust port can vendor them per `cross-sdk-inspection.md` Rule 4a (sibling-canonical fixtures vendored, not re-authored).

## Open questions for the human

These need a human gate BEFORE `/todos` so the plan does not lock in a decision the user will reverse:

1. **Permission name strings** — proposed `scheduler:read` and `scheduler:admin`. Should these be `scheduler.read` / `scheduler.admin` (dot-separated) or `kailash.scheduler.admin` (hierarchical)? The handler examples in `nexus/auth/guards.py:21` use unqualified names like `"admin"`; the handler examples elsewhere use colon-separated names like `"orgs:delete"` (`guards.py:29`). User pick.

2. **PACT integration: required or optional?** — The plan assumes PACT is optional (AuthGuard alone suffices when PACT is not installed). Alternative: require PACT for all admin operations. The brief's "Acceptance criteria" makes no PACT mention; the `framework-first.md` auth-split splits authn (Nexus) from authz (PACT) but both are framework-first defaults, not hard requirements. User pick.

3. **Admin handler namespace** — proposed `scheduler.admin.*`. Alternative names: `kailash.scheduler.*` (matches Python module path), `admin.scheduler.*` (matches `@app.handler("admin.reset", ...)` example in `core.py:2774`), or just `scheduler.*` (then read vs write split by permission). User pick — affects every URL, CLI command, MCP tool name.

4. **Migration helper scope** — v1 plan: CRON `PeriodicTask` only. Should interval and clocked PeriodicTasks be in v1 too? They double the helper's surface but match brief's "Migration helper from `django-celery-beat`'s `PeriodicTask` table" without qualifier. User pick.

5. **Multi-instance coordination** — The plan accepts the "stale list_schedules across instances until reload" behavior (failure-point #6) and documents it. Alternative: add a multi-instance coordination layer (Redis pub-sub, advisory locks). This is a much larger feature (separate session). User pick on whether to scope-add or accept current behavior.

6. **Recent-fires retention** — `scheduler.admin.recent_fires` would return the last N JobEvents. What's N? Bounded ring buffer in memory (per `rules/infrastructure-sql.md` Rule 7 bounded-stores), persistent in SQLite, or NoneType (don't ship recent_fires in v1)? User pick.

## Effort estimate

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget — autonomous execution cycles, NOT human-days.

- **Shard 1** (in-process additions + unit tests): 1 session, ~250 LOC. Feedback loop: pytest. Multiplier 3-5× applies.
- **Shard 2** (Nexus admin handlers + Tier 2 integration): 1 session, ~300 LOC. Feedback loop: pytest with real Nexus. Heaviest invariant load (7); at the budget cap.
- **Shard 3** (NexusError variant + migration helper): 1 session, ~200 LOC. Two distinct bug classes — variant addition AND migration helper. Could fold into Shard 2 if the user prefers, but separation respects the per-PR review gate.
- **Shard 4** (cross-channel parity test + docs): 1 session, ~150 LOC. Lightest shard.

**Total: 4 autonomous execution cycles**, executed serially because Shards 2-4 depend on Shard 1's surface. Could parallelize Shards 3 and 4 once Shard 2 lands. With #912 (per-task time limits, OPEN at session start) running in parallel on a different surface, no scheduling conflict — admin API is independent per the user's sequencing note in the prompt.

End-to-end real wall-clock from `/analyze` to `/release`: ~4 sessions if run serially, ~3 sessions if Shards 3+4 parallelize after Shard 2.
