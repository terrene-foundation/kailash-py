#!/usr/bin/env python3
"""
Default Value Strategy Manager for DataFlow NOT NULL Column Addition

Provides comprehensive default value strategies with constraint validation
and performance optimization for bulk operations.

This module implements the strategy pattern for different default value
generation approaches, ensuring safe and efficient NOT NULL column additions.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import asyncpg

from .not_null_handler import (
    ColumnDefinition,
    DefaultValueStrategy,
    DefaultValueType,
    ValidationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class DefaultStrategy:
    """Represents a specific default value strategy configuration."""

    strategy_type: DefaultValueType
    sql_expression: str
    requires_batching: bool = False
    estimated_performance: Optional[Dict[str, Any]] = None
    validation_rules: List[str] = None
    dependencies: List[str] = None

    def __post_init__(self):
        if self.validation_rules is None:
            self.validation_rules = []
        if self.dependencies is None:
            self.dependencies = []


class ConditionalDefaultStrategy(DefaultValueStrategy):
    """Strategy for conditional default values based on existing data."""

    def generate_default_expression(self, column: ColumnDefinition) -> str:
        """Generate SQL for conditional default value."""
        if not hasattr(column, "conditional_rules") or not column.conditional_rules:
            raise ValueError("Conditional strategy requires conditional_rules")

        # Build CASE expression from conditions
        case_parts = ["CASE"]

        for condition, value in column.conditional_rules:
            # Ensure condition is safe SQL
            safe_condition = self._sanitize_condition(condition)
            safe_value = self._format_value_for_type(value, column.data_type)
            case_parts.append(f"WHEN {safe_condition} THEN {safe_value}")

        # Add default case
        if hasattr(column, "default_fallback_value"):
            fallback_value = self._format_value_for_type(
                column.default_fallback_value, column.data_type
            )
            case_parts.append(f"ELSE {fallback_value}")
        else:
            # Use type-appropriate default
            fallback = self._get_type_default(column.data_type)
            case_parts.append(f"ELSE {fallback}")

        case_parts.append("END")
        return " ".join(case_parts)

    def validate_against_constraints(
        self, column: ColumnDefinition, existing_constraints: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate conditional default against constraints."""
        issues = []
        warnings = []

        if not hasattr(column, "conditional_rules") or not column.conditional_rules:
            issues.append("Conditional strategy requires conditional_rules attribute")
            return ValidationResult(is_safe=False, issues=issues, warnings=warnings)

        # Validate each condition
        for i, (condition, value) in enumerate(column.conditional_rules):
            # Basic SQL injection prevention
            if not self._is_safe_condition(condition):
                issues.append(f"Unsafe SQL condition in rule {i}: {condition}")

            # Validate value type compatibility
            try:
                self._format_value_for_type(value, column.data_type)
            except ValueError as e:
                issues.append(f"Value type incompatible in rule {i}: {str(e)}")

        # Warn about performance implications
        if len(column.conditional_rules) > 10:
            warnings.append("Large number of conditions may impact performance")

        # Check for constraint compatibility
        for constraint in existing_constraints:
            if constraint.get("constraint_type") == "CHECK":
                warnings.append(
                    "Manual validation needed for CHECK constraint with conditional logic"
                )

        return ValidationResult(
            is_safe=len(issues) == 0, issues=issues, warnings=warnings
        )

    def estimate_performance_impact(
        self, table_name: str, row_count: int, column: ColumnDefinition
    ) -> Dict[str, Any]:
        """Estimate performance for conditional default."""
        # Conditional logic requires table scan and evaluation
        complexity_factor = len(getattr(column, "conditional_rules", [])) * 0.1
        base_time = 2.0 + complexity_factor
        per_row_time = 0.0002 + (
            complexity_factor * 0.00005
        )  # Additional overhead per condition

        estimated_time = base_time + (row_count * per_row_time)

        return {
            "estimated_seconds": estimated_time,
            "strategy": "batched_update",
            "batch_required": True,
            "recommended_batch_size": 5000,  # Smaller batches due to complexity
            "requires_table_scan": True,
            "complexity_factor": complexity_factor,
        }

    def _sanitize_condition(self, condition: str) -> str:
        """Sanitize SQL condition for safety."""
        # Remove dangerous keywords and patterns
        dangerous_patterns = [
            r"\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)\b",
            r"--",
            r"/\*",
            r"\*/",
            r";",
            r"\bEXEC\b",
            r"\bEXECUTE\b",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, condition, re.IGNORECASE):
                raise ValueError(f"Dangerous SQL pattern detected: {pattern}")

        return condition

    def _is_safe_condition(self, condition: str) -> bool:
        """Check if SQL condition is safe."""
        try:
            self._sanitize_condition(condition)
            return True
        except ValueError:
            return False

    def _format_value_for_type(self, value: Any, data_type: str) -> str:
        """Format value appropriately for SQL and data type."""
        data_type_upper = data_type.upper()

        if value is None:
            return "NULL"
        elif data_type_upper in ["VARCHAR", "TEXT", "CHAR"]:
            return f"'{str(value).replace(chr(39), chr(39)+chr(39))}'"
        elif data_type_upper in ["INTEGER", "INT", "BIGINT", "SMALLINT"]:
            return str(int(value))
        elif data_type_upper in ["BOOLEAN", "BOOL"]:
            return "TRUE" if value else "FALSE"
        elif data_type_upper in ["FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]:
            return str(float(value))
        elif data_type_upper.startswith("TIMESTAMP"):
            if isinstance(value, datetime):
                return f"'{value.isoformat()}'"
            return f"'{str(value)}'"
        else:
            # Generic string handling
            return f"'{str(value).replace(chr(39), chr(39)+chr(39))}'"

    def _get_type_default(self, data_type: str) -> str:
        """Get appropriate default value for data type."""
        data_type_upper = data_type.upper()

        if data_type_upper in ["VARCHAR", "TEXT", "CHAR"]:
            return "''"
        elif data_type_upper in ["INTEGER", "INT", "BIGINT", "SMALLINT"]:
            return "0"
        elif data_type_upper in ["BOOLEAN", "BOOL"]:
            return "FALSE"
        elif data_type_upper in ["FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]:
            return "0.0"
        elif data_type_upper.startswith("TIMESTAMP"):
            return "CURRENT_TIMESTAMP"
        elif data_type_upper == "UUID":
            return "gen_random_uuid()"
        else:
            return "NULL"


class SequenceDefaultStrategy(DefaultValueStrategy):
    """Strategy for sequence-based default values."""

    def generate_default_expression(self, column: ColumnDefinition) -> str:
        """Generate SQL for sequence default value."""
        sequence_name = getattr(column, "sequence_name", None)
        if not sequence_name:
            # Generate sequence name if not provided
            sequence_name = f"{column.name}_seq"

        return f"nextval('{sequence_name}')"

    def validate_against_constraints(
        self, column: ColumnDefinition, existing_constraints: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate sequence default against constraints."""
        issues = []
        warnings = []

        # Check if column type is compatible with sequences
        data_type = column.data_type.upper()
        if data_type not in [
            "INTEGER",
            "INT",
            "BIGINT",
            "SMALLINT",
            "SERIAL",
            "BIGSERIAL",
        ]:
            issues.append(f"Sequence not compatible with type {column.data_type}")

        # Warn about sequence management
        sequence_name = getattr(column, "sequence_name", f"{column.name}_seq")
        warnings.append(
            f"Sequence {sequence_name} must be created and managed separately"
        )

        # Check for unique constraints compatibility
        for constraint in existing_constraints:
            if constraint.get("constraint_type") == "UNIQUE":
                warnings.append(
                    "Sequence values with unique constraints require careful management"
                )

        return ValidationResult(
            is_safe=len(issues) == 0, issues=issues, warnings=warnings
        )

    def estimate_performance_impact(
        self, table_name: str, row_count: int, column: ColumnDefinition
    ) -> Dict[str, Any]:
        """Estimate performance for sequence default."""
        # Sequences are very efficient - single DDL operation
        estimated_time = min(0.2 + (row_count * 0.0000002), 3.0)

        return {
            "estimated_seconds": estimated_time,
            "strategy": "single_ddl",
            "batch_required": False,
            "sequence_dependency": True,
            "requires_sequence_creation": True,
        }


class ForeignKeyDefaultStrategy(DefaultValueStrategy):
    """Strategy for foreign key default values with reference validation."""

    def generate_default_expression(self, column: ColumnDefinition) -> str:
        """Generate SQL for foreign key default value."""
        if not column.foreign_key_reference:
            raise ValueError("Foreign key strategy requires foreign_key_reference")

        # Handle both static default and lookup-based defaults
        if hasattr(column, "fk_lookup_condition"):
            # Dynamic lookup (more complex)
            ref_parts = column.foreign_key_reference.split(".")
            if len(ref_parts) != 2:
                raise ValueError(
                    "Foreign key reference must be in format 'table.column'"
                )

            ref_table, ref_column = ref_parts
            lookup_condition = getattr(column, "fk_lookup_condition")

            return f"(SELECT {ref_column} FROM {ref_table} WHERE {lookup_condition} LIMIT 1)"

        elif column.default_value is not None:
            # Static foreign key value
            return str(column.default_value)

        else:
            raise ValueError(
                "Foreign key strategy requires either default_value or fk_lookup_condition"
            )

    def validate_against_constraints(
        self, column: ColumnDefinition, existing_constraints: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate foreign key default against constraints."""
        issues = []
        warnings = []

        if not column.foreign_key_reference:
            issues.append("Foreign key strategy requires foreign_key_reference")
            return ValidationResult(is_safe=False, issues=issues, warnings=warnings)

        # Validate reference format
        ref_parts = column.foreign_key_reference.split(".")
        if len(ref_parts) != 2:
            issues.append("Foreign key reference must be in format 'table.column'")

        # Validate default value or lookup condition
        has_default = column.default_value is not None
        has_lookup = hasattr(column, "fk_lookup_condition")

        if not has_default and not has_lookup:
            issues.append(
                "Foreign key strategy requires either default_value or fk_lookup_condition"
            )

        if has_lookup:
            lookup_condition = getattr(column, "fk_lookup_condition")
            if not self._is_safe_condition(lookup_condition):
                issues.append(f"Unsafe lookup condition: {lookup_condition}")

        # Warn about referential integrity
        warnings.append(
            "Foreign key defaults require validation that referenced values exist"
        )

        if has_lookup:
            warnings.append("Dynamic foreign key lookup may impact performance")

        return ValidationResult(
            is_safe=len(issues) == 0, issues=issues, warnings=warnings
        )

    def estimate_performance_impact(
        self, table_name: str, row_count: int, column: ColumnDefinition
    ) -> Dict[str, Any]:
        """Estimate performance for foreign key default."""
        has_lookup = hasattr(column, "fk_lookup_condition")

        if has_lookup:
            # Dynamic lookup requires subquery for each row
            base_time = 5.0  # Higher overhead
            per_row_time = 0.001  # 1ms per row for lookup
            estimated_time = base_time + (row_count * per_row_time)

            return {
                "estimated_seconds": estimated_time,
                "strategy": "batched_update",
                "batch_required": True,
                "recommended_batch_size": 1000,  # Small batches due to lookups
                "requires_foreign_table_access": True,
                "lookup_overhead": True,
            }
        else:
            # Static foreign key value
            estimated_time = min(0.5 + (row_count * 0.0000005), 5.0)

            return {
                "estimated_seconds": estimated_time,
                "strategy": "single_ddl",
                "batch_required": row_count > 500000,
                "requires_foreign_key_validation": True,
            }

    def _is_safe_condition(self, condition: str) -> bool:
        """Check if lookup condition is safe."""
        # Similar to ConditionalDefaultStrategy
        dangerous_patterns = [
            r"\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)\b",
            r"--",
            r"/\*",
            r"\*/",
            r";",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, condition, re.IGNORECASE):
                return False
        return True


class DefaultValueStrategyManager:
    """
    Manages multiple default value strategies for NOT NULL column addition.

    Provides strategy selection, validation, and execution coordination
    for various default value generation approaches.
    """

    def __init__(self):
        """Initialize the strategy manager."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Import strategy classes to avoid circular imports
        from .not_null_handler import (
            ComputedDefaultStrategy,
            FunctionDefaultStrategy,
            StaticDefaultStrategy,
        )

        # Initialize all available strategies
        self._strategies = {
            DefaultValueType.STATIC: StaticDefaultStrategy(),
            DefaultValueType.COMPUTED: ComputedDefaultStrategy(),
            DefaultValueType.FUNCTION: FunctionDefaultStrategy(),
            DefaultValueType.CONDITIONAL: ConditionalDefaultStrategy(),
            DefaultValueType.SEQUENCE: SequenceDefaultStrategy(),
            DefaultValueType.FOREIGN_KEY: ForeignKeyDefaultStrategy(),
        }

        self.logger.info(
            f"Initialized DefaultValueStrategyManager with {len(self._strategies)} strategies"
        )

    def get_strategy(self, strategy_type: DefaultValueType) -> DefaultValueStrategy:
        """Get strategy instance for the specified type."""
        if strategy_type not in self._strategies:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        return self._strategies[strategy_type]

    def list_available_strategies(self) -> List[DefaultValueType]:
        """List all available strategy types."""
        return list(self._strategies.keys())

    def static_default(self, value: Any) -> DefaultStrategy:
        """Create static default value strategy."""
        # Determine SQL representation based on value type
        # Note: bool must come before int since bool is subclass of int
        if isinstance(value, bool):
            sql_expr = "TRUE" if value else "FALSE"
        elif isinstance(value, str):
            sql_expr = f"'{value.replace(chr(39), chr(39)+chr(39))}'"
        elif isinstance(value, (int, float, Decimal)):
            sql_expr = str(value)
        elif isinstance(value, datetime):
            sql_expr = f"'{value.isoformat()}'"
        elif isinstance(value, date):
            sql_expr = f"'{value.isoformat()}'"
        elif value is None:
            sql_expr = "NULL"
        else:
            sql_expr = f"'{str(value).replace(chr(39), chr(39)+chr(39))}'"

        return DefaultStrategy(
            strategy_type=DefaultValueType.STATIC,
            sql_expression=sql_expr,
            requires_batching=False,
            estimated_performance={"overhead": "minimal", "fast_path": True},
        )

    def computed_default(
        self, expression: str, context: Dict[str, Any] = None
    ) -> DefaultStrategy:
        """Create computed default value strategy."""
        if context is None:
            context = {}

        # Basic validation of expression
        if not self._validate_sql_expression(expression):
            raise ValueError(f"Invalid or unsafe SQL expression: {expression}")

        # Estimate complexity based on expression
        complexity = self._analyze_expression_complexity(expression, context)

        return DefaultStrategy(
            strategy_type=DefaultValueType.COMPUTED,
            sql_expression=expression,
            requires_batching=complexity.get("requires_batching", True),
            estimated_performance=complexity,
            validation_rules=[
                "expression_safety",
                "column_references",
                "function_availability",
            ],
            dependencies=context.get("dependencies", []),
        )

    def function_default(
        self, function_name: str, args: List[str] = None
    ) -> DefaultStrategy:
        """Create function-based default value strategy."""
        if args is None:
            args = []

        # Build function call expression
        if args:
            args_str = ", ".join(args)
            sql_expr = f"{function_name}({args_str})"
        else:
            # Handle common functions without parentheses
            if function_name.upper() in [
                "CURRENT_TIMESTAMP",
                "CURRENT_DATE",
                "CURRENT_TIME",
            ]:
                sql_expr = function_name.upper()
            else:
                sql_expr = f"{function_name}()"

        # Validate function name
        if not self._is_valid_function_name(function_name):
            raise ValueError(f"Invalid or unsafe function name: {function_name}")

        performance = self._estimate_function_performance(function_name)

        return DefaultStrategy(
            strategy_type=DefaultValueType.FUNCTION,
            sql_expression=sql_expr,
            requires_batching=performance.get("requires_batching", False),
            estimated_performance=performance,
            validation_rules=["function_exists", "parameter_compatibility"],
            dependencies=[function_name],
        )

    def conditional_default(self, conditions: List[Tuple[str, Any]]) -> DefaultStrategy:
        """Create conditional default value strategy."""
        if not conditions:
            raise ValueError("Conditional strategy requires at least one condition")

        # Build CASE expression
        case_parts = ["CASE"]
        dependencies = []

        for condition, value in conditions:
            # Validate condition safety
            if not self._validate_sql_expression(condition):
                raise ValueError(f"Unsafe condition: {condition}")

            # Extract column dependencies
            deps = self._extract_column_dependencies(condition)
            dependencies.extend(deps)

            # Format value appropriately
            if isinstance(value, str):
                formatted_value = f"'{value.replace(chr(39), chr(39)+chr(39))}'"
            else:
                formatted_value = str(value)

            case_parts.append(f"WHEN {condition} THEN {formatted_value}")

        case_parts.append("END")
        sql_expr = " ".join(case_parts)

        return DefaultStrategy(
            strategy_type=DefaultValueType.CONDITIONAL,
            sql_expression=sql_expr,
            requires_batching=True,
            estimated_performance={
                "complexity": "high",
                "requires_table_scan": True,
                "batch_size": 5000,
            },
            validation_rules=[
                "condition_safety",
                "column_references",
                "value_type_compatibility",
            ],
            dependencies=list(set(dependencies)),
        )

    def sequence_default(self, sequence_name: str) -> DefaultStrategy:
        """Create sequence-based default value strategy."""
        if not sequence_name:
            raise ValueError("Sequence name is required")

        # Validate sequence name
        if not self._is_valid_identifier(sequence_name):
            raise ValueError(f"Invalid sequence name: {sequence_name}")

        return DefaultStrategy(
            strategy_type=DefaultValueType.SEQUENCE,
            sql_expression=f"nextval('{sequence_name}')",
            requires_batching=False,
            estimated_performance={"overhead": "minimal", "sequence_dependency": True},
            validation_rules=["sequence_exists", "sequence_permissions"],
            dependencies=[sequence_name],
        )

    def foreign_key_default(
        self,
        reference_table: str,
        reference_column: str,
        lookup_condition: Optional[str] = None,
        static_value: Optional[Any] = None,
    ) -> DefaultStrategy:
        """Create foreign key default value strategy."""
        if not reference_table or not reference_column:
            raise ValueError("Reference table and column are required")

        if lookup_condition and static_value is not None:
            raise ValueError("Cannot specify both lookup_condition and static_value")

        if not lookup_condition and static_value is None:
            raise ValueError("Must specify either lookup_condition or static_value")

        # Validate identifiers
        if not self._is_valid_identifier(reference_table):
            raise ValueError(f"Invalid reference table name: {reference_table}")
        if not self._is_valid_identifier(reference_column):
            raise ValueError(f"Invalid reference column name: {reference_column}")

        if lookup_condition:
            # Dynamic lookup
            if not self._validate_sql_expression(lookup_condition):
                raise ValueError(f"Unsafe lookup condition: {lookup_condition}")

            sql_expr = f"(SELECT {reference_column} FROM {reference_table} WHERE {lookup_condition} LIMIT 1)"
            performance = {
                "complexity": "high",
                "requires_foreign_table_access": True,
                "batch_size": 1000,
            }
            dependencies = [
                reference_table,
                reference_column,
            ] + self._extract_column_dependencies(lookup_condition)
        else:
            # Static value
            sql_expr = str(static_value)
            performance = {"overhead": "minimal", "foreign_key_validation": True}
            dependencies = [reference_table, reference_column]

        return DefaultStrategy(
            strategy_type=DefaultValueType.FOREIGN_KEY,
            sql_expression=sql_expr,
            requires_batching=lookup_condition is not None,
            estimated_performance=performance,
            validation_rules=[
                "foreign_table_exists",
                "foreign_column_exists",
                "referential_integrity",
            ],
            dependencies=dependencies,
        )

    async def validate_strategy_compatibility(
        self,
        strategy: DefaultStrategy,
        column: ColumnDefinition,
        table_constraints: List[Dict[str, Any]],
        connection: Optional[asyncpg.Connection] = None,
    ) -> ValidationResult:
        """Validate strategy compatibility with column and table constraints."""
        strategy_impl = self._strategies[strategy.strategy_type]
        return strategy_impl.validate_against_constraints(column, table_constraints)

    async def estimate_strategy_performance(
        self,
        strategy: DefaultStrategy,
        table_name: str,
        row_count: int,
        column: ColumnDefinition,
        connection: Optional[asyncpg.Connection] = None,
    ) -> Dict[str, Any]:
        """Estimate performance impact of strategy."""
        strategy_impl = self._strategies[strategy.strategy_type]
        return strategy_impl.estimate_performance_impact(table_name, row_count, column)

    def recommend_strategy(
        self,
        column: ColumnDefinition,
        table_info: Dict[str, Any],
        performance_requirements: Optional[Dict[str, Any]] = None,
    ) -> Tuple[DefaultValueType, str]:
        """Recommend optimal strategy based on column and table characteristics."""
        row_count = table_info.get("row_count", 0)
        data_type = column.data_type.upper()

        # Foreign key recommendation has highest priority
        if column.foreign_key_reference:
            return (
                DefaultValueType.FOREIGN_KEY,
                "Foreign key columns require referential integrity",
            )

        # Performance-based recommendations
        if (
            performance_requirements
            and performance_requirements.get("priority") == "speed"
        ):
            if row_count < 1000000:
                return (
                    DefaultValueType.STATIC,
                    "Fast execution for small to medium tables",
                )
            else:
                return (
                    DefaultValueType.FUNCTION,
                    "Functions scale well for large tables",
                )

        # Data-type based recommendations
        if data_type in ["INTEGER", "BIGINT", "SMALLINT"]:
            if column.unique:
                return (
                    DefaultValueType.SEQUENCE,
                    "Unique integers best handled with sequences",
                )
            else:
                return (
                    DefaultValueType.STATIC,
                    "Simple static default for non-unique integers",
                )

        elif data_type.startswith("TIMESTAMP"):
            return (
                DefaultValueType.FUNCTION,
                "CURRENT_TIMESTAMP is optimal for timestamp columns",
            )

        elif data_type == "UUID":
            return (
                DefaultValueType.FUNCTION,
                "UUID generation functions are most appropriate",
            )

        # Default recommendation
        return DefaultValueType.STATIC, "Static defaults are simplest and most reliable"

    # Private helper methods

    def _validate_sql_expression(self, expression: str) -> bool:
        """Validate SQL expression for safety."""
        if not expression or not expression.strip():
            return False

        # Check for dangerous patterns
        dangerous_patterns = [
            r"\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)\b",
            r"\b(SELECT)\b",  # Disallow subqueries in conditions
            r"\b(GRANT|REVOKE)\b",  # Disallow privilege manipulation
            r"\b(ROLE|USER|SUPERUSER)\b",  # Disallow user/role manipulation
            r"--",
            r"/\*",
            r"\*/",
            r";",
            r"\bEXEC\b",
            r"\bEXECUTE\b",
            r"\bxp_cmdshell\b",
            r"\bUNION\b",  # Disallow UNION attacks
            r'OR\s+[\'"]?1[\'"]?\s*=\s*[\'"]?1[\'"]?',  # Classic SQL injection pattern
            r"1\s*=\s*1",  # Simple tautology
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, expression, re.IGNORECASE):
                return False

        return True

    def _analyze_expression_complexity(
        self, expression: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze complexity of SQL expression."""
        complexity_indicators = [
            ("CASE", 2),
            ("WHEN", 1),
            ("SELECT", 5),
            ("JOIN", 10),
            ("SUBQUERY", 8),
            ("FUNCTION", 3),
        ]

        complexity_score = 0
        for indicator, weight in complexity_indicators:
            if indicator.upper() in expression.upper():
                complexity_score += weight

        return {
            "complexity_score": complexity_score,
            "requires_batching": complexity_score
            > 2,  # Lower threshold for computed expressions
            "estimated_overhead": complexity_score * 0.1,
            "recommended_batch_size": max(1000, 10000 - (complexity_score * 1000)),
        }

    def _is_valid_function_name(self, function_name: str) -> bool:
        """Validate function name for safety."""
        if not function_name or not function_name.strip():
            return False

        function_upper = function_name.upper()

        # Blacklist dangerous function names
        dangerous_functions = [
            "DROP",
            "DROP_TABLE",
            "DELETE",
            "TRUNCATE",
            "ALTER",
            "CREATE",
            "INSERT",
            "UPDATE",
            "EXEC",
            "EXECUTE",
            "XP_CMDSHELL",
            "SP_EXECUTESQL",
            "OPENROWSET",
        ]

        if function_upper in dangerous_functions:
            return False

        # Check for dangerous patterns in function name
        if any(danger in function_upper for danger in dangerous_functions):
            return False

        # Allow known safe functions
        safe_functions = [
            "CURRENT_TIMESTAMP",
            "CURRENT_DATE",
            "CURRENT_TIME",
            "NOW",
            "GENERATE_UUID",
            "GEN_RANDOM_UUID",
            "UPPER",
            "LOWER",
            "TRIM",
            "LENGTH",
            "ABS",
            "ROUND",
            "CEIL",
            "FLOOR",
            "COALESCE",
            "NULLIF",
            "SUBSTRING",
            "CONCAT",
        ]

        if function_upper in safe_functions:
            return True

        # Allow user-defined functions that match naming pattern but don't contain dangerous keywords
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", function_name):
            return True

        return False

    def _estimate_function_performance(self, function_name: str) -> Dict[str, Any]:
        """Estimate performance characteristics of function."""
        fast_functions = ["CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"]
        medium_functions = ["NOW", "UPPER", "LOWER", "TRIM", "ABS", "ROUND"]
        slow_functions = ["GENERATE_UUID", "GEN_RANDOM_UUID"]

        function_upper = function_name.upper()

        if function_upper in fast_functions:
            return {
                "category": "fast",
                "overhead": "minimal",
                "requires_batching": False,
            }
        elif function_upper in medium_functions:
            return {"category": "medium", "overhead": "low", "requires_batching": False}
        elif function_upper in slow_functions:
            return {
                "category": "slow",
                "overhead": "moderate",
                "requires_batching": True,
                "recommended_batch_size": 10000,
            }
        else:
            return {
                "category": "unknown",
                "overhead": "unknown",
                "requires_batching": True,
                "recommended_batch_size": 5000,
            }

    def _is_valid_identifier(self, identifier: str) -> bool:
        """Validate SQL identifier (table name, column name, etc.)."""
        if not identifier or not identifier.strip():
            return False

        # SQL identifier pattern
        return re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier) is not None

    def _extract_column_dependencies(self, expression: str) -> List[str]:
        """Extract column names referenced in expression."""
        # Simplified column extraction - in production this would be more sophisticated
        # Look for patterns like word.word or standalone words that could be columns
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"
        matches = re.findall(pattern, expression)

        # Filter out SQL keywords
        sql_keywords = {
            "SELECT",
            "FROM",
            "WHERE",
            "AND",
            "OR",
            "NOT",
            "IN",
            "EXISTS",
            "CASE",
            "WHEN",
            "THEN",
            "ELSE",
            "END",
            "IS",
            "NULL",
            "TRUE",
            "FALSE",
            "LIKE",
            "BETWEEN",
            "ORDER",
            "BY",
            "GROUP",
            "HAVING",
            "LIMIT",
            "OFFSET",
        }

        columns = []
        for match in matches:
            if match.upper() not in sql_keywords:
                columns.append(match)

        return list(set(columns))


# Required strategy classes are imported from not_null_handler in the init method
