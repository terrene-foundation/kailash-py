"""Integration tests for SQLDatabaseNode with MySQL.

These tests require a real MySQL database connection via Docker.
"""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError


@pytest.mark.integration
@pytest.mark.requires_mysql
class TestSQLDatabaseNodeMySQL:
    """Test SQLDatabaseNode with real MySQL database."""

    @pytest.fixture(scope="class")
    def mysql_config(self):
        """MySQL configuration for tests."""
        return {
            "connection_string": "mysql+pymysql://kailash_test:test_password@localhost:3307/kailash_test",
            "pool_size": 5,
            "max_overflow": 10,
        }

    @pytest.fixture(scope="class", autouse=True)
    def mysql_setup(self, mysql_config):
        """Setup MySQL test database."""
        # Setup test data
        from sqlalchemy import create_engine, text

        engine = create_engine(mysql_config["connection_string"])

        with engine.connect() as conn:
            # Drop and create tables
            conn.execute(text("DROP TABLE IF EXISTS test_orders"))
            conn.execute(text("DROP TABLE IF EXISTS test_users"))

            # Create test tables
            conn.execute(
                text(
                    """
                CREATE TABLE test_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE,
                    age INT,
                    active BOOLEAN DEFAULT TRUE,
                    balance DECIMAL(10, 2),
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
                )
            )

            conn.execute(
                text(
                    """
                CREATE TABLE test_orders (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    product VARCHAR(200),
                    quantity INT,
                    price DECIMAL(10, 2),
                    order_date DATE,
                    FOREIGN KEY (user_id) REFERENCES test_users(id)
                )
            """
                )
            )

            # Insert test data
            conn.execute(
                text(
                    """
                INSERT INTO test_users (name, email, age, balance, metadata) VALUES
                ('Alice', 'alice@example.com', 30, 1000.50, '{"vip": true}'),
                ('Bob', 'bob@example.com', 25, 500.00, '{"vip": false}'),
                ('Charlie', 'charlie@example.com', 35, 1500.75, '{"vip": true}')
            """
                )
            )

            conn.execute(
                text(
                    """
                INSERT INTO test_orders (user_id, product, quantity, price, order_date) VALUES
                (1, 'Laptop', 1, 999.99, '2024-01-15'),
                (1, 'Mouse', 2, 29.99, '2024-01-16'),
                (2, 'Keyboard', 1, 79.99, '2024-01-17')
            """
                )
            )

            conn.commit()

        yield

        # Cleanup
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_orders"))
            conn.execute(text("DROP TABLE IF EXISTS test_users"))
            conn.commit()

    def test_basic_connection_and_select(self, mysql_config):
        """Test basic MySQL connection and SELECT query."""
        node = SQLDatabaseNode(**mysql_config)

        # Simple SELECT
        result = node.execute(
            query="SELECT * FROM test_users WHERE active = TRUE ORDER BY id"
        )

        assert "data" in result
        assert len(result["data"]) == 3
        assert result["data"][0]["name"] == "Alice"
        assert result["data"][0]["active"] == 1  # MySQL stores boolean as tinyint

    def test_crud_operations(self, mysql_config):
        """Test CREATE, READ, UPDATE, DELETE operations."""
        node = SQLDatabaseNode(**mysql_config)

        # INSERT
        insert_result = node.execute(
            query="""
            INSERT INTO test_users (name, email, age, balance)
            VALUES (:name, :email, :age, :balance)
        """,
            parameters={
                "name": "David",
                "email": "david@example.com",
                "age": 28,
                "balance": 750.25,
            },
        )
        assert insert_result["row_count"] == 1

        # SELECT to verify
        select_result = node.execute(
            query="SELECT * FROM test_users WHERE email = :email",
            parameters={"email": "david@example.com"},
        )
        assert len(select_result["data"]) == 1
        assert select_result["data"][0]["name"] == "David"

        # UPDATE
        update_result = node.execute(
            query="UPDATE test_users SET age = :age WHERE email = :email",
            parameters={"age": 29, "email": "david@example.com"},
        )
        assert update_result["row_count"] == 1

        # DELETE
        delete_result = node.execute(
            query="DELETE FROM test_users WHERE email = :email",
            parameters={"email": "david@example.com"},
        )
        assert delete_result["row_count"] == 1

    def test_result_formats(self, mysql_config):
        """Test result format (currently only dict format is supported)."""
        node = SQLDatabaseNode(**mysql_config)

        # Default dict format
        dict_result = node.execute(
            query="SELECT name, age FROM test_users ORDER BY id LIMIT 2"
        )
        assert isinstance(dict_result["data"], list)
        assert isinstance(dict_result["data"][0], dict)
        assert dict_result["data"][0]["name"] == "Alice"
        assert dict_result["data"][0]["age"] == 30
        assert dict_result["data"][1]["name"] == "Bob"
        assert dict_result["data"][1]["age"] == 25

        # Verify columns are included
        assert "columns" in dict_result
        assert "name" in dict_result["columns"]
        assert "age" in dict_result["columns"]

        # Verify row count
        assert dict_result["row_count"] == 2

    def test_parameterized_queries_security(self, mysql_config):
        """Test parameterized queries for SQL injection prevention."""
        node = SQLDatabaseNode(**mysql_config)

        # Test with potentially malicious input
        malicious_input = "'; DROP TABLE test_users; --"

        # This should be safe due to parameterization
        result = node.execute(
            query="SELECT * FROM test_users WHERE name = :name",
            parameters={"name": malicious_input},
        )

        assert "data" in result
        assert len(result["data"]) == 0  # No matching user

        # Verify table still exists
        table_check = node.execute(query="SELECT COUNT(*) as count FROM test_users")
        assert table_check["data"][0]["count"] > 0

    def test_transaction_rollback(self, mysql_config):
        """Test transaction rollback on error."""
        node = SQLDatabaseNode(**mysql_config)

        initial_count = node.execute(query="SELECT COUNT(*) as count FROM test_users")[
            "data"
        ][0]["count"]

        # Try to insert with duplicate email (should fail)
        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(
                query="""
                INSERT INTO test_users (name, email, age, balance)
                VALUES (:name, :email, :age, :balance)
            """,
                parameters={
                    "name": "Alice Duplicate",
                    "email": "alice@example.com",  # Duplicate email
                    "age": 31,
                    "balance": 2000.00,
                },
            )

        # Verify count unchanged
        final_count = node.execute(query="SELECT COUNT(*) as count FROM test_users")[
            "data"
        ][0]["count"]
        assert final_count == initial_count

    def test_connection_pooling(self, mysql_config):
        """Test connection pooling behavior."""
        # Create multiple nodes with same config
        nodes = [SQLDatabaseNode(**mysql_config) for _ in range(3)]

        # Execute queries on all nodes
        results = []
        for i, node in enumerate(nodes):
            result = node.execute(
                query="SELECT :node_id as node_id, COUNT(*) as count FROM test_users",
                parameters={"node_id": i},
            )
            results.append(result["data"][0])

        # All should succeed
        assert all(r["count"] > 0 for r in results)

    def test_complex_joins(self, mysql_config):
        """Test complex JOIN queries."""
        node = SQLDatabaseNode(**mysql_config)

        result = node.execute(
            query="""
            SELECT
                u.name,
                u.email,
                COUNT(o.id) as order_count,
                SUM(o.quantity * o.price) as total_spent
            FROM test_users u
            LEFT JOIN test_orders o ON u.id = o.user_id
            GROUP BY u.id, u.name, u.email
            HAVING COUNT(o.id) > 0
            ORDER BY total_spent DESC
        """
        )

        assert "data" in result
        assert len(result["data"]) == 2  # Only users with orders

    def test_mysql_specific_features(self, mysql_config):
        """Test MySQL-specific features."""
        node = SQLDatabaseNode(**mysql_config)

        # Test JSON functions (MySQL 5.7+)
        result = node.execute(
            query="""
            SELECT name, JSON_EXTRACT(metadata, '$.vip') as is_vip
            FROM test_users
            WHERE JSON_EXTRACT(metadata, '$.vip') = true
            ORDER BY name
        """
        )
        assert len(result["data"]) == 2  # Alice and Charlie are VIP

        # Test DATE functions
        date_result = node.execute(
            query="""
            SELECT
                YEAR(order_date) as year,
                MONTH(order_date) as month,
                COUNT(*) as order_count
            FROM test_orders
            GROUP BY YEAR(order_date), MONTH(order_date)
        """
        )
        assert date_result["data"][0]["year"] == 2024
        assert date_result["data"][0]["month"] == 1

    def test_mysql_charset_unicode(self, mysql_config):
        """Test MySQL Unicode handling."""
        node = SQLDatabaseNode(**mysql_config)

        # Insert Unicode data
        unicode_data = {
            "name": "José García 🚀",
            "email": "jose@example.com",
            "age": 30,
            "balance": 1000.00,
        }

        insert_result = node.execute(
            query="""
            INSERT INTO test_users (name, email, age, balance)
            VALUES (:name, :email, :age, :balance)
        """,
            parameters=unicode_data,
        )
        assert insert_result["row_count"] == 1

        # Retrieve and verify
        select_result = node.execute(
            query="SELECT name FROM test_users WHERE email = :email",
            parameters={"email": "jose@example.com"},
        )
        assert select_result["data"][0]["name"] == "José García 🚀"
