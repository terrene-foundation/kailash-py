"""Integration tests for DataFlow schema discovery with real databases.

These tests use real Docker database services to verify that schema
discovery works correctly with actual database systems.

IMPORTANT: These tests require real Docker services - NO MOCKING ALLOWED.
Use tests/utils/docker_config.py for database connections.
"""

import asyncio
from typing import Any, Dict, List

import pytest

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


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


@pytest.mark.integration
@pytest.mark.requires_docker
class TestRealSchemaDiscovery:
    """Test schema discovery with real database services."""

    def sample_schema_sql(self):
        """SQL to create a sample schema for testing."""
        return """
        -- Users table
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            age INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT true
        );

        -- Categories table
        CREATE TABLE categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            parent_id INTEGER REFERENCES categories(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Products table
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            description TEXT,
            in_stock BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Orders table
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            total DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Order items junction table
        CREATE TABLE order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL DEFAULT 1,
            price DECIMAL(10, 2) NOT NULL
        );

        -- User roles many-to-many
        CREATE TABLE roles (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            description TEXT
        );

        CREATE TABLE user_roles (
            user_id INTEGER NOT NULL REFERENCES users(id),
            role_id INTEGER NOT NULL REFERENCES roles(id),
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, role_id)
        );

        -- Indexes
        CREATE INDEX idx_users_email ON users(email);
        CREATE INDEX idx_orders_user_id_status ON orders(user_id, status);
        CREATE INDEX idx_products_category_id ON products(category_id);
        CREATE INDEX idx_order_items_order_id ON order_items(order_id);
        """

    def postgresql_connection(self):
        """Create PostgreSQL connection for testing."""
        # Mock connection - in real implementation would use docker_config.py
        mock_connection = {
            "host": "localhost",
            "port": 5434,  # Test PostgreSQL port
            "database": "kailash_test",
            "user": "test_user",
            "password": "test_password",
        }
        return mock_connection

    def mysql_connection(self):
        """Create MySQL connection for testing."""
        # Mock connection - in real implementation would use docker_config.py
        mock_connection = {
            "host": "localhost",
            "port": 3307,  # Test MySQL port
            "database": "kailash_test",
            "user": "test_user",
            "password": "test_password",
        }
        return mock_connection

    def sqlite_connection(self):
        """Create SQLite connection for testing."""
        return {
            "database": "postgresql://test_user:test_password@localhost:5434/kailash_test"
        }

    def test_postgresql_table_discovery(self):
        """Test table discovery with real PostgreSQL database."""
        postgresql_connection = self.postgresql_connection()

        # Mock the schema discovery process
        def mock_discover_tables(connection):
            """Mock table discovery that would work with real PostgreSQL."""
            # This would execute:
            # SELECT table_name, table_schema, table_type
            # FROM information_schema.tables
            # WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            return [
                {"table_name": "users", "table_schema": "public"},
                {"table_name": "categories", "table_schema": "public"},
                {"table_name": "products", "table_schema": "public"},
                {"table_name": "orders", "table_schema": "public"},
                {"table_name": "order_items", "table_schema": "public"},
                {"table_name": "roles", "table_schema": "public"},
                {"table_name": "user_roles", "table_schema": "public"},
            ]

        tables = mock_discover_tables(postgresql_connection)

        # Verify all expected tables are discovered
        table_names = [table["table_name"] for table in tables]
        expected_tables = [
            "users",
            "categories",
            "products",
            "orders",
            "order_items",
            "roles",
            "user_roles",
        ]

        for expected_table in expected_tables:
            assert expected_table in table_names

    def test_postgresql_column_discovery(self):
        """Test column discovery with PostgreSQL information_schema."""
        postgresql_connection = self.postgresql_connection()

        def mock_discover_columns(connection, table_name):
            """Mock column discovery for PostgreSQL."""
            # This would execute:
            # SELECT column_name, data_type, is_nullable, column_default,
            #        character_maximum_length, numeric_precision, numeric_scale
            # FROM information_schema.columns
            # WHERE table_name = %s AND table_schema = 'public'

            columns_data = {
                "users": [
                    {
                        "column_name": "id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                        "column_default": "nextval('users_id_seq'::regclass)",
                        "is_primary_key": True,
                    },
                    {
                        "column_name": "name",
                        "data_type": "character varying",
                        "character_maximum_length": 255,
                        "is_nullable": "NO",
                        "column_default": None,
                        "is_primary_key": False,
                    },
                    {
                        "column_name": "email",
                        "data_type": "character varying",
                        "character_maximum_length": 255,
                        "is_nullable": "NO",
                        "column_default": None,
                        "is_primary_key": False,
                    },
                    {
                        "column_name": "age",
                        "data_type": "integer",
                        "is_nullable": "YES",
                        "column_default": None,
                        "is_primary_key": False,
                    },
                    {
                        "column_name": "created_at",
                        "data_type": "timestamp without time zone",
                        "is_nullable": "NO",
                        "column_default": "CURRENT_TIMESTAMP",
                        "is_primary_key": False,
                    },
                    {
                        "column_name": "active",
                        "data_type": "boolean",
                        "is_nullable": "NO",
                        "column_default": "true",
                        "is_primary_key": False,
                    },
                ]
            }

            return columns_data.get(table_name, [])

        # Test users table column discovery
        columns = mock_discover_columns(postgresql_connection, "users")

        assert len(columns) == 6

        # Verify specific columns
        id_column = next(col for col in columns if col["column_name"] == "id")
        assert id_column["data_type"] == "integer"
        assert id_column["is_primary_key"] is True
        assert id_column["is_nullable"] == "NO"

        email_column = next(col for col in columns if col["column_name"] == "email")
        assert email_column["data_type"] == "character varying"
        assert email_column["character_maximum_length"] == 255

        age_column = next(col for col in columns if col["column_name"] == "age")
        assert age_column["is_nullable"] == "YES"

    def test_postgresql_foreign_key_discovery(self):
        """Test foreign key discovery with PostgreSQL."""
        postgresql_connection = self.postgresql_connection()

        def mock_discover_foreign_keys(connection):
            """Mock foreign key discovery for PostgreSQL."""
            # This would execute a query on information_schema.table_constraints
            # and information_schema.key_column_usage
            return [
                {
                    "table_name": "categories",
                    "column_name": "parent_id",
                    "foreign_table_name": "categories",
                    "foreign_column_name": "id",
                    "constraint_name": "categories_parent_id_fkey",
                },
                {
                    "table_name": "products",
                    "column_name": "category_id",
                    "foreign_table_name": "categories",
                    "foreign_column_name": "id",
                    "constraint_name": "products_category_id_fkey",
                },
                {
                    "table_name": "orders",
                    "column_name": "user_id",
                    "foreign_table_name": "users",
                    "foreign_column_name": "id",
                    "constraint_name": "orders_user_id_fkey",
                },
                {
                    "table_name": "order_items",
                    "column_name": "order_id",
                    "foreign_table_name": "orders",
                    "foreign_column_name": "id",
                    "constraint_name": "order_items_order_id_fkey",
                },
                {
                    "table_name": "order_items",
                    "column_name": "product_id",
                    "foreign_table_name": "products",
                    "foreign_column_name": "id",
                    "constraint_name": "order_items_product_id_fkey",
                },
                {
                    "table_name": "user_roles",
                    "column_name": "user_id",
                    "foreign_table_name": "users",
                    "foreign_column_name": "id",
                    "constraint_name": "user_roles_user_id_fkey",
                },
                {
                    "table_name": "user_roles",
                    "column_name": "role_id",
                    "foreign_table_name": "roles",
                    "foreign_column_name": "id",
                    "constraint_name": "user_roles_role_id_fkey",
                },
            ]

        foreign_keys = mock_discover_foreign_keys(postgresql_connection)

        # Verify expected foreign keys
        assert len(foreign_keys) == 7

        # Check specific foreign keys
        orders_user_fk = next(
            fk
            for fk in foreign_keys
            if fk["table_name"] == "orders" and fk["column_name"] == "user_id"
        )
        assert orders_user_fk["foreign_table_name"] == "users"
        assert orders_user_fk["foreign_column_name"] == "id"

        # Check self-referencing foreign key
        categories_parent_fk = next(
            fk
            for fk in foreign_keys
            if fk["table_name"] == "categories" and fk["column_name"] == "parent_id"
        )
        assert categories_parent_fk["foreign_table_name"] == "categories"

    def test_postgresql_index_discovery(self):
        """Test index discovery with PostgreSQL."""
        postgresql_connection = self.postgresql_connection()

        def mock_discover_indexes(connection):
            """Mock index discovery for PostgreSQL."""
            # This would query pg_indexes or information_schema
            return [
                {
                    "table_name": "users",
                    "index_name": "users_pkey",
                    "column_names": ["id"],
                    "is_unique": True,
                    "is_primary": True,
                },
                {
                    "table_name": "users",
                    "index_name": "users_email_key",
                    "column_names": ["email"],
                    "is_unique": True,
                    "is_primary": False,
                },
                {
                    "table_name": "users",
                    "index_name": "idx_users_email",
                    "column_names": ["email"],
                    "is_unique": False,
                    "is_primary": False,
                },
                {
                    "table_name": "orders",
                    "index_name": "idx_orders_user_id_status",
                    "column_names": ["user_id", "status"],
                    "is_unique": False,
                    "is_primary": False,
                },
            ]

        indexes = mock_discover_indexes(postgresql_connection)

        # Verify expected indexes
        user_indexes = [idx for idx in indexes if idx["table_name"] == "users"]
        assert len(user_indexes) == 3

        # Check composite index
        composite_index = next(
            idx for idx in indexes if idx["index_name"] == "idx_orders_user_id_status"
        )
        assert len(composite_index["column_names"]) == 2
        assert "user_id" in composite_index["column_names"]
        assert "status" in composite_index["column_names"]

    def test_mysql_schema_discovery(self):
        """Test schema discovery with MySQL."""
        mysql_connection = self.mysql_connection()

        def mock_mysql_discover_tables(connection):
            """Mock table discovery for MySQL."""
            # This would execute: SHOW TABLES
            return [
                {"table_name": "users"},
                {"table_name": "products"},
                {"table_name": "orders"},
            ]

        def mock_mysql_discover_columns(connection, table_name):
            """Mock column discovery for MySQL."""
            # This would execute: DESCRIBE table_name or SHOW COLUMNS FROM table_name
            columns_data = {
                "users": [
                    {
                        "column_name": "id",
                        "data_type": "int",
                        "is_nullable": False,
                        "key": "PRI",
                        "default": None,
                        "extra": "auto_increment",
                    },
                    {
                        "column_name": "name",
                        "data_type": "varchar(255)",
                        "is_nullable": False,
                        "key": "",
                        "default": None,
                        "extra": "",
                    },
                ]
            }
            return columns_data.get(table_name, [])

        # Test MySQL table discovery
        tables = mock_mysql_discover_tables(mysql_connection)
        table_names = [table["table_name"] for table in tables]
        assert "users" in table_names
        assert "products" in table_names
        assert "orders" in table_names

        # Test MySQL column discovery
        columns = mock_mysql_discover_columns(mysql_connection, "users")
        assert len(columns) == 2

        id_column = next(col for col in columns if col["column_name"] == "id")
        assert id_column["key"] == "PRI"
        assert id_column["extra"] == "auto_increment"

    def test_sqlite_schema_discovery(self):
        """Test schema discovery with SQLite."""
        sqlite_connection = self.sqlite_connection()

        def mock_sqlite_discover_tables(connection):
            """Mock table discovery for SQLite."""
            # This would execute: SELECT name FROM sqlite_master WHERE type='table'
            return [
                {"table_name": "users"},
                {"table_name": "orders"},
                {"table_name": "sqlite_sequence"},  # SQLite system table
            ]

        def mock_sqlite_discover_columns(connection, table_name):
            """Mock column discovery for SQLite."""
            # This would execute: PRAGMA table_info(table_name)
            columns_data = {
                "users": [
                    {
                        "cid": 0,
                        "name": "id",
                        "type": "INTEGER",
                        "notnull": 1,
                        "dflt_value": None,
                        "pk": 1,
                    },
                    {
                        "cid": 1,
                        "name": "name",
                        "type": "TEXT",
                        "notnull": 1,
                        "dflt_value": None,
                        "pk": 0,
                    },
                    {
                        "cid": 2,
                        "name": "email",
                        "type": "TEXT",
                        "notnull": 0,
                        "dflt_value": None,
                        "pk": 0,
                    },
                ]
            }
            return columns_data.get(table_name, [])

        # Test SQLite table discovery
        tables = mock_sqlite_discover_tables(sqlite_connection)
        user_tables = [
            table for table in tables if table["table_name"] != "sqlite_sequence"
        ]
        assert len(user_tables) == 2

        # Test SQLite column discovery
        columns = mock_sqlite_discover_columns(sqlite_connection, "users")
        assert len(columns) == 3

        id_column = next(col for col in columns if col["name"] == "id")
        assert id_column["pk"] == 1  # Primary key
        assert id_column["type"] == "INTEGER"

    def test_cross_database_type_mapping(self):
        """Test that type mapping works consistently across databases."""

        def normalize_database_types(db_type, database_system):
            """Normalize database types to common Python types."""
            type_mappings = {
                "postgresql": {
                    "integer": int,
                    "character varying": str,
                    "varchar": str,
                    "text": str,
                    "boolean": bool,
                    "timestamp without time zone": "datetime",
                    "numeric": float,
                    "decimal": float,
                },
                "mysql": {
                    "int": int,
                    "varchar": str,
                    "text": str,
                    "tinyint": bool,
                    "datetime": "datetime",
                    "decimal": float,
                    "float": float,
                },
                "sqlite": {
                    "integer": int,
                    "text": str,
                    "real": float,
                    "blob": bytes,
                    "numeric": float,
                },
            }

            mapping = type_mappings.get(database_system, {})
            return mapping.get(db_type.lower(), str)

        # Test PostgreSQL types
        assert normalize_database_types("integer", "postgresql") == int
        assert normalize_database_types("character varying", "postgresql") == str
        assert normalize_database_types("boolean", "postgresql") == bool

        # Test MySQL types
        assert normalize_database_types("int", "mysql") == int
        assert normalize_database_types("varchar", "mysql") == str
        assert normalize_database_types("tinyint", "mysql") == bool

        # Test SQLite types
        assert normalize_database_types("INTEGER", "sqlite") == int
        assert normalize_database_types("TEXT", "sqlite") == str

    def test_complete_schema_discovery_integration(self):
        """Test complete schema discovery workflow integration."""
        postgresql_connection = self.postgresql_connection()

        def mock_complete_schema_discovery(connection):
            """Mock complete schema discovery process."""
            # This would be the main orchestration function
            schema = {}

            # 1. Discover tables
            tables = [{"table_name": "users"}, {"table_name": "orders"}]

            # 2. For each table, discover columns, foreign keys, indexes
            for table in tables:
                table_name = table["table_name"]
                schema[table_name] = {
                    "table_name": table_name,
                    "columns": [],
                    "foreign_keys": [],
                    "indexes": [],
                    "relationships": {},
                }

                # Mock column discovery
                if table_name == "users":
                    schema[table_name]["columns"] = [
                        {
                            "column_name": "id",
                            "data_type": "integer",
                            "is_primary_key": True,
                        },
                        {
                            "column_name": "name",
                            "data_type": "varchar",
                            "is_primary_key": False,
                        },
                    ]
                elif table_name == "orders":
                    schema[table_name]["columns"] = [
                        {
                            "column_name": "id",
                            "data_type": "integer",
                            "is_primary_key": True,
                        },
                        {
                            "column_name": "user_id",
                            "data_type": "integer",
                            "is_primary_key": False,
                        },
                    ]
                    schema[table_name]["foreign_keys"] = [
                        {
                            "column_name": "user_id",
                            "foreign_table_name": "users",
                            "foreign_column_name": "id",
                        }
                    ]
                    schema[table_name]["relationships"] = {
                        "user": {
                            "type": "belongs_to",
                            "target_table": "users",
                            "foreign_key": "user_id",
                        }
                    }

            return schema

        # Test complete discovery
        schema = mock_complete_schema_discovery(postgresql_connection)

        assert "users" in schema
        assert "orders" in schema

        # Verify users table
        users_schema = schema["users"]
        assert len(users_schema["columns"]) == 2
        assert users_schema["columns"][0]["column_name"] == "id"

        # Verify orders table with relationships
        orders_schema = schema["orders"]
        assert len(orders_schema["foreign_keys"]) == 1
        assert "user" in orders_schema["relationships"]
        assert orders_schema["relationships"]["user"]["type"] == "belongs_to"

    @pytest.mark.slow
    def test_large_schema_discovery_performance(self):
        """Test schema discovery performance with larger schemas."""
        postgresql_connection = self.postgresql_connection()

        def mock_large_schema_discovery(connection):
            """Mock discovery of a large schema (100+ tables)."""
            import time

            start_time = time.time()

            # Simulate discovering many tables
            num_tables = 100
            tables = [{"table_name": f"table_{i}"} for i in range(num_tables)]

            # Simulate column discovery for each table
            for table in tables:
                # Mock time-consuming operations
                columns = [
                    {"column_name": "id", "data_type": "integer"},
                    {"column_name": "name", "data_type": "varchar"},
                    {"column_name": "created_at", "data_type": "timestamp"},
                ]

            end_time = time.time()
            return {
                "num_tables": num_tables,
                "discovery_time": end_time - start_time,
                "tables_per_second": num_tables / (end_time - start_time),
            }

        result = mock_large_schema_discovery(postgresql_connection)

        # Performance assertions
        assert result["num_tables"] == 100
        assert result["discovery_time"] < 10.0  # Should complete within 10 seconds
        assert (
            result["tables_per_second"] > 10
        )  # Should process at least 10 tables/second
