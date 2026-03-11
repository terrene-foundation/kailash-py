"""
Unit tests for Unsafe DDL Protection (TODO-130B).

Tests the addition of "IF NOT EXISTS" protection to CREATE TABLE statements
and transaction wrapping for DDL operations in DataFlow engine.

Focuses on:
- CREATE TABLE statements include "IF NOT EXISTS" clause
- Transaction wrapping for multi-statement DDL operations
- Rollback capability for failed DDL operations
- DDL safety across different database types (PostgreSQL, MySQL, SQLite)
"""

from unittest.mock import patch

import pytest

from dataflow.core.engine import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite
from tests.utils.real_infrastructure import real_infra


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestUnsafeDDLProtection:
    """Test DDL safety protection in DataFlow engine."""

    def test_create_table_includes_if_not_exists_postgresql(self, test_suite):
        """Test that CREATE TABLE statements include IF NOT EXISTS for PostgreSQL."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

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
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url="mysql://user:pass@localhost:3306/test")

        model_fields = {
            "title": {"type": str, "required": True},
            "content": {"type": str, "required": False},
        }

        # Generate CREATE TABLE SQL for MySQL
        sql = dataflow._generate_create_table_sql("Post", "mysql", model_fields)

        # Should include "IF NOT EXISTS" clause
        assert "CREATE TABLE IF NOT EXISTS" in sql.upper()
        assert "posts (" in sql.lower()  # Table names are pluralized

    def test_create_table_includes_if_not_exists_sqlite(self):
        """Test that CREATE TABLE statements include IF NOT EXISTS for SQLite."""
        # SQLite fully supported since v0.1.0
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url="sqlite:///test.db")

        model_fields = {
            "product_name": {"type": str, "required": True},
            "price": {"type": float, "required": True},
        }

        # Generate CREATE TABLE SQL for SQLite
        sql = dataflow._generate_create_table_sql("Product", "sqlite", model_fields)

        # Should include "IF NOT EXISTS" clause
        assert "CREATE TABLE IF NOT EXISTS" in sql.upper()
        assert "products (" in sql.lower()  # Table names are pluralized

    def test_ddl_operations_wrapped_in_transaction(self, test_suite):
        """Test that DDL operations are wrapped in database transactions."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

        # Mock database connection and transaction
        # TODO: Use real connection from real_infra
        # TODO: Use real transaction from real_infra
        mock_connection.begin.return_value = mock_transaction

        with patch.object(
            dataflow, "_get_database_connection", return_value=mock_connection
        ):
            # Execute DDL operation
            dataflow._execute_ddl_with_transaction(
                "CREATE TABLE IF NOT EXISTS test (id SERIAL PRIMARY KEY)"
            )

        # Verify transaction was used
        mock_connection.begin.assert_called_once()
        mock_transaction.commit.assert_called_once()

    def test_ddl_transaction_rollback_on_error(self, test_suite):
        """Test that DDL transactions are rolled back on error."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

        # Mock database connection and transaction
        # TODO: Use real connection from real_infra
        # TODO: Use real transaction from real_infra
        mock_connection.begin.return_value = mock_transaction
        mock_connection.execute.side_effect = Exception("DDL execution failed")

        with patch.object(
            dataflow, "_get_database_connection", return_value=mock_connection
        ):
            # Execute DDL operation that will fail
            with pytest.raises(Exception, match="DDL execution failed"):
                dataflow._execute_ddl_with_transaction(
                    "CREATE TABLE test (invalid syntax)"
                )

        # Verify transaction was rolled back
        mock_connection.begin.assert_called_once()
        mock_transaction.rollback.assert_called_once()
        mock_transaction.commit.assert_not_called()

    def test_multi_statement_ddl_transaction_safety(self, test_suite):
        """Test transaction safety for multi-statement DDL operations."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

        # Mock database connection
        # TODO: Use real connection from real_infra
        # TODO: Use real transaction from real_infra
        mock_connection.begin.return_value = mock_transaction

        ddl_statements = [
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name VARCHAR(100))",
            "CREATE INDEX IF NOT EXISTS idx_users_name ON users(name)",
            "CREATE TABLE IF NOT EXISTS posts (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id))",
        ]

        with patch.object(
            dataflow, "_get_database_connection", return_value=mock_connection
        ):
            dataflow._execute_multi_statement_ddl(ddl_statements)

        # Verify all statements were executed in single transaction
        mock_connection.begin.assert_called_once()
        assert mock_connection.execute.call_count == len(ddl_statements)
        mock_transaction.commit.assert_called_once()

    def test_partial_ddl_failure_triggers_complete_rollback(self, test_suite):
        """Test that partial DDL failure triggers complete rollback of all statements."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

        # Mock database connection - second statement will fail
        # TODO: Use real connection from real_infra
        # TODO: Use real transaction from real_infra
        mock_connection.begin.return_value = mock_transaction
        mock_connection.execute.side_effect = [
            None,
            Exception("Second statement failed"),
            None,
        ]

        ddl_statements = [
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY)",
            "INVALID SQL STATEMENT",  # This will fail
            "CREATE TABLE IF NOT EXISTS posts (id SERIAL PRIMARY KEY)",
        ]

        with patch.object(
            dataflow, "_get_database_connection", return_value=mock_connection
        ):
            with pytest.raises(Exception, match="Second statement failed"):
                dataflow._execute_multi_statement_ddl(ddl_statements)

        # Verify rollback was called and commit was not
        mock_transaction.rollback.assert_called_once()
        mock_transaction.commit.assert_not_called()

    def test_ddl_safety_preserves_existing_tables(self):
        """Test that DDL safety prevents accidental table recreation."""
        # SQLite fully supported since v0.1.0
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url="sqlite:///test.db")

        model_fields = {"username": {"type": str, "required": True}}

        # Generate SQL - should be safe for existing tables
        sql = dataflow._generate_create_table_sql("User", "sqlite", model_fields)

        # SQL should not drop or replace existing tables
        assert "DROP TABLE" not in sql.upper()
        assert "CREATE OR REPLACE" not in sql.upper()
        assert "IF NOT EXISTS" in sql.upper()

    def test_ddl_error_logging_and_reporting(self, test_suite):
        """Test that DDL errors are properly logged and reported."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

        # Mock logger
        with patch("dataflow.core.engine.logger") as mock_logger:
            # TODO: Use real connection from real_infra
            # TODO: Use real transaction from real_infra
            mock_connection.begin.return_value = mock_transaction
            mock_connection.execute.side_effect = Exception(
                "DDL failed with detailed error"
            )

            with patch.object(
                dataflow, "_get_database_connection", return_value=mock_connection
            ):
                with pytest.raises(Exception):
                    dataflow._execute_ddl_with_transaction(
                        "CREATE TABLE test (id SERIAL)"
                    )

            # Verify error was logged
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "DDL failed" in error_call

    def test_ddl_safety_with_complex_schema(self, test_suite):
        """Test DDL safety with complex schema including indexes and foreign keys."""
        with patch("dataflow.core.engine.DataFlow._initialize_database"):
            dataflow = DataFlow(database_url=test_suite.config.url)

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

    def test_database_type_specific_ddl_safety(self, test_suite):
        """Test that DDL safety is applied correctly for different database types."""
        # Testing with PostgreSQL (shared test infrastructure)
        database_configs = [
            (test_suite.config.url, "postgresql"),
        ]

        model_fields = {"name": {"type": str, "required": True}}

        for db_url, db_type in database_configs:
            with patch("dataflow.core.engine.DataFlow._initialize_database"):
                dataflow = DataFlow(database_url=test_suite.config.url)

            sql = dataflow._generate_create_table_sql(
                "TestModel", db_type, model_fields
            )

            # All database types should include IF NOT EXISTS
            assert (
                "IF NOT EXISTS" in sql.upper()
            ), f"Missing IF NOT EXISTS for {db_type}"
            assert "CREATE TABLE" in sql.upper(), f"Missing CREATE TABLE for {db_type}"
