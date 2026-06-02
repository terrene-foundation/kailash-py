# Migrating from django-celery-beat

`scripts/migrate_from_celery_beat.py` is a one-shot tool that reads the schedules in a
[django-celery-beat](https://github.com/celery/django-celery-beat) database and translates
them into Kailash `WorkflowScheduler` registrations.

## What it does — and what it can't

The tool translates the **schedule** (the timing and the enabled/disabled state). It
**cannot** translate **what runs**: a celery `PeriodicTask` points at a Celery task — a
Python callable like `billing.tasks.run` — while a Kailash schedule needs a
`WorkflowBuilder`. There is no mechanical way to turn a callable into a workflow, so wiring
each task to its replacement workflow is your step. The tool scaffolds it for you with an
explicit `WIRE ME` marker on every emitted registration.

## Usage

```bash
python scripts/migrate_from_celery_beat.py \
    --django-db postgresql://user:pass@host:5432/djangodb \
    --out celery_beat_manifest.json \
    --script register_schedules.py      # optional starter script
```

Supported source databases: **sqlite, postgresql, mysql** (resolved through the kailash
`ConnectionManager` dialects — install the matching async driver for your source DB).

The tool produces two artifacts:

- **`--out` manifest (JSON, required):** one entry per `PeriodicTask` — its name, the source
  celery task name, the translated trigger (`cron` / `interval`), the enabled flag, and any
  per-row migration warnings. This is the machine-readable record.
- **`--script` starter (Python, optional):** one `schedule_cron(...)` / `schedule_interval(...)`
  call per row, with the `WorkflowBuilder` left as a `WIRE ME` placeholder. **It does not run
  as-is** — fill in each workflow first.

## Worked example

Given a celery-beat DB with a weekly cron task and a disabled polling interval:

```text
$ python scripts/migrate_from_celery_beat.py --django-db "sqlite:///django.sqlite3" \
      --out manifest.json --script register.py

2 PeriodicTask rows: 1 cron, 1 interval, 0 unsupported; 1 disabled; 1 with warnings.
  [warn] weekly-billing: source crontab timezone is 'America/New_York'; WorkflowScheduler
         applies one GLOBAL timezone (default UTC) — per-task timezone is NOT preserved. ...
```

`manifest.json`:

```json
[
  {
    "name": "health-poll",
    "celery_task": "ops.tasks.poll",
    "trigger": "interval",
    "cron_expression": null,
    "interval_seconds": 300.0,
    "enabled": false,
    "warnings": []
  },
  {
    "name": "weekly-billing",
    "celery_task": "billing.tasks.run",
    "trigger": "cron",
    "cron_expression": "0 9 15 * 1",
    "interval_seconds": null,
    "enabled": true,
    "warnings": ["source crontab timezone is 'America/New_York'; ..."]
  }
]
```

`register.py` (excerpt — complete the `WIRE ME` placeholders, then run):

```python
from kailash.runtime.scheduler import WorkflowScheduler
from kailash.runtime.scheduler_admin import SchedulerAdminAPI
from kailash.workflow.builder import WorkflowBuilder

scheduler = WorkflowScheduler()  # configure job_store / timezone as needed
admin = SchedulerAdminAPI(scheduler)

# --- weekly-billing  (celery task: billing.tasks.run) ---
# WIRE ME: build the WorkflowBuilder that replaces celery task 'billing.tasks.run'
wb_weekly_billing = WorkflowBuilder()  # <-- replace with real workflow
sid_weekly_billing = scheduler.schedule_cron(wb_weekly_billing, '0 9 15 * 1', name='weekly-billing')
```

## Translation rules

| celery-beat source        | Kailash target                               | Notes                                                                                                                                                                                                                                                  |
| ------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `CrontabSchedule`         | `schedule_cron(wb, "<5-field cron>")`        | Fields are **reordered**: celery stores `(minute, hour, day_of_week, day_of_month, month_of_year)`; standard cron is `(minute, hour, day_of_month, month, day_of_week)`. Field values and the `0=Sunday` day-of-week numbering pass through unchanged. |
| `IntervalSchedule`        | `schedule_interval(wb, seconds=N)`           | `seconds = every × period`, where `period ∈ {days, hours, minutes, seconds, microseconds}`.                                                                                                                                                            |
| `enabled = False`         | register, then `admin.disable_schedule(sid)` | The schedule is created paused.                                                                                                                                                                                                                        |
| per-task `timezone` ≠ UTC | (warning)                                    | `WorkflowScheduler` applies **one global** timezone (default UTC) — a per-task timezone is not preserved. Construct the scheduler with that timezone if all tasks share it, or group tasks by timezone into separate schedulers.                       |
| Solar / Clocked schedules | (warning, not translated)                    | Out of scope — migrate these manually.                                                                                                                                                                                                                 |

## Notes

- celery's `CrontabSchedule` is **minute-granularity** (no seconds field), so there is no
  sub-minute cron to translate or reject.
- A sub-second `IntervalSchedule` (e.g. `every=500, period=microseconds`) is valid for
  `schedule_interval` but flagged as likely-impractical.
- The tool reads with static `SELECT`s against the fixed `django_celery_beat_*` table names —
  no schema changes are made to the source database.
