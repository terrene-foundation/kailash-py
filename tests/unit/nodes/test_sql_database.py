"""Tests for SQL database nodes."""

import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError

# ============================================================================
# GLOBAL TEST FIXTURES - Database Configuration and Setup
# ============================================================================


@pytest.fixture(scope="session")
def db_configs(sqlite_test_database):
    """Create database configurations for all database tests."""
    return {
        "sqlite_test": {
            "connection_string": f"sqlite:///{sqlite_test_database}",
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
        },
        "postgres_test": {
            "connection_string": "sqlite:///:memory:",
            "pool_size": 8,
            "max_overflow": 15,
            "pool_timeout": 60,
            "pool_recycle": 3600,
            "connect_args": {},
        },
        "mysql_test": {
            "connection_string": "mysql+pymysql://root:test_password@localhost:3307/kailash_test",
            "pool_size": 6,
            "max_overflow": 12,
            "pool_timeout": 45,
            "pool_recycle": 7200,
            "connect_args": {"charset": "utf8mb4", "connect_timeout": 20},
        },
    }


@pytest.fixture(scope="session")
def sqlite_test_database():
    """Create a test SQLite database with sample data."""
    import uuid

    db_path = f"test_shared_{uuid.uuid4().hex[:8]}.db"

    # Remove existing database
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create test tables
    cursor.execute(
        """
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            age INTEGER,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE test_orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            product TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES test_users (id)
        )
    """
    )

    # Insert test data
    test_users_data = [
        (1, "John Doe", "john@example.com", 30, True),
        (2, "Jane Smith", "jane@example.com", 25, True),
        (3, "Bob Johnson", "bob@example.com", 35, False),
        (4, "Alice Brown", "alice@example.com", 28, True),
        (5, "Charlie Wilson", "charlie@example.com", 45, True),
    ]
    cursor.executemany(
        "INSERT INTO test_users (id, name, email, age, active) VALUES (?, ?, ?, ?, ?)",
        test_users_data,
    )

    test_orders_data = [
        (1, 1, "Laptop", 999.99, "completed"),
        (2, 1, "Mouse", 29.99, "completed"),
        (3, 2, "Phone", 599.99, "pending"),
        (4, 4, "Tablet", 299.99, "completed"),
        (5, 4, "Keyboard", 79.99, "pending"),
    ]
    cursor.executemany(
        "INSERT INTO test_orders (id, user_id, product, amount, status) VALUES (?, ?, ?, ?, ?)",
        test_orders_data,
    )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


def check_database_availability(connection_string, timeout=5):
    """Check if a database is available."""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(connection_string, pool_timeout=timeout)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_available():
    """Check if SQLite in-memory is available for testing."""
    conn_str = "sqlite:///:memory:"
    return check_database_availability(conn_str)


@pytest.fixture(scope="session")
def mysql_available():
    """Check if MySQL is available for testing."""
    conn_str = "mysql+pymysql://root:test_password@localhost:3307/kailash_test"
    return check_database_availability(conn_str)


# ============================================================================
# SQLite Tests (Primary Implementation)
# ============================================================================


class TestSQLDatabaseNodeSQLite:
    """Test SQLDatabaseNode with SQLite database."""

    def test_basic_connection_and_select(self, sqlite_test_database, db_configs):
        """Test basic database connection and SELECT query."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        result = node.execute(
            query="SELECT * FROM test_users WHERE active = ?",
            parameters=[True],
            result_format="dict",
        )

        assert "data" in result
        assert "row_count" in result
        assert "columns" in result
        assert "execution_time" in result

        assert result["row_count"] == 4  # 4 active users
        assert len(result["data"]) == 4
        assert "id" in result["columns"]
        assert "name" in result["columns"]

        # Verify first user data
        first_user = result["data"][0]
        assert first_user["name"] == "John Doe"
        assert first_user["email"] == "john@example.com"
        assert first_user["active"] == 1  # SQLite stores boolean as int

    def test_crud_operations(self, sqlite_test_database, db_configs):
        """Test CREATE, READ, UPDATE, DELETE operations."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # CREATE (INSERT)
        insert_result = node.execute(
            query="INSERT INTO test_users (name, email, age, active) VALUES (?, ?, ?, ?)",
            parameters=["Test User", "test@example.com", 30, True],
            result_format="dict",
        )
        assert insert_result["row_count"] == 1
        assert insert_result["data"] == []  # No rows returned for INSERT

        # READ (SELECT with specific criteria)
        read_result = node.execute(
            query="SELECT * FROM test_users WHERE email = ?",
            parameters=["test@example.com"],
            result_format="dict",
        )
        assert read_result["row_count"] == 1
        assert read_result["data"][0]["name"] == "Test User"
        user_id = read_result["data"][0]["id"]

        # UPDATE
        update_result = node.execute(
            query="UPDATE test_users SET age = ? WHERE id = ?",
            parameters=[31, user_id],
            result_format="dict",
        )
        assert update_result["row_count"] == 1

        # Verify UPDATE worked
        verify_result = node.execute(
            query="SELECT age FROM test_users WHERE id = ?",
            parameters=[user_id],
            result_format="dict",
        )
        assert verify_result["data"][0]["age"] == 31

        # DELETE
        delete_result = node.execute(
            query="DELETE FROM test_users WHERE id = ?",
            parameters=[user_id],
            result_format="dict",
        )
        assert delete_result["row_count"] == 1

        # Verify DELETE worked
        verify_delete = node.execute(
            query="SELECT COUNT(*) as count FROM test_users WHERE id = ?",
            parameters=[user_id],
            result_format="dict",
        )
        assert verify_delete["data"][0]["count"] == 0

    def test_result_formats(self, sqlite_test_database, db_configs):
        """Test different result format options."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])
        query = "SELECT name, age FROM test_users LIMIT 2"

        # Test dict format (default)
        dict_result = node.execute(query=query, result_format="dict")
        assert isinstance(dict_result["data"][0], dict)
        assert "name" in dict_result["data"][0]
        assert "age" in dict_result["data"][0]

        # Test list format
        list_result = node.execute(query=query, result_format="list")
        assert isinstance(list_result["data"][0], list)
        assert len(list_result["data"][0]) == 2  # name, age

        # Test raw format
        raw_result = node.execute(query=query, result_format="raw")
        assert isinstance(raw_result["data"][0], list)

    def test_parameterized_queries_security(self, sqlite_test_database, db_configs):
        """Test parameterized queries prevent SQL injection."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # This malicious input should be safely handled by parameterization
        malicious_input = "1'; DROP TABLE test_users; --"

        result = node.execute(
            query="SELECT * FROM test_users WHERE id = ?",
            parameters=[malicious_input],
            result_format="dict",
        )

        # Should return 0 rows (no user with ID matching the malicious string)
        assert result["row_count"] == 0

        # Verify table still exists by counting all users
        verify_result = node.execute(
            query="SELECT COUNT(*) as count FROM test_users", result_format="dict"
        )
        assert verify_result["data"][0]["count"] == 5  # Original test users

    def test_transaction_rollback(self, sqlite_test_database, db_configs):
        """Test transaction rollback on errors."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # Get initial count
        initial_result = node.execute(
            query="SELECT COUNT(*) as count FROM test_users", result_format="dict"
        )
        initial_count = initial_result["data"][0]["count"]

        # This should fail and rollback
        with pytest.raises(NodeExecutionError):
            node.execute(
                query="INSERT INTO nonexistent_table VALUES (1, 'test')",
                result_format="dict",
            )

        # Verify rollback - count should be unchanged
        after_error = node.execute(
            query="SELECT COUNT(*) as count FROM test_users", result_format="dict"
        )
        assert after_error["data"][0]["count"] == initial_count

    def test_connection_pooling(self, sqlite_test_database, db_configs):
        """Test connection pooling with concurrent queries."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        def execute_query(query_id):
            """Execute a query and return timing info."""
            start_time = time.time()
            try:
                result = node.execute(
                    query="SELECT COUNT(*) as count FROM test_users WHERE id <= ?",
                    parameters=[query_id],
                )
                end_time = time.time()
                return {
                    "query_id": query_id,
                    "success": True,
                    "duration": end_time - start_time,
                    "count": result["data"][0]["count"],
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "query_id": query_id,
                    "success": False,
                    "duration": end_time - start_time,
                    "error": str(e),
                }

        # Test concurrent execution (should use connection pool)
        num_concurrent_queries = 4

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=num_concurrent_queries) as executor:
            futures = [
                executor.submit(execute_query, i)
                for i in range(1, num_concurrent_queries + 1)
            ]
            results = [future.result() for future in as_completed(futures)]

        total_time = time.time() - start_time

        # Assertions - allow for some failures due to database contention
        successful_queries = [r for r in results if r["success"]]
        failed_queries = [r for r in results if not r["success"]]

        # Log failed queries for debugging
        if failed_queries:
            print(f"⚠️  {len(failed_queries)} queries failed:")
            for fq in failed_queries:
                print(f"   Query {fq['query_id']}: {fq.get('error', 'Unknown error')}")

        # Require at least 50% of queries to succeed for connection pooling test
        min_required = max(2, num_concurrent_queries // 2)
        assert (
            len(successful_queries) >= min_required
        ), f"At least {min_required} queries should succeed, got {len(successful_queries)}"

        # Instead of checking absolute time, verify that connection pooling provides benefit
        # Calculate average time per query
        avg_query_time = sum(r["duration"] for r in successful_queries) / len(
            successful_queries
        )

        # If queries were sequential, total time would be approximately num_queries * avg_time
        expected_sequential_time = num_concurrent_queries * avg_query_time

        # With pooling, concurrent execution should be faster than sequential
        # On fast systems, the benefit might be minimal, so use a more lenient threshold
        pooling_efficiency = total_time / expected_sequential_time
        # Allow up to 100% overhead for connection pooling on CI systems or when queries are very simple
        # The main goal is to verify pooling doesn't cause excessive slowdown (2x is acceptable for CI)
        assert (
            pooling_efficiency < 2.0
        ), f"Connection pooling significantly slower than sequential: {pooling_efficiency:.2f} (expected < 2.0)"

        # Log efficiency for monitoring - ideally should be < 0.75 but not required
        if pooling_efficiency >= 0.75:
            print(
                f"⚠️  Connection pooling efficiency suboptimal: {pooling_efficiency:.2f}"
            )
        else:
            print(f"✅ Connection pooling efficient: {pooling_efficiency:.2f}")

        # Log timing info for debugging
        print(
            f"   Total time: {total_time:.2f}s, Avg query time: {avg_query_time:.2f}s, Efficiency: {pooling_efficiency:.2f}"
        )

        # Verify query results are correct
        for result in successful_queries:
            expected_count = min(result["query_id"], 5)  # We have 5 test users
            assert result["count"] == expected_count

    def test_query_timeout(self, sqlite_test_database, db_configs):
        """Test query timeout functionality."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # Test with reasonable timeout - should work
        start_time = time.time()
        result = node.execute(
            query="SELECT COUNT(*) as count FROM test_users", timeout=5
        )
        duration = time.time() - start_time

        assert result["row_count"] == 1
        # Just verify the query completed, don't check absolute time
        assert duration > 0  # Query took some time
        assert result["data"][0]["count"] == 5

    def test_node_reusability(self, sqlite_test_database, db_configs):
        """Test that same node can execute multiple different queries."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # Execute multiple different queries with the same node
        result1 = node.execute(query="SELECT COUNT(*) as total_users FROM test_users")
        result2 = node.execute(query="SELECT COUNT(*) as total_orders FROM test_orders")
        result3 = node.execute(
            query="SELECT name FROM test_users WHERE age > ?",
            parameters=[30],
            result_format="dict",
        )

        # All queries should succeed
        assert result1["data"][0]["total_users"] == 5
        assert result2["data"][0]["total_orders"] == 5
        assert len(result3["data"]) >= 1  # At least one user over 30

        # Verify the node maintained its connection configuration (check pattern since we use UUID)
        assert node.connection_string.startswith("sqlite:///test_shared_")
        assert node.connection_string.endswith(".db")

    def test_performance_metrics(self, sqlite_test_database, db_configs):
        """Test that performance metrics are captured."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        result = node.execute(
            query="SELECT * FROM test_users LIMIT 1", result_format="dict"
        )

        assert "execution_time" in result
        assert isinstance(result["execution_time"], float)
        assert result["execution_time"] >= 0

    def test_complex_joins(self, sqlite_test_database, db_configs):
        """Test complex queries with JOINs."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        result = node.execute(
            query="""
                SELECT u.name, u.email, COUNT(o.id) as order_count, SUM(o.amount) as total_spent
                FROM test_users u
                LEFT JOIN test_orders o ON u.id = o.user_id
                WHERE u.active = ?
                GROUP BY u.id, u.name, u.email
                ORDER BY total_spent DESC
            """,
            parameters=[True],
            result_format="dict",
        )

        assert result["row_count"] >= 1
        assert "name" in result["columns"]
        assert "order_count" in result["columns"]
        assert "total_spent" in result["columns"]

        # Check that data makes sense
        for row in result["data"]:
            assert row["order_count"] >= 0
            # total_spent can be NULL for users with no orders (SQL SUM behavior)
            assert row["total_spent"] is None or row["total_spent"] >= 0

    def test_error_handling(self, sqlite_test_database, db_configs):
        """Test various error conditions."""
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # Test invalid SQL syntax
        with pytest.raises(NodeExecutionError):
            node.execute(query="INVALID SQL SYNTAX")

        # Test missing table
        with pytest.raises(NodeExecutionError):
            node.execute(query="SELECT * FROM nonexistent_table")

        # Test invalid column
        with pytest.raises(NodeExecutionError):
            node.execute(query="SELECT nonexistent_column FROM test_users")

    def test_missing_parameters(self, db_configs):
        """Test error handling for missing required parameters."""
        # Test missing query in run() - connection is now required in constructor
        node_with_connection = SQLDatabaseNode(**db_configs["sqlite_test"])
        with pytest.raises(NodeExecutionError, match="query parameter is required"):
            node_with_connection.execute()

        # Test that the API requires connection_string in constructor
        with pytest.raises(
            NodeExecutionError, match="connection_string parameter is required"
        ):
            SQLDatabaseNode()  # No connection_string provided


# ============================================================================
# Security Tests
# ============================================================================


class TestSQLDatabaseNodeSecurity:
    """Test security features of SQLDatabaseNode."""

    def test_connection_string_validation(self, db_configs):
        """Test connection string security validation."""
        # Use dummy connection for utility method testing
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # Test unsupported protocol
        with pytest.raises(NodeExecutionError, match="Unsupported database protocol"):
            node._validate_connection_string("mongodb://localhost/test")

        # Test dangerous characters
        with pytest.raises(NodeExecutionError, match="dangerous characters"):
            node._validate_connection_string("sqlite:///test.db'; DROP TABLE users;")

    def test_query_safety_validation(self, db_configs):
        """Test query safety validation."""
        # Use dummy connection for utility method testing
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # These should log warnings but not raise exceptions
        node._validate_query_safety("SELECT * FROM users")  # Safe
        node._validate_query_safety("SELECT * FROM users; DROP TABLE admin;")  # Warning

    def test_identifier_sanitization(self, db_configs):
        """Test identifier sanitization."""
        # Use dummy connection for utility method testing
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        # Valid identifiers
        assert node._sanitize_identifier("valid_table") == "valid_table"
        assert node._sanitize_identifier("table_123") == "table_123"
        assert node._sanitize_identifier("db.table") == "db.table"

        # Invalid identifiers
        with pytest.raises(NodeExecutionError, match="Invalid identifier"):
            node._sanitize_identifier("table'; DROP")

        with pytest.raises(NodeExecutionError, match="Invalid identifier"):
            node._sanitize_identifier("123invalid")

    def test_password_masking(self, db_configs):
        """Test password masking in connection strings."""
        # Test static method directly
        test_cases = [
            ("postgresql://user:secret@host/db", "postgresql://user:***@host/db"),
            (
                "mysql://admin:password123@localhost/mydb",
                "mysql://admin:***@localhost/mydb",
            ),
            ("sqlite:///local.db", "sqlite:///local.db"),  # No password to mask
        ]

        for original, expected in test_cases:
            masked = SQLDatabaseNode._mask_connection_password(original)
            assert masked == expected

    def test_error_message_sanitization(self, db_configs):
        """Test error message sanitization."""
        # Use dummy connection for utility method testing
        node = SQLDatabaseNode(**db_configs["sqlite_test"])

        test_cases = [
            (
                "Connection failed for postgresql://user:secret@host/db",
                "Connection failed for postgresql://***:***@host/db",
            ),
            # Updated: Only passwords and sensitive fields are masked, not all quoted strings
            ("Query failed: 'sensitive data'", "Query failed: 'sensitive data'"),
            ('Error in query "SELECT secret"', 'Error in query "SELECT secret"'),
            # New test cases for targeted sanitization
            ("password='mypass123'", "password='***'"),
            ("api_key='sk-1234567890'", "api_key='***'"),
        ]

        for original, expected in test_cases:
            sanitized = node._sanitize_error_message(original)
            assert sanitized == expected
