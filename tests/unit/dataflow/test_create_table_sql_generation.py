"""Unit tests for DataFlow CREATE TABLE SQL generation functionality.

These tests ensure that CREATE TABLE SQL statements are correctly generated
from Python model definitions for different database systems.
"""

import os
import sys
from datetime import datetime
from typing import Optional

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../apps/kailash-dataflow/src")
)

from dataflow import DataFlow


class TestCreateTableSQLGeneration:
    """Test CREATE TABLE SQL generation from Python models."""

    def test_basic_create_table_postgresql(self):
        """Test basic CREATE TABLE generation for PostgreSQL."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str
            age: int
            active: bool = True

        # Generate CREATE TABLE SQL
        sql = db._generate_create_table_sql("User", "postgresql")

        # Verify the SQL structure
        assert "CREATE TABLE users (" in sql
        assert "id SERIAL PRIMARY KEY," in sql
        assert "name VARCHAR(255) NOT NULL" in sql
        assert "email VARCHAR(255) NOT NULL" in sql
        assert "age INTEGER NOT NULL" in sql
        assert "active BOOLEAN DEFAULT TRUE" in sql
        assert "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in sql
        assert "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in sql
        assert sql.endswith(");")

    def test_basic_create_table_mysql(self):
        """Test basic CREATE TABLE generation for MySQL."""
        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float
            in_stock: bool = True

        # Generate CREATE TABLE SQL
        sql = db._generate_create_table_sql("Product", "mysql")

        # Verify MySQL-specific syntax
        assert "CREATE TABLE products (" in sql
        assert "id INT AUTO_INCREMENT PRIMARY KEY," in sql
        assert "name VARCHAR(255) NOT NULL" in sql
        assert "price DOUBLE NOT NULL" in sql
        assert "in_stock TINYINT(1) DEFAULT 1" in sql
        assert "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in sql
        assert (
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            in sql
        )

    def test_basic_create_table_sqlite(self):
        """Test basic CREATE TABLE generation for SQLite."""
        db = DataFlow()

        @db.model
        class Category:
            name: str
            description: Optional[str] = None

        # Generate CREATE TABLE SQL
        sql = db._generate_create_table_sql("Category", "sqlite")

        # Verify SQLite-specific syntax
        assert "CREATE TABLE categorys (" in sql
        assert "id INTEGER PRIMARY KEY AUTOINCREMENT," in sql
        assert "name TEXT NOT NULL" in sql
        assert "description TEXT" in sql
        assert "created_at TEXT DEFAULT CURRENT_TIMESTAMP" in sql
        assert "updated_at TEXT DEFAULT CURRENT_TIMESTAMP" in sql

    def test_create_table_with_optional_fields(self):
        """Test CREATE TABLE with optional fields."""
        db = DataFlow()

        @db.model
        class BlogPost:
            title: str
            content: str
            published: bool = False
            author_id: Optional[int] = None
            tags: Optional[list] = None

        # Generate CREATE TABLE SQL
        sql = db._generate_create_table_sql("BlogPost", "postgresql")

        # Verify optional fields handling
        assert "title VARCHAR(255) NOT NULL" in sql
        assert "content VARCHAR(255) NOT NULL" in sql
        assert "published BOOLEAN DEFAULT FALSE" in sql
        assert "author_id INTEGER" in sql  # Optional, so no NOT NULL
        assert "tags JSONB" in sql  # Optional list

    def test_create_table_complex_types(self):
        """Test CREATE TABLE with complex types (dict, list, datetime)."""
        db = DataFlow()

        @db.model
        class Event:
            name: str
            event_date: datetime
            metadata: dict
            attendees: list
            created_by: int

        # Generate CREATE TABLE SQL for different databases
        postgresql_sql = db._generate_create_table_sql("Event", "postgresql")
        mysql_sql = db._generate_create_table_sql("Event", "mysql")
        sqlite_sql = db._generate_create_table_sql("Event", "sqlite")

        # PostgreSQL should use JSONB for dict/list, TIMESTAMP for datetime
        assert "event_date TIMESTAMP NOT NULL" in postgresql_sql
        assert "metadata JSONB NOT NULL" in postgresql_sql
        assert "attendees JSONB NOT NULL" in postgresql_sql

        # MySQL should use JSON for dict/list, DATETIME for datetime
        assert "event_date DATETIME NOT NULL" in mysql_sql
        assert "metadata JSON NOT NULL" in mysql_sql
        assert "attendees JSON NOT NULL" in mysql_sql

        # SQLite should use TEXT for everything except int
        assert "event_date TEXT NOT NULL" in sqlite_sql
        assert "metadata TEXT NOT NULL" in sqlite_sql
        assert "attendees TEXT NOT NULL" in sqlite_sql

    def test_create_table_error_handling(self):
        """Test error handling for invalid models."""
        db = DataFlow()

        # Test with non-existent model
        with pytest.raises(ValueError, match="No fields found for model"):
            db._generate_create_table_sql("NonExistentModel", "postgresql")

    def test_generate_indexes_sql(self):
        """Test INDEX generation for models."""
        db = DataFlow()

        @db.model
        class Order:
            user_id: int
            total: float
            status: str = "pending"

            # Define custom indexes
            __dataflow__ = {
                "indexes": [
                    {"name": "idx_order_status", "fields": ["status"]},
                    {
                        "name": "idx_order_user_status",
                        "fields": ["user_id", "status"],
                        "unique": False,
                    },
                ]
            }

        # Generate index SQL
        indexes = db._generate_indexes_sql("Order", "postgresql")

        # Should have custom indexes
        assert any(
            "CREATE INDEX idx_order_status ON orders (status);" in idx
            for idx in indexes
        )
        assert any(
            "CREATE INDEX idx_order_user_status ON orders (user_id, status);" in idx
            for idx in indexes
        )

    def test_generate_foreign_key_constraints_sql(self):
        """Test foreign key constraint generation."""
        db = DataFlow()

        # First register the parent model
        @db.model
        class User:
            name: str
            email: str

        # Then register model with foreign key
        @db.model
        class Order:
            user_id: int
            total: float

        # Mock relationship (normally auto-detected)
        if not hasattr(db, "_relationships"):
            db._relationships = {}
        db._relationships["orders"] = {
            "user": {
                "type": "belongs_to",
                "target_table": "users",
                "foreign_key": "user_id",
                "target_key": "id",
            }
        }

        # Generate foreign key constraints
        constraints = db._generate_foreign_key_constraints_sql("Order", "postgresql")

        # Should have foreign key constraint
        assert len(constraints) == 1
        constraint_sql = constraints[0]
        assert "ALTER TABLE orders" in constraint_sql
        assert "ADD CONSTRAINT fk_orders_user_id" in constraint_sql
        assert "FOREIGN KEY (user_id)" in constraint_sql
        assert "REFERENCES users(id)" in constraint_sql

    def test_generate_complete_schema_sql(self):
        """Test complete schema generation for multiple models."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str

        @db.model
        class Order:
            user_id: int
            total: float
            status: str = "pending"

        # Mock relationships
        if not hasattr(db, "_relationships"):
            db._relationships = {}
        db._relationships["orders"] = {
            "user": {
                "type": "belongs_to",
                "target_table": "users",
                "foreign_key": "user_id",
                "target_key": "id",
            }
        }

        # Generate complete schema
        schema_sql = db.generate_complete_schema_sql("postgresql")

        # Should have tables, indexes, and foreign keys
        assert "tables" in schema_sql
        assert "indexes" in schema_sql
        assert "foreign_keys" in schema_sql

        # Should have 2 tables
        assert len(schema_sql["tables"]) == 2

        # Should have table SQL for both models
        table_sqls = "\n".join(schema_sql["tables"])
        assert "CREATE TABLE users" in table_sqls
        assert "CREATE TABLE orders" in table_sqls

        # Should have foreign key constraints
        assert len(schema_sql["foreign_keys"]) >= 1

    def test_create_tables_method(self):
        """Test the create_tables method execution."""
        db = DataFlow()

        @db.model
        class TestModel:
            name: str
            value: int

        # Should not raise any errors
        db.create_tables("postgresql")
        db.create_tables("mysql")
        db.create_tables("sqlite")

    def test_table_naming_conventions(self):
        """Test table naming conventions for different model names."""
        db = DataFlow()

        # Test various class name patterns
        test_cases = [
            ("User", "users"),
            ("Order", "orders"),
            ("OrderItem", "order_items"),
            ("ProductCategory", "product_categorys"),  # Note: simple pluralization
            ("UserProfile", "user_profiles"),
        ]

        for class_name, expected_table in test_cases:
            actual_table = db._class_name_to_table_name(class_name)
            assert actual_table == expected_table

    def test_sql_generation_with_inheritance_models(self):
        """Test SQL generation doesn't break with model inheritance patterns."""
        db = DataFlow()

        @db.model
        class BaseEntity:
            created_by: str
            active: bool = True

        @db.model
        class SpecificEntity:
            name: str
            description: str
            owner_id: int

        # Both models should generate SQL independently
        base_sql = db._generate_create_table_sql("BaseEntity", "postgresql")
        specific_sql = db._generate_create_table_sql("SpecificEntity", "postgresql")

        assert "CREATE TABLE base_entitys" in base_sql
        assert "CREATE TABLE specific_entitys" in specific_sql
        assert "created_by VARCHAR(255) NOT NULL" in base_sql
        assert "name VARCHAR(255) NOT NULL" in specific_sql

    def test_database_specific_column_types(self):
        """Test that column types are correctly adapted for different databases."""
        db = DataFlow()

        @db.model
        class TypeTest:
            text_field: str
            number_field: int
            decimal_field: float
            flag_field: bool
            date_field: datetime
            json_field: dict

        # Test PostgreSQL types
        pg_sql = db._generate_create_table_sql("TypeTest", "postgresql")
        assert "text_field VARCHAR(255)" in pg_sql
        assert "number_field INTEGER" in pg_sql
        assert "decimal_field REAL" in pg_sql
        assert "flag_field BOOLEAN" in pg_sql
        assert "date_field TIMESTAMP" in pg_sql
        assert "json_field JSONB" in pg_sql

        # Test MySQL types
        mysql_sql = db._generate_create_table_sql("TypeTest", "mysql")
        assert "text_field VARCHAR(255)" in mysql_sql
        assert "number_field INT" in mysql_sql
        assert "decimal_field DOUBLE" in mysql_sql
        assert "flag_field TINYINT(1)" in mysql_sql
        assert "date_field DATETIME" in mysql_sql
        assert "json_field JSON" in mysql_sql

        # Test SQLite types
        sqlite_sql = db._generate_create_table_sql("TypeTest", "sqlite")
        assert "text_field TEXT" in sqlite_sql
        assert "number_field INTEGER" in sqlite_sql
        assert "decimal_field REAL" in sqlite_sql
        assert "flag_field INTEGER" in sqlite_sql  # SQLite doesn't have boolean
        assert "date_field TEXT" in sqlite_sql  # SQLite stores dates as text
        assert "json_field TEXT" in sqlite_sql  # SQLite stores JSON as text
