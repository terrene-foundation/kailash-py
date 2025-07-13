"""Unit tests for DataFlow CRUD SQL template generation functionality.

These tests ensure that CRUD SQL templates (INSERT, SELECT, UPDATE, DELETE)
are correctly generated from Python model definitions for different database systems.
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


class TestCRUDSQLGeneration:
    """Test CRUD SQL template generation from Python models."""

    def test_insert_sql_postgresql(self):
        """Test INSERT SQL generation for PostgreSQL."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str
            age: int
            active: bool = True

        # Generate INSERT SQL
        sql = db._generate_insert_sql("User", "postgresql")

        # Verify PostgreSQL-specific INSERT syntax
        assert (
            "INSERT INTO users (name, email, age, active) VALUES ($1, $2, $3, $4)"
            in sql
        )
        assert "RETURNING id, created_at, updated_at" in sql

    def test_insert_sql_mysql(self):
        """Test INSERT SQL generation for MySQL."""
        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float
            in_stock: bool = True

        # Generate INSERT SQL
        sql = db._generate_insert_sql("Product", "mysql")

        # Verify MySQL-specific INSERT syntax
        assert sql == "INSERT INTO products (name, price, in_stock) VALUES (%s, %s, %s)"

    def test_insert_sql_sqlite(self):
        """Test INSERT SQL generation for SQLite."""
        db = DataFlow()

        @db.model
        class Order:
            user_id: int
            total: float
            status: str = "pending"

        # Generate INSERT SQL
        sql = db._generate_insert_sql("Order", "sqlite")

        # Verify SQLite-specific INSERT syntax
        assert sql == "INSERT INTO orders (user_id, total, status) VALUES (?, ?, ?)"

    def test_select_sql_postgresql(self):
        """Test SELECT SQL generation for PostgreSQL."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str
            age: int

        # Generate SELECT SQL templates
        sql_templates = db._generate_select_sql("User", "postgresql")

        # Verify all SELECT templates are generated
        assert "select_by_id" in sql_templates
        assert "select_all" in sql_templates
        assert "select_with_filter" in sql_templates
        assert "select_with_pagination" in sql_templates
        assert "count_all" in sql_templates
        assert "count_with_filter" in sql_templates

        # Verify PostgreSQL-specific syntax
        assert (
            sql_templates["select_by_id"]
            == "SELECT id, name, email, age, created_at, updated_at FROM users WHERE id = $1"
        )
        assert (
            sql_templates["select_all"]
            == "SELECT id, name, email, age, created_at, updated_at FROM users"
        )
        assert sql_templates["count_all"] == "SELECT COUNT(*) FROM users"

    def test_select_sql_mysql(self):
        """Test SELECT SQL generation for MySQL."""
        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float

        # Generate SELECT SQL templates
        sql_templates = db._generate_select_sql("Product", "mysql")

        # Verify MySQL-specific syntax
        assert (
            sql_templates["select_by_id"]
            == "SELECT id, name, price, created_at, updated_at FROM products WHERE id = %s"
        )

    def test_select_sql_sqlite(self):
        """Test SELECT SQL generation for SQLite."""
        db = DataFlow()

        @db.model
        class Category:
            name: str
            description: str

        # Generate SELECT SQL templates
        sql_templates = db._generate_select_sql("Category", "sqlite")

        # Verify SQLite-specific syntax
        assert (
            sql_templates["select_by_id"]
            == "SELECT id, name, description, created_at, updated_at FROM categorys WHERE id = ?"
        )

    def test_update_sql_postgresql(self):
        """Test UPDATE SQL generation for PostgreSQL."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        # Generate UPDATE SQL
        sql = db._generate_update_sql("User", "postgresql")

        # Verify PostgreSQL-specific UPDATE syntax
        assert (
            "UPDATE users SET name = $1, email = $2, active = $3, updated_at = CURRENT_TIMESTAMP WHERE id = $4"
            in sql
        )
        assert "RETURNING id, updated_at" in sql

    def test_update_sql_mysql(self):
        """Test UPDATE SQL generation for MySQL."""
        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float

        # Generate UPDATE SQL
        sql = db._generate_update_sql("Product", "mysql")

        # Verify MySQL-specific UPDATE syntax
        assert (
            sql
            == "UPDATE products SET name = %s, price = %s, updated_at = NOW() WHERE id = %s"
        )

    def test_update_sql_sqlite(self):
        """Test UPDATE SQL generation for SQLite."""
        db = DataFlow()

        @db.model
        class Order:
            total: float
            status: str

        # Generate UPDATE SQL
        sql = db._generate_update_sql("Order", "sqlite")

        # Verify SQLite-specific UPDATE syntax
        assert (
            sql
            == "UPDATE orders SET total = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        )

    def test_delete_sql_postgresql(self):
        """Test DELETE SQL generation for PostgreSQL."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str

        # Generate DELETE SQL templates
        sql_templates = db._generate_delete_sql("User", "postgresql")

        # Verify all DELETE templates are generated
        assert "delete_by_id" in sql_templates
        assert "delete_with_filter" in sql_templates
        assert "delete_all" in sql_templates

        # Verify PostgreSQL-specific syntax
        assert sql_templates["delete_by_id"] == "DELETE FROM users WHERE id = $1"
        assert sql_templates["delete_all"] == "DELETE FROM users"

    def test_delete_sql_mysql(self):
        """Test DELETE SQL generation for MySQL."""
        db = DataFlow()

        @db.model
        class Product:
            name: str

        # Generate DELETE SQL templates
        sql_templates = db._generate_delete_sql("Product", "mysql")

        # Verify MySQL-specific syntax
        assert sql_templates["delete_by_id"] == "DELETE FROM products WHERE id = %s"

    def test_delete_sql_sqlite(self):
        """Test DELETE SQL generation for SQLite."""
        db = DataFlow()

        @db.model
        class Category:
            name: str

        # Generate DELETE SQL templates
        sql_templates = db._generate_delete_sql("Category", "sqlite")

        # Verify SQLite-specific syntax
        assert sql_templates["delete_by_id"] == "DELETE FROM categorys WHERE id = ?"

    def test_bulk_sql_postgresql(self):
        """Test bulk operation SQL generation for PostgreSQL."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str

        # Generate bulk SQL templates
        sql_templates = db._generate_bulk_sql("User", "postgresql")

        # Verify PostgreSQL bulk operations
        assert "bulk_insert" in sql_templates
        assert "bulk_update" in sql_templates

        # Verify PostgreSQL-specific UNNEST syntax
        assert (
            "INSERT INTO users (name, email) SELECT UNNEST($1::text[]), UNNEST($2::text[])"
            in sql_templates["bulk_insert"]
        )
        assert "UPDATE users SET" in sql_templates["bulk_update"]
        assert "UNNEST(" in sql_templates["bulk_update"]

    def test_bulk_sql_mysql(self):
        """Test bulk operation SQL generation for MySQL."""
        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float

        # Generate bulk SQL templates
        sql_templates = db._generate_bulk_sql("Product", "mysql")

        # Verify MySQL bulk operations
        assert "bulk_insert" in sql_templates
        assert "bulk_update" in sql_templates

        # Verify MySQL-specific syntax
        assert (
            "INSERT INTO products (name, price) VALUES {values_list}"
            in sql_templates["bulk_insert"]
        )
        assert "ON DUPLICATE KEY UPDATE" in sql_templates["bulk_update"]
        assert "VALUES(name)" in sql_templates["bulk_update"]

    def test_bulk_sql_sqlite(self):
        """Test bulk operation SQL generation for SQLite."""
        db = DataFlow()

        @db.model
        class Order:
            user_id: int
            total: float

        # Generate bulk SQL templates
        sql_templates = db._generate_bulk_sql("Order", "sqlite")

        # Verify SQLite bulk operations
        assert "bulk_insert" in sql_templates
        assert "bulk_upsert" in sql_templates

        # Verify SQLite-specific syntax
        assert (
            "INSERT INTO orders (user_id, total) VALUES {values_list}"
            in sql_templates["bulk_insert"]
        )
        assert "INSERT OR REPLACE INTO orders" in sql_templates["bulk_upsert"]

    def test_generate_all_crud_sql(self):
        """Test comprehensive CRUD SQL generation."""
        db = DataFlow()

        @db.model
        class User:
            name: str
            email: str
            age: Optional[int] = None
            active: bool = True

        # Generate all CRUD SQL
        all_sql = db.generate_all_crud_sql("User", "postgresql")

        # Verify all operation types are included
        assert "insert" in all_sql
        assert "select" in all_sql
        assert "update" in all_sql
        assert "delete" in all_sql
        assert "bulk" in all_sql

        # Verify structure of each operation
        assert isinstance(all_sql["insert"], str)
        assert isinstance(all_sql["select"], dict)
        assert isinstance(all_sql["update"], str)
        assert isinstance(all_sql["delete"], dict)
        assert isinstance(all_sql["bulk"], dict)

    def test_complex_model_sql_generation(self):
        """Test SQL generation for complex models with various field types."""
        db = DataFlow()

        @db.model
        class Event:
            title: str
            description: Optional[str] = None
            start_date: datetime
            end_date: Optional[datetime] = None
            attendee_count: int = 0
            is_public: bool = False
            metadata: dict
            tags: list

        # Generate CRUD SQL for PostgreSQL
        pg_sql = db.generate_all_crud_sql("Event", "postgresql")

        # Verify INSERT handles all field types
        insert_sql = pg_sql["insert"]
        assert "INSERT INTO events" in insert_sql
        assert (
            "title, description, start_date, end_date, attendee_count, is_public, metadata, tags"
            in insert_sql
        )
        assert "RETURNING id, created_at, updated_at" in insert_sql

        # Verify SELECT includes all columns
        select_sql = pg_sql["select"]["select_all"]
        assert (
            "id, title, description, start_date, end_date, attendee_count, is_public, metadata, tags, created_at, updated_at"
            in select_sql
        )

        # Verify UPDATE handles all fields
        update_sql = pg_sql["update"]
        assert "SET title = $1, description = $2, start_date = $3" in update_sql

    def test_sql_generation_field_exclusion(self):
        """Test that auto-generated fields are properly excluded from certain operations."""
        db = DataFlow()

        @db.model
        class TestModel:
            name: str
            value: int

        # Generate SQL templates
        all_sql = db.generate_all_crud_sql("TestModel", "postgresql")

        # INSERT should exclude id, created_at, updated_at
        insert_sql = all_sql["insert"]
        assert "id" not in insert_sql.split("(")[1].split(")")[0]  # Not in column list
        assert "created_at" not in insert_sql.split("(")[1].split(")")[0]
        assert "updated_at" not in insert_sql.split("(")[1].split(")")[0]

        # SELECT should include all columns
        select_sql = all_sql["select"]["select_all"]
        assert "id" in select_sql
        assert "created_at" in select_sql
        assert "updated_at" in select_sql

        # UPDATE should exclude id, created_at but handle updated_at
        update_sql = all_sql["update"]
        # Check that id is not in the SET clause (before WHERE)
        set_portion = update_sql.split("WHERE")[0]
        assert "id =" not in set_portion  # id should not be in SET clause
        assert "created_at =" not in set_portion
        assert (
            "updated_at =" in set_portion
            or "updated_at = CURRENT_TIMESTAMP" in set_portion
        )  # but updated_at should be set

    def test_sql_generation_error_handling(self):
        """Test error handling in SQL generation."""
        db = DataFlow()

        # Test with non-existent model - should return empty fields and handle gracefully
        try:
            result = db._generate_insert_sql("NonExistentModel", "postgresql")
            # If it doesn't raise an error, it should at least return valid SQL with no fields
            assert "NonExistentModel" not in result or "()" in result
        except (KeyError, ValueError, AttributeError):
            # These are acceptable errors for non-existent models
            pass

    def test_database_specific_parameter_placeholders(self):
        """Test that parameter placeholders are database-specific."""
        db = DataFlow()

        @db.model
        class TestModel:
            field1: str
            field2: int
            field3: bool

        # Test PostgreSQL uses $1, $2, $3
        pg_insert = db._generate_insert_sql("TestModel", "postgresql")
        assert "$1, $2, $3" in pg_insert

        pg_select = db._generate_select_sql("TestModel", "postgresql")
        assert "$1" in pg_select["select_by_id"]

        pg_update = db._generate_update_sql("TestModel", "postgresql")
        assert "$1" in pg_update and "$2" in pg_update and "$3" in pg_update

        # Test MySQL uses %s
        mysql_insert = db._generate_insert_sql("TestModel", "mysql")
        assert "%s, %s, %s" in mysql_insert

        mysql_select = db._generate_select_sql("TestModel", "mysql")
        assert "%s" in mysql_select["select_by_id"]

        # Test SQLite uses ?
        sqlite_insert = db._generate_insert_sql("TestModel", "sqlite")
        assert "?, ?, ?" in sqlite_insert

        sqlite_select = db._generate_select_sql("TestModel", "sqlite")
        assert "?" in sqlite_select["select_by_id"]

    def test_sql_generation_with_empty_model(self):
        """Test SQL generation gracefully handles models with minimal fields."""
        db = DataFlow()

        @db.model
        class MinimalModel:
            name: str

        # Should generate valid SQL even with just one field
        all_sql = db.generate_all_crud_sql("MinimalModel", "postgresql")

        # Verify basic structure
        assert "INSERT INTO minimal_models (name) VALUES ($1)" in all_sql["insert"]
        assert (
            "SELECT id, name, created_at, updated_at FROM minimal_models"
            in all_sql["select"]["select_all"]
        )
        assert "UPDATE minimal_models SET name = $1" in all_sql["update"]
