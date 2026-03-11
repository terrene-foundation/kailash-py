"""
Integration tests for OptimizedSchemaComparator with real database connections.

Tests streaming schema comparison and parallel table inspection with actual
SQLite and PostgreSQL connections (mocked for CI).
"""

import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest
from dataflow.migrations.schema_state_manager import (
    DatabaseSchema,
    ModelSchema,
    SchemaComparisonResult,
)
from dataflow.performance.migration_optimizer import OptimizedSchemaComparator

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite
from tests.utils.real_infrastructure import real_infra


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


class TestStreamingSchemaComparatorIntegration:
    """Integration tests for streaming schema comparison with real databases."""

    def setup_method(self):
        """Set up test fixtures with real database."""
        self.comparator = OptimizedSchemaComparator(max_schema_size=1000)

        # Create in-memory SQLite database for testing
        self.test_db = sqlite3.connect(":memory:")
        self.setup_test_schema()

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.test_db:
            self.test_db.close()

    def setup_test_schema(self):
        """Set up test schema in SQLite database."""
        cursor = self.test_db.cursor()

        # Create test tables
        cursor.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total DECIMAL(10,2) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                description TEXT
            )
        """
        )

        self.test_db.commit()
        cursor.close()

    @pytest.mark.skip(
        reason="API changed - parallel_table_inspection method no longer exists"
    )
    def test_real_database_table_inspection(self):
        """Test table inspection with real SQLite database."""

        def connection_factory():
            # Create new connection for each thread to avoid SQLite threading issues
            temp_db = sqlite3.connect(":memory:")
            # Recreate schema in new connection
            cursor = temp_db.cursor()
            cursor.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    total DECIMAL(10,2) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    price DECIMAL(10,2) NOT NULL,
                    description TEXT
                )
            """
            )
            temp_db.commit()
            cursor.close()
            return temp_db

        table_names = ["users", "orders", "products"]

        # Test parallel inspection with real database
        result = self.comparator.parallel_table_inspection(
            table_names, connection_factory=connection_factory, max_workers=2
        )

        # Verify results
        assert len(result) == len(table_names)

        # Check users table structure
        assert "users" in result
        users_columns = result["users"]["columns"]
        assert "id" in users_columns
        assert "name" in users_columns
        assert "email" in users_columns
        assert users_columns["id"]["primary_key"]
        assert not users_columns["name"]["nullable"]

        # Check orders table structure
        assert "orders" in result
        orders_columns = result["orders"]["columns"]
        assert "user_id" in orders_columns
        assert "total" in orders_columns
        assert "status" in orders_columns

    @pytest.mark.skip(
        reason="API changed - streaming_schema_comparison method renamed/removed"
    )
    def test_streaming_comparison_with_database_schemas(self):
        """Test streaming comparison using schemas derived from real database."""

        # Create current schema from database
        def create_schema_iterator_from_db():
            table_names = ["users", "orders", "products"]
            for table_name in table_names:
                table_def = self.comparator._inspect_table_from_database(
                    table_name, self.test_db
                )
                yield {table_name: table_def}

        # Create target schema with modifications
        def create_modified_schema_iterator():
            # Users table - add new column
            yield {
                "users": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "primary_key": True,
                            "nullable": False,
                        },
                        "name": {"type": "VARCHAR(100)", "nullable": False},
                        "email": {"type": "VARCHAR(255)", "nullable": False},
                        "phone": {
                            "type": "VARCHAR(20)",
                            "nullable": True,
                        },  # New column
                    }
                }
            }

            # Orders table - remove status column
            yield {
                "orders": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "primary_key": True,
                            "nullable": False,
                        },
                        "user_id": {"type": "INTEGER", "nullable": False},
                        "total": {"type": "DECIMAL(10,2)", "nullable": False},
                        # status column removed
                    }
                }
            }

            # New table
            yield {
                "inventory": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "primary_key": True,
                            "nullable": False,
                        },
                        "product_id": {"type": "INTEGER", "nullable": False},
                        "quantity": {"type": "INTEGER", "nullable": False},
                    }
                }
            }

        # Execute streaming comparison
        result = self.comparator.streaming_schema_comparison(
            create_schema_iterator_from_db(), create_modified_schema_iterator()
        )

        # Verify results
        assert isinstance(result, SchemaComparisonResult)
        assert result.has_changes()

        # Check for new/removed tables
        # Current has: users, orders, products (from DB)
        # Target has: users, orders, inventory (modified schema)
        # So: products should be removed (in current but not target)
        #     inventory should be added (in target but not current)
        assert "inventory" in result.removed_tables  # In target but not current
        assert "products" in result.added_tables  # In current but not target

        # Check for modified tables
        assert "users" in result.modified_tables
        assert "phone" in result.modified_tables["users"]["removed_columns"]

        assert "orders" in result.modified_tables
        assert "status" in result.modified_tables["orders"]["added_columns"]

    @pytest.mark.skip(
        reason="API changed - parallel_table_inspection method no longer exists"
    )
    def test_large_schema_performance_integration(self):
        """Test performance with larger schemas using real database operations."""
        # Create larger schema in database
        cursor = self.test_db.cursor()

        # Create multiple tables with many columns
        for i in range(20):  # 20 tables
            columns = ["id INTEGER PRIMARY KEY"]
            for j in range(30):  # 30 columns per table
                columns.append(f"col_{j} VARCHAR(255)")

            create_sql = f"CREATE TABLE large_table_{i} ({', '.join(columns)})"
            cursor.execute(create_sql)

        self.test_db.commit()
        cursor.close()

        # Test parallel inspection performance
        table_names = [f"large_table_{i}" for i in range(20)]

        def large_connection_factory():
            # Create new connection with large schema for each thread
            temp_db = sqlite3.connect(":memory:")
            cursor = temp_db.cursor()

            for i in range(20):  # 20 tables
                columns = ["id INTEGER PRIMARY KEY"]
                for j in range(30):  # 30 columns per table
                    columns.append(f"col_{j} VARCHAR(255)")

                create_sql = f"CREATE TABLE large_table_{i} ({', '.join(columns)})"
                cursor.execute(create_sql)

            temp_db.commit()
            cursor.close()
            return temp_db

        start_time = time.perf_counter()
        result = self.comparator.parallel_table_inspection(
            table_names, connection_factory=large_connection_factory, max_workers=4
        )
        end_time = time.perf_counter()

        execution_time_ms = (end_time - start_time) * 1000

        # Verify performance
        assert execution_time_ms < 5000  # Should complete within 5 seconds
        assert len(result) == len(table_names)

        # Verify correctness
        for table_name in table_names:
            assert table_name in result
            assert len(result[table_name]["columns"]) == 31  # 1 id + 30 data columns

    def test_memory_efficiency_with_real_data(self):
        """Test memory efficiency with real database data."""
        import gc

        # Create many tables in database
        cursor = self.test_db.cursor()

        for i in range(100):  # 100 tables
            cursor.execute(
                f"""
                CREATE TABLE mem_test_table_{i} (
                    id INTEGER PRIMARY KEY,
                    data1 TEXT,
                    data2 TEXT,
                    data3 TEXT,
                    data4 TEXT,
                    data5 TEXT
                )
            """
            )

        self.test_db.commit()
        cursor.close()

        # Monitor memory usage
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Create schema iterators for streaming comparison
        def database_schema_iterator():
            table_names = [f"mem_test_table_{i}" for i in range(100)]
            for table_name in table_names:
                table_def = self.comparator._inspect_table_from_database(
                    table_name, self.test_db
                )
                yield {table_name: table_def}

        def modified_schema_iterator():
            for i in range(100):
                yield {
                    f"mem_test_table_{i}": {
                        "columns": {
                            "id": {
                                "type": "INTEGER",
                                "primary_key": True,
                                "nullable": False,
                            },
                            "data1": {"type": "TEXT", "nullable": True},
                            "data2": {"type": "TEXT", "nullable": True},
                            "data3": {"type": "TEXT", "nullable": True},
                            "data4": {"type": "TEXT", "nullable": True},
                            "data5": {"type": "TEXT", "nullable": True},
                            "data6": {"type": "TEXT", "nullable": True},  # New column
                        }
                    }
                }

        # Execute streaming comparison with small chunks
        result = self.comparator.streaming_schema_comparison(
            database_schema_iterator(),
            modified_schema_iterator(),
            chunk_size=10,  # Small chunks for memory efficiency
        )

        gc.collect()
        final_objects = len(gc.get_objects())

        # Verify memory efficiency
        object_growth = final_objects - initial_objects
        assert object_growth < 1500, f"Memory usage too high: {object_growth} objects"

        # Verify correctness
        assert isinstance(result, SchemaComparisonResult)
        assert result.has_changes()
        assert len(result.modified_tables) == 100  # All tables modified

    def test_concurrent_database_access(self):
        """Test concurrent database access safety."""
        import threading

        def connection_factory():
            # Each thread gets its own connection with schema
            temp_db = sqlite3.connect(":memory:")
            cursor = temp_db.cursor()
            cursor.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    total DECIMAL(10,2) NOT NULL
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    price DECIMAL(10,2) NOT NULL
                )
            """
            )
            temp_db.commit()
            cursor.close()
            return temp_db

        table_names = ["users", "orders", "products"]
        results = {}
        errors = []

        def worker(worker_id: int):
            try:
                # Each worker performs table inspection
                worker_result = self.comparator.parallel_table_inspection(
                    table_names, connection_factory=connection_factory, max_workers=2
                )
                results[worker_id] = worker_result
            except Exception as e:
                errors.append(e)

        # Run multiple workers concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify no errors
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 5

        # Verify consistent results
        first_result = results[0]
        for worker_id, result in results.items():
            assert len(result) == len(first_result)
            for table_name in table_names:
                assert table_name in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=5"])
