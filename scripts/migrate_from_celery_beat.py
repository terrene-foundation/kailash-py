#!/usr/bin/env python3
"""One-shot migration aid: django-celery-beat -> Kailash WorkflowScheduler (#938).

Reads the ``django_celery_beat_*`` tables from a Django database and emits:

1. A **manifest** (JSON) — one entry per ``PeriodicTask`` row with its translated
   Kailash trigger (5-field cron string or interval seconds), enabled flag, source
   celery task name, and any per-row migration warnings. The manifest is the
   machine-readable, fully-testable output (no Kailash workflow required to produce it).
2. A **starter registration script** (Python) — one ``schedule_cron(...)`` /
   ``schedule_interval(...)`` call per row, with the ``workflow_builder`` left as an
   explicit ``WIRE ME`` placeholder.

**What this tool does NOT do (by design):** it cannot synthesise *what runs*. A celery
``PeriodicTask`` references a Celery task name (a Python callable, e.g.
``myapp.tasks.send_report``); a Kailash schedule needs a ``WorkflowBuilder``. There is no
mechanical translation from a callable to a workflow — that is the operator's wiring step,
which the emitted starter script scaffolds. The tool translates the *schedule* (timing,
enabled state); the operator supplies the *workflow*.

Usage::

    python scripts/migrate_from_celery_beat.py \\
        --django-db postgresql://user:pass@host:5432/djangodb \\
        --out celery_beat_manifest.json \\
        [--script register_schedules.py]

Supported source DBs: sqlite, postgresql, mysql (via kailash ConnectionManager dialects).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("kailash.scheduler.migrate_celery_beat")

# django-celery-beat IntervalSchedule.period -> seconds-per-unit.
PERIOD_SECONDS: dict[str, float] = {
    "days": 86_400.0,
    "hours": 3_600.0,
    "minutes": 60.0,
    "seconds": 1.0,
    "microseconds": 1e-6,
}

# Timezone values that the Kailash scheduler's global UTC default carries faithfully.
_UTC_EQUIVALENT = {None, "", "UTC", "utc", "Etc/UTC"}


@dataclass
class ScheduleRow:
    """A single migrated PeriodicTask row."""

    name: str
    celery_task: str
    trigger: str  # "cron" | "interval" | "unsupported"
    cron_expression: str | None = None
    interval_seconds: float | None = None
    enabled: bool = True
    warnings: list[str] = field(default_factory=list)


def crontab_to_cron(
    minute: str,
    hour: str,
    day_of_week: str,
    day_of_month: str,
    month_of_year: str,
) -> str:
    """Translate a django-celery-beat CrontabSchedule to a standard 5-field cron string.

    django-celery-beat stores fields in the order
    ``(minute, hour, day_of_week, day_of_month, month_of_year)``. Standard cron — which
    ``WorkflowScheduler.schedule_cron`` consumes — is
    ``(minute, hour, day_of_month, month, day_of_week)``. The day-of-week and
    day-of-month fields are therefore **reordered**, not copied positionally.

    Field VALUES (``*``, ranges ``1-5``, lists ``1,15``, steps ``*/5``) and the
    day-of-week numbering (both celery and cron use ``0=Sunday``) pass through unchanged.
    Celery does NOT store a seconds field (its crontab is minute-granularity), so there
    is no seconds component to translate or reject.
    """
    fields = [
        (minute or "*").strip(),
        (hour or "*").strip(),
        (day_of_month or "*").strip(),
        (month_of_year or "*").strip(),
        (day_of_week or "*").strip(),
    ]
    return " ".join(f or "*" for f in fields)


def interval_to_seconds(every: int | None, period: str) -> float:
    """Translate a django-celery-beat IntervalSchedule (every, period) to seconds.

    Raises ``ValueError`` for an unknown period or a non-positive ``every`` (Kailash
    ``schedule_interval`` requires a positive seconds value).
    """
    try:
        every_int = int(every)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(
            f"IntervalSchedule.every must be a positive integer, got {every!r}"
        ) from None
    if every_int <= 0:
        raise ValueError(
            f"IntervalSchedule.every must be a positive integer, got {every!r}"
        )
    key = (period or "").strip().lower()
    if key not in PERIOD_SECONDS:
        raise ValueError(
            f"Unknown IntervalSchedule.period {period!r}; "
            f"expected one of {sorted(PERIOD_SECONDS)}"
        )
    return every_int * PERIOD_SECONDS[key]


def build_schedule_row(row: dict[str, Any]) -> ScheduleRow:
    """Translate one joined PeriodicTask DB row (dict) into a ScheduleRow.

    The row is the LEFT JOIN of periodictask with crontabschedule + intervalschedule;
    crontab/interval columns are ``None`` when the corresponding FK is null.
    """
    name = str(row.get("name") or "<unnamed>")
    celery_task = str(row.get("task") or "<unknown-task>")
    # A DB NULL on enabled is django-celery-beat's BooleanField(default=True);
    # `.get(..., True)` only fires for a MISSING key, so coerce None explicitly.
    _enabled_raw = row.get("enabled", True)
    enabled = True if _enabled_raw is None else bool(_enabled_raw)
    warnings: list[str] = []

    # Surface (don't silently flatten) control chars in DB-sourced strings — they are
    # both a generated-script-injection vector and a tampering signal worth showing.
    for _label, _val in (("name", name), ("task", celery_task)):
        if _CONTROL_CHARS.search(_val):
            warnings.append(
                f"source {_label} contained control characters (newlines/control "
                f"bytes); sanitized in generated output — review the source row"
            )

    has_crontab = row.get("crontab_id") is not None
    has_interval = row.get("interval_id") is not None

    if has_crontab and has_interval:
        warnings.append(
            "row has BOTH crontab_id and interval_id set (malformed); "
            "using crontab and ignoring interval"
        )

    if has_crontab:
        cron = crontab_to_cron(
            minute=str(row.get("minute", "*")),
            hour=str(row.get("hour", "*")),
            day_of_week=str(row.get("day_of_week", "*")),
            day_of_month=str(row.get("day_of_month", "*")),
            month_of_year=str(row.get("month_of_year", "*")),
        )
        tz = row.get("timezone")
        if tz not in _UTC_EQUIVALENT:
            warnings.append(
                f"source crontab timezone is {tz!r}; WorkflowScheduler applies one "
                f"GLOBAL timezone (default UTC) — per-task timezone is NOT preserved. "
                f"Construct the target scheduler with timezone={tz!r} if all tasks "
                f"share it, or group by timezone into separate schedulers."
            )
        return ScheduleRow(
            name=name,
            celery_task=celery_task,
            trigger="cron",
            cron_expression=cron,
            enabled=enabled,
            warnings=warnings,
        )

    if has_interval:
        try:
            seconds = interval_to_seconds(
                every=row.get("every"), period=str(row.get("period", ""))
            )
        except ValueError as exc:
            warnings.append(f"interval translation failed: {exc}")
            return ScheduleRow(
                name=name,
                celery_task=celery_task,
                trigger="unsupported",
                enabled=enabled,
                warnings=warnings,
            )
        if seconds < 1.0:
            warnings.append(
                f"sub-second interval ({seconds}s) — valid for schedule_interval but "
                f"likely impractical; review before registering"
            )
        return ScheduleRow(
            name=name,
            celery_task=celery_task,
            trigger="interval",
            interval_seconds=seconds,
            enabled=enabled,
            warnings=warnings,
        )

    warnings.append(
        "row has neither crontab nor interval schedule (solar/clocked schedules are "
        "out of scope for this migrator) — not translated; migrate this task manually"
    )
    return ScheduleRow(
        name=name,
        celery_task=celery_task,
        trigger="unsupported",
        enabled=enabled,
        warnings=warnings,
    )


_READ_QUERY = """
SELECT
    pt.name            AS name,
    pt.task            AS task,
    pt.enabled         AS enabled,
    pt.interval_id     AS interval_id,
    pt.crontab_id      AS crontab_id,
    c.minute           AS minute,
    c.hour             AS hour,
    c.day_of_week      AS day_of_week,
    c.day_of_month     AS day_of_month,
    c.month_of_year    AS month_of_year,
    c.timezone         AS timezone,
    i.every            AS every,
    i.period           AS period
FROM django_celery_beat_periodictask pt
LEFT JOIN django_celery_beat_crontabschedule c ON pt.crontab_id = c.id
LEFT JOIN django_celery_beat_intervalschedule i ON pt.interval_id = i.id
ORDER BY pt.name
"""


async def read_celery_beat(url: str) -> list[ScheduleRow]:
    """Read all PeriodicTask rows from a Django database via kailash ConnectionManager.

    Uses the dialect-portable ConnectionManager (sqlite / postgresql / mysql) so no
    raw per-driver code is needed. The read is a static SELECT against fixed
    django-celery-beat table names — no user-controlled SQL.
    """
    from kailash.db.connection import ConnectionManager

    conn = ConnectionManager(url)
    await conn.initialize()
    try:
        rows = await conn.fetch(_READ_QUERY)
    finally:
        await conn.close()
    return [build_schedule_row(dict(r)) for r in rows]


def emit_manifest(rows: list[ScheduleRow]) -> str:
    """Serialise the translated rows as an indented JSON manifest."""
    return json.dumps([asdict(r) for r in rows], indent=2, sort_keys=False)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _safe_comment(value: object) -> str:
    """Flatten control chars so a DB value cannot break out of a ``#`` comment line.

    Defense-in-depth against injection of executable lines into the generated starter
    script via a newline in a DB-sourced ``name``/task value. The anomaly itself is
    surfaced as a row warning at ``build_schedule_row`` time (not silently swallowed).
    """
    return _CONTROL_CHARS.sub(" ", str(value))


def _safe_identifier(name: str) -> str:
    """Turn a PeriodicTask name into a safe Python identifier for the starter script."""
    ident = re.sub(r"\W+", "_", name).strip("_") or "task"
    if ident[0].isdigit():
        ident = f"t_{ident}"
    return ident


_SCRIPT_HEADER = '''#!/usr/bin/env python3
"""Starter schedule-registration script generated from django-celery-beat (#938).

THIS SCRIPT IS A STARTING POINT — IT DOES NOT RUN AS-IS. Each schedule below needs a
``WorkflowBuilder`` that performs what the original celery task did; those are marked
``WIRE ME``. Replace each placeholder, then run.
"""
from kailash.runtime.scheduler import WorkflowScheduler
from kailash.runtime.scheduler_admin import SchedulerAdminAPI
from kailash.workflow.builder import WorkflowBuilder

scheduler = WorkflowScheduler()  # configure job_store / timezone as needed
admin = SchedulerAdminAPI(scheduler)

# WIRE ME: audit-trail actor recorded for every disable_schedule call (required, non-empty).
MIGRATION_ACTOR = "celery-beat-migration"
'''


def emit_script(rows: list[ScheduleRow]) -> str:
    """Emit a Python starter script registering each translated schedule.

    The ``workflow_builder`` for each task is an explicit placeholder — the operator
    supplies the workflow that replaces the original celery task body.
    """
    lines: list[str] = [_SCRIPT_HEADER]
    seen_idents: set[str] = set()
    for r in rows:
        # Deduplicate identifiers so two names that collapse to the same identifier
        # (e.g. "report-daily" / "report.daily") do not silently shadow each other.
        base_ident = _safe_identifier(r.name)
        ident = base_ident
        suffix = 2
        while ident in seen_idents:
            ident = f"{base_ident}_{suffix}"
            suffix += 1
        seen_idents.add(ident)

        safe_name = _safe_comment(r.name)
        safe_task = _safe_comment(r.celery_task)
        lines.append(f"# --- {safe_name}  (celery task: {safe_task}) ---")
        if ident != base_ident:
            lines.append(
                f"# WARNING: identifier '{base_ident}' collided with an earlier task; "
                f"using '{ident}' to disambiguate"
            )
        for w in r.warnings:
            lines.append(f"# WARNING: {_safe_comment(w)}")
        if r.trigger == "unsupported":
            lines.append(
                f"# SKIPPED: '{safe_name}' could not be translated automatically "
                f"(see warning above); migrate manually.\n"
            )
            continue
        lines.append(
            f"# WIRE ME: build the WorkflowBuilder that replaces celery task "
            f"'{safe_task}'"
        )
        lines.append(
            f"wb_{ident} = WorkflowBuilder()  # <-- replace with real workflow"
        )
        if r.trigger == "cron":
            lines.append(
                f"sid_{ident} = scheduler.schedule_cron("
                f"wb_{ident}, {r.cron_expression!r}, name={r.name!r})"
            )
        else:  # interval
            lines.append(
                f"sid_{ident} = scheduler.schedule_interval("
                f"wb_{ident}, seconds={r.interval_seconds!r}, name={r.name!r})"
            )
        if not r.enabled:
            lines.append(
                f"admin.disable_schedule(sid_{ident}, actor=MIGRATION_ACTOR)"
                f"  # source PeriodicTask.enabled=False"
            )
        lines.append("")
    return "\n".join(lines)


def _summarise(rows: list[ScheduleRow]) -> str:
    cron = sum(1 for r in rows if r.trigger == "cron")
    interval = sum(1 for r in rows if r.trigger == "interval")
    unsupported = sum(1 for r in rows if r.trigger == "unsupported")
    disabled = sum(1 for r in rows if not r.enabled)
    warned = sum(1 for r in rows if r.warnings)
    return (
        f"{len(rows)} PeriodicTask rows: {cron} cron, {interval} interval, "
        f"{unsupported} unsupported; {disabled} disabled; {warned} with warnings."
    )


async def _amain(args: argparse.Namespace) -> int:
    try:
        rows = await read_celery_beat(args.django_db)
    except Exception as exc:
        # Redact: log only the exception TYPE, never str(exc) — a driver's
        # connect-failure message can embed the credential-bearing DSN.
        logger.error("failed to read source Django DB: %s", type(exc).__name__)
        return 1
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(emit_manifest(rows))
    logger.info("Wrote manifest: %s", args.out)
    if args.script:
        with open(args.script, "w", encoding="utf-8") as fh:
            fh.write(emit_script(rows))
        logger.info("Wrote starter script: %s", args.script)
    print(_summarise(rows))
    for r in rows:
        for w in r.warnings:
            print(f"  [warn] {r.name}: {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate django-celery-beat PeriodicTask rows to Kailash schedules."
    )
    parser.add_argument(
        "--django-db",
        required=True,
        help="Connection URL for the source Django DB (sqlite/postgresql/mysql).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the JSON manifest.",
    )
    parser.add_argument(
        "--script",
        default=None,
        help="Optional path to write a Python starter registration script.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
