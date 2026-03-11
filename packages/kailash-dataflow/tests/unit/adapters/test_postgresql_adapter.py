"""
Unit tests for PostgreSQL database adapter.

Tests PostgreSQL-specific functionality without requiring database connection.
"""

import asyncio
import warnings
from unittest.mock import AsyncMock, Mock, patch

import pytest
from dataflow.adapters.exceptions import ConnectionError, QueryError, TransactionError
from dataflow.adapters.postgresql import PostgreSQLAdapter, PostgreSQLTransaction


class TestPostgreSQLAdapter:
    """Test PostgreSQL adapter functionality."""

    def test_adapter_initialization(self):
        """Test PostgreSQL adapter initializes correctly."""
        connection_string = "postgresql://test:test@localhost:5432/testdb"

        adapter = PostgreSQLAdapter(connection_string, pool_size=15, max_overflow=25)

        assert adapter.connection_string == connection_string
        assert adapter.scheme == "postgresql"
        assert adapter.host == "localhost"
        assert adapter.port == 5432
        assert adapter.database == "testdb"
        assert adapter.username == "test"
        assert adapter.password == "test"
        assert adapter.pool_size == 15
        assert adapter.max_overflow == 25
        assert not adapter.is_connected

    def test_get_dialect(self):
        """Test PostgreSQL dialect identification."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        dialect = adapter.get_dialect()

        assert dialect == "postgresql"

    @pytest.mark.asyncio
    async def test_create_connection_pool_success(self):
        """Test successful connection pool creation."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock asyncpg.create_pool
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.release = AsyncMock()
        mock_pool.close = AsyncMock()

        with patch(
            "asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool
        ):
            await adapter.create_connection_pool()

            assert adapter.connection_pool == mock_pool
            assert adapter.is_connected

    @pytest.mark.asyncio
    async def test_create_connection_pool_failure(self):
        """Test connection pool creation failure."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        with patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            side_effect=Exception("Connection failed"),
        ):
            with pytest.raises(ConnectionError):
                await adapter.create_connection_pool()

            assert adapter.connection_pool is None
            assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_execute_query_success(self):
        """Test successful query execution."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock connection pool and connection
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = [{"id": 1, "name": "test"}]

        # Create a proper async context manager class
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        result = await adapter.execute_query("SELECT * FROM users")

        assert result == [{"id": 1, "name": "test"}]
        mock_connection.fetch.assert_called_once_with("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_execute_query_with_params(self):
        """Test query execution with parameters."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock connection
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = [{"id": 1, "name": "Alice"}]

        # Create a proper async context manager class
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        result = await adapter.execute_query("SELECT * FROM users WHERE id = $1", [1])

        assert result == [{"id": 1, "name": "Alice"}]
        mock_connection.fetch.assert_called_once_with(
            "SELECT * FROM users WHERE id = $1", 1
        )

    @pytest.mark.asyncio
    async def test_execute_query_not_connected(self):
        """Test query execution when not connected."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        with pytest.raises(ConnectionError):
            await adapter.execute_query("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_execute_query_error(self):
        """Test query execution with database error."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock connection that raises error
        mock_connection = AsyncMock()
        mock_connection.fetch.side_effect = Exception("Table does not exist")

        # Create a proper async context manager class
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        with pytest.raises(QueryError):
            await adapter.execute_query("SELECT * FROM nonexistent_table")

    @pytest.mark.asyncio
    async def test_execute_insert_query(self):
        """Test INSERT query execution."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock connection for INSERT
        mock_connection = AsyncMock()
        mock_connection.execute.return_value = "INSERT 0 1"  # PostgreSQL response

        # Create a proper async context manager class
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        result = await adapter.execute_insert(
            "INSERT INTO users (name) VALUES ($1)", ["Alice"]
        )

        assert result == "INSERT 0 1"
        mock_connection.execute.assert_called_once_with(
            "INSERT INTO users (name) VALUES ($1)", "Alice"
        )

    @pytest.mark.asyncio
    async def test_execute_bulk_insert(self):
        """Test bulk insert operation."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock connection for bulk insert
        mock_connection = AsyncMock()
        mock_connection.executemany.return_value = None

        # Create a proper async context manager class
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        data = [("Alice",), ("Bob",), ("Charlie",)]
        await adapter.execute_bulk_insert("INSERT INTO users (name) VALUES ($1)", data)

        mock_connection.executemany.assert_called_once_with(
            "INSERT INTO users (name) VALUES ($1)", data
        )

    @pytest.mark.asyncio
    async def test_close_connection_pool(self):
        """Test connection pool cleanup."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock connection pool
        mock_pool = AsyncMock()
        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        await adapter.close_connection_pool()

        mock_pool.close.assert_called_once()
        assert adapter.connection_pool is None
        assert not adapter.is_connected

    def test_get_connection_parameters(self):
        """Test extracting connection parameters for asyncpg."""
        adapter = PostgreSQLAdapter(
            "postgresql://test:test@localhost:5432/testdb?sslmode=require"
        )

        params = adapter.get_connection_parameters()

        expected_params = {
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "user": "test",
            "password": "test",
            "min_size": 10,  # pool_size
            "max_size": 30,  # pool_size + max_overflow
        }

        for key, value in expected_params.items():
            assert params[key] == value

    def test_format_query_postgresql_style(self):
        """Test PostgreSQL-style parameter formatting."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Test standard parameter substitution
        query = "SELECT * FROM users WHERE id = ? AND name = ?"
        params = [1, "Alice"]

        formatted_query, formatted_params = adapter.format_query(query, params)

        assert formatted_query == "SELECT * FROM users WHERE id = $1 AND name = $2"
        assert formatted_params == params

    def test_supports_feature(self):
        """Test PostgreSQL feature support."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # PostgreSQL supports these features
        assert adapter.supports_feature("json")
        assert adapter.supports_feature("arrays")
        assert adapter.supports_feature("window_functions")
        assert adapter.supports_feature("cte")  # Common Table Expressions
        assert adapter.supports_feature("fulltext_search")  # Use correct feature name

        # PostgreSQL doesn't support these features
        assert not adapter.supports_feature("nonexistent_feature")

    @pytest.mark.asyncio
    async def test_transaction_context(self):
        """Test transaction context management."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Mock transaction with proper async methods
        mock_transaction = AsyncMock()
        mock_transaction.start = AsyncMock()
        mock_transaction.commit = AsyncMock()
        mock_transaction.rollback = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.transaction = Mock(return_value=mock_transaction)

        # Mock pool with acquire/release
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)
        mock_pool.release = AsyncMock()

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        async with adapter.transaction() as trans:
            # Transaction should be available through the context manager
            pass

        # Verify transaction lifecycle methods were called
        mock_connection.transaction.assert_called_once()
        mock_transaction.start.assert_called_once()
        mock_transaction.commit.assert_called_once()

    def test_get_schema_info(self):
        """Test getting schema information queries."""
        adapter = PostgreSQLAdapter("postgresql://test:test@localhost:5432/testdb")

        # Test table list query
        tables_query = adapter.get_tables_query()
        assert "information_schema.tables" in tables_query
        assert "table_type = 'BASE TABLE'" in tables_query

        # Test column info query
        columns_query = adapter.get_columns_query("users")
        assert "information_schema.columns" in columns_query
        assert "table_name = 'users'" in columns_query


class TestPostgreSQLTransactionDel:
    """Test PostgreSQLTransaction __del__ fallback behavior."""

    def test_class_level_defaults_exist(self):
        """Test that class-level defaults are defined as safety net."""
        # Class-level defaults should exist even before __init__ runs
        assert hasattr(PostgreSQLTransaction, "_committed")
        assert hasattr(PostgreSQLTransaction, "_rolled_back")
        assert hasattr(PostgreSQLTransaction, "connection")
        assert hasattr(PostgreSQLTransaction, "_source_traceback")

        # Verify the class-level default values
        assert PostgreSQLTransaction._committed is False
        assert PostgreSQLTransaction._rolled_back is False
        assert PostgreSQLTransaction.connection is None
        assert PostgreSQLTransaction._source_traceback is None

    def test_init_sets_committed_and_rolled_back_flags(self):
        """Test that __init__ sets _committed and _rolled_back to False."""
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)

        assert txn._committed is False
        assert txn._rolled_back is False

    def test_init_captures_source_traceback_in_debug_mode(self):
        """Test that __init__ captures source traceback when __debug__ is True."""
        # __debug__ is True by default (unless running with -O flag)
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)

        # In normal (non-optimized) Python, __debug__ is True,
        # so _source_traceback should be a StackSummary
        if __debug__:
            assert txn._source_traceback is not None
            assert len(txn._source_traceback) > 0
        else:
            # If running with -O, traceback should not be captured
            assert txn._source_traceback is None

    def test_del_no_warning_when_committed(self):
        """Test that __del__ does NOT warn when transaction was committed."""
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)
        txn.connection = Mock()  # Simulate acquired connection
        txn._committed = True

        # Should not emit any ResourceWarning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_no_warning_when_rolled_back(self):
        """Test that __del__ does NOT warn when transaction was rolled back."""
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)
        txn.connection = Mock()  # Simulate acquired connection
        txn._rolled_back = True

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_no_warning_when_connection_is_none(self):
        """Test that __del__ does NOT warn when connection was never acquired."""
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)
        # connection is None by default (never entered __aenter__)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_warns_when_not_committed_or_rolled_back(self):
        """Test that __del__ emits ResourceWarning for abandoned transaction."""
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)
        txn.connection = Mock()  # Simulate acquired connection
        # Neither committed nor rolled back — abandoned transaction

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 1
            warning_message = str(resource_warnings[0].message)
            assert (
                "PostgreSQLTransaction GC'd without commit/rollback" in warning_message
            )

    def test_del_warning_includes_source_traceback(self):
        """Test that __del__ warning message includes creation traceback."""
        mock_pool = Mock()
        txn = PostgreSQLTransaction(mock_pool)
        txn.connection = Mock()  # Simulate acquired connection

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 1
            warning_message = str(resource_warnings[0].message)

            # When __debug__ is True, traceback should be included
            if __debug__:
                assert "Created at:" in warning_message
                # The traceback should reference this test file
                assert "test_postgresql_adapter" in warning_message
            else:
                assert "unknown" in warning_message

    @pytest.mark.asyncio
    async def test_aexit_sets_committed_on_success(self):
        """Test that __aexit__ sets _committed = True on successful exit."""
        mock_transaction = AsyncMock()
        mock_transaction.start = AsyncMock()
        mock_transaction.commit = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.transaction = Mock(return_value=mock_transaction)

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)
        mock_pool.release = AsyncMock()

        txn = PostgreSQLTransaction(mock_pool)

        async with txn:
            pass  # No exception — should commit

        assert txn._committed is True
        assert txn._rolled_back is False

    @pytest.mark.asyncio
    async def test_aexit_sets_rolled_back_on_exception(self):
        """Test that __aexit__ sets _rolled_back = True on exception."""
        mock_transaction = AsyncMock()
        mock_transaction.start = AsyncMock()
        mock_transaction.commit = AsyncMock()
        mock_transaction.rollback = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.transaction = Mock(return_value=mock_transaction)

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)
        mock_pool.release = AsyncMock()

        txn = PostgreSQLTransaction(mock_pool)

        with pytest.raises(ValueError, match="test error"):
            async with txn:
                raise ValueError("test error")

        assert txn._committed is False
        assert txn._rolled_back is True

    @pytest.mark.asyncio
    async def test_no_warning_after_normal_context_manager_usage(self):
        """Test that proper context manager usage does not trigger __del__ warning."""
        mock_transaction = AsyncMock()
        mock_transaction.start = AsyncMock()
        mock_transaction.commit = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.transaction = Mock(return_value=mock_transaction)

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)
        mock_pool.release = AsyncMock()

        txn = PostgreSQLTransaction(mock_pool)

        async with txn:
            pass

        # After proper usage, __del__ should not warn
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0
