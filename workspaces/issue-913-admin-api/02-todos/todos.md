# Issue #913 /todos: admin API for WorkflowScheduler

**Workspace**: `workspaces/issue-913-admin-api/`
**Branch base SHA at /todos time**: `d5d84dbd` (`main` HEAD, 2026-05-09)
**Architecture plan source**: `workspaces/issue-913-admin-api/01-analyze/architecture-plan.md`
**Sequencing**: Option B — Shard 0 launches in parallel with #912 Shard 1 NOW; Shards 1+ sequence after Shard 0 merges.

---

## Root-cause decisions (user-approved 2026-05-09)

These four decisions are baked into every shard below. Restated verbatim from the user's gate at the close of `/analyze`:

**RC1 — `**kwargs` removal scope: not applicable to #913.\*\* (Owned by #912.) The admin API does not introduce new variadic-kwargs signatures; #912's per-task time-limit work owns that surface separately.

**RC2 — `kailash.errors` namespace: not applicable to #913.** (Owned by #912; no new module, exceptions go to `sdk_exceptions.py`.) New typed exceptions for #913 (`ScheduleNotFoundError`) live in the existing scheduler exception module path; no new top-level error namespace is introduced.

**RC3 — PACT integration: REQUIRED.** Add `kailash-pact` as a required dep for kailash-nexus admin handlers. Every admin handler MUST emit a PACT envelope; `GovernanceEngine` performs RBAC + audit (per `pact-governance.md` D/T/R: Decide what op, Trust whose envelope, Record audit row). Nexus AuthGuard handles authn (token + permission string `scheduler:admin`). PACT is NOT optional. The `framework-first.md` table mandates PACT for admin/governance/RBAC/policy work.

**RC4 — `pause`/`resume`/`update_cron` scheduler methods: YES, AS #913 Shard 0.** Per `autonomous-execution.md` MUST Rule 4 (Fix-Immediately within shard budget). Land 3 new methods directly on `WorkflowScheduler` in `src/kailash/runtime/scheduler.py`: `pause(schedule_id)`, `resume(schedule_id)`, `update_cron(schedule_id, new_cron_expr)`. ~150 LOC, ≤3 invariants per method. Each method gets a Tier-2 integration test (start scheduler → schedule job → call method → assert observable state change → cancel). Shard 0 launches BEFORE any Nexus handler shard.

---

## Brief-gap verification

Verified at `/todos` time against `src/kailash/runtime/scheduler.py` at SHA `d5d84dbd`:

| Method           | Present? | Evidence                                                                      |
| ---------------- | -------- | ----------------------------------------------------------------------------- |
| `schedule_cron`  | YES      | `src/kailash/runtime/scheduler.py:499`                                        |
| `cancel`         | YES      | `src/kailash/runtime/scheduler.py:703`                                        |
| `list_schedules` | YES      | `src/kailash/runtime/scheduler.py:725`                                        |
| `pause`          | **NO**   | `grep -n 'def pause' src/kailash/runtime/scheduler.py` returns no match       |
| `resume`         | **NO**   | `grep -n 'def resume' src/kailash/runtime/scheduler.py` returns no match      |
| `update_cron`    | **NO**   | `grep -n 'def update_cron' src/kailash/runtime/scheduler.py` returns no match |

**Conclusion**: The brief's framing is accurate — `WorkflowScheduler` exposes add/cancel/list today, but lacks the three modify operations the admin API requires. Shard 0 closes that gap before Nexus handlers can wrap them.

---

## Framework choice — Nexus + PACT

Per `rules/framework-first.md` § ABSOLUTE Work-Domain → Framework Binding:

- **HTTP API, REST, gateway, middleware, login, sessions, websockets** → **Nexus** (MANDATORY)
- **Governance, RBAC, policy, access control, envelopes, audit** → **PACT** (MANDATORY)
- **MCP servers, tools, resources, transports, exposing APIs as LLM tools** → **MCP** (MANDATORY) — auto-included via Nexus's `@app.handler` multi-channel surface

**Auth split (frozen)**: Nexus owns authentication (JWT token validation, session population). PACT owns authorization (RBAC, envelope-based clearance, structured audit). Per RC3 above, PACT is required, not optional.

Raw FastAPI / Flask / aiohttp is BLOCKED. Optional-PACT codepaths are BLOCKED.

The in-process scheduler additions (Shard 0 — `pause`/`resume`/`update_cron`) are plain Python on `WorkflowScheduler`; they are NOT a Nexus or PACT concern at the runtime layer. The Nexus handler module (Shards 1+) wraps these methods.

---

## Shard plan

### Shard 0 — In-process scheduler methods (`pause` / `resume` / `update_cron`)

**Value-anchor**: User's brief gate at close of `/analyze` (RC4, 2026-05-09): "land 3 new methods directly on `WorkflowScheduler` … BEFORE any Nexus handler shard." The Nexus admin handlers cannot wrap operations the runtime does not expose; Shard 0 closes the runtime-surface gap that makes the entire admin-API workstream possible. Without these methods, every operator action (pause a runaway billing job, update a cron after DST change, resume after maintenance) is impossible without a process restart — the brief's literal acceptance criterion fails.

**Files touched**:

- `src/kailash/runtime/scheduler.py` — add three new methods on `WorkflowScheduler` class.
- `src/kailash/runtime/_scheduler_exceptions.py` (new, OR add to existing exception module) — `ScheduleNotFoundError(KeyError)` typed exception.
- `tests/integration/runtime/test_scheduler_admin_methods.py` (new) — 3 Tier-2 integration tests exercising real APScheduler + temp SQLite job store.
- `tests/unit/runtime/test_scheduler_admin_methods_unit.py` (new) — 3 Tier-1 unit tests for fast feedback.

**Method signatures (frozen at /todos time)**:

```python
def pause(self, schedule_id: str) -> ScheduleInfo: ...
def resume(self, schedule_id: str) -> ScheduleInfo: ...
def update_cron(self, schedule_id: str, cron_expression: str) -> ScheduleInfo: ...
```

**Invariants (≤3 per method, 9 total — within shard budget)**:

`pause(schedule_id)`:

1. **Idempotency** — calling `pause` on an already-paused schedule returns success with `enabled=False`; no APScheduler exception raised.
2. **No-effect-when-already-target** — second call MUST NOT re-emit a state-transition log line; INFO-level log fires once on the first transition only.
3. **Typed-error on unknown ID** — `schedule_id` not in `_schedules` raises `ScheduleNotFoundError`, NOT bare `KeyError` or `JobLookupError`.

`resume(schedule_id)`: 4. **Idempotency** — calling `resume` on an already-running schedule returns success with `enabled=True`; no exception. 5. **Preserves-cron-next-fire-on-resume** — after pause→resume, `next_run_time` is computed against the trigger's `next_fire_time(now)`, not the pre-pause stored value; verified by asserting `next_run_time > now`. 6. **Typed-error on unknown ID** — same as pause, raises `ScheduleNotFoundError`.

`update_cron(schedule_id, cron_expression)`: 7. **Cron-validation-before-write** — invalid cron raises `ValueError` BEFORE any `_schedules` mutation or APScheduler call; mirrors the 5-field check at `scheduler.py:542-547`. 8. **Atomic state update** — on success, BOTH `_schedules[id].trigger_args` AND APScheduler's stored trigger reflect the new cron; verified by asserting `next_run_time` advanced to the new slot. 9. **Typed-error on unknown ID** — raises `ScheduleNotFoundError`; ValueError reserved for invalid cron.

**LOC estimate**: ~150 LOC scheduler.py (3 methods × ~40 LOC each + ~30 LOC for typed-exception module + observability).

**Tests required (Tier-2 integration tests, real APScheduler + temp SQLite job store, NO mocking per `rules/testing.md`)**:

1. `test_admin_pause_then_resume_changes_next_run_time` — schedule cron `*/5 * * * *`, capture `next_run_time`, call `pause` (assert `enabled=False, next_run_time=None`), call `resume` (assert `enabled=True, next_run_time > now`).
2. `test_admin_update_cron_advances_next_fire` — schedule at `0 6 * * *`, call `update_cron(sched, "0 7 * * *")`, assert `next_run_time` advanced to the 07:00 slot. Brief's literal acceptance criterion.
3. `test_admin_idempotent_pause_and_unknown_id` — pause twice (second is no-op success); call `pause("sched-nonexistent")` → assert `ScheduleNotFoundError` raised; same for `resume` and `update_cron`.

**Tier-1 unit tests (in-memory MemoryJobStore for fast iteration)**:

- `test_pause_idempotent_unit` — fast structural check.
- `test_update_cron_validates_5_field_unit` — invalid-cron `ValueError` BEFORE `_schedules` mutation (assert dict unchanged on raise).
- `test_schedule_not_found_error_is_subclass_of_keyerror` — typed exception relationship.

**Dependencies**:

- None blocking (Shard 0 is the prereq for everything else).
- Lifecycle event hooks from #914 (`_hooks_job_success` / `_hooks_job_error`) are NOT required for Shard 0; Shard 0 only adds runtime methods. `recent_fires` admin handler in Shards 1+ depends on #914.

**Worktree assignment**:

- **Branch**: `feat/issue-913-shard-0-scheduler-methods`
- **Worktree path**: `.claude/worktrees/issue-913-shard-0/` (per `worktree-isolation.md` Rules 1, 5, 6)
- **Base SHA**: `d5d84dbd` (`main`, pinned at /todos time per Rule 5)
- **Sequencing**: parallel with `#912 Shard 1` (independent surface — #912 touches per-task time limits in a different scheduler region; Shard 0 adds new methods, no edit-overlap)
- **Pre-flight verify at launch**: `git rev-parse main` matches `d5d84dbd` OR pin to current main HEAD before worktree creation

---

### Shard 1 — Nexus handler skeleton + AuthGuard + PACT envelope wiring

**Value-anchor**: Architecture plan § "API surface" + RC3 (user-approved 2026-05-09): every admin handler routes through Nexus's `@app.handler` multi-channel surface AND through PACT's `GovernanceEngine.verify_action()` for envelope-based RBAC + audit. Without this scaffold, every handler in Shards 2+ would reinvent auth/audit wiring (the multi-site kwarg failure mode `rules/security.md` § "Multi-Site Kwarg Plumbing" warns against). Centralizing auth + envelope construction in one wrapper closes that class structurally.

**Files touched**:

- `packages/kailash-nexus/src/nexus/admin/__init__.py` (new module) — package exports.
- `packages/kailash-nexus/src/nexus/admin/scheduler_handlers.py` (new) — `register_scheduler_admin_handlers(app, scheduler, governance_engine)` registration function + envelope-construction helper.
- `packages/kailash-nexus/src/nexus/admin/_envelope.py` (new) — PACT envelope construction helper (D/T/R address from JWT subject, action from handler name, context dict).
- `packages/kailash-nexus/src/nexus/admin/_dto.py` (new) — `ScheduleInfoDTO` JSON-serializable dataclass + `from_schedule_info()` converter (redacts `_kailash_retry_spec` per architecture plan § "API surface").
- `packages/kailash-nexus/src/nexus/errors.py` — add `ScheduleNotFoundError` variant (404 / `SCHEDULE_NOT_FOUND`).
- `packages/kailash-nexus/pyproject.toml` — add `kailash-pact` to required `dependencies`.
- `packages/kailash-nexus/src/nexus/admin/tests/test_envelope_construction_unit.py` (new) — Tier-1 unit tests.
- `tests/integration/nexus/test_scheduler_admin_authguard_wiring.py` (new) — Tier-2 AuthGuard wiring test.
- `tests/integration/nexus/test_scheduler_admin_pact_envelope_wiring.py` (new) — Tier-2 PACT envelope construction + audit row test.

**Invariants (8 total, at-budget)**:

1. **AuthGuard non-None** — every handler registration MUST pass a non-None `guard=AuthGuard.RequirePermission(...)`; registration code raises `ConfigError` if the guard is None at `register_scheduler_admin_handlers()` time. Closes the unauthenticated-endpoint failure mode (architecture plan § FP-1).
2. **Envelope construction always fires** — every mutating handler call MUST construct a PACT envelope BEFORE the scheduler op runs; verified by asserting `governance_engine.verify_action()` was called for every mutation in the Tier-2 test.
3. **Envelope verdict is BLOCKED-fail-closed** — `governance_engine.verify_action()` returning anything other than ALLOWED (or its non-blocked equivalents) MUST short-circuit with HTTP 403 + `code: "FORBIDDEN"`; the underlying scheduler method MUST NOT run.
4. **Audit row exists post-mutation** — every successful mutating handler emits BOTH a structured INFO log line AND a PACT audit envelope; verified by asserting an audit-store row with `action`, `actor_user_id`, `before_state`, `after_state`, `correlation_id` (per `rules/observability.md` Rule 2).
5. **DTO redaction** — `ScheduleInfoDTO.from_schedule_info()` strips `_kailash_retry_spec` from `kwargs`, replacing with the spec's `__dict__` minus exception-type repr (`retry_on_names` / `dont_retry_on_names` only).
6. **Manager-shape Tier-2 wiring test** — per `rules/facade-manager-detection.md` MUST Rule 1, the `governance_engine` is a `*Engine` shape; the wiring test imports it through Nexus, runs a real op, asserts an audit row exists in the real audit store.
7. **Read-vs-write permission split** — `scheduler.admin.list` / `.get` / `.stats` use `AuthGuard.RequirePermission("scheduler:read")`; `pause` / `resume` / `update_cron` / `delete` use `"scheduler:admin"`.
8. **NexusError taxonomy preserved** — `ScheduleNotFoundError` raised by Shard-0 methods maps to HTTP 404 with body `{"error": "...", "code": "SCHEDULE_NOT_FOUND"}` per `rules/nexus-http-status-convention.md` Rules 1 + 2.

**LOC estimate**: ~280 LOC across new module + envelope helper + DTO + error variant + tests (at the per-shard cap; do NOT expand mid-session per `rules/autonomous-execution.md`).

**Tests required (Tier-2, real Nexus + real WorkflowScheduler + real GovernanceEngine + temp SQLite, NO mocking)**:

1. `test_authguard_blocks_unauthenticated_request` — Nexus with `enable_auth=True`; call admin handler with no JWT → assert 401.
2. `test_authguard_blocks_insufficient_permission` — JWT with `permissions=["scheduler:read"]`; call mutating handler → assert 403.
3. `test_pact_envelope_constructed_for_every_mutation` — call `pause` over HTTP; assert `governance_engine` recorded a `verify_action(role_address, action="scheduler.admin.pause", context={...})` call.
4. `test_pact_audit_row_persisted_post_mutation` — call `pause` over HTTP; assert one PACT audit-store row exists with the expected `actor_user_id`, `before_state`, `after_state`.
5. `test_pact_blocked_verdict_short_circuits_mutation` — construct an envelope that BLOCKs `scheduler:write`; call `pause`; assert HTTP 403 AND assert the underlying schedule's `enabled` did NOT change (mutation never ran).
6. `test_schedule_not_found_returns_404_with_code` — call any handler with `schedule_id="sched-nonexistent"`; assert HTTP 404 + body `{"error": "...", "code": "SCHEDULE_NOT_FOUND"}` per the frozen taxonomy.
7. `test_dto_redacts_retry_spec` — schedule with `_kailash_retry_spec` in kwargs; call `list`; assert response DTO does not contain that key, and `retry_spec` field reflects only `retry_on_names` / `dont_retry_on_names` (not exception class repr).
8. `test_governance_engine_wiring_through_facade` — per `rules/facade-manager-detection.md` Rule 1; imports `governance_engine` through Nexus's admin module, runs a real mutation, asserts the engine actually fired (manager-shape wiring test).

**Dependencies**:

- **Shard 0 merged** — handlers cannot wrap `pause`/`resume`/`update_cron` until they exist on `WorkflowScheduler`.
- `kailash-pact` package available in monorepo (already present at `packages/kailash-pact/`); ADD as required dep in `kailash-nexus/pyproject.toml`.
- `GovernanceEngine` from `kailash.trust.pact.engine` (lives at `src/kailash/trust/pact/engine.py:196`).
- Nexus `AuthGuard.RequirePermission` (lives at `packages/kailash-nexus/src/nexus/auth/guards.py:117, 239, 258`).

**Worktree assignment**:

- **Branch**: `feat/issue-913-shard-1-nexus-pact-skeleton`
- **Worktree path**: `.claude/worktrees/issue-913-shard-1/`
- **Base SHA**: HEAD of `main` after Shard 0 merges (pin at launch time, NOT at /todos time, per `rules/specs-authority.md` MUST Rule 5c amend-at-launch).
- **Sequencing**: serial AFTER Shard 0 merges to main.

---

### Shard 2 — Read-side admin handlers (list / get / stats)

**Value-anchor**: Architecture plan § "API surface" — operators need to see what's scheduled before they can act. The brief's first acceptance criterion ("list, enable/disable, update cron, delete schedules") opens with list. Read handlers are the most-called surface (dashboard polling) and the lowest-blast-radius group, so they validate the Shard 1 scaffold under load before any mutating handler ships.

**Files touched**:

- `packages/kailash-nexus/src/nexus/admin/scheduler_handlers.py` — implement 3 handlers (`scheduler.admin.list`, `.get`, `.stats`).
- `packages/kailash-nexus/src/nexus/admin/_dto.py` — extend with `StatsDTO`.
- `tests/integration/nexus/test_scheduler_admin_read_handlers.py` (new) — Tier-2 read-handler integration tests.

**Invariants (5)**:

1. **Always read through `list_schedules()`** — handlers MUST call `scheduler.list_schedules()` (which re-reads `next_run_time` from APScheduler at call time per `scheduler.py:732-739`); MUST NOT return cached `_schedules` dict directly. Closes the multi-instance drift FP-6.
2. **Read permission only** — all 3 handlers register with `AuthGuard.RequirePermission("scheduler:read")`.
3. **DEBUG-only audit** — read handlers emit DEBUG (NOT INFO/WARN) per `rules/observability.md` Rule 8 (schema-revealing field names at DEBUG); no PACT audit envelope written for read ops (PACT audit rows are for state changes only).
4. **HTTP/CLI/MCP parity** — same handler responds correctly to all three transports; verified by Tier-2 test that calls `list` over HTTP, then over the CLI channel, then via MCP tool, and asserts byte-equivalent DTO output.
5. **Stats counts match list output** — `stats` returns `{total, enabled, paused, types: {cron, interval, once}, fire_times_count}` consistent with the same scheduler's `list` output (no parallel state).

**LOC estimate**: ~180 LOC (3 read handlers + DTO + tests).

**Tests required**:

1. `test_admin_list_returns_all_schedules` — schedule three workflows (cron + interval + once), call `list` → assert all three present with correct types and `next_run_time`.
2. `test_admin_get_returns_one_schedule` — `get(sched_id)` returns the same DTO as the matching entry in `list`.
3. `test_admin_stats_reflects_state` — schedule N items, pause some, call `stats` → assert counts match `list` output.
4. `test_admin_list_cross_channel_parity` — same call over HTTP, CLI, MCP returns byte-equivalent JSON.
5. `test_admin_read_does_not_emit_pact_audit_envelope` — call `list`; assert audit store has zero new rows.

**Dependencies**: Shard 1 merged (AuthGuard + PACT scaffold + DTO).

**Worktree assignment**:

- **Branch**: `feat/issue-913-shard-2-read-handlers`
- **Worktree path**: `.claude/worktrees/issue-913-shard-2/`
- **Base SHA**: HEAD of `main` after Shard 1 merges.
- **Sequencing**: serial AFTER Shard 1.

---

### Shard 3 — Write-side admin handlers (pause / resume / update_cron / delete)

**Value-anchor**: Architecture plan § "API surface" + brief's literal acceptance criteria. Mutating operations are why operators come to the admin API — pausing a runaway billing job at 03:00, updating a cron after a DST change, deleting a deprecated schedule. Without these, the workstream's brief is unmet.

**Files touched**:

- `packages/kailash-nexus/src/nexus/admin/scheduler_handlers.py` — implement 4 mutating handlers.
- `tests/integration/nexus/test_scheduler_admin_write_handlers.py` (new) — Tier-2 write-handler integration tests.

**Invariants (7)**:

1. **Admin permission** — all 4 handlers register with `AuthGuard.RequirePermission("scheduler:admin")`.
2. **PACT envelope for every mutation** — `governance_engine.verify_action()` fires before scheduler op (inherited from Shard 1 scaffold).
3. **Idempotency on ALREADY-IN-TARGET-STATE** — `pause` on already-paused returns 200 with current DTO (NOT a 5xx); same for `resume` on already-running. Closes FP-4.
4. **404 on unknown ID** — every handler returning 404 with `code: "SCHEDULE_NOT_FOUND"` (inherited from Shard 1).
5. **400 on invalid cron** — `update_cron` validates BEFORE writing; invalid cron returns 400 with `code: "INVALID_INPUT"` (per `rules/nexus-http-status-convention.md` Rule 5 legacy contract). Cites the original cron string in the error message.
6. **Response includes `next_run_time` AND `in_flight_run_ids`** — every successful mutation returns the post-mutation DTO with new `next_run_time` plus any `in_flight_run_ids` (run_ids currently executing the schedule's previous trigger). Closes FP-3 mutation-during-fire footgun.
7. **State-transition log + audit on EVERY mutation** — INFO log with `actor_user_id`, `action`, `before_state`, `after_state`, `correlation_id`; PACT audit envelope persisted (per `rules/observability.md` Rule 4 + RC3).

**LOC estimate**: ~220 LOC (4 mutating handlers + tests).

**Tests required**:

1. `test_admin_pause_changes_state` — call `pause`, assert `enabled=False, next_run_time=None`, audit row exists.
2. `test_admin_resume_recomputes_next_run_time` — pause then resume, assert `next_run_time > now`.
3. `test_admin_update_cron_changes_next_fire` — change cron from `0 6 * * *` to `0 7 * * *`, assert `next_run_time` advances to 07:00 slot. Brief's literal acceptance.
4. `test_admin_delete_removes_schedule` — call `delete(sched)`, assert subsequent `list` excludes it AND APScheduler's `get_job(id)` returns None.
5. `test_admin_idempotent_pause_returns_200` — pause twice, second call returns 200 with same DTO; audit row count = 1 (only first-transition logs).
6. `test_admin_invalid_cron_returns_400_with_input_code` — call `update_cron(sched, "not a cron")`, assert HTTP 400 + body `{"error": "...", "code": "INVALID_INPUT"}`.
7. `test_admin_mutation_during_in_flight_fire` — start a long-running schedule, call `update_cron` mid-flight, assert response includes `in_flight_run_ids` populated (not empty).
8. `test_admin_pact_blocked_verdict_short_circuits_delete` — envelope BLOCKs scheduler:write, call `delete`, assert 403 AND schedule still exists.

**Dependencies**: Shard 2 merged (read handlers proven; scaffold validated under read-load).

**Worktree assignment**:

- **Branch**: `feat/issue-913-shard-3-write-handlers`
- **Worktree path**: `.claude/worktrees/issue-913-shard-3/`
- **Base SHA**: HEAD of `main` after Shard 2 merges.
- **Sequencing**: serial AFTER Shard 2.

---

### Shard 4 — Migration helper (`migrate_from_celery_beat`)

**Value-anchor**: Architecture plan § "API surface" + brief's optional acceptance criterion ("Migration helper from `django-celery-beat`'s `PeriodicTask` table"). Operators with existing celery-beat deployments are the SDK's natural conversion audience; without this helper, every migration is a hand-rolled script that drifts. The helper imports zero Django code (per architecture plan FP-10) — operators serialize their `PeriodicTask` rows in their own Django process and pass the dicts to the helper.

**Files touched**:

- `packages/kailash-nexus/src/nexus/admin/scheduler_migrate.py` (new) — `migrate_from_celery_beat(scheduler, periodic_tasks: list[dict]) -> dict`.
- `packages/kailash-nexus/src/nexus/admin/scheduler_handlers.py` — register `scheduler.admin.migrate_from_celery_beat` handler wrapping the helper.
- `tests/integration/nexus/test_scheduler_admin_migration.py` (new) — Tier-2 migration tests.

**Invariants (4)**:

1. **Zero Django imports** — `grep -n 'import django\|from django' packages/kailash-nexus/src/nexus/admin/scheduler_migrate.py` returns no matches.
2. **CRON-only in v1** — interval / clocked PeriodicTasks raise `ValueError` with a clear "deferred to v2" message; the helper's docstring documents the supported shape.
3. **Idempotent re-run** — calling `migrate_from_celery_beat` twice with the same `periodic_tasks` list does NOT duplicate schedules (verified by asserting `list_schedules()` count unchanged on second call).
4. **Admin permission** — handler registered with `AuthGuard.RequirePermission("scheduler:admin")` (mutation).

**LOC estimate**: ~170 LOC (helper + handler + tests).

**Tests required**:

1. `test_migrate_from_celery_beat_imports_cron_tasks` — pass 3 dicts shaped like Django `PeriodicTask` rows (CRON), assert 3 schedules registered with correct cron expressions.
2. `test_migrate_helper_is_idempotent` — call twice with same input; second call returns `{imported: 0, errors: []}` with no duplicate schedules.
3. `test_migrate_interval_task_returns_error_with_v2_note` — pass an interval-shaped dict; assert it appears in the `errors:` list with a "deferred to v2" message.
4. `test_migrate_helper_imports_no_django` — grep test runs at test time as a structural invariant.

**Dependencies**: Shard 3 merged (write handlers exist; migration helper is just bulk `schedule_cron` calls with idempotency).

**Worktree assignment**:

- **Branch**: `feat/issue-913-shard-4-migrate-helper`
- **Worktree path**: `.claude/worktrees/issue-913-shard-4/`
- **Base SHA**: HEAD of `main` after Shard 3 merges.
- **Sequencing**: serial AFTER Shard 3 (could parallelize with a hypothetical Shard 5 docs-shard if desired; see Open Questions Q4).

---

## Tier-2 test plan summary

Per `rules/testing.md` Tier 2 (NO mocking) + `rules/orphan-detection.md` Rule 2 (every wired manager has a Tier 2 test) + `rules/facade-manager-detection.md` Rule 2 (test file naming):

**Scheduler-method tests** (Shard 0):

- `tests/integration/runtime/test_scheduler_admin_methods.py` — pause/resume/update_cron/idempotency/typed-error coverage against real APScheduler + temp SQLite.

**AuthGuard tests** (Shard 1):

- `tests/integration/nexus/test_scheduler_admin_authguard_wiring.py` — 401/403 paths against real Nexus with `enable_auth=True`.

**PACT envelope + audit tests** (Shard 1):

- `tests/integration/nexus/test_scheduler_admin_pact_envelope_wiring.py` — envelope construction, BLOCKED-verdict short-circuit, audit-row persistence.

**Read handler tests** (Shard 2):

- `tests/integration/nexus/test_scheduler_admin_read_handlers.py` — list/get/stats + cross-channel parity (HTTP/CLI/MCP).

**Write handler tests** (Shard 3):

- `tests/integration/nexus/test_scheduler_admin_write_handlers.py` — pause/resume/update_cron/delete + idempotency + 404/400 error variants.

**Migration tests** (Shard 4):

- `tests/integration/nexus/test_scheduler_admin_migration.py` — CRON imports + idempotency + interval-deferred behavior.

**Manager-shape wiring test** (per `rules/facade-manager-detection.md` Rule 2):

- `tests/integration/nexus/test_scheduler_admin_governance_engine_wiring.py` — exercises `governance_engine` end-to-end; named per the rule's `_wiring.py` convention.

---

## NexusError taxonomy update

Per `rules/nexus-http-status-convention.md` MUST NOT clause ("Add a new `NexusError` variant without updating both `status_code()` and `error_code()` in the SDK in the same commit"):

**New variant** (lands in Shard 1, single commit):

| `NexusError` variant | HTTP status | Error code (JSON body) |
| -------------------- | ----------- | ---------------------- |
| `ScheduleNotFound`   | 404         | `SCHEDULE_NOT_FOUND`   |

**Implementation**: subclass `NexusError` in `packages/kailash-nexus/src/nexus/errors.py` with `status_code: int = 404` and `error_code: str = "SCHEDULE_NOT_FOUND"`. Mirror the existing `NotFoundError` (line 130, status 404, code `not_found`) shape. Body shape preserved bit-for-bit per Rule 2.

**Reuse vs new**: the architecture plan (§ FP-4) considered reusing `HandlerNotFound` but rejected it because operators reading the dashboard `code: "HANDLER_NOT_FOUND"` would investigate Nexus routing, not scheduler state. Adding the variant is correct; the cost is one row in the frozen taxonomy.

---

## Dependency declarations

**`kailash-pact` becomes a required dep for kailash-nexus admin handlers** (RC3, lands in Shard 1):

`packages/kailash-nexus/pyproject.toml` — add `kailash-pact` to the `dependencies` list (NOT to `[project.optional-dependencies.dev]` per `rules/python-environment.md` Rule 4 — sub-package test deps stay in their own pyproject; the runtime dep belongs in the runtime `dependencies` list).

```toml
# kailash-nexus/pyproject.toml
[project]
dependencies = [
    "kailash-pact >= <current-min-version>",   # required for admin handlers (PACT envelope + audit)
    # ... other deps ...
]
```

**Why required, not optional**: Per RC3, every admin handler MUST emit a PACT envelope. Marking PACT optional would create a silent-fallback path where the handler runs without envelope construction when PACT is absent — exactly the failure mode `rules/zero-tolerance.md` Rule 3 + `rules/security.md` § "Multi-Site Kwarg Plumbing" prohibit. Required-dep makes the contract explicit at install time.

**`apscheduler`** — already a kailash-runtime dep; no change.

**No phantom transitive caps** — per `rules/dependencies.md` § "Phantom Transitive Deps" — kailash-nexus does not directly import APScheduler; the constraint stays in kailash-runtime.

---

## Cross-SDK alignment notes (descriptive only)

Per `rules/repo-scope-discipline.md` — kailash-rs (Rust SDK) ALSO has a workflow scheduler surface. The Rust scheduler's admin API would be the symmetric feature, but **filing a kailash-rs issue from THIS session is BLOCKED**. That decision belongs to the user when they next open Claude Code in `kailash-rs`.

Descriptive observations only:

- The Rust SDK's equivalent surface would expose `Scheduler::pause(id)` / `resume(id)` / `update_cron(id, expr)` plus an Axum (or equivalent) handler module that is the Rust analog of Shard 1+.
- The Rust SDK has no APScheduler — its scheduler is a native implementation, so the in-process admin methods would touch its internal job store directly rather than delegating to a third-party library.
- Cross-SDK semantic parity (per `rules/cross-sdk-inspection.md` § EATP D6 and Rule 4a) requires the JSON DTO shape returned by HTTP handlers to be byte-equivalent across both SDKs. The DTOs defined in Shard 1 should be authored with this in mind so the Rust port can vendor them per `cross-sdk-inspection.md` Rule 4a (sibling-canonical fixtures vendored, not re-authored).
- Status taxonomy parity: `ScheduleNotFound → 404 SCHEDULE_NOT_FOUND` should be the same row in the Rust `NexusError` enum when that work happens upstream.

These notes are workspace-record material only. No issue filing, no upstream action from this session.

---

## Open questions for human gate before /implement

These are the BLOCKING-class questions — items that, if reversed by the user post-`/todos`, require a plan rewrite. Architecture-plan § "Open questions" had 6 questions; RC1–RC4 closed two of them (Q2 PACT-required and Q4 migration-helper-scope). Three remain:

**Q1 — Permission name strings**: Proposed `scheduler:admin` and `scheduler:read` (colon-separated, matching the existing `orgs:delete` example at `packages/kailash-nexus/src/nexus/auth/guards.py:29`). Alternatives: `scheduler.admin` (dot-separated) or `kailash.scheduler.admin` (hierarchical).

I recommend **`scheduler:admin` and `scheduler:read`** (colon-separated, matching existing Nexus convention). Implications: every admin handler registration uses this pair; migration tests assert both strings; downstream consumers' RBAC config files MUST use the same form. Pros: matches existing Nexus AuthGuard examples (`orgs:delete`, `agents:create`); operators learn one convention. Cons: differs from Python module path (`kailash.scheduler.admin`), so operators reading code may briefly mis-spell the permission. Recommendation stands because in-codebase precedent outweighs the path-vs-permission cosmetic mismatch.

**Q2 — Admin handler namespace**: Proposed `scheduler.admin.*` (e.g., `scheduler.admin.list`, `scheduler.admin.pause`). Alternatives: `kailash.scheduler.*` (matches Python module path), `admin.scheduler.*` (matches `@app.handler("admin.reset", ...)` example at `packages/kailash-nexus/src/nexus/core.py:2774`), or `scheduler.*` (read vs write split by permission alone, no `admin.` segment).

I recommend **`scheduler.admin.*`** (e.g., `scheduler.admin.list`, `scheduler.admin.pause`). Implications: every URL becomes `/api/handlers/scheduler.admin.<op>`; every CLI command becomes `nexus call scheduler.admin.<op>`; every MCP tool name carries `scheduler.admin.` prefix. Pros: clear separation between user-facing scheduler operations (none today) and admin operations; matches the `admin.reset` example precedent in core.py:2774. Cons: one extra segment in every URL/command/tool name (mild verbosity). Recommendation stands — the `.admin.` segment is the operator's signal that "this is a privileged surface."

**Q3 — Recent-fires retention scope**: The architecture plan (§ "API surface") includes `scheduler.admin.recent_fires` returning the last N JobEvents from #914's lifecycle hooks. Open: what is N? Bounded ring buffer in memory (per `rules/infrastructure-sql.md` Rule 7 bounded-stores), persistent in SQLite, or NOT shipped in v1 (defer to v2)?

I recommend **defer `recent_fires` to a v2 follow-up issue, drop from #913 scope**. Implications: Shard 2 (read handlers) ships only `list` / `get` / `stats`, not `recent_fires`; the architecture plan's `JobEventDTO` is unused in v1; #914 lifecycle hooks remain a separate workstream until v2. Pros: removes the unanswered N-question that would otherwise gate Shard 2; respects per-session capacity budget (Shard 2 stays at ~180 LOC instead of growing to ~270 with ring-buffer plumbing); brief's acceptance criteria do NOT mention recent-fires (it's a stretch goal from the architecture plan, not the user's brief). Cons: operators wanting "what fired in the last hour" must wait for v2; the `JobEventDTO` work in this plan becomes orphaned (delete it from this plan's deliverables — see `rules/orphan-detection.md` Rule 3). Recommendation stands because Q3 is unanswerable today (in-memory N is a design call the user has not made) and shipping without `recent_fires` does not break the brief.

---

## Effort estimate

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget — autonomous execution cycles, NOT human-days:

- **Shard 0** (scheduler methods + Tier-2 tests, parallel with #912 Shard 1): 1 session, ~150 LOC, 9 invariants. Feedback loop: pytest. Multiplier 3-5× applies (real APScheduler is fast).
- **Shard 1** (Nexus + AuthGuard + PACT + DTO + error variant): 1 session, ~280 LOC, 8 invariants. AT THE BUDGET CAP — heaviest invariant load. Do NOT expand mid-session.
- **Shard 2** (read handlers): 1 session, ~180 LOC, 5 invariants. Light shard.
- **Shard 3** (write handlers): 1 session, ~220 LOC, 7 invariants. Mid-budget.
- **Shard 4** (migration helper): 1 session, ~170 LOC, 4 invariants. Light shard.

**Total: 5 autonomous execution cycles**, with Shard 0 running in parallel with #912 Shard 1 (saves 1 wall-clock unit).

End-to-end real wall-clock from this `/todos` to `/release`:

- **Serial path**: ~5 sessions (Shard 0 → Shard 1 → Shard 2 → Shard 3 → Shard 4).
- **Parallel-with-#912 path**: ~5 sessions still (Shard 0 lives in the same wall-clock unit as #912 Shard 1; subsequent shards are sequential because Shards 2–4 each depend on the prior shard's surface).
- **Aggressive parallel**: Shards 2 (read) and 4 (migration helper) could parallelize after Shard 1 ships, since Shard 4's helper is bulk `schedule_cron` calls with idempotency — does not require Shard 3's mutating handlers. That brings the wall-clock to ~4 sessions if the user authorizes a 2-shard wave per `rules/worktree-isolation.md` Rule 4 (≤3 in a wave).

**Risk class**: Shard 1 is the highest-risk shard (8 invariants at the cap, new module, new dep, new error variant, multi-site kwarg plumbing through every handler). If Shard 1 takes 1.5 sessions, the total slips to ~5.5–6 — within tolerance.

---

## Self-attestation — value-anchor + dependency receipts

Per `rules/value-prioritization.md` MUST Rule 2, every shard above carries a value-anchor citing a Rule-1 user-anchored source:

- Shard 0: user's RC4 gate of 2026-05-09.
- Shard 1: architecture plan § "API surface" + RC3 user gate.
- Shard 2: architecture plan § "API surface" + brief's literal acceptance criterion ("list").
- Shard 3: architecture plan § "API surface" + brief's literal acceptance criterion ("enable/disable, update cron, delete").
- Shard 4: architecture plan § "API surface" + brief's optional acceptance criterion ("Migration helper").

Per `rules/specs-authority.md` MUST Rule 5c, the orchestrator at /implement launch time MUST cross-check todo claims against the then-current canonical spec AND prior merged shards' state — amend at launch if drift exists. Any drift between this /todos plan and main HEAD at launch time is the orchestrator's responsibility to reconcile in the launch prompt, NOT to leave for the agent to discover mid-implementation.

Per `rules/upstream-issue-hygiene.md` — NO upstream issue filing from this /todos session. Cross-SDK alignment notes are descriptive only; they do not authorize action in this or any other repo session.
