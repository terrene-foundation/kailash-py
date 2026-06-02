# Brief — #938 django-celery-beat PeriodicTask migration helper

**Source issue:** terrene-foundation/kailash-py#938 (follow-up to #913 AC4)

## Verified prerequisites (2026-06-02 — all met)

| Issue assumption                                                         | Verified state                                                                                  | Disposition                                                                                                  |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| PR #936 ships `SchedulerAdminAPI`                                        | **MERGED** 2026-05-10; `src/kailash/runtime/scheduler_admin.py`                                 | available                                                                                                    |
| `SchedulerAdminAPI.disable_schedule` exists                              | **CONFIRMED** `scheduler_admin.py:297`                                                          | use for `enabled=False` rows                                                                                 |
| `WorkflowScheduler.schedule_cron(wb, cron_expr: str(5-field), name=...)` | **CONFIRMED** `scheduler.py:593`                                                                | target API                                                                                                   |
| `WorkflowScheduler.schedule_interval(wb, seconds: float, name=...)`      | **CONFIRMED** `scheduler.py:694`                                                                | target API                                                                                                   |
| #913 (parent brief)                                                      | **CLOSED**                                                                                      | AC1–3 shipped; this is AC4                                                                                   |
| CLI `python -m kailash.scheduler.migrate_celery_beat`                    | **`kailash.scheduler` package does NOT exist** — scheduler lives at `kailash.runtime.scheduler` | AMEND: `kailash.runtime.migrate_celery_beat` OR new `kailash/scheduler/` pkg OR `scripts/` — /todos decision |
| existing migrator                                                        | none                                                                                            | clean greenfield                                                                                             |

## The load-bearing design decision (surfaced for /todos)

Both target APIs require a **`workflow_builder`**. A django-celery-beat `PeriodicTask` row carries a Celery **task name** (dotted path to a Python callable, e.g. `myapp.tasks.send_report`) + its schedule — NOT a Kailash `WorkflowBuilder`. The migrator can mechanically translate the **schedule** (cron/interval timing) but cannot synthesize **what runs** (the task body). So the output contract must be decided:

- **Option A — emit a migration script/report** (one `schedule_cron(...)`/`schedule_interval(...)` call per row, with the `workflow_builder` left as a clearly-marked `# TODO: map <task_name> to a WorkflowBuilder` reference). Honest migration AID; the user wires task bodies. Risk: emits placeholder workflow refs (must NOT be a runnable stub that silently no-ops — zero-tolerance Rule 2).
- **Option B — require a task-name→WorkflowBuilder mapping as input** (`--task-map mapping.py`); the migrator emits fully-wired registrations only for mapped tasks, and reports unmapped rows. Turnkey for mapped tasks; needs user-supplied mapping.
- **Option C — emit a structured data manifest** (JSON/YAML: each row → {name, trigger_kind, cron/seconds, enabled, task_name}) that a separate runtime loader consumes. Decouples timing-translation from task-wiring entirely.

Recommendation (to confirm at /todos): **Option C for the read+translate core + Option A as the codegen output** — the migrator reads PeriodicTask rows → emits a manifest (fully testable, no workflow needed) AND a commented schedule-registration script. This keeps the Tier-2 test honest (assert manifest correctness against a seeded Django DB, no placeholder workflows) and gives the user a real starting script. Avoids placeholder-stub workflows entirely.

## Acceptance criteria (from issue, with mapping decision applied)

- [ ] Reads `PeriodicTask` rows from a Django DB (configurable connection). django.setup() vs raw-SQL reader — /todos decision (raw SQL avoids a Django runtime dep for a one-shot tool).
- [ ] CrontabSchedule (celery 6-field with seconds + 5-field) → Kailash 5-field cron; **REJECT non-zero seconds with a clear error**; handle timezone + day-of-week conventions.
- [ ] IntervalSchedule → `seconds=` mapping.
- [ ] `enabled=False` rows → registered then `SchedulerAdminAPI.disable_schedule`.
- [ ] Tier-2 integration test: seed a Django test DB with PeriodicTask rows, run migrator, assert each row produced the correct translated output (real DB, NO mocking).
- [ ] CLI surface (module path amended per prereq table).
- [ ] Docs: `docs/scheduler/migrating-from-celery-beat.md` worked example.

## Out of scope

- Auto-translating celery task BODIES into Kailash workflows (fundamentally impossible — a callable ≠ a WorkflowBuilder; this is the user's wiring step, aided by the emitted script).
