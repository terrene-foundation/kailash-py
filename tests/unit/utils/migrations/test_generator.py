"""Unit tests for migration generator."""

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.utils.migrations.generator import MigrationGenerator


class TestMigrationGeneratorInitialization:
    """Test MigrationGenerator initialization."""

    def test_init_with_default_directory(self):
        """Test initialization with default directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "mkdir") as mock_mkdir:
                generator = MigrationGenerator()
                assert generator.migrations_dir == Path("./migrations")
                mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_init_with_custom_directory(self):
        """Test initialization with custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = f"{tmpdir}/my_migrations"
            generator = MigrationGenerator(custom_dir)
            assert generator.migrations_dir == Path(custom_dir)
            assert os.path.exists(custom_dir)

    def test_init_creates_directory_if_not_exists(self):
        """Test that init creates directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations_dir = f"{tmpdir}/new_migrations"
            assert not os.path.exists(migrations_dir)

            generator = MigrationGenerator(migrations_dir)
            assert os.path.exists(migrations_dir)
            assert os.path.isdir(migrations_dir)


class TestGetNextMigrationNumber:
    """Test getting next migration number."""

    def test_get_next_number_empty_directory(self):
        """Test getting next number with no existing migrations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)
            assert generator.get_next_migration_number() == "001"

    def test_get_next_number_with_existing_migrations(self):
        """Test getting next number with existing migrations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            # Create some existing migration files
            Path(f"{tmpdir}/001_initial.py").touch()
            Path(f"{tmpdir}/002_add_users.py").touch()
            Path(f"{tmpdir}/005_add_products.py").touch()

            assert generator.get_next_migration_number() == "006"

    def test_get_next_number_ignores_non_migration_files(self):
        """Test that non-migration files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            # Create various files
            Path(f"{tmpdir}/001_migration.py").touch()
            Path(f"{tmpdir}/test_file.py").touch()
            Path(f"{tmpdir}/__init__.py").touch()
            Path(f"{tmpdir}/abc_not_numbered.py").touch()

            assert generator.get_next_migration_number() == "002"

    def test_get_next_number_handles_gaps(self):
        """Test handling gaps in migration numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            # Create migrations with gaps
            Path(f"{tmpdir}/001_first.py").touch()
            Path(f"{tmpdir}/003_third.py").touch()
            Path(f"{tmpdir}/007_seventh.py").touch()

            assert generator.get_next_migration_number() == "008"


class TestCreateMigration:
    """Test migration creation."""

    def test_create_base_migration(self):
        """Test creating a base migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            filepath = generator.create_migration(
                name="Test Migration",
                description="Test migration description",
                migration_type="base",
            )

            assert os.path.exists(filepath)
            assert filepath.endswith("001_test_migration.py")

            content = Path(filepath).read_text()
            assert "class TestMigration(Migration):" in content
            assert 'id = "001_test_migration"' in content
            assert 'description = "Test migration description"' in content
            assert "async def forward(self, connection):" in content
            assert "async def backward(self, connection):" in content

    def test_create_schema_migration(self):
        """Test creating a schema migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            filepath = generator.create_migration(
                name="Add User Table",
                description="Create user table",
                migration_type="schema",
            )

            content = Path(filepath).read_text()
            assert "CREATE TABLE IF NOT EXISTS example_table" in content
            assert "CREATE INDEX idx_example_name" in content
            assert "DROP TABLE IF EXISTS example_table CASCADE" in content

    def test_create_data_migration(self):
        """Test creating a data migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            filepath = generator.create_migration(
                name="Update User Data",
                description="Update user data in batches",
                migration_type="data",
            )

            content = Path(filepath).read_text()
            assert "class UpdateUserData(DataMigration):" in content
            assert "batch_size = 1000" in content
            assert "SELECT id FROM example_table" in content
            assert "UPDATE example_table" in content

    def test_create_migration_with_dependencies(self):
        """Test creating migration with dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            filepath = generator.create_migration(
                name="dependent_migration",
                description="Migration with dependencies",
                dependencies=["001_initial", "002_add_users"],
            )

            content = Path(filepath).read_text()
            assert 'dependencies = ["001_initial", "002_add_users"]' in content

    def test_name_slugification(self):
        """Test that migration names are properly slugified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            test_cases = [
                ("Test Migration!", "test_migration"),
                ("UPPERCASE NAME", "uppercase_name"),
                ("multiple   spaces", "multiple_spaces"),
                ("special@#$chars", "special_chars"),
                ("__leading_underscores__", "leading_underscores"),
            ]

            for i, (input_name, expected_slug) in enumerate(test_cases):
                filepath = generator.create_migration(
                    name=input_name, description="Test"
                )
                filename = os.path.basename(filepath)
                assert filename == f"{i+1:03d}_{expected_slug}.py"

    def test_sequential_numbering(self):
        """Test that migrations are numbered sequentially."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            # Create multiple migrations
            filepath1 = generator.create_migration("first", "First migration")
            filepath2 = generator.create_migration("second", "Second migration")
            filepath3 = generator.create_migration("third", "Third migration")

            assert "001_first.py" in filepath1
            assert "002_second.py" in filepath2
            assert "003_third.py" in filepath3


class TestClassNameGeneration:
    """Test class name generation from migration ID."""

    def test_class_name_conversion(self):
        """Test converting migration ID to class name."""
        generator = MigrationGenerator()

        test_cases = [
            ("001_initial_migration", "InitialMigration"),
            ("002_add_users", "AddUsers"),
            ("003_create_products_table", "CreateProductsTable"),
            ("004_update_user_emails", "UpdateUserEmails"),
            ("005_single", "Single"),
        ]

        for migration_id, expected_class in test_cases:
            assert generator._class_name(migration_id) == expected_class


class TestCreateInitialMigrations:
    """Test creating initial system migrations."""

    def test_create_initial_migrations(self):
        """Test creating initial migration set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            migrations = generator.create_initial_migrations()

            assert len(migrations) == 3

            # Check first migration
            assert "001_create_users_table.py" in migrations[0]
            content1 = Path(migrations[0]).read_text()
            assert "Create users table for authentication" in content1

            # Check second migration
            assert "002_create_tenants_table.py" in migrations[1]
            content2 = Path(migrations[1]).read_text()
            assert "Create tenants table for multi-tenancy" in content2
            assert '"001_create_users_table"' in content2

            # Check third migration
            assert "003_create_workflow_tables.py" in migrations[2]
            content3 = Path(migrations[2]).read_text()
            assert "Create workflow execution tracking tables" in content3
            assert '"001_create_users_table"' in content3
            assert '"002_create_tenants_table"' in content3


class TestGenerateFromDiff:
    """Test generating migrations from schema differences."""

    def test_generate_from_diff_new_table(self):
        """Test generating migration for new table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            current_schema = {"tables": {}}
            target_schema = {
                "tables": {
                    "users": {
                        "columns": {
                            "id": {"type": "serial", "primary_key": True},
                            "email": {"type": "varchar(255)", "nullable": False},
                        }
                    }
                }
            }

            filepath = generator.generate_from_diff(
                current_schema, target_schema, "add_users", "Add users table"
            )

            content = Path(filepath).read_text()
            assert "CREATE TABLE users" in content
            assert "DROP TABLE IF EXISTS users CASCADE" in content

    def test_generate_from_diff_drop_table(self):
        """Test generating migration for dropping table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            current_schema = {
                "tables": {"old_table": {"columns": {"id": {"type": "serial"}}}}
            }
            target_schema = {"tables": {}}

            operations = generator._analyze_schema_diff(current_schema, target_schema)

            assert len(operations) == 1
            assert operations[0]["type"] == "drop_table"
            assert operations[0]["table"] == "old_table"

    def test_generate_from_diff_add_column(self):
        """Test generating migration for adding column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            current_schema = {
                "tables": {"users": {"columns": {"id": {"type": "serial"}}}}
            }
            target_schema = {
                "tables": {
                    "users": {
                        "columns": {
                            "id": {"type": "serial"},
                            "email": {"type": "varchar(255)"},
                        }
                    }
                }
            }

            operations = generator._analyze_schema_diff(current_schema, target_schema)

            assert len(operations) == 1
            assert operations[0]["type"] == "add_column"
            assert operations[0]["table"] == "users"
            assert operations[0]["column"] == "email"

    def test_generate_from_diff_drop_column(self):
        """Test generating migration for dropping column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            current_schema = {
                "tables": {
                    "users": {
                        "columns": {
                            "id": {"type": "serial"},
                            "deprecated": {"type": "text"},
                        }
                    }
                }
            }
            target_schema = {
                "tables": {"users": {"columns": {"id": {"type": "serial"}}}}
            }

            operations = generator._analyze_schema_diff(current_schema, target_schema)

            assert len(operations) == 1
            assert operations[0]["type"] == "drop_column"
            assert operations[0]["table"] == "users"
            assert operations[0]["column"] == "deprecated"

    def test_analyze_complex_diff(self):
        """Test analyzing complex schema differences."""
        generator = MigrationGenerator()

        current_schema = {
            "tables": {
                "users": {
                    "columns": {
                        "id": {"type": "serial"},
                        "name": {"type": "varchar(100)"},
                    }
                },
                "old_table": {"columns": {"id": {"type": "serial"}}},
            }
        }

        target_schema = {
            "tables": {
                "users": {
                    "columns": {
                        "id": {"type": "serial"},
                        "email": {"type": "varchar(255)"},
                    }
                },
                "products": {
                    "columns": {
                        "id": {"type": "serial"},
                        "name": {"type": "varchar(255)"},
                    }
                },
            }
        }

        operations = generator._analyze_schema_diff(current_schema, target_schema)

        # Should have: create products, drop old_table, add email to users, drop name from users
        op_types = [op["type"] for op in operations]
        assert "create_table" in op_types
        assert "drop_table" in op_types
        assert "add_column" in op_types
        assert "drop_column" in op_types

    def test_generate_diff_migration_content(self):
        """Test generated diff migration content."""
        generator = MigrationGenerator()

        operations = [
            {
                "type": "create_table",
                "table": "test_table",
                "definition": {"columns": {"id": {"type": "serial"}}},
            }
        ]

        content = generator._generate_diff_migration(
            "001_test", "Test migration", operations
        )

        assert "class Test(Migration):" in content
        assert 'id = "001_test"' in content
        assert "CREATE TABLE test_table" in content
        assert "DROP TABLE IF EXISTS test_table CASCADE" in content
        assert "Auto-generated from schema diff" in content


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_migration_name(self):
        """Test handling empty migration name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            # Empty string should still create a valid migration
            filepath = generator.create_migration("", "Empty name test")
            assert os.path.exists(filepath)
            # Should result in just the number
            assert (
                re.match(r"001_\.py$", os.path.basename(filepath))
                or "001.py" in filepath
            )

    def test_very_long_migration_name(self):
        """Test handling very long migration names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            long_name = (
                "this_is_a_very_long_migration_name_" * 5
            )  # Reduced to avoid filesystem limits
            filepath = generator.create_migration(long_name, "Long name test")

            # File should still be created
            assert os.path.exists(filepath)
            # Filename should be reasonable length
            filename = os.path.basename(filepath)
            assert len(filename) < 255  # Most filesystems limit is 255

    def test_unicode_in_migration_name(self):
        """Test handling unicode in migration names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            filepath = generator.create_migration(
                "migration_with_émojis_🎉", "Unicode test"
            )

            assert os.path.exists(filepath)
            # Should be slugified to ASCII
            assert "001_migration_with_mojis" in filepath

    @patch("kailash.utils.migrations.generator.datetime")
    def test_consistent_timestamp_format(self, mock_datetime):
        """Test that timestamps are consistently formatted."""
        mock_now = Mock()
        mock_now.isoformat.return_value = "2024-01-15T10:30:00"
        mock_datetime.now.return_value = mock_now

        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            filepath = generator.create_migration("test", "Test migration")
            content = Path(filepath).read_text()

            assert "Generated on: 2024-01-15T10:30:00" in content

    def test_invalid_migration_type(self):
        """Test handling invalid migration type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MigrationGenerator(tmpdir)

            # Should fall back to base migration
            filepath = generator.create_migration(
                "test", "Test", migration_type="invalid_type"
            )

            content = Path(filepath).read_text()
            # Should use base migration template
            assert "class Test(Migration):" in content
            assert "DataMigration" not in content
