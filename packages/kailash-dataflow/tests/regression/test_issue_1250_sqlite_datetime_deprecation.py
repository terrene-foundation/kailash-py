# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1250.

Storing a ``datetime`` through DataFlow's SQLite path emitted a
``DeprecationWarning`` from ``aiosqlite`` -> stdlib ``sqlite3`` because DataFlow
relied on the ``sqlite3`` *default* datetime adapter, deprecated as of Python
3.12. The fix registers explicit ISO-8601 ``datetime``/``date`` adapters at
import of ``dataflow.adapters.sqlite`` so no warning is emitted on 3.12+.
"""

from __future__ import annotations

import datetime as _datetime
import sqlite3
import warnings

import pytest


@pytest.mark.regression
def test_issue_1250_sqlite_datetime_adapters_registered():
    """Importing the DataFlow SQLite adapter registers explicit datetime adapters.

    With the explicit adapter registered, binding a ``datetime`` through
    ``sqlite3`` (which ``aiosqlite`` wraps) no longer triggers the deprecated
    default-adapter path, so no ``DeprecationWarning`` fires.
    """
    import dataflow.adapters.sqlite  # noqa: F401 -- import triggers registration

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE t (d TIMESTAMP, day DATE, tz TIMESTAMP)")
            conn.execute(
                "INSERT INTO t VALUES (?, ?, ?)",
                (
                    _datetime.datetime(2026, 1, 1, 12, 0, 0),
                    _datetime.date(2026, 1, 1),
                    _datetime.datetime(
                        2026, 1, 1, 12, 0, 0, tzinfo=_datetime.timezone.utc
                    ),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT d, day, tz FROM t").fetchone()
        finally:
            conn.close()

    # Byte-for-byte identical to the deprecated stdlib default's output:
    # datetime uses a SPACE separator, NOT "T" — so existing rows still match.
    assert row[0] == "2026-01-01 12:00:00"
    assert row[1] == "2026-01-01"
    # tz-aware: SPACE separator + offset, exactly as the legacy default emitted
    # (the legacy adapter was literally ``isoformat(" ")``).
    assert row[2] == "2026-01-01 12:00:00+00:00"


@pytest.mark.regression
def test_issue_1250_no_datetime_deprecation_warning_on_sqlite_express(tmp_path):
    """A datetime round-trip through DataFlow's SQLite express path emits no
    ``DeprecationWarning`` on Python 3.12+ (the issue's acceptance criterion)."""
    from dataflow import DataFlow

    db = DataFlow(f"sqlite:///{tmp_path}/d1250.sqlite", auto_migrate=True)

    @db.model
    class Event1250:
        name: str
        at: _datetime.datetime

    db._ensure_connected()

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        created = db.express_sync.create(
            "Event1250",
            {"name": "x", "at": _datetime.datetime(2026, 1, 1, 12, 0, 0)},
        )

    assert created["name"] == "x"

    # The datetime survives the round-trip (stored + read back).
    rows = db.express_sync.list("Event1250", {"name": "x"})
    assert len(rows) == 1
    assert "2026-01-01" in str(rows[0]["at"])
