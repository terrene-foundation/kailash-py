"""Regression tests for issue #1603 — quote SET/WHERE/table identifiers in
``features/bulk.py`` (defense-in-depth).

Before the fix, ``features/bulk.py`` built its SET / WHERE clauses and INSERT
column lists by interpolating the column IDENTIFIER directly
(``f"{field} = ${n}"``, ``f"{field} IN (...)"``, ``INSERT INTO {table_name}
({column_names})``) instead of routing every dynamic identifier through
``dialect.quote_identifier()`` the way ``core/nodes.py`` + ``core/engine.py``
already do. Values were (and still are) parameter-bound, so this was NOT a live
injection — but no enforcement point guaranteed ``update_values`` / filter /
record keys stay trusted, so a future refactor admitting caller-influenced keys
would silently open injection with no test signal.

The fix routes EVERY dynamic identifier (SET columns, WHERE columns, table
names, INSERT column lists, ON CONFLICT targets, EXCLUDED refs) through
``dialect.quote_identifier()`` (validate-then-quote, reject-don't-escape) in the
shared ``_build_where_clause`` helper, in ``bulk_create`` / ``bulk_update`` (both
paths) / ``bulk_delete``, and in the three ``_build_*_upsert`` builders plus the
SQLite ``_count_existing_conflicts`` pre-count.

These behavioral tests call the REAL code paths (no mocks):
1. Unit-behavioral: an injection-shaped column raises ``InvalidIdentifierError``
   (rejected, never interpolated raw); a legit column appears QUOTED in the
   generated SQL (proves ``quote_identifier`` is invoked).
2. Tier-2: a real file-backed SQLite ``bulk_update`` round-trips (values stay
   bound, quoting works end-to-end, verified by read-back); an injection-shaped
   filter column is rejected and the table is left unchanged.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression,
``rules/dataflow-identifier-safety.md`` MUST-3).
"""

import sqlite3
import tempfile

import pytest

from dataflow import DataFlow
from dataflow.adapters.dialect import InvalidIdentifierError
from dataflow.features.bulk import BulkOperations

# A representative SQL-injection-shaped identifier that a strict allowlist
# (``^[a-zA-Z_][a-zA-Z0-9_]*$``) MUST reject rather than escape-and-embed.
INJECTION_COL = 'name"; DROP TABLE users; --'

_BATCH = [{"id": "r1", "name": "A"}]


# ---------------------------------------------------------------------------
# Unit-behavioral: the identifier-building helpers reject / quote directly.
# BulkOperations needs no live DataFlow for these pure string builders.
# ---------------------------------------------------------------------------
@pytest.fixture
def ops():
    return BulkOperations(None)


@pytest.mark.regression
@pytest.mark.parametrize(
    "db_type,q", [("postgresql", '"'), ("mysql", "`"), ("sqlite", '"')]
)
def test_where_clause_quotes_legit_column(ops, db_type, q):
    """A legitimate filter column appears QUOTED (identifier not interpolated raw)."""
    where, params = ops._build_where_clause({"status": "active"}, db_type)
    assert f"{q}status{q}" in where, where
    # The VALUE is still a bound parameter, not string-interpolated.
    assert params == ["active"]
    assert "active" not in where


@pytest.mark.regression
@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
def test_where_clause_rejects_injection_column(ops, db_type):
    """An injection-shaped filter column is REJECTED, never interpolated raw."""
    with pytest.raises(InvalidIdentifierError):
        ops._build_where_clause({INJECTION_COL: "x"}, db_type)


@pytest.mark.regression
@pytest.mark.parametrize("db_type", ["postgresql", "mysql", "sqlite"])
def test_where_clause_rejects_injection_in_mongo_operator(ops, db_type):
    """The MongoDB-operator branch ($in) also quote-validates the column key."""
    with pytest.raises(InvalidIdentifierError):
        ops._build_where_clause({INJECTION_COL: {"$in": [1, 2]}}, db_type)


@pytest.mark.regression
@pytest.mark.parametrize(
    "builder,q",
    [
        ("_build_postgresql_upsert", '"'),
        ("_build_mysql_upsert", "`"),
        ("_build_sqlite_upsert", '"'),
    ],
)
def test_upsert_builders_quote_legit_identifiers(ops, builder, q):
    """Each upsert builder QUOTES the table + columns (not interpolated raw)."""
    query, params = getattr(ops, builder)(
        "widgets", ["id", "name"], _BATCH, "update", "Widget", ["id"]
    )
    assert f"{q}widgets{q}" in query, query
    assert f"{q}name{q}" in query, query


@pytest.mark.regression
@pytest.mark.parametrize(
    "builder",
    ["_build_postgresql_upsert", "_build_mysql_upsert", "_build_sqlite_upsert"],
)
def test_upsert_builders_reject_injection_column(ops, builder):
    """An injection-shaped column is REJECTED by every upsert builder."""
    with pytest.raises(InvalidIdentifierError):
        getattr(ops, builder)(
            "widgets",
            ["id", INJECTION_COL],
            [{"id": "r1", INJECTION_COL: "A"}],
            "update",
            "Widget",
            ["id"],
        )


@pytest.mark.regression
@pytest.mark.parametrize(
    "builder",
    ["_build_postgresql_upsert", "_build_mysql_upsert", "_build_sqlite_upsert"],
)
def test_upsert_builders_reject_injection_table(ops, builder):
    """An injection-shaped table name is REJECTED by every upsert builder."""
    with pytest.raises(InvalidIdentifierError):
        getattr(ops, builder)(
            'widgets"; DROP TABLE users; --',
            ["id", "name"],
            _BATCH,
            "update",
            "Widget",
            ["id"],
        )


# ---------------------------------------------------------------------------
# Tier-2: real file-backed SQLite — quoting works end-to-end, values bound.
# ---------------------------------------------------------------------------
@pytest.fixture
def sqlite_db():
    tmpdir = tempfile.mkdtemp()
    db = DataFlow(f"sqlite:///{tmpdir}/df.db", auto_migrate=True)

    @db.model
    class Widget:
        id: str
        name: str
        qty: int

    db._ensure_connected()
    try:
        yield db, tmpdir
    finally:
        db.close()


def _rows(tmpdir, sql):
    con = sqlite3.connect(f"{tmpdir}/df.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_bulk_update_filter_path_roundtrips_with_quoting(sqlite_db):
    """Filter-based bulk_update applies (quoting works); values stay bound."""
    db, tmpdir = sqlite_db
    await db.express.bulk_create(
        "Widget",
        [{"id": "w1", "name": "A", "qty": 1}, {"id": "w2", "name": "A", "qty": 2}],
    )

    res = await db.bulk.bulk_update(
        "Widget",
        filter_criteria={"name": "A"},
        update_values={"qty": 99},
    )
    assert res.get("success") is True, res

    # Read-back proves the quoted SET/WHERE executed and both rows updated.
    rows = _rows(tmpdir, "SELECT id, qty FROM widgets ORDER BY id")
    assert rows == [("w1", 99), ("w2", 99)], rows


@pytest.mark.regression
@pytest.mark.integration
async def test_bulk_update_injection_filter_column_is_rejected(sqlite_db):
    """An injection-shaped filter column never executes; the table is unchanged."""
    db, tmpdir = sqlite_db
    await db.express.bulk_create("Widget", [{"id": "w1", "name": "A", "qty": 1}])

    res = await db.bulk.bulk_update(
        "Widget",
        filter_criteria={INJECTION_COL: "A"},
        update_values={"qty": 42},
    )
    # Rejected at quote_identifier → the broad handler returns success=False;
    # the malicious query never ran.
    assert res.get("success") is False, res

    rows = _rows(tmpdir, "SELECT id, qty FROM widgets ORDER BY id")
    assert rows == [("w1", 1)], rows  # unchanged — no DROP, no update
