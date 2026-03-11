"""
Tier 1 Unit Tests for Safety Validation System

Tests the safety validation components that replace mock implementations
with real database validation for schema integrity and application compatibility.

Core Functionalities Tested:
1. SafetyCheckResult structure and serialization
2. SchemaIntegrityValidator (foreign keys)
3. ApplicationCompatibilityValidator (views)
4. Database type detection
5. Error handling and edge cases
"""

from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataflow.migrations.safety_validation import (
    ApplicationCompatibilityValidator,
    SafetyCheckResult,
    SafetyCheckSeverity,
    SchemaIntegrityValidator,
    validate_migration_safety,
)


class TestSafetyCheckResult:
    """Test SafetyCheckResult dataclass."""

    def test_safety_check_result_creation(self):
        """Test creating SafetyCheckResult with basic fields."""
        result = SafetyCheckResult(
            check_name="test_check",
            passed=True,
            severity=SafetyCheckSeverity.INFO,
            message="Test passed",
        )

        assert result.check_name == "test_check"
        assert result.passed is True
        assert result.severity == SafetyCheckSeverity.INFO
        assert result.message == "Test passed"
        assert result.violations == []
        assert result.warnings == []
        assert result.recommendations == []

    def test_safety_check_result_with_violations(self):
        """Test SafetyCheckResult with violations and recommendations."""
        result = SafetyCheckResult(
            check_name="fk_check",
            passed=False,
            severity=SafetyCheckSeverity.CRITICAL,
            message="Foreign key violations found",
            violations=["FK constraint broken", "Orphaned FK reference"],
            recommendations=["Update FK constraints", "Drop orphaned FKs"],
            affected_objects=["old_table", "new_table"],
        )

        assert result.passed is False
        assert len(result.violations) == 2
        assert len(result.recommendations) == 2
        assert "old_table" in result.affected_objects

    def test_safety_check_result_to_dict(self):
        """Test converting SafetyCheckResult to dictionary."""
        result = SafetyCheckResult(
            check_name="test",
            passed=True,
            severity=SafetyCheckSeverity.HIGH,
            message="Test message",
            violations=["violation1"],
            execution_time_ms=123.45,
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["check_name"] == "test"
        assert result_dict["passed"] is True
        assert result_dict["severity"] == "high"
        assert result_dict["execution_time_ms"] == 123.45
        assert "violation1" in result_dict["violations"]


class TestSchemaIntegrityValidatorUnit:
    """Test SchemaIntegrityValidator with mocked connections."""

    @pytest.mark.asyncio
    async def test_foreign_key_validation_postgresql_success(self):
        """Test PostgreSQL FK validation when no violations."""
        # Mock connection manager
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = SchemaIntegrityValidator(mock_conn_manager, "postgresql")
        result = await validator.validate_foreign_keys("old_table", "new_table")

        assert result.check_name == "foreign_key_constraints"
        assert result.passed is True
        assert result.severity == SafetyCheckSeverity.INFO
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_foreign_key_validation_postgresql_violations(self):
        """Test PostgreSQL FK validation with violations."""
        # Mock connection manager with FK violations
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "constraint_name": "fk_test",
                    "table_name": "other_table",
                    "column_name": "ref_id",
                    "foreign_table_name": "old_table",  # Still references old table!
                    "foreign_column_name": "id",
                }
            ]
        )
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = SchemaIntegrityValidator(mock_conn_manager, "postgresql")
        result = await validator.validate_foreign_keys("old_table", "new_table")

        assert result.check_name == "foreign_key_constraints"
        assert result.passed is False
        assert result.severity == SafetyCheckSeverity.CRITICAL
        assert len(result.violations) > 0
        assert "old_table" in result.violations[0]
        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_foreign_key_validation_sqlite_success(self):
        """Test SQLite FK validation when no violations."""
        # Mock connection manager for SQLite
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()

        # Mock PRAGMA queries
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)  # Old table doesn't exist
        mock_cursor.fetchall = AsyncMock(return_value=[])  # No FKs

        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = SchemaIntegrityValidator(mock_conn_manager, "sqlite")
        result = await validator.validate_foreign_keys("old_table", "new_table")

        assert result.check_name == "foreign_key_constraints"
        assert result.passed is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_foreign_key_validation_unsupported_database(self):
        """Test FK validation with unsupported database type."""
        mock_conn_manager = MagicMock()
        validator = SchemaIntegrityValidator(mock_conn_manager, "mysql")
        result = await validator.validate_foreign_keys("old_table", "new_table")

        assert result.passed is False
        assert result.severity == SafetyCheckSeverity.CRITICAL
        assert "Unsupported database type" in result.message

    @pytest.mark.asyncio
    async def test_foreign_key_validation_database_error(self):
        """Test FK validation handles database errors gracefully."""
        # Mock connection manager that raises error
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=Exception("Connection failed"))
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = SchemaIntegrityValidator(mock_conn_manager, "postgresql")
        result = await validator.validate_foreign_keys("old_table", "new_table")

        assert result.passed is False
        assert result.severity == SafetyCheckSeverity.CRITICAL
        # Database errors are added to violations list
        assert len(result.violations) > 0
        assert "Connection failed" in result.violations[0]


class TestApplicationCompatibilityValidatorUnit:
    """Test ApplicationCompatibilityValidator with mocked connections."""

    @pytest.mark.asyncio
    async def test_view_validation_postgresql_success(self):
        """Test PostgreSQL view validation when no violations."""
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = ApplicationCompatibilityValidator(mock_conn_manager, "postgresql")
        result = await validator.validate_views("old_table", "new_table")

        assert result.check_name == "view_references"
        assert result.passed is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_view_validation_postgresql_violations(self):
        """Test PostgreSQL view validation with violations."""
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "schemaname": "public",
                    "viewname": "test_view",
                    "definition": "SELECT * FROM old_table WHERE id > 0",
                }
            ]
        )
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = ApplicationCompatibilityValidator(mock_conn_manager, "postgresql")
        result = await validator.validate_views("old_table", "new_table")

        assert result.check_name == "view_references"
        assert result.passed is False
        assert result.severity == SafetyCheckSeverity.HIGH
        assert len(result.violations) > 0
        assert "test_view" in result.violations[0]

    @pytest.mark.asyncio
    async def test_view_validation_sqlite_success(self):
        """Test SQLite view validation when no violations."""
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                (
                    "new_table_view",
                    "CREATE VIEW new_table_view AS SELECT * FROM new_table",
                )
            ]
        )

        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        validator = ApplicationCompatibilityValidator(mock_conn_manager, "sqlite")
        result = await validator.validate_views("old_table", "new_table")

        assert result.check_name == "view_references"
        assert result.passed is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_view_validation_unsupported_database(self):
        """Test view validation with unsupported database type."""
        mock_conn_manager = MagicMock()
        validator = ApplicationCompatibilityValidator(mock_conn_manager, "mysql")
        result = await validator.validate_views("old_table", "new_table")

        assert result.passed is False
        assert result.severity == SafetyCheckSeverity.HIGH
        assert "Unsupported database type" in result.message


class TestValidateMigrationSafetyUnit:
    """Test complete migration safety validation."""

    @pytest.mark.asyncio
    async def test_validate_migration_safety_all_checks(self):
        """Test that validate_migration_safety runs all checks."""
        # Mock connection manager
        mock_conn_manager = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_conn_manager.get_connection = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        results = await validate_migration_safety(
            mock_conn_manager, "old_table", "new_table", "postgresql"
        )

        # Should have both check types
        assert "foreign_key_constraints" in results
        assert "view_references" in results

        # Both should be SafetyCheckResult objects
        assert isinstance(results["foreign_key_constraints"], SafetyCheckResult)
        assert isinstance(results["view_references"], SafetyCheckResult)

    @pytest.mark.asyncio
    async def test_validate_migration_safety_with_failures(self):
        """Test validation with failures in some checks."""
        mock_conn_manager = MagicMock()

        # Create separate connection mocks for FK and view validators
        # FK validator connection will return violations
        mock_fk_conn = AsyncMock()
        mock_fk_conn.fetch = AsyncMock(
            return_value=[
                {
                    "constraint_name": "fk_test",
                    "table_name": "other_table",
                    "column_name": "ref_id",
                    "foreign_table_name": "old_table",  # Still references old table
                    "foreign_column_name": "id",
                }
            ]
        )

        # View validator connection will return no violations
        mock_view_conn = AsyncMock()
        mock_view_conn.fetch = AsyncMock(return_value=[])  # No views with old table

        # Return different mocks for each validator
        call_count = [0]

        def get_connection_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: FK validator
                return AsyncMock(__aenter__=AsyncMock(return_value=mock_fk_conn))
            else:
                # Second call: View validator
                return AsyncMock(__aenter__=AsyncMock(return_value=mock_view_conn))

        mock_conn_manager.get_connection = MagicMock(
            side_effect=get_connection_side_effect
        )

        results = await validate_migration_safety(
            mock_conn_manager, "old_table", "new_table", "postgresql"
        )

        # FK check should fail (violations found)
        assert results["foreign_key_constraints"].passed is False
        assert (
            results["foreign_key_constraints"].severity == SafetyCheckSeverity.CRITICAL
        )
        assert len(results["foreign_key_constraints"].violations) > 0

        # View check should pass (no violations)
        assert results["view_references"].passed is True
        assert len(results["view_references"].violations) == 0


class TestSafetyCheckSeverity:
    """Test SafetyCheckSeverity enum."""

    def test_severity_levels(self):
        """Test all severity levels exist."""
        assert SafetyCheckSeverity.CRITICAL.value == "critical"
        assert SafetyCheckSeverity.HIGH.value == "high"
        assert SafetyCheckSeverity.MEDIUM.value == "medium"
        assert SafetyCheckSeverity.LOW.value == "low"
        assert SafetyCheckSeverity.INFO.value == "info"

    def test_severity_comparison(self):
        """Test severity levels can be compared."""
        critical = SafetyCheckSeverity.CRITICAL
        high = SafetyCheckSeverity.HIGH
        info = SafetyCheckSeverity.INFO

        assert critical != high
        assert high != info
        assert critical == SafetyCheckSeverity.CRITICAL
