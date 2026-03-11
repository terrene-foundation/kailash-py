"""
Unit tests for the Data Validation Engine.

These tests verify the functionality of the DataValidationEngine for column
datatype migration validation using mocked database interactions.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dataflow.migration.data_validation_engine import (
    ColumnStatistics,
    DataSample,
    DataValidationEngine,
    ValidationCategory,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)


class TestDataValidationEngine:
    """Test suite for DataValidationEngine."""

    @pytest.fixture
    def engine(self):
        """Create a DataValidationEngine instance for testing."""
        return DataValidationEngine("sqlite:///:memory:")

    @pytest.fixture
    def mock_runtime_results(self):
        """Mock runtime results for database queries."""
        return {
            "analyze_column": {
                "rows": [
                    {
                        "total_rows": 1000,
                        "null_count": 50,
                        "unique_count": 800,
                        "min_length": 1,
                        "max_length": 50,
                        "avg_length": 15.5,
                        "sample_values": [
                            {"value": "test_value", "count": 100, "percentage": 10.0},
                            {"value": "another_value", "count": 50, "percentage": 5.0},
                        ],
                    }
                ]
            },
            "count_incompatible": {"rows": [{"incompatible_count": 25}]},
        }

    @pytest.mark.asyncio
    async def test_validate_type_conversion_success(self, engine, mock_runtime_results):
        """Test successful type conversion validation."""
        # The engine creates its own LocalRuntime internally, so we need to patch
        # the LocalRuntime class to intercept the execute call
        with patch(
            "dataflow.migration.data_validation_engine.LocalRuntime"
        ) as mock_runtime_class:
            mock_runtime = Mock()
            mock_runtime.execute.return_value = (mock_runtime_results, "run_id")
            mock_runtime_class.return_value = mock_runtime

            result = await engine.validate_type_conversion(
                "users", "age", "varchar(10)", "integer"
            )

            assert isinstance(result, ValidationResult)
            assert result.total_rows == 1000
            assert result.incompatible_rows == 25
            assert result.column_stats is not None
            assert result.column_stats.total_rows == 1000
            assert result.column_stats.null_count == 50

    @pytest.mark.asyncio
    async def test_validate_type_conversion_with_errors(self, engine):
        """Test type conversion validation with database errors."""
        error_results = {"analyze_column": {"error": "Table does not exist"}}

        with patch.object(
            engine.runtime, "execute", return_value=(error_results, "run_id")
        ):
            result = await engine.validate_type_conversion(
                "nonexistent", "column", "text", "integer"
            )

            assert not result.is_compatible
            assert len(result.issues) == 1
            assert result.issues[0].severity == ValidationSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_count_incompatible_data(self, engine, mock_runtime_results):
        """Test counting incompatible data rows."""
        # The engine creates its own LocalRuntime internally, so we need to patch
        # the LocalRuntime class to intercept the execute call
        with patch(
            "dataflow.migration.data_validation_engine.LocalRuntime"
        ) as mock_runtime_class:
            mock_runtime = Mock()
            mock_runtime.execute.return_value = (mock_runtime_results, "run_id")
            mock_runtime_class.return_value = mock_runtime

            count = await engine.count_incompatible_data(
                "users", "age", "varchar(10)", "integer"
            )

            assert count == 25

    @pytest.mark.asyncio
    async def test_count_incompatible_data_no_sql(self, engine):
        """Test counting incompatible data when no validation SQL is generated."""
        with patch.object(
            engine, "_generate_compatibility_check_sql", return_value=None
        ):
            count = await engine.count_incompatible_data(
                "users", "age", "unknown_type", "another_unknown_type"
            )

            assert count == 0

    @pytest.mark.asyncio
    async def test_analyze_column_data(self, engine, mock_runtime_results):
        """Test column data analysis."""
        # The engine creates its own LocalRuntime internally, so we need to patch
        # the LocalRuntime class to intercept the execute call
        with patch(
            "dataflow.migration.data_validation_engine.LocalRuntime"
        ) as mock_runtime_class:
            mock_runtime = Mock()
            mock_runtime.execute.return_value = (mock_runtime_results, "run_id")
            mock_runtime_class.return_value = mock_runtime

            stats = await engine._analyze_column_data("users", "name")

            assert isinstance(stats, ColumnStatistics)
            assert stats.total_rows == 1000
            assert stats.null_count == 50
            assert stats.unique_count == 800
            assert stats.max_length == 50
            assert len(stats.sample_values) == 2
            assert stats.sample_values[0].value == "test_value"
            assert stats.sample_values[0].count == 100

    @pytest.mark.asyncio
    async def test_analyze_column_data_with_error(self, engine):
        """Test column data analysis with database error."""
        error_results = {"analyze_column": {"error": "Permission denied"}}

        with patch.object(
            engine.runtime, "execute", return_value=(error_results, "run_id")
        ):
            stats = await engine._analyze_column_data("users", "name")

            # Should return minimal stats on error
            assert stats.total_rows == 0
            assert stats.null_count == 0
            assert stats.unique_count == 0

    @pytest.mark.asyncio
    async def test_check_type_compatibility_precision_loss(self, engine):
        """Test type compatibility checking for precision loss."""
        column_stats = ColumnStatistics(
            total_rows=1000, null_count=0, unique_count=1000, max_length=20
        )

        issues = await engine._check_type_compatibility(
            column_stats, "bigint", "integer"
        )

        # Should detect potential precision loss
        precision_issues = [
            i for i in issues if i.category == ValidationCategory.PRECISION_LOSS
        ]
        assert len(precision_issues) > 0
        assert precision_issues[0].severity == ValidationSeverity.WARNING

    @pytest.mark.asyncio
    async def test_check_type_compatibility_size_constraints(self, engine):
        """Test type compatibility checking for size constraints."""
        column_stats = ColumnStatistics(
            total_rows=1000,
            null_count=0,
            unique_count=1000,
            max_length=100,  # Longer than target size
            sample_values=[DataSample(value="a" * 100, count=1, percentage=0.1)],
        )

        issues = await engine._check_type_compatibility(
            column_stats, "text", "varchar(50)"
        )

        # Should detect size constraint violation
        size_issues = [
            i for i in issues if i.category == ValidationCategory.SIZE_CONSTRAINT
        ]
        assert len(size_issues) > 0
        assert size_issues[0].severity == ValidationSeverity.ERROR

    @pytest.mark.asyncio
    async def test_check_type_compatibility_null_constraints(self, engine):
        """Test type compatibility checking for null constraints."""
        column_stats = ColumnStatistics(
            total_rows=1000, null_count=100, unique_count=900  # Has null values
        )

        issues = await engine._check_type_compatibility(column_stats, "text", "integer")

        # Should detect null values
        null_issues = [
            i for i in issues if i.category == ValidationCategory.NULL_CONSTRAINT
        ]
        assert len(null_issues) > 0
        assert null_issues[0].severity == ValidationSeverity.INFO

    @pytest.mark.asyncio
    async def test_check_type_compatibility_format_incompatibility(self, engine):
        """Test type compatibility checking for format incompatibility."""
        column_stats = ColumnStatistics(
            total_rows=1000,
            null_count=0,
            unique_count=1000,
            sample_values=[
                DataSample(value="not_a_number", count=100, percentage=10.0),
                DataSample(value="123", count=900, percentage=90.0),
            ],
        )

        with patch.object(engine, "_is_valid_numeric_format") as mock_numeric:
            mock_numeric.side_effect = lambda x: x == "123"  # Only "123" is valid

            issues = await engine._check_type_compatibility(
                column_stats, "text", "integer"
            )

            # Should detect format incompatibility
            format_issues = [
                i
                for i in issues
                if i.category == ValidationCategory.FORMAT_INCOMPATIBILITY
            ]
            assert len(format_issues) > 0
            assert format_issues[0].severity == ValidationSeverity.ERROR

    def test_check_precision_loss(self, engine):
        """Test precision loss detection."""
        column_stats = ColumnStatistics(
            total_rows=1000, null_count=0, unique_count=1000
        )

        # Test bigint to integer conversion
        issues = engine._check_precision_loss(column_stats, "bigint", "integer")
        assert len(issues) > 0
        assert issues[0].category == ValidationCategory.PRECISION_LOSS

        # Test float to integer conversion
        issues = engine._check_precision_loss(
            column_stats, "double precision", "integer"
        )
        assert len(issues) > 0
        assert "truncate decimal places" in issues[0].message

    def test_check_size_constraints(self, engine):
        """Test size constraint checking."""
        column_stats = ColumnStatistics(
            total_rows=1000,
            null_count=0,
            unique_count=1000,
            max_length=100,
            sample_values=[DataSample(value="a" * 100, count=1, percentage=0.1)],
        )

        issues = engine._check_size_constraints(column_stats, "text", "varchar(50)")
        assert len(issues) > 0
        assert issues[0].category == ValidationCategory.SIZE_CONSTRAINT
        assert issues[0].severity == ValidationSeverity.ERROR

    def test_check_null_constraints(self, engine):
        """Test null constraint checking."""
        column_stats_with_nulls = ColumnStatistics(
            total_rows=1000, null_count=100, unique_count=900
        )

        issues = engine._check_null_constraints(
            column_stats_with_nulls, "text", "integer"
        )
        assert len(issues) > 0
        assert issues[0].category == ValidationCategory.NULL_CONSTRAINT

        column_stats_no_nulls = ColumnStatistics(
            total_rows=1000, null_count=0, unique_count=1000
        )

        issues = engine._check_null_constraints(
            column_stats_no_nulls, "text", "integer"
        )
        assert len(issues) == 0

    def test_check_format_compatibility_text_to_date(self, engine):
        """Test format compatibility for text to date conversion."""
        column_stats = ColumnStatistics(
            total_rows=1000,
            null_count=0,
            unique_count=1000,
            sample_values=[
                DataSample(value="2023-01-01", count=500, percentage=50.0),
                DataSample(value="invalid_date", count=500, percentage=50.0),
            ],
        )

        with patch.object(engine, "_is_valid_date_format") as mock_date:
            mock_date.side_effect = lambda x: x == "2023-01-01"

            issues = engine._check_format_compatibility(column_stats, "text", "date")
            assert len(issues) > 0
            assert issues[0].category == ValidationCategory.FORMAT_INCOMPATIBILITY

    def test_check_format_compatibility_text_to_numeric(self, engine):
        """Test format compatibility for text to numeric conversion."""
        column_stats = ColumnStatistics(
            total_rows=1000,
            null_count=0,
            unique_count=1000,
            sample_values=[
                DataSample(value="123", count=500, percentage=50.0),
                DataSample(value="not_a_number", count=500, percentage=50.0),
            ],
        )

        with patch.object(engine, "_is_valid_numeric_format") as mock_numeric:
            mock_numeric.side_effect = lambda x: x == "123"

            issues = engine._check_format_compatibility(column_stats, "text", "integer")
            assert len(issues) > 0
            assert issues[0].category == ValidationCategory.FORMAT_INCOMPATIBILITY

    def test_generate_compatibility_check_sql_text_to_numeric(self, engine):
        """Test SQL generation for text to numeric compatibility check."""
        sql = engine._generate_compatibility_check_sql(
            "users", "age", "text", "integer"
        )

        assert sql is not None
        assert "incompatible_count" in sql
        assert "users" in sql
        assert "age" in sql
        assert "!~" in sql  # Should use regex for numeric validation

    def test_generate_compatibility_check_sql_text_to_date(self, engine):
        """Test SQL generation for text to date compatibility check."""
        sql = engine._generate_compatibility_check_sql(
            "events", "event_date", "text", "date"
        )

        assert sql is not None
        assert "incompatible_count" in sql
        assert "events" in sql
        assert "event_date" in sql

    def test_generate_compatibility_check_sql_size_constraint(self, engine):
        """Test SQL generation for size constraint check."""
        sql = engine._generate_compatibility_check_sql(
            "users", "name", "text", "varchar(50)"
        )

        assert sql is not None
        assert "LENGTH" in sql
        assert "> 50" in sql

    def test_generate_conversion_recommendation(self, engine):
        """Test conversion recommendation generation."""
        column_stats = ColumnStatistics(
            total_rows=1000, null_count=0, unique_count=1000
        )

        # Test with critical issues
        critical_issue = ValidationIssue(
            severity=ValidationSeverity.CRITICAL,
            category=ValidationCategory.DATA_COMPATIBILITY,
            message="Critical error",
        )

        recommendation = engine._generate_conversion_recommendation(
            column_stats, "text", "integer", [critical_issue]
        )
        assert "BLOCKED" in recommendation

        # Test with error issues
        error_issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FORMAT_INCOMPATIBILITY,
            message="Format error",
        )

        recommendation = engine._generate_conversion_recommendation(
            column_stats, "text", "integer", [error_issue]
        )
        assert "MANUAL_INTERVENTION" in recommendation

        # Test with warnings
        warning_issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            category=ValidationCategory.PRECISION_LOSS,
            message="Precision warning",
        )

        recommendation = engine._generate_conversion_recommendation(
            column_stats, "bigint", "integer", [warning_issue]
        )
        assert "PROCEED_WITH_CAUTION" in recommendation

        # Test with no issues
        recommendation = engine._generate_conversion_recommendation(
            column_stats, "integer", "bigint", []
        )
        assert "SAFE" in recommendation

    def test_estimate_conversion_time(self, engine):
        """Test conversion time estimation."""
        # Small dataset
        small_stats = ColumnStatistics(total_rows=100, null_count=0, unique_count=100)

        time_ms = engine._estimate_conversion_time(small_stats, "integer", "bigint")
        assert time_ms >= 100  # Minimum time
        assert time_ms <= 300000  # Maximum time

        # Large dataset with complex conversion
        large_stats = ColumnStatistics(
            total_rows=1000000,
            null_count=0,
            unique_count=1000000,
            max_length=2000,  # Large text
        )

        time_ms = engine._estimate_conversion_time(large_stats, "text", "date")
        assert time_ms > 1000  # Should be higher for complex conversion
        assert time_ms <= 300000  # But capped at maximum

    def test_normalize_type_name(self, engine):
        """Test type name normalization."""
        assert engine._normalize_type_name("INT4") == "integer"
        assert engine._normalize_type_name("int8") == "bigint"
        assert engine._normalize_type_name("VARCHAR(255)") == "varchar"
        assert engine._normalize_type_name("DOUBLE PRECISION") == "double precision"
        assert engine._normalize_type_name("float4") == "real"

    def test_extract_type_size(self, engine):
        """Test type size extraction."""
        assert engine._extract_type_size("varchar(255)") == 255
        assert engine._extract_type_size("char(10)") == 10
        assert engine._extract_type_size("text") is None
        assert engine._extract_type_size("numeric(10,2)") == 10

    def test_is_valid_date_format(self, engine):
        """Test date format validation."""
        assert engine._is_valid_date_format("2023-01-01")
        assert engine._is_valid_date_format("2023-12-31 23:59:59")
        assert engine._is_valid_date_format("2023-01-01T12:00:00")
        assert not engine._is_valid_date_format("invalid-date")
        assert not engine._is_valid_date_format("2023/01/01")

    def test_is_valid_numeric_format(self, engine):
        """Test numeric format validation."""
        assert engine._is_valid_numeric_format("123")
        assert engine._is_valid_numeric_format("-456")
        assert engine._is_valid_numeric_format("123.456")
        assert engine._is_valid_numeric_format("1.23e10")
        assert engine._is_valid_numeric_format("-.5")
        assert not engine._is_valid_numeric_format("not_a_number")
        assert not engine._is_valid_numeric_format("123.45.67")
