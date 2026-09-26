"""Regression: DataFlow's own call sites must BIND their dialect (#1971c).

#1971b made the unbound identifier budget warn at runtime. That warning then
fired on DataFlow's ordinary happy path: a single ``express.bulk_upsert``
against SQLite emitted three WARN lines ::

    identifier.unknown_dialect_budget: .../migrations/sync_ddl_executor.py:583 ...
    identifier.unknown_dialect_budget: .../features/bulk.py:1570 ...
    identifier.unknown_dialect_budget: .../features/bulk.py:1574 ...

Those three sites were not dialect-less. ``bulk._bulk_upsert`` resolves
``database_type`` roughly thirty lines above its validate calls, and the
``sync_ddl_executor`` site sits inside a branch literally guarded by
``self._db_type == "sqlite"``. Both had the engine in hand and passed the
unknown sentinel anyway — which is fail-OPEN on PostgreSQL, where the sentinel
(SQLite's 128) accepts a 64..128-char identifier the server then truncates at
63, aliasing two models onto one physical table. That is the #1971 defect
itself, reachable through DataFlow's most common write path.

Both poles are asserted here deliberately. A silence-only test passes just as
well if the warning were deleted or the code path broken, so the second pole
pins that a GENUINELY unknown dialect still warns.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import tempfile

import pytest

from dataflow.adapters.dialect import identifier_budget_for
from kailash.db.dialect import (
    _UNKNOWN_BUDGET_WARNED_SITES,
    MYSQL_MAX_IDENTIFIER_LENGTH,
    POSTGRES_MAX_IDENTIFIER_LENGTH,
    SQLITE_MAX_IDENTIFIER_LENGTH,
    _UnknownBudget,
    _validate_identifier,
)

_MARKER = "identifier.unknown_dialect_budget"


@pytest.fixture(autouse=True)
def _clear_warn_memo():
    """The memo is process-global and once-per-site; clear it both sides.

    Without this a sibling test that already tripped a site would make the
    silence assertions below pass for the wrong reason.
    """
    _UNKNOWN_BUDGET_WARNED_SITES.clear()
    yield
    _UNKNOWN_BUDGET_WARNED_SITES.clear()


# ---------------------------------------------------------------------------
# Pole 1 — the real DataFlow paths are silent
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_sync_ddl_executor_get_table_columns_binds_sqlite(caplog):
    """``sync_ddl_executor.py`` PRAGMA branch — guarded by _db_type == sqlite."""
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    db_path = os.path.join(tempfile.mkdtemp(), "t.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    executor = SyncDDLExecutor(f"sqlite:///{db_path}")
    assert executor._db_type == "sqlite"

    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        columns = executor.get_table_columns("users")

    # The path must still WORK, not merely fall silent: a broken path would
    # also emit no warning.
    assert [c["name"] for c in columns] == ["id", "name"]
    assert _MARKER not in caplog.text, (
        "sync_ddl_executor validated an identifier against the unknown-dialect "
        f"budget inside a branch guarded by _db_type == 'sqlite': {caplog.text!r}"
    )


@pytest.mark.regression
def test_express_bulk_upsert_binds_its_detected_dialect(caplog):
    """``features/bulk.py`` — ``database_type`` is resolved before validation."""
    from dataflow import DataFlow

    db_path = os.path.join(tempfile.mkdtemp(), "t.db")
    db = DataFlow(f"sqlite:///{db_path}")

    @db.model
    class Widget:
        id: str
        name: str

    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        asyncio.run(
            db.express.bulk_upsert(
                "Widget",
                [{"id": "w1", "name": "alpha"}, {"id": "w2", "name": "beta"}],
                conflict_on=["id"],
            )
        )

    assert _MARKER not in caplog.text, (
        "bulk_upsert validated identifiers against the unknown-dialect budget "
        f"although database_type was already resolved: {caplog.text!r}"
    )


# ---------------------------------------------------------------------------
# Pole 2 — the control: a genuinely unknown dialect STILL warns
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_genuinely_unknown_dialect_still_warns(caplog):
    """Without this the silence above is unfalsifiable.

    If the resolver started handing back a bound budget for everything, or the
    warning were removed outright, every assertion above would still pass.
    """
    budget = identifier_budget_for("mongodb")
    assert isinstance(budget, _UnknownBudget), (
        "an unresolvable engine must keep the unknown sentinel so the warning "
        "it exists to carry still fires"
    )

    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        _validate_identifier("users", max_length=budget)

    assert _MARKER in caplog.text, (
        "a call site that genuinely cannot name its engine must still be "
        "surfaced; silencing it would hide the #1971 hazard entirely"
    )


@pytest.mark.regression
@pytest.mark.parametrize(
    "database_type,expected",
    [
        ("postgresql", POSTGRES_MAX_IDENTIFIER_LENGTH),
        ("mysql", MYSQL_MAX_IDENTIFIER_LENGTH),
        ("sqlite", SQLITE_MAX_IDENTIFIER_LENGTH),
        ("PostgreSQL", POSTGRES_MAX_IDENTIFIER_LENGTH),
    ],
)
def test_resolver_binds_the_real_budget(database_type, expected):
    """PostgreSQL must resolve to 63, not the sentinel's 128.

    This is the half that actually closes #1971: binding PostgreSQL means a
    64..128-char identifier is now rejected client-side instead of being
    truncated server-side onto a colliding table name.
    """
    budget = identifier_budget_for(database_type)
    assert budget == expected
    assert not isinstance(budget, _UnknownBudget)
