# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #2006 -- CREATE sent an explicit NULL for unset optional fields.

The CREATE path built its INSERT column list from EVERY model field, with
exactly three exemptions (``id`` when unsupplied, ``created_at``,
``updated_at``), then filled anything the caller had not supplied with
``None``. An explicit ``NULL`` OVERRIDES a column ``DEFAULT``, so:

* on a nullable column the row silently landed with ``NULL``;
* on ``NOT NULL DEFAULT ...`` -- a common audit/event-table shape -- the
  INSERT failed outright with a not-null violation.

A second, independent defect: a callable model default (``ts: datetime = _now``)
was honoured by the INSERT path but interpolated as ``repr()`` by the DDL
generator, producing ``DEFAULT '<function _now at 0x...>'`` with no diagnostic.

Every test here exercises a REAL SQLite database and reads the row back with an
independent ``sqlite3`` connection, because a table's ``DEFAULT`` is applied by
the database, not by anything observable in the generated SQL string.

Note on the issue text: #2006 attributed the NULL-fill to the ``else`` branch
("optional field without default"). For the issue's OWN repro
(``ts: datetime = None``) the ``@db.model`` decorator records
``{"default": None}``, so the ``elif "default" in field_info`` branch ran
instead. Both branches are covered below; fixing only one leaves the reported
case broken.
"""

import sqlite3
from datetime import datetime

import pytest


def _rows(db_file: str, sql: str):
    """Read the table back over an independent connection (ground truth)."""
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _create_table(db_file: str, ddl: str) -> None:
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()


@pytest.mark.regression
def test_issue_2006_none_default_field_omitted_so_column_default_applies(
    tmp_path,
) -> None:
    """The issue's own repro: ``ts: datetime = None`` on a NOT NULL DEFAULT column.

    Covers the ``elif "default" in field_info`` branch -- the one the issue
    text misattributed. Before the fix this raised
    ``NOT NULL constraint failed: events_2006.ts``.
    """
    from dataflow import DataFlow

    db_file = str(tmp_path / "elif_branch.db")
    _create_table(
        db_file,
        """CREATE TABLE events_2006 (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "EventElif2006",
        (),
        {
            "__annotations__": {"id": str, "ts": datetime, "note": str},
            "__tablename__": "events_2006",
            "ts": None,
            "note": None,
        },
    )
    db.model(Model)

    # Pin the branch this test is aimed at: `= None` records a "default" key.
    field_info = db.get_model_fields("EventElif2006")["ts"]
    assert "default" in field_info, f"expected the elif branch shape, got {field_info}"
    assert field_info["default"] is None

    db.express_sync.create("EventElif2006", {"id": "e1"})

    rows = _rows(db_file, "SELECT id, ts, note FROM events_2006")
    assert len(rows) == 1, f"expected the row to persist, got {rows}"
    assert (
        rows[0][1] is not None
    ), "ts holds NULL: the INSERT bound an explicit NULL over the column DEFAULT"
    assert rows[0][2] is None, "note has no column DEFAULT, so it should be NULL"


@pytest.mark.regression
def test_issue_2006_dynamic_registration_records_no_default_key(tmp_path) -> None:
    """Schema-introspected registration yields the ``else``-branch field shape.

    This is the measurement the next test's fixture rests on: a nullable column
    with no database default registers as ``required: False`` with NO "default"
    key at all -- a shape the ``@db.model`` decorator can never produce.
    """
    from dataflow import DataFlow

    db_file = str(tmp_path / "introspect.db")
    _create_table(
        db_file,
        """CREATE TABLE tickets2006 (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    outcome = db.register_schema_as_models()
    assert not outcome.get("errors"), outcome.get("errors")

    model_name = outcome["registered_models"][0]
    fields = db.get_model_fields(model_name)
    assert (
        "default" not in fields["note"]
    ), f"expected the else-branch shape for a nullable no-default column: {fields}"
    assert fields["note"].get("required") is False


@pytest.mark.regression
def test_issue_2006_missing_default_key_field_omitted_so_column_default_applies(
    tmp_path,
) -> None:
    """Covers the ``else`` branch: optional field, NO "default" key at all.

    The registry entry is shaped exactly as
    ``register_schema_as_models`` produces it (proven by the test above); it is
    reproduced here on a table whose column carries ``NOT NULL DEFAULT``, which
    introspection alone cannot give us -- an introspected default column always
    gains a "default" key and would exercise the other branch.
    """
    from dataflow import DataFlow

    db_file = str(tmp_path / "else_branch.db")
    _create_table(
        db_file,
        """CREATE TABLE audits_2006 (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "AuditElse2006",
        (),
        {
            "__annotations__": {"id": str, "ts": datetime},
            "__tablename__": "audits_2006",
            "ts": None,
        },
    )
    db.model(Model)

    # Drop to the introspection-registered shape: optional, no "default" key.
    db.get_model_fields("AuditElse2006")["ts"].pop("default")
    assert db.get_model_fields("AuditElse2006")["ts"] == {
        "type": datetime,
        "required": False,
    }

    db.express_sync.create("AuditElse2006", {"id": "a1"})

    rows = _rows(db_file, "SELECT id, ts FROM audits_2006")
    assert len(rows) == 1, f"expected the row to persist, got {rows}"
    assert (
        rows[0][1] is not None
    ), "ts holds NULL: the else branch still binds an explicit NULL"


@pytest.mark.regression
def test_issue_2006_explicit_none_still_writes_null(tmp_path) -> None:
    """An explicitly supplied ``None`` must still reach the database as NULL.

    Membership in the caller's input is the discriminator, never the value --
    otherwise "omit unset fields" would silently become "you can never write
    NULL over a column DEFAULT".
    """
    from dataflow import DataFlow

    db_file = str(tmp_path / "explicit_none.db")
    _create_table(
        db_file,
        """CREATE TABLE notes_2006 (
            id TEXT PRIMARY KEY,
            body TEXT DEFAULT 'auto'
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "Note2006",
        (),
        {
            "__annotations__": {"id": str, "body": str},
            "__tablename__": "notes_2006",
            "body": None,
        },
    )
    db.model(Model)

    db.express_sync.create("Note2006", {"id": "n-omitted"})
    db.express_sync.create("Note2006", {"id": "n-explicit", "body": None})

    rows = dict(_rows(db_file, "SELECT id, body FROM notes_2006"))
    assert rows["n-omitted"] == "auto", "unset field should fall through to the DEFAULT"
    assert rows["n-explicit"] is None, "an explicit None must be written as NULL"


@pytest.mark.regression
def test_issue_2006_model_default_still_beats_column_default(tmp_path) -> None:
    """A real (non-None) model default is still bound, overriding the column DEFAULT."""
    from dataflow import DataFlow

    db_file = str(tmp_path / "model_default.db")
    _create_table(
        db_file,
        """CREATE TABLE jobs_2006 (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "Job2006",
        (),
        {
            "__annotations__": {"id": str, "status": str},
            "__tablename__": "jobs_2006",
            "status": "active",
        },
    )
    db.model(Model)

    db.express_sync.create("Job2006", {"id": "j1"})

    rows = _rows(db_file, "SELECT id, status FROM jobs_2006")
    assert rows[0][1] == "active", f"model default should win over the column: {rows}"


@pytest.mark.regression
def test_issue_2006_every_column_omitted_uses_all_defaults_insert(tmp_path) -> None:
    """When EVERY candidate column is omitted, the all-defaults INSERT form is used.

    ``INSERT INTO t () VALUES ()`` is a syntax error on SQLite, so this is the
    edge the omission logic has to hold: an auto-generated id plus a single
    optional field the caller does not supply leaves no bound column at all.
    """
    from dataflow import DataFlow

    db_file = str(tmp_path / "all_defaults.db")
    _create_table(
        db_file,
        """CREATE TABLE pings_2006 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "Ping2006",
        (),
        {
            "__annotations__": {"id": int, "seen_at": datetime},
            "__tablename__": "pings_2006",
            "seen_at": None,
        },
    )
    db.model(Model)

    db.express_sync.create("Ping2006", {})

    rows = _rows(db_file, "SELECT id, seen_at FROM pings_2006")
    assert len(rows) == 1, f"expected the all-defaults INSERT to persist a row: {rows}"
    assert rows[0][0] is not None, "id should be auto-generated"
    assert rows[0][1] is not None, "seen_at should carry the column DEFAULT"


@pytest.mark.regression
def test_issue_2006_missing_required_field_still_raises(tmp_path) -> None:
    """Omission must not swallow a genuinely missing REQUIRED field."""
    from dataflow import DataFlow

    db_file = str(tmp_path / "required.db")
    _create_table(
        db_file,
        """CREATE TABLE parts_2006 (
            id TEXT PRIMARY KEY,
            sku TEXT NOT NULL
        )""",
    )

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "Part2006",
        (),
        {
            "__annotations__": {"id": str, "sku": str},
            "__tablename__": "parts_2006",
        },
    )
    db.model(Model)

    with pytest.raises(Exception) as exc_info:
        db.express_sync.create("Part2006", {"id": "p1"})
    assert "sku" in str(
        exc_info.value
    ), f"error should name the field: {exc_info.value}"
    assert _rows(db_file, "SELECT id FROM parts_2006") == []


@pytest.mark.regression
@pytest.mark.parametrize("database_type", ["postgresql", "mysql", "sqlite"])
def test_issue_2006_callable_default_emits_no_column_default(
    tmp_path, database_type: str
) -> None:
    """A callable default must never be interpolated as ``repr()`` into DDL."""
    from dataflow import DataFlow

    def _now() -> datetime:
        return datetime(2020, 1, 2, 3, 4, 5)

    db = DataFlow(
        f"sqlite:///{tmp_path / 'ddl.db'}", auto_migrate=False, cache_enabled=False
    )
    Model = type(
        "ProbeDdl2006",
        (),
        {
            "__annotations__": {"id": str, "ts": datetime},
            "__tablename__": "probes_2006",
            "ts": _now,
        },
    )
    db.model(Model)

    ddl = db._generate_create_table_sql("ProbeDdl2006", database_type)
    assert "<function" not in ddl, f"function repr() leaked into DDL:\n{ddl}"
    assert "0x" not in ddl, f"a memory address leaked into DDL:\n{ddl}"
    # The ts column itself must carry no DEFAULT -- the CREATE path supplies it.
    # Identifier quoting is dialect-specific (MySQL uses backticks).
    ts_line = [line for line in ddl.splitlines() if "ts" in line.split()[0]]
    assert ts_line, f"ts column missing from DDL:\n{ddl}"
    assert "DEFAULT" not in ts_line[0], f"callable default emitted a DEFAULT: {ts_line}"


@pytest.mark.regression
def test_issue_2006_callable_default_value_is_written_by_create(tmp_path) -> None:
    """The other half of the contract: the CREATE path calls the callable.

    DDL omitting the DEFAULT is only correct because the INSERT supplies the
    value; asserting the DDL alone would leave the column silently unpopulated.
    """
    from dataflow import DataFlow

    db_file = str(tmp_path / "callable_insert.db")
    _create_table(
        db_file,
        """CREATE TABLE stamps_2006 (
            id TEXT PRIMARY KEY,
            label TEXT
        )""",
    )

    calls = []

    def _label() -> str:
        calls.append(1)
        return f"generated-{len(calls)}"

    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)
    Model = type(
        "Stamp2006",
        (),
        {
            "__annotations__": {"id": str, "label": str},
            "__tablename__": "stamps_2006",
            "label": _label,
        },
    )
    db.model(Model)

    db.express_sync.create("Stamp2006", {"id": "s1"})

    rows = _rows(db_file, "SELECT id, label FROM stamps_2006")
    assert (
        rows[0][1] == "generated-1"
    ), f"callable default was not evaluated at insert time: {rows}"
