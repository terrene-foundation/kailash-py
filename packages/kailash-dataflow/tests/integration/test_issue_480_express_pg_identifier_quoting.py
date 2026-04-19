"""
Regression tests for issue #480.

DataFlowExpress previously generated malformed PostgreSQL for
``create`` / ``list`` / ``read`` / ``update`` / ``delete`` when the model
contained reserved-word column names (``order``, ``desc``, ``group``,
``user`` ...) or mixed-case column names (``firstName``). The root cause
was that every SQL generator interpolated table and column identifiers
raw into the query string, so PostgreSQL either raised a syntax error
(reserved words) or silently lowercased the column name (mixed case).

Fix: route every dynamic identifier through ``DialectManager.get_dialect
(database_type).quote_identifier(...)`` before interpolation. See
``rules/dataflow-identifier-safety.md`` MUST Rule 1.

These tests are SQLite-invisible: SQLite accepts the unquoted DDL as a
synonym and the unquoted DML as a lookup against the stored (case-
insensitive) identifier. PostgreSQL does not — which is why the bug
escaped the pre-existing SQLite test suite.

Cross-SDK parity: mirrors ``esperie-enterprise/kailash-rs#403``.
"""

from __future__ import annotations

import uuid

import pytest
from dataflow import DataFlow

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create the standard integration test suite against real PostgreSQL."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def _clean_tables(test_suite):
    """Drop bug-specific tables before AND after each test."""

    tables = [
        "issue480_items",
        "issue480_ledgers",
        "issue480_customers",
    ]

    async def _wipe():
        async with test_suite.get_connection() as conn:
            for t in tables:
                try:
                    await conn.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
                except Exception:  # pragma: no cover — best-effort teardown
                    pass
            # Reset DataFlow's bookkeeping tables so auto-migrate doesn't
            # think the schema is already up-to-date.
            for bookkeeping in (
                "dataflow_migrations",
                "dataflow_model_registry",
                "dataflow_migration_history",
            ):
                try:
                    await conn.execute(f"TRUNCATE {bookkeeping}")
                except Exception:  # pragma: no cover — missing table is fine
                    pass

    await _wipe()
    yield
    await _wipe()


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.timeout(30)
class TestIssue480ExpressPostgresIdentifierQuoting:
    """Regression: DataFlowExpress must quote identifiers on PostgreSQL."""

    async def test_issue_480_exact_reproduction_from_issue_body(
        self, test_suite, _clean_tables
    ):
        """The exact repro from #480 body — create/list/read an `Item` model.

        Pre-fix: INSERT/SELECT interpolate the table name unquoted, the
        behaviour works on SQLite but fails on PostgreSQL when the table
        name or column name is a reserved word or mixed-case.  The issue
        body's ``Item`` uses only safe identifiers, so this test asserts
        the basic smoke-test path still works — it's the entry point any
        user hits first.
        """
        db = DataFlow(test_suite.config.url, auto_migrate=True, pool_size=2)

        # Use a unique table_name to avoid colliding with other tests.
        @db.model
        class Issue480Item:
            __tablename__ = "issue480_items"
            id: str
            name: str

        await db.initialize()

        rid = f"x-{uuid.uuid4().hex[:8]}"
        created = await db.express.create("Issue480Item", {"id": rid, "name": "test"})
        assert created["id"] == rid
        assert created["name"] == "test"

        # State-persistence read-back — mandatory by rules/testing.md.
        fetched = await db.express.read("Issue480Item", rid)
        assert fetched is not None
        assert fetched["id"] == rid
        assert fetched["name"] == "test"

        # list returns at least the one row we created.
        rows = await db.express.list("Issue480Item")
        assert len(rows) >= 1
        assert any(r["id"] == rid for r in rows)

        await db.close_async()

    async def test_issue_480_reserved_word_columns_create_list_read(
        self, test_suite, _clean_tables
    ):
        """Reserved PG keywords as column names MUST round-trip.

        Pre-fix: ``CREATE TABLE ledgers (order INTEGER, desc TEXT, ...)``
        raises ``syntax error at or near "order"`` on PostgreSQL because
        ``order`` is a reserved word.  The SDK's auto-migration DDL and
        every CRUD SQL generator must quote the identifier so the reserved
        word is parsed as an identifier.
        """
        db = DataFlow(test_suite.config.url, auto_migrate=True, pool_size=2)

        @db.model
        class Issue480Ledger:
            __tablename__ = "issue480_ledgers"
            id: str
            order: int  # reserved word
            desc: str  # reserved word

        await db.initialize()
        rid = f"L-{uuid.uuid4().hex[:8]}"

        created = await db.express.create(
            "Issue480Ledger", {"id": rid, "order": 1, "desc": "initial"}
        )
        assert created["id"] == rid
        assert created["order"] == 1
        assert created["desc"] == "initial"

        fetched = await db.express.read("Issue480Ledger", rid)
        assert fetched is not None
        assert fetched["order"] == 1
        assert fetched["desc"] == "initial"

        rows = await db.express.list("Issue480Ledger")
        assert any(r["id"] == rid for r in rows)

        await db.close_async()

    async def test_issue_480_reserved_word_update_and_delete(
        self, test_suite, _clean_tables
    ):
        """UPDATE and DELETE also MUST quote reserved-word identifiers.

        Separate test because UPDATE has its own SQL-generation path in
        ``dataflow.core.nodes`` that diverged from the read/create path.
        See rules/testing.md § "Delegating Primitives Need Direct
        Coverage".
        """
        db = DataFlow(test_suite.config.url, auto_migrate=True, pool_size=2)

        @db.model
        class Issue480Ledger:
            __tablename__ = "issue480_ledgers"
            id: str
            order: int
            desc: str

        await db.initialize()
        rid = f"L-{uuid.uuid4().hex[:8]}"

        await db.express.create(
            "Issue480Ledger", {"id": rid, "order": 1, "desc": "initial"}
        )
        updated = await db.express.update(
            "Issue480Ledger", rid, {"order": 42, "desc": "patched"}
        )
        assert updated["order"] == 42
        assert updated["desc"] == "patched"

        # State-persistence verification: read-back after update.
        post = await db.express.read("Issue480Ledger", rid)
        assert post["order"] == 42
        assert post["desc"] == "patched"

        deleted = await db.express.delete("Issue480Ledger", rid)
        assert deleted is True

        after = await db.express.read("Issue480Ledger", rid)
        assert after is None

        await db.close_async()

    async def test_issue_480_camel_case_column_names_preserved(
        self, test_suite, _clean_tables
    ):
        """Mixed-case column names MUST round-trip identically.

        Pre-fix: ``CREATE TABLE customers (firstName TEXT, ...)`` stores
        the column as ``firstname`` because PostgreSQL lowercases
        unquoted identifiers.  The INSERT then returns
        ``{"firstname": ...}`` to the caller instead of ``{"firstName":
        ...}``, breaking round-tripping with user code that expects the
        camelCase key it passed in.
        """
        db = DataFlow(test_suite.config.url, auto_migrate=True, pool_size=2)

        @db.model
        class Issue480Customer:
            __tablename__ = "issue480_customers"
            id: str
            firstName: str

        await db.initialize()
        rid = f"c-{uuid.uuid4().hex[:8]}"

        created = await db.express.create(
            "Issue480Customer", {"id": rid, "firstName": "Alice"}
        )
        # Caller's camelCase key MUST survive the round-trip.
        assert (
            "firstName" in created
        ), f"firstName key lost in return (got keys: {list(created.keys())})"
        assert created["firstName"] == "Alice"

        fetched = await db.express.read("Issue480Customer", rid)
        assert fetched is not None
        assert fetched["firstName"] == "Alice"

        rows = await db.express.list("Issue480Customer")
        assert any(r.get("firstName") == "Alice" for r in rows)

        # Verify the actual column name stored in PostgreSQL is the
        # mixed-case form — this is what DataFlow's dialect-aware
        # identifier quoting guarantees.
        async with test_suite.get_connection() as conn:
            columns = await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'issue480_customers'
                """
            )
        column_names = {row["column_name"] for row in columns}
        assert (
            "firstName" in column_names
        ), f"mixed-case column lowercased by PostgreSQL (got: {column_names})"

        await db.close_async()
