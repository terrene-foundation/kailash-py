"""
Integration tests for Unsafe DDL Protection (TODO-130B).

Tests the addition of "IF NOT EXISTS" protection to CREATE TABLE statements
and transaction wrapping for DDL operations in DataFlow engine.

Focuses on:
- CREATE TABLE statements include "IF NOT EXISTS" clause
- Transaction wrapping for multi-statement DDL operations
- Rollback capability for failed DDL operations
- DDL safety across different database types (PostgreSQL, MySQL, SQLite)

NO MOCKING per ``rules/testing.md`` § Tier 2. Uses real PostgreSQL
via IntegrationTestSuite for tests that require DB execution; SQL-
generation tests build DataFlow without any patching because
``_generate_create_table_sql`` is a pure string method.
"""

import uuid

import pytest
from dataflow.core.engine import DataFlow

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def real_dataflow(test_suite):
    """Create a real DataFlow instance bound to the shared PostgreSQL."""
    df = DataFlow(
        database_url=test_suite.config.url,
        auto_migrate=False,
        migration_enabled=False,
        cache_enabled=False,
    )
    yield df
    try:
        df.close()
    except Exception:
        pass


class TestUnsafeDDLProtection:
    """Test DDL safety protection in DataFlow engine."""

    def test_create_table_includes_if_not_exists_postgresql(self, real_dataflow):
        """Test that CREATE TABLE statements include IF NOT EXISTS for PostgreSQL."""
        dataflow = real_dataflow

        # Test model fields
        model_fields = {
            "name": {"type": str, "required": True},
            "email": {"type": str, "required": False},
        }

        # Generate CREATE TABLE SQL for PostgreSQL
        sql = dataflow._generate_create_table_sql("User", "postgresql", model_fields)

        # Should include "IF NOT EXISTS" clause
        assert "CREATE TABLE IF NOT EXISTS" in sql.upper()
        assert "users (" in sql.lower()  # Table names are pluralized

    @pytest.mark.skip(reason="MySQL test infrastructure not configured in CI")
    def test_create_table_includes_if_not_exists_mysql(self):
        """Test that CREATE TABLE statements include IF NOT EXISTS for MySQL."""
        # MySQL fully supported since v0.5.6 - skipped only due to CI infrastructure
        # No patching: _generate_create_table_sql is a pure string method.
        # When MySQL is available, instantiate a DataFlow bound to a real
        # MySQL URL and call _generate_create_table_sql directly.
        pytest.skip("MySQL test infrastructure not configured in CI")

    def test_create_table_includes_if_not_exists_sqlite(self, tmp_path):
        """Test that CREATE TABLE statements include IF NOT EXISTS for SQLite.

        Uses a real file-backed SQLite database so DataFlow's init path runs
        end-to-end without any patching.
        """
        db_file = tmp_path / "unsafe_ddl.db"
        dataflow = DataFlow(
            database_url=f"sqlite:///{db_file}",
            auto_migrate=False,
            migration_enabled=False,
            cache_enabled=False,
        )
        try:
            model_fields = {
                "product_name": {"type": str, "required": True},
                "price": {"type": float, "required": True},
            }

            # Generate CREATE TABLE SQL for SQLite
            sql = dataflow._generate_create_table_sql("Product", "sqlite", model_fields)

            # Should include "IF NOT EXISTS" clause
            assert "CREATE TABLE IF NOT EXISTS" in sql.upper()
            assert "products (" in sql.lower()  # Table names are pluralized
        finally:
            try:
                dataflow.close()
            except Exception:
                pass

    async def test_ddl_operations_wrapped_in_transaction(
        self, real_dataflow, test_suite
    ):
        """Test that DDL operations execute via a real transaction and persist.

        Uses a unique table name per run so the test is idempotent, then
        verifies the table exists via a separate read-back connection
        (state-persistence verification per ``rules/testing.md``).
        """
        dataflow = real_dataflow
        table = f"ddl_safety_{uuid.uuid4().hex[:8]}"
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {table} " "(id SERIAL PRIMARY KEY, note TEXT)"
        )
        try:
            dataflow._execute_ddl_with_transaction(ddl)
            async with test_suite.get_connection() as conn:
                row = await conn.fetchrow(
                    "SELECT to_regclass($1) AS oid", f"public.{table}"
                )
                assert (
                    row["oid"] is not None
                ), f"Expected {table} to exist after DDL transaction"
        finally:
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    async def test_ddl_transaction_rollback_on_error(self, real_dataflow, test_suite):
        """Test that DDL transactions roll back on error.

        Submits a deliberately invalid DDL statement against real PostgreSQL
        and verifies that (a) the driver raises, and (b) no partial schema
        is left behind.
        """
        dataflow = real_dataflow
        table = f"ddl_rb_{uuid.uuid4().hex[:8]}"
        # Deliberately invalid column definition to trigger a rollback
        bad_ddl = f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, INVALID_COLUMN_DEF)"
        with pytest.raises(Exception):
            dataflow._execute_ddl_with_transaction(bad_ddl)

        async with test_suite.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT to_regclass($1) AS oid", f"public.{table}"
            )
            assert (
                row["oid"] is None
            ), f"Expected {table} to NOT exist after rolled-back DDL"

    async def test_multi_statement_ddl_transaction_safety(
        self, real_dataflow, test_suite
    ):
        """Test transaction safety for multi-statement DDL operations."""
        dataflow = real_dataflow
        users_table = f"ddl_users_{uuid.uuid4().hex[:8]}"
        posts_table = f"ddl_posts_{uuid.uuid4().hex[:8]}"
        ddl_statements = [
            (
                f"CREATE TABLE IF NOT EXISTS {users_table} "
                "(id SERIAL PRIMARY KEY, name VARCHAR(100))"
            ),
            f"CREATE INDEX IF NOT EXISTS idx_{users_table}_name ON {users_table}(name)",
            (
                f"CREATE TABLE IF NOT EXISTS {posts_table} "
                f"(id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES {users_table}(id))"
            ),
        ]
        try:
            dataflow._execute_multi_statement_ddl(ddl_statements)
            async with test_suite.get_connection() as conn:
                for name in (users_table, posts_table):
                    row = await conn.fetchrow(
                        "SELECT to_regclass($1) AS oid", f"public.{name}"
                    )
                    assert (
                        row["oid"] is not None
                    ), f"Expected {name} to exist after multi-statement DDL"
        finally:
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {posts_table} CASCADE")
                await conn.execute(f"DROP TABLE IF EXISTS {users_table} CASCADE")

    async def test_partial_ddl_failure_triggers_complete_rollback(
        self, real_dataflow, test_suite
    ):
        """Partial DDL failure MUST trigger full rollback of all statements."""
        dataflow = real_dataflow
        good_table = f"ddl_good_{uuid.uuid4().hex[:8]}"
        never_table = f"ddl_never_{uuid.uuid4().hex[:8]}"
        ddl_statements = [
            f"CREATE TABLE IF NOT EXISTS {good_table} (id SERIAL PRIMARY KEY)",
            "INVALID SQL STATEMENT",  # This will fail
            f"CREATE TABLE IF NOT EXISTS {never_table} (id SERIAL PRIMARY KEY)",
        ]
        try:
            with pytest.raises(Exception):
                dataflow._execute_multi_statement_ddl(ddl_statements)
            async with test_suite.get_connection() as conn:
                for name in (good_table, never_table):
                    row = await conn.fetchrow(
                        "SELECT to_regclass($1) AS oid", f"public.{name}"
                    )
                    assert (
                        row["oid"] is None
                    ), f"Expected {name} to NOT exist after rolled-back batch"
        finally:
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {never_table} CASCADE")
                await conn.execute(f"DROP TABLE IF EXISTS {good_table} CASCADE")

    def test_ddl_safety_preserves_existing_tables(self, tmp_path):
        """Test that DDL safety prevents accidental table recreation."""
        db_file = tmp_path / "safety.db"
        dataflow = DataFlow(
            database_url=f"sqlite:///{db_file}",
            auto_migrate=False,
            migration_enabled=False,
            cache_enabled=False,
        )
        try:
            model_fields = {"username": {"type": str, "required": True}}

            # Generate SQL - should be safe for existing tables
            sql = dataflow._generate_create_table_sql("User", "sqlite", model_fields)

            # SQL should not drop or replace existing tables
            assert "DROP TABLE" not in sql.upper()
            assert "CREATE OR REPLACE" not in sql.upper()
            assert "IF NOT EXISTS" in sql.upper()
        finally:
            try:
                dataflow.close()
            except Exception:
                pass

    async def test_ddl_error_logging_and_reporting(self, real_dataflow, caplog):
        """Test that DDL errors are properly logged and reported via real logger."""
        import logging

        dataflow = real_dataflow
        with caplog.at_level(logging.ERROR, logger="dataflow.core.engine"):
            with pytest.raises(Exception):
                dataflow._execute_ddl_with_transaction(
                    "CREATE TABLE _invalid_name_with_bad_col (id SERIAL, INVALID)"
                )

        # Error should have been logged
        assert any(
            "DDL" in rec.message or "error" in rec.message.lower()
            for rec in caplog.records
        ), "Expected an ERROR log entry for the failed DDL"

    def test_ddl_safety_with_complex_schema(self, real_dataflow):
        """Test DDL safety with complex schema including indexes and foreign keys."""
        dataflow = real_dataflow
        model_fields = {
            "title": {"type": str, "required": True, "index": True},
            "user_id": {"type": int, "required": True, "foreign_key": "users.id"},
            "created_at": {"type": "datetime", "required": False, "default": "now()"},
        }

        # Generate CREATE TABLE SQL with complex schema
        sql = dataflow._generate_create_table_sql("Article", "postgresql", model_fields)

        # Should be safe and include IF NOT EXISTS
        assert "CREATE TABLE IF NOT EXISTS" in sql.upper()
        assert "articles (" in sql.lower()  # Table names are pluralized

        # Should include all field definitions
        assert "title" in sql.lower()
        assert "user_id" in sql.lower()
        assert "created_at" in sql.lower()

    def test_database_type_specific_ddl_safety(self, real_dataflow):
        """Test that DDL safety is applied correctly for different database types."""
        dataflow = real_dataflow

        # Testing with PostgreSQL (shared test infrastructure)
        database_types = ["postgresql"]

        model_fields = {"name": {"type": str, "required": True}}

        for db_type in database_types:
            sql = dataflow._generate_create_table_sql(
                "TestModel", db_type, model_fields
            )

            # All database types should include IF NOT EXISTS
            assert (
                "IF NOT EXISTS" in sql.upper()
            ), f"Missing IF NOT EXISTS for {db_type}"
            assert "CREATE TABLE" in sql.upper(), f"Missing CREATE TABLE for {db_type}"
