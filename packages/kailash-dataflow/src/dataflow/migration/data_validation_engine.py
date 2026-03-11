"""
Data Validation Engine for Column Datatype Migration.

This engine provides comprehensive validation capabilities for column datatype changes,
ensuring data compatibility and safety before migration execution. It integrates with
the Migration Orchestration Engine to prevent data loss during schema evolution.

Key Features:
- Pre-validates data compatibility for type changes
- Counts incompatible data rows for impact assessment
- Provides detailed validation reports with suggestions
- Integrates with DataFlow's PostgreSQL-first execution model
- Uses DataFlow connection pooling and AsyncSQLDatabaseNode patterns
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(Enum):
    """Categories of validation issues."""

    DATA_COMPATIBILITY = "data_compatibility"
    PRECISION_LOSS = "precision_loss"
    FORMAT_INCOMPATIBILITY = "format_incompatibility"
    NULL_CONSTRAINT = "null_constraint"
    SIZE_CONSTRAINT = "size_constraint"
    RANGE_CONSTRAINT = "range_constraint"


@dataclass
class ValidationIssue:
    """A single validation issue discovered during type conversion analysis."""

    severity: ValidationSeverity
    category: ValidationCategory
    message: str
    affected_rows: int = 0
    suggestion: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSample:
    """Sample of data from column for validation analysis."""

    value: Any
    count: int
    percentage: float
    is_null: bool = False


@dataclass
class ColumnStatistics:
    """Statistical information about a column's data."""

    total_rows: int
    null_count: int
    unique_count: int
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    avg_length: Optional[float] = None
    max_length: Optional[int] = None
    common_patterns: List[str] = field(default_factory=list)
    sample_values: List[DataSample] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of data validation for column type conversion."""

    is_compatible: bool
    total_rows: int
    incompatible_rows: int
    issues: List[ValidationIssue] = field(default_factory=list)
    column_stats: Optional[ColumnStatistics] = None
    recommended_approach: Optional[str] = None
    estimated_conversion_time_ms: int = 0


class DataValidationEngine:
    """
    Engine for validating data compatibility before column type conversions.

    This engine analyzes existing data in a column to determine if it can be
    safely converted to a new datatype, providing detailed reports on any
    potential issues or data loss.
    """

    def __init__(self, connection_string: str):
        """
        Initialize the Data Validation Engine.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string

        # ✅ FIX: Detect async context and use appropriate runtime
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "DataValidationEngine: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "DataValidationEngine: Detected sync context, using LocalRuntime"
            )

        # Detect database type for AsyncSQLDatabaseNode
        from ..adapters.connection_parser import ConnectionParser

        self.database_type = ConnectionParser.detect_database_type(connection_string)

        # Validation configuration
        self.sample_size = 10000  # Number of rows to sample for analysis
        self.analysis_timeout_ms = 30000  # 30 seconds timeout for analysis

        logger.info("Data Validation Engine initialized for PostgreSQL")

    async def validate_type_conversion(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> ValidationResult:
        """
        Validate if a column can be safely converted to a new type.

        Args:
            table_name: Name of the table
            column_name: Name of the column to convert
            old_type: Current column type
            new_type: Target column type

        Returns:
            ValidationResult with compatibility assessment
        """
        try:
            logger.info(
                f"Starting validation for {table_name}.{column_name}: {old_type} -> {new_type}"
            )

            # Step 1: Get column statistics
            column_stats = await self._analyze_column_data(table_name, column_name)

            # If analysis failed (no rows), this indicates an error
            if column_stats.total_rows == 0 and column_stats.null_count == 0:
                # This likely indicates a table/column error - should fail validation
                error_issue = ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    category=ValidationCategory.DATA_COMPATIBILITY,
                    message="Failed to analyze column data - table or column may not exist",
                    suggestion="Verify table and column names exist and are accessible",
                )

                return ValidationResult(
                    is_compatible=False,
                    total_rows=0,
                    incompatible_rows=0,
                    issues=[error_issue],
                )

            # Step 2: Check type compatibility
            compatibility_issues = await self._check_type_compatibility(
                column_stats, old_type, new_type
            )

            # Step 3: Count incompatible data
            incompatible_count = await self.count_incompatible_data(
                table_name, column_name, old_type, new_type
            )

            # Step 4: Generate recommendations
            recommended_approach = self._generate_conversion_recommendation(
                column_stats, old_type, new_type, compatibility_issues
            )

            # Step 5: Estimate conversion time
            estimated_time = self._estimate_conversion_time(
                column_stats, old_type, new_type
            )

            # Determine overall compatibility
            is_compatible = all(
                issue.severity != ValidationSeverity.CRITICAL
                for issue in compatibility_issues
            )

            result = ValidationResult(
                is_compatible=is_compatible,
                total_rows=column_stats.total_rows,
                incompatible_rows=incompatible_count,
                issues=compatibility_issues,
                column_stats=column_stats,
                recommended_approach=recommended_approach,
                estimated_conversion_time_ms=estimated_time,
            )

            logger.info(
                f"Validation completed: {len(compatibility_issues)} issues found, "
                f"{incompatible_count}/{column_stats.total_rows} incompatible rows"
            )

            return result

        except Exception as e:
            logger.error(f"Validation failed for {table_name}.{column_name}: {e}")

            # Return error result
            error_issue = ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                category=ValidationCategory.DATA_COMPATIBILITY,
                message=f"Validation failed: {str(e)}",
                suggestion="Check table and column names, ensure database connectivity",
            )

            return ValidationResult(
                is_compatible=False,
                total_rows=0,
                incompatible_rows=0,
                issues=[error_issue],
            )

    async def count_incompatible_data(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> int:
        """
        Count the number of rows that cannot be converted to the new type.

        Args:
            table_name: Name of the table
            column_name: Name of the column
            old_type: Current column type
            new_type: Target column type

        Returns:
            Number of incompatible rows
        """
        try:
            # Generate validation SQL based on type conversion
            validation_sql = self._generate_compatibility_check_sql(
                table_name, column_name, old_type, new_type
            )

            if not validation_sql:
                logger.warning(
                    f"No validation SQL generated for {old_type} -> {new_type}"
                )
                return 0

            # Execute validation query
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "count_incompatible",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": validation_sql,
                    "timeout_ms": self.analysis_timeout_ms,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use LocalRuntime for validation operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())

            if "count_incompatible" not in results:
                logger.error("Failed to execute incompatible data count query")
                return 0

            result_data = results["count_incompatible"]
            if result_data.get("error"):
                logger.error(f"Query error: {result_data['error']}")
                return 0

            # Extract count from results
            # Handle different result formats
            if "result" in result_data and "data" in result_data["result"]:
                rows = result_data["result"]["data"]
            else:
                rows = result_data.get("rows", [])

            if rows and len(rows) > 0:
                return int(rows[0].get("incompatible_count", 0))

            return 0

        except Exception as e:
            logger.error(f"Failed to count incompatible data: {e}")
            return 0

    async def _analyze_column_data(
        self, table_name: str, column_name: str
    ) -> ColumnStatistics:
        """Analyze column data to gather statistics for validation."""
        try:
            # Generate comprehensive analysis SQL
            analysis_sql = f"""
            WITH column_analysis AS (
                SELECT
                    COUNT(*) as total_rows,
                    COUNT("{column_name}") as non_null_count,
                    COUNT(*) - COUNT("{column_name}") as null_count,
                    COUNT(DISTINCT "{column_name}") as unique_count
                FROM "{table_name}"
            ),
            value_analysis AS (
                SELECT
                    "{column_name}" as value,
                    COUNT(*) as value_count,
                    ROUND(COUNT(*) * 100.0 / (SELECT total_rows FROM column_analysis), 2) as percentage
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
                GROUP BY "{column_name}"
                ORDER BY value_count DESC
                LIMIT 20
            ),
            string_analysis AS (
                SELECT
                    MIN(LENGTH(CAST("{column_name}" AS TEXT))) as min_length,
                    MAX(LENGTH(CAST("{column_name}" AS TEXT))) as max_length,
                    AVG(LENGTH(CAST("{column_name}" AS TEXT))) as avg_length
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
            )
            SELECT
                ca.total_rows,
                ca.null_count,
                ca.unique_count,
                sa.min_length,
                sa.max_length,
                sa.avg_length,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'value', va.value,
                            'count', va.value_count,
                            'percentage', va.percentage
                        )
                        ORDER BY va.value_count DESC
                    ) FILTER (WHERE va.value IS NOT NULL),
                    '[]'::json
                ) as sample_values
            FROM column_analysis ca
            CROSS JOIN string_analysis sa
            LEFT JOIN value_analysis va ON true
            GROUP BY ca.total_rows, ca.null_count, ca.unique_count,
                     sa.min_length, sa.max_length, sa.avg_length
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "analyze_column",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": analysis_sql,
                    "timeout_ms": self.analysis_timeout_ms,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use LocalRuntime for validation operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())

            if "analyze_column" not in results:
                raise Exception("Failed to execute column analysis query")

            result_data = results["analyze_column"]
            if result_data.get("error"):
                raise Exception(f"Query error: {result_data['error']}")

            # Handle different result formats
            if "result" in result_data and "data" in result_data["result"]:
                rows = result_data["result"]["data"]
            else:
                rows = result_data.get("rows", [])

            if not rows:
                logger.error(
                    f"Analysis query returned no rows. Result data: {result_data}"
                )
                raise Exception("No analysis results returned")

            row = rows[0]

            # Parse sample values
            sample_values = []
            if row.get("sample_values"):
                samples_data = row["sample_values"]
                if isinstance(samples_data, str):
                    # Handle JSON string format
                    import json

                    samples_data = json.loads(samples_data)

                if isinstance(samples_data, list):
                    for sample in samples_data:
                        sample_values.append(
                            DataSample(
                                value=sample["value"],
                                count=int(sample["count"]),
                                percentage=float(sample["percentage"]),
                            )
                        )

            stats = ColumnStatistics(
                total_rows=int(row["total_rows"]),
                null_count=int(row["null_count"]),
                unique_count=int(row["unique_count"]),
                avg_length=float(row["avg_length"]) if row["avg_length"] else None,
                max_length=int(row["max_length"]) if row["max_length"] else None,
                sample_values=sample_values,
            )

            logger.debug(
                f"Column analysis completed: {stats.total_rows} rows, "
                f"{stats.null_count} nulls, {stats.unique_count} unique values"
            )

            return stats

        except Exception as e:
            logger.error(f"Column analysis failed: {e}")
            # Return minimal stats on error
            return ColumnStatistics(
                total_rows=0, null_count=0, unique_count=0, sample_values=[]
            )

    async def _check_type_compatibility(
        self, column_stats: ColumnStatistics, old_type: str, new_type: str
    ) -> List[ValidationIssue]:
        """Check compatibility between old and new column types."""
        issues = []

        # Normalize type names for comparison
        old_type_norm = self._normalize_type_name(old_type)
        new_type_norm = self._normalize_type_name(new_type)

        logger.debug(f"Checking compatibility: {old_type_norm} -> {new_type_norm}")

        # Check for potential data loss scenarios
        issues.extend(
            self._check_precision_loss(column_stats, old_type_norm, new_type_norm)
        )
        issues.extend(
            self._check_size_constraints(column_stats, old_type, new_type)
        )  # Use original types for size checking
        issues.extend(
            self._check_null_constraints(column_stats, old_type_norm, new_type_norm)
        )
        issues.extend(
            self._check_format_compatibility(column_stats, old_type_norm, new_type_norm)
        )

        return issues

    def _check_precision_loss(
        self, column_stats: ColumnStatistics, old_type: str, new_type: str
    ) -> List[ValidationIssue]:
        """Check for potential precision loss in numeric conversions."""
        issues = []

        # Numeric type precision mappings
        precision_order = {
            "bigint": 10,
            "int8": 10,
            "integer": 8,
            "int4": 8,
            "int": 8,
            "smallint": 6,
            "int2": 6,
            "decimal": 9,
            "numeric": 9,
            "double precision": 7,
            "float8": 7,
            "real": 5,
            "float4": 5,
            "money": 4,
        }

        old_precision = precision_order.get(old_type, 0)
        new_precision = precision_order.get(new_type, 0)

        if old_precision > new_precision and old_precision > 0 and new_precision > 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.PRECISION_LOSS,
                    message=f"Converting from {old_type} to {new_type} may cause precision loss",
                    affected_rows=column_stats.total_rows - column_stats.null_count,
                    suggestion="Consider using a higher precision type or validate that precision loss is acceptable",
                )
            )

        # Special case: float to integer conversion
        if old_type in [
            "real",
            "double precision",
            "float4",
            "float8",
        ] and new_type in [
            "integer",
            "bigint",
            "smallint",
            "int",
            "int2",
            "int4",
            "int8",
        ]:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.PRECISION_LOSS,
                    message=f"Converting from {old_type} to {new_type} will truncate decimal places",
                    affected_rows=column_stats.total_rows - column_stats.null_count,
                    suggestion="Ensure all values are whole numbers or acceptable for truncation",
                )
            )

        return issues

    def _check_size_constraints(
        self, column_stats: ColumnStatistics, old_type: str, new_type: str
    ) -> List[ValidationIssue]:
        """Check for size constraint violations."""
        issues = []

        # Extract size constraints from type definitions
        old_size = self._extract_type_size(old_type)
        new_size = self._extract_type_size(new_type)

        # Check string length constraints for text-based types
        text_types = ["text", "varchar", "char", "character"]

        old_is_text = (
            any(old_type.lower().startswith(t) for t in text_types)
            or old_type.lower() == "text"
        )
        new_is_text = (
            any(new_type.lower().startswith(t) for t in text_types)
            or new_type.lower() == "text"
        )

        if old_is_text and new_is_text:
            if (
                new_size
                and column_stats.max_length
                and column_stats.max_length > new_size
            ):
                affected_rows = sum(
                    sample.count
                    for sample in column_stats.sample_values
                    if isinstance(sample.value, str)
                    and len(str(sample.value)) > new_size
                )

                # If we couldn't calculate from samples, estimate based on max_length
                if affected_rows == 0 and column_stats.max_length > new_size:
                    affected_rows = max(
                        1, column_stats.total_rows // 10
                    )  # Estimate 10% affected

                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.SIZE_CONSTRAINT,
                        message=f"Some values exceed new type size limit ({new_size} characters)",
                        affected_rows=affected_rows,
                        suggestion=f"Increase target size to at least {column_stats.max_length} characters or truncate data",
                    )
                )

        return issues

    def _check_null_constraints(
        self, column_stats: ColumnStatistics, old_type: str, new_type: str
    ) -> List[ValidationIssue]:
        """Check for NULL constraint violations."""
        issues = []

        # This would be extended to check if new type has NOT NULL constraint
        # For now, just warn about existing nulls if converting to stricter type
        if column_stats.null_count > 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.NULL_CONSTRAINT,
                    message=f"Column contains {column_stats.null_count} NULL values",
                    affected_rows=column_stats.null_count,
                    suggestion="Ensure new type allows NULL values or provide default values",
                )
            )

        return issues

    def _check_format_compatibility(
        self, column_stats: ColumnStatistics, old_type: str, new_type: str
    ) -> List[ValidationIssue]:
        """Check for format compatibility issues."""
        issues = []

        # Check text to date/timestamp conversion
        if old_type in ["text", "varchar", "char"] and new_type in [
            "date",
            "timestamp",
            "timestamptz",
            "time",
        ]:

            # Sample a few values to check format compatibility
            incompatible_samples = []
            for sample in column_stats.sample_values[:5]:  # Check first 5 samples
                if not self._is_valid_date_format(str(sample.value)):
                    incompatible_samples.append(sample.value)

            if incompatible_samples:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FORMAT_INCOMPATIBILITY,
                        message=f"Some text values cannot be converted to {new_type}",
                        suggestion=f"Ensure all values follow valid date format. Examples of incompatible values: {incompatible_samples[:3]}",
                    )
                )

        # Check text to numeric conversion
        if old_type in ["text", "varchar", "char"] and new_type in [
            "integer",
            "bigint",
            "real",
            "double precision",
            "numeric",
            "decimal",
        ]:

            incompatible_samples = []
            for sample in column_stats.sample_values[:5]:
                if not self._is_valid_numeric_format(str(sample.value)):
                    incompatible_samples.append(sample.value)

            if incompatible_samples:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FORMAT_INCOMPATIBILITY,
                        message=f"Some text values cannot be converted to {new_type}",
                        suggestion=f"Ensure all values are valid numbers. Examples of incompatible values: {incompatible_samples[:3]}",
                    )
                )

        return issues

    def _generate_compatibility_check_sql(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> Optional[str]:
        """Generate SQL to check data compatibility for type conversion."""

        old_type_norm = self._normalize_type_name(old_type)
        new_type_norm = self._normalize_type_name(new_type)

        # Text to numeric conversion check
        if old_type_norm in ["text", "varchar", "char"] and new_type_norm in [
            "integer",
            "bigint",
            "real",
            "double precision",
            "numeric",
            "decimal",
        ]:
            return f"""
            SELECT COUNT(*) as incompatible_count
            FROM "{table_name}"
            WHERE "{column_name}" IS NOT NULL
            AND "{column_name}" !~ '^-?[0-9]+\.?[0-9]*$'
            """

        # Text to date conversion check
        if old_type_norm in ["text", "varchar", "char"] and new_type_norm in [
            "date",
            "timestamp",
            "timestamptz",
        ]:
            return f"""
            SELECT COUNT(*) as incompatible_count
            FROM "{table_name}"
            WHERE "{column_name}" IS NOT NULL
            AND "{column_name}" IS NOT NULL
            AND (
                "{column_name}" !~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                OR "{column_name}" !~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}'
            )
            """

        # Size constraint check for string types
        if old_type_norm.startswith(
            ("varchar", "char", "text")
        ) and new_type_norm.startswith(("varchar", "char")):

            new_size = self._extract_type_size(new_type)
            if new_size:
                return f"""
                SELECT COUNT(*) as incompatible_count
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
                AND LENGTH("{column_name}") > {new_size}
                """

        # Default: no incompatible data
        return """
        SELECT 0 as incompatible_count
        """

    def _generate_conversion_recommendation(
        self,
        column_stats: ColumnStatistics,
        old_type: str,
        new_type: str,
        issues: List[ValidationIssue],
    ) -> str:
        """Generate recommendation for handling the type conversion."""

        critical_issues = [
            i for i in issues if i.severity == ValidationSeverity.CRITICAL
        ]
        error_issues = [i for i in issues if i.severity == ValidationSeverity.ERROR]

        if critical_issues:
            return "BLOCKED: Critical issues prevent conversion. Resolve data issues first."

        if error_issues:
            return "MANUAL_INTERVENTION: Errors detected. Clean data or use multi-step conversion."

        warning_issues = [i for i in issues if i.severity == ValidationSeverity.WARNING]
        if warning_issues:
            return (
                "PROCEED_WITH_CAUTION: Warnings detected. Review potential data loss."
            )

        return "SAFE: No issues detected. Conversion can proceed directly."

    def _estimate_conversion_time(
        self, column_stats: ColumnStatistics, old_type: str, new_type: str
    ) -> int:
        """Estimate conversion time in milliseconds."""
        # Base time per row (microseconds)
        base_time_per_row = 0.1

        # Complexity multipliers
        complexity_multiplier = 1.0

        old_type_norm = self._normalize_type_name(old_type)
        new_type_norm = self._normalize_type_name(new_type)

        # String parsing operations are more expensive
        if old_type_norm in ["text", "varchar", "char"] and new_type_norm in [
            "date",
            "timestamp",
            "numeric",
            "integer",
        ]:
            complexity_multiplier = 2.0

        # Large text conversions
        if column_stats.max_length and column_stats.max_length > 1000:
            complexity_multiplier *= 1.5

        estimated_ms = int(
            column_stats.total_rows * base_time_per_row * complexity_multiplier
        )

        # Minimum 100ms, maximum 5 minutes
        return max(100, min(estimated_ms, 300000))

    def _normalize_type_name(self, type_name: str) -> str:
        """Normalize PostgreSQL type names for comparison."""
        type_name = type_name.lower().strip()

        # Handle type aliases
        type_aliases = {
            "int4": "integer",
            "int8": "bigint",
            "int2": "smallint",
            "float4": "real",
            "float8": "double precision",
            "bool": "boolean",
        }

        # Extract base type (remove size specifications)
        base_type = re.sub(r"\([^)]*\)", "", type_name)

        return type_aliases.get(base_type, base_type)

    def _extract_type_size(self, type_name: str) -> Optional[int]:
        """Extract size constraint from type definition."""
        # Handle both simple and complex type specifications
        match = re.search(r"\((\d+)(?:,\d+)?\)", type_name)
        if match:
            return int(match.group(1))
        return None

    def _is_valid_date_format(self, value: str) -> bool:
        """Check if string value can be converted to date."""
        # Simple date format validation
        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",  # YYYY-MM-DD HH:MM:SS
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",  # ISO format
        ]

        return any(re.match(pattern, value.strip()) for pattern in date_patterns)

    def _is_valid_numeric_format(self, value: str) -> bool:
        """Check if string value can be converted to numeric."""
        # Simple numeric format validation
        numeric_pattern = r"^-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$"
        return bool(re.match(numeric_pattern, value.strip()))
