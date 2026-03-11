"""
Integration tests for SQL injection prevention with real database connections.

Tests SQL injection prevention with actual database operations using Docker services.
NO MOCKING - uses real PostgreSQL, MySQL, and SQLite databases.
"""

import asyncio
import os
import sqlite3
from typing import Any, Dict, List

import mysql.connector
import pytest
from dataflow import DataFlow
from dataflow.nodes.bulk_create import BulkCreateNode
from dataflow.nodes.bulk_delete import BulkDeleteNode
from dataflow.nodes.bulk_update import BulkUpdateNode

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def test_databases(test_suite):
    """Get test database configurations using IntegrationTestSuite."""
    return {
        "postgresql": {
            "url": test_suite.config.url,
            "driver": "asyncpg",
        },
        "sqlite": {"url": "sqlite:///test_dataflow.db", "driver": "sqlite3"},
    }


def get_test_databases(test_suite):
    """Get test database configurations using IntegrationTestSuite."""
    return {
        "postgresql": {
            "url": test_suite.config.url,
            "driver": "asyncpg",
        },
        "sqlite": {"url": "sqlite:///test_dataflow.db", "driver": "sqlite3"},
    }


class TestSQLInjectionWithRealDatabases:
    """Test SQL injection prevention with real database connections."""

    @pytest.fixture(autouse=True)
    async def setup_databases(self, test_suite):
        """Create test tables in all databases using async DataFlow API."""
        # Get test database configurations
        test_databases = get_test_databases(test_suite)

        # PostgreSQL
        if "postgresql" in test_databases:
            try:
                db = DataFlow(
                    test_databases["postgresql"]["url"],
                    auto_migrate=False,
                    existing_schema_mode=True,
                )
                conn = await db._get_async_database_connection()
                try:
                    await conn.execute("DROP TABLE IF EXISTS test_users CASCADE")
                    await conn.execute(
                        """
                        CREATE TABLE test_users (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(100),
                            email VARCHAR(100) UNIQUE,
                            active BOOLEAN DEFAULT true,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """
                    )
                finally:
                    await conn.close()
            except Exception as e:
                pytest.skip(f"PostgreSQL not available: {e}")

        # MySQL (not included in IntegrationTestSuite, skip)
        if "mysql" in test_databases:
            try:
                # Parse MySQL URL
                url = test_databases["mysql"]["url"]
                # mysql://user:pass@host:port/database
                parts = url.replace("mysql://", "").split("@")
                user_pass = parts[0].split(":")
                host_db = parts[1].split("/")
                host_port = host_db[0].split(":")

                conn = mysql.connector.connect(
                    host=host_port[0],
                    port=int(host_port[1]) if len(host_port) > 1 else 3306,
                    user=user_pass[0],
                    password=user_pass[1],
                    database=host_db[1],
                )
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS test_users")
                cursor.execute(
                    """
                    CREATE TABLE test_users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100),
                        email VARCHAR(100) UNIQUE,
                        active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """
                )
                conn.commit()
                conn.close()
            except Exception as e:
                pytest.skip(f"MySQL not available: {e}")

        # SQLite
        conn = sqlite3.connect("test_dataflow.db")
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute(
            """
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.commit()
        conn.close()

        yield

        # Cleanup
        if os.path.exists("test_dataflow.db"):
            os.remove("test_dataflow.db")

    @pytest.mark.parametrize(
        "database_type,database_url",
        [
            ("postgresql", "from_test_suite"),
            ("sqlite", "sqlite:///test_dataflow.db"),
        ],
    )
    def test_table_injection_attempts_blocked(
        self, test_suite, database_type, database_url
    ):
        """Test that table name injection attempts are blocked."""
        # Get actual URL from test suite if needed
        if database_url == "from_test_suite":
            database_url = test_suite.config.url

        injection_attempts = [
            "test_users; DROP TABLE test_users;",
            "test_users'; DELETE FROM test_users;--",
            "test_users UNION SELECT * FROM test_users",
            "test_users/**/WHERE/**/1=1",
            "test_users-- DROP TABLE test_users",
        ]

        for malicious_table in injection_attempts:
            with pytest.raises(ValueError) as exc_info:
                BulkCreateNode(
                    table_name=malicious_table,
                    database_type=database_type,
                    connection_string=database_url,
                )
            assert "Invalid table name" in str(exc_info.value)

    @pytest.mark.parametrize(
        "database_type,database_url",
        [
            ("postgresql", "from_test_suite"),
            ("sqlite", "sqlite:///test_dataflow.db"),
        ],
    )
    def test_column_injection_blocked_during_insert(
        self, test_suite, database_type, database_url
    ):
        """Test that column name injection is blocked during insert operations."""
        # Get actual URL from test suite if needed
        if database_url == "from_test_suite":
            database_url = test_suite.config.url

        node = BulkCreateNode(
            table_name="test_users",
            database_type=database_type,
            connection_string=database_url,
        )

        # Malicious column names should be rejected
        malicious_data = [
            {"name'; DROP TABLE test_users;--": "test"},
            {"name) VALUES ('test'); DROP TABLE test_users;--": "value"},
            {"email/**/WHERE/**/1=1": "test@test.com"},
        ]

        for data in malicious_data:
            with pytest.raises(ValueError) as exc_info:
                asyncio.run(node.async_run(data=[data]))
            assert "Invalid column name" in str(exc_info.value)

    @pytest.mark.parametrize(
        "database_type,database_url",
        [
            ("postgresql", "from_test_suite"),
            ("sqlite", "sqlite:///test_dataflow.db"),
        ],
    )
    def test_parameterized_queries_prevent_value_injection(
        self, test_suite, database_type, database_url
    ):
        """Test that parameterized queries prevent SQL injection in values."""
        # Get actual URL from test suite if needed
        if database_url == "from_test_suite":
            database_url = test_suite.config.url

        node = BulkCreateNode(
            table_name="test_users",
            database_type=database_type,
            connection_string=database_url,
        )

        # These values contain SQL injection attempts but should be safely inserted
        malicious_values = [
            {"name": "admin'; DROP TABLE test_users;--", "email": "admin@test.com"},
            {"name": "test' OR '1'='1", "email": "test@test.com"},
            {"name": "user'); DELETE FROM test_users;--", "email": "user@test.com"},
        ]

        # Insert should succeed - values are parameterized
        result = asyncio.run(node.async_run(data=malicious_values))
        assert result["success"] is True
        assert result["inserted"] == len(malicious_values)

        # Verify table still exists and has the data
        if database_type == "postgresql":
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test_users")
            count = cursor.fetchone()[0]
            assert count == len(malicious_values)

            # Verify the malicious strings were stored as data, not executed
            cursor.execute(
                "SELECT name FROM test_users WHERE email = %s", ("admin@test.com",)
            )
            name = cursor.fetchone()[0]
            assert name == "admin'; DROP TABLE test_users;--"
            conn.close()

    @pytest.mark.parametrize(
        "database_type,database_url",
        [
            ("postgresql", "from_test_suite"),
            ("sqlite", "sqlite:///test_dataflow.db"),
        ],
    )
    def test_bulk_operations_with_injection_attempts(
        self, test_suite, database_type, database_url
    ):
        """Test bulk operations handle injection attempts correctly."""
        # Get actual URL from test suite if needed
        if database_url == "from_test_suite":
            database_url = test_suite.config.url

        # First insert some test data
        create_node = BulkCreateNode(
            table_name="test_users",
            database_type=database_type,
            connection_string=database_url,
        )

        test_data = [
            {"name": "user1", "email": "user1@test.com"},
            {"name": "user2", "email": "user2@test.com"},
            {"name": "user3", "email": "user3@test.com"},
        ]

        result = asyncio.run(create_node.async_run(data=test_data))
        assert result["success"] is True

        # Now try bulk update with injection
        update_node = BulkUpdateNode(
            table_name="test_users",
            database_type=database_type,
            connection_string=database_url,
        )

        # This should fail due to invalid column name
        with pytest.raises(ValueError) as exc_info:
            asyncio.run(
                update_node.async_run(
                    filter={"active": True},
                    update={"name'; DROP TABLE test_users;--": "hacked"},
                )
            )
        assert "Invalid column name" in str(exc_info.value)

        # But this should work - parameterized value
        result = asyncio.run(
            update_node.async_run(
                filter={"active": True},
                update={"name": "updated'; DROP TABLE test_users;--"},
            )
        )
        assert result["success"] is True

    def test_workflow_integration_with_injection_prevention(self):
        """Test SQL injection prevention in workflow context."""
        db = DataFlow(database_url="sqlite:///test_workflow.db")

        @db.model
        class Product:
            name: str
            price: float
            category: str

        workflow = WorkflowBuilder()

        # This should fail - invalid table name in node creation
        with pytest.raises(ValueError) as exc_info:
            workflow.add_node(
                "BulkCreateNode",
                "create_products",
                {
                    "table_name": "products; DROP TABLE products;",
                    "database_type": "sqlite",
                    "connection_string": "sqlite:///test_workflow.db",
                },
            )

        # Create with valid table name
        workflow.add_node(
            "ProductBulkCreateNode",
            "create_products",
            {
                "data": [
                    {"name": "Laptop", "price": 999.99, "category": "Electronics"},
                    {
                        "name": "Mouse'; DROP TABLE products;--",
                        "price": 29.99,
                        "category": "Electronics",
                    },
                ]
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify products were created with malicious string as data
        conn = sqlite3.connect("test_workflow.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM product WHERE price = 29.99")
        name = cursor.fetchone()[0]
        assert name == "Mouse'; DROP TABLE products;--"
        conn.close()

        # Cleanup
        if os.path.exists("test_workflow.db"):
            os.remove("test_workflow.db")

    @pytest.mark.parametrize(
        "database_type,database_url",
        [
            ("postgresql", "from_test_suite"),
            ("sqlite", "sqlite:///test_dataflow.db"),
        ],
    )
    def test_concurrent_operations_with_injection_attempts(
        self, test_suite, database_type, database_url
    ):
        """Test concurrent operations don't bypass injection prevention."""
        # Get actual URL from test suite if needed
        if database_url == "from_test_suite":
            database_url = test_suite.config.url

        import concurrent.futures

        node = BulkCreateNode(
            table_name="test_users",
            database_type=database_type,
            connection_string=database_url,
        )

        def try_injection(injection_type):
            if injection_type == "table":
                # Should fail
                try:
                    bad_node = BulkCreateNode(
                        table_name="test_users; DROP TABLE test_users;",
                        database_type=database_type,
                        connection_string=database_url,
                    )
                    return "FAILED - Table injection not blocked"
                except ValueError:
                    return "PASSED - Table injection blocked"

            elif injection_type == "column":
                # Should fail
                try:
                    asyncio.run(
                        node.async_run(
                            data=[{"name'; DROP TABLE test_users;--": "test"}]
                        )
                    )
                    return "FAILED - Column injection not blocked"
                except ValueError:
                    return "PASSED - Column injection blocked"

            elif injection_type == "value":
                # Should succeed (parameterized)
                try:
                    result = asyncio.run(
                        node.async_run(
                            data=[
                                {
                                    "name": f"test{injection_type}'; DROP TABLE test_users;--",
                                    "email": f"{injection_type}@test.com",
                                }
                            ]
                        )
                    )
                    return "PASSED - Value injection safely parameterized"
                except Exception as e:
                    return f"FAILED - Value parameterization failed: {e}"

        # Run concurrent injection attempts
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []

            # Mix of injection attempts
            for i in range(10):
                injection_type = ["table", "column", "value"][i % 3]
                futures.append(executor.submit(try_injection, injection_type))

            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All security checks should pass
        for result in results:
            assert "PASSED" in result, f"Security check failed: {result}"

    def test_error_messages_dont_leak_structure(self):
        """Test that error messages don't reveal database structure."""
        node = BulkCreateNode(
            table_name="test_users",
            database_type="sqlite",
            connection_string="sqlite:///test_dataflow.db",
        )

        # Try various injections and verify error messages are generic
        injection_attempts = [
            {"table": "users; SELECT * FROM sqlite_master;"},
            {"column": "name' FROM test_users;--"},
            {"value": "test'; SELECT password FROM users;--"},
        ]

        for attempt_type, malicious_input in [
            (k, v) for d in injection_attempts for k, v in d.items()
        ]:
            try:
                if attempt_type == "table":
                    BulkCreateNode(
                        table_name=malicious_input,
                        database_type="sqlite",
                        connection_string="sqlite:///test_dataflow.db",
                    )
                elif attempt_type == "column":
                    node._generate_single_insert_sql({malicious_input: "value"})
                else:
                    # This should succeed (parameterized)
                    continue

            except ValueError as e:
                error_msg = str(e)
                # Should not reveal internal structure
                assert "sqlite_master" not in error_msg
                assert "password" not in error_msg
                assert "FROM" not in error_msg.upper()
                # Should have generic message
                assert "Invalid" in error_msg
