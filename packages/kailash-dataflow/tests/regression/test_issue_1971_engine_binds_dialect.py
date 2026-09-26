"""Issue #1971 — ``core/engine.py`` binds the TARGET dialect's identifier budget.

Three code paths in :mod:`dataflow.core.engine` validated dynamic identifiers
against ``DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH`` while the engine they were
generating SQL *for* was already resolved and in scope:

* ``_inspect_sqlite_schema_real`` — statically SQLite (``SQLiteAdapter``),
* ``_generate_foreign_key_constraints_sql(model_name, database_type)``,
* ``_generate_migration_sql(operation, table_name, database_type)``.

That sentinel is SQLite's 128 — the LOOSEST budget — so on PostgreSQL a
64..128-char identifier passed client-side validation and was then TRUNCATED
SERVER-SIDE at 63, silently aliasing two models onto one physical table. The
fix routes every site through ``dataflow.adapters.dialect.identifier_budget_for``.

Both poles are asserted here:

* **efficacy** — a KNOWN dialect emits NO unbound-budget warning, and the path
  still returns real SQL / real schema data (a silence-only assertion would
  also pass if the code path were simply broken);
* **control** — a GENUINELY UNKNOWN dialect STILL warns, because
  ``identifier_budget_for`` returns the sentinel on a miss. Without this pole a
  test could pass by deleting the warning outright.

A third pole asserts the bind is load-bearing rather than cosmetic: a 70-char
column name is REJECTED for ``postgresql`` (budget 63) and ACCEPTED for
``sqlite`` (budget 128). That is the intended behaviour change — an identifier
PostgreSQL would have truncated now fails loudly, client-side.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from dataflow import DataFlow
from dataflow.adapters.dialect import identifier_budget_for
from dataflow.core import engine as engine_module
from dataflow.migrations.schema_state_manager import MigrationOperation
from kailash.db import dialect as kailash_dialect_module
from kailash.db.dialect import (
    DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH,
    IdentifierError,
    _validate_identifier,
)

#: Logger the unbound-budget warning is emitted on.
_WARN_LOGGER = kailash_dialect_module.__name__

#: Substring identifying the warning, so the assertions cannot pass on some
#: unrelated WARNING record that happens to be in the caplog buffer.
_WARN_MARKER = "identifier.unknown_dialect_budget"


# ---------------------------------------------------------------------------
# Import-provenance guard
# ---------------------------------------------------------------------------
# pytest run from a git worktree silently imports the INSTALLED copy from
# site-packages unless PYTHONPATH is pinned, in which case every assertion
# below reports on code that is not the code under review. Fail loudly instead.
def test_modules_under_test_are_the_worktree_copy():
    """The engine + dialect modules imported here live in THIS checkout."""
    # tests/regression/<file> -> tests/ -> kailash-dataflow/ -> packages/ -> repo root
    repo_root = Path(__file__).resolve().parents[4]

    engine_path = Path(engine_module.__file__).resolve()
    dialect_path = Path(kailash_dialect_module.__file__).resolve()

    assert engine_path.is_relative_to(repo_root), (
        f"engine imported from {engine_path}, which is OUTSIDE this checkout "
        f"({repo_root}). Pin PYTHONPATH to <repo>/src and "
        f"<repo>/packages/kailash-dataflow/src before running this suite."
    )
    assert dialect_path.is_relative_to(repo_root), (
        f"kailash.db.dialect imported from {dialect_path}, which is OUTSIDE "
        f"this checkout ({repo_root})."
    )


@pytest.fixture(autouse=True)
def _reset_warned_sites():
    """Clear the once-per-site warn ledger so each test observes a fresh site.

    ``_warn_unknown_identifier_budget_once`` records ``(filename, lineno)`` in a
    module-global set, so the SECOND test touching a given call site would see
    silence regardless of whether the budget is bound — a non-discriminating
    instrument. Clearing before AND after keeps each assertion independent and
    leaves no residue for the rest of the session.
    """
    kailash_dialect_module._UNKNOWN_BUDGET_WARNED_SITES.clear()
    yield
    kailash_dialect_module._UNKNOWN_BUDGET_WARNED_SITES.clear()


def _budget_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if _WARN_MARKER in r.getMessage()]


def _make_db(tmp_path: Path) -> DataFlow:
    return DataFlow(f"sqlite:///{tmp_path / 'engine_1971.db'}", auto_migrate=False)


# ---------------------------------------------------------------------------
# Instrument control — the warning IS observable through caplog
# ---------------------------------------------------------------------------
def test_control_unbound_budget_still_warns(caplog):
    """Known-answer control: an unbound budget DOES reach caplog.

    Every "no warning was emitted" assertion below is worthless unless this
    passes — it establishes that the logger name, propagation and capture level
    used by those assertions can carry the record at all.
    """
    with caplog.at_level(logging.WARNING, logger=_WARN_LOGGER):
        _validate_identifier(
            "some_table", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
        )

    warnings = _budget_warnings(caplog)
    assert warnings, (
        "control failed: an explicitly UNBOUND budget emitted no "
        f"{_WARN_MARKER!r} record — the capture is blind, so the silence "
        "assertions in this module prove nothing."
    )
    assert "TRUNCATED server-side at" in warnings[0]


def test_resolver_returns_sentinel_for_unrecognised_dialect():
    """``identifier_budget_for`` keeps the genuinely-unknown case warning."""
    assert identifier_budget_for("cockroachdb") is DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
    assert identifier_budget_for(None) is DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
    # ...while every dialect DataFlow supports resolves to a real, bound budget.
    assert identifier_budget_for("postgresql") == 63
    assert identifier_budget_for("mysql") == 64
    assert identifier_budget_for("sqlite") == 128


# ---------------------------------------------------------------------------
# Site group A — _inspect_sqlite_schema_real (3 call sites)
# ---------------------------------------------------------------------------
async def test_inspect_sqlite_schema_binds_sqlite_budget(tmp_path, caplog):
    """SQLite schema discovery is silent AND returns the real schema."""
    db_path = tmp_path / "inspect_1971.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author_id INTEGER REFERENCES authors(id)
        );
        CREATE INDEX idx_books_author_id ON books(author_id);
        """
    )
    conn.commit()
    conn.close()

    db = _make_db(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_WARN_LOGGER):
        schema = await db._inspect_sqlite_schema_real(str(db_path))

    # (a) real data — a broken path returning {} must not pass as "silence".
    assert set(schema) == {"authors", "books"}
    assert [c["name"] for c in schema["books"]["columns"]] == [
        "id",
        "title",
        "author_id",
    ]
    assert schema["books"]["foreign_keys"][0]["foreign_table_name"] == "authors"
    assert any(i["name"] == "idx_books_author_id" for i in schema["books"]["indexes"])

    # (b) silence — the dialect is statically SQLite, so nothing is unbound.
    assert _budget_warnings(caplog) == []


# ---------------------------------------------------------------------------
# Site group B — _generate_foreign_key_constraints_sql (5 call sites)
# ---------------------------------------------------------------------------
def _db_with_belongs_to(tmp_path: Path) -> DataFlow:
    """Register a model carrying the belongs_to shape the FK generator reads.

    ``_relationships`` is normally populated by schema discovery against a live
    database; the dict written there is reproduced verbatim (see
    ``engine.py::_auto_detect_relationships``) so this test exercises the real
    generator against the real contract rather than a rewritten one.
    """
    db = _make_db(tmp_path)

    @db.model
    class Book:
        id: str
        title: str
        author_id: str

    db._relationships = {
        "books": {
            "author": {
                "type": "belongs_to",
                "target_table": "authors",
                "foreign_key": "author_id",
                "target_key": "id",
                "auto_detected": True,
            }
        }
    }
    return db


@pytest.mark.parametrize("database_type", ["postgresql", "mysql", "sqlite"])
def test_fk_constraints_known_dialect_is_silent(tmp_path, caplog, database_type):
    db = _db_with_belongs_to(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_WARN_LOGGER):
        constraints = db._generate_foreign_key_constraints_sql("Book", database_type)

    # (a) real SQL — not an empty list standing in for silence.
    assert len(constraints) == 1
    assert constraints[0].startswith("ALTER TABLE books ADD CONSTRAINT fk_books_author")
    assert "FOREIGN KEY (author_id) REFERENCES authors(id);" in constraints[0]

    # (b) silence.
    assert _budget_warnings(caplog) == []


def test_fk_constraints_unknown_dialect_still_warns(tmp_path, caplog):
    """Control: an unsupported target keeps the #1971 warning firing."""
    db = _db_with_belongs_to(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_WARN_LOGGER):
        constraints = db._generate_foreign_key_constraints_sql("Book", "cockroachdb")

    assert len(constraints) == 1, "the unknown-dialect path must still emit SQL"
    warnings = _budget_warnings(caplog)
    assert warnings, (
        "an unrecognised database_type must keep warning — the sentinel is the "
        "signal that nobody bound a dialect."
    )
    assert "engine.py" in warnings[0], warnings[0]


# ---------------------------------------------------------------------------
# Site group C — _generate_migration_sql (4 call sites)
# ---------------------------------------------------------------------------
def _drop_column_op() -> MigrationOperation:
    return MigrationOperation(
        operation_type="DROP_COLUMN",
        table_name="books",
        details={"column_name": "subtitle"},
    )


@pytest.mark.parametrize("database_type", ["postgresql", "mysql", "sqlite"])
def test_migration_sql_known_dialect_is_silent(tmp_path, caplog, database_type):
    db = _make_db(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_WARN_LOGGER):
        sql = db._generate_migration_sql(_drop_column_op(), "books", database_type)

    # (a) real SQL.
    assert sql == "ALTER TABLE books DROP COLUMN subtitle;"
    # (b) silence.
    assert _budget_warnings(caplog) == []


def test_migration_sql_unknown_dialect_still_warns(tmp_path, caplog):
    """Control: an unsupported target keeps the #1971 warning firing."""
    db = _make_db(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_WARN_LOGGER):
        sql = db._generate_migration_sql(_drop_column_op(), "books", "cockroachdb")

    assert sql == "ALTER TABLE books DROP COLUMN subtitle;"
    warnings = _budget_warnings(caplog)
    assert warnings, "an unrecognised database_type must keep warning"
    assert "engine.py" in warnings[0], warnings[0]


# ---------------------------------------------------------------------------
# The bind is LOAD-BEARING, not cosmetic
# ---------------------------------------------------------------------------
def test_postgres_budget_rejects_identifier_postgres_would_truncate(tmp_path):
    """A 70-char column is REFUSED for postgresql and ACCEPTED for sqlite.

    This is the data-correctness half of #1971 and the intended behaviour
    change: before the fix BOTH branches passed (both validated against 128),
    and PostgreSQL then truncated the name server-side at 63.
    """
    db = _make_db(tmp_path)
    long_column = "c" + "o" * 69  # 70 chars: > PG 63, > MySQL 64, < SQLite 128
    assert len(long_column) == 70

    op = MigrationOperation(
        operation_type="DROP_COLUMN",
        table_name="books",
        details={"column_name": long_column},
    )

    with pytest.raises(IdentifierError) as pg_exc:
        db._generate_migration_sql(op, "books", "postgresql")
    assert "exceeds 63-char limit" in str(pg_exc.value)

    with pytest.raises(IdentifierError) as mysql_exc:
        db._generate_migration_sql(op, "books", "mysql")
    assert "exceeds 64-char limit" in str(mysql_exc.value)

    # SQLite's own budget genuinely permits it — the fix binds the budget, it
    # does not tighten every dialect to the strictest one.
    assert (
        db._generate_migration_sql(op, "books", "sqlite")
        == f"ALTER TABLE books DROP COLUMN {long_column};"
    )
