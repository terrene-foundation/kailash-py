#!/usr/bin/env python3
"""
Tier 1 Unit Tests for Bug 006 Migration Fix
Tests individual component functionality in isolation with mocking allowed.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from dataflow.migrations.auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationStatus,
    MigrationType,
    PostgreSQLMigrationGenerator,
    PostgreSQLSchemaInspector,
    TableDefinition,
)


class TestTypeCompatibilityUnit:
    """Tier 1: Unit tests for type compatibility logic."""

    def test_direct_type_match(self):
        """Test direct type matching works correctly."""
        generator = PostgreSQLMigrationGenerator()

        # Direct matches should work
        assert generator._types_are_compatible("str", "str") is True
        assert generator._types_are_compatible("int", "int") is True
        assert generator._types_are_compatible("bool", "bool") is True

    def test_string_type_compatibility(self):
        """Test string type variations are compatible."""
        generator = PostgreSQLMigrationGenerator()

        test_cases = [
            ("str", "varchar", True),
            ("str", "text", True),
            ("str", "character varying", True),
            ("str", "varchar(255)", True),
            ("string", "varchar", True),
            ("str", "integer", False),  # Incompatible
        ]

        for model_type, db_type, expected in test_cases:
            result = generator._types_are_compatible(model_type, db_type)
            assert result == expected, f"Failed: {model_type} vs {db_type}"

    def test_numeric_type_compatibility(self):
        """Test numeric type variations are compatible."""
        generator = PostgreSQLMigrationGenerator()

        test_cases = [
            ("int", "integer", True),
            ("int", "bigint", True),
            ("int", "smallint", True),
            ("int", "serial", True),
            ("integer", "bigserial", True),
            ("float", "decimal", True),
            ("float", "numeric", True),
            ("float", "real", True),
            ("float", "double precision", True),
            ("int", "varchar", False),  # Incompatible
        ]

        for model_type, db_type, expected in test_cases:
            result = generator._types_are_compatible(model_type, db_type)
            assert result == expected, f"Failed: {model_type} vs {db_type}"

    def test_datetime_type_compatibility(self):
        """Test datetime type variations are compatible."""
        generator = PostgreSQLMigrationGenerator()

        test_cases = [
            ("datetime", "timestamp", True),
            ("datetime", "timestamp with time zone", True),
            ("datetime", "timestamp without time zone", True),
            ("datetime", "timestamptz", True),
            ("date", "date", True),
            ("time", "time", True),
            ("datetime", "varchar", False),  # Incompatible
        ]

        for model_type, db_type, expected in test_cases:
            result = generator._types_are_compatible(model_type, db_type)
            assert result == expected, f"Failed: {model_type} vs {db_type}"


class TestSchemaCompatibilityUnit:
    """Tier 1: Unit tests for schema compatibility logic."""

    def test_compatible_schemas_basic(self):
        """Test basic schema compatibility checking."""
        generator = PostgreSQLMigrationGenerator()

        # Database has more fields than model (common scenario)
        db_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(name="id", type="serial", nullable=False),
                ColumnDefinition(name="username", type="varchar", nullable=False),
                ColumnDefinition(name="email", type="varchar", nullable=False),
                ColumnDefinition(name="is_active", type="boolean", nullable=True),
                ColumnDefinition(name="created_at", type="timestamp", nullable=True),
                ColumnDefinition(name="legacy_field", type="varchar", nullable=True),
            ],
        )

        # Model only defines subset of fields
        model_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(name="username", type="str", nullable=False),
                ColumnDefinition(name="email", type="str", nullable=False),
                ColumnDefinition(name="is_active", type="bool", nullable=True),
            ],
        )

        # Should be compatible
        assert generator._schemas_are_compatible(db_table, model_table) is True

    def test_incompatible_schemas_missing_column(self):
        """Test schema incompatibility when model requires missing column."""
        generator = PostgreSQLMigrationGenerator()

        # Database missing required field
        db_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(name="id", type="serial", nullable=False),
                ColumnDefinition(name="username", type="varchar", nullable=False),
                # Missing email field that model requires
            ],
        )

        model_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(name="username", type="str", nullable=False),
                ColumnDefinition(
                    name="email", type="str", nullable=False
                ),  # Required but missing
            ],
        )

        # Should be incompatible
        assert generator._schemas_are_compatible(db_table, model_table) is False

    def test_incompatible_schemas_nullable_mismatch(self):
        """Test schema incompatibility when nullable constraints don't match."""
        generator = PostgreSQLMigrationGenerator()

        # Database allows NULL but model requires NOT NULL
        db_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(
                    name="username", type="varchar", nullable=True
                ),  # Allows NULL
            ],
        )

        model_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(
                    name="username", type="str", nullable=False
                ),  # Requires NOT NULL
            ],
        )

        # Should be incompatible
        assert generator._schemas_are_compatible(db_table, model_table) is False

    def test_auto_generated_fields_ignored(self):
        """Test that auto-generated fields are ignored in compatibility check."""
        generator = PostgreSQLMigrationGenerator()

        # Database has auto-generated fields
        db_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(name="username", type="varchar", nullable=False),
            ],
        )

        # Model includes auto-generated fields
        model_table = TableDefinition(
            name="users",
            columns=[
                ColumnDefinition(
                    name="id", type="int", nullable=False
                ),  # Auto-generated
                ColumnDefinition(name="username", type="str", nullable=False),
                ColumnDefinition(
                    name="created_at", type="datetime", nullable=True
                ),  # Auto-generated
                ColumnDefinition(
                    name="updated_at", type="datetime", nullable=True
                ),  # Auto-generated
            ],
        )

        # Should be compatible (auto fields ignored)
        assert generator._schemas_are_compatible(db_table, model_table) is True


class TestMigrationChecksumUnit:
    """Tier 1: Unit tests for migration checksum functionality."""

    def test_migration_checksum_already_applied(self):
        """Test checksum detection for already applied migrations."""
        # This tests the logic but uses mocked migration system
        from dataflow.migrations.auto_migration_system import AutoMigrationSystem

        system = AutoMigrationSystem(Mock())

        # Create migration operations that will generate same checksum
        shared_operations = [
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="users",
                description="Create users table",
                sql_up="CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(100))",
                sql_down="DROP TABLE users",
            )
        ]

        # Create a migration
        migration = Migration(
            version="20240101_120000",
            name="test_migration",
            operations=shared_operations,
        )

        # Mock that this migration was already applied with identical content
        applied_migration = Migration(
            version="20240101_120000",  # Same version
            name="test_migration",  # Same name
            operations=shared_operations,  # Same operations = same checksum
        )
        applied_migration.status = MigrationStatus.APPLIED
        # Set the checksum as it would be stored in database
        applied_migration.checksum = applied_migration.generate_checksum()

        system.applied_migrations = [applied_migration]

        # Should detect as already applied (same checksum)
        assert system._is_migration_already_applied(migration) is True

    def test_migration_checksum_not_applied(self):
        """Test checksum detection for new migrations."""
        from dataflow.migrations.auto_migration_system import AutoMigrationSystem

        system = AutoMigrationSystem(Mock())

        # Create a new migration
        migration = Migration(
            version="20240101_120000",
            name="new_migration",
            checksum="xyz789new123",
            operations=[],
        )

        # Mock different migration was applied
        applied_migration = Migration(
            version="20240101_110000",
            name="previous_migration",
            checksum="abc123different",  # Different checksum
            operations=[],
        )
        applied_migration.status = MigrationStatus.APPLIED

        system.applied_migrations = [applied_migration]

        # Should detect as NOT applied
        assert system._is_migration_already_applied(migration) is False

    def test_migration_checksum_failed_status_ignored(self):
        """Test that failed migrations don't prevent re-application."""
        from dataflow.migrations.auto_migration_system import AutoMigrationSystem

        system = AutoMigrationSystem(Mock())

        migration = Migration(
            version="20240101_120000",
            name="retry_migration",
            checksum="retry123def456",
            operations=[],
        )

        # Mock that this migration failed before
        failed_migration = Migration(
            version="20240101_110000",
            name="failed_migration",
            checksum="retry123def456",  # Same checksum
            operations=[],
        )
        failed_migration.status = MigrationStatus.FAILED  # But failed!

        system.applied_migrations = [failed_migration]

        # Should allow re-application (failed status ignored)
        assert system._is_migration_already_applied(migration) is False


if __name__ == "__main__":
    # Run unit tests directly
    pytest.main([__file__, "-v", "--tb=short"])
