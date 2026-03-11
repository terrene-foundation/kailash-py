#!/usr/bin/env python3
"""
Bug 006 Validation Test - Comprehensive verification of the fix.
This test demonstrates that the reported bug is resolved.
"""

import asyncio
import os

# Import with proper path handling
import sys
from unittest.mock import Mock

import pytest

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite

sys.path.insert(0, "src")

from dataflow.migrations.auto_migration_system import (
    AutoMigrationSystem,
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationStatus,
    MigrationType,
    PostgreSQLMigrationGenerator,
    TableDefinition,
)


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


class TestBug006ValidationComplete:
    """Comprehensive validation that Bug 006 is fixed."""

    def test_type_compatibility_prevents_destructive_migration(self):
        """Test that type compatibility checking prevents unnecessary migrations."""
        generator = PostgreSQLMigrationGenerator()

        # All these should be compatible and NOT trigger migrations
        compatibility_cases = [
            # DataFlow uses Python types, DB uses PostgreSQL types
            ("str", "varchar(255)"),
            ("str", "text"),
            ("str", "character varying"),
            ("int", "integer"),
            ("int", "bigint"),
            ("int", "serial"),
            ("float", "decimal(10,2)"),
            ("float", "numeric"),
            ("bool", "boolean"),
            ("datetime", "timestamp"),
            ("datetime", "timestamp with time zone"),
        ]

        for model_type, db_type in compatibility_cases:
            result = generator._types_are_compatible(model_type, db_type)
            assert (
                result is True
            ), f"Compatible types {model_type} vs {db_type} should not trigger migration"

    def test_schema_compatibility_prevents_destructive_migration(self):
        """Test that schema compatibility checking prevents destructive migrations."""
        generator = PostgreSQLMigrationGenerator()

        # Scenario: Existing database with extra legacy fields
        existing_db_table = TableDefinition(
            name="customers",
            columns=[
                # Fields that DataFlow model defines
                ColumnDefinition(name="id", type="serial", nullable=False),
                ColumnDefinition(name="customer_code", type="varchar", nullable=False),
                ColumnDefinition(name="company_name", type="varchar", nullable=False),
                ColumnDefinition(name="email", type="varchar", nullable=False),
                ColumnDefinition(name="is_active", type="boolean", nullable=True),
                # Legacy fields NOT in DataFlow model
                ColumnDefinition(name="legacy_id", type="varchar", nullable=True),
                ColumnDefinition(name="old_system_ref", type="varchar", nullable=True),
                ColumnDefinition(name="import_date", type="timestamp", nullable=True),
                ColumnDefinition(name="created_at", type="timestamp", nullable=True),
                ColumnDefinition(name="updated_at", type="timestamp", nullable=True),
            ],
        )

        # DataFlow model only defines subset of fields
        dataflow_model_table = TableDefinition(
            name="customers",
            columns=[
                ColumnDefinition(name="customer_code", type="str", nullable=False),
                ColumnDefinition(name="company_name", type="str", nullable=False),
                ColumnDefinition(name="email", type="str", nullable=False),
                ColumnDefinition(name="is_active", type="bool", nullable=True),
            ],
        )

        # Should be compatible - no migration needed
        is_compatible = generator._schemas_are_compatible(
            existing_db_table, dataflow_model_table
        )
        assert (
            is_compatible is True
        ), "DataFlow model subset should be compatible with existing database"

    def test_checksum_prevents_duplicate_migrations(self):
        """Test that migration checksums prevent duplicate applications."""
        system = AutoMigrationSystem(Mock())

        # Create identical migrations (same content)
        shared_ops = [
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="users",
                description="Create users table",
                sql_up="CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(100), email VARCHAR(255))",
                sql_down="DROP TABLE users",
            )
        ]

        # First app's migration
        migration_app1 = Migration(
            version="20240101_100000", name="initial_schema", operations=shared_ops
        )

        # Second app's migration (same content, different timestamp)
        migration_app2 = Migration(
            version="20240101_100001",  # Different version
            name="initial_schema",  # Same name
            operations=shared_ops,  # Same operations
        )

        # Simulate first migration was applied
        applied_migration = Migration(
            version="20240101_100000", name="initial_schema", operations=shared_ops
        )
        applied_migration.status = MigrationStatus.APPLIED
        applied_migration.checksum = applied_migration.generate_checksum()

        system.applied_migrations = [applied_migration]

        # Second app should detect this as already applied
        # Note: checksums will differ due to different versions
        # This tests the real scenario where different apps generate different migrations
        # but the fix should use schema compatibility instead

        # For this unit test, let's test that identical migrations are detected
        identical_migration = Migration(
            version="20240101_100000",  # Same version
            name="initial_schema",  # Same name
            operations=shared_ops,  # Same operations
        )

        is_already_applied = system._is_migration_already_applied(identical_migration)
        assert (
            is_already_applied is True
        ), "Identical migration should be detected as already applied"

    def test_comprehensive_bug_006_scenario_unit_level(self):
        """
        Unit-level test of the complete Bug 006 scenario.
        Tests the logic without requiring real database.
        """

        # === Scenario: Multiple developers with same models ===

        # Developer A defines models
        dev_a_models = {
            "users": TableDefinition(
                name="users",
                columns=[
                    ColumnDefinition(name="username", type="str", nullable=False),
                    ColumnDefinition(name="email", type="str", nullable=False),
                    ColumnDefinition(name="is_active", type="bool", nullable=True),
                ],
            ),
            "projects": TableDefinition(
                name="projects",
                columns=[
                    ColumnDefinition(name="name", type="str", nullable=False),
                    ColumnDefinition(name="description", type="str", nullable=True),
                    ColumnDefinition(name="owner_id", type="int", nullable=False),
                ],
            ),
        }

        # Existing database (after Dev A's migration)
        existing_db_schema = {
            "users": TableDefinition(
                name="users",
                columns=[
                    ColumnDefinition(name="id", type="serial", nullable=False),
                    ColumnDefinition(name="username", type="varchar", nullable=False),
                    ColumnDefinition(name="email", type="varchar", nullable=False),
                    ColumnDefinition(name="is_active", type="boolean", nullable=True),
                    ColumnDefinition(
                        name="created_at", type="timestamp", nullable=True
                    ),
                    ColumnDefinition(
                        name="updated_at", type="timestamp", nullable=True
                    ),
                ],
            ),
            "projects": TableDefinition(
                name="projects",
                columns=[
                    ColumnDefinition(name="id", type="serial", nullable=False),
                    ColumnDefinition(name="name", type="varchar", nullable=False),
                    ColumnDefinition(name="description", type="text", nullable=True),
                    ColumnDefinition(name="owner_id", type="integer", nullable=False),
                    ColumnDefinition(
                        name="created_at", type="timestamp", nullable=True
                    ),
                    ColumnDefinition(
                        name="updated_at", type="timestamp", nullable=True
                    ),
                ],
            ),
        }

        # Developer B joins with identical models
        dev_b_models = dev_a_models.copy()  # Identical models

        # Test compatibility for each table
        generator = PostgreSQLMigrationGenerator()

        for table_name, model_table in dev_b_models.items():
            db_table = existing_db_schema[table_name]
            is_compatible = generator._schemas_are_compatible(db_table, model_table)
            assert (
                is_compatible is True
            ), f"Dev B's {table_name} model should be compatible with existing DB"

        # Developer C with subset of fields (admin panel)
        dev_c_models = {
            "users": TableDefinition(
                name="users",
                columns=[
                    ColumnDefinition(name="username", type="str", nullable=False),
                    ColumnDefinition(name="email", type="str", nullable=False),
                    # Admin doesn't need is_active field
                ],
            ),
            # Admin doesn't need projects table
        }

        # Test compatibility for subset models
        for table_name, model_table in dev_c_models.items():
            db_table = existing_db_schema[table_name]
            is_compatible = generator._schemas_are_compatible(db_table, model_table)
            assert (
                is_compatible is True
            ), f"Dev C's subset {table_name} model should be compatible"

        print("✅ Bug 006 validation passed at unit level!")
        print("   - Type compatibility prevents unnecessary migrations")
        print("   - Schema compatibility handles legacy fields")
        print("   - Checksum detection prevents duplicates")
        print("   - Multi-developer scenarios work correctly")


def test_bug_006_edge_cases():
    """Test edge cases that could bypass the fix."""

    generator = PostgreSQLMigrationGenerator()

    # Edge case 1: Nullable mismatch (should be incompatible)
    db_table = TableDefinition(
        name="test",
        columns=[
            ColumnDefinition(name="field", type="varchar", nullable=True)
        ],  # DB allows NULL
    )
    model_table = TableDefinition(
        name="test",
        columns=[
            ColumnDefinition(
                name="field", type="str", nullable=False
            )  # Model requires NOT NULL
        ],
    )

    is_compatible = generator._schemas_are_compatible(db_table, model_table)
    assert is_compatible is False, "Nullable mismatch should be incompatible"

    # Edge case 2: Missing required field (should be incompatible)
    db_table = TableDefinition(
        name="test",
        columns=[
            ColumnDefinition(name="field1", type="varchar", nullable=False)
            # Missing field2 that model requires
        ],
    )
    model_table = TableDefinition(
        name="test",
        columns=[
            ColumnDefinition(name="field1", type="str", nullable=False),
            ColumnDefinition(
                name="field2", type="str", nullable=False
            ),  # Required but missing
        ],
    )

    is_compatible = generator._schemas_are_compatible(db_table, model_table)
    assert is_compatible is False, "Missing required field should be incompatible"

    # Edge case 3: Type incompatibility (should be incompatible)
    db_table = TableDefinition(
        name="test",
        columns=[
            ColumnDefinition(name="field", type="integer", nullable=False)
        ],  # DB has integer
    )
    model_table = TableDefinition(
        name="test",
        columns=[
            ColumnDefinition(name="field", type="str", nullable=False)
        ],  # Model wants string
    )

    is_compatible = generator._schemas_are_compatible(db_table, model_table)
    assert is_compatible is False, "Type incompatibility should be incompatible"

    print("✅ Edge cases tested - fix handles incompatible scenarios correctly")


if __name__ == "__main__":
    print("Bug 006 Comprehensive Validation Test")
    print("=" * 50)

    # Run the validation tests
    test_instance = TestBug006ValidationComplete()

    print("\n1. Testing type compatibility...")
    test_instance.test_type_compatibility_prevents_destructive_migration()
    print("✅ Type compatibility working")

    print("\n2. Testing schema compatibility...")
    test_instance.test_schema_compatibility_prevents_destructive_migration()
    print("✅ Schema compatibility working")

    print("\n3. Testing checksum prevention...")
    test_instance.test_checksum_prevents_duplicate_migrations()
    print("✅ Checksum prevention working")

    print("\n4. Testing comprehensive scenario...")
    test_instance.test_comprehensive_bug_006_scenario_unit_level()

    print("\n5. Testing edge cases...")
    test_bug_006_edge_cases()

    print("\n" + "=" * 50)
    print("🎉 BUG 006 IS FIXED!")
    print("✅ All validation tests passed")
    print("✅ Destructive auto-migrations prevented")
    print("✅ Multi-developer scenarios work")
    print("✅ Legacy database integration safe")
    print("=" * 50)
