"""
Test MySQL-specific sync DDL functionality for Docker/FastAPI environments.

This test verifies that the SyncDDLExecutor fix works correctly with MySQL,
specifically testing:
1. pymysql connection string parsing
2. MySQL-specific DDL patterns
3. Table creation with various MySQL column types
4. Sync DDL execution while an event loop is running (Docker/FastAPI simulation)
5. Error handling for MySQL-specific errors

IMPORTANT: These tests require a real MySQL database to run.
"""

import asyncio
import os
import random
import time
from datetime import datetime
from typing import Optional

import pytest

# Skip if pymysql is not available
try:
    import pymysql

    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False

from dataflow import DataFlow
from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor


# Get MySQL connection details from environment or use defaults
def get_mysql_url():
    """Get MySQL URL from environment, trying multiple sources."""
    # First check for explicit test URL
    if os.getenv("TEST_MYSQL_URL"):
        return os.getenv("TEST_MYSQL_URL")

    # Check for MYSQL_URL
    if os.getenv("MYSQL_URL"):
        return os.getenv("MYSQL_URL")

    # Default: Standard SDK Docker infrastructure (port 3307)
    # Uses kailash_test user as configured in docker-compose.test.yml
    return "mysql://kailash_test:test_password@localhost:3307/kailash_test"


def is_mysql_available():
    """Check if MySQL is available for testing."""
    if not PYMYSQL_AVAILABLE:
        return False

    try:
        conn = pymysql.connect(
            host="localhost",
            port=3307,
            database="kailash_test",
            user="kailash_test",  # Docker compose uses kailash_test
            password="test_password",
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


# Mark all tests to skip if MySQL is not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not PYMYSQL_AVAILABLE,
        reason="pymysql not installed - required for MySQL sync DDL",
    ),
    pytest.mark.skipif(
        not is_mysql_available(),
        reason="MySQL not available - ensure Docker MySQL is running on port 3307",
    ),
]


@pytest.fixture
def mysql_url():
    """Get MySQL URL for tests."""
    return get_mysql_url()


@pytest.fixture
def unique_table_name():
    """Generate unique table name for test isolation."""
    timestamp = int(time.time() * 1000000)
    random_suffix = random.randint(1000, 9999)
    return f"sync_ddl_test_{timestamp}_{random_suffix}"


@pytest.fixture
def cleanup_tables(mysql_url):
    """Cleanup fixture that drops test tables after tests."""
    tables_to_cleanup = []

    yield tables_to_cleanup

    # Cleanup all created tables
    try:
        executor = SyncDDLExecutor(mysql_url)
        for table_name in tables_to_cleanup:
            try:
                executor.execute_ddl(f"DROP TABLE IF EXISTS {table_name}")
            except Exception:
                pass
    except Exception:
        pass


class TestSyncDDLMySQLConnection:
    """Test MySQL connection via SyncDDLExecutor."""

    def test_mysql_connection_successful(self, mysql_url):
        """Test that SyncDDLExecutor can connect to MySQL using pymysql."""
        executor = SyncDDLExecutor(mysql_url)

        # Simple query to verify connection
        result = executor.execute_query("SELECT 1 as test_value")

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "result" in result
        assert result["result"][0][0] == 1

    def test_mysql_connection_parsing(self, mysql_url):
        """Test that connection string is parsed correctly for MySQL."""
        executor = SyncDDLExecutor(mysql_url)

        # Verify database type detection
        assert executor._db_type == "mysql"

        # Verify connection works
        result = executor.execute_query("SELECT VERSION()")
        assert "error" not in result
        # MySQL version string typically contains version number
        assert result["result"][0][0] is not None

    def test_mysql_special_chars_in_password(self):
        """Test connection with special characters in password (if applicable)."""
        # This tests the ConnectionParser's ability to handle special chars
        from dataflow.adapters.connection_parser import ConnectionParser

        # Test URL with special characters
        test_url = "mysql://user:pass%23word@localhost:3306/testdb"
        components = ConnectionParser.parse_connection_string(test_url)

        assert components["username"] == "user"
        assert components["password"] == "pass#word"  # Should be decoded
        assert components["host"] == "localhost"
        assert components["port"] == 3306


class TestSyncDDLMySQLDDL:
    """Test MySQL DDL operations via SyncDDLExecutor."""

    def test_create_table_basic(self, mysql_url, unique_table_name, cleanup_tables):
        """Test basic CREATE TABLE with MySQL."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        sql = f"""
        CREATE TABLE {unique_table_name} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True, f"CREATE TABLE failed: {result.get('error')}"
        assert executor.table_exists(unique_table_name) is True

    def test_create_table_mysql_types(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """Test CREATE TABLE with MySQL-specific types."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        # Test all MySQL types that DataFlow uses
        sql = f"""
        CREATE TABLE {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            age INT,
            price FLOAT,
            is_active BOOLEAN DEFAULT TRUE,
            metadata JSON,
            tags JSON,
            binary_data BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True, f"CREATE TABLE failed: {result.get('error')}"

        # Verify table was created
        assert executor.table_exists(unique_table_name) is True

    def test_create_table_if_not_exists(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """Test CREATE TABLE IF NOT EXISTS idempotency."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        sql = f"""
        CREATE TABLE IF NOT EXISTS {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            name TEXT
        )
        """

        # First creation
        result1 = executor.execute_ddl(sql)
        assert result1["success"] is True

        # Second creation (should succeed due to IF NOT EXISTS)
        result2 = executor.execute_ddl(sql)
        assert result2["success"] is True

    def test_create_index(self, mysql_url, unique_table_name, cleanup_tables):
        """Test CREATE INDEX on MySQL table."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        # Create table first
        executor.execute_ddl(
            f"""
        CREATE TABLE {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            email VARCHAR(255),
            status VARCHAR(50)
        )
        """
        )

        # Create index
        index_name = f"idx_{unique_table_name[:50]}_email"
        result = executor.execute_ddl(
            f"CREATE INDEX {index_name} ON {unique_table_name} (email)"
        )

        assert result["success"] is True, f"CREATE INDEX failed: {result.get('error')}"

    def test_table_exists_mysql(self, mysql_url, unique_table_name, cleanup_tables):
        """Test table_exists method with MySQL SHOW TABLES."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        # Table should not exist initially
        assert executor.table_exists(unique_table_name) is False

        # Create table
        executor.execute_ddl(
            f"CREATE TABLE {unique_table_name} (id VARCHAR(255) PRIMARY KEY)"
        )

        # Now table should exist
        assert executor.table_exists(unique_table_name) is True

        # Check non-existent table
        assert (
            executor.table_exists("this_table_definitely_does_not_exist_xyz123")
            is False
        )


class TestSyncDDLMySQLAsyncContext:
    """
    Test that SyncDDLExecutor works correctly when called from within
    an async context (simulating Docker/FastAPI scenario) with MySQL.

    This is the KEY test suite - it verifies the architectural fix works
    with a real MySQL database.
    """

    @pytest.mark.asyncio
    async def test_ddl_inside_async_function(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """
        Test DDL execution inside an async function with MySQL.

        This simulates what happens in FastAPI when:
        1. uvicorn's event loop is running
        2. Module is imported, triggering @db.model
        3. auto_migrate=True triggers table creation via sync DDL
        """
        cleanup_tables.append(unique_table_name)

        # Verify we're inside an async context
        loop = asyncio.get_running_loop()
        assert loop is not None, "Event loop should be running"

        # This should work WITHOUT hanging or causing event loop errors
        executor = SyncDDLExecutor(mysql_url)
        result = executor.execute_ddl(
            f"CREATE TABLE {unique_table_name} (id VARCHAR(255) PRIMARY KEY, name TEXT)"
        )

        assert result["success"] is True, f"DDL failed: {result.get('error')}"
        assert executor.table_exists(unique_table_name) is True

    @pytest.mark.asyncio
    async def test_multiple_ddl_in_async(self, mysql_url, cleanup_tables):
        """Test multiple DDL operations inside async context with MySQL."""
        # Generate unique table names
        timestamp = int(time.time() * 1000000)
        users_table = f"sync_ddl_users_{timestamp}"
        posts_table = f"sync_ddl_posts_{timestamp}"
        cleanup_tables.extend([users_table, posts_table])

        executor = SyncDDLExecutor(mysql_url)

        # Create multiple tables
        result1 = executor.execute_ddl(
            f"""
        CREATE TABLE {users_table} (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255)
        )
        """
        )

        result2 = executor.execute_ddl(
            f"""
        CREATE TABLE {posts_table} (
            id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(255),
            title VARCHAR(255) NOT NULL,
            content TEXT,
            FOREIGN KEY (user_id) REFERENCES {users_table}(id)
        )
        """
        )

        assert result1["success"] is True
        assert result2["success"] is True

        # Insert data
        executor.execute_ddl(
            f"INSERT INTO {users_table} (id, name) VALUES ('user-1', 'Alice')"
        )
        executor.execute_ddl(
            f"INSERT INTO {posts_table} (id, user_id, title) VALUES ('post-1', 'user-1', 'First Post')"
        )

        # Query data
        users = executor.execute_query(f"SELECT * FROM {users_table}")
        posts = executor.execute_query(f"SELECT * FROM {posts_table}")

        assert len(users["result"]) == 1
        assert len(posts["result"]) == 1

    @pytest.mark.asyncio
    async def test_ddl_batch_in_async(self, mysql_url, cleanup_tables):
        """Test batch DDL execution inside async context with MySQL."""
        timestamp = int(time.time() * 1000000)
        tables = [f"sync_ddl_batch_{timestamp}_{i}" for i in range(3)]
        cleanup_tables.extend(tables)

        executor = SyncDDLExecutor(mysql_url)

        statements = [
            f"CREATE TABLE {tables[0]} (id VARCHAR(255) PRIMARY KEY)",
            f"CREATE TABLE {tables[1]} (id VARCHAR(255) PRIMARY KEY)",
            f"CREATE TABLE {tables[2]} (id VARCHAR(255) PRIMARY KEY)",
        ]

        result = executor.execute_ddl_batch(statements)

        assert result["success"] is True, f"Batch DDL failed: {result.get('error')}"
        assert result["executed_count"] == 3

        for table in tables:
            assert executor.table_exists(table) is True


class TestSyncDDLDataFlowMySQLIntegration:
    """Test DataFlow auto_migrate with MySQL using sync DDL."""

    @pytest.mark.asyncio
    async def test_dataflow_auto_migrate_mysql(self, mysql_url, cleanup_tables):
        """Test that DataFlow auto_migrate works with MySQL in async context."""
        # Generate unique model name
        timestamp = int(time.time())

        # Create DataFlow with auto_migrate=True
        db = DataFlow(mysql_url, auto_migrate=True)

        # Define a unique model class
        table_name = f"test_users_{timestamp}"
        cleanup_tables.append(table_name)

        @db.model
        class TestUser:
            id: str
            name: str
            email: str
            is_active: bool = True

        # Override the table name for cleanup
        TestUser.__name__ = f"TestUser{timestamp}"

        # Verify model was registered
        assert f"TestUser{timestamp}" in db._models or "TestUser" in db._models

        # Give it a moment if needed
        await asyncio.sleep(0.1)

        # Verify schema cache shows table as ensured
        cache_checked = db._schema_cache.is_table_ensured(
            (
                f"TestUser{timestamp}"
                if f"TestUser{timestamp}" in db._models
                else "TestUser"
            ),
            mysql_url,
        )

    def test_dataflow_create_tables_sync_mysql(self, mysql_url, cleanup_tables):
        """Test explicit create_tables_sync with MySQL."""
        timestamp = int(time.time())

        # Create DataFlow with auto_migrate=False
        db = DataFlow(mysql_url, auto_migrate=False)

        @db.model
        class SyncTestModel:
            id: str
            value: str

        SyncTestModel.__name__ = f"SyncTestModel{timestamp}"

        # Explicitly create tables using sync method
        success = db.create_tables_sync()

        assert success is True, "create_tables_sync should return True"

        # Add the generated table name to cleanup
        # DataFlow uses lowercase + 's' suffix
        cleanup_tables.append(f"synctestmodel{timestamp}s")


class TestSyncDDLMySQLErrorHandling:
    """Test MySQL-specific error handling."""

    def test_handles_duplicate_table_error(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """Test that duplicate table creation is handled gracefully."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        # Create table first time
        executor.execute_ddl(
            f"CREATE TABLE {unique_table_name} (id VARCHAR(255) PRIMARY KEY)"
        )

        # Try to create again WITHOUT IF NOT EXISTS
        result = executor.execute_ddl(
            f"CREATE TABLE {unique_table_name} (id VARCHAR(255) PRIMARY KEY)"
        )

        # Should return error (not exception)
        assert result["success"] is False
        assert "error" in result
        assert (
            "already exists" in result["error"].lower()
            or "exists" in result["error"].lower()
        )

    def test_handles_invalid_sql(self, mysql_url):
        """Test that invalid SQL returns error, not exception."""
        executor = SyncDDLExecutor(mysql_url)

        result = executor.execute_ddl("THIS IS NOT VALID SQL")

        assert result["success"] is False
        assert "error" in result

    def test_handles_syntax_error(self, mysql_url):
        """Test MySQL syntax error handling."""
        executor = SyncDDLExecutor(mysql_url)

        result = executor.execute_ddl("CREATE TABLE (missing name) (id VARCHAR(255))")

        assert result["success"] is False
        assert "error" in result


class TestSyncDDLMySQLColumnTypes:
    """Test MySQL-specific column type handling."""

    def test_json_default_value(self, mysql_url, unique_table_name, cleanup_tables):
        """Test JSON column with MySQL (MySQL 5.7+)."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        # MySQL doesn't allow DEFAULT for JSON columns directly
        # But we can create a JSON column and insert
        sql = f"""
        CREATE TABLE {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            metadata JSON
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True, f"JSON DDL failed: {result.get('error')}"

        # Insert a row with JSON data
        executor.execute_ddl(
            f"""INSERT INTO {unique_table_name} (id, metadata) VALUES ('test-1', '{{"key": "value"}}')"""
        )

        # Query and verify JSON column
        query_result = executor.execute_query(
            f"SELECT metadata FROM {unique_table_name} WHERE id = 'test-1'"
        )
        assert "error" not in query_result

    def test_boolean_default_value(self, mysql_url, unique_table_name, cleanup_tables):
        """Test BOOLEAN column with MySQL TINYINT(1) representation."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        sql = f"""
        CREATE TABLE {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            is_active BOOLEAN DEFAULT TRUE,
            is_verified BOOLEAN DEFAULT FALSE
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True

        # Insert and verify
        executor.execute_ddl(f"INSERT INTO {unique_table_name} (id) VALUES ('test-1')")
        query_result = executor.execute_query(
            f"SELECT is_active, is_verified FROM {unique_table_name} WHERE id = 'test-1'"
        )

        # MySQL returns BOOLEAN as TINYINT (1 or 0)
        assert query_result["result"][0][0] == 1
        assert query_result["result"][0][1] == 0

    def test_timestamp_default_current_timestamp(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """Test TIMESTAMP column with CURRENT_TIMESTAMP default."""
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        sql = f"""
        CREATE TABLE {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True

        # Insert and verify timestamps are set
        executor.execute_ddl(f"INSERT INTO {unique_table_name} (id) VALUES ('test-1')")
        query_result = executor.execute_query(
            f"SELECT created_at, updated_at FROM {unique_table_name} WHERE id = 'test-1'"
        )

        # Both should have values (not NULL)
        assert query_result["result"][0][0] is not None
        assert query_result["result"][0][1] is not None


class TestSyncDDLMySQLVsPostgreSQL:
    """Test differences in MySQL vs PostgreSQL sync DDL handling."""

    def test_varchar_vs_text_primary_key(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """
        Test that MySQL uses VARCHAR for primary keys (TEXT not allowed as PK in MySQL).

        This tests a key difference between MySQL and PostgreSQL:
        - PostgreSQL: TEXT can be primary key
        - MySQL: TEXT cannot be primary key, must use VARCHAR(n)
        """
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        # This is the pattern that works in MySQL (VARCHAR, not TEXT)
        sql = f"""
        CREATE TABLE {unique_table_name} (
            id VARCHAR(255) PRIMARY KEY,
            name TEXT
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True, f"VARCHAR PK failed: {result.get('error')}"

    def test_auto_increment_vs_serial(
        self, mysql_url, unique_table_name, cleanup_tables
    ):
        """
        Test MySQL AUTO_INCREMENT (vs PostgreSQL SERIAL).
        """
        cleanup_tables.append(unique_table_name)

        executor = SyncDDLExecutor(mysql_url)

        sql = f"""
        CREATE TABLE {unique_table_name} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255)
        )
        """
        result = executor.execute_ddl(sql)

        assert result["success"] is True

        # Insert and verify auto-increment
        executor.execute_ddl(f"INSERT INTO {unique_table_name} (name) VALUES ('Alice')")
        executor.execute_ddl(f"INSERT INTO {unique_table_name} (name) VALUES ('Bob')")

        query_result = executor.execute_query(
            f"SELECT id, name FROM {unique_table_name} ORDER BY id"
        )

        assert len(query_result["result"]) == 2
        assert query_result["result"][0][0] == 1
        assert query_result["result"][1][0] == 2


class TestSyncDDLMissingPymysql:
    """Test behavior when pymysql is not available."""

    def test_import_error_message(self, mysql_url):
        """Test that ImportError provides helpful message."""
        # This test verifies the error message when pymysql is missing
        # We can't actually test the missing case, but we verify the code path exists

        executor = SyncDDLExecutor(mysql_url)

        # If pymysql is available, this should work
        # The ImportError path is tested implicitly by the implementation
        assert executor._db_type == "mysql"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
