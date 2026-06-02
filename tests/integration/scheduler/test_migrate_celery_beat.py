"""Tier-2 integration tests for scripts/migrate_from_celery_beat.py (#938).

Pure-translation assertions run as fast direct calls; the reader assertion seeds a REAL
sqlite database with the django-celery-beat schema and reads it back through the actual
kailash ConnectionManager path (real infra, NO mocking — rules/testing.md Tier 2).
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "migrate_from_celery_beat.py"


def _load_migrator() -> ModuleType:
    """Import the migrator script (scripts/ is not a package) via importlib."""
    spec = importlib.util.spec_from_file_location("migrate_from_celery_beat", _SCRIPT)
    assert spec and spec.loader, f"cannot load {_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so @dataclass can resolve cls.__module__.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mig = _load_migrator()


# --------------------------------------------------------------------------
# Pure translation — crontab field reorder (celery order != standard cron order)
# --------------------------------------------------------------------------
def test_crontab_reorders_dow_and_dom_fields() -> None:
    # celery stores (minute, hour, day_of_week, day_of_month, month_of_year);
    # standard cron is (minute, hour, day_of_month, month, day_of_week).
    # "0 9 1 15 *" in celery = minute0 hour9 dow1(Mon) dom15 moy* ->
    # standard "0 9 15 * 1".
    assert (
        mig.crontab_to_cron(
            minute="0", hour="9", day_of_week="1", day_of_month="15", month_of_year="*"
        )
        == "0 9 15 * 1"
    )


def test_crontab_defaults_blank_fields_to_star() -> None:
    assert (
        mig.crontab_to_cron(
            minute="*/5", hour="", day_of_week="", day_of_month="", month_of_year=""
        )
        == "*/5 * * * *"
    )


# --------------------------------------------------------------------------
# Pure translation — interval -> seconds
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "every,period,expected",
    [
        (5, "minutes", 300.0),
        (2, "hours", 7200.0),
        (1, "days", 86400.0),
        (30, "seconds", 30.0),
    ],
)
def test_interval_to_seconds(every: int, period: str, expected: float) -> None:
    assert mig.interval_to_seconds(every, period) == expected


def test_interval_rejects_nonpositive_every() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        mig.interval_to_seconds(0, "minutes")


def test_interval_rejects_unknown_period() -> None:
    with pytest.raises(ValueError, match="Unknown IntervalSchedule.period"):
        mig.interval_to_seconds(5, "fortnights")


# --------------------------------------------------------------------------
# build_schedule_row warnings
# --------------------------------------------------------------------------
def test_non_utc_timezone_warns_about_global_scheduler_tz() -> None:
    row = mig.build_schedule_row(
        {
            "name": "report",
            "task": "myapp.tasks.report",
            "enabled": 1,
            "crontab_id": 1,
            "interval_id": None,
            "minute": "0",
            "hour": "9",
            "day_of_week": "*",
            "day_of_month": "*",
            "month_of_year": "*",
            "timezone": "America/New_York",
        }
    )
    assert row.trigger == "cron"
    assert row.cron_expression == "0 9 * * *"
    assert any("per-task timezone is NOT preserved" in w for w in row.warnings)


def test_neither_crontab_nor_interval_is_unsupported() -> None:
    row = mig.build_schedule_row(
        {
            "name": "solar_task",
            "task": "myapp.tasks.sunrise",
            "enabled": 1,
            "crontab_id": None,
            "interval_id": None,
        }
    )
    assert row.trigger == "unsupported"
    assert any("solar/clocked" in w for w in row.warnings)


# --------------------------------------------------------------------------
# Tier-2 — real sqlite django-celery-beat DB read through ConnectionManager
# --------------------------------------------------------------------------
def _seed_celery_beat_db(db_path: Path) -> None:
    """Create the django-celery-beat schema + seed rows in a REAL sqlite DB."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            CREATE TABLE django_celery_beat_intervalschedule (
                id INTEGER PRIMARY KEY, every INTEGER, period TEXT);
            CREATE TABLE django_celery_beat_crontabschedule (
                id INTEGER PRIMARY KEY, minute TEXT, hour TEXT, day_of_week TEXT,
                day_of_month TEXT, month_of_year TEXT, timezone TEXT);
            CREATE TABLE django_celery_beat_periodictask (
                id INTEGER PRIMARY KEY, name TEXT, task TEXT, enabled INTEGER,
                interval_id INTEGER, crontab_id INTEGER);
            """
        )
        con.execute(
            "INSERT INTO django_celery_beat_crontabschedule VALUES "
            "(1, '0', '9', '1', '15', '*', 'UTC')"
        )
        con.execute(
            "INSERT INTO django_celery_beat_intervalschedule VALUES (1, 5, 'minutes')"
        )
        con.executemany(
            "INSERT INTO django_celery_beat_periodictask "
            "(id, name, task, enabled, interval_id, crontab_id) VALUES (?,?,?,?,?,?)",
            [
                (1, "nightly-report", "app.tasks.report", 1, None, 1),  # cron, enabled
                (2, "poll-queue", "app.tasks.poll", 1, 1, None),  # interval, enabled
                (3, "disabled-cron", "app.tasks.legacy", 0, None, 1),  # cron, disabled
                (4, "orphan", "app.tasks.orphan", 1, None, None),  # unsupported
            ],
        )
        con.commit()
    finally:
        con.close()


def test_read_celery_beat_translates_real_sqlite_db(tmp_path: Path) -> None:
    db_path = tmp_path / "djangodb.sqlite3"
    _seed_celery_beat_db(db_path)

    rows = asyncio.run(mig.read_celery_beat(f"sqlite:///{db_path}"))
    by_name = {r.name: r for r in rows}

    assert set(by_name) == {"nightly-report", "poll-queue", "disabled-cron", "orphan"}

    nightly = by_name["nightly-report"]
    assert nightly.trigger == "cron"
    assert nightly.cron_expression == "0 9 15 * 1"  # reordered dow<->dom
    assert nightly.enabled is True
    assert nightly.warnings == []

    poll = by_name["poll-queue"]
    assert poll.trigger == "interval"
    assert poll.interval_seconds == 300.0
    assert poll.celery_task == "app.tasks.poll"

    disabled = by_name["disabled-cron"]
    assert disabled.trigger == "cron"
    assert disabled.enabled is False

    orphan = by_name["orphan"]
    assert orphan.trigger == "unsupported"
    assert orphan.warnings

    # Manifest round-trips to valid JSON with the translated values.
    manifest = json.loads(mig.emit_manifest(rows))
    assert {m["name"] for m in manifest} == set(by_name)

    # Starter script: disabled row emits disable_schedule; unsupported row is skipped.
    script = mig.emit_script(rows)
    assert "schedule_cron(" in script
    assert "schedule_interval(" in script
    # disable call MUST carry the required keyword-only audit actor (real signature
    # is disable_schedule(schedule_id, *, actor) — a bare call TypeErrors at runtime).
    assert "disable_schedule(" in script
    assert "actor=MIGRATION_ACTOR" in script
    assert "WIRE ME" in script
    assert "app.tasks.orphan" in script  # surfaced as a SKIPPED comment, not silent
    # The emitted script parses as valid Python (no syntax errors from interpolation).
    ast.parse(script)


def test_emit_script_resists_comment_injection() -> None:
    """A newline-laden PeriodicTask.name MUST NOT inject an executable line into the
    generated starter script (security: DB-sourced values are control-char-flattened).
    """
    malicious = mig.build_schedule_row(
        {
            "name": "evil\nimport os\nos.system('boom')  #",
            "task": "app.tasks.x\nimport sys",
            "enabled": 1,
            "crontab_id": 1,
            "interval_id": None,
            "minute": "0",
            "hour": "0",
            "day_of_week": "*",
            "day_of_month": "*",
            "month_of_year": "*",
            "timezone": "UTC",
        }
    )
    # The control-char anomaly is surfaced, not silently swallowed.
    assert any("control characters" in w for w in malicious.warnings)

    script = mig.emit_script([malicious])
    tree = ast.parse(script)  # must be valid Python
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    # The injected `import os` / `import sys` must NOT have become real statements.
    assert "os" not in imported
    assert "sys" not in imported


def test_emit_script_disambiguates_colliding_identifiers() -> None:
    """Two names that collapse to the same identifier get distinct sids + a warning."""
    rows = [
        mig.ScheduleRow(
            name="report-daily",
            celery_task="t",
            trigger="interval",
            interval_seconds=60.0,
        ),
        mig.ScheduleRow(
            name="report.daily",
            celery_task="t",
            trigger="interval",
            interval_seconds=60.0,
        ),
    ]
    script = mig.emit_script(rows)
    assert "sid_report_daily " in script
    assert "sid_report_daily_2 " in script
    assert "collided" in script
    ast.parse(script)
